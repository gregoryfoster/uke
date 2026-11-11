"""Text-to-speech engines with an on-disk cache.

Every clip is cached as a loudness-normalized 24 kHz mono WAV, keyed by engine, voice, rate and text,
so a rebuild only synthesizes new or changed text. Japanese is always synthesized from kana.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

RATE = 24000
NORMALIZE = "loudnorm=I=-16:TP=-1.5:LRA=11"
CACHE_VERSION = "1"


class TTSError(RuntimeError):
    pass


def require_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise TTSError("ffmpeg is required for audio (macOS: brew install ffmpeg).")
    return exe


def ffmpeg(*args: str) -> None:
    r = subprocess.run([require_ffmpeg(), "-loglevel", "error", "-y", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise TTSError(f"ffmpeg failed: {r.stderr.strip()}")


class Engine:
    name = "base"
    default_voices: dict[str, str] = {}
    normalize = True

    def __init__(self, voices: dict[str, str] | None = None, rates: dict[str, float] | None = None):
        self.voices = {**self.default_voices, **{k: v for k, v in (voices or {}).items() if v}}
        self.rates = {"ja": 1.0, "en": 1.0, **(rates or {})}

    def render(self, text: str, lang: str, out: Path) -> Path:
        """Write audio for text to a file ffmpeg can read; return its path."""
        raise NotImplementedError

    def key(self, text: str, lang: str) -> str:
        raw = "\x1f".join([CACHE_VERSION, self.name, lang, self.voices[lang], str(self.rates[lang]), text])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()


class SayEngine(Engine):
    """macOS `say`. Offline and free; Kyoko compact is robotic, the free Premium download is better."""
    name = "say"
    default_voices = {"ja": "Kyoko", "en": "Samantha"}

    def render(self, text, lang, out):
        if not shutil.which("say"):
            raise TTSError("the 'say' engine needs macOS.")
        path = out.with_suffix(".aiff")
        args = ["say", "-v", self.voices[lang], "-o", str(path)]
        if self.rates[lang] != 1.0:
            args += ["-r", str(int(175 * self.rates[lang]))]
        subprocess.run([*args, text], check=True)
        return path


DEFAULT_GCLOUD_CONFIG = "~/.config/gcloud-uke"


def gcloud_config_dir() -> Path:
    """uke's own gcloud config directory: $UKE_GCLOUD_CONFIG, else ~/.config/gcloud-uke."""
    return Path(os.environ.get("UKE_GCLOUD_CONFIG") or DEFAULT_GCLOUD_CONFIG).expanduser()


def credentials_path() -> Path:
    return gcloud_config_dir() / "application_default_credentials.json"


class GoogleEngine(Engine):
    """Google Cloud Text-to-Speech.

    Credentials come only from uke's own gcloud config directory (see gcloud_config_dir), never from
    the machine-wide ~/.config/gcloud or GOOGLE_APPLICATION_CREDENTIALS, which other projects share.
    Set the project with --gcp-project or UKE_GCP_PROJECT; it is sent as the quota project.
    """
    name = "google"
    default_voices = {"ja": "ja-JP-Chirp3-HD-Kore", "en": "en-US-Chirp3-HD-Kore"}  # same voice in both languages

    def __init__(self, voices=None, rates=None, project: str | None = None):
        super().__init__(voices, rates)
        self.project = project or os.environ.get("UKE_GCP_PROJECT")
        self._client = None

    def credentials(self):
        path = credentials_path()
        if not path.is_file():
            raise TTSError(
                f"no uke Google credentials at {path}. Log in once with:\n"
                f"  CLOUDSDK_CONFIG={gcloud_config_dir()} gcloud auth application-default login")
        info = json.loads(path.read_text())
        kind = info.get("type")
        if kind == "authorized_user":
            from google.oauth2.credentials import Credentials
            creds = Credentials.from_authorized_user_info(info)
        elif kind == "impersonated_service_account":
            from google.auth.impersonated_credentials import Credentials
            creds = Credentials.from_impersonated_service_account_info(info)
        else:
            raise TTSError(f"{path} holds '{kind}' credentials; uke accepts a user login or "
                           "service-account impersonation from `gcloud auth application-default login`.")
        return creds.with_quota_project(self.project)

    def client(self):
        if self._client is None:
            try:
                from google.cloud import texttospeech
            except ImportError as e:
                raise TTSError("google-cloud-texttospeech is missing; run `uv sync`.") from e
            if not self.project:
                raise TTSError("set the Google Cloud project with --gcp-project or UKE_GCP_PROJECT.")
            creds = self.credentials()
            self._tts = texttospeech
            # REST, not gRPC: gRPC logs fork warnings every time ffmpeg runs as a subprocess
            self._client = texttospeech.TextToSpeechClient(
                credentials=creds, transport="rest", client_options={"quota_project_id": self.project})
        return self._client

    def render(self, text, lang, out):
        client = self.client()
        tts = self._tts
        voice = self.voices[lang]
        params = {"audio_encoding": tts.AudioEncoding.LINEAR16, "sample_rate_hertz": RATE}
        if self.rates[lang] != 1.0:
            params["speaking_rate"] = self.rates[lang]
        resp = client.synthesize_speech(
            input=tts.SynthesisInput(text=text),
            voice=tts.VoiceSelectionParams(language_code="-".join(voice.split("-")[:2]), name=voice),
            audio_config=tts.AudioConfig(**params),
        )
        path = out.with_suffix(".wav")
        path.write_bytes(resp.audio_content)
        return path

    def list_voices(self, prefix: str) -> list[str]:
        resp = self.client().list_voices(language_code=prefix)
        return sorted(v.name for v in resp.voices)


class EdgeEngine(Engine):
    """Microsoft Edge read-aloud voices via edge-tts. Free and keyless, but an unofficial endpoint."""
    name = "edge"
    default_voices = {"ja": "ja-JP-NanamiNeural", "en": "en-US-AriaNeural"}

    def render(self, text, lang, out):
        try:
            import edge_tts
        except ImportError as e:
            raise TTSError("edge-tts is missing; run `uv sync`.") from e
        rate = f"{round((self.rates[lang] - 1) * 100):+d}%"
        path = out.with_suffix(".mp3")
        asyncio.run(edge_tts.Communicate(text, self.voices[lang], rate=rate).save(str(path)))
        return path


class SilentEngine(Engine):
    """Writes silence sized to the text. For tests and dry runs: no network, no voices."""
    name = "silent"
    default_voices = {"ja": "silent", "en": "silent"}
    normalize = False

    def render(self, text, lang, out):
        path = out.with_suffix(".wav")
        write_silence(path, 0.3 + 0.05 * len(text))
        return path


ENGINES = {e.name: e for e in (GoogleEngine, SayEngine, EdgeEngine, SilentEngine)}


def make_engine(name: str, ja_voice=None, en_voice=None, ja_rate=1.0, en_rate=1.0, gcp_project=None) -> Engine:
    if name not in ENGINES:
        raise TTSError(f"unknown engine '{name}'; choose from {', '.join(ENGINES)}")
    kw = dict(voices={"ja": ja_voice, "en": en_voice}, rates={"ja": ja_rate, "en": en_rate})
    if name == "google":
        return GoogleEngine(project=gcp_project, **kw)
    return ENGINES[name](**kw)


def write_silence(path: Path, seconds: float) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"\x00\x00" * int(RATE * seconds))


class Synth:
    """Cached synthesis: clip(text, lang) returns a normalized WAV path."""

    def __init__(self, engine: Engine, cache_dir: Path):
        self.engine = engine
        self.cache = cache_dir / engine.name
        self.cache.mkdir(parents=True, exist_ok=True)
        self.synthesized = 0

    def clip(self, text: str, lang: str) -> Path:
        dest = self.cache / f"{self.engine.key(text, lang)}.wav"
        if dest.exists():
            return dest
        with tempfile.TemporaryDirectory() as tmp:
            raw = self.engine.render(text, lang, Path(tmp) / "raw")
            filters = f"{NORMALIZE}," if self.engine.normalize else ""
            part = Path(tmp) / "out.wav"
            ffmpeg("-i", str(raw), "-af", f"{filters}aresample={RATE}",
                   "-ac", "1", "-ar", str(RATE), "-sample_fmt", "s16", str(part))
            part.replace(dest)
        self.synthesized += 1
        return dest


def concat(pieces: list[Path | float], out: Path) -> None:
    """Join WAV clips (all 24 kHz mono s16) and pauses given in seconds into one WAV."""
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        for p in pieces:
            if isinstance(p, (int, float)):
                w.writeframes(b"\x00\x00" * int(RATE * p))
            else:
                with wave.open(str(p), "rb") as r:
                    if (r.getnchannels(), r.getsampwidth(), r.getframerate()) != (1, 2, RATE):
                        raise TTSError(f"unexpected clip format: {p}")
                    w.writeframes(r.readframes(r.getnframes()))


def encode_mp3(wav: Path, mp3: Path, tags: dict[str, str] | None = None) -> None:
    meta = [a for k, v in (tags or {}).items() for a in ("-metadata", f"{k}={v}")]
    ffmpeg("-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "64k", *meta, str(mp3))


def duration(path: Path) -> float:
    if path.suffix == ".wav":
        with wave.open(str(path), "rb") as r:
            return r.getnframes() / r.getframerate()
    probe = shutil.which("ffprobe")
    if not probe:
        raise TTSError("ffprobe is required to measure MP3 duration.")
    out = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())

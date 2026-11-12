"""Command line: uke build deck|audio|all, uke voices, uke sample (also `python -m uke ...`)."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import REPO
from .audio import build_commute
from .data import load
from .deck import build_deck
from .tts import ENGINES, Synth, TTSError, concat, encode_mp3, make_engine

SAMPLE = ["しょうめんうち", "かたてこーさどり", "いっきょう", "こてがえし", "りょうてどり、てんちなげ"]
SAMPLE_EN = "Straight strike to the head."


def engine_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--engine", choices=list(ENGINES), default=os.environ.get("UKE_TTS_ENGINE", "google"),
                   help="TTS engine (default: $UKE_TTS_ENGINE or google)")
    p.add_argument("--ja-voice", default=os.environ.get("UKE_JA_VOICE"))
    p.add_argument("--en-voice", default=os.environ.get("UKE_EN_VOICE"))
    p.add_argument("--ja-rate", type=float, default=1.0, help="speaking rate for Japanese, 1.0 = normal")
    p.add_argument("--en-rate", type=float, default=1.0)
    p.add_argument("--gcp-project", default=None, help="Google Cloud project (or $UKE_GCP_PROJECT)")
    p.add_argument("--out", type=Path, default=REPO / "build", help="output folder (default: build/)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="uke")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="generate the Anki deck and/or commute audio from data/")
    b.add_argument("target", choices=["deck", "audio", "all"])
    b.add_argument("--recall-pause", type=float, default=3.0, help="seconds after the Japanese term")
    b.add_argument("--after-pause", type=float, default=2.0, help="seconds after the meaning")
    engine_args(b)
    v = sub.add_parser("voices", help="list the engine's Japanese and English voices (google only)")
    engine_args(v)
    s = sub.add_parser("sample", help="render five sample terms to build/tts-samples/ to compare voices")
    engine_args(s)
    a = ap.parse_args(argv)

    try:
        engine = make_engine(a.engine, a.ja_voice, a.en_voice, a.ja_rate, a.en_rate, a.gcp_project)
        if a.cmd == "voices":
            if a.engine != "google":
                print("voices lists Google voices only; see `say -v '?'` or `edge-tts --list-voices`.")
                return 2
            for lang in ("ja-JP", "en-US"):
                print(f"{lang}:\n  " + "\n  ".join(engine.list_voices(lang)))
            return 0

        synth = Synth(engine, a.out / "cache" / "tts")
        if a.cmd == "sample":
            dest = a.out / "tts-samples"
            dest.mkdir(parents=True, exist_ok=True)
            wav = dest / "tmp.wav"
            pieces = [p for t in SAMPLE for p in (synth.clip(t, "ja"), 0.8)] + [synth.clip(SAMPLE_EN, "en")]
            concat(pieces, wav)
            mp3 = dest / f"{engine.name}-{engine.voices['ja']}-{engine.voices['en']}.mp3"
            encode_mp3(wav, mp3)
            wav.unlink()
            print(mp3)
            return 0

        return build(a, synth)
    except TTSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def build(a, synth: Synth) -> int:
    ds = load()
    warn: list[str] = []
    a.out.mkdir(parents=True, exist_ok=True)
    print(f"engine: {synth.engine.name} (ja {synth.engine.voices['ja']}, en {synth.engine.voices['en']})")
    if a.target in ("deck", "all"):
        path = build_deck(ds, synth, a.out / "uke.apkg", warn)
        print(f"deck: {path} ({len(ds.entries)} notes)")
    if a.target in ("audio", "all"):
        made = build_commute(ds.study_set(), synth, a.out / "audio", warn, a.recall_pause, a.after_pause)
        print(f"commute audio: {len(made)} entries, loop at {a.out / 'audio' / 'uke-study-loop.mp3'}")
    print(f"clips synthesized this run: {synth.synthesized} (the rest came from the cache)")
    for w in dict.fromkeys(warn):
        print(f"warning: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

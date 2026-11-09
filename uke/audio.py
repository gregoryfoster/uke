"""Audio: the Japanese clip for each card, and the commute loop for the study set.

Commute pattern, audio only: Japanese term, pause, each root (Japanese then English), the English
meaning, pause. No tones, chimes or references to a screen, so it is safe to play while driving.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from .data import Entry
from .tts import Synth, concat, encode_mp3

LEAD_IN = 0.4          # seconds of silence before each entry
ROOT_GAP = 0.25        # between a root and its meaning
BETWEEN_ROOTS = 0.6


def no_kana_warning(e: Entry) -> str:
    return f"{e.kind} '{e.id}': kana is null, so it has no audio"


def card_audio(synth: Synth, e: Entry, dest: Path) -> Path | None:
    """The Japanese term alone, as played on the cards."""
    if not e.kana:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "a.wav"
        concat([0.2, synth.clip(e.kana, "ja")], wav)
        encode_mp3(wav, dest)
    return dest


def commute_pieces(synth: Synth, e: Entry, recall: float, after: float) -> list:
    """Clips and pauses for one entry, or [] when it has no kana."""
    if not e.kana:
        return []
    pieces: list = [LEAD_IN, synth.clip(e.kana, "ja"), recall]
    for seg in e.segments:
        single = len(seg.roots) == 1 and seg.roots[0].kana == seg.kana
        if e.kind == "kumi_waza" and single:
            # a part that is its own root (omote, katameru): the part and its gloss
            pieces += [synth.clip(seg.kana, "ja"), ROOT_GAP, synth.clip(seg.gloss, "en"), BETWEEN_ROOTS]
            continue
        if single:
            continue  # the meaning below already covers it
        for r in seg.roots:
            if not r.kana:
                continue
            pieces += [synth.clip(r.kana, "ja"), ROOT_GAP,
                       synth.clip(r.meaning.split(";")[0].strip(), "en"), BETWEEN_ROOTS]
    pieces += [synth.clip(e.meaning + ".", "en"), after]
    return pieces


def build_commute(entries: list[Entry], synth: Synth, out_dir: Path, warn: list[str],
                  recall: float = 3.0, after: float = 2.0) -> dict[str, Path]:
    """One MP3 per entry, a combined loop and an .m3u playlist. Returns entry id -> MP3."""
    study_dir = out_dir / "study"
    if study_dir.exists():
        shutil.rmtree(study_dir)
    study_dir.mkdir(parents=True)
    made: dict[str, Path] = {}
    loop: list = []
    with tempfile.TemporaryDirectory() as tmp:
        for e in entries:
            pieces = commute_pieces(synth, e, recall, after)
            if not pieces:
                warn.append(no_kana_warning(e))
                continue
            n = len(made) + 1
            wav = Path(tmp) / f"{n}.wav"
            concat(pieces, wav)
            mp3 = study_dir / f"{n:02d}-{e.id}.mp3"
            encode_mp3(wav, mp3, {"title": e.romaji, "album": "Uke study set", "track": str(n)})
            made[e.id] = mp3
            loop += pieces
        wav = Path(tmp) / "loop.wav"
        concat(loop, wav)
        encode_mp3(wav, out_dir / "uke-study-loop.mp3", {"title": "Uke study set loop", "album": "Uke study set"})
    (out_dir / "uke-study.m3u").write_text(
        "#EXTM3U\n" + "".join(f"study/{p.name}\n" for p in made.values()), encoding="utf-8")
    return made

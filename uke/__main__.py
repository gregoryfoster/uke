"""Command line: uke build deck|audio|all, uke today, uke voices, uke sample, uke personal (also `python -m uke ...`)."""
from __future__ import annotations

import argparse
import datetime
import os
import sys
from pathlib import Path

from . import REPO
from .audio import build_commute
from .data import load, load_motto
from . import personal, today
from .deck import anki_search, build_deck, compare, manifest_path, read_manifest
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
    td = sub.add_parser("today", help="the daily ritual: one motto line, one technique, one question")
    td.add_argument("--date", type=datetime.date.fromisoformat, default=None,
                    help="show another day's prompt, YYYY-MM-DD (default: today)")
    td.add_argument("--answer", help="answer without being asked (default: ask when run in a terminal)")
    pe = sub.add_parser("personal", help="where personal data lives, and syncing it with its private store")
    psub = pe.add_subparsers(dest="action", required=True)
    psub.add_parser("status", help="show the personal directory, its store and unsynced changes")
    sy = psub.add_parser("sync", help="commit local changes, pull remote ones, push")
    sy.add_argument("-m", "--message", help="commit message (default: uke personal sync <date>)")
    ini = psub.add_parser("init", help="fetch your private store into the personal directory")
    ini.add_argument("url", help="e.g. https://github.com/<you>/uke-personal.git")
    a = ap.parse_args(argv)

    if a.cmd == "personal":
        return personal_cmd(a)
    if a.cmd == "today":
        return today_cmd(a)

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


def today_cmd(a) -> int:
    try:
        p = today.pick(load(), load_motto(), a.date or datetime.date.today())
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    where = personal.personal_dir()
    has_personal = where.exists()
    motto_text = None
    if has_personal:
        try:
            motto_text = today.read_motto(where, p.motto_id)
        except ValueError as e:
            print(f"warning: {e}; showing the theme instead", file=sys.stderr)
    print(today.render(p, motto_text))
    if not has_personal:
        print(f"\nNo personal data at {where}, so answers are not saved. With it, they go to "
              f"{where / 'reflections.yaml'} (set it up with `uke personal init <url>`).")
        return 0
    try:
        today.check_reflections(where)    # before asking, so an answer is never typed in vain
    except ValueError as e:
        print(f"error: {e}. Nothing was asked or saved.", file=sys.stderr)
        return 1
    answer = a.answer
    if answer is None:
        if not sys.stdin.isatty():
            return 0
        try:
            answer = input("> ")
        except EOFError:
            answer = ""
        except KeyboardInterrupt:
            print("\nNothing saved.")
            return 130
    answer = answer.strip()
    if not answer:
        print("Nothing saved.")
        return 0
    try:
        path = today.save(where, p, answer)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"Saved to {path}. Back it up with `uke personal sync`.")
    return 0


def personal_cmd(a) -> int:
    path = personal.personal_dir()
    try:
        if a.action == "init":
            store = personal.init(a.url, path)
            print(f"personal data: {path} ({store.provider}, {store.remote()})")
            return 0
        if not path.exists():
            print(f"personal data: not set up; uke looks in {path} ($UKE_PERSONAL to change).\n"
                  "Run `uke personal init <url>` with your private repo, or copy personal.example/ there.")
            return 0 if a.action == "status" else 1
        store = personal.open_store(path)
        if a.action == "status":
            print(f"personal data: {path}\nstore: {store.provider}" + (f" ({store.remote()})" if store.remote() else ""))
            pending = store.pending()
            print(f"not synced: {len(pending)}" + "".join(f"\n  {line}" for line in pending))
            return 0
        print(store.sync(a.message or f"uke personal sync {datetime.date.today().isoformat()}"))
        return 0
    except personal.StoreError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def report_changes(before: dict | None, after: dict) -> None:
    """What re-importing this deck does compared with the previous build in the same folder."""
    if before is None:
        print("since the last build: no earlier build here to compare with")
        return
    c = compare(before, after)
    print(f"since the last build: {len(c.added)} added, {len(c.changed)} changed, {len(c.removed)} removed")
    if c.removed:
        print("removed from the deck, but re-importing leaves them in Anki; find each in the Browse window"
              " and delete or suspend it:")
        for k in c.removed:
            e = before["notes"][k]
            print(f"  {e['name']}: {anki_search(k, e)}")


def build(a, synth: Synth) -> int:
    ds = load()
    warn: list[str] = []
    a.out.mkdir(parents=True, exist_ok=True)
    print(f"engine: {synth.engine.name} (ja {synth.engine.voices['ja']}, en {synth.engine.voices['en']})")
    if a.target in ("deck", "all"):
        apkg = a.out / "uke.apkg"
        before = read_manifest(manifest_path(apkg))
        path = build_deck(ds, synth, apkg, warn)
        print(f"deck: {path} ({len(ds.entries)} notes)")
        report_changes(before, read_manifest(manifest_path(apkg)))
    if a.target in ("audio", "all"):
        made = build_commute(ds.study_set(), synth, a.out / "audio", warn, a.recall_pause, a.after_pause)
        print(f"commute audio: {len(made)} entries, loop at {a.out / 'audio' / 'uke-study-loop.mp3'}")
    print(f"clips synthesized this run: {synth.synthesized} (the rest came from the cache)")
    for w in dict.fromkeys(warn):
        print(f"warning: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

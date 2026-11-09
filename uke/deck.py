"""Anki deck: one note per kumi waza entry, kata and term, with three cards.

1. Japanese -> roots + English   (term and audio on the front)
2. English -> Japanese           (audio on the back)
3. Breakdown                     (roots for terms and kata; part roles for kumi waza).
   Skipped for single-root words, where it would repeat card 1.

Note GUIDs come from entry ids, so re-importing updates cards instead of duplicating them.
Kanji is stored but not shown until it is verified (Phase 3).
"""
from __future__ import annotations

from html import escape
from pathlib import Path

import genanki

from .audio import card_audio, no_kana_warning
from .data import Dataset, Entry, Segment
from .tts import Synth

MODEL_ID = 1731000101
DECK_IDS = {"kumi_waza": 1731000201, "kata": 1731000202, "term": 1731000203}
DECK_NAMES = {"kumi_waza": "Uke::Kumi waza", "kata": "Uke::Kata", "term": "Uke::Terms"}

FIELDS = ["Id", "Name", "Kana", "Kanji", "Category", "English", "Meaning", "Breakdown",
          "BreakdownPrompt", "BreakdownAsk", "Audio", "ClipUrl", "Grades", "Note"]

DETAILS = """
<div class="kana">{{Kana}}</div>
<div class="breakdown">{{Breakdown}}</div>
<div class="meaning">{{Meaning}}</div>
{{#Note}}<div class="note">{{Note}}</div>{{/Note}}
{{#ClipUrl}}<div><a class="clip" href="{{ClipUrl}}">&#9654; Watch clip</a></div>{{/ClipUrl}}
<div class="grades">{{Grades}}</div>
"""

TEMPLATES = [
    {
        "name": "1 Japanese to meaning",
        "qfmt": '<div class="tag">{{Category}}</div><div class="jp">{{Name}}</div>{{Audio}}'
                '<div class="ask">Roots and meaning?</div>',
        "afmt": '<div class="back">{{FrontSide}}<hr id="answer">' + DETAILS + "</div>",
    },
    {
        "name": "2 English to Japanese",
        "qfmt": '<div class="tag">{{Category}}</div><div class="en">{{English}}</div>'
                '<div class="ask">In Japanese?</div>',
        "afmt": '<div class="back">{{FrontSide}}<hr id="answer"><div class="jp">{{Name}}</div>{{Audio}}'
                + DETAILS + "</div>",
    },
    {
        "name": "3 Breakdown",
        "qfmt": '{{#BreakdownPrompt}}<div class="tag">{{Category}}</div><div class="jp">{{BreakdownPrompt}}</div>'
                '<div class="ask">{{BreakdownAsk}}</div>{{/BreakdownPrompt}}',
        "afmt": '<div class="back">{{FrontSide}}<hr id="answer"><div class="jp small">{{Name}}</div>{{Audio}}'
                + DETAILS + "</div>",
    },
]

CSS = """
.card { font-family: -apple-system, "Hiragino Sans", "Noto Sans JP", "Segoe UI", sans-serif;
        font-size: 20px; text-align: center; color: #1d1d1f; background: #fbfaf6; padding: 12px; }
.nightMode.card, .night_mode.card, .nightMode .card, .night_mode .card { color: #ececec; background: #1f1f1f; }
.tag { font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: #8a8a8a; }
.jp { font-size: 30px; font-weight: 600; margin: .3em 0; }
.jp.small { font-size: 24px; }
.en { font-size: 24px; margin: .4em 0; }
.ask { font-size: 14px; color: #8a8a8a; margin-top: .8em; }
.back .ask { display: none; }
.kana { font-size: 18px; color: #7a7a7a; }
.breakdown { display: inline-block; text-align: left; margin: .7em auto; line-height: 1.7; font-size: 18px; }
.breakdown .k { color: #7a7a7a; font-size: 15px; }
.breakdown .from, .breakdown .not { color: #8a8a8a; font-size: 15px; }
.role { font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: #a0522d;
        border: 1px solid currentColor; border-radius: 4px; padding: 0 4px; margin-right: 4px; }
.nightMode .role, .night_mode .role { color: #e0a070; }
.meaning { font-size: 22px; font-weight: 600; margin: .5em 0; }
.note { font-size: 15px; font-style: italic; margin: .4em 0; }
.clip { display: inline-block; margin: .6em 0; font-size: 16px; }
.grades { font-size: 12px; color: #8a8a8a; margin-top: .6em; }
"""

MODEL = genanki.Model(MODEL_ID, "Uke term", fields=[{"name": f} for f in FIELDS],
                      templates=TEMPLATES, css=CSS)


def grade_label(gid: str) -> str:
    return {"1kyu": "1st kyu", "2kyu": "2nd kyu", "3kyu": "3rd kyu"}.get(gid, gid.replace("kyu", "th kyu"))


def roots_html(seg: Segment) -> str:
    parts = []
    for r in seg.roots:
        shown = r.surface or r.romaji
        kana = f' <span class="k">{escape(r.kana)}</span>' if r.kana else ""
        bits = [escape(r.meaning)]
        if r.surface and r.surface != r.romaji:
            # the kana is the base form, so it goes with "from", not next to the changed sound
            bits.append(f'<span class="from">from {escape(r.romaji)}</span>{kana}')
            kana = ""
        if r.not_meanings:
            bits.append('<span class="not">not ' + escape(", not ".join(r.not_meanings)) + "</span>")
        parts.append(f"<b>{escape(shown)}</b>{kana} ({'; '.join(bits)})")
    html = " + ".join(parts)
    if not seg.aligned:
        html += ' <span class="from">(not every root is entered yet)</span>'
    return html


def breakdown_html(e: Entry) -> str:
    if e.kind != "kumi_waza":
        return roots_html(e.segments[0])
    lines = []
    for s in e.segments:
        kana = f' <span class="k">{escape(s.kana)}</span>' if s.kana else ""
        own_root = len(s.roots) == 1 and s.roots[0].romaji.lower() == s.romaji.lower()
        roots = escape(s.roots[0].meaning) if own_root else roots_html(s)
        lines.append(f'<div><span class="role">{escape(s.role)}</span><b>{escape(s.romaji)}</b>{kana}'
                     f" = {roots} &rarr; {escape(s.gloss)}</div>")
    return "".join(lines)


def breakdown_prompt(e: Entry) -> tuple[str, str]:
    """Front of card 3, and its question. Empty when the card would repeat card 1."""
    if e.kind == "kumi_waza":
        return " · ".join(s.romaji for s in e.segments), "Name each part's role and meaning"
    seg = e.segments[0]
    if len(seg.roots) < 2:
        return "", ""
    if seg.aligned:
        return " · ".join(r.surface for r in seg.roots), "What does each root mean?"
    return e.romaji, "Which roots build it, and what do they mean?"


def tags(e: Entry) -> list[str]:
    t = [f"uke::{e.status}", f"kind::{e.kind.replace('_', '-')}", f"category::{e.category.replace(' ', '-')}"]
    t += [f"grade::{g}" for g in e.grades]
    if e.basic_art:
        t.append("basic-art")
    return t


def note_for(e: Entry, audio_name: str | None) -> genanki.Note:
    prompt, ask = breakdown_prompt(e)
    grades = ", ".join(grade_label(g) for g in e.grades) or "not yet required"
    status = {"study": "study set", "review": "review", "later": "later"}[e.status]
    if e.basic_art:
        grades = f"Basic Art {e.basic_art} · {grades}"
    values = {
        "Id": e.id,
        "Name": escape(e.romaji),
        "Kana": escape(e.kana or ""),
        "Kanji": escape(e.kanji or ""),
        "Category": escape(e.category),
        "English": escape(e.english_prompt),
        "Meaning": escape(e.meaning),
        "Breakdown": breakdown_html(e),
        "BreakdownPrompt": escape(prompt),
        "BreakdownAsk": escape(ask),
        "Audio": f"[sound:{audio_name}]" if audio_name else "",
        "ClipUrl": escape(e.clip_url or "", quote=True),
        "Grades": escape(f"{grades} · {status}"),
        "Note": escape(e.note or ""),
    }
    return genanki.Note(model=MODEL, fields=[values[f] for f in FIELDS], tags=tags(e),
                        guid=genanki.guid_for("uke", e.kind, e.id))


def build_deck(ds: Dataset, synth: Synth, out: Path, warn: list[str]) -> Path:
    media_dir = out.parent / "deck-media"
    media_dir.mkdir(parents=True, exist_ok=True)
    decks = {k: genanki.Deck(DECK_IDS[k], DECK_NAMES[k]) for k in DECK_IDS}
    media = []
    for e in ds.entries:
        name = f"uke-{e.kind}-{e.id}.mp3"
        path = card_audio(synth, e, media_dir / name)
        if path is None:
            warn.append(no_kana_warning(e))
            name = None
        else:
            media.append(str(path))
        decks[e.kind].add_note(note_for(e, name))
    genanki.Package(list(decks.values()), media_files=media).write_to_file(str(out))
    return out

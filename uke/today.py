"""uke today: the daily ritual. One motto line, one technique, one question.

The prompt depends only on the date (and data/), so running it twice the same day shows the same thing:
- The motto line rotates in order, so eight days in a row cover all eight lines.
- The technique is a weighted pick, by a hash of the date, from the study and review sets
  (kumi waza and kata), with review entries weighted double.

The motto text comes from personal data; without it only the line's theme is shown. uke never writes
motto text. The answer is appended to the personal reflections.yaml; without a personal directory,
the prompt is shown and nothing is saved.
"""
from __future__ import annotations

import datetime
import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from .data import REVIEW, STUDY, Dataset, Entry

QUESTION = "Where did this show up in your day?"
DAILY_PRINCIPLE = "p-daily-life"   # data/principles.yaml: "the daily prompt practises this now"
WEIGHTS = {STUDY: 1, REVIEW: 2}
KINDS = ("kumi_waza", "kata")


@dataclass
class Prompt:
    date: datetime.date
    motto_id: str
    motto_line: int
    motto_theme: str
    entry: Entry


def candidates(ds: Dataset) -> list[Entry]:
    return [e for e in ds.entries if e.kind in KINDS and e.status in WEIGHTS]


def pick(ds: Dataset, motto: list[dict], date: datetime.date) -> Prompt:
    """The day's prompt. A hash (not Python's random) keeps it stable across Python versions."""
    m = motto[date.toordinal() % len(motto)]
    pool = candidates(ds)
    if not pool:
        raise ValueError("no kumi waza or kata in the study or review sets to pick from; "
                         "check profile.next_exam in data/grades.yaml")
    weights = [WEIGHTS[e.status] for e in pool]
    n = int(hashlib.sha256(f"uke-today:{date.isoformat()}".encode()).hexdigest(), 16) % sum(weights)
    for e, w in zip(pool, weights):
        if n < w:
            break
        n -= w
    return Prompt(date, m["id"], m["line"], m["theme"], e)


def breakdown_lines(e: Entry) -> list[str]:
    """Plain-text roots: each part of a kumi waza, or the roots of a kata."""
    def roots(seg):
        return " + ".join(f"{r.surface or r.romaji} ({r.meaning.split(';')[0].strip()})" for r in seg.roots)

    if e.kind == "kumi_waza":
        return [f"{s.role}: {s.romaji}" + (f" {s.kana}" if s.kana else "") + f" = {roots(s)} -> {s.gloss}"
                for s in e.segments]
    seg = e.segments[0]
    return [roots(seg)] if seg.roots else []


def render(p: Prompt, motto_text: str | None) -> str:
    e = p.entry
    label = {"kumi_waza": "kumi waza", "kata": "kata"}[e.kind]
    where = [label, {"study": "study set", "review": "review"}[e.status]]
    if e.basic_art:
        where.append(f"Basic Art {e.basic_art}")
    lines = [f"uke today · {p.date:%A} {p.date.day} {p.date:%B %Y}", ""]
    if motto_text:
        lines.append(f"Motto, line {p.motto_line}: {motto_text}")
    else:
        lines.append(f"Motto, line {p.motto_line} (theme): {p.motto_theme}")
    lines += ["", f"Technique: {e.romaji} ({', '.join(where)})"]
    if e.kana:
        lines.append(f"  {e.kana}")
    lines += [f"  {line}" for line in breakdown_lines(e)]
    lines.append(f"  Meaning: {e.meaning}")
    if e.clip_url:
        lines.append(f"  Clip: {e.clip_url}")
    lines += ["", QUESTION]
    return "\n".join(lines)


def load_personal_yaml(path: Path, key: str, kind: type):
    """(file text, parsed doc) for a personal file whose top-level key must be of kind.

    Raises ValueError naming the file only: YAML errors quote the offending line, which is personal text.
    """
    try:
        raw = path.read_text(encoding="utf-8")
        doc = yaml.safe_load(raw) or {}
    except (yaml.YAMLError, ValueError, UnicodeDecodeError):   # ValueError: impossible dates
        raise ValueError(f"{path} cannot be read as YAML; run `uv run scripts/validate.py` to find the line") from None
    if not isinstance(doc, dict) or not isinstance(doc.get(key) if doc.get(key) is not None else kind(), kind):
        raise ValueError(f"{path} needs a top-level {key} {'mapping' if kind is dict else 'list'}")
    return raw, doc


def read_motto(personal: Path, motto_id: str) -> str | None:
    """The day's motto line from personal data; None if absent or empty. ValueError if the file is malformed."""
    path = personal / "motto.yaml"
    if not path.exists():
        return None
    text = (load_personal_yaml(path, "motto_text", dict)[1].get("motto_text") or {}).get(motto_id)
    return text.strip() if isinstance(text, str) and text.strip() else None


def check_reflections(personal: Path) -> None:
    """Raise ValueError if reflections.yaml exists but cannot take an answer, before one is asked for."""
    path = personal / "reflections.yaml"
    if path.exists():
        load_personal_yaml(path, "reflections", list)


def save(personal: Path, p: Prompt, text: str) -> Path:
    """Append one reflection to reflections.yaml, keeping the comment lines at the top of the file.

    The new file is written beside the old one and moved over it, so an interruption leaves the old intact.
    """
    path = personal / "reflections.yaml"
    header, doc = [], {}
    if path.exists():
        raw, doc = load_personal_yaml(path, "reflections", list)
        for line in raw.splitlines():
            if not line.startswith("#"):
                break
            header.append(line)
    doc["reflections"] = [*(doc.get("reflections") or []), {
        "subject": p.entry.id, "date": p.date, "motto": p.motto_id,
        "principle": DAILY_PRINCIPLE, "text": text,
    }]
    body = "\n".join(header) + ("\n" if header else "") + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False,
                                                                        width=100)
    fd, tmp = tempfile.mkstemp(dir=personal, prefix=".reflections-", suffix=".yaml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path

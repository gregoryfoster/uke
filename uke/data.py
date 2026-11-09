"""Load data/ into study entries: one per kumi waza entry, kata and term.

Nothing here reads personal/; the generators must work without it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import REPO

STUDY, REVIEW, LATER = "study", "review", "later"


@dataclass
class RootUse:
    id: str
    romaji: str            # base form, e.g. tori
    surface: str | None    # form as it appears in the word, e.g. dori; None if alignment failed
    kana: str | None
    meaning: str
    not_meanings: list[str] = field(default_factory=list)  # homophone meanings, for "not shoulder"


@dataclass
class Segment:
    """One spoken word of an entry: a term inside a kumi waza, or the whole word for a term or kata."""
    romaji: str
    kana: str | None
    role: str | None       # term category when the segment is a kumi waza part
    gloss: str | None      # first English gloss of the part
    roots: list[RootUse]
    aligned: bool


@dataclass
class Entry:
    id: str
    kind: str              # kumi_waza | kata | term
    romaji: str
    kana: str | None
    kanji: str | None
    category: str          # term category, or "kumi waza" / "kata"
    glosses: list[str]
    segments: list[Segment]
    grades: list[str]      # every grade whose requirements include it, in grade order
    status: str            # study | review | later
    clip_url: str | None = None
    note: str | None = None
    basic_art: int | None = None
    order: int = 0         # position for stable output ordering

    @property
    def english_prompt(self) -> str:
        """English side used to ask for the Japanese."""
        if self.kind == "kumi_waza":
            return " · ".join(s.gloss for s in self.segments)
        return " / ".join(self.glosses)

    @property
    def meaning(self) -> str:
        """Spoken and printed English meaning."""
        if self.kind == "kumi_waza":
            text = ", ".join(s.gloss for s in self.segments)
        else:
            text = self.glosses[0]
        return text[:1].upper() + text[1:]


def _load(data: Path, name: str):
    with open(data / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def short_meaning(meaning: str) -> str:
    """First sense only: 'throw; also the person throwing' -> 'throw'; 'one side, one of a pair' -> 'one side'."""
    return meaning.split(";")[0].split(",")[0].strip()


def align(romaji: str, root_ids: list[str], roots: dict) -> list[str] | None:
    """Split a romanized word into the surface forms of its roots, allowing listed sound changes.

    Returns None when the roots do not spell the word (e.g. Juntai, whose 'jun' root is not entered).
    """
    word = romaji.lower().replace(" ", "").replace("-", "")

    def forms(rid):
        r = roots[rid]
        return sorted({r["romaji"], *r.get("sound_changes", [])}, key=len, reverse=True)

    def walk(pos, i):
        if i == len(root_ids):
            return [] if pos == len(word) else None
        for f in forms(root_ids[i]):
            if word.startswith(f, pos):
                rest = walk(pos + len(f), i + 1)
                if rest is not None:
                    return [f, *rest]
        return None

    return walk(0, 0)


def _root_uses(romaji: str, root_ids: list[str], roots: dict) -> tuple[list[RootUse], bool]:
    surfaces = align(romaji, root_ids, roots)
    uses = []
    for i, rid in enumerate(root_ids):
        r = roots[rid]
        uses.append(RootUse(
            id=rid,
            romaji=r["romaji"],
            surface=surfaces[i] if surfaces else None,
            kana=r.get("kana"),
            meaning=r["meaning"],
            not_meanings=[short_meaning(roots[h]["meaning"]) for h in r.get("homophones", [])],
        ))
    return uses, surfaces is not None


@dataclass
class Dataset:
    entries: list[Entry]
    study_grades: list[str]
    grade_order: dict[str, int]

    def by_id(self, kind: str, id_: str) -> Entry:
        return next(e for e in self.entries if e.kind == kind and e.id == id_)

    def study_set(self) -> list[Entry]:
        """Study-set entries in a stable order: kumi waza, Basic Arts, kata, then terms."""
        return [e for e in self.entries if e.status == STUDY]


def load(repo: Path = REPO) -> Dataset:
    data = repo / "data"
    roots = {r["id"]: r for r in _load(data, "roots.yaml")["roots"]}
    terms = {t["id"]: t for t in _load(data, "terms.yaml")["terms"]}
    kata = _load(data, "kata.yaml")["kata"]
    kumi = _load(data, "kumi_waza.yaml")["kumi_waza"]
    media = _load(data, "media.yaml")["media"]
    g = _load(data, "grades.yaml")

    grade_list = sorted(g["grades"], key=lambda x: x["order"])
    grade_order = {gr["id"]: gr["order"] for gr in grade_list}
    nxt = grade_order[g["profile"]["next_exam"]]
    # Nage and uke must know the names for their exam and one level above.
    study_grades = [gid for gid, o in grade_order.items() if nxt <= o <= nxt + 1]

    # ---- which grades require each item ----
    kumi_by_id = {k["id"]: k for k in kumi}
    need: dict[tuple[str, str], list[str]] = {}

    def add(kind, id_, gid):
        lst = need.setdefault((kind, id_), [])
        if gid not in lst:
            lst.append(gid)

    for gr in grade_list:
        gid = gr["id"]
        kw = list(gr.get("kumi_waza", []))
        if gr.get("basic_arts"):
            kw += [k["id"] for k in kumi if k.get("basic_art")]
        for kid in kw:
            add("kumi_waza", kid, gid)
            for part in kumi_by_id[kid]["parts"]:
                add("term", part, gid)
        for tid in gr.get("levels", []) + gr.get("exercises", []):
            add("term", tid, gid)
        for fa in gr.get("free_arts", []):
            add("term", fa["attack"], gid)
        if gr.get("kata_with_counting"):
            for k in kata:
                add("kata", k["id"], gid)

    def status(grades):
        if any(x in study_grades for x in grades):
            return STUDY
        if any(grade_order[x] < nxt for x in grades):
            return REVIEW
        return LATER

    # ---- media ----
    clip = {}
    for m in media:
        if m.get("subject"):
            url = m["url"]
            if m.get("start"):
                url += ("&" if "?" in url else "?") + f"t={int(m['start'])}s"
            clip[m["subject"]] = url

    def term_segment(t, role=None):
        uses, ok = _root_uses(t["romaji"], t["roots"], roots)
        return Segment(t["romaji"], t.get("kana"), role, t["gloss_en"][0], uses, ok)

    entries: list[Entry] = []
    n = 0

    # kumi waza: study-grade lists first (in grade order), then the Basic Arts, then the rest
    listed = list(dict.fromkeys(
        kid for gr in grade_list if gr["id"] in study_grades for kid in gr.get("kumi_waza", [])))
    file_pos = {k["id"]: i for i, k in enumerate(kumi)}

    def kumi_rank(k):
        if k["id"] in listed:
            return (0, listed.index(k["id"]))
        if k.get("basic_art"):
            return (1, k["basic_art"])
        return (2, file_pos[k["id"]])

    for k in sorted(kumi, key=kumi_rank):
        parts = [terms[p] for p in k["parts"]]
        segs = [term_segment(t, role=t["category"]) for t in parts]
        kanas = [t.get("kana") for t in parts]
        grades = need.get(("kumi_waza", k["id"]), [])
        entries.append(Entry(
            id=k["id"], kind="kumi_waza",
            romaji=" ".join(t["romaji"] for t in parts),
            kana="、".join(kanas) if all(kanas) else None,
            kanji=None, category="kumi waza",
            glosses=[", ".join(s.gloss for s in segs)],
            segments=segs, grades=grades, status=status(grades),
            clip_url=clip.get(k["id"]), note=k.get("note"), basic_art=k.get("basic_art"), order=n,
        ))
        n += 1

    for k in sorted(kata, key=lambda k: k["order"]):
        uses, ok = _root_uses(k["romaji"], k["roots"], roots)
        grades = need.get(("kata", k["id"]), [])
        entries.append(Entry(
            id=k["id"], kind="kata", romaji=k["romaji"], kana=k.get("kana"), kanji=k.get("kanji"),
            category="kata", glosses=k["gloss_en"],
            segments=[Segment(k["romaji"], k.get("kana"), None, k["gloss_en"][0], uses, ok)],
            grades=grades, status=status(grades),
            clip_url=clip.get(k["id"]) or clip.get("kata-all"), note=k.get("note"), order=n,
        ))
        n += 1

    for t in terms.values():
        grades = need.get(("term", t["id"]), [])
        entries.append(Entry(
            id=t["id"], kind="term", romaji=t["romaji"], kana=t.get("kana"), kanji=t.get("kanji"),
            category=t["category"], glosses=t["gloss_en"], segments=[term_segment(t)],
            grades=grades, status=status(grades), clip_url=clip.get(t["id"]), note=t.get("note"), order=n,
        ))
        n += 1

    # sort grades on each entry for display
    for e in entries:
        e.grades.sort(key=lambda x: grade_order[x])
    return Dataset(entries, study_grades, grade_order)

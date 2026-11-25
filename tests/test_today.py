"""uke today: the same date gives the same prompt; it works with and without personal data."""
import datetime
import io
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
import yaml

from uke import today
from uke.__main__ import main
from uke.data import REVIEW, STUDY, load

REPO = Path(__file__).resolve().parents[1]
DAY = datetime.date(2026, 11, 24)
MOTTO = "a line only the student pastes"


@pytest.fixture(scope="module")
def ds():
    return load()


@pytest.fixture(scope="module")
def motto():
    return today.motto_lines()


@pytest.fixture
def personal_dir(tmp_path, monkeypatch):
    d = tmp_path / "personal"
    shutil.copytree(REPO / "personal.example", d)
    (d / "motto.yaml").write_text(f'motto_text:\n  motto-1: "{MOTTO}"\n  motto-2: null\n', encoding="utf-8")
    monkeypatch.setenv("UKE_PERSONAL", str(d))
    return d


def test_same_date_same_prompt(ds, motto):
    a, b = today.pick(ds, motto, DAY), today.pick(ds, motto, DAY)
    assert (a.motto_id, a.entry.id) == (b.motto_id, b.entry.id)
    assert today.render(a, None) == today.render(b, None)


def test_motto_lines_rotate_in_order(ds, motto):
    ids = [today.pick(ds, motto, DAY + datetime.timedelta(n)).motto_id for n in range(16)]
    assert ids[:8] == ids[8:]
    assert sorted(ids[:8]) == sorted(m["id"] for m in motto)
    lines = [today.pick(ds, motto, DAY + datetime.timedelta(n)).motto_line for n in range(8)]
    assert all((b - a) % 8 == 1 for a, b in zip(lines, lines[1:]))


def test_technique_comes_from_study_and_review_weighted_to_review(ds, motto):
    picks = [today.pick(ds, motto, DAY + datetime.timedelta(n)).entry for n in range(4000)]
    assert {e.kind for e in picks} <= {"kumi_waza", "kata"}
    assert {e.status for e in picks} <= {STUDY, REVIEW}
    pool = today.candidates(ds)
    per_entry = Counter(e.id for e in picks)
    mean = lambda status: (sum(per_entry[e.id] for e in pool if e.status == status)
                           / sum(1 for e in pool if e.status == status))
    assert 1.5 < mean(REVIEW) / mean(STUDY) < 2.7      # review entries come up about twice as often
    assert len(per_entry) == len(pool)                   # every candidate comes up


def test_prompt_shows_technique_roots_meaning_clip_and_question(ds, motto):
    p = next(today.pick(ds, motto, DAY + datetime.timedelta(n)) for n in range(400)
             if today.pick(ds, motto, DAY + datetime.timedelta(n)).entry.id == "katadori-ikkyo-omote-katameru")
    out = today.render(p, None)
    e = p.entry
    assert f"Technique: {e.romaji}" in out and e.kana in out
    for s in e.segments:
        assert f"{s.role}: {s.romaji}" in out
    assert f"Meaning: {e.meaning}" in out and f"Clip: {e.clip_url}" in out
    assert out.rstrip().endswith(today.QUESTION)


def test_without_personal_data_prints_theme_and_saves_nothing(tmp_path, monkeypatch, capsys, motto):
    where = tmp_path / "absent"
    monkeypatch.setenv("UKE_PERSONAL", str(where))
    assert main(["today", "--date", "2026-11-24", "--answer", "anything"]) == 0
    out = capsys.readouterr().out
    line = next(m for m in motto if m["id"] == today.pick(load(), motto, DAY).motto_id)
    assert f"(theme): {line['theme']}" in out
    assert "answers are not saved" in out and str(where / "reflections.yaml") in out
    assert not where.exists()


def test_with_personal_data_shows_motto_and_saves_the_answer(personal_dir, capsys, monkeypatch, motto):
    date = next(DAY + datetime.timedelta(n) for n in range(8)
                if today.pick(load(), motto, DAY + datetime.timedelta(n)).motto_id == "motto-1")
    assert main(["today", "--date", date.isoformat(), "--answer", "  Held my ground in a hard meeting.  "]) == 0
    out = capsys.readouterr().out
    assert f"Motto, line 1: {MOTTO}" in out and "Saved to" in out
    raw = (personal_dir / "reflections.yaml").read_text(encoding="utf-8")
    assert raw.startswith("# Your own")                               # the file's header comment is kept
    [r] = yaml.safe_load(raw)["reflections"]
    p = today.pick(load(), motto, date)
    assert r == {"subject": p.entry.id, "date": date, "motto": "motto-1", "principle": "p-daily-life",
                 "text": "Held my ground in a hard meeting."}

    # a second answer is appended, and the validator accepts the result
    assert main(["today", "--date", date.isoformat(), "--answer", "Again in the evening."]) == 0
    assert len(yaml.safe_load((personal_dir / "reflections.yaml").read_text())["reflections"]) == 2
    v = subprocess.run([sys.executable, str(REPO / "scripts" / "validate.py")], capture_output=True, text=True)
    assert v.returncode == 0, v.stdout
    assert "reflections: 2" in v.stdout


def test_an_empty_motto_line_shows_its_theme(personal_dir, capsys, motto):
    date = next(DAY + datetime.timedelta(n) for n in range(8)
                if today.pick(load(), motto, DAY + datetime.timedelta(n)).motto_id == "motto-2")
    assert main(["today", "--date", date.isoformat(), "--answer", ""]) == 0
    out = capsys.readouterr().out
    assert "Motto, line 2 (theme):" in out and "Nothing saved." in out
    assert yaml.safe_load((personal_dir / "reflections.yaml").read_text())["reflections"] == []


def test_asks_in_a_terminal_and_skips_when_piped(personal_dir, monkeypatch, capsys):
    class Tty(io.StringIO):
        def isatty(self):
            return True
    monkeypatch.setattr(sys, "stdin", Tty("Kept my posture on the bus.\n"))
    assert main(["today", "--date", "2026-11-24"]) == 0
    assert "Saved to" in capsys.readouterr().out
    monkeypatch.setattr(sys, "stdin", io.StringIO("ignored\n"))
    assert main(["today", "--date", "2026-11-24"]) == 0
    assert "Saved to" not in capsys.readouterr().out
    assert len(yaml.safe_load((personal_dir / "reflections.yaml").read_text())["reflections"]) == 1


def test_a_broken_reflections_file_is_not_overwritten(personal_dir, capsys):
    (personal_dir / "reflections.yaml").write_text("reflections:\n  text: not a list\n", encoding="utf-8")
    assert main(["today", "--date", "2026-11-24", "--answer", "x"]) == 1
    assert "not a mapping with a reflections list" in capsys.readouterr().err
    assert (personal_dir / "reflections.yaml").read_text() == "reflections:\n  text: not a list\n"

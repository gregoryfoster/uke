"""Build the deck and commute audio with the silent engine (no network, no voices) and check the output."""
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from uke.audio import build_commute
from uke.data import STUDY, align, load
from uke.deck import breakdown_prompt, build_deck
from uke.tts import SilentEngine, Synth, duration

REPO = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is required")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    # A repo copy with data/ only: personal/ is absent.
    root = tmp_path_factory.mktemp("repo")
    shutil.copytree(REPO / "data", root / "data")
    assert not (root / "personal").exists()
    ds = load(root)
    synth = Synth(SilentEngine(), root / "build" / "cache")
    warn: list[str] = []
    apkg = build_deck(ds, synth, root / "build" / "uke.apkg", warn)
    made = build_commute(ds.study_set(), synth, root / "build" / "audio", warn)
    return SimpleNamespace(root=root, ds=ds, apkg=apkg, made=made, warn=warn, synth=synth)


@pytest.fixture(scope="module")
def anki(built):
    """Notes and cards from the .apkg: {(category, id): (fields, tags, card count)}, plus its media names."""
    with zipfile.ZipFile(built.apkg) as z, tempfile.TemporaryDirectory() as tmp:
        z.extract("collection.anki2", tmp)
        media = set(json.loads(z.read("media")).values())
        db = sqlite3.connect(Path(tmp) / "collection.anki2")
        rows = db.execute("select n.flds, n.tags, count(c.id) from notes n join cards c on c.nid = n.id group by n.id")
        notes = {}
        for flds, tags, cards in rows:
            f = flds.split("\x1f")
            notes[(f[4], f[0])] = (f, tags.split(), cards)
        db.close()
    return SimpleNamespace(notes=notes, media=media)


def note(anki, e):
    return anki.notes[(e.category, e.id)]


def test_validator_still_passes():
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "validate.py")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_study_set_matches_validator(built):
    out = subprocess.run([sys.executable, str(REPO / "scripts" / "validate.py")],
                         capture_output=True, text=True).stdout
    listed, section = set(), None
    for line in out.splitlines():
        if line.startswith("study set") or line.startswith("8 Basic Arts"):
            section = True
        elif not line.strip():
            section = None
        elif section:
            name = line.split("<-")[0].strip()
            listed.add(name.split(". ", 1)[-1])
    ours = {e.romaji for e in built.ds.study_set() if e.kind == "kumi_waza"}
    assert ours == listed


def test_every_entry_has_a_note(built, anki):
    assert len(anki.notes) == len(built.ds.entries)


def test_every_study_entry_produces_cards(built, anki):
    study = built.ds.study_set()
    assert study
    for e in study:
        fields, tags, cards = note(anki, e)
        expected = 3 if breakdown_prompt(e)[0] else 2
        assert cards == expected, e.id
        assert "uke::study" in tags
        assert any(t.startswith("grade::") for t in tags)


def test_every_study_entry_with_kana_produces_audio(built, anki):
    for e in built.ds.study_set():
        fields, _, _ = note(anki, e)
        audio = fields[10]
        if e.kana:
            assert audio.startswith("[sound:"), e.id
            assert audio[7:-1] in anki.media, e.id
            assert duration(built.made[e.id]) > 1, e.id
        else:
            assert audio == ""
            assert e.id not in built.made
            assert any(e.id in w and "kana is null" in w for w in built.warn)


def test_juntai_has_cards_but_no_audio(built, anki):
    juntai = built.ds.by_id("term", "juntai")
    assert juntai.kana is None
    assert note(anki, juntai)[2] >= 2
    assert "juntai" not in built.made


def test_loop_holds_every_entry(built):
    loop = built.root / "build" / "audio" / "uke-study-loop.mp3"
    total = sum(duration(p) for p in built.made.values())
    assert abs(duration(loop) - total) < 0.1 * len(built.made) + 1
    playlist = (built.root / "build" / "audio" / "uke-study.m3u").read_text().splitlines()
    assert len(playlist) == len(built.made) + 1


def test_cards_link_clips(built, anki):
    e = built.ds.by_id("kumi_waza", "katadori-ikkyo-omote-katameru")
    assert note(anki, e)[0][11].startswith("https://www.youtube.com/")
    no_clip = built.ds.by_id("kumi_waza", "ryotedori-tenchinage-omote")
    assert note(anki, no_clip)[0][11] == ""


def test_rebuild_uses_cache(built):
    before = built.synth.synthesized
    build_commute(built.ds.study_set(), built.synth, built.root / "build" / "audio2", [])
    assert built.synth.synthesized == before


@pytest.mark.parametrize("romaji, roots, expected", [
    ("Ikkyo", ["ichi", "kyo"], ["ik", "kyo"]),
    ("Happo", ["hachi", "ho"], ["hap", "po"]),
    ("Kotegaeshi", ["ko-small", "te", "kaeshi"], ["ko", "te", "gaeshi"]),
    ("Ushirotekubidori", ["ushiro", "te", "kubi", "tori"], ["ushiro", "te", "kubi", "dori"]),
    ("Zenshin Koshin", ["zen", "shin-advance", "ko-back", "shin-advance"], ["zen", "shin", "ko", "shin"]),
    ("Juntai", ["tai"], None),
])
def test_align(built, romaji, roots, expected):
    import yaml
    with open(built.root / "data" / "roots.yaml", encoding="utf-8") as f:
        table = {r["id"]: r for r in yaml.safe_load(f)["roots"]}
    assert align(romaji, roots, table) == expected


def test_study_status_comes_from_profile(built):
    assert built.ds.study_grades == ["4kyu", "3kyu"]
    review_only = built.ds.by_id("kumi_waza", "katatekosadori-kokyunage")
    assert review_only.status == "review"
    assert built.ds.by_id("kumi_waza", "ryotedori-tenchinage-ura").status == STUDY


def test_tts_kana_is_spoken_but_kana_is_shown(built, anki):
    e = built.ds.by_id("term", "katatekosadori")
    assert e.kana == "かたてこうさどり"
    assert e.speech == "かたてこーさどり"
    assert note(anki, e)[0][2] == "かたてこうさどり"   # Kana field on the card
    kumi = built.ds.by_id("kumi_waza", "katatekosadori-kotegaeshi-omote")
    assert kumi.speech.startswith("かたてこーさどり、")
    assert kumi.segments[0].speech == "かたてこーさどり"
    # terms without tts_kana speak their kana
    assert built.ds.by_id("term", "kotegaeshi").speech == built.ds.by_id("term", "kotegaeshi").kana


def test_validator_rejects_bad_tts_kana(tmp_path):
    shutil.copytree(REPO / "data", tmp_path / "data")
    shutil.copytree(REPO / "scripts", tmp_path / "scripts")
    terms = tmp_path / "data" / "terms.yaml"
    terms.write_text(terms.read_text(encoding="utf-8").replace(
        'tts_kana: "かたてこーさどり"', 'tts_kana: "katatekosadori"'), encoding="utf-8")
    r = subprocess.run([sys.executable, str(tmp_path / "scripts" / "validate.py")], capture_output=True, text=True)
    assert r.returncode == 1
    assert "tts_kana must be kana only" in r.stdout + r.stderr

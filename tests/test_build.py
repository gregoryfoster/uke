"""Build the deck and commute audio with the silent engine (no network, no voices) and check the output."""
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from uke.audio import answer_pieces, breakdown_pieces, build_commute
from uke.data import STUDY, align, load
from uke.deck import (AUDIO_FIELDS, FIELDS, MODEL, anki_search, breakdown_prompt, build_deck, compare,
                      manifest_path, read_manifest)
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


def test_audio_is_named_by_content(built, anki):
    manifest = read_manifest(manifest_path(built.apkg))
    assert set(manifest["notes"]) == {f"{e.kind}:{e.id}" for e in built.ds.entries}
    total = 0
    for e in built.ds.entries:
        audio = manifest["notes"][f"{e.kind}:{e.id}"]["audio"]
        assert ("term" in audio) == bool(e.speech), e.id
        fields = note(anki, e)[0]
        for slot, name in audio.items():
            part = "" if slot == "term" else f"-{slot}"
            assert re.fullmatch(rf"uke-{e.kind}-{re.escape(e.id)}{part}-[0-9a-f]{{8}}\.mp3", name), name
            assert name in anki.media
            assert fields[FIELDS.index(AUDIO_FIELDS[slot])] == f"[sound:{name}]"
        total += len(audio)
    assert len(anki.media) == total


def test_every_side_is_spoken(built, anki):
    """Hands free: each card's front and back has audio, so auto advance can run a session."""
    for e in built.ds.entries:
        fields = note(anki, e)[0]
        spoken = lambda f: fields[FIELDS.index(f)].startswith("[sound:")
        assert spoken("PromptAudio") and spoken("AnswerAudio"), e.id      # card 2 front, card 1 back
        assert spoken("Audio") == bool(e.speech), e.id                      # card 1 front, card 2 back
        assert spoken("BreakdownAudio") == bool(breakdown_prompt(e)[0]), e.id  # card 3 back


def test_templates_play_each_clip_on_the_right_side():
    t = {tpl["name"][0]: tpl for tpl in MODEL.templates}
    back = lambda n: t[n]["afmt"].split('<hr id="answer">', 1)[1]   # the part after {{FrontSide}}
    assert "{{Audio}}" in t["1"]["qfmt"] and "{{AnswerAudio}}" in back("1")
    assert "{{PromptAudio}}" in t["2"]["qfmt"] and "{{Audio}}" in back("2")
    assert "{{Audio}}" in t["3"]["qfmt"] and "{{BreakdownAudio}}" in back("3")
    for n in "123":
        # front audio replays only through {{FrontSide}}, which Anki does not autoplay on the back
        assert "{{Audio}}" not in back(n) or n == "2"


def test_spoken_answer_says_roots_and_meaning(built):
    synth = built.synth
    e = built.ds.by_id("term", "kotegaeshi")
    pieces = answer_pieces(synth, e)
    clips = [p for p in pieces if isinstance(p, Path)]
    assert len(clips) == 2 * len(e.segments[0].roots) + 1      # each root in Japanese and English, then the meaning
    assert clips[-1] == synth.clip(e.meaning + ".", "en")
    kumi = built.ds.by_id("kumi_waza", "katadori-ikkyo-omote-katameru")
    said = [p for p in breakdown_pieces(synth, kumi) if isinstance(p, Path)]
    assert said[:3] == [synth.clip(kumi.segments[0].role, "en"), synth.clip(kumi.segments[0].speech, "ja"),
                        synth.clip(kumi.segments[0].gloss, "en")]
    assert len(said) == 3 * len(kumi.segments)


def test_juntai_is_spoken_in_english_only(built, anki):
    fields = note(anki, built.ds.by_id("term", "juntai"))[0]
    assert fields[FIELDS.index("Audio")] == ""
    assert fields[FIELDS.index("PromptAudio")].startswith("[sound:")
    assert fields[FIELDS.index("AnswerAudio")].startswith("[sound:")


def test_changed_speech_changes_only_its_audio(built, tmp_path):
    """A tts_kana fix renames the audio of the entries that speak it, so Anki takes the new sound."""
    shutil.copytree(built.root / "data", tmp_path / "data")
    terms = tmp_path / "data" / "terms.yaml"
    text = terms.read_text(encoding="utf-8")
    assert 'tts_kana: "かたてこーさどり"' in text
    terms.write_text(text.replace('tts_kana: "かたてこーさどり"', 'tts_kana: "かたてこーさどりー、どり"'),
                     encoding="utf-8")
    ds = load(tmp_path)
    synth = Synth(SilentEngine(), tmp_path / "build" / "cache")
    apkg = build_deck(ds, synth, tmp_path / "build" / "uke.apkg", [])

    old, new = read_manifest(manifest_path(built.apkg)), read_manifest(manifest_path(apkg))
    c = compare(old, new)
    assert not c.added and not c.removed
    assert "term:katatekosadori" in c.changed
    assert all("katatekosadori" in k for k in c.changed), c.changed
    for k in c.changed:
        assert new["notes"][k]["audio"] != old["notes"][k]["audio"]
    for k in set(new["notes"]) - set(c.changed):
        assert new["notes"][k] == old["notes"][k], k


def test_rebuild_reports_no_changes(built, tmp_path):
    apkg = build_deck(built.ds, built.synth, tmp_path / "uke.apkg", [])
    c = compare(read_manifest(manifest_path(built.apkg)), read_manifest(manifest_path(apkg)))
    assert c.added == c.changed == c.removed == []


def test_removed_entries_are_reported_with_a_search(built):
    old = read_manifest(manifest_path(built.apkg))
    new = {"notes": {k: v for k, v in old["notes"].items() if k != "term:juntai"}}
    c = compare(old, new)
    assert c.removed == ["term:juntai"] and c.added == c.changed == []
    assert anki_search("term:juntai", old["notes"]["term:juntai"]) == '"deck:Uke::Terms" "Id:juntai"'
    assert compare(new, old).added == ["term:juntai"]

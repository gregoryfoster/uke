# Aikido terminology tool

Learn the Japanese terms of Aikido Olympia (Aikido Yuishinkai) by their roots, their English meanings,
the movement, and the principle behind each technique.

## Layout

| Path | What it holds |
| --- | --- |
| `data/roots.yaml` | Roots (morphemes) with kana, kanji, meaning and review status |
| `data/terms.yaml` | Attacks, techniques, directions, finishes and practice vocabulary, built from roots |
| `data/kata.yaml` | The 21 Yuishinkai Aikido Kata |
| `data/kumi_waza.yaml` | Partner techniques composed from terms, including the 8 Basic Arts |
| `data/grades.yaml` | Grade requirements and the current study profile |
| `data/media.yaml` | Video links from the dojo criteria |
| `data/principles.yaml` | Motto line themes and dojo principles |
| `data/sources.yaml` | The documents everything cites |
| `personal.example/` | Templates for personal data (motto text, reflections); copy to `personal/`, which git ignores |
| `scripts/validate.py` | Checks references and reports the study set and review status |

## Check the data

```
pip install -r requirements.txt
python scripts/validate.py
```

## Review status

Every root starts as `draft`. Sensei confirms meanings (`status: confirmed`);
kanji are checked in a trusted dictionary (`kanji_status: verified`).

## Build the deck and commute audio (Phase 1)

Needs Python 3.10+ and ffmpeg (`brew install ffmpeg`). Output goes to `build/`, which git ignores.

```
pip install -r requirements.txt
python -m uke build all            # or: build deck, build audio
```

| Output | What it is |
| --- | --- |
| `build/uke.apkg` | Anki deck: one note per kumi waza entry, kata and term, three cards each (Japanese to meaning, English to Japanese, breakdown). Tagged `uke::study`, `uke::review` or `uke::later` and `grade::4kyu` etc., so filtered decks can pick the study set. |
| `build/audio/study/*.mp3` | Commute audio, one file per study-set entry: Japanese term, pause, roots and English meaning, pause. Audio only. |
| `build/audio/uke-study-loop.mp3` | All study-set entries in one file, plus `uke-study.m3u` |

The study set is the next exam in `data/grades.yaml` (`profile.next_exam`) plus the grade above it.
Entries with `kana: null` (e.g. Juntai) get cards but no audio, and the build prints a warning.

### Text-to-speech

Japanese is synthesized from the `kana` field, never from romaji. Clips are cached in `build/cache/tts/`,
so only new or changed text is synthesized.

| `--engine` | Notes |
| --- | --- |
| `google` (default) | Google Cloud Text-to-Speech, voice Chirp 3 HD Kore in both languages. Set `UKE_GCP_PROJECT` (or `--gcp-project`) and log in with `gcloud auth application-default login`. |
| `say` | macOS voices, offline. Install Kyoko (Premium) in System Settings > Accessibility > Spoken Content for better Japanese. |
| `edge` | Microsoft Edge read-aloud voices. Free and keyless, but an unofficial endpoint. |
| `silent` | Silence sized to the text, for tests. |

Pick voices with `--ja-voice` / `--en-voice` (or `UKE_JA_VOICE` / `UKE_EN_VOICE`). `python -m uke voices`
lists Google voices; `python -m uke sample --engine google --ja-voice ja-JP-Neural2-B --en-voice en-US-Neural2-F` renders five terms
to `build/tts-samples/` for comparison. Check pronunciation with Sensei before relying on a voice.

### Tests

```
pip install -r requirements-dev.txt
python -m pytest
```

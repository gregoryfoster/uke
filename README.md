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

## Setup

The project uses [uv](https://docs.astral.sh/uv/). `uv sync` creates `.venv/` with the locked dependencies
(Python version from `.python-version`); `uv run` does the same on demand.

```
uv sync
```

## Check the data

```
uv run scripts/validate.py
```

## Review status

Every root starts as `draft`. Sensei confirms meanings (`status: confirmed`);
kanji are checked in a trusted dictionary (`kanji_status: verified`).

## Build the deck and commute audio (Phase 1)

Needs ffmpeg (`brew install ffmpeg`). Output goes to `build/`, which git ignores.

```
uv run uke build all               # or: build deck, build audio
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

All-hiragana text gives the voice no word boundaries, so it can misread a long vowel: it read
かたてこうさどり as "katateko… usadori", with a pause inside こうさ. When that happens, add `tts_kana`
to the term or kata with the long vowel written as ー (`tts_kana: "かたてこーさどり"`). The voice reads
`tts_kana`; cards still show `kana`. The validator checks that `tts_kana` is kana only.

| `--engine` | Notes |
| --- | --- |
| `google` (default) | Google Cloud Text-to-Speech, voice Chirp 3 HD Kore in both languages. Set `UKE_GCP_PROJECT` (or `--gcp-project`) and log in once to uke's own gcloud config (see below). |
| `say` | macOS voices, offline. Install Kyoko (Premium) in System Settings > Accessibility > Spoken Content for better Japanese. |
| `edge` | Microsoft Edge read-aloud voices. Free and keyless, but an unofficial endpoint. |
| `silent` | Silence sized to the text, for tests. |

Pick voices with `--ja-voice` / `--en-voice` (or `UKE_JA_VOICE` / `UKE_EN_VOICE`). `uv run uke voices`
lists Google voices; `uv run uke sample --engine google --ja-voice ja-JP-Neural2-B --en-voice en-US-Neural2-F` renders five terms
to `build/tts-samples/` for comparison. Check pronunciation with Sensei before relying on a voice.

#### Google credentials

uke reads Google credentials only from its own gcloud config directory, `~/.config/gcloud-uke`
(override with `UKE_GCLOUD_CONFIG`). Log in there once:

```
CLOUDSDK_CONFIG=~/.config/gcloud-uke gcloud auth application-default login
```

Don't use the plain `gcloud auth application-default login`: it overwrites
`~/.config/gcloud/application_default_credentials.json`, which every project on the machine shares,
and silently changes which identity their code runs as. For the same reason uke ignores that file and
`GOOGLE_APPLICATION_CREDENTIALS`. No `set-quota-project` is needed; uke sends `UKE_GCP_PROJECT` as
the quota project. If the file is missing, the google engine stops and prints the login command.

The committed `.envrc` sets `CLOUDSDK_CONFIG` for direnv, so `gcloud` commands typed in this repo use
the same directory. Put `UKE_GCP_PROJECT` in a gitignored `.env` next to it.

### Tests

```
uv run pytest
```

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
| `personal.example/` | The shape of your personal data (motto text, reflections, captures), which lives in a private store, never here |
| `scripts/validate.py` | Checks references and reports the study set and review status |
| `scripts/check_public.py` | Fails if personal data is committed to this public repo |

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

## Personal data

Motto text, your own reflections and post-class captures are personal, and this repo is public.
They live in a private store that uke syncs into a local directory, shaped like `personal.example/`.
uke reads that directory from `UKE_PERSONAL`, or from `personal/` in this checkout (gitignored), and
everything works without it.

A private GitHub repo is the first supported store; any repo name works. To set one up, create an
empty private repo (e.g. `uke-personal`), push the contents of `personal.example/` to it, then:

```
uv run uke personal init https://github.com/<you>/uke-personal.git   # clones into the personal directory
uv run uke personal status                                          # where it is, and what is not synced
uv run uke personal sync                                            # commit local changes, pull, push
```

To keep it somewhere other than `personal/`, set `UKE_PERSONAL` (e.g. in `.env`) before `init`; a
relative path is relative to this repo, e.g. `../uke-personal`. In a git worktree of uke, both the
default and a relative path are taken from the main checkout, so all worktrees share one personal
directory. Any address git can clone works,
including `me@host:repo` and local paths. `status` fetches first, so it also shows changes made on
the phone that are not pulled yet.
On the phone, add or edit files in the private repo on github.com (Add file > Create new file), for
example a voice-memo transcript in `captures/inbox/`; the next `uke personal sync` brings it down.
If the same file changed in both places, sync stops before pushing, keeps your local changes committed,
and leaves the clone clean; resolve it with `git pull --rebase` in the personal directory. Any other
failure (offline, credentials) is reported as git reported it.
Other stores, such as a Google Cloud Storage bucket, are not supported yet; each is one `Store`
subclass in `uke/personal.py`.

The validator checks personal files when present (known subjects, principle and motto ids, dates)
and prints counts only, never their content. CI runs `scripts/check_public.py` on every commit of a
PR and fails if personal data appears: a path under `personal/` or `captures/`, a file in
`personal.example/` that is not part of the template, a filled-in template, or a `motto_text` or
`reflections` key in any other text file, in YAML, JSON, quoted or flow style (Python under `tests/` is
skipped, since the tests build fake personal files). It checks the whole repo from any directory.
The template's `.gitignore` keeps OS and editor files, which can hold unsaved drafts, out of the
private store. Run it before committing:

```
uv run scripts/check_public.py
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
| `build/uke.apkg` | Anki deck: one note per kumi waza entry, kata and term, three cards each (Japanese to meaning, English to Japanese, breakdown). Every side is spoken, so it runs hands free (see below). Tagged `uke::study`, `uke::review` or `uke::later` and `grade::4kyu` etc., so filtered decks can pick the study set. |
| `build/audio/study/*.mp3` | Commute audio, one file per study-set entry: Japanese term, pause, roots and English meaning, pause. Audio only. |
| `build/audio/uke-study-loop.mp3` | All study-set entries in one file, plus `uke-study.m3u` |
| `build/uke.manifest.json` | The deck's notes with a fingerprint of each, so the next build can say what changed |

The study set is the next exam in `data/grades.yaml` (`profile.next_exam`) plus the grade above it.
Entries with `kana: null` (e.g. Juntai) get cards but no audio, and the build prints a warning.

### Updating the deck in Anki

Rebuild, then import `uke.apkg` again: on Android, open it in AnkiDroid. Each note's id comes from its
entry id in `data/`, so re-importing updates existing cards in place and keeps their review history.

On the import screen, set **Update notes** and **Update note types** to **Always** and turn on
**Merge note types** (checked in AnkiDroid 2.25.3). With the defaults, cards are not updated when the
note type has changed, for example when a build adds a field. "Always" is safe because the deck is
generated: nothing in it is edited in Anki.

- **Changed audio:** card audio files are named by their content (`uke-term-shomenuchi-160d1508.mp3`),
  so a fixed pronunciation gets a new file name and replaces the old sound. Anki would otherwise keep
  a file it already has with the same name. Old files linger until you run Check Media and delete the unused ones
  (AnkiDroid: the deck list's menu > Check media; desktop: Tools > Check Media).
- **Removed or renamed entries:** re-importing never deletes cards. The build compares itself with the
  previous build in the same folder and lists what was added, changed and removed. For each removed
  entry it prints an Anki search such as `"deck:Uke::Terms" "Id:juntai"`; paste it into the Browse
  window, then delete or suspend the note.
- **Anki is read-only:** every field is overwritten on re-import, so anything typed into a card in
  Anki is lost. Your own notes and reflections belong in your personal data, not in the deck.

### Hands free: auto advance in AnkiDroid

Every side of every card is spoken, so the deck can run without touching the phone:

| Card | Front says | Back says |
| --- | --- | --- |
| 1 Japanese to meaning | the term | each root (Japanese, then English), then the meaning |
| 2 English to Japanese | the English prompt | the term |
| 3 Breakdown | the term | each part's role and gloss, or each root's meaning |

The front's audio is not replayed on the back. Anki's auto advance supplies the two waits. In
AnkiDroid (checked in 2.25.3), open the options for the Uke deck and, under **Auto Advance**, set:

| Setting | Value | Why |
| --- | --- | --- |
| Seconds to show question for | e.g. 7 | time to recall before the answer is spoken |
| Seconds to show answer for | e.g. 5 | pause after the answer, before the next card |
| Wait for audio | on | each wait starts after the speech ends |
| Question action | Show Answer | |
| Answer action | Bury Card | hands free, no card is graded: burying hides it for the rest of the day and leaves its interval unchanged |

Options belong to a preset that other decks may share ("Default (used by 5 decks)"); auto advance
still only runs when you turn it on. Start studying the deck and AnkiDroid offers to turn on auto
advance. A review card buried this way comes back tomorrow, a day late; study it normally if that
matters.

The commute MP3s (`uke build audio`) are the same pattern without Anki: term, pause, roots and
meaning, pause, with the pauses set by `--recall-pause` and `--after-pause`.

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

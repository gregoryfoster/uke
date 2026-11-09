# Aikido terminology tool

A personal learning tool for Aikido Olympia (Aikido Yuishinkai). It binds four things to every term:
the Japanese words and their roots, the English meanings, the movement, and the principle behind it.

Plan and rationale: https://claude.ai/artifact/Wt9bbupi47Y9yPzaJipMEe

## Priorities (in order)
1. Understand the principle behind each technique.
2. Hear a term in class and move without hesitation.
3. Be ready for kyu examinations.
4. Explain techniques and their meanings to others.

Built for one student (currently 5th kyu) first, dojo mates later.

## Data rules
- `data/` is the single source of truth. Decks, audio and the app are generated from it; never hand-edit generated output.
- The dojo criteria (`dojo-criteria-2022` in `data/sources.yaml`) outrank every other source. Do not add techniques,
  grades or requirements that are not in a cited source.
- Dojo spelling is primary (Shomenuchi, Ikkyo). Headquarters spellings (Shoumenuchi, Ikkyou) go in `spelling_variants`.
- Roots carry `status` (draft -> confirmed by Sensei) and `kanji_status` (draft -> verified in a trusted dictionary).
  Never mark either as confirmed or verified without the user saying so.
- Never invent kanji. If unsure, set `kana`/`kanji` to null with a `note`, as with Juntai.
- This repo is public. Never commit motto text, reflections, voice notes or other personal practice data.
  Those live in `personal/` (gitignored); `personal.example/` shows the shape. Code must run when `personal/` is absent.
- Never write motto text yourself; only the user pastes it.
- Kumi waza are composed from term ids in `parts`; one entry per direction (omote/ura) so each is recalled separately.

## Before committing
Run `python scripts/validate.py`. It must exit 0. Mention any new warnings in the PR description.

## Phases
- Phase 0 (now): data files, roots table, validator.
- Phase 1: generate a spaced-repetition deck and commute audio from `data/`; daily ritual; post-class voice notes.
- Phase 2: phone-friendly web app over the term graph; "Sensei calls it" drill; four-direction recall.
- Phase 3: kana and kanji views, diagrams for clip gaps, dojo footage, sharing with dojo mates.

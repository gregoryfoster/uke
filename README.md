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

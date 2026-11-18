# uke personal data

Personal practice data for [uke](https://github.com/gregoryfoster/uke): motto text, reflections and
post-class captures. Keep this repository **private**; uke itself is public and never stores these files.

| Path | What it holds |
| --- | --- |
| `motto.yaml` | The dojo motto lines, pasted in your own copy |
| `reflections.yaml` | Your own "why" for each technique: subject, date, principle id, text |
| `captures/inbox/` | Post-class voice-memo transcripts, dropped here from the phone |
| `.gitignore` | Keeps OS and editor files (which can hold unsaved drafts) out of `uke personal sync` |

uke reads this directory from `UKE_PERSONAL`, or from `personal/` inside the uke checkout.
`uke personal sync` pulls and pushes it; see uke's README, "Personal data".

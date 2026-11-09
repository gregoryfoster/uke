#!/usr/bin/env python3
"""Check the term graph for broken references and report what still needs review.

Usage: python scripts/validate.py
Exit code 1 if any error is found; warnings never fail the run.
"""
import sys
from collections import Counter
from pathlib import Path

import yaml

DATA = Path(__file__).resolve().parent.parent / "data"
errors, warnings = [], []


def load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def check_unique(items, label):
    counts = Counter(i["id"] for i in items)
    for i, n in counts.items():
        if n > 1:
            errors.append(f"{label}: id '{i}' appears {n} times")
    return {i["id"]: i for i in items}


roots = check_unique(load("roots.yaml")["roots"], "roots")
terms = check_unique(load("terms.yaml")["terms"], "terms")
kata = check_unique(load("kata.yaml")["kata"], "kata")
kumi = check_unique(load("kumi_waza.yaml")["kumi_waza"], "kumi_waza")
media = check_unique(load("media.yaml")["media"], "media")
g = load("grades.yaml")
grades = check_unique(g["grades"], "grades")
p = load("principles.yaml")
principles = check_unique(p["principles"], "principles")
sources = check_unique(load("sources.yaml")["sources"], "sources")

# roots referenced by terms and kata
used_roots = set()
for label, coll in (("term", terms), ("kata", kata)):
    for item in coll.values():
        for r in item.get("roots", []):
            used_roots.add(r)
            if r not in roots:
                errors.append(f"{label} '{item['id']}': unknown root '{r}'")
for r in roots.values():
    for h in r.get("homophones", []):
        if h not in roots:
            errors.append(f"root '{r['id']}': unknown homophone '{h}'")
unused = sorted(set(roots) - used_roots)
if unused:
    warnings.append(f"roots not used by any term or kata yet: {', '.join(unused)}")

# kumi waza parts
for k in kumi.values():
    for part in k["parts"]:
        if part not in terms:
            errors.append(f"kumi_waza '{k['id']}': unknown part '{part}'")

# grades
for gr in grades.values():
    for k in gr.get("kumi_waza", []):
        if k not in kumi:
            errors.append(f"grade '{gr['id']}': unknown kumi_waza '{k}'")
    for e in gr.get("exercises", []):
        if e not in terms:
            errors.append(f"grade '{gr['id']}': unknown exercise '{e}'")
    for lv in gr.get("levels", []):
        if lv not in terms:
            errors.append(f"grade '{gr['id']}': unknown level '{lv}'")
    for fa in gr.get("free_arts", []):
        if fa["attack"] not in terms:
            errors.append(f"grade '{gr['id']}': unknown free_arts attack '{fa['attack']}'")
for key in ("current_rank", "next_exam"):
    if g["profile"][key] not in grades:
        errors.append(f"profile.{key}: unknown grade '{g['profile'][key]}'")

# media subjects
subjects = set(kumi) | set(kata) | set(terms) | {"kata-all"}
covered = set()
for m in media.values():
    s = m.get("subject")
    if s is None:
        continue
    if s not in subjects:
        errors.append(f"media '{m['id']}': unknown subject '{s}'")
    covered.add(s)

# principles
for pr in principles.values():
    if pr["source"] not in sources:
        errors.append(f"principle '{pr['id']}': unknown source '{pr['source']}'")
    for t in pr.get("terms", []):
        if t not in terms:
            errors.append(f"principle '{pr['id']}': unknown term '{t}'")

# ---- report ----
def name(k):
    return " ".join(terms[p]["romaji"] for p in k["parts"])


order = {gr["id"]: gr["order"] for gr in grades.values()}
nxt = g["profile"]["next_exam"]
study = [gid for gid, o in sorted(order.items(), key=lambda x: x[1]) if order[nxt] <= o <= order[nxt] + 1]
study_kumi = [k for gid in study for k in grades[gid].get("kumi_waza", [])]
basic = sorted((k for k in kumi.values() if k.get("basic_art")), key=lambda k: k["basic_art"])

print(f"roots {len(roots)} · terms {len(terms)} · kata {len(kata)} · kumi waza {len(kumi)} · media {len(media)}")
print(f"roots awaiting Sensei: {sum(r['status'] != 'confirmed' for r in roots.values())}")
print(f"kanji awaiting dictionary check: {sum(r.get('kanji_status') != 'verified' for r in roots.values())}")
personal = DATA.parent / "personal" / "motto.yaml"
if personal.exists():
    with open(personal, encoding="utf-8") as f:
        texts = (yaml.safe_load(f) or {}).get("motto_text", {})
    print(f"motto lines still empty: {sum(not texts.get(m['id']) for m in p['motto'])}")
else:
    print("motto text: not set up (copy personal.example/ to personal/)")
print(f"\nstudy set ({' + '.join(study)}), plus the 8 Basic Arts in review:")
for k in dict.fromkeys(study_kumi):
    flag = "" if k in covered else "   <- no clip"
    print(f"  {name(kumi[k])}{flag}")
print("\n8 Basic Arts:")
for k in basic:
    flag = "" if k["id"] in covered else "   <- no clip"
    print(f"  {k['basic_art']}. {name(k)}{flag}")

for w in warnings:
    print(f"\nwarning: {w}")
if errors:
    print("\nERRORS:")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
print("\nOK: no broken references.")

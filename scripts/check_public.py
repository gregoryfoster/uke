#!/usr/bin/env python3
"""Fail if personal data is committed to this public repo.

Usage: uv run scripts/check_public.py [REV ...]
Checks each git revision given (default: HEAD and the staged index). CI passes every commit of a PR,
because a file added in one commit and deleted in the next would still be public in the history.

Personal data belongs in the private personal store (see README, "Personal data"):
- no path under personal/ or captures/
- no motto_text key outside personal.example/motto.yaml, whose values must all stay null
- personal.example/reflections.yaml must keep an empty list
Messages name files and keys only, never their content.
"""
import re
import subprocess
import sys

import yaml

TEMPLATE_MOTTO = "personal.example/motto.yaml"
TEMPLATE_REFLECTIONS = "personal.example/reflections.yaml"
MOTTO_KEY = re.compile(r"^\s*motto_text\s*:", re.M)
INDEX = ":index"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def files(rev: str) -> list[str]:
    if rev == INDEX:
        return git("ls-files", "-z").split("\0")[:-1]
    return git("ls-tree", "-r", "-z", "--name-only", rev).split("\0")[:-1]


def read(rev: str, path: str) -> str:
    spec = f":{path}" if rev == INDEX else f"{rev}:{path}"
    try:
        return git("show", spec)
    except subprocess.CalledProcessError:
        return ""


def check(rev: str) -> list[str]:
    problems = []
    paths = files(rev)
    for path in paths:
        if path.startswith(("personal/", "captures/")):
            problems.append(f"{path}: personal data path")
    text_paths = [p for p in paths if p.endswith((".yaml", ".yml", ".json", ".md", ".txt"))]
    for path in text_paths:
        if path != TEMPLATE_MOTTO and MOTTO_KEY.search(read(rev, path)):
            problems.append(f"{path}: has a motto_text key")
    if TEMPLATE_MOTTO in paths:
        motto = (yaml.safe_load(read(rev, TEMPLATE_MOTTO)) or {}).get("motto_text") or {}
        filled = [k for k, v in motto.items() if v is not None]
        if filled:
            problems.append(f"{TEMPLATE_MOTTO}: motto_text must stay null, filled: {', '.join(filled)}")
    if TEMPLATE_REFLECTIONS in paths:
        if (yaml.safe_load(read(rev, TEMPLATE_REFLECTIONS)) or {}).get("reflections"):
            problems.append(f"{TEMPLATE_REFLECTIONS}: reflections must stay an empty list")
    return problems


def main(revs: list[str]) -> int:
    failed = False
    for rev in revs or ["HEAD", INDEX]:
        label = "staged changes" if rev == INDEX else git("rev-parse", "--short", rev).strip()
        for problem in check(rev):
            print(f"{label}: {problem}")
            failed = True
    if failed:
        print("\nPersonal data must not be committed here; keep it in your private personal store.")
        return 1
    print("OK: no personal data in the checked revisions.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

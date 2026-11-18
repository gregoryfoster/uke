#!/usr/bin/env python3
"""Fail if personal data is committed to this public repo.

Usage: uv run scripts/check_public.py [REV ...]
Checks each git revision given (default: HEAD and the staged index). CI passes every commit of a PR,
because a file added in one commit and deleted in the next would still be public in the history.

Personal data belongs in the private personal store (see README, "Personal data"):
- no path under personal/ or captures/
- personal.example/ holds only its template files, and they stay empty
- no motto_text or reflections key in any other text file
Messages name files and keys only, never their content.
"""
import subprocess
import sys

import yaml

TEMPLATE = "personal.example/"
TEMPLATE_MOTTO = TEMPLATE + "motto.yaml"
TEMPLATE_REFLECTIONS = TEMPLATE + "reflections.yaml"
TEMPLATE_FILES = {TEMPLATE_MOTTO, TEMPLATE_REFLECTIONS, TEMPLATE + "README.md", TEMPLATE + "captures/inbox/.gitkeep"}
PERSONAL_KEYS = r"^[[:space:]]*(motto_text|reflections)[[:space:]]*:"
INDEX = ":index"


def git(*args: str, ok=(0,)) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode not in ok:
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def files(rev: str) -> list[str]:
    if rev == INDEX:
        return git("ls-files", "-z").split("\0")[:-1]
    return git("ls-tree", "-r", "-z", "--name-only", rev).split("\0")[:-1]


def with_personal_keys(rev: str) -> list[str]:
    """Text files at rev with a line that starts a motto_text or reflections key (one git process)."""
    where = ["--cached", "-E", "-e", PERSONAL_KEYS] if rev == INDEX else ["-E", "-e", PERSONAL_KEYS, rev]
    out = git("grep", "-I", "-l", "-z", *where, ok=(0, 1))
    prefix = "" if rev == INDEX else f"{rev}:"
    return [p.removeprefix(prefix) for p in out.split("\0") if p]


def read(rev: str, path: str) -> str:
    return git("show", f":{path}" if rev == INDEX else f"{rev}:{path}")


def check(rev: str) -> list[str]:
    problems = []
    paths = files(rev)
    for path in paths:
        if path.startswith(("personal/", "captures/")):
            problems.append(f"{path}: personal data path")
        elif path.startswith(TEMPLATE) and path not in TEMPLATE_FILES:
            problems.append(f"{path}: not part of the personal.example/ template")
    for path in with_personal_keys(rev):
        if path not in (TEMPLATE_MOTTO, TEMPLATE_REFLECTIONS):
            problems.append(f"{path}: has a motto_text or reflections key")
    if TEMPLATE_MOTTO in paths:
        motto = (yaml.safe_load(read(rev, TEMPLATE_MOTTO)) or {}).get("motto_text") or {}
        filled = [str(k) for k, v in motto.items() if v is not None] if isinstance(motto, dict) else ["(not a mapping)"]
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

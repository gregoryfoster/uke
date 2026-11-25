#!/usr/bin/env python3
"""Fail if personal data is committed to this public repo.

Usage: uv run scripts/check_public.py [REV ...]
Checks each git revision given (default: HEAD and the staged index), across the whole repo wherever it
is run from. CI passes every commit of a PR, because a file added in one commit and deleted in the next
would still be public in the history.

Personal data belongs in the private personal store (see README, "Personal data"):
- no path under personal/ or captures/
- personal.example/ holds only its template files, and they stay empty (motto keys are motto ids)
- no motto_text or reflections key in any other text file: YAML, JSON, quoted or flow style.
  In Python only quoted keys count (a dict literal could hold real text; `motto_text: str` is an
  annotation), and Python under tests/ is skipped, since the tests build fake personal files in code.
Messages name files and keys only, never their content, and never echo a parse error (it quotes the line).
"""
import re
import subprocess
import sys

import yaml

TEMPLATE = "personal.example/"
TEMPLATE_MOTTO = TEMPLATE + "motto.yaml"
TEMPLATE_REFLECTIONS = TEMPLATE + "reflections.yaml"
TEMPLATE_KEEP = TEMPLATE + "captures/inbox/.gitkeep"
TEMPLATE_FILES = {TEMPLATE_MOTTO, TEMPLATE_REFLECTIONS, TEMPLATE + "README.md", TEMPLATE + ".gitignore", TEMPLATE_KEEP}
MOTTO_ID = re.compile(r"motto-[0-9]+")
# the key at a line start, after "- ", "{" or ",", optionally quoted: YAML block, flow and JSON styles
PERSONAL_KEYS = r"""(^|[-{,[:space:]])["']?(motto_text|reflections)["']?[[:space:]]*:"""
# in Python, only a quoted key, as in a dict literal that could hold real text
QUOTED_KEYS = r"""["'](motto_text|reflections)["'][[:space:]]*:"""
INDEX = ":index"
SELF = "scripts/check_public.py"


def git(*args: str, ok=(0,), cwd=None) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd or TOP)
    if r.returncode not in ok:
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def files(rev: str) -> list[str]:
    if rev == INDEX:
        return git("ls-files", "-z").split("\0")[:-1]
    return git("ls-tree", "-r", "-z", "--name-only", rev).split("\0")[:-1]


def grep(rev: str, pattern: str, *pathspec: str) -> list[str]:
    """Text files at rev, within pathspec, with a line matching pattern."""
    where = ["--cached", "-E", "-e", pattern] if rev == INDEX else ["-E", "-e", pattern, rev]
    out = git("grep", "-I", "-l", "-z", *where, "--", *pathspec, ok=(0, 1))
    prefix = "" if rev == INDEX else f"{rev}:"
    return [p.removeprefix(prefix) for p in out.split("\0") if p]


def with_personal_keys(rev: str) -> list[str]:
    """Text files at rev with a motto_text or reflections key (two git processes)."""
    # this script describes the keys it looks for, so it is never scanned itself; CI runs the newest
    # version over every commit of a PR, so the exclusion also covers this file's earlier versions
    return (grep(rev, PERSONAL_KEYS, ".", ":(exclude,glob)**/*.py")
            + grep(rev, QUOTED_KEYS, ":(glob)**/*.py", ":(exclude,glob)tests/**/*.py", f":(exclude){SELF}"))


def read(rev: str, path: str) -> str:
    return git("show", f":{path}" if rev == INDEX else f"{rev}:{path}")


def template(rev: str, path: str, key: str, problems: list[str]):
    """A template's top-level key, or None after recording a problem. Parse errors are not echoed."""
    try:
        doc = yaml.safe_load(read(rev, path))
    except Exception:  # YAMLError quotes the offending line; ValueError comes from impossible dates
        problems.append(f"{path}: not valid YAML")
        return None
    if doc is not None and not isinstance(doc, dict):
        problems.append(f"{path}: must be a mapping with a {key} key")
        return None
    return (doc or {}).get(key)


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
        motto = template(rev, TEMPLATE_MOTTO, "motto_text", problems) or {}
        if not isinstance(motto, dict):
            problems.append(f"{TEMPLATE_MOTTO}: motto_text must be a mapping of motto ids to null")
        elif not all(isinstance(k, str) and MOTTO_ID.fullmatch(k) for k in motto):
            problems.append(f"{TEMPLATE_MOTTO}: motto_text keys must be motto ids (motto-1, motto-2, ...)")
        elif any(v is not None for v in motto.values()):
            filled = [k for k, v in motto.items() if v is not None]
            problems.append(f"{TEMPLATE_MOTTO}: motto_text must stay null, filled: {', '.join(filled)}")
    if TEMPLATE_REFLECTIONS in paths and template(rev, TEMPLATE_REFLECTIONS, "reflections", problems):
        problems.append(f"{TEMPLATE_REFLECTIONS}: reflections must stay an empty list")
    if TEMPLATE_KEEP in paths and read(rev, TEMPLATE_KEEP).strip():
        problems.append(f"{TEMPLATE_KEEP}: must stay empty")
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


# every git command runs at the top of the work tree, so ls-tree, ls-files and grep see the whole repo
TOP = git("rev-parse", "--show-toplevel", cwd=".").strip()

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

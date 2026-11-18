"""Personal data: motto text, reflections and captures, kept outside this public repo.

uke always reads personal data from a local directory: $UKE_PERSONAL, else personal/ in the repo.
Everything must keep working when that directory is absent, and nothing here prints its content.

A store keeps the directory in step with where it lives remotely. Git (e.g. a private GitHub repo)
is the first provider. To add another, such as a Google Cloud Storage bucket, write a Store subclass
that implements handles(), found_in(), fetch() and sync(), add it to PROVIDERS, and drop its entry
from UNSUPPORTED.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from . import REPO


def personal_dir(repo: Path = REPO) -> Path:
    """Where personal data lives locally: $UKE_PERSONAL, else personal/ next to data/."""
    env = os.environ.get("UKE_PERSONAL")
    return Path(env).expanduser().resolve() if env else repo / "personal"


class StoreError(RuntimeError):
    pass


CREDENTIALS = re.compile(r"(\b[a-z][a-z0-9+.-]*://)[^/@\s]+@", re.I)


def redact(text: str) -> str:
    """Hide credentials embedded in URLs (https://user:token@host/...)."""
    return CREDENTIALS.sub(r"\1***@", text)


class Store:
    """A local personal directory and the remote it syncs with."""
    provider = "none"

    def __init__(self, path: Path):
        self.path = path

    @classmethod
    def handles(cls, url: str) -> bool:
        """Whether this provider can fetch from url."""
        return False

    @classmethod
    def found_in(cls, path: Path) -> bool:
        """Whether an existing directory was fetched by this provider."""
        return False

    @classmethod
    def fetch(cls, url: str, path: Path) -> Store:
        """Create path from the remote at url."""
        raise StoreError(f"{cls.provider} stores cannot be fetched")

    def remote(self) -> str | None:
        """The remote, safe to print."""
        return None

    def pending(self) -> list[str]:
        """Local changes not yet sent to the remote, one line each (file names, never content)."""
        return []

    def sync(self, message: str) -> str:
        """Fetch remote changes, then send local ones. Returns a one-line summary."""
        return "nothing to sync: this directory has no remote store"


class LocalStore(Store):
    """A plain directory with no remote."""
    provider = "local"


class GitStore(Store):
    """A git clone, e.g. of a private GitHub repo. Edits made on github.com arrive on sync."""
    provider = "git"

    @classmethod
    def handles(cls, url):
        return url.startswith(("https://", "http://", "ssh://", "git@", "file://", "/")) or url.endswith(".git")

    @classmethod
    def found_in(cls, path):
        return (path / ".git").exists()

    @classmethod
    def fetch(cls, url, path):
        run_git(["clone", "-q", url, str(path)])
        return cls(path)

    def git(self, *args: str, check: bool = True) -> str:
        return run_git(["-C", str(self.path), *args], check=check)

    def remote(self):
        url = self.git("remote", "get-url", "origin", check=False)
        return redact(url) if url else None

    def pending(self):
        changes = [line for line in self.git("status", "--porcelain").splitlines() if line]
        ahead = self.git("rev-list", "--count", "@{upstream}..HEAD", check=False)
        if ahead and ahead != "0":
            changes.append(f"{ahead} commit(s) not pushed")
        return changes

    def in_progress(self) -> str | None:
        """A rebase or merge left unfinished in the clone, if any."""
        gitdir = Path(self.git("rev-parse", "--absolute-git-dir"))
        for name, what in (("rebase-merge", "rebase"), ("rebase-apply", "rebase"), ("MERGE_HEAD", "merge")):
            if (gitdir / name).exists():
                return what
        return None

    def sync(self, message):
        unfinished = self.in_progress()
        if unfinished:
            raise StoreError(f"a {unfinished} is unfinished in {self.path}; finish or abort it with git, then sync again")
        self.git("add", "-A")
        committed = bool(self.git("status", "--porcelain"))
        if committed:
            self.git("commit", "-q", "-m", message)
        try:
            self.git("pull", "-q", "--rebase")
        except StoreError:
            self.git("rebase", "--abort", check=False)
            raise StoreError(
                "the remote has changes that conflict with yours, so nothing was pushed"
                + (" (your changes are committed locally)" if committed else "")
                + f". Resolve them with git in {self.path} (git pull --rebase), then sync again.") from None
        self.git("push", "-q")
        return f"synced with {self.remote()}" + (" (committed local changes)" if committed else "")


def run_git(args: list[str], check: bool = True) -> str:
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True)
    except FileNotFoundError:
        raise StoreError("git is required for a git personal store; install it and try again") from None
    if check and r.returncode != 0:
        cmd = args[2] if args[:1] == ["-C"] else args[0]
        raise StoreError(redact(f"git {cmd} failed: {(r.stderr or r.stdout).strip()}"))
    return r.stdout.strip()


PROVIDERS: list[type[Store]] = [GitStore]
UNSUPPORTED = {"gs://": "Google Cloud Storage"}


def open_store(path: Path) -> Store:
    """The store for an existing personal directory, chosen by what is in it."""
    for cls in PROVIDERS:
        if cls.found_in(path):
            return cls(path)
    return LocalStore(path)


def store_for_url(url: str) -> type[Store]:
    """The provider for a remote URL, for `uke personal init`."""
    for prefix, name in UNSUPPORTED.items():
        if url.startswith(prefix):
            raise StoreError(f"{name} is not supported yet; use a git URL such as "
                             "https://github.com/<you>/uke-personal.git")
    for cls in PROVIDERS:
        if cls.handles(url):
            return cls
    raise StoreError(f"no personal store provider handles {redact(url)}")


def init(url: str, path: Path) -> Store:
    """Fetch a remote personal store into path, which must not exist yet."""
    if path.exists():
        raise StoreError(f"{path} already exists")
    return store_for_url(url).fetch(url, path)

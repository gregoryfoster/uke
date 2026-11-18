"""Personal data: motto text, reflections and captures, kept outside this public repo.

uke always reads personal data from a local directory: $UKE_PERSONAL, else personal/ in the repo.
Everything must keep working when that directory is absent.

A store keeps the directory in step with where it lives remotely. Git (e.g. a private GitHub repo)
is the first provider; another, such as a Google Cloud Storage bucket, is a new Store subclass plus
a branch in store_for_url() and open_store().
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from . import REPO


def personal_dir(repo: Path = REPO) -> Path:
    """Where personal data lives locally: $UKE_PERSONAL, else personal/ next to data/."""
    env = os.environ.get("UKE_PERSONAL")
    return Path(env).expanduser().resolve() if env else repo / "personal"


class StoreError(RuntimeError):
    pass


class Store:
    """A local personal directory and the remote it syncs with."""
    provider = "none"

    def __init__(self, path: Path):
        self.path = path

    def remote(self) -> str | None:
        return None

    def pending(self) -> list[str]:
        """Local changes not yet sent to the remote, one line each."""
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

    def git(self, *args: str, check: bool = True) -> str:
        r = subprocess.run(["git", "-C", str(self.path), *args], capture_output=True, text=True)
        if check and r.returncode != 0:
            raise StoreError(f"git {' '.join(args)} failed: {(r.stderr or r.stdout).strip()}")
        return r.stdout.strip()

    def remote(self) -> str | None:
        return self.git("remote", "get-url", "origin", check=False) or None

    def pending(self) -> list[str]:
        changes = [line for line in self.git("status", "--porcelain").splitlines() if line]
        ahead = self.git("rev-list", "--count", "@{upstream}..HEAD", check=False)
        if ahead and ahead != "0":
            changes.append(f"{ahead} commit(s) not pushed")
        return changes

    def sync(self, message: str) -> str:
        self.git("add", "-A")
        committed = bool(self.git("status", "--porcelain"))
        if committed:
            self.git("commit", "-q", "-m", message)
        self.git("pull", "-q", "--rebase")
        self.git("push", "-q")
        return f"synced with {self.remote()}" + (" (committed local changes)" if committed else "")


def open_store(path: Path) -> Store:
    """The store for an existing personal directory, chosen by what is in it."""
    if (path / ".git").exists():
        return GitStore(path)
    return LocalStore(path)


def store_for_url(url: str) -> type[Store]:
    """The provider for a remote URL, for `uke personal init`."""
    if url.startswith("gs://"):
        raise StoreError("Google Cloud Storage is not supported yet; use a git URL such as "
                         "https://github.com/<you>/uke-personal.git")
    return GitStore


def init(url: str, path: Path) -> Store:
    """Fetch a remote personal store into path, which must not exist yet."""
    if path.exists():
        raise StoreError(f"{path} already exists")
    cls = store_for_url(url)
    if cls is GitStore:
        r = subprocess.run(["git", "clone", "-q", url, str(path)], capture_output=True, text=True)
        if r.returncode != 0:
            raise StoreError(f"git clone failed: {r.stderr.strip()}")
    return open_store(path)

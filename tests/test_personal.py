"""Personal data: where it is read from, syncing it with a git store, and keeping it out of this repo.

Everything runs on local temporary repos; no network and no real personal data.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from uke import personal
from uke.personal import StoreError
from uke.__main__ import main

REPO = Path(__file__).resolve().parents[1]
SECRET = "a line only the student writes"


@pytest.fixture(autouse=True)
def git_identity(monkeypatch):
    for k in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{k}_NAME", "test")
        monkeypatch.setenv(f"GIT_{k}_EMAIL", "test@example.invalid")


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True).stdout


@pytest.fixture
def remote(tmp_path):
    """A bare repo seeded from personal.example/, standing in for the private GitHub repo."""
    seed = tmp_path / "seed"
    shutil.copytree(REPO / "personal.example", seed)
    git(tmp_path, "init", "-q", "-b", "main", str(seed))
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "seed")
    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "-q", "--bare", str(seed), str(bare))
    return bare


def test_personal_dir_defaults_to_repo_and_follows_env(tmp_path, monkeypatch):
    monkeypatch.delenv("UKE_PERSONAL")
    assert personal.personal_dir(tmp_path) == tmp_path / "personal"
    monkeypatch.setenv("UKE_PERSONAL", str(tmp_path / "anywhere" / "my-data"))
    assert personal.personal_dir(tmp_path) == (tmp_path / "anywhere" / "my-data").resolve()


def test_relative_personal_dir_is_relative_to_the_repo(tmp_path, monkeypatch):
    repo = tmp_path / "uke"
    monkeypatch.setenv("UKE_PERSONAL", "../uke-personal")
    for cwd in (tmp_path, repo / "scripts"):
        cwd.mkdir(parents=True, exist_ok=True)
        monkeypatch.chdir(cwd)
        assert personal.personal_dir(repo) == (tmp_path / "uke-personal").resolve()


@pytest.mark.parametrize("url, handled", [
    ("https://github.com/me/uke-personal.git", True),
    ("git@github.com:me/uke-personal.git", True),
    ("me@nas:repos/uke-personal", True),
    ("../uke-personal", True),
    ("~/backups/uke-personal", True),
    ("s3://bucket/uke", False),
])
def test_git_handles_every_git_address(url, handled):
    assert personal.GitStore.handles(url) is handled


def test_status_without_personal_data(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("UKE_PERSONAL", str(tmp_path / "absent"))
    assert main(["personal", "status"]) == 0
    assert "not set up" in capsys.readouterr().out
    assert main(["personal", "sync"]) == 1


def test_plain_directory_is_a_local_store(tmp_path):
    store = personal.open_store(tmp_path)
    assert store.provider == "local" and store.remote() is None and store.pending() == []


def test_gcs_is_not_supported_yet(tmp_path):
    with pytest.raises(personal.StoreError, match="not supported yet"):
        personal.init("gs://bucket/uke", tmp_path / "p")
    assert not (tmp_path / "p").exists()


def test_init_refuses_an_existing_directory(remote, tmp_path):
    (tmp_path / "p").mkdir()
    with pytest.raises(personal.StoreError, match="already exists"):
        personal.init(str(remote), tmp_path / "p")


def test_git_store_round_trip(remote, tmp_path, monkeypatch, capsys):
    laptop = tmp_path / "laptop"
    monkeypatch.setenv("UKE_PERSONAL", str(laptop))
    assert main(["personal", "init", str(remote)]) == 0
    store = personal.open_store(laptop)
    assert store.provider == "git" and store.remote() == str(remote)
    assert (laptop / "captures" / "inbox").is_dir()

    # an edit made elsewhere (github.com from the phone) ...
    phone = personal.init(str(remote), tmp_path / "phone")
    (phone.path / "captures" / "inbox" / "2026-11-17.txt").write_text("ikkyo omote", encoding="utf-8")
    phone.sync("capture")

    # ... and a local one, both arrive in one sync
    (laptop / "reflections.yaml").write_text(
        f'reflections:\n  - {{subject: shomenuchi, date: 2026-11-17, text: "{SECRET}"}}\n', encoding="utf-8")
    assert store.pending()
    capsys.readouterr()
    assert main(["personal", "status"]) == 0
    assert SECRET not in capsys.readouterr().out
    assert main(["personal", "sync", "-m", "reflection"]) == 0
    assert store.pending() == []
    assert (laptop / "captures" / "inbox" / "2026-11-17.txt").exists()
    assert "reflection" in git(remote, "log", "--format=%s", "-1")


def run_validate(tmp_path, personal_dir):
    env = {"UKE_PERSONAL": str(personal_dir), "PATH": ""}
    return subprocess.run([sys.executable, str(REPO / "scripts" / "validate.py")],
                          capture_output=True, text=True, env=env)


def write_personal(d: Path, reflections: str, motto: str = "motto-1: null"):
    d.mkdir(parents=True, exist_ok=True)
    (d / "motto.yaml").write_text(f"motto_text:\n  {motto}\n", encoding="utf-8")
    (d / "reflections.yaml").write_text(f"reflections:\n{reflections}", encoding="utf-8")


def test_validator_checks_personal_data_without_printing_it(tmp_path):
    d = tmp_path / "p"
    write_personal(d, f'  - {{subject: shomenuchi, date: 2026-11-17, principle: p-ki-heart-mind, text: "{SECRET}"}}\n',
                   motto=f'motto-1: "{SECRET}"')
    r = run_validate(tmp_path, d)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "reflections: 1" in r.stdout and "motto lines still empty: 7" in r.stdout
    assert SECRET not in r.stdout + r.stderr


@pytest.mark.parametrize("line, error", [
    ('  - {subject: no-such-technique, date: 2026-11-17, text: "x"}', "subject is not a technique, kata or term id"),
    (f'  - {{subject: "{SECRET}", date: 2026-11-17, text: "x"}}', "subject is not a technique, kata or term id"),
    ('  - {subject: [shomenuchi], date: 2026-11-17, text: "x"}', "subject is not a technique, kata or term id"),
    ('  - {subject: kata-all, date: 2026-11-17, text: "x"}', "subject is not a technique, kata or term id"),
    ('  - {subject: shomenuchi, date: 2026-11-17, principle: p-nope, text: "x"}', "principle is not a principle id"),
    ('  - {subject: shomenuchi, date: yesterday, text: "x"}', "date must be YYYY-MM-DD"),
])
def test_validator_rejects_bad_personal_references(tmp_path, line, error):
    d = tmp_path / "p"
    write_personal(d, line + "\n")
    r = run_validate(tmp_path, d)
    assert r.returncode == 1
    assert error in r.stdout
    assert SECRET not in r.stdout + r.stderr and "Traceback" not in r.stderr


def test_validator_rejects_unknown_motto_id(tmp_path):
    d = tmp_path / "p"
    write_personal(d, "  []\n", motto=f'motto-99: "{SECRET}"')
    r = run_validate(tmp_path, d)
    assert r.returncode == 1 and "key 1 is not a motto id" in r.stdout
    assert SECRET not in r.stdout


@pytest.fixture
def public(tmp_path):
    """A small copy of this repo's layout under git, for the personal-data guard."""
    root = tmp_path / "public"
    (root / "data").mkdir(parents=True)
    shutil.copytree(REPO / "personal.example", root / "personal.example")
    (root / "data" / "terms.yaml").write_text("terms: []\n", encoding="utf-8")
    git(tmp_path, "init", "-q", "-b", "main", str(root))
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "clean")
    return root


def guard(root, *revs):
    return subprocess.run([sys.executable, str(REPO / "scripts" / "check_public.py"), *revs],
                          cwd=root, capture_output=True, text=True)


def commit(root, path, text, msg="change"):
    f = root / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")
    git(root, "add", "-f", path)
    git(root, "commit", "-q", "-m", msg)
    return git(root, "rev-parse", "HEAD").strip()


def test_guard_passes_a_clean_repo(public):
    r = guard(public)
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("path, text, problem", [
    ("personal/motto.yaml", "motto_text: {}\n", "personal data path"),
    ("captures/2026-11-17.yaml", "date: 2026-11-17\n", "personal data path"),
    ("data/notes.yaml", f'motto_text:\n  motto-1: "{SECRET}"\n', "has a motto_text or reflections key"),
    ("tests/fixtures/notes.yml", f'reflections:\n  - {{text: "{SECRET}"}}\n', "has a motto_text or reflections key"),
    ("personal.example/captures/inbox/2026-11-17.txt", SECRET, "not part of the personal.example/ template"),
    ("personal.example/captures/inbox/.gitkeep", SECRET, ".gitkeep: must stay empty"),
    ("data/export.json", f'{{"motto_text": {{"motto-1": "{SECRET}"}}}}\n', "has a motto_text or reflections key"),
    ("data/notes.yaml", f'- reflections: ["{SECRET}"]\n', "has a motto_text or reflections key"),
    ("data/notes.yaml", f'{{reflections: ["{SECRET}"]}}\n', "has a motto_text or reflections key"),
    ("data/notes.yaml", f"'motto_text': {{motto-1: x}}\n", "has a motto_text or reflections key"),
    ("personal.example/motto.yaml", f"motto_text:\n  motto-1: {SECRET}: and more\n", "motto.yaml: not valid YAML"),
    ("personal.example/reflections.yaml", f"reflections:\n  - {{date: 2026-11-31, text: {SECRET}}}\n", "not valid YAML"),
    ("personal.example/motto.yaml", f'- "{SECRET}"\n', "must be a mapping"),
    ("personal.example/motto.yaml", f'motto_text:\n  motto-1: "{SECRET}"\n', "must stay null"),
    ("personal.example/reflections.yaml", f'reflections:\n  - {{text: "{SECRET}"}}\n', "must stay an empty list"),
])
def test_guard_rejects_personal_data(public, path, text, problem):
    commit(public, path, text)
    r = guard(public)
    assert r.returncode == 1 and problem in r.stdout
    assert SECRET not in r.stdout


def test_guard_catches_data_deleted_in_a_later_commit(public):
    base = git(public, "rev-parse", "HEAD").strip()
    commit(public, "personal/reflections.yaml", "reflections: []\n", "oops")
    git(public, "rm", "-q", "personal/reflections.yaml")
    git(public, "commit", "-q", "-m", "remove")
    assert guard(public, "HEAD").returncode == 0
    revs = git(public, "rev-list", f"{base}..HEAD").split()
    r = guard(public, "HEAD", *revs)
    assert r.returncode == 1 and "personal/reflections.yaml" in r.stdout


def test_guard_checks_staged_changes(public):
    (public / "personal").mkdir()
    (public / "personal" / "motto.yaml").write_text("motto_text: {}\n", encoding="utf-8")
    git(public, "add", "-f", "personal/motto.yaml")
    r = guard(public)
    assert r.returncode == 1 and "staged changes" in r.stdout


def test_sync_conflict_leaves_a_clean_clone(remote, tmp_path):
    laptop = personal.init(str(remote), tmp_path / "laptop")
    phone = personal.init(str(remote), tmp_path / "phone")
    for store, words in ((phone, "from the phone"), (laptop, "from the laptop")):
        (store.path / "reflections.yaml").write_text(f'reflections: []  # {words}\n', encoding="utf-8")
    phone.sync("phone edit")
    with pytest.raises(StoreError, match="conflict with yours, so nothing was pushed .your changes are committed locally"):
        laptop.sync("laptop edit")
    assert laptop.in_progress() is None
    assert "1 commit(s) not pushed" in laptop.pending()
    assert "from the laptop" in (laptop.path / "reflections.yaml").read_text(encoding="utf-8")
    assert "phone edit" in git(remote, "log", "--format=%s", "-1")


def test_sync_refuses_an_unfinished_rebase(remote, tmp_path):
    store = personal.init(str(remote), tmp_path / "p")
    (store.path / ".git" / "rebase-merge").mkdir()
    with pytest.raises(StoreError, match="a rebase is unfinished"):
        store.sync("x")


def test_remote_urls_are_printed_without_credentials(remote, tmp_path):
    assert personal.redact("https://me:ghp_secret@github.com/me/uke-personal.git") == \
        "https://***@github.com/me/uke-personal.git"
    store = personal.init(str(remote), tmp_path / "p")
    store.git("remote", "set-url", "origin", "https://me:ghp_secret@example.invalid/uke-personal.git")
    assert "ghp_secret" not in store.remote()



def test_git_errors_are_printed_without_credentials(monkeypatch):
    """No network: stand in for git failing with the URL in its message."""
    def fake_run(args, **kw):
        return subprocess.CompletedProcess(args, 128, "", "fatal: unable to access "
                                           "'https://me:ghp_secret@github.com/me/uke-personal.git/': 403")
    monkeypatch.setattr(personal.subprocess, "run", fake_run)
    with pytest.raises(StoreError) as e:
        personal.run_git(["clone", "-q", "https://me:ghp_secret@github.com/me/uke-personal.git", "p"])
    assert "ghp_secret" not in str(e.value) and "https://***@github.com" in str(e.value)


def test_missing_git_is_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    with pytest.raises(StoreError, match="git is required"):
        personal.init("https://github.com/me/uke-personal.git", tmp_path / "p")


def test_unknown_url_scheme_is_refused(tmp_path):
    with pytest.raises(StoreError, match="no personal store provider handles"):
        personal.init("s3://bucket/uke", tmp_path / "p")


@pytest.mark.parametrize("motto, reflections, error", [
    (f'motto_text:\n  - "{SECRET}"\n', "reflections: []\n", "motto_text must be a mapping"),
    (f'- "{SECRET}"\n', "reflections: []\n", "motto_text must be a mapping"),
    ("motto_text: {}\n", f'reflections:\n  text: "{SECRET}"\n', "reflections must be a list"),
    ("motto_text: {}\n", f'reflections: [{{subject: "{SECRET}"\n', "reflections.yaml: not valid YAML (line"),
    ("motto_text: {}\n", f'reflections:\n  - {{subject: shomenuchi, date: 2026-11-31, text: "{SECRET}"}}\n',
     "reflections.yaml: has an impossible date"),
])
def test_validator_reports_malformed_personal_files(tmp_path, motto, reflections, error):
    d = tmp_path / "p"
    d.mkdir()
    (d / "motto.yaml").write_text(motto, encoding="utf-8")
    (d / "reflections.yaml").write_text(reflections, encoding="utf-8")
    r = run_validate(tmp_path, d)
    assert r.returncode == 1 and error in r.stdout, r.stdout + r.stderr
    assert SECRET not in r.stdout + r.stderr and "Traceback" not in r.stderr


def test_tests_never_see_real_personal_data():
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "validate.py")], capture_output=True, text=True)
    assert "personal data: not set up" in r.stdout


def test_guard_skips_python_code(public):
    commit(public, "tests/test_fake.py", 'FAKE = "reflections: []"\nmotto_text: int = 0\n')
    assert guard(public).returncode == 0


def test_sync_reports_the_real_error_when_offline(remote, tmp_path):
    store = personal.init(str(remote), tmp_path / "p")
    (store.path / "reflections.yaml").write_text("reflections: []  # edited\n", encoding="utf-8")
    remote.rename(tmp_path / "moved.git")   # the remote is unreachable
    with pytest.raises(StoreError) as e:
        store.sync("offline edit")
    msg = str(e.value)
    assert "conflict" not in msg and "git pull failed" in msg
    assert "Nothing was pushed (your changes are committed locally)" in msg
    assert store.in_progress() is None


def test_status_sees_remote_changes(remote, tmp_path):
    laptop = personal.init(str(remote), tmp_path / "laptop")
    phone = personal.init(str(remote), tmp_path / "phone")
    (phone.path / "captures" / "inbox" / "2026-11-17.txt").write_text("ikkyo", encoding="utf-8")
    phone.sync("capture")
    assert "1 commit(s) on the remote not pulled" in laptop.pending()
    remote.rename(tmp_path / "moved.git")
    assert "could not reach the remote, so its new changes are unknown" in laptop.pending()

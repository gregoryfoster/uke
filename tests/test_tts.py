"""GoogleEngine credentials come only from uke's own gcloud config directory. No network."""
import json

import pytest

from uke.tts import GoogleEngine, TTSError, credentials_path, gcloud_config_dir, login_command


def write_adc(path, client_id):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "type": "authorized_user", "client_id": client_id,
        "client_secret": "secret", "refresh_token": "token",
    }))
    return path


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A machine-wide ADC file and GOOGLE_APPLICATION_CREDENTIALS that uke must never read."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    shared = write_adc(tmp_path / "home" / ".config" / "gcloud" / "application_default_credentials.json", "shared")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(shared))
    monkeypatch.setenv("CLOUDSDK_CONFIG", str(shared.parent))
    monkeypatch.delenv("UKE_GCLOUD_CONFIG", raising=False)
    return tmp_path


def test_default_config_dir_is_uke_only(env):
    assert gcloud_config_dir() == env / "home" / ".config" / "gcloud-uke"


def test_missing_credentials_fail_with_login_command(env):
    with pytest.raises(TTSError) as e:
        GoogleEngine(project="p").credentials()
    msg = str(e.value)
    assert str(credentials_path()) in msg
    assert f"CLOUDSDK_CONFIG={gcloud_config_dir()} gcloud auth application-default login" in msg


def test_loads_only_uke_credentials(env, monkeypatch):
    monkeypatch.setenv("UKE_GCLOUD_CONFIG", str(env / "uke-gcloud"))
    write_adc(credentials_path(), "uke")
    creds = GoogleEngine(project="p").credentials()
    assert creds.client_id == "uke"
    assert creds.quota_project_id == "p"


def test_rejects_other_credential_types(env, monkeypatch):
    monkeypatch.setenv("UKE_GCLOUD_CONFIG", str(env / "uke-gcloud"))
    credentials_path().parent.mkdir(parents=True)
    credentials_path().write_text(json.dumps({"type": "service_account"}))
    with pytest.raises(TTSError, match="service_account"):
        GoogleEngine(project="p").credentials()


def test_refused_login_says_how_to_log_in_again(env, monkeypatch):
    from google.auth.exceptions import RefreshError

    class Revoked:
        def list_voices(self, **kw):
            raise RefreshError("invalid_grant: Token has been expired or revoked.")

    engine = GoogleEngine(project="p")
    engine._client = Revoked()
    with pytest.raises(TTSError) as e:
        engine.list_voices("ja-JP")
    assert "invalid_grant" in str(e.value)
    assert login_command() in str(e.value)

"""Keep every test away from the developer's real personal data."""
import pytest


@pytest.fixture(autouse=True)
def no_personal_data(tmp_path, monkeypatch):
    # validate.py and uke read $UKE_PERSONAL, else personal/ in the checkout, which may hold a real clone.
    monkeypatch.setenv("UKE_PERSONAL", str(tmp_path / "no-personal-data"))

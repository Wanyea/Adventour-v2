import os
from pathlib import Path

import pytest

from remote_service import PreflightError, validate_environment


def valid_env(tmp_path: Path) -> dict[str, str]:
    credentials = tmp_path / "firebase.json"
    credentials.write_text("{}", encoding="utf-8")
    return {
        "ADVENTOUR_REMOTE_MODE": "true",
        "ADVENTOUR_DEV_AUTH": "false",
        "DATABASE_URL": "postgresql://pilot:secret@127.0.0.1:5432/adventour",
        "FIREBASE_PROJECT_ID": "pilot-project",
        "FIREBASE_SERVICE_ACCOUNT_PATH": str(credentials),
        "ADVENTOUR_BIND_HOST": "127.0.0.1",
        "PORT": "8080",
    }


def test_remote_preflight_accepts_local_postgres_and_real_auth(tmp_path):
    result = validate_environment(valid_env(tmp_path))
    assert result["bind_host"] == "127.0.0.1"
    assert result["port"] == "8080"


@pytest.mark.parametrize("field,value", [
    ("ADVENTOUR_REMOTE_MODE", "false"),
    ("ADVENTOUR_DEV_AUTH", "true"),
    ("DATABASE_URL", "postgresql://pilot:secret@db.example.test:5432/adventour"),
    ("DATABASE_URL", "sqlite:///adventour.db"),
    ("ADVENTOUR_BIND_HOST", "0.0.0.0"),
])
def test_remote_preflight_fails_closed(tmp_path, field, value):
    env = valid_env(tmp_path)
    env[field] = value
    with pytest.raises(PreflightError):
        validate_environment(env)


def test_remote_preflight_requires_firebase_credentials(tmp_path):
    env = valid_env(tmp_path)
    env["FIREBASE_SERVICE_ACCOUNT_PATH"] = os.fspath(tmp_path / "missing.json")
    with pytest.raises(PreflightError, match="does not exist"):
        validate_environment(env)

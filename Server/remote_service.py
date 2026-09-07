"""Fail-closed Windows service entry point for the friends pilot.

The Flask module creates its database schema while importing.  Keep this
module as the only remote entry point so unsafe configuration is rejected
before that import can have side effects.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from dotenv import load_dotenv


class PreflightError(RuntimeError):
    """Raised when the pilot service is not safe to start."""


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_loopback(host: str) -> bool:
    normalized = host.strip().lower().strip("[]")
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _check_local_postgres(database_url: str) -> None:
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise PreflightError("DATABASE_URL must use PostgreSQL for remote pilot service")
    if not parsed.hostname or not _is_loopback(parsed.hostname):
        raise PreflightError("DATABASE_URL must point to local-only PostgreSQL")


def validate_environment(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Validate the remote-service contract without importing Flask or SQLAlchemy."""

    values = dict(os.environ if env is None else env)
    if not _truthy(values.get("ADVENTOUR_REMOTE_MODE")):
        raise PreflightError("ADVENTOUR_REMOTE_MODE=true is required")
    if _truthy(values.get("ADVENTOUR_DEV_AUTH")):
        raise PreflightError("ADVENTOUR_DEV_AUTH must be false for remote service")

    database_url = values.get("DATABASE_URL", "").strip()
    if not database_url:
        raise PreflightError("DATABASE_URL is required")
    _check_local_postgres(database_url)

    project_id = values.get("FIREBASE_PROJECT_ID", "").strip()
    if not project_id:
        raise PreflightError("FIREBASE_PROJECT_ID is required")
    # app.py's Firebase initializer intentionally consumes this explicit path;
    # accepting ADC here would make preflight claim real auth while the app
    # silently fell back to public-token verification.
    credentials_path = values.get("FIREBASE_SERVICE_ACCOUNT_PATH")
    if not credentials_path:
        raise PreflightError("FIREBASE_SERVICE_ACCOUNT_PATH is required")
    if not Path(credentials_path).is_file():
        raise PreflightError("Firebase service-account file does not exist")

    bind_host = values.get("ADVENTOUR_BIND_HOST", "127.0.0.1").strip()
    if not _is_loopback(bind_host):
        raise PreflightError("ADVENTOUR_BIND_HOST must be loopback-only")
    try:
        port = int(values.get("PORT", "8080"))
    except ValueError as exc:
        raise PreflightError("PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise PreflightError("PORT must be between 1 and 65535")

    return {"bind_host": bind_host, "port": str(port), "version": values.get("ADVENTOUR_SERVICE_VERSION", "unversioned-development")}


def load_environment() -> None:
    """Load the operator-selected env file before preflight, without printing it."""
    env_file = os.getenv("ENV_FILE")
    if env_file:
        load_dotenv(env_file, override=True)


def build_app():
    """Run preflight first, then import the side-effectful Flask application."""

    settings = validate_environment()
    from app import app  # noqa: PLC0415 - deliberately after preflight

    app.config["REMOTE_SERVICE_MODE"] = True
    app.config["SERVICE_VERSION"] = settings["version"]
    return app, settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Adventour's loopback pilot service")
    parser.add_argument("--check", action="store_true", help="validate configuration without importing the app")
    args = parser.parse_args()
    try:
        load_environment()
        settings = validate_environment()
        if args.check:
            print("remote service preflight passed")
            return 0
        app, settings = build_app()
        from waitress import serve  # noqa: PLC0415 - dependency is needed only after preflight

        serve(app, host=settings["bind_host"], port=int(settings["port"]))
        return 0
    except PreflightError as exc:
        print(f"remote service refused to start: {exc}")
        return 2
    except ImportError as exc:
        print(f"remote service dependency missing: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

"""Focused HTTP and schema contract for the user-authored home locality."""

import os
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text

from adventour_backend.services.profile_service import ensure_user_profile_columns


def _isolated_backend():
    if not os.getenv("ENV_FILE", "").endswith(".env.ingest-check"):
        pytest.skip("Run against the isolated ingestion database")
    import app as backend
    return backend


def _headers():
    email = f"home-city-{uuid.uuid4().hex[:12]}@adventour.local"
    return email, {"Authorization": f"Bearer dev:{email}"}


def _delete_test_user(backend, email):
    with backend.app.app_context():
        backend.User.query.filter_by(email=email).delete()
        backend.db.session.commit()


def test_home_city_profile_contract_and_authenticated_owner():
    backend = _isolated_backend()
    email, headers = _headers()
    other_email, other_headers = _headers()
    display_name = f"Home City {uuid.uuid4().hex[:8]}"
    try:
        client = backend.app.test_client()
        # Authentication creates the user; /user accepts an omitted locality unchanged.
        user = client.post("/user", headers=headers, json={"home_city": "  Montréal  "})
        assert user.status_code == 201
        assert user.json["user"]["home_city"] == "Montréal"
        assert user.json["user"]["profile_complete"] is False

        profile = client.put("/user/profile", headers=headers, json={"display_name": display_name})
        assert profile.status_code == 200
        assert profile.json["user"]["home_city"] == "Montréal"

        profile = client.put("/user/profile", headers=headers, json={"home_city": "東京"})
        assert profile.status_code == 200
        assert profile.json["user"]["home_city"] == "東京"

        with backend.app.app_context():
            backend.db.session.remove()
        user_id = "dev-" + email.split("@", 1)[0]
        reread = client.get(f"/user/{user_id}", headers=headers)
        assert reread.status_code == 200
        assert reread.json["user"]["home_city"] == profile.json["user"]["home_city"]

        history = client.get("/api/profile/history", headers=headers)
        assert history.status_code == 200
        assert history.json["user"]["home_city"] == "東京"

        invalid = client.put("/user/profile", headers=headers, json={"display_name": "Must Not Persist", "home_city": "bad\u0000city"})
        assert invalid.status_code == 400
        current = client.put("/user/profile", headers=headers, json={})
        assert current.json["user"]["display_name"] == display_name
        assert current.json["user"]["home_city"] == "東京"

        assert client.put("/user/profile", headers=other_headers, json={"home_city": "São Paulo"}).status_code == 200
        unchanged = client.put("/user/profile", headers=headers, json={})
        assert unchanged.json["user"]["home_city"] == "東京"

        cleared = client.put("/user/profile", headers=headers, json={"home_city": "   "})
        assert cleared.status_code == 200
        assert cleared.json["user"]["home_city"] is None
        assert client.put("/user/profile", headers=headers, json={"home_city": None}).status_code == 200
        complete = client.put("/user/profile", headers=headers, json={"date_of_birth": "1990-01-01"})
        assert complete.json["user"]["profile_complete"] is True
    finally:
        _delete_test_user(backend, email)
        _delete_test_user(backend, other_email)


@pytest.mark.parametrize("value", [123, [], {"city": "Paris"}, "x" * 161, "Paris\nFrance"])
def test_home_city_rejects_invalid_values_without_mutation(value):
    backend = _isolated_backend()
    email, headers = _headers()
    try:
        client = backend.app.test_client()
        assert client.put("/user/profile", headers=headers, json={"home_city": "Nairobi"}).status_code == 200
        rejected = client.put("/user/profile", headers=headers, json={"home_city": value})
        assert rejected.status_code == 400
        assert client.put("/user/profile", headers=headers, json={}).json["user"]["home_city"] == "Nairobi"
    finally:
        _delete_test_user(backend, email)


@pytest.mark.parametrize("body", ["null", "[]"])
def test_profile_requires_a_json_object(body):
    backend = _isolated_backend()
    email, headers = _headers()
    try:
        client = backend.app.test_client()
        assert client.put("/user/profile", headers=headers, json={"home_city": "Nairobi"}).status_code == 200
        assert client.put("/user/profile", headers=headers, data=body,
                          content_type="application/json").status_code == 400
        assert client.put("/user/profile", headers=headers, json={}).json["user"]["home_city"] == "Nairobi"
    finally:
        _delete_test_user(backend, email)


def test_home_city_schema_migration_is_idempotent():
    backend = _isolated_backend()
    with backend.app.app_context():
        backend.ensure_local_schema()
        backend.ensure_local_schema()
        columns = {column["name"] for column in inspect(backend.db.engine).get_columns("user")}
    assert {"date_of_birth", "home_city"} <= columns


def test_home_city_schema_migrates_a_legacy_dob_only_table():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE "user" (id INTEGER PRIMARY KEY, date_of_birth DATE)'))

    ensure_user_profile_columns(engine, "user")
    ensure_user_profile_columns(engine, "user")
    columns = {column["name"] for column in inspect(engine).get_columns("user")}
    assert {"id", "date_of_birth", "home_city"} <= columns

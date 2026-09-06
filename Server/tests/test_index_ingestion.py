"""Transactional refresh checks, opt-in against a clearly named isolated database."""

import os

import h3
import psycopg2
import pytest
from psycopg2.extensions import parse_dsn

from data_pipeline import index_stages
from data_pipeline.load_postgres import ingest
from data_pipeline.postgres_index import SCHEMA


def source(pid, metro, name, lat=29.89, lon=-81.31):
    return (pid, name, metro, "restaurant", "restaurant", "food_and_drink", .9,
            None, None, "independent", 1, [], [], [], "Example", "FL", lat, lon,
            "32084", h3.latlng_to_cell(lat, lon, 8), h3.latlng_to_cell(lat, lon, 7))


def test_refresh_preserves_other_metro_history_identity_and_rolls_back_failure(monkeypatch):
    dsn = os.environ.get("ADVENTOUR_TEST_PG_DSN")
    if not dsn:
        pytest.skip("Set ADVENTOUR_TEST_PG_DSN to an adventour_ingest_check_* database")
    assert parse_dsn(dsn).get("dbname", "").startswith("adventour_ingest_check_")
    conn = psycopg2.connect(dsn)
    config = {"release": "2026-07-22.0", "metros": {"test_a": {}, "test_b": {}}}
    rows = [source("test-a1", "test_a", "Distinctive Coffee House"),
            source("test-a2", "test_a", "Distinctive Coffee House"),
            source("test-a3", "test_a", "Other Local Bakery"),
            source("test-b1", "test_b", "Distant Diner", lat=28.5)]
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)
            cur.execute("CREATE TEMP TABLE example_history (entity_id text)")
        ingest(conn, rows, config)
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(canonical_id,id) FROM places WHERE id='test-a2'")
            entity = cur.fetchone()[0]
            assert entity == "test-a1"
            cur.execute("INSERT INTO example_history VALUES (%s)", (entity,))
            cur.execute("SELECT row_to_json(p)::text FROM places p WHERE metro='test_b'")
            untouched = cur.fetchall()
        selected = {**config, "metros": {"test_a": {}}}
        refresh = [rows[1], rows[2], source("test-a4", "test_a", "A New Restaurant")]
        with pytest.raises(ValueError, match="active records absent"):
            ingest(conn, refresh, selected)
        ingest(conn, refresh, selected, allow_large_change=True)
        with conn.cursor() as cur:
            cur.execute("SELECT row_to_json(p)::text FROM places p WHERE metro='test_b'")
            assert cur.fetchall() == untouched
            cur.execute("SELECT index_active FROM places WHERE id='test-a1'")
            assert cur.fetchone() == (False,)
            cur.execute("SELECT canonical_id,canonical_lat,canonical_lon,canonical_h3_r8 FROM places WHERE id='test-a2'")
            root, lat, lon, cell = cur.fetchone()
            assert root == entity and cell == h3.latlng_to_cell(lat, lon, 8)
            cur.execute("SELECT entity_id FROM example_history")
            assert cur.fetchone() == (entity,)
            cur.execute("SAVEPOINT before_failure")
        def fail(*args):
            raise RuntimeError("deliberate score-stage failure")
        monkeypatch.setattr(index_stages, "score_places", fail)
        with pytest.raises(RuntimeError, match="deliberate"):
            ingest(conn, refresh + [source("test-failed", "test_a", "Not Committed")], selected)
        with conn.cursor() as cur:
            cur.execute("ROLLBACK TO SAVEPOINT before_failure")
            cur.execute("SELECT count(*) FROM places WHERE id='test-failed'")
            assert cur.fetchone() == (0,)
    finally:
        conn.rollback()
        conn.close()

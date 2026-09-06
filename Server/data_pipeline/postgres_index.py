"""Additive owned-index schema and connection helpers. Never drop user data."""

import os

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import make_dsn, parse_dsn


def dsn():
    return os.environ.get("ADVENTOUR_PG_DSN") or make_dsn(
        host=os.environ.get("PGHOST", "localhost"), port=os.environ.get("PGPORT", "5432"),
        user=os.environ.get("PGUSER", "postgres"), dbname=os.environ.get("PGDATABASE", "adventour"))


def describe(value):
    p = parse_dsn(value)
    return f"{p.get('host', 'localhost')}:{p.get('port', '5432')}/{p.get('dbname', '?')}"


def ensure_database(value):
    name = parse_dsn(value).get("dbname")
    if not name or name in {"postgres", "template0", "template1"}:
        raise ValueError("Select an application database explicitly, not a maintenance database.")
    conn = psycopg2.connect(make_dsn(value, dbname="postgres"))
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,))
            if not cur.fetchone():
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS places (
    id text PRIMARY KEY, name text NOT NULL, metro text NOT NULL,
    category text, basic_category text, taxonomy_bucket text, confidence double precision,
    brand_name text, brand_wikidata text, chain_class text NOT NULL, fl_name_count integer NOT NULL,
    websites text[], socials text[], phones text[], locality text, region text,
    lat double precision NOT NULL, lon double precision NOT NULL,
    h3_r8 text NOT NULL, h3_r7 text NOT NULL
);
ALTER TABLE places ADD COLUMN IF NOT EXISTS postcode text;
ALTER TABLE places ADD COLUMN IF NOT EXISTS tier text;
ALTER TABLE places ADD COLUMN IF NOT EXISTS tier_reason text;
ALTER TABLE places ADD COLUMN IF NOT EXISTS needs_booking boolean DEFAULT false;
ALTER TABLE places ADD COLUMN IF NOT EXISTS authenticity double precision;
ALTER TABLE places ADD COLUMN IF NOT EXISTS authenticity_why text;
ALTER TABLE places ADD COLUMN IF NOT EXISTS score_components jsonb;
ALTER TABLE places ADD COLUMN IF NOT EXISTS score_density integer;
ALTER TABLE places ADD COLUMN IF NOT EXISTS canonical_id text;
ALTER TABLE places ADD COLUMN IF NOT EXISTS cluster_size integer;
ALTER TABLE places ADD COLUMN IF NOT EXISTS loc_spread_m double precision;
ALTER TABLE places ADD COLUMN IF NOT EXISTS canonical_lat double precision;
ALTER TABLE places ADD COLUMN IF NOT EXISTS canonical_lon double precision;
ALTER TABLE places ADD COLUMN IF NOT EXISTS canonical_h3_r8 text;
ALTER TABLE places ADD COLUMN IF NOT EXISTS index_active boolean NOT NULL DEFAULT true;
ALTER TABLE places ADD COLUMN IF NOT EXISTS source_release text;
ALTER TABLE places ADD COLUMN IF NOT EXISTS source_seen_at timestamptz;
CREATE INDEX IF NOT EXISTS places_h3_r8_idx ON places(h3_r8);
CREATE INDEX IF NOT EXISTS places_canonical_h3_idx ON places(canonical_h3_r8);
CREATE INDEX IF NOT EXISTS places_h3_r7_idx ON places(h3_r7);
CREATE INDEX IF NOT EXISTS places_metro_idx ON places(metro);
CREATE INDEX IF NOT EXISTS places_tier_idx ON places(tier);
CREATE INDEX IF NOT EXISTS places_canonical_idx ON places(canonical_id);
CREATE INDEX IF NOT EXISTS places_auth_idx ON places(authenticity DESC);
CREATE TABLE IF NOT EXISTS index_ingestion (
    id bigserial PRIMARY KEY, completed_at timestamptz NOT NULL DEFAULT now(),
    release text NOT NULL, metros text[] NOT NULL, source_count integer NOT NULL,
    config jsonb NOT NULL
);
"""

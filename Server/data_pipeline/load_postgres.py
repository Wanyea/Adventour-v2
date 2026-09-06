"""Load the Orlando + Palm Coast seed into local Postgres.

Geospatial indexing is done with H3 cell IDs computed in Python and stored as
indexed text columns, rather than PostGIS + h3-pg. Reasons:

  - `h3-pg` has no reliable prebuilt Windows binary, and the portable Postgres
    archive we run locally does not ship PostGIS at all.
  - A radius query becomes `WHERE h3_r8 = ANY(<ring>)` plus a Haversine filter,
    which is entirely adequate at this scale (~19k rows).
  - The schema stays portable: it runs unchanged on any managed Postgres later,
    and PostGIS can be layered on when there is a reason to.

Run scripts/setup-local-postgres.ps1 first.
"""

import os
from pathlib import Path

import duckdb
import h3
import psycopg2
from psycopg2.extensions import parse_dsn
from psycopg2.extras import execute_values

def _dsn():
    """Prefer an explicit URI, else assemble from standard libpq variables.

    The libpq path avoids URI percent-encoding entirely -- a password containing
    '@', '#', '/' or '%' silently corrupts a URI DSN but is fine in PGPASSWORD.
    """
    uri = os.environ.get("ADVENTOUR_PG_DSN")
    if uri:
        return uri
    parts = {
        "host": os.environ.get("PGHOST", "localhost"),
        "port": os.environ.get("PGPORT", "5432"),
        "user": os.environ.get("PGUSER", "postgres"),
        "dbname": os.environ.get("PGDATABASE", "postgres"),
    }
    if os.environ.get("PGPASSWORD"):
        parts["password"] = os.environ["PGPASSWORD"]
    return " ".join(f"{k}={v}" for k, v in parts.items())


DSN = _dsn()

HERE = Path(__file__).resolve().parent / "data"
PLACES = f"read_parquet('{(HERE / 'seed_places.parquet').as_posix()}')"
NAMES = f"read_parquet('{(HERE / 'florida_names.parquet').as_posix()}')"

RELEVANT = ("food_and_drink", "arts_and_entertainment", "cultural_and_historic", "sports_and_recreation")
EXCLUDED = ("christian_place_of_worship", "place_of_worship", "cemetery", "school",
            "gym", "fitness_studio", "sport_or_fitness_facility", "swimming_pool")

# r8 hexagons are ~0.46 km2 -- the working resolution for "near me" queries.
# r7 (~5 km2) is kept as a coarse bucket for wider sweeps and aggregate stats.
H3_FINE, H3_COARSE = 8, 7

SCHEMA = """
DROP TABLE IF EXISTS places CASCADE;
CREATE TABLE places (
    id              text PRIMARY KEY,
    name            text NOT NULL,
    metro           text NOT NULL,
    category        text,
    basic_category  text,
    taxonomy_bucket text,
    confidence      double precision,
    brand_name      text,
    brand_wikidata  text,
    chain_class     text NOT NULL,
    fl_name_count   integer NOT NULL,
    websites        text[],
    socials         text[],
    phones          text[],
    locality        text,
    region          text,
    lat             double precision NOT NULL,
    lon             double precision NOT NULL,
    h3_r8           text NOT NULL,
    h3_r7           text NOT NULL
);
CREATE INDEX places_h3_r8_idx        ON places (h3_r8);
CREATE INDEX places_h3_r7_idx        ON places (h3_r7);
CREATE INDEX places_chain_class_idx  ON places (chain_class);
CREATE INDEX places_bucket_idx       ON places (taxonomy_bucket);
CREATE INDEX places_metro_idx        ON places (metro);
"""

QUERY = f"""
SELECT
    p.id, p.name, p.metro, p.category, p.basic_category,
    p.taxonomy_hierarchy[1] AS taxonomy_bucket,
    p.confidence, p.brand_name, p.brand_wikidata,
    CASE
        WHEN p.brand_wikidata IS NOT NULL
          OR greatest(coalesce(fe.fl_count,1), coalesce(fb.fl_count,1)) >= 10 THEN 'chain'
        WHEN greatest(coalesce(fe.fl_count,1), coalesce(fb.fl_count,1)) >= 3 THEN 'regional'
        ELSE 'independent'
    END AS chain_class,
    greatest(coalesce(fe.fl_count,1), coalesce(fb.fl_count,1)) AS fl_name_count,
    p.websites, p.socials, p.phones, p.locality, p.region, p.lat, p.lon
FROM {PLACES} p
LEFT JOIN (SELECT name_norm, count(*) fl_count FROM {NAMES} GROUP BY 1) fe
       ON lower(trim(p.name)) = fe.name_norm
LEFT JOIN (SELECT name_norm, count(*) fl_count FROM {NAMES} GROUP BY 1) fb
       ON lower(trim(regexp_replace(p.name,
          '\\s+(at|of|in|-|–|—|@|\\|)\\s+.*$|\\s+\\(.*\\)$', '', 'i'))) = fb.name_norm
WHERE p.taxonomy_hierarchy[1] IN {RELEVANT}
  AND coalesce(p.basic_category,'') NOT IN {EXCLUDED}
  AND coalesce(p.operating_status,'open') <> 'closed'
  AND p.lat IS NOT NULL AND p.lon IS NOT NULL
"""

COLUMNS = (
    "id, name, metro, category, basic_category, taxonomy_bucket, confidence, "
    "brand_name, brand_wikidata, chain_class, fl_name_count, websites, socials, "
    "phones, locality, region, lat, lon, h3_r8, h3_r7"
)


def describe(dsn):
    """Human-readable target, with the password never included."""
    p = parse_dsn(dsn)
    return f"{p.get('host','?')}:{p.get('port','?')}/{p.get('dbname','?')} as {p.get('user','?')}"


def with_dbname(dsn, name):
    p = parse_dsn(dsn)
    p["dbname"] = name
    return " ".join(f"{k}={v}" for k, v in p.items())


def ensure_database(dsn, name="adventour"):
    """Create the target database if it does not exist, then return a DSN for it.

    Lets the caller point at the `postgres` maintenance database and have
    everything else handled here. parse_dsn accepts both URI and key-value forms,
    so this works whichever way credentials were supplied.
    """
    admin = with_dbname(dsn, "postgres")
    dsn = with_dbname(dsn, name)

    conn = psycopg2.connect(admin)
    conn.autocommit = True  # CREATE DATABASE cannot run inside a transaction
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
        if cur.fetchone() is None:
            cur.execute(f'CREATE DATABASE "{name}"')
            print(f"  created database '{name}'")
        else:
            print(f"  database '{name}' already exists")
    conn.close()
    return dsn


def main():
    print("reading seed ...")
    rows = duckdb.connect().execute(QUERY).fetchall()
    print(f"  {len(rows):,} places")

    print("computing H3 cells ...")
    enriched = []
    for r in rows:
        lat, lon = r[16], r[17]
        enriched.append(
            tuple(r)
            + (h3.latlng_to_cell(lat, lon, H3_FINE), h3.latlng_to_cell(lat, lon, H3_COARSE))
        )

    print(f"connecting to {describe(DSN)} ...")
    dsn = ensure_database(DSN)
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(SCHEMA)
        execute_values(
            cur, f"INSERT INTO places ({COLUMNS}) VALUES %s", enriched, page_size=1000
        )
        conn.commit()

        print("\n=== loaded ===")
        cur.execute(
            """
            SELECT metro, chain_class, count(*)
            FROM places GROUP BY 1,2
            ORDER BY 1, CASE chain_class
                WHEN 'chain' THEN 1 WHEN 'regional' THEN 2 ELSE 3 END
            """
        )
        for metro, cls, n in cur.fetchall():
            print(f"  {metro:<12}{cls:<14}{n:>7,}")
        cur.execute("SELECT count(*), count(DISTINCT h3_r8) FROM places")
        total, cells = cur.fetchone()
        print(f"  {'TOTAL':<12}{'':<14}{total:>7,}   across {cells:,} H3 r8 cells")

        # Prove the index works the way recommendations will use it: everything
        # within ~2km of downtown Palm Coast, nearest first.
        print("\n=== smoke test: independents within ~2km of Palm Coast center ===")
        lat, lon = 29.5844, -81.2079
        ring = list(h3.grid_disk(h3.latlng_to_cell(lat, lon, H3_FINE), 3))
        cur.execute(
            """
            SELECT name, basic_category,
                   round((6371000 * acos(least(1, greatest(-1,
                       cos(radians(%s)) * cos(radians(lat)) * cos(radians(lon) - radians(%s))
                     + sin(radians(%s)) * sin(radians(lat))))))::numeric) AS meters
            FROM places
            WHERE h3_r8 = ANY(%s) AND chain_class = 'independent'
            ORDER BY meters LIMIT 8
            """,
            (lat, lon, lat, ring),
        )
        for name, cat, meters in cur.fetchall():
            print(f"  {str(meters):>6}m  {name[:36]:<36} {cat}")


if __name__ == "__main__":
    main()

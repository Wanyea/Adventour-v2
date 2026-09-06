"""Add `postcode` to the places index.

Additive on purpose: pulled straight from Overture and UPDATEd by id, rather than
re-running the pipeline. A full rebuild would remint canonical_ids, and
place_event rows already reference those entity ids.
"""

import os

import duckdb
import psycopg2
from psycopg2.extras import execute_values

RELEASE = "2026-07-22.0"
PLACES = f"s3://overturemaps-us-west-2/release/{RELEASE}/theme=places/type=place/*"
DSN = os.environ.get("ADVENTOUR_PG_DSN", "host=localhost port=5432 user=postgres dbname=adventour")
BBOXES = {  # must match pull_overture.py
    "orlando": dict(xmin=-81.70, xmax=-81.10, ymin=28.30, ymax=28.75),
    "palm_coast": dict(xmin=-81.35, xmax=-81.05, ymin=29.42, ymax=29.70),
}

con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
rows = []
for metro, b in BBOXES.items():
    print(f"fetching postcodes for {metro} ...", flush=True)
    rows += con.execute(
        f"""
        SELECT id, addresses[1].postcode AS postcode
        FROM read_parquet('{PLACES}')
        WHERE bbox.xmin BETWEEN {b['xmin']} AND {b['xmax']}
          AND bbox.ymin BETWEEN {b['ymin']} AND {b['ymax']}
          AND addresses[1].postcode IS NOT NULL
        """
    ).fetchall()
print(f"  {len(rows):,} records with a postcode")

with psycopg2.connect(DSN) as conn, conn.cursor() as cur:
    cur.execute("ALTER TABLE places ADD COLUMN IF NOT EXISTS postcode text")
    execute_values(
        cur,
        "UPDATE places p SET postcode = v.pc FROM (VALUES %s) AS v(id, pc) WHERE p.id = v.id",
        [(r[0], (r[1] or "").strip()[:5]) for r in rows], page_size=2000,
    )
    cur.execute("CREATE INDEX IF NOT EXISTS places_postcode_idx ON places (postcode)")
    conn.commit()
    cur.execute("""SELECT postcode, count(*) FROM places
                   WHERE metro='orlando' AND tier='KEEP'
                     AND postcode IN ('32819','32839','32803','32816')
                   GROUP BY 1 ORDER BY 2 DESC""")
    print("\ntarget ZIPs, KEEP tier:")
    total = 0
    for pc, n in cur.fetchall():
        total += n
        print(f"  {pc}  {n:>5,}")
    print(f"  total {total:,}")

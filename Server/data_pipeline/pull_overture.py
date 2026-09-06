"""Pull Overture Places for the Adventour seed metros.

Two pulls:
  1. Full records for Orlando + Palm Coast  -> the candidate set.
  2. Name + brand only for all of Florida   -> chain-frequency reference.

Florida-wide is a proxy for national chain presence. A national chain has many
Florida locations; a beloved one-off does not. Cheap enough to run, and it keeps
the bbox predicate pushdown that makes these queries fast.

Output: data/ (gitignored). Nothing here touches the app or the server schema.
"""

import time
from pathlib import Path

import duckdb

RELEASE = "2026-07-22.0"
PLACES = f"s3://overturemaps-us-west-2/release/{RELEASE}/theme=places/type=place/*"

METROS = {
    "orlando": dict(xmin=-81.70, xmax=-81.10, ymin=28.30, ymax=28.75),
    "palm_coast": dict(xmin=-81.35, xmax=-81.05, ymin=29.42, ymax=29.70),
}
FLORIDA = dict(xmin=-87.70, xmax=-79.90, ymin=24.40, ymax=31.10)

OUT = Path(__file__).resolve().parent / "data"


def connect():
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;")
    con.execute("SET s3_region='us-west-2';")
    return con


def bbox_clause(b):
    return (
        f"bbox.xmin BETWEEN {b['xmin']} AND {b['xmax']} "
        f"AND bbox.ymin BETWEEN {b['ymin']} AND {b['ymax']}"
    )


def pull_metros(con):
    dest = OUT / "seed_places.parquet"
    clauses = " OR ".join(f"({bbox_clause(b)})" for b in METROS.values())
    labels = "\n".join(
        f"WHEN {bbox_clause(b)} THEN '{name}'" for name, b in METROS.items()
    )
    con.execute(
        f"""
        COPY (
            SELECT
                id,
                names.primary                  AS name,
                categories.primary             AS category,
                categories.alternate           AS category_alt,
                basic_category,
                taxonomy.hierarchy             AS taxonomy_hierarchy,
                confidence,
                operating_status,
                brand.names.primary            AS brand_name,
                brand.wikidata                 AS brand_wikidata,
                websites,
                socials,
                phones,
                addresses[1].locality          AS locality,
                addresses[1].region            AS region,
                bbox.xmin                      AS lon,
                bbox.ymin                      AS lat,
                CASE {labels} ELSE 'other' END AS metro
            FROM read_parquet('{PLACES}')
            WHERE ({clauses})
              AND names.primary IS NOT NULL
        ) TO '{dest.as_posix()}' (FORMAT PARQUET)
        """
    )
    return dest


def pull_florida_names(con):
    """Minimal columns only -- this is a name-frequency reference, not a candidate set."""
    dest = OUT / "florida_names.parquet"
    con.execute(
        f"""
        COPY (
            SELECT
                lower(trim(names.primary)) AS name_norm,
                brand.names.primary        AS brand_name
            FROM read_parquet('{PLACES}')
            WHERE {bbox_clause(FLORIDA)}
              AND names.primary IS NOT NULL
        ) TO '{dest.as_posix()}' (FORMAT PARQUET)
        """
    )
    return dest


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    con = connect()

    for label, fn in (("metros", pull_metros), ("florida names", pull_florida_names)):
        print(f"pulling {label} ...", flush=True)
        start = time.time()
        dest = fn(con)
        rows = con.execute(
            f"SELECT count(*) FROM read_parquet('{dest.as_posix()}')"
        ).fetchone()[0]
        size_mb = dest.stat().st_size / 1e6
        print(f"  {rows:,} rows -> {dest.name} ({size_mb:.1f} MB, {time.time()-start:.0f}s)")


if __name__ == "__main__":
    main()

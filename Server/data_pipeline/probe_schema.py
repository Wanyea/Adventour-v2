"""Probe the Overture Places schema so the pull script targets real columns."""

import duckdb

RELEASE = "2026-07-22.0"
PLACES = f"s3://overturemaps-us-west-2/release/{RELEASE}/theme=places/type=place/*"

con = duckdb.connect()
con.execute("INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;")
con.execute("SET s3_region='us-west-2';")

print(f"release: {RELEASE}\n")
for row in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{PLACES}')").fetchall():
    print(f"  {row[0]:<20} {row[1]}")

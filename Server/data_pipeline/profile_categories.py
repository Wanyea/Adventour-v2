"""What is actually in the seed pull? Pick the category filter from data, not guesswork."""

from pathlib import Path

import duckdb

DATA = Path(__file__).resolve().parent / "data" / "seed_places.parquet"
con = duckdb.connect()
places = f"read_parquet('{DATA.as_posix()}')"

print("=== rows by metro ===")
for metro, n in con.execute(
    f"SELECT metro, count(*) FROM {places} GROUP BY 1 ORDER BY 2 DESC"
).fetchall():
    print(f"  {metro:<12} {n:>8,}")

print("\n=== top-level taxonomy bucket ===")
rows = con.execute(
    f"""
    SELECT coalesce(taxonomy_hierarchy[1], '(none)') AS bucket,
           count(*) AS n,
           round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct
    FROM {places} GROUP BY 1 ORDER BY 2 DESC LIMIT 25
    """
).fetchall()
for bucket, n, pct in rows:
    print(f"  {bucket:<40} {n:>8,}  {pct:>5}%")

print("\n=== top basic_category ===")
for cat, n in con.execute(
    f"""
    SELECT coalesce(basic_category,'(none)'), count(*)
    FROM {places} GROUP BY 1 ORDER BY 2 DESC LIMIT 30
    """
).fetchall():
    print(f"  {cat:<40} {n:>8,}")

print("\n=== confidence distribution ===")
for lo, n in con.execute(
    f"""
    SELECT floor(confidence * 10) / 10 AS band, count(*)
    FROM {places} GROUP BY 1 ORDER BY 1
    """
).fetchall():
    print(f"  >={lo:<5} {n:>8,}")

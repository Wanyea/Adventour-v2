"""Acquire a pinned Overture regional snapshot, including postcodes and provenance.

From Server/: python -m data_pipeline.pull_overture --config data_pipeline/metros.json
No database writes. Only public Overture data is acquired here.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

import duckdb

from data_pipeline.metro_config import DEFAULT, bbox_clause, read_config, sql_literal


def checksum(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def acquire(config, output):
    output.mkdir(parents=True, exist_ok=True)
    source = sql_literal(f"s3://overturemaps-us-west-2/release/{config['release']}/theme=places/type=place/*")
    clauses = " OR ".join(f"({bbox_clause(b)})" for b in config["metros"].values())
    labels = " ".join(f"WHEN {bbox_clause(box)} THEN {sql_literal(name)}"
                      for name, box in config["metros"].items())
    queries = {
        "seed_places.parquet": f"""
            SELECT id, names.primary AS name, categories.primary AS category,
                   basic_category, taxonomy.hierarchy AS taxonomy_hierarchy,
                   confidence, operating_status, brand.names.primary AS brand_name,
                   brand.wikidata AS brand_wikidata, websites, socials, phones,
                   addresses[1].locality AS locality, addresses[1].region AS region,
                   addresses[1].postcode AS postcode, bbox.xmin AS lon, bbox.ymin AS lat,
                   CASE {labels} END AS metro
            FROM read_parquet({source}) WHERE ({clauses}) AND names.primary IS NOT NULL
        """,
        "reference_names.parquet": f"""
            SELECT lower(trim(names.primary)) AS name_norm
            FROM read_parquet({source})
            WHERE {bbox_clause(config['reference_bbox'])} AND names.primary IS NOT NULL
        """,
    }
    manifest = {"config": config, "files": {}}
    with duckdb.connect() as con:
        con.execute("INSTALL httpfs")
        con.execute("LOAD httpfs")
        con.execute("SET s3_region='us-west-2'")
        for name, query in queries.items():
            start = time.monotonic()
            print(f"Pulling {name} ...", flush=True)
            pending, target = output / f"{name}.pending", output / name
            con.execute(f"COPY ({query}) TO {sql_literal(pending.as_posix())} (FORMAT PARQUET)")
            count = con.execute(f"SELECT count(*) FROM read_parquet({sql_literal(pending.as_posix())})").fetchone()[0]
            if not count:
                raise ValueError(f"Source returned no rows for {name}; snapshot not accepted")
            pending.replace(target)
            manifest["files"][name] = {"sha256": checksum(target), "rows": count}
            print(f"  {count:,} rows, {target.stat().st_size / 1e6:.1f} MB, {time.monotonic()-start:.0f}s", flush=True)
    target = output / "snapshot.json"
    pending = output / "snapshot.pending.json"
    pending.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    pending.replace(target)
    print(f"Verified snapshot manifest: {target}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "data" / "snapshot")
    args = parser.parse_args()
    try:
        acquire(read_config(args.config), args.output)
    except (ValueError, OSError, KeyError, duckdb.Error) as exc:
        parser.exit(1, f"Acquisition failed; do not ingest an incomplete snapshot: {exc}\n")


if __name__ == "__main__":
    main()

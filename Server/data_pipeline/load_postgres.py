"""Load -> filter -> score -> dedup one verified snapshot, in one transaction.

Default is a rollback preview. --apply commits only the configured metros;
source records and user history are never deleted. --create-db creates exactly
ADVENTOUR_PG_DSN's database, never silently redirects to adventour.
"""

import argparse
import json
from pathlib import Path

import duckdb
import h3
import psycopg2
from psycopg2.extras import Json, execute_values

from data_pipeline import index_stages
from data_pipeline.metro_config import DEFAULT, read_config, sql_literal
from data_pipeline.postgres_index import SCHEMA, describe, dsn, ensure_database
from data_pipeline.pull_overture import checksum

RELEVANT = ("food_and_drink", "arts_and_entertainment", "cultural_and_historic", "sports_and_recreation")
EXCLUDED = ("christian_place_of_worship", "place_of_worship", "cemetery", "school",
            "gym", "fitness_studio", "sport_or_fitness_facility", "swimming_pool")
COLUMNS = ["id", "name", "metro", "category", "basic_category", "taxonomy_bucket", "confidence",
           "brand_name", "brand_wikidata", "chain_class", "fl_name_count", "websites", "socials",
           "phones", "locality", "region", "lat", "lon", "postcode", "h3_r8", "h3_r7"]


def read_snapshot(folder, config):
    manifest = json.loads((folder / "snapshot.json").read_text(encoding="utf-8"))
    if manifest["config"] != config:
        raise ValueError("Snapshot/config mismatch. Acquire the selected config first.")
    for name in ("seed_places.parquet", "reference_names.parquet"):
        if checksum(folder / name) != manifest["files"][name]["sha256"]:
            raise ValueError(f"Snapshot checksum mismatch: {name}; reacquire the full snapshot.")
    places = sql_literal((folder / "seed_places.parquet").as_posix())
    names = sql_literal((folder / "reference_names.parquet").as_posix())
    query = rf"""
        WITH counts AS (SELECT name_norm,count(*) AS n FROM read_parquet({names}) GROUP BY 1)
        SELECT p.id,p.name,p.metro,p.category,p.basic_category,p.taxonomy_hierarchy[1],
               p.confidence,p.brand_name,p.brand_wikidata,
               CASE WHEN p.brand_wikidata IS NOT NULL OR greatest(coalesce(fe.n,1),coalesce(fb.n,1))>=10
                   THEN 'chain' WHEN greatest(coalesce(fe.n,1),coalesce(fb.n,1))>=3 THEN 'regional'
                   ELSE 'independent' END,
               greatest(coalesce(fe.n,1),coalesce(fb.n,1)),p.websites,p.socials,p.phones,
               p.locality,p.region,p.lat,p.lon,p.postcode
        FROM read_parquet({places}) p
        LEFT JOIN counts fe ON lower(trim(p.name))=fe.name_norm
        LEFT JOIN counts fb ON lower(trim(regexp_replace(p.name,
            '\s+(at|of|in|-|–|—|@|\|)\s+.*$|\s+\(.*\)$','','i')))=fb.name_norm
        WHERE p.taxonomy_hierarchy[1] IN {RELEVANT}
          AND coalesce(p.basic_category,'') NOT IN {EXCLUDED}
          AND coalesce(p.operating_status,'open')<>'closed'
          AND p.lat IS NOT NULL AND p.lon IS NOT NULL
    """
    with duckdb.connect() as con:
        rows = con.execute(query).fetchall()
    if {r[2] for r in rows} != set(config["metros"]) or len({r[0] for r in rows}) != len(rows):
        raise ValueError("Empty/unexpected metro or duplicate source IDs in snapshot.")
    enriched = []
    for row in rows:
        box = config["metros"][row[2]]
        lat, lon = row[16], row[17]
        if not (box["ymin"] <= lat <= box["ymax"] and box["xmin"] <= lon <= box["xmax"]):
            raise ValueError(f"Source coordinate outside configured metro: {row[0]}")
        enriched.append((*row, h3.latlng_to_cell(lat, lon, 8), h3.latlng_to_cell(lat, lon, 7)))
    return enriched


def ingest(conn, rows, config, allow_large_change=False):
    metros = list(config["metros"])
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(72819385)")
        cur.execute(SCHEMA)
        cur.execute("SELECT id,metro,COALESCE(canonical_id,id),index_active FROM places")
        existing = cur.fetchall()
        incoming = {row[0]: row[2] for row in rows}
        if any(pid in incoming and incoming[pid] != metro for pid, metro, _, _ in existing):
            raise ValueError("Snapshot overlaps an existing metro; resolve its boundary before importing.")
        prior = {pid: entity for pid, metro, entity, _ in existing if metro in metros}
        for metro in metros:
            old = {pid for pid, m, _, active in existing if m == metro and active}
            lost = old - incoming.keys()
            if old and len(lost) / len(old) > .30 and not allow_large_change:
                raise ValueError(f"{metro}: {len(lost)}/{len(old)} active records absent. Review the snapshot; "
                                 "use --allow-large-change only after accepting this retirement.")
        # Records absent from this source snapshot remain addressable for history.
        cur.execute("""UPDATE places SET index_active=false,tier='DROP',tier_reason='absent_from_snapshot'
            WHERE metro=ANY(%s) AND NOT (id=ANY(%s))""", (metros, list(incoming)))
        assignments = ",".join(f"{col}=EXCLUDED.{col}" for col in COLUMNS if col != "id")
        execute_values(cur, f"""INSERT INTO places ({','.join(COLUMNS)}) VALUES %s
            ON CONFLICT(id) DO UPDATE SET {assignments}, index_active=true""", rows, page_size=1000)
        cur.execute("""UPDATE places SET source_release=%s,source_seen_at=now(),authenticity=NULL,
            authenticity_why=NULL,score_components=NULL,score_density=NULL
            WHERE metro=ANY(%s) AND index_active""", (config["release"], metros))
    filtered = index_stages.filter_places(conn, metros)
    scored = index_stages.score_places(conn, metros)
    entities = index_stages.deduplicate(conn, metros, prior)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO index_ingestion(release,metros,source_count,config) VALUES(%s,%s,%s,%s)",
                    (config["release"], metros, len(rows), Json(config)))
    return {"source_records": len(rows), "filtered": filtered, "scored": scored, "keep_entities": entities}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT)
    parser.add_argument("--snapshot", type=Path, default=Path(__file__).parent / "data" / "snapshot")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--create-db", action="store_true")
    parser.add_argument("--allow-large-change", action="store_true")
    args = parser.parse_args()
    try:
        config = read_config(args.config)
        rows = read_snapshot(args.snapshot, config)
        target = dsn()
        print(f"Target: {describe(target)}; metros: {', '.join(config['metros'])}", flush=True)
        if args.create_db:
            if not args.apply:
                raise ValueError("--create-db requires --apply; preview never creates a database.")
            ensure_database(target)
        conn = psycopg2.connect(target)
        try:
            result = ingest(conn, rows, config, args.allow_large_change)
            if args.apply:
                conn.commit()
            else:
                conn.rollback()
            print(json.dumps(result, indent=2))
            print("Committed." if args.apply else "Preview rolled back. Repeat with --apply to commit.")
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except (ValueError, OSError, KeyError, duckdb.Error, psycopg2.Error) as exc:
        parser.exit(1, f"Ingestion refused; no partial index update committed: {exc}\n")


if __name__ == "__main__":
    main()

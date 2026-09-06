"""Cluster the index, report the effect, and check nothing good was merged away."""

import json
import os
from collections import Counter
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

from dedup import build_clusters, choose_survivor, haversine_m

DSN = os.environ.get("ADVENTOUR_PG_DSN", "host=localhost port=5432 user=postgres dbname=adventour")
LAB = {r["id"]: r for r in json.loads(
    (Path(__file__).resolve().parent / "qa" / "adventour_palm_coast_labels.json")
    .read_text(encoding="utf-8"))["labels"]}
APPLY = os.environ.get("DEDUP_APPLY") == "1"

with psycopg2.connect(DSN) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
    cur.execute("""SELECT id, name, metro, lat, lon, chain_class, fl_name_count,
                          basic_category, websites, socials, phones, authenticity, tier
                   FROM places WHERE tier='KEEP'""")
    rows = [dict(r) for r in cur.fetchall()]

clusters, comparisons, split_off, idf, default_idf = build_clusters(rows)
multi = {k: v for k, v in clusters.items() if len(v) > 1}

print(f"=== clustering {len(rows):,} KEEP places ({comparisons:,} pair comparisons) ===")
print(f"  clusters with >1 record : {len(multi):,}")
print(f"  records inside them     : {sum(len(v) for v in multi.values()):,}")
print(f"  records removed by merge: {sum(len(v) - 1 for v in multi.values()):,}")
print(f"  index after dedup       : {len(clusters):,}")
print(f"  split back out (chains) : {split_off:,}")

print("\n=== cluster size distribution ===")
for size, n in sorted(Counter(len(v) for v in multi.values()).items()):
    print(f"  {size} records{'':<4}{n:>6} clusters")

print("\n=== Washington Oaks, the case that started this ===")
for key, members in multi.items():
    if any("washington oaks" in (m["name"] or "").lower() for m in members):
        surv, loc, spread = choose_survivor(members)
        print(f"  {len(members)} records -> '{surv['name']}'")
        print(f"  location from medoid: {loc['lat']:.4f}, {loc['lon']:.4f}  (spread {spread/1000:.1f} km)")
        for m in members:
            mark = "*" if m is surv else " "
            print(f"    {mark} {m['name'][:44]:<44} {m['lat']:.4f}  {str(m['basic_category'])[:18]}")

print("\n=== safety check: did any labelled gem get merged into something else? ===")
lost = []
for members in multi.values():
    if len(members) < 2:
        continue
    surv, _, _ = choose_survivor(members)
    for m in members:
        if m is surv:
            continue
        lab = LAB.get(m["id"])
        if lab and lab["label"] in ("gem", "solid"):
            slab = LAB.get(surv["id"])
            lost.append((m["name"], lab["label"], surv["name"], slab["label"] if slab else "unlabelled"))
print(f"  gems/solids absorbed into another record: {len(lost)}")
for a, l, b, sl in lost:
    print(f"    {a[:36]:<36} ({l}) -> {b[:32]} ({sl})")

print("\n=== largest merges (sanity-check these) ===")
for members in sorted(multi.values(), key=len, reverse=True)[:6]:
    surv, loc, spread = choose_survivor(members)
    names = " | ".join(sorted({m["name"][:26] for m in members}))
    print(f"  {len(members):>2}x  {names[:96]}")
    print(f"       -> {surv['name'][:44]:<44} spread {spread/1000:.1f} km  ({members[0]['chain_class']})")

if APPLY:
    with psycopg2.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("ALTER TABLE places ADD COLUMN IF NOT EXISTS canonical_id text")
        cur.execute("ALTER TABLE places ADD COLUMN IF NOT EXISTS cluster_size int")
        cur.execute("ALTER TABLE places ADD COLUMN IF NOT EXISTS loc_spread_m double precision")
        cur.execute("ALTER TABLE places ADD COLUMN IF NOT EXISTS canonical_lat double precision")
        cur.execute("ALTER TABLE places ADD COLUMN IF NOT EXISTS canonical_lon double precision")
        updates = []
        for members in clusters.values():
            surv, loc, spread = choose_survivor(members)
            for m in members:
                updates.append((m["id"], surv["id"], len(members), round(spread, 1),
                                loc["lat"], loc["lon"]))
        execute_values(cur,
            """UPDATE places p SET canonical_id=v.c, cluster_size=v.n, loc_spread_m=v.s,
                      canonical_lat=v.la, canonical_lon=v.lo
               FROM (VALUES %s) AS v(id, c, n, s, la, lo) WHERE p.id=v.id""",
            updates, page_size=2000)
        cur.execute("CREATE INDEX IF NOT EXISTS places_canonical_idx ON places (canonical_id)")
        conn.commit()
    print(f"\napplied: canonical_id written for {len(updates):,} rows")
else:
    print("\n(dry run — set DEDUP_APPLY=1 to write canonical_id)")

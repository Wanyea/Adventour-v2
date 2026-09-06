"""How much of our seed could get opening hours from OpenStreetMap?

Two questions, and the second is the one that matters:
  1. Of OSM POIs in these metros, what fraction carry an `opening_hours` tag?
  2. How many of OUR Overture places can actually be matched to one of those?

A high OSM coverage rate is worthless if we cannot join it to our own records.

Licensing note: OSM is ODbL. Per the brief, OSM-derived hours must live in a
separate attributed table, not commingled into `places`.
"""

import json
import time
from pathlib import Path

import duckdb
import requests

OVERPASS = "https://overpass-api.de/api/interpreter"
HERE = Path(__file__).resolve().parent / "data"
PLACES = f"read_parquet('{(HERE / 'seed_places.parquet').as_posix()}')"

# Overpass bbox order is (south, west, north, east).
BBOXES = {
    "orlando": (28.30, -81.70, 28.75, -81.10),
    "palm_coast": (29.42, -81.35, 29.70, -81.05),
}

QUERY = """
[out:json][timeout:300];
(
  nwr["amenity"~"^(restaurant|cafe|bar|pub|fast_food|ice_cream|biergarten|nightclub|food_court|winery)$"]({bbox});
  nwr["tourism"~"^(museum|attraction|gallery|zoo|theme_park|aquarium|artwork|viewpoint)$"]({bbox});
  nwr["leisure"~"^(park|garden|nature_reserve|water_park|marina|bowling_alley)$"]({bbox});
  nwr["shop"~"^(bakery|coffee|deli|greengrocer|confectionery|chocolate|cheese)$"]({bbox});
  nwr["historic"]({bbox});
);
out tags center;
"""


def fetch_osm(metro, bbox):
    cache = HERE / f"osm_{metro}.json"
    if cache.exists():
        print(f"  {metro}: using cached {cache.name}")
        return json.loads(cache.read_text(encoding="utf-8"))
    q = QUERY.format(bbox=",".join(str(v) for v in bbox))
    print(f"  {metro}: querying Overpass ...", flush=True)
    start = time.time()
    resp = requests.post(OVERPASS, data={"data": q}, timeout=400,
                         headers={"User-Agent": "AdventourBot/0.1 (hours coverage study)"})
    resp.raise_for_status()
    data = resp.json()
    cache.write_text(json.dumps(data), encoding="utf-8")
    print(f"  {metro}: {len(data.get('elements', [])):,} elements in {time.time()-start:.0f}s")
    return data


def main():
    HERE.mkdir(parents=True, exist_ok=True)
    rows = []
    print("fetching OSM data")
    for metro, bbox in BBOXES.items():
        data = fetch_osm(metro, bbox)
        for el in data.get("elements", []):
            tags = el.get("tags", {})
            name = tags.get("name")
            if not name:
                continue
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lon = el.get("lon") or (el.get("center") or {}).get("lon")
            if lat is None or lon is None:
                continue
            rows.append({
                "metro": metro,
                "name": name,
                "lat": lat,
                "lon": lon,
                "opening_hours": tags.get("opening_hours"),
                "website": tags.get("website") or tags.get("contact:website"),
            })
        # Be a good citizen with the shared public Overpass instance.
        time.sleep(2)

    con = duckdb.connect()
    con.execute("CREATE TABLE osm (metro VARCHAR, name VARCHAR, lat DOUBLE, lon DOUBLE, "
                "opening_hours VARCHAR, website VARCHAR)")
    con.executemany(
        "INSERT INTO osm VALUES (?,?,?,?,?,?)",
        [(r["metro"], r["name"], r["lat"], r["lon"], r["opening_hours"], r["website"]) for r in rows],
    )

    print(f"\n=== OSM named POIs in scope: {len(rows):,} ===")
    print(f"{'metro':<14}{'POIs':>8}{'with hours':>13}{'rate':>8}")
    for metro, n, wh in con.execute(
        "SELECT metro, count(*), sum((opening_hours IS NOT NULL)::int) FROM osm GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall():
        print(f"{metro:<14}{n:>8,}{wh:>13,}{100.0*wh/n:>7.1f}%")

    total, with_hours = con.execute(
        "SELECT count(*), sum((opening_hours IS NOT NULL)::int) FROM osm"
    ).fetchone()
    print(f"{'TOTAL':<14}{total:>8,}{with_hours:>13,}{100.0*with_hours/total:>7.1f}%")

    # The question that actually matters: can we join this to our seed?
    # Match on normalized name within ~150m (0.0015 deg is roughly 165m at this latitude).
    print("\n=== matching OSM hours onto our Overture seed ===")
    con.execute(
        f"""
        CREATE VIEW seed AS
        SELECT id, name, lower(trim(name)) AS name_norm, lat, lon, basic_category
        FROM {PLACES}
        WHERE taxonomy_hierarchy[1] IN
            ('food_and_drink','arts_and_entertainment','cultural_and_historic','sports_and_recreation')
          AND coalesce(basic_category,'') NOT IN
            ('christian_place_of_worship','place_of_worship','cemetery','school',
             'gym','fitness_studio','sport_or_fitness_facility','swimming_pool')
          AND coalesce(operating_status,'open') <> 'closed'
        """
    )
    seed_n = con.execute("SELECT count(*) FROM seed").fetchone()[0]
    matched, matched_hours = con.execute(
        """
        SELECT count(DISTINCT s.id),
               count(DISTINCT CASE WHEN o.opening_hours IS NOT NULL THEN s.id END)
        FROM seed s JOIN osm o
          ON lower(trim(o.name)) = s.name_norm
         AND abs(o.lat - s.lat) < 0.0015
         AND abs(o.lon - s.lon) < 0.0015
        """
    ).fetchone()
    print(f"  seed places in scope        : {seed_n:,}")
    print(f"  matched to an OSM record    : {matched:,}  ({100.0*matched/seed_n:.1f}%)")
    print(f"  matched AND OSM has hours   : {matched_hours:,}  ({100.0*matched_hours/seed_n:.1f}%)")

    # The decisive question. The sample above was Dunkin', LongHorn, Five Guys --
    # if OSM's hours coverage skews to chains, it contributes nothing to the
    # places Adventour actually exists to recommend.
    print("\n=== recoverable hours by chain class ===")
    names_pq = f"read_parquet('{(HERE / 'florida_names.parquet').as_posix()}')"
    con.execute(f"CREATE VIEW name_freq AS SELECT name_norm, count(*) fl_count FROM {names_pq} GROUP BY 1")
    con.execute(
        f"""
        CREATE VIEW seed_cls AS
        SELECT p.id, p.name, lower(trim(p.name)) AS name_norm, p.lat, p.lon,
            CASE WHEN p.brand_wikidata IS NOT NULL OR coalesce(f.fl_count,1) >= 10 THEN 'chain'
                 WHEN coalesce(f.fl_count,1) >= 3 THEN 'regional' ELSE 'independent' END AS chain_class
        FROM {PLACES} p
        LEFT JOIN name_freq f ON lower(trim(regexp_replace(p.name,
            '\\s+(at|of|in|-|–|—|@|\\|)\\s+.*$|\\s+\\(.*\\)$', '', 'i'))) = f.name_norm
        WHERE p.taxonomy_hierarchy[1] IN
            ('food_and_drink','arts_and_entertainment','cultural_and_historic','sports_and_recreation')
          AND coalesce(p.basic_category,'') NOT IN
            ('christian_place_of_worship','place_of_worship','cemetery','school',
             'gym','fitness_studio','sport_or_fitness_facility','swimming_pool')
          AND coalesce(p.operating_status,'open') <> 'closed'
        """
    )
    print(f"{'class':<14}{'in seed':>9}{'w/ OSM hours':>14}{'covered':>10}")
    for cls, n, got in con.execute(
        """
        SELECT s.chain_class, count(DISTINCT s.id),
               count(DISTINCT CASE WHEN o.opening_hours IS NOT NULL THEN s.id END)
        FROM seed_cls s
        LEFT JOIN osm o ON lower(trim(o.name)) = s.name_norm
             AND abs(o.lat - s.lat) < 0.0015 AND abs(o.lon - s.lon) < 0.0015
        GROUP BY 1 ORDER BY CASE s.chain_class
            WHEN 'chain' THEN 1 WHEN 'regional' THEN 2 ELSE 3 END
        """
    ).fetchall():
        print(f"{cls:<14}{n:>9,}{got:>14,}{100.0*got/n:>9.1f}%")

    print("\n=== sample of recoverable hours ===")
    for name, hours in con.execute(
        """
        SELECT DISTINCT s.name, o.opening_hours
        FROM seed s JOIN osm o
          ON lower(trim(o.name)) = s.name_norm
         AND abs(o.lat - s.lat) < 0.0015 AND abs(o.lon - s.lon) < 0.0015
        WHERE o.opening_hours IS NOT NULL
        LIMIT 8
        """
    ).fetchall():
        print(f"  {name[:34]:<34} {hours[:44]}")


if __name__ == "__main__":
    main()

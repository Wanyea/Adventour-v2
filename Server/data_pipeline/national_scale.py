"""How big is the index at US scale, and what does verification cost there?

Two metros is not a plan. This counts Adventour-relevant places across the
continental US directly from Overture rather than extrapolating, then prices
closure verification under a demand-driven rollout.
"""

import time
import duckdb

RELEASE = "2026-07-22.0"
PLACES = f"s3://overturemaps-us-west-2/release/{RELEASE}/theme=places/type=place/*"

RELEVANT = ("food_and_drink", "arts_and_entertainment", "cultural_and_historic", "sports_and_recreation")
# Gate 6: every labeled instance of these was rejected by a human.
DEAD_CATEGORIES = (
    "christian_place_of_worship", "place_of_worship", "cemetery", "school",
    "gym", "fitness_studio", "sport_or_recreation_club", "swimming_pool",
    "religious_organization",
)

CONUS = dict(xmin=-125.0, xmax=-66.9, ymin=24.4, ymax=49.4)

con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")

print("counting continental US (this scans a lot of parquet) ...", flush=True)
start = time.time()
total, relevant, kept, historic = con.execute(
    f"""
    SELECT
      count(*),
      count(*) FILTER (WHERE taxonomy.hierarchy[1] IN {RELEVANT}),
      count(*) FILTER (WHERE taxonomy.hierarchy[1] IN {RELEVANT}
                         AND coalesce(basic_category,'') NOT IN {DEAD_CATEGORIES}
                         AND coalesce(basic_category,'') <> 'historic_site'
                         AND basic_category IS NOT NULL
                         AND coalesce(operating_status,'open') <> 'closed'),
      count(*) FILTER (WHERE taxonomy.hierarchy[1] IN {RELEVANT}
                         AND basic_category = 'historic_site')
    FROM read_parquet('{PLACES}')
    WHERE bbox.xmin BETWEEN {CONUS['xmin']} AND {CONUS['xmax']}
      AND bbox.ymin BETWEEN {CONUS['ymin']} AND {CONUS['ymax']}
      AND names.primary IS NOT NULL
    """
).fetchone()
print(f"  done in {time.time()-start:.0f}s\n")

print("=== continental US, Overture places ===")
print(f"  all named POIs                    {total:>12,}")
print(f"  in Adventour taxonomy buckets     {relevant:>12,}")
print(f"  after Gate 6 category drops       {kept:>12,}   <- the real index")
print(f"    (historic_site removed alone:   {historic:>12,})")

RATE = 0.020  # Place Details Enterprise: businessStatus + currentOpeningHours
print(f"\n=== closure verification at ${RATE:.3f}/place ===")
print(f"  entire US index, once             ${kept*RATE:>12,.0f}")
print(f"  quarterly refresh                 ${kept*RATE*4:>12,.0f}/yr")

print("\n=== demand-driven rollout: pay per metro you actually enter ===")
print("  Cost scales with markets entered, not with the size of the index.")
# Our two metros give a real places-per-capita rate to size other markets.
pc_places, pc_pop = 712, 90_000
orl_places, orl_pop = 18_673, 2_700_000
rate_per_100k = ((pc_places / pc_pop) + (orl_places / orl_pop)) / 2 * 100_000
print(f"  observed ~{rate_per_100k:.0f} relevant places per 100k residents\n")
print(f"  {'market':<28}{'population':>12}{'~places':>10}{'one-time':>11}{'/yr @ Q':>10}")
for name, pop in [
    ("Palm Coast", 90_000),
    ("Orlando metro", 2_700_000),
    ("Chicago metro", 9_500_000),
    ("New York metro", 19_500_000),
    ("Top-10 US metros", 90_000_000),
    ("Top-50 US metros", 180_000_000),
]:
    n = pop / 100_000 * rate_per_100k
    print(f"  {name:<28}{pop:>12,}{n:>10,.0f}{n*RATE:>11,.0f}{n*RATE*4:>10,.0f}")

print("\n  Note: free Enterprise tier is 1,000 calls/month, so the first ~1,000")
print("  places in any new market are free. That covers a Palm Coast outright.")

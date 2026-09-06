"""The Scope A decision gate.

Question: can we source opening hours from businesses' own websites, or do
independents -- the places Adventour exists to surface -- lack the web presence
that chains have?

Refined after diagnose.py surfaced three problems with the first pass:
  1. 'either site or social' overstates what we can crawl. Overture's largest
     contributor is Meta, so social-derived records carry a social link by
     construction. That inflates 'socials' without implying hours are reachable.
     The honest number for a crawl plan is WEBSITE coverage alone.
  2. Exact-name matching missed chains with location suffixes ('Planet Fitness -
     Orlando (Belle Isle), FL'). Small -- 0.6% -- but free to fix.
  3. The relevant set carried ~4k non-destinations: churches, gyms, fitness
     studios. Nobody takes an Adventour to a Planet Fitness.
"""

from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent / "data"
PLACES = f"read_parquet('{(HERE / 'seed_places.parquet').as_posix()}')"
NAMES = f"read_parquet('{(HERE / 'florida_names.parquet').as_posix()}')"

RELEVANT = ("food_and_drink", "arts_and_entertainment", "cultural_and_historic", "sports_and_recreation")

# Present in the relevant taxonomy buckets, but not places you take an Adventour to.
EXCLUDED = (
    "christian_place_of_worship", "place_of_worship", "cemetery", "school",
    "gym", "fitness_studio", "sport_or_fitness_facility", "swimming_pool",
)

con = duckdb.connect()
con.execute(f"CREATE VIEW name_freq AS SELECT name_norm, count(*) fl_count FROM {NAMES} GROUP BY 1")

# Strip location qualifiers before matching, so 'Subway @ Orlando Science Center'
# resolves to 'subway'.
con.execute(
    f"""
    CREATE VIEW base AS
    SELECT *,
        lower(trim(regexp_replace(name,
            '\\s+(at|of|in|-|–|—|@|\\|)\\s+.*$|\\s+\\(.*\\)$', '', 'i'))) AS base_name,
        lower(trim(name)) AS exact_name
    FROM {PLACES}
    WHERE taxonomy_hierarchy[1] IN {RELEVANT}
      AND coalesce(operating_status,'open') <> 'closed'
      AND coalesce(basic_category,'') NOT IN {EXCLUDED}
    """
)

con.execute(
    """
    CREATE VIEW seed AS
    SELECT b.*,
        greatest(coalesce(fe.fl_count,1), coalesce(fb.fl_count,1)) AS fl_count,
        CASE
            WHEN b.brand_wikidata IS NOT NULL
              OR greatest(coalesce(fe.fl_count,1), coalesce(fb.fl_count,1)) >= 10 THEN 'chain'
            WHEN greatest(coalesce(fe.fl_count,1), coalesce(fb.fl_count,1)) >= 3 THEN 'regional'
            ELSE 'independent'
        END AS chain_class,
        (b.websites IS NOT NULL AND len(b.websites) > 0) AS has_site,
        (b.socials  IS NOT NULL AND len(b.socials)  > 0) AS has_social
    FROM base b
    LEFT JOIN name_freq fe ON b.exact_name = fe.name_norm
    LEFT JOIN name_freq fb ON b.base_name  = fb.name_norm
    """
)

total = con.execute("SELECT count(*) FROM seed").fetchone()[0]
print(f"Adventour-relevant destinations, Orlando + Palm Coast: {total:,}")
print("(after removing worship, gyms, fitness, pools, cemeteries)\n")

print("=== web presence by chain class ===")
print(f"{'class':<14}{'places':>9}{'WEBSITE':>10}{'socials':>10}")
for cls, n, site, social in con.execute(
    """
    SELECT chain_class, count(*),
           round(100.0*sum(has_site::int)/count(*), 1),
           round(100.0*sum(has_social::int)/count(*), 1)
    FROM seed GROUP BY 1
    ORDER BY CASE chain_class WHEN 'chain' THEN 1 WHEN 'regional' THEN 2 ELSE 3 END
    """
).fetchall():
    print(f"{cls:<14}{n:>9,}{site:>9}%{social:>9}%")

print("\n=== the number that matters: independents with a crawlable website ===")
print(f"{'bucket':<28}{'places':>9}{'website':>10}{'crawlable':>11}")
grand = 0
for bucket, n, pct, crawl in con.execute(
    """
    SELECT taxonomy_hierarchy[1], count(*),
           round(100.0*sum(has_site::int)/count(*), 1), sum(has_site::int)
    FROM seed WHERE chain_class='independent'
    GROUP BY 1 ORDER BY 2 DESC
    """
).fetchall():
    grand += crawl
    print(f"{bucket:<28}{n:>9,}{pct:>9}%{crawl:>11,}")
print(f"{'TOTAL':<28}{'':>9}{'':>10}{grand:>11,}")

# NOTE: provenance breakdown (coverage by source dataset) needs the `sources`
# column, which pull_overture.py does not select. Worth adding in Scope A to
# confirm whether social coverage is a Meta-provenance artifact -- but it does
# not gate this decision, because the crawl plan rests on WEBSITE coverage only.

print("\n=== crawl target sizing ===")
n_crawl, n_total = con.execute(
    """
    SELECT sum(has_site::int), count(*) FROM seed
    WHERE chain_class IN ('independent','regional')
    """
).fetchone()
n_chain = con.execute("SELECT count(*) FROM seed WHERE chain_class='chain'").fetchone()[0]
print(f"  independents + regionals with a website: {n_crawl:,} of {n_total:,}")
print(f"  chains (hours less critical, and we deprioritize them anyway): {n_chain:,}")

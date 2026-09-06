"""Two suspicious results from measure_coverage.py:
  1. sports_and_recreation independents at exactly 100% 'either' -- implausible.
  2. 'Publix Liquors at Beach Village' classed independent -- exact-name matching
     is defeated by location suffixes.
"""

from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent / "data"
PLACES = f"read_parquet('{(HERE / 'seed_places.parquet').as_posix()}')"
NAMES = f"read_parquet('{(HERE / 'florida_names.parquet').as_posix()}')"

con = duckdb.connect()
con.execute(f"CREATE VIEW name_freq AS SELECT name_norm, count(*) fl_count FROM {NAMES} GROUP BY 1")
con.execute(
    f"""
    CREATE VIEW seed AS
    SELECT p.*, coalesce(f.fl_count,1) AS fl_count,
        CASE WHEN p.brand_wikidata IS NOT NULL OR coalesce(f.fl_count,1) >= 10 THEN 'chain'
             WHEN coalesce(f.fl_count,1) >= 3 THEN 'regional' ELSE 'independent' END AS chain_class,
        (p.websites IS NOT NULL AND len(p.websites) > 0) AS has_site,
        (p.socials IS NOT NULL AND len(p.socials) > 0) AS has_social
    FROM {PLACES} p LEFT JOIN name_freq f ON lower(trim(p.name)) = f.name_norm
    WHERE p.taxonomy_hierarchy[1] IN
        ('food_and_drink','arts_and_entertainment','cultural_and_historic','sports_and_recreation')
      AND coalesce(p.operating_status,'open') <> 'closed'
    """
)

print("=== 1. sports_and_recreation: is 100% real? ===")
n, site, social, either = con.execute(
    """
    SELECT count(*), sum(has_site::int), sum(has_social::int),
           sum((has_site OR has_social)::int)
    FROM seed WHERE chain_class='independent' AND taxonomy_hierarchy[1]='sports_and_recreation'
    """
).fetchone()
print(f"  places={n:,}  website={site:,}  social={social:,}  either={either:,}")
print(f"  places WITHOUT either: {n - either}")

print("\n  top basic_category in that bucket:")
for cat, c in con.execute(
    """
    SELECT coalesce(basic_category,'(none)'), count(*) FROM seed
    WHERE chain_class='independent' AND taxonomy_hierarchy[1]='sports_and_recreation'
    GROUP BY 1 ORDER BY 2 DESC LIMIT 8
    """
).fetchall():
    print(f"    {cat:<36} {c:>6,}")

print("\n=== 2. how many 'independents' are chains with a location suffix? ===")
# Strip a trailing location qualifier and re-test against Florida name counts.
con.execute(
    """
    CREATE VIEW restripped AS
    SELECT name, fl_count,
        lower(trim(regexp_replace(name,
            '\\s+(at|of|in|-|–|—|@|\\|)\\s+.*$|\\s+\\(.*\\)$', '', 'i'))) AS base_name
    FROM seed WHERE chain_class='independent'
    """
)
rows = con.execute(
    """
    SELECT r.name, r.base_name, f.fl_count AS base_fl
    FROM restripped r JOIN name_freq f ON r.base_name = f.name_norm
    WHERE f.fl_count >= 10 AND r.base_name <> lower(trim(r.name))
    ORDER BY f.fl_count DESC LIMIT 15
    """
).fetchall()
misses = con.execute(
    """
    SELECT count(*) FROM restripped r JOIN name_freq f ON r.base_name = f.name_norm
    WHERE f.fl_count >= 10 AND r.base_name <> lower(trim(r.name))
    """
).fetchone()[0]
total_indep = con.execute("SELECT count(*) FROM seed WHERE chain_class='independent'").fetchone()[0]
print(f"  misclassified by suffix: {misses:,} of {total_indep:,} independents "
      f"({100.0*misses/total_indep:.1f}%)")
for name, base, fl in rows:
    print(f"    {name:<40} -> {base:<24} FL={fl}")

print("\n=== 3. non-destination noise in the relevant set ===")
for cat, c in con.execute(
    """
    SELECT basic_category, count(*) FROM seed
    WHERE basic_category IN ('christian_place_of_worship','place_of_worship','atm',
                             'school','cemetery','office')
    GROUP BY 1 ORDER BY 2 DESC
    """
).fetchall():
    print(f"    {cat:<36} {c:>6,}")

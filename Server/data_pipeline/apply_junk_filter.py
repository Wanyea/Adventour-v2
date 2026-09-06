"""Apply the tiered filter to the loaded seed and report the impact."""

import os
import psycopg2
from psycopg2.extras import execute_values

from junk_filter import classify, needs_booking

DSN = os.environ.get("ADVENTOUR_PG_DSN", "host=localhost port=5432 user=postgres dbname=adventour")

with psycopg2.connect(DSN) as conn, conn.cursor() as cur:
    cur.execute("ALTER TABLE places ADD COLUMN IF NOT EXISTS tier text")
    cur.execute("ALTER TABLE places ADD COLUMN IF NOT EXISTS tier_reason text")
    cur.execute("ALTER TABLE places ADD COLUMN IF NOT EXISTS needs_booking boolean DEFAULT false")
    cur.execute("SELECT id, name, basic_category FROM places")
    rows = cur.fetchall()

    updates = []
    for pid, name, cat in rows:
        tier, reason = classify(name, cat)
        updates.append((pid, tier, reason, needs_booking(name, cat)))

    execute_values(
        cur,
        """UPDATE places p SET tier = v.tier, tier_reason = v.reason,
                             needs_booking = v.booking
           FROM (VALUES %s) AS v(id, tier, reason, booking) WHERE p.id = v.id""",
        updates, page_size=2000,
    )
    cur.execute("CREATE INDEX IF NOT EXISTS places_tier_idx ON places (tier)")
    conn.commit()

    print(f"=== tiers across {len(rows):,} places ===")
    cur.execute("""SELECT tier, count(*), round(100.0*count(*)/sum(count(*)) OVER (), 1)
                   FROM places GROUP BY 1 ORDER BY 2 DESC""")
    for tier, n, pct in cur.fetchall():
        print(f"  {tier:<8}{n:>8,}{pct:>7}%")

    print("\n=== why places were dropped ===")
    cur.execute("""SELECT tier_reason, count(*) FROM places WHERE tier='DROP'
                   GROUP BY 1 ORDER BY 2 DESC LIMIT 14""")
    for reason, n in cur.fetchall():
        print(f"  {reason:<40}{n:>8,}")

    print("\n=== what survives, by metro and chain class ===")
    cur.execute("""SELECT metro, chain_class, count(*) FROM places WHERE tier='KEEP'
                   GROUP BY 1,2 ORDER BY 1, CASE chain_class
                     WHEN 'chain' THEN 1 WHEN 'regional' THEN 2 ELSE 3 END""")
    for metro, cls, n in cur.fetchall():
        print(f"  {metro:<12}{cls:<14}{n:>8,}")

    print("\n=== the deck a Palm Coast user would now see (nearest independents) ===")
    cur.execute("""
        SELECT name, basic_category,
               round((6371000 * acos(least(1, greatest(-1,
                   cos(radians(29.5844))*cos(radians(lat))*cos(radians(lon)-radians(-81.2079))
                 + sin(radians(29.5844))*sin(radians(lat))))))::numeric) AS m
        FROM places
        WHERE tier='KEEP' AND chain_class IN ('independent','regional') AND metro='palm_coast'
        ORDER BY m LIMIT 12
    """)
    for name, cat, m in cur.fetchall():
        print(f"  {str(m):>6}m  {name[:40]:<40} {cat}")

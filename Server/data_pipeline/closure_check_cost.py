"""What does closure-checking actually cost, under each strategy?

Gate 6 found 9.1% of the seed permanently closed, undetectable from free data.
This prices the options. Rates are the 0-100k volume tier, verified 2026-08-17.

Field-mask detail that matters: in Places API (New), `businessStatus` sits in the
Pro tier, but `currentOpeningHours` is Enterprise. Since we are paying for a call
either way, +$0.003 buys the live hours we could not source at all (Gate 2-4).
"""

import os
import psycopg2

DSN = os.environ.get("ADVENTOUR_PG_DSN", "host=localhost port=5432 user=postgres dbname=adventour")

DETAILS_PRO = 0.017         # businessStatus  -> closure detection only
DETAILS_ENTERPRISE = 0.020  # + currentOpeningHours, rating, priceLevel
FREE_PRO_PER_MONTH = 5_000
FREE_ENTERPRISE_PER_MONTH = 1_000

CLOSED_RATE = 0.091         # measured, Gate 6
CARDS_PER_SESSION = 12      # cards a user actually swipes before accepting or quitting
SESSIONS_PER_USER_MONTH = 4

with psycopg2.connect(DSN) as conn, conn.cursor() as cur:
    cur.execute("SELECT metro, count(*) FROM places GROUP BY 1 ORDER BY 2 DESC")
    metros = dict(cur.fetchall())
total_places = sum(metros.values())

print("=== the seed ===")
for m, n in metros.items():
    print(f"  {m:<12}{n:>8,}")
print(f"  {'TOTAL':<12}{total_places:>8,}")

print(f"\n=== per-session cost (12 cards swiped, {CLOSED_RATE:.1%} of them dead) ===")
print(f"  {'strategy':<44}{'calls':>7}{'$/session':>12}{'dead cards seen':>18}")

def row(name, calls, protected_cards, rate=DETAILS_ENTERPRISE):
    cost = calls * rate
    unprotected = CARDS_PER_SESSION - protected_cards
    dead = unprotected * CLOSED_RATE
    print(f"  {name:<44}{calls:>7}{cost:>12.3f}{dead:>18.2f}")
    return cost

c_none  = row("A. no check", 0, 0)
c_all   = row("B. check every displayed card", CARDS_PER_SESSION, CARDS_PER_SESSION)
c_top3  = row("C. check top 3 only", 3, 3)
c_lazy  = row("D. top 3 + refill 3 at a time as they swipe", CARDS_PER_SESSION, CARDS_PER_SESSION)

print(f"\n  For scale, the Path A deck-driven model priced in the brief was $0.130/session.")

print("\n=== monthly cost at scale (4 sessions/user) ===")
print(f"  {'users':>8}{'B: every card':>16}{'C: top 3':>12}{'A: none':>10}")
for users in (100, 1_000, 10_000, 100_000):
    s = users * SESSIONS_PER_USER_MONTH
    print(f"  {users:>8,}{s*c_all:>16,.0f}{s*c_top3:>12,.0f}{0:>10}")

print("\n=== strategy E: verify each PLACE once, persist the result ===")
print("  Cost scales with distinct places, not impressions -- so it saturates.")
for m, n in metros.items():
    print(f"  {m:<12}{n:>8,} places  x ${DETAILS_ENTERPRISE:.3f} = ${n*DETAILS_ENTERPRISE:>9,.2f}")
print(f"  {'BOTH':<12}{total_places:>8,} places  x ${DETAILS_ENTERPRISE:.3f} = "
      f"${total_places*DETAILS_ENTERPRISE:>9,.2f}  one-time")
print(f"  quarterly re-verify: ${total_places*DETAILS_ENTERPRISE*4:,.2f}/yr for the whole index")

print("\n  Palm Coast alone, to launch one testable metro:")
pc = metros.get("palm_coast", 0)
print(f"    ${pc*DETAILS_ENTERPRISE:.2f} one-time  /  ${pc*DETAILS_ENTERPRISE*4:.2f} per year")

print("\n=== where the free tier lands ===")
print(f"  Enterprise free tier: {FREE_ENTERPRISE_PER_MONTH:,} calls/month")
print(f"    covers {FREE_ENTERPRISE_PER_MONTH/CARDS_PER_SESSION:>6.0f} sessions/month under B")
print(f"    covers {FREE_ENTERPRISE_PER_MONTH/3:>6.0f} sessions/month under C")
print(f"    covers all of Palm Coast ({pc:,} places) in "
      f"{pc/FREE_ENTERPRISE_PER_MONTH:.1f} months under E, at zero cost")

"""Score every KEEP place, then check the combined score beats its parts."""

import json
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

from authenticity import authenticity_score, explain
from eval_authenticity_signals import auc

DSN = os.environ.get("ADVENTOUR_PG_DSN", "host=localhost port=5432 user=postgres dbname=adventour")
HERE = Path(__file__).resolve().parent
LABELS = {r["id"]: r for r in
          json.loads((HERE / "qa" / "adventour_palm_coast_labels.json").read_text(encoding="utf-8"))["labels"]}

with psycopg2.connect(DSN) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
    cur.execute("ALTER TABLE places ADD COLUMN IF NOT EXISTS authenticity double precision")
    cur.execute("ALTER TABLE places ADD COLUMN IF NOT EXISTS authenticity_why text")
    cur.execute("""
        SELECT p.id, p.name, p.confidence, p.socials, p.chain_class, p.metro,
               (SELECT count(*) FROM places q WHERE q.h3_r8=p.h3_r8 AND q.tier='KEEP') AS cell_density
        FROM places p WHERE p.tier='KEEP'
    """)
    rows = [dict(r) for r in cur.fetchall()]

    updates = []
    for r in rows:
        s, comp = authenticity_score(
            r["confidence"], bool(r["socials"]), r["cell_density"], r["chain_class"])
        r["score"] = s
        updates.append((r["id"], s, explain(r["name"], s, comp, r["chain_class"])))

    execute_values(cur,
        """UPDATE places p SET authenticity=v.s, authenticity_why=v.w
           FROM (VALUES %s) AS v(id, s, w) WHERE p.id=v.id""",
        updates, page_size=2000)
    cur.execute("CREATE INDEX IF NOT EXISTS places_auth_idx ON places (authenticity DESC)")
    conn.commit()

print(f"scored {len(rows):,} KEEP places")

# Does combining actually help, or is confidence carrying it alone?
labeled = []
for r in rows:
    lab = LABELS.get(r["id"])
    if lab and lab["label"] and lab["label"] not in ("solid", "chain"):
        labeled.append((r, 1 if lab["label"] == "gem" else 0))

print(f"\n=== combined score vs its parts (n={len(labeled)}) ===")
print(f"  {'combined authenticity score':<34}{auc([(r['score'], y) for r, y in labeled]):>7.3f}")
print(f"  {'confidence alone':<34}{auc([(float(r['confidence'] or 0), y) for r, y in labeled]):>7.3f}")

with psycopg2.connect(DSN) as conn, conn.cursor() as cur:
    print("\n=== top scored, Palm Coast ===")
    cur.execute("""SELECT name, round(authenticity::numeric,3), authenticity_why FROM places
                   WHERE tier='KEEP' AND metro='palm_coast'
                   ORDER BY authenticity DESC LIMIT 10""")
    for n, s, w in cur.fetchall():
        print(f"  {str(s):<6} {n[:36]:<36} {w[7:]}")
    print("\n=== bottom scored, Palm Coast ===")
    cur.execute("""SELECT name, round(authenticity::numeric,3), authenticity_why FROM places
                   WHERE tier='KEEP' AND metro='palm_coast'
                   ORDER BY authenticity ASC LIMIT 6""")
    for n, s, w in cur.fetchall():
        print(f"  {str(s):<6} {n[:36]:<36} {w[7:]}")

"""Test candidate authenticity signals against the human labels before building a score.

The brief asserted several of these. Asserting is how the popularity mistake got in.
Each signal here is measured on the places that survive the junk filter, because
authenticity ranking only ever applies to those.

Positive class = 'gem'. Negative = generic / not_worth / junk. 'solid' and 'chain'
are excluded from the contrast so the signal is measured on the real question:
among plausible places, which ones are actually special?
"""

import json
import math
import os
import re
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

DSN = os.environ.get("ADVENTOUR_PG_DSN", "host=localhost port=5432 user=postgres dbname=adventour")
HERE = Path(__file__).resolve().parent
LABELS = {r["id"]: r for r in
          json.loads((HERE / "qa" / "adventour_palm_coast_labels.json").read_text(encoding="utf-8"))["labels"]}

# Tokens that root a name in this specific place. Built from local geography,
# not from the label set, so it is not fitted to the answers.
LOCAL_TOKENS = re.compile(
    r"\b(palm coast|flagler|hammock|a1a|coquina|matanzas|ormond|bunnell|"
    r"marineland|beachside|oceanside|beach|coast|island|intracoastal|dunes)\b", re.I)


def auc(pairs):
    """Rank AUC. 0.5 = no signal. Handles ties at 0.5 credit."""
    pos = [v for v, y in pairs if y]
    neg = [v for v, y in pairs if not y]
    if not pos or not neg:
        return float("nan")
    wins = sum((1.0 if p > n else 0.5 if p == n else 0.0) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def main():
    with psycopg2.connect(DSN) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            WITH cat_metro AS (
                SELECT metro, basic_category, count(*) AS n_local
                FROM places WHERE tier='KEEP' GROUP BY 1,2
            ), cat_all AS (
                SELECT basic_category, count(*) AS n_state
                FROM places WHERE tier='KEEP' GROUP BY 1
            ), tot AS (
                SELECT metro, count(*) AS m_total FROM places WHERE tier='KEEP' GROUP BY 1
            ), grand AS (SELECT count(*) AS g FROM places WHERE tier='KEEP')
            SELECT p.id, p.name, p.basic_category, p.chain_class, p.confidence,
                   p.fl_name_count, p.websites, p.socials, p.h3_r8,
                   cm.n_local, ca.n_state, t.m_total, g.g,
                   (SELECT count(*) FROM places q
                     WHERE q.h3_r8 = p.h3_r8 AND q.tier='KEEP') AS cell_density
            FROM places p
            JOIN cat_metro cm ON cm.metro=p.metro AND cm.basic_category IS NOT DISTINCT FROM p.basic_category
            JOIN cat_all  ca ON ca.basic_category IS NOT DISTINCT FROM p.basic_category
            JOIN tot t ON t.metro=p.metro
            CROSS JOIN grand g
            WHERE p.tier='KEEP' AND p.metro='palm_coast'
            """
        )
        rows = [dict(r) for r in cur.fetchall()]

    labeled = []
    for r in rows:
        lab = LABELS.get(r["id"])
        if not lab or not lab["label"]:
            continue
        if lab["label"] in ("solid", "chain"):
            continue
        r["y"] = 1 if lab["label"] == "gem" else 0
        labeled.append(r)

    print(f"evaluating on {len(labeled)} labeled KEEP places "
          f"({sum(r['y'] for r in labeled)} gems / {sum(1-r['y'] for r in labeled)} not)\n")

    def feat_category_rarity(r):
        # Local share of this category vs its share across the whole index.
        # <1 means the category is under-represented locally = "distinctive".
        local_share = r["n_local"] / max(r["m_total"], 1)
        global_share = r["n_state"] / max(r["g"], 1)
        return -math.log((local_share + 1e-9) / (global_share + 1e-9))

    FEATURES = {
        "chain_class (indep+regional > chain)":
            lambda r: {"independent": 1, "regional": 1, "chain": 0}.get(r["chain_class"], 0),
        "regional specifically":
            lambda r: 1 if r["chain_class"] == "regional" else 0,
        "category rarity (brief's 'distinctiveness')": feat_category_rarity,
        "local name affinity": lambda r: 1 if LOCAL_TOKENS.search(r["name"] or "") else 0,
        "Overture confidence": lambda r: float(r["confidence"] or 0),
        "has website": lambda r: 1 if (r["websites"] or []) else 0,
        "has socials": lambda r: 1 if (r["socials"] or []) else 0,
        "statewide name count (low = unique)": lambda r: -math.log1p(r["fl_name_count"]),
        "H3 cell density (low = off the strip)": lambda r: -math.log1p(r["cell_density"]),
    }

    print(f"  {'signal':<46}{'AUC':>7}   reading")
    results = []
    for name, fn in FEATURES.items():
        a = auc([(fn(r), r["y"]) for r in labeled])
        if a != a:
            verdict = "no variance"
        elif a >= 0.65:
            verdict = "USEFUL"
        elif a >= 0.57:
            verdict = "weak"
        elif a <= 0.35:
            verdict = "USEFUL, INVERTED"
        elif a <= 0.43:
            verdict = "weak, inverted"
        else:
            verdict = "no signal"
        results.append((name, a, verdict))
        print(f"  {name:<46}{a:>7.3f}   {verdict}")

    print("\n=== the category-rarity hypothesis, examined ===")
    print("  The brief claimed locally-rare categories are more authentic.")
    gems = [r for r in labeled if r["y"]]
    top = sorted(gems, key=lambda r: -r["n_local"])[:8]
    print(f"  Most COMMON local categories among gems:")
    for r in top:
        print(f"    {r['name'][:34]:<34} {str(r['basic_category']):<18} {r['n_local']:>4} in metro")


if __name__ == "__main__":
    main()


def confound_check():
    """Is `confidence` measuring authenticity, or just re-detecting closures?

    Gate 6 found 12 closed businesses, and several sit in the negative class here.
    If confidence is really an existence score, its apparent signal would vanish
    once closures are removed from the contrast.
    """
    import re as _re
    CLOSED = _re.compile(r"(closed|doesn'?t exist|does not exist|couldn'?t find)", _re.I)

    with psycopg2.connect(DSN) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""SELECT id, confidence, socials, h3_r8,
                              (SELECT count(*) FROM places q WHERE q.h3_r8=p.h3_r8 AND q.tier='KEEP') AS cell_density
                       FROM places p WHERE tier='KEEP' AND metro='palm_coast'""")
        rows = {r["id"]: dict(r) for r in cur.fetchall()}

    keep, dropped = [], 0
    for pid, r in rows.items():
        lab = LABELS.get(pid)
        if not lab or not lab["label"] or lab["label"] in ("solid", "chain"):
            continue
        note = lab.get("note") or ""
        if lab["label"] != "gem" and CLOSED.search(note):
            dropped += 1
            continue          # remove closures from the negative class
        r["y"] = 1 if lab["label"] == "gem" else 0
        keep.append(r)

    print(f"\n=== confound check: closures removed from the negatives ===")
    print(f"  excluded {dropped} closed places; {len(keep)} remain "
          f"({sum(r['y'] for r in keep)} gems / {sum(1-r['y'] for r in keep)} not)")
    for name, fn in (
        ("Overture confidence", lambda r: float(r["confidence"] or 0)),
        ("has socials", lambda r: 1 if (r["socials"] or []) else 0),
        ("H3 cell density", lambda r: -math.log1p(r["cell_density"])),
    ):
        a = auc([(fn(r), r["y"]) for r in keep])
        print(f"  {name:<28}{a:>7.3f}")


confound_check()

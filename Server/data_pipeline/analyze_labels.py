"""What the Palm Coast ground truth says about our signals.

Reads qa/adventour_palm_coast_labels.json and scores every heuristic we built
against a human who has lived there 18 years.
"""

import json
import os
import re
from collections import Counter
from pathlib import Path

import psycopg2

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "qa" / "adventour_palm_coast_labels.json").read_text(encoding="utf-8"))
ROWS = DATA["labels"]
DSN = os.environ.get("ADVENTOUR_PG_DSN", "host=localhost port=5432 user=postgres dbname=adventour")

GOOD = {"gem", "solid"}
BAD = {"junk", "not_worth"}

def pct(n, d):
    return f"{100.0*n/d:>5.1f}%" if d else "    -"

print(f"=== labels ({len(ROWS)} places, {sum(1 for r in ROWS if r['label'])} labeled) ===")
for label, n in Counter(r["label"] for r in ROWS).most_common():
    print(f"  {str(label):<12}{n:>4}  {pct(n, len(ROWS))}")

# ---------------------------------------------------------------- chain class
print("\n=== our chain_class vs their verdict ===")
print(f"  {'we said':<14}{'n':>4}{'gem':>6}{'solid':>7}{'generic':>9}{'not_worth':>11}{'junk':>6}{'chain':>7}")
for cls in ("chain", "regional", "independent"):
    sub = [r for r in ROWS if r["our_chain_class"] == cls and r["label"]]
    c = Counter(r["label"] for r in sub)
    print(f"  {cls:<14}{len(sub):>4}{c['gem']:>6}{c['solid']:>7}{c['generic']:>9}"
          f"{c['not_worth']:>11}{c['junk']:>6}{c['chain']:>7}")

called_chain = [r for r in ROWS if r["label"] == "chain"]
print(f"\n  they called {len(called_chain)} places a chain; we had classified them as:")
for cls, n in Counter(r["our_chain_class"] for r in called_chain).most_common():
    print(f"    {cls:<14}{n:>4}")

# ---------------------------------------------------------------- junk filter
JUNK_RE = re.compile(r"(hoa|homeowners|condominium|condo assoc|property owners|association, inc|apartments|realty|property manag)", re.I)
CORP_RE = re.compile(r"(llc|inc\.?$|corp|holdings)", re.I)

print("\n=== junk detection: did our name heuristic catch what they rejected? ===")
truth_junk = [r for r in ROWS if r["label"] == "junk"]
caught = [r for r in truth_junk if JUNK_RE.search(r["name"]) or CORP_RE.search(r["name"])]
print(f"  they marked junk        : {len(truth_junk)}")
print(f"  our name patterns caught: {len(caught)}  ({pct(len(caught), len(truth_junk)).strip()})")
print(f"  MISSED by name patterns : {len(truth_junk)-len(caught)}")
for r in truth_junk:
    if not (JUNK_RE.search(r["name"]) or CORP_RE.search(r["name"])):
        print(f"    {r['name'][:42]:<42} {str(r['basic_category'])}")

# false positives: our patterns fired but the human liked it
fp = [r for r in ROWS if (JUNK_RE.search(r["name"]) or CORP_RE.search(r["name"])) and r["label"] in GOOD]
print(f"\n  our patterns fired on {len(fp)} places they actually liked:")
for r in fp:
    print(f"    {r['name'][:42]:<42} {r['label']}")

# ---------------------------------------------------------------- categories
print("\n=== which Overture categories are worth recommending? ===")
bycat = {}
for r in ROWS:
    if not r["label"]:
        continue
    bycat.setdefault(str(r["basic_category"]), []).append(r["label"])
print(f"  {'category':<32}{'n':>4}{'good':>6}{'bad':>5}   verdict")
for cat, labs in sorted(bycat.items(), key=lambda kv: -len(kv[1])):
    if len(labs) < 2:
        continue
    g = sum(1 for l in labs if l in GOOD)
    b = sum(1 for l in labs if l in BAD)
    verdict = "DROP" if b == len(labs) else ("keep" if g > b else "mixed")
    print(f"  {cat:<32}{len(labs):>4}{g:>6}{b:>5}   {verdict}")

# ---------------------------------------------------------------- closures
print("\n=== closed / nonexistent businesses ===")
CLOSED_RE = re.compile(r"(closed|doesn'?t exist|does not exist|couldn'?t find|not exist)", re.I)
closed = [r for r in ROWS if r["note"] and CLOSED_RE.search(r["note"])]
print(f"  flagged closed or gone by the human: {len(closed)}  ({pct(len(closed), len(ROWS)).strip()} of sample)")
would_have = [r for r in closed if re.search(r"would have|or i'?d recommend|might have", r["note"], re.I)]
print(f"  of those, they SAID they would have recommended it: {len(would_have)}")
print(f"  their Overture confidence: min {min(r['confidence'] for r in closed):.2f} "
      f"max {max(r['confidence'] for r in closed):.2f} "
      f"mean {sum(r['confidence'] for r in closed)/len(closed):.2f}")
for r in closed:
    print(f"    conf {r['confidence']:.2f}  {r['name'][:38]:<38} {r['note'][:44]}")

# ---------------------------------------------------------------- confidence
print("\n=== does Overture confidence predict anything? ===")
for lo, hi in ((0.0, 0.5), (0.5, 0.8), (0.8, 0.95), (0.95, 1.01)):
    sub = [r for r in ROWS if r["label"] and lo <= r["confidence"] < hi]
    if not sub:
        continue
    g = sum(1 for r in sub if r["label"] in GOOD)
    b = sum(1 for r in sub if r["label"] in BAD)
    print(f"  conf {lo:.2f}-{hi:.2f}: n={len(sub):>3}  good {pct(g,len(sub))}  bad {pct(b,len(sub))}")

# ---------------------------------------------------------------- recall
print("\n=== recall: are their must-have places even in our database? ===")
wanted = [w.strip() for w in DATA["freeform"]["missing"].split(",") if w.strip()]
with psycopg2.connect(DSN) as conn, conn.cursor() as cur:
    for w in wanted:
        key = re.sub(r"\s+in\s+.*$|\s*\(.*\)$", "", w).strip()
        cur.execute(
            """SELECT name, basic_category, chain_class FROM places
               WHERE metro='palm_coast' AND name ILIKE %s LIMIT 2""",
            (f"%{key.split()[0]}%" if len(key.split()) == 1 else f"%{' '.join(key.split()[:2])}%",),
        )
        hits = cur.fetchall()
        mark = "  IN DB" if hits else "MISSING"
        extra = f" -> {hits[0][0]}" if hits else ""
        print(f"  [{mark}] {key[:40]:<40}{extra}")

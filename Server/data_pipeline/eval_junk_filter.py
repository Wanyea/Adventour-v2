"""Score the junk filter against the 131 human labels.

The asymmetry that matters: dropping a place the reviewer called a gem is a
product failure you cannot see. Leaving junk in is a swipe. So false positives
are the number to drive to zero, and recall is secondary.
"""

import json
from collections import Counter
from pathlib import Path

from junk_filter import classify

HERE = Path(__file__).resolve().parent
ROWS = json.loads((HERE / "qa" / "adventour_palm_coast_labels.json").read_text(encoding="utf-8"))["labels"]
ROWS = [r for r in ROWS if r["label"]]

GOOD = {"gem", "solid"}
REJECTED = {"junk", "not_worth"}

for r in ROWS:
    r["tier"], r["reason"] = classify(r["name"], r["basic_category"])

print(f"=== filter output over {len(ROWS)} labeled places ===")
for tier, n in Counter(r["tier"] for r in ROWS).most_common():
    print(f"  {tier:<8}{n:>5}")

# ---- the number that must be zero -----------------------------------------
fp = [r for r in ROWS if r["tier"] == "DROP" and r["label"] in GOOD]
print(f"\n=== FALSE POSITIVES (dropped something they liked): {len(fp)} ===")
for r in fp:
    print(f"  !! {r['name'][:44]:<44} {r['label']:<6} {r['reason']}")
if not fp:
    print("  none")

# ---- recall on what they rejected -----------------------------------------
truth_junk = [r for r in ROWS if r["label"] == "junk"]
dropped_junk = [r for r in truth_junk if r["tier"] == "DROP"]
print(f"\n=== recall on 'junk' ===")
print(f"  labeled junk        {len(truth_junk):>4}")
print(f"  filter drops        {len(dropped_junk):>4}   ({100.0*len(dropped_junk)/len(truth_junk):.1f}%)")
print(f"  previous heuristic          61.2%")

missed = [r for r in truth_junk if r["tier"] != "DROP"]
print(f"\n  still missed ({len(missed)}):")
for r in missed:
    print(f"    {r['name'][:44]:<44} {str(r['basic_category']):<26} -> {r['tier']}")

# ---- precision -------------------------------------------------------------
dropped = [r for r in ROWS if r["tier"] == "DROP"]
correct = [r for r in dropped if r["label"] in REJECTED]
print(f"\n=== precision ===")
print(f"  filter drops        {len(dropped):>4}")
print(f"  of those, rejected by human {len(correct):>4}   "
      f"({100.0*len(correct)/len(dropped):.1f}%)")
other = [r for r in dropped if r["label"] not in REJECTED and r["label"] not in GOOD]
if other:
    print(f"  dropped but labeled generic/chain ({len(other)}):")
    for r in other:
        print(f"    {r['name'][:40]:<40} {r['label']:<8} {r['reason']}")

# ---- what survives ---------------------------------------------------------
kept = [r for r in ROWS if r["tier"] == "KEEP"]
kg = sum(1 for r in kept if r["label"] in GOOD)
kb = sum(1 for r in kept if r["label"] in REJECTED)
print(f"\n=== quality of what survives ===")
print(f"  before filter: {sum(1 for r in ROWS if r['label'] in GOOD)} good / "
      f"{sum(1 for r in ROWS if r['label'] in REJECTED)} bad  of {len(ROWS)}"
      f"   ({100.0*sum(1 for r in ROWS if r['label'] in GOOD)/len(ROWS):.1f}% good)")
print(f"  after filter : {kg} good / {kb} bad  of {len(kept)}"
      f"   ({100.0*kg/len(kept):.1f}% good)")

print(f"\n=== GATED and MOBILE tiers ===")
for tier in ("GATED", "MOBILE"):
    sub = [r for r in ROWS if r["tier"] == tier]
    if not sub:
        continue
    print(f"  {tier}:")
    for r in sub:
        print(f"    {r['name'][:44]:<44} {r['label']:<10} {r['reason']}")

print("\n=== remaining bad places that survive as KEEP ===")
for r in kept:
    if r["label"] in REJECTED:
        note = (r["note"] or "")[:40]
        print(f"    {r['name'][:38]:<38} {r['label']:<10} {str(r['basic_category'])[:18]:<18} {note}")

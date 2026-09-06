"""Do the Palm Coast findings hold in Orlando?

Gate 8's caveat was explicit: n=46, one metro, one labeller, nine signals tested.
This re-runs the same measurements on a second metro with different character --
a tourist strip (32819), a local neighbourhood (32803), and a campus (32816).
"""

import json
import math
import os
import re
from collections import Counter
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

HERE = Path(__file__).resolve().parent / "qa"
DSN = os.environ.get("ADVENTOUR_PG_DSN", "host=localhost port=5432 user=postgres dbname=adventour")
GOOD, BAD = {"gem", "solid"}, {"junk", "not_worth"}


def auc(pairs):
    pos = [v for v, y in pairs if y]
    neg = [v for v, y in pairs if not y]
    if not pos or not neg:
        return float("nan")
    return sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg) / (len(pos) * len(neg))


def load(fname):
    return json.loads((HERE / fname).read_text(encoding="utf-8"))


def enrich(labels):
    ids = [r["id"] for r in labels]
    with psycopg2.connect(DSN) as c, c.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT id, confidence, socials, websites, chain_class, tier, authenticity, postcode,
                   (SELECT count(*) FROM places q WHERE q.h3_r8=p.h3_r8 AND q.tier='KEEP') AS cell_density
            FROM places p WHERE id = ANY(%s)""", (ids,))
        idx = {r["id"]: dict(r) for r in cur.fetchall()}
    out = []
    for r in labels:
        if not r["label"] or r["id"] not in idx:
            continue
        out.append({**r, **idx[r["id"]]})
    return out


for fname, name in (("adventour_palm_coast_labels.json", "PALM COAST"),
                    ("adventour_orlando_labels.json", "ORLANDO")):
    data = load(fname)
    rows = enrich(data["labels"])
    print(f"\n{'='*66}\n{name}  —  {len(rows)} labelled places found in the index\n{'='*66}")

    print("  labels:", ", ".join(f"{k} {v}" for k, v in Counter(r["label"] for r in rows).most_common()))

    # --- junk filter, as shipped -------------------------------------------
    truth_junk = [r for r in rows if r["label"] == "junk"]
    caught = [r for r in truth_junk if r["tier"] != "KEEP"]
    fp = [r for r in rows if r["tier"] != "KEEP" and r["label"] in GOOD]
    print(f"\n  junk filter: caught {len(caught)}/{len(truth_junk)} junk"
          f" ({100.0*len(caught)/max(len(truth_junk),1):.0f}%), "
          f"false positives {len(fp)}")
    for r in fp:
        print(f"    !! dropped a {r['label']}: {r['name'][:44]}")

    # --- chain classifier ---------------------------------------------------
    called = [r for r in rows if r["label"] == "chain"]
    right = [r for r in called if r["chain_class"] == "chain"]
    print(f"  chain classifier: {len(right)}/{len(called)} of human 'chain' calls matched")

    # --- the Gate 8 signals -------------------------------------------------
    contrast = [r for r in rows if r["label"] in ("gem", "generic", "not_worth", "junk")]
    for r in contrast:
        r["y"] = 1 if r["label"] == "gem" else 0
    if len({r["y"] for r in contrast}) == 2:
        print(f"\n  authenticity signals (gem vs generic/not_worth/junk, n={len(contrast)}):")
        for label, fn in (
            ("Overture confidence", lambda r: float(r["confidence"] or 0)),
            ("has socials", lambda r: 1 if r["socials"] else 0),
            ("has website", lambda r: 1 if r["websites"] else 0),
            ("H3 cell density", lambda r: -math.log1p(r["cell_density"] or 0)),
            ("our authenticity score", lambda r: float(r["authenticity"] or 0)),
        ):
            print(f"    {label:<26}AUC {auc([(fn(r), r['y']) for r in contrast]):.3f}")

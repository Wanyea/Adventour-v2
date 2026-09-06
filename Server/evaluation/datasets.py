"""Immutable human answers joined to the current index, with explicit provenance."""

import json
import hashlib
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

DSN = os.environ.get("ADVENTOUR_PG_DSN", "host=localhost port=5432 user=postgres dbname=adventour")
QA = Path(__file__).resolve().parent.parent / "data_pipeline" / "qa"
REGISTRY = Path(__file__).with_name("label_sets.json")
GOOD = {"gem", "solid"}
BAD = {"junk", "not_worth", "trap"}
JUDGED = GOOD | BAD | {"generic", "chain"}


def registry():
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def metadata(metro):
    data = registry()
    sets = [s for s in data["sets"] if s["metro"] == metro]
    populations = {s["sampling_population"] for s in sets}
    return {
        "sets": [s["id"] for s in sets],
        "source_hashes": {s["id"]: hashlib.sha256((REGISTRY.parent / s["file"]).read_bytes()).hexdigest()
                          for s in sets},
        "sampling_population": next(iter(populations)) if len(populations) == 1 else "mixed",
        "reviewers": sorted({s["reviewer_id"] for s in sets}),
        "held_out": bool(sets) and all(s["role"] == "holdout" for s in sets)
        and not any(metro in used for used in data["fitted_on"].values()),
        "fitted_on": {c: metro in used for c, used in data["fitted_on"].items()},
    }


def _index_rows(ids):
    with psycopg2.connect(DSN) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT original.id, p.name, p.basic_category, p.taxonomy_bucket, p.chain_class,
                   p.tier, p.tier_reason, p.confidence, p.authenticity, p.websites,
                   p.socials, p.postcode, p.metro,
                   COALESCE(p.canonical_id, p.id) AS entity_id, p.cluster_size,
                   (SELECT count(*) FROM places q
                    WHERE q.h3_r8 = p.h3_r8 AND q.tier='KEEP') AS cell_density
            FROM places original
            JOIN places p ON p.id = COALESCE(original.canonical_id, original.id)
            WHERE original.id = ANY(%s)
        """, (list(ids),))
        return {r["id"]: dict(r) for r in cur.fetchall()}


def load(metro):
    """Return observations, preserving reviewer, original sample and source IDs."""
    answers, freeform = [], {"responses": []}
    for entry in registry()["sets"]:
        if entry["metro"] != metro:
            continue
        path = REGISTRY.parent / entry["file"]
        data = json.loads(path.read_text(encoding="utf-8"))
        freeform["responses"].append(data.get("freeform", {}))
        answers.extend({**r, "_set": entry["id"], "_reviewer": entry["reviewer_id"]}
                       for r in data.get("labels", []) if r.get("label")
                       and r.get("metro", metro) == metro)
    idx = _index_rows(r["id"] for r in answers)
    rows = []
    for answer in answers:
        hit = idx.get(answer["id"])
        rows.append({**answer, **(hit or {}), "_missing_from_index": hit is None})
    freeform["missing"] = ", ".join(f.get("missing", "") for f in freeform["responses"])
    return rows, freeform


def load_all():
    return {m: load(m) for m in available_metros()}


def in_sample(component, metro):
    return metro in registry()["fitted_on"].get(component, [])


def available_metros():
    return sorted({s["metro"] for s in registry()["sets"]})

"""Label sets joined to the live index, split by metro.

The central idea of Scope C, and the reason it exists: **every component declares
which metro it was fitted on.** Gate 12 happened because the authenticity score
was tuned on Palm Coast and then reported at AUC 0.954 against those same labels.
Out of sample it was 0.639. A number measured on the data it was fitted to is not
evidence, and the harness must be structurally unable to present it as such.
"""

import json
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

DSN = os.environ.get("ADVENTOUR_PG_DSN", "host=localhost port=5432 user=postgres dbname=adventour")
QA = Path(__file__).resolve().parent.parent / "data_pipeline" / "qa"

LABEL_FILES = {
    "palm_coast": "adventour_palm_coast_labels.json",
    "orlando": "adventour_orlando_labels.json",
}

# Which metro's labels each component was built against. Anything measured on its
# own fitting metro is reported as IN-SAMPLE and excluded from the headline.
FITTED_ON = {
    "junk_filter": "palm_coast",
    "authenticity": "palm_coast",
    "chain_classifier": None,      # derived from statewide name frequency, not labels
    "tag_mapping": None,           # asserted against category semantics, not labels
}

GOOD = {"gem", "solid"}
BAD = {"junk", "not_worth"}
# 'unknown' means the labeller could not judge -- not a negative. Excluding it is
# required for honesty: 30 of Orlando's 137 were unknown.
JUDGED = {"gem", "solid", "generic", "not_worth", "junk", "chain", "trap"}


def _index_rows(ids):
    with psycopg2.connect(DSN) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, name, basic_category, taxonomy_bucket, chain_class, tier, tier_reason,
                   confidence, authenticity, websites, socials, postcode, metro,
                   COALESCE(canonical_id, id) AS entity_id, cluster_size,
                   (SELECT count(*) FROM places q WHERE q.h3_r8 = p.h3_r8 AND q.tier='KEEP')
                       AS cell_density
            FROM places p WHERE id = ANY(%s)
            """,
            (list(ids),),
        )
        return {r["id"]: dict(r) for r in cur.fetchall()}


def load(metro):
    """Return labelled rows joined to the index, plus the freeform answers."""
    path = QA / LABEL_FILES[metro]
    if not path.exists():
        return [], {}
    data = json.loads(path.read_text(encoding="utf-8"))
    labels = [r for r in data.get("labels", []) if r.get("label")]
    idx = _index_rows(r["id"] for r in labels)

    rows = []
    for r in labels:
        hit = idx.get(r["id"])
        if not hit:
            # Dropped by a re-ingest, or merged away by dedup. Not an error, but
            # it must not silently shrink the denominator without being visible.
            rows.append({**r, "_missing_from_index": True})
            continue
        rows.append({**r, **hit, "_missing_from_index": False})
    return rows, data.get("freeform", {})


def load_all():
    return {m: load(m) for m in LABEL_FILES}


def in_sample(component, metro):
    return FITTED_ON.get(component) == metro


def available_metros():
    return [m for m in LABEL_FILES if (QA / LABEL_FILES[m]).exists()]

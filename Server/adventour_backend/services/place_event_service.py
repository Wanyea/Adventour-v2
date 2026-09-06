"""Record swipe feedback against the Postgres index.

Replaces the legacy `/api/events` path, which resolved `place_id` against an
integer-keyed `place` table that this architecture no longer uses. Nothing here
adapts to that table.

Every event carries the score the recommender showed at the time. Gate 8 found
the authenticity score is a quality floor but not a ranker -- 490 places share a
single value -- and behavioural data is the only way to break those ties. That
only works if we know what the model believed when the card was shown, so the
snapshot is written at event time and never back-filled.
"""

import os

from sqlalchemy import text

VALID_EVENT_TYPES = {
    "impression", "accept", "reject", "navigate",
    "arrival", "rate", "save", "share", "closed_report",
}

INSERT = text(
    """
    INSERT INTO place_event
        (user_id, entity_id, record_id, event_type, event_value,
         context, metro, score_snapshot, explanation_snapshot)
    VALUES
        (:user_id, :entity_id, :record_id, :event_type, :event_value,
         :context, :metro, :score, :explanation)
    RETURNING id, occurred_at
    """
)

# Resolve whatever id the client sent to a canonical entity. The app may send
# either the entity id or the specific record id it was dealt.
LOOKUP = text(
    """
    SELECT COALESCE(canonical_id, id) AS entity_id, id AS record_id,
           metro, authenticity, authenticity_why
    FROM places
    WHERE id = :pid OR canonical_id = :pid
    ORDER BY (id = :pid) DESC
    LIMIT 1
    """
)

SUPPRESS = text(
    """
    INSERT INTO suppressed_place (google_place_id, entity_id, source)
    VALUES (:gid, :entity_id, 'user_report')
    ON CONFLICT (google_place_id) DO NOTHING
    """
)


def is_enabled():
    return os.getenv("ADVENTOUR_USE_LOCAL_INDEX", "").lower() in ("1", "true", "yes")


def record(db, user_id, place_id, event_type, event_value=None, context=None):
    """Record one interaction. Returns the stored row, or raises ValueError."""
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(
            f"unknown event_type {event_type!r}; expected one of {sorted(VALID_EVENT_TYPES)}"
        )
    if not place_id:
        raise ValueError("place_id is required")

    row = db.session.execute(LOOKUP, {"pid": str(place_id)}).mappings().first()
    if row is None:
        # Deliberately not an error the user sees as a failure: the index is
        # rebuilt independently of the app, so an id can legitimately go stale.
        # Log the event against the raw id rather than losing the signal.
        entity_id, record_id, metro, score, why = str(place_id), None, None, None, None
    else:
        entity_id = row["entity_id"]
        record_id = row["record_id"]
        metro = row["metro"]
        score = float(row["authenticity"]) if row["authenticity"] is not None else None
        why = row["authenticity_why"]

    stored = db.session.execute(
        INSERT,
        {
            "user_id": user_id,
            "entity_id": entity_id,
            "record_id": record_id,
            "event_type": event_type,
            "event_value": event_value,
            "context": context,
            "metro": metro,
            "score": score,
            "explanation": why,
        },
    ).mappings().first()

    # A user saying "this was closed" is unambiguously our own data -- no
    # provider licensing question attached. See brief sec.10b.
    if event_type == "closed_report":
        db.session.execute(SUPPRESS, {"gid": f"adventour:{entity_id}", "entity_id": entity_id})

    db.session.commit()
    return {
        "id": stored["id"],
        "entity_id": entity_id,
        "event_type": event_type,
        "score_snapshot": score,
        "occurred_at": stored["occurred_at"].isoformat(),
    }


def summary(db, user_id):
    """Counts by event type -- used to confirm feedback is actually landing."""
    rows = db.session.execute(
        text(
            """SELECT event_type, count(*) AS n FROM place_event
               WHERE user_id = :uid GROUP BY 1 ORDER BY 2 DESC"""
        ),
        {"uid": user_id},
    ).mappings().all()
    return {r["event_type"]: r["n"] for r in rows}

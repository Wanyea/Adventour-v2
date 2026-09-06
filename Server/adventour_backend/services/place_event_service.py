"""Record owned interactions against the exact serving decision, without committing callers."""

import json

from sqlalchemy import text

from . import decision_service

VALID_EVENT_TYPES = {"impression", "accept", "reject", "navigate", "arrival", "rate", "save", "share", "closed_report"}


def record(db, user_id, place_id, event_type, event_value=None, context=None,
           decision_id=None, test_activity=False):
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError("Unknown event type.")
    decision = decision_service.get(db, user_id, decision_id, place_id, lock=True)
    payload = decision["payload"]
    if event_type in {"navigate", "arrival", "rate", "save", "share"} and decision["verdict"] != "accept" \
            and payload.get("snapshot_origin") != "legacy_unsnapshotted":
        raise ValueError("Accept the place before recording this action.")
    if event_type in {"accept", "reject"}:
        if decision["verdict"] and decision["verdict"] != event_type:
            raise ValueError("This card already has a different verdict.")
        db.session.execute(text("UPDATE recommendation_decision SET verdict=:v WHERE id=:id"),
                           {"v": event_type, "id": decision_id})
    if event_type == "rate" and (type(event_value) is not int or not 1 <= event_value <= 5):
        raise ValueError("Rating must be an integer between 1 and 5.")
    # Never persist arbitrary client metadata or provider display fields.
    params = {"uid": user_id, "entity": decision["entity_id"], "record": decision["record_id"],
              "event": event_type, "value": event_value if event_type == "rate" else None,
              "context": "adventour" if context == "adventour" else "solo",
              "metro": decision["metro"], "score": payload["score"],
              "why": payload.get("explanation"), "components": json.dumps(payload.get("score_components")),
              "decision": decision_id, "test": decision["test_activity"] or test_activity}
    row = db.session.execute(text("""INSERT INTO place_event
        (user_id,entity_id,record_id,event_type,event_value,context,metro,score_snapshot,
         explanation_snapshot,components_snapshot,decision_id,test_activity)
        VALUES(:uid,:entity,:record,:event,:value,:context,:metro,:score,:why,
               CAST(:components AS jsonb),:decision,:test)
        ON CONFLICT(user_id,decision_id,event_type) WHERE decision_id IS NOT NULL
        DO NOTHING RETURNING id,occurred_at"""), params).mappings().first()
    if row is None:
        row = db.session.execute(text("""SELECT id,occurred_at FROM place_event
            WHERE user_id=:uid AND decision_id=:decision AND event_type=:event"""), params).mappings().one()
    return {"id": row["id"], "entity_id": decision["entity_id"], "event_type": event_type,
            "score_snapshot": payload["score"], "decision_id": decision_id,
            "occurred_at": row["occurred_at"].isoformat()}


def summary(db, user_id):
    rows = db.session.execute(text("""SELECT event_type,count(*) AS n FROM place_event
        WHERE user_id=:uid GROUP BY 1 ORDER BY 2 DESC"""), {"uid": user_id}).mappings().all()
    return {r["event_type"]: r["n"] for r in rows}

"""Owned, immutable serving snapshots. A client cannot invent its score history."""

import json
import uuid

from sqlalchemy import text


def attach(db, user_id, recommendations, test_activity=False):
    for rank, place in enumerate(recommendations, 1):
        decision_id = str(uuid.uuid4())
        payload = {**place, "rank": rank}
        db.session.execute(text("""INSERT INTO recommendation_decision
            (id,user_id,entity_id,record_id,metro,payload,test_activity)
            VALUES(:id,:uid,:entity,:record,:metro,CAST(:payload AS jsonb),:test)"""),
            {"id": decision_id, "uid": user_id, "entity": place["place_id"],
             "record": place["provider_place_id"], "metro": place["metro"],
             "payload": json.dumps(payload), "test": test_activity})
        place["decision_id"] = decision_id


def get(db, user_id, decision_id, place_id=None, lock=False):
    if not decision_id:
        raise ValueError("Refresh the deck to obtain a current decision ID.")
    row = db.session.execute(text("""SELECT * FROM recommendation_decision
        WHERE id=:id AND user_id=:uid""" + (" FOR UPDATE" if lock else "")),
        {"id": decision_id, "uid": user_id}).mappings().first()
    if row is None or place_id and str(place_id) not in {row["entity_id"], row["record_id"]}:
        raise ValueError("Decision does not belong to this user and place.")
    return row


def for_stop(db, user_id, stop):
    metadata = json.loads(stop.metadata_json or "{}")
    if metadata.get("decision_id"):
        return metadata["decision_id"]
    # Existing history predates serving snapshots. Preserve it without inventing
    # the score it saw. A legacy migration has no implication for a new swipe.
    decision_id = str(uuid.uuid4())
    payload = {"score": None, "score_components": None, "explanation": None,
               "snapshot_origin": "legacy_unsnapshotted"}
    db.session.execute(text("""INSERT INTO recommendation_decision
        (id,user_id,entity_id,record_id,metro,payload,test_activity)
        VALUES(:id,:uid,:entity,:record,'unknown',CAST(:payload AS jsonb),
               COALESCE((SELECT firebase_uid LIKE 'dev-%' FROM "user" WHERE id=:uid),false))"""),
        {"id": decision_id, "uid": user_id, "entity": stop.entity_id,
         "record": stop.record_id or stop.entity_id, "payload": json.dumps(payload)})
    indexed = db.session.execute(text("""SELECT name,basic_category,canonical_lat,canonical_lon,lat,lon
        FROM places WHERE id=:record OR id=:entity ORDER BY (id=:record) DESC LIMIT 1"""),
        {"record": stop.record_id or stop.entity_id, "entity": stop.entity_id}).mappings().first()
    display = {"name": indexed["name"], "types": [indexed["basic_category"]],
               "latitude": indexed["canonical_lat"] if indexed["canonical_lat"] is not None else indexed["lat"],
               "longitude": indexed["canonical_lon"] if indexed["canonical_lon"] is not None else indexed["lon"]} if indexed else {}
    stop.metadata_json = json.dumps({"source": "legacy_session", "provider": "adventour_index",
                                    "decision_id": decision_id, "display": display})
    return decision_id

"""Transparent personal fit, separate from the index's structural evidence.

Policy weights are declared in docs/phase2-discovery.md; not fitted quality claims.
All feedback belongs to the requesting user. No provider access or writes here.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

MODEL = "personal_v1"


def context(db, user_id, now=None):
    now = now or datetime.now(timezone.utc)
    preferences = db.session.execute(text('SELECT preferences FROM "user" WHERE id=:uid'),
                                     {"uid": user_id}).scalar() or ""
    rows = db.session.execute(text("""SELECT e.entity_id,e.event_type,e.event_value,e.occurred_at,
        d.payload->'tag_groups' AS tag_groups
        FROM place_event e LEFT JOIN recommendation_decision d ON d.id=e.decision_id
        WHERE e.user_id=:uid AND e.occurred_at >= :since
          AND e.event_type IN ('impression','accept','reject','arrival','rate')
          AND (NOT e.test_activity OR EXISTS
               (SELECT 1 FROM "user" u WHERE u.id=:uid AND u.firebase_uid LIKE 'dev-%'))
        ORDER BY e.occurred_at DESC,e.id DESC"""),
        {"uid": user_id, "since": now - timedelta(days=90)}).mappings().all()
    return from_history(preferences.split(','), rows, now)


def from_history(preferences, rows, now):
    hidden, impressed, latest = set(), set(), {}
    for row in rows:
        entity, kind = row['entity_id'], row['event_type']
        age = now - row['occurred_at']
        if age < timedelta(0):
            continue
        if kind == 'reject' and age < timedelta(days=30) or \
                kind in {'accept', 'arrival', 'rate'} and age < timedelta(days=7):
            hidden.add(entity)
        if kind == 'impression' and age < timedelta(days=1):
            impressed.add(entity)
        if kind in {'accept', 'reject', 'rate'}:
            prior = latest.get(entity)
            # Rows are newest first: a rating replaces its earlier acceptance,
            # but must not override a later rejection on a different visit.
            if prior is None:
                latest[entity] = row
    votes = defaultdict(list)
    for row in latest.values():
        value = ((float(row['event_value']) - 3) / 2 if row['event_type'] == 'rate'
                 else .5 if row['event_type'] == 'accept' else -1)
        for tag in set(row['tag_groups'] or []):
            votes[tag].append(value)
    return {'preferences': set(preferences) - {''}, 'hidden': hidden, 'impressed': impressed,
            'feedback': {tag: sum(values) / (len(values) + 3) for tag, values in votes.items()},
            'counts': {tag: len(values) for tag, values in votes.items()}}


def score(place, history, radius, chain_class):
    tags = set(place['tag_groups'])
    matched = sorted(tags & history['preferences'])
    feedback = sum(history['feedback'].get(tag, 0) for tag in tags) / max(1, len(tags))
    parts = {
        'interests': .5 if matched else 0.0,
        'feedback': round(.2 * feedback, 6),
        'distance': round(.2 * max(0, 1 - place['distance_meters'] / radius), 6),
        'local_policy': .1 if chain_class in {'independent', 'regional'} else 0.0,
        'repeat': -.1 if place['place_id'] in history['impressed'] else 0.0,
    }
    count = max((history['counts'].get(tag, 0) for tag in tags), default=0)
    place.update({
        'model': MODEL, 'score': round(sum(parts.values()), 6), 'ranking_components': parts,
        'matched_interests': matched, 'feedback_count': count,
        'availability': 'unknown',
        'explanation': ('Matches your ' + ', '.join(t.replace('_', ' ') for t in matched) + ' interests. '
                        if matched else 'No saved-interest match. ') +
                       ('Your past choices in these categories affect this order. ' if count else
                        'No past category feedback yet. ') +
                       'Distance and local-first policy also affect the order. Hours and public access are unverified.',
    })
    return place

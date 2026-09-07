"""Versioned optional answers; missingness is never a negative taste label."""
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import uuid
from zoneinfo import ZoneInfo

from sqlalchemy import text
from . import pilot_service as pilot

REASONS = {'taste', 'setting', 'distance', 'timing', 'price_booking', 'familiar',
           'unclear', 'facts', 'other'}
PROBLEMS = {'location', 'date_time', 'closed_cancelled', 'sold_out_access',
            'broken_link', 'category_description', 'other'}
SIGNALS = {'view', 'interaction', 'open_source', 'navigate', 'explanation_opened'}


def client_time(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed
    except (ValueError, TypeError, AttributeError):
        raise ValueError('A timezone-aware occurred_at is required') from None


def invitation(db, row, source, now=None):
    now = now or datetime.now(timezone.utc)
    prior = db.session.execute(text('SELECT * FROM pilot_invitation WHERE decision_id=:d AND source=:s'),
                               {'d': row['id'], 's': source}).mappings().first()
    if prior:
        return dict(prior)
    if source == 'sampled':
        zone = ZoneInfo(row['context']['timezone'])
        day = now.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0)
        counts = db.session.execute(text("""SELECT count(*) FILTER(WHERE i.offered_at>=:day) AS daily,
            count(*) FILTER(WHERE r.session_id=:session) AS session,
            max(i.offered_at) AS last FROM pilot_invitation i
            JOIN pilot_decision d ON d.id=i.decision_id JOIN pilot_request r ON r.id=d.request_id
            WHERE r.user_id=:user AND r.pilot_id=:pilot AND i.source='sampled'"""),
            {'day': day, 'session': row['session_id'], 'user': row['user_id'], 'pilot': row['pilot_id']}).mappings().one()
        if counts['daily'] >= 3 or counts['session'] >= 2 or \
                counts['last'] and now - counts['last'] < timedelta(minutes=10):
            return None
        if secrets.randbelow(4) != 0:
            return None
    interests = [i for i in row['context'].get('interests', []) if i]
    selected = row['context'].get('tag_group')
    if selected and selected != 'all':
        interests = [selected]
    total = db.session.execute(text("""SELECT count(*) FROM pilot_invitation i
        JOIN pilot_decision d ON d.id=i.decision_id JOIN pilot_request r ON r.id=d.request_id
        WHERE r.user_id=:u AND r.pilot_id=:p"""),
        {'u': row['user_id'], 'p': row['pilot_id']}).scalar()
    block = int.from_bytes(hashlib.sha256(f"{row['pilot_id']}:{row['user_id']}:{total // 2}".encode()).digest()[:4], 'big') % 2
    question = 'relevance_v1' if interests and total % 2 == block else 'appeal_v1'
    interest = secrets.choice(interests) if question == 'relevance_v1' else None
    ident = str(uuid.uuid4())
    result = db.session.execute(text("""INSERT INTO pilot_invitation
        (id,decision_id,source,question,interest,probability,offered_at)
        VALUES(:id,:d,:s,:q,:i,:p,:now) RETURNING *"""),
        {'id': ident, 'd': row['id'], 's': source, 'q': question, 'i': interest,
         'p': .25 if source == 'sampled' else 1., 'now': now}).mappings().one()
    return dict(result)


def signal(db, row, data):
    kind = data.get('kind')
    if kind not in SIGNALS:
        raise ValueError('Unknown pilot signal')
    happened = client_time(data.get('occurred_at'))
    duration = data.get('duration_ms', 0)
    if type(duration) is not int or not 0 <= duration <= 86400000:
        raise ValueError('Invalid exposure duration')
    if kind == 'view' and duration < 1000:
        raise ValueError('Qualifying view requires one continuous second')
    metadata = {'schema_version': pilot.VERSION, 'duration_ms': duration,
                'visibility_rule': 'half_card_foreground_continuous_1s_v1',
                'clock_skew_seconds': round((datetime.now(timezone.utc) - happened).total_seconds(), 3)}
    prior = db.session.execute(text('SELECT * FROM pilot_signal WHERE decision_id=:d AND kind=:k'),
                               {'d': row['id'], 'k': kind}).mappings().first()
    if prior:
        inv = db.session.execute(text("SELECT * FROM pilot_invitation WHERE decision_id=:d AND source='sampled'"),
                                 {'d': row['id']}).mappings().first()
        return {'id': prior['id'], 'invitation': dict(inv) if inv else None}
    ident = pilot.uid(data.get('id'))
    inv = None
    # Only the first qualifying exposure can sample; interaction then view is not two chances.
    exposed = db.session.execute(text("SELECT 1 FROM pilot_signal WHERE decision_id=:d AND kind IN ('view','interaction')"),
                                {'d': row['id']}).first()
    if kind in {'view', 'interaction'} and not exposed:
        inv = invitation(db, row, 'sampled')
        metadata['sample_probability'] = .25
        metadata['invitation_created'] = inv is not None
    db.session.execute(text("""INSERT INTO pilot_signal(id,decision_id,kind,occurred_at,payload)
        VALUES(:id,:d,:k,:at,CAST(:p AS jsonb))"""),
        {'id': ident, 'd': row['id'], 'k': kind, 'at': happened, 'p': pilot.encode(metadata)})
    return {'id': ident, 'invitation': inv}


def answer(db, row, data):
    ident, invitation_id = pilot.uid(data.get('id')), pilot.uid(data.get('invitation_id'))
    inv = db.session.execute(text('SELECT * FROM pilot_invitation WHERE id=:id AND decision_id=:d FOR UPDATE'),
                             {'id': invitation_id, 'd': row['id']}).mappings().first()
    if inv is None:
        raise ValueError('Invitation does not belong to decision')
    kind, value = data.get('answer_kind'), data.get('value')
    reason, problem, note = data.get('reason'), data.get('problem'), data.get('note')
    if kind not in {'rated', 'unknown'} or kind == 'rated' and (type(value) is not int or not 0 <= value <= 4) \
            or kind == 'unknown' and value is not None:
        raise ValueError('Expected rated 0–4 or explicit unknown')
    if reason is not None and reason not in REASONS or problem is not None and problem not in PROBLEMS:
        raise ValueError('Unknown feedback reason/problem')
    if problem and reason != 'facts':
        raise ValueError('A problem subtype requires the facts reason')
    if note is not None and (not isinstance(note, str) or len(note) > 280):
        raise ValueError('Optional note must be at most 280 characters')
    duration = data.get('duration_ms')
    if type(duration) is not int or not 0 <= duration <= 86400000:
        raise ValueError('Invalid answer duration')
    happened = client_time(data.get('occurred_at'))
    supersedes = pilot.uid(data['supersedes']) if data.get('supersedes') else None
    fields = {'invitation_id': invitation_id, 'answer_kind': kind, 'value': value,
              'reason': reason, 'problem': problem, 'note': note, 'duration_ms': duration,
              'occurred_at': happened, 'supersedes': supersedes}
    existing = db.session.execute(text('SELECT * FROM pilot_feedback WHERE id=:id'), {'id': ident}).mappings().first()
    if existing:
        if any(existing[k] != v for k, v in fields.items()):
            raise ValueError('Retry differs from the original answer')
        return {'id': ident, 'status': 'saved'}
    if inv['status'] == 'skipped':
        raise ValueError('Invitation was skipped')
    if supersedes:
        previous = db.session.execute(text('SELECT id FROM pilot_feedback WHERE id=:id AND invitation_id=:i'),
                                      {'id': supersedes, 'i': invitation_id}).first()
        successor = db.session.execute(text('SELECT 1 FROM pilot_feedback WHERE supersedes=:id'), {'id': supersedes}).first()
        if not previous or successor:
            raise ValueError('Correction must replace the latest answer')
    elif inv['status'] == 'answered':
        raise ValueError('Use the original id for a retry or supersedes for a correction')
    db.session.execute(text("""INSERT INTO pilot_feedback
        (id,invitation_id,answer_kind,value,reason,problem,note,duration_ms,occurred_at,supersedes)
        VALUES(:id,:invitation_id,:answer_kind,:value,:reason,:problem,:note,:duration_ms,:occurred_at,:supersedes)"""),
        {'id': ident, **fields})
    db.session.execute(text("UPDATE pilot_invitation SET status='answered' WHERE id=:id"), {'id': invitation_id})
    return {'id': ident, 'status': 'saved'}

"""Pilot-only enrollment, immutable served facts, and owned replay inputs.

Client build headers express context, never replace authentication/enrollment.
No provider content enters this service. All snapshots are built by server code.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import g, request
from sqlalchemy import text

VERSION = 'pilot_v1'


def uid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Expected a UUID') from None


def encode(value):
    def convert(item):
        if isinstance(item, set):
            return sorted(item)
        if isinstance(item, datetime):
            return item.isoformat()
        raise TypeError(type(item).__name__)
    return json.dumps(value, default=convert, allow_nan=False)


def enrollment(db, user_id):
    pilot = request.headers.get('X-Adventour-Pilot', '')
    build = request.headers.get('X-Adventour-Build', '')
    # A standard request exits without even reading study tables.
    if not pilot or not build:
        return None
    return db.session.execute(text("""SELECT e.* FROM pilot_enrollment e
        JOIN pilot_build b ON b.pilot_id=e.pilot_id
        WHERE e.pilot_id=:pilot AND e.user_id=:user AND e.active
          AND b.build_id=:build AND b.active"""),
        {'pilot': pilot, 'user': user_id, 'build': build}).mappings().first()


def begin(db, user_id, context):
    member = enrollment(db, user_id)
    if member is None:
        return None
    session = uid(request.headers.get('X-Adventour-Session'))
    zone = request.headers.get('X-Adventour-Timezone', 'UTC')
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError('Invalid pilot timezone') from None
    # Context is constructed by the route, never arbitrary client metadata.
    context = {**context, 'timezone': zone, 'schema_version': VERSION,
               'backend_release': os.getenv('PILOT_BACKEND_RELEASE', 'unversioned-development'),
               'started_at': datetime.now(timezone.utc).isoformat()}
    ident = str(uuid.uuid4())
    db.session.execute(text("""INSERT INTO pilot_request
        (id,pilot_id,user_id,session_id,build_id,schema_version,test_activity,context)
        VALUES(:id,:pilot,:user,:session,:build,:version,:test,CAST(:context AS jsonb))"""),
        {'id': ident, 'pilot': member['pilot_id'], 'user': user_id, 'session': session,
         'build': request.headers['X-Adventour-Build'], 'version': VERSION,
         'test': bool(getattr(g, 'test_activity', False)), 'context': encode(context)})
    return {'id': ident, 'trace': {}}


def attach(db, capture, items, kind):
    if capture is None:
        return
    for rank, item in enumerate(items, 1):
        ident = str(uuid.uuid4())
        key = item['place_id'] if kind == 'place' else item['source_id'] + '/' + item['occurrence_id']
        db.session.execute(text("""INSERT INTO pilot_decision
            (id,request_id,item_kind,item_key,rank,core_decision_id,payload)
            VALUES(:id,:request,:kind,:key,:rank,:core,CAST(:payload AS jsonb))"""),
            {'id': ident, 'request': capture['id'], 'kind': kind, 'key': key,
             'rank': rank, 'core': item.get('decision_id'), 'payload': encode(item)})
        item['pilot_decision_id'] = ident
    db.session.execute(text('UPDATE pilot_request SET trace=CAST(:trace AS jsonb) WHERE id=:id'),
                       {'id': capture['id'], 'trace': encode(capture['trace'])})


def decision(db, user_id, ident):
    member = enrollment(db, user_id)
    if member is None:
        raise PermissionError('Pilot enrollment and approved pilot build required')
    # Serialize participant sampling/caps and concurrent uploads.
    db.session.execute(text('SELECT 1 FROM pilot_enrollment WHERE pilot_id=:p AND user_id=:u FOR UPDATE'),
                       {'p': member['pilot_id'], 'u': user_id})
    row = db.session.execute(text("""SELECT d.*,r.user_id,r.pilot_id,r.session_id,
        r.context,r.build_id FROM pilot_decision d JOIN pilot_request r ON r.id=d.request_id
        WHERE d.id=:id AND r.user_id=:user AND r.pilot_id=:pilot"""),
        {'id': uid(ident), 'user': user_id, 'pilot': member['pilot_id']}).mappings().first()
    if row is None:
        raise PermissionError('Decision does not belong to this participant and study')
    return row


def source_fingerprint():
    # Content hashes identify deployed rules even in an uncommitted dev build.
    root = Path(__file__).parent
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in ('personal_ranking_service.py', 'local_index_service.py',
                         'tag_group_service.py', 'local_event_service.py')}

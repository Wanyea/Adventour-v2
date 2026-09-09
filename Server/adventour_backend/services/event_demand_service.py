"""Durable, coalesced demand queue for arbitrary event locations.

The queue contains geography and scheduling state only.  Acquisition is performed
by a worker after a short transactional claim; HTTP requests never fetch sources.
"""
from datetime import datetime, timedelta, timezone
import uuid

import h3
from sqlalchemy import text

DDL = """
CREATE TABLE IF NOT EXISTS event_demand (
    work_key text PRIMARY KEY, h3_r8 text NOT NULL, latitude double precision NOT NULL,
    longitude double precision NOT NULL, radius_meters integer NOT NULL,
    window_start date NOT NULL, window_days integer NOT NULL DEFAULT 14,
    state text NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','running','backoff','failed')),
    due_at timestamptz NOT NULL, attempts integer NOT NULL DEFAULT 0,
    lease_expires_at timestamptz, fencing_token uuid, last_error text,
    created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
    UNIQUE(h3_r8, window_start, window_days)
);
CREATE INDEX IF NOT EXISTS event_demand_due_idx ON event_demand(state,due_at);
"""


def work_key(cell, start, days):
    return f"events:{cell}:{start.isoformat()}:{days}"


def enqueue(db, latitude, longitude, radius_meters=50000, now=None):
    now = now or datetime.now(timezone.utc)
    cell = h3.latlng_to_cell(latitude, longitude, 8)
    start = now.date()
    key = work_key(cell, start, 14)
    db.session.execute(text("""INSERT INTO event_demand
        (work_key,h3_r8,latitude,longitude,radius_meters,window_start,window_days,due_at,created_at,updated_at)
        VALUES(:key,:cell,:lat,:lon,:radius,:start,14,:now,:now,:now)
        ON CONFLICT(h3_r8,window_start,window_days) DO UPDATE SET
          latitude=EXCLUDED.latitude,longitude=EXCLUDED.longitude,
          radius_meters=GREATEST(event_demand.radius_meters,EXCLUDED.radius_meters),
          updated_at=EXCLUDED.updated_at,
          state=CASE WHEN event_demand.state='failed' THEN 'queued' ELSE event_demand.state END"""),
        {'key': key, 'cell': cell, 'lat': latitude, 'lon': longitude, 'radius': int(radius_meters),
         'start': start, 'now': now})
    return key


def state(db, latitude, longitude, now=None):
    now = now or datetime.now(timezone.utc)
    cell = h3.latlng_to_cell(latitude, longitude, 8)
    row = db.session.execute(text("""SELECT state,due_at,last_error FROM event_demand
        WHERE h3_r8=:cell AND window_start=:start AND window_days=14"""),
        {'cell': cell, 'start': now.date()}).mappings().first()
    if row is None:
        return {'acquisition_state': 'idle', 'next_check_at': None, 'reason': None}
    return {'acquisition_state': row['state'], 'next_check_at': row['due_at'].isoformat(),
            'reason': row['last_error']}


def claim(db, now=None, lease_seconds=300):
    now = now or datetime.now(timezone.utc)
    token = uuid.uuid4()
    row = db.session.execute(text("""SELECT work_key FROM event_demand
      WHERE (state IN ('queued','backoff') AND due_at<=:now)
         OR (state='running' AND lease_expires_at<:now)
      ORDER BY due_at,created_at FOR UPDATE SKIP LOCKED LIMIT 1"""), {'now': now}).first()
    if not row:
        return None
    updated = db.session.execute(text("""UPDATE event_demand SET state='running',attempts=attempts+1,
      lease_expires_at=:lease,fencing_token=:token,updated_at=:now WHERE work_key=:key
      RETURNING *"""), {'key': row[0], 'lease': now+timedelta(seconds=lease_seconds),
                          'token': token, 'now': now}).mappings().one()
    return dict(updated)


def finish(db, work_key_value, fencing_token, *, success, error=None, now=None):
    now = now or datetime.now(timezone.utc)
    state_value = 'queued' if success else 'backoff'
    db.session.execute(text("""UPDATE event_demand SET state=:state,
      due_at=:due,last_error=:error,lease_expires_at=NULL,fencing_token=NULL,updated_at=:now
      WHERE work_key=:key AND state='running' AND fencing_token=:token"""),
        {'state': state_value, 'due': now + (timedelta(hours=6) if success else timedelta(minutes=5)),
         'error': type(error).__name__ if error else None, 'now': now,
         'key': work_key_value, 'token': fencing_token})

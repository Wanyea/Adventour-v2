"""Owned regional event index with fail-closed query-time freshness."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import text

from .local_index_service import _cells_for

SOURCES = Path(__file__).resolve().parents[2] / 'data_pipeline' / 'event_sources.json'
DDL = """
CREATE TABLE IF NOT EXISTS event_source (
    id text PRIMARY KEY, name text NOT NULL, metro text NOT NULL,
    permission_url text NOT NULL, last_success timestamptz, last_attempt timestamptz,
    last_error text, report jsonb
);
CREATE TABLE IF NOT EXISTS local_event (
    source_id text NOT NULL REFERENCES event_source(id), occurrence_id text NOT NULL,
    series_id text NOT NULL, title text NOT NULL, starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL, timezone text NOT NULL, metro text NOT NULL,
    category text NOT NULL, source_url text NOT NULL, official_url text NOT NULL,
    access_note text NOT NULL, access_url text NOT NULL, venue_name text NOT NULL,
    entity_id text, latitude double precision NOT NULL, longitude double precision NOT NULL,
    h3_r8 text NOT NULL, verified_at timestamptz NOT NULL, expires_at timestamptz NOT NULL,
    PRIMARY KEY(source_id,occurrence_id), CHECK(ends_at>starts_at),
    CHECK(expires_at<=ends_at AND expires_at<=verified_at+interval '24 hours')
);
CREATE INDEX IF NOT EXISTS local_event_region_time_idx ON local_event(h3_r8,starts_at);
"""


def sources():
    return json.loads(SOURCES.read_text(encoding='utf-8'))


def replace_window(db, source_id, config, records, report, now=None):
    now = now or datetime.now(timezone.utc)
    start = datetime.fromisoformat(report['window_start']).replace(tzinfo=ZoneInfo('America/New_York'))
    end = start + timedelta(days=report['window_days'])
    db.session.execute(text("""INSERT INTO event_source(id,name,metro,permission_url,last_attempt,last_success,report)
        VALUES(:id,:name,:metro,:permission,:now,:now,CAST(:report AS jsonb))
        ON CONFLICT(id) DO UPDATE SET last_attempt=:now,last_success=:now,last_error=NULL,
        report=CAST(:report AS jsonb),permission_url=:permission"""),
        {'id': source_id, 'name': config['name'], 'metro': config['metro'],
         'permission': config['permission_url'], 'now': now, 'report': json.dumps(report)})
    # Atomic full-window replacement also removes disappeared/cancelled occurrences.
    db.session.execute(text("""DELETE FROM local_event WHERE source_id=:source
        AND (starts_at>=:start AND starts_at<:end OR ends_at<=:now)"""),
        {'source': source_id, 'start': start, 'end': end, 'now': now})
    for record in records:
        columns = list(record)
        db.session.execute(text('INSERT INTO local_event (' + ','.join(columns) + ') VALUES (' +
                                ','.join(':'+c for c in columns) + ') ON CONFLICT(source_id,occurrence_id) DO UPDATE SET ' +
                                ','.join(c+'=EXCLUDED.'+c for c in columns if c not in {'source_id','occurrence_id'})), record)


def listing(db, latitude, longitude, radius=16000, tag='all', now=None):
    import math
    now = now or datetime.now(timezone.utc)
    if not all(math.isfinite(v) for v in (latitude, longitude, radius)) or not \
            (-90<=latitude<=90 and -180<=longitude<=180 and 100<=radius<=50000):
        raise ValueError('Invalid event region or radius (100–50000 metres)')
    rows = db.session.execute(text("""SELECT e.*,s.name AS source_name,
        6371000*acos(least(1,greatest(-1,cos(radians(:lat))*cos(radians(latitude))*
        cos(radians(longitude)-radians(:lon))+sin(radians(:lat))*sin(radians(latitude))))) AS distance_meters
        FROM local_event e JOIN event_source s ON s.id=e.source_id
        WHERE e.h3_r8=ANY(:cells) AND e.ends_at>:now AND e.expires_at>:now
          AND e.verified_at>:oldest AND e.verified_at<=:now
          AND (:tag='all' OR e.category=:tag)
        ORDER BY starts_at,title,source_id,occurrence_id"""),
        {'lat': latitude, 'lon': longitude, 'cells': _cells_for(latitude,longitude,radius),
         'now': now, 'oldest': now-timedelta(hours=24), 'tag': tag}).mappings().all()
    events, seen = [], {}
    for row in rows:
        if row['distance_meters'] > radius:
            continue
        item = {k: v.isoformat() if isinstance(v,datetime) else v for k,v in row.items()}
        key = (row['entity_id'], row['title'].casefold(), row['starts_at'])
        if key in seen:
            seen[key]['sources'].append({'name': row['source_name'], 'url': row['source_url']})
            continue
        item['sources'] = [{'name': row['source_name'], 'url': row['source_url']}]
        seen[key] = item
        events.append(item)
    return {'events': events[:50], 'checked_at': now.isoformat(),
            'coverage_note': 'Limited calendar coverage. No results does not mean no local events.',
            'freshness_note': 'Removed after ending or 24 hours without source verification.'}

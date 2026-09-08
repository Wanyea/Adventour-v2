"""Owned regional event index with fail-closed query-time freshness."""

from datetime import datetime, time, timedelta, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import text

from .local_index_service import _cells_for
from .tag_group_service import GROUPS

SOURCES = Path(__file__).resolve().parents[2] / 'data_pipeline' / 'event_sources.json'
EVENT_COLUMNS = ('source_id', 'occurrence_id', 'series_id', 'title', 'starts_at', 'ends_at',
                 'timezone', 'metro', 'category', 'source_url', 'official_url', 'access_note',
                 'access_url', 'venue_name', 'entity_id', 'latitude', 'longitude', 'h3_r8',
                 'verified_at', 'expires_at')
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
    """Return the validated operator registry, including each stable source id."""
    from data_pipeline import event_registry
    registry = event_registry.sources(path=SOURCES)
    return event_registry.selected(registry=registry)


def _aware(value, field):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(field+' must be timezone-aware')
    return value


def _window(report, config):
    try:
        day = datetime.fromisoformat(report['window_start']).date()
        days = report['window_days']
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('Invalid event refresh window') from exc
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 31:
        raise ValueError('Invalid event refresh window')
    try:
        zone = ZoneInfo(config.get('timezone', 'America/New_York'))
    except (TypeError, ValueError) as exc:
        raise ValueError('Invalid event source timezone') from exc
    start = datetime.combine(day, time.min, tzinfo=zone)
    return start, start+timedelta(days=days), zone


def _validated_records(source_id, config, records, start, end, now):
    age = config.get('max_age_hours', 24)
    if not isinstance(age, (int, float)) or isinstance(age, bool) or not 0 < age <= 24:
        raise ValueError('Event source max_age_hours must be between zero and 24')
    expected = set(EVENT_COLUMNS)
    accepted = []
    for raw in records:
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError('Event record has unsupported or missing columns')
        if raw['source_id'] != source_id:
            raise ValueError('Event record source_id does not match refresh source')
        record = dict(raw)
        starts, ends = _aware(record['starts_at'], 'starts_at'), _aware(record['ends_at'], 'ends_at')
        verified, expires = _aware(record['verified_at'], 'verified_at'), _aware(record['expires_at'], 'expires_at')
        if not starts < ends or verified > now:
            raise ValueError('Event record has invalid time bounds')
        if not start <= starts.astimezone(start.tzinfo) < end:
            raise ValueError('Event record falls outside refresh window')
        record['expires_at'] = min(expires, ends, verified+timedelta(hours=age))
        if record['expires_at'] <= now:
            raise ValueError('Event record is already expired')
        accepted.append(record)
    return accepted


def replace_window(db, source_id, config, records, report, now=None):
    now = now or datetime.now(timezone.utc)
    _aware(now, 'now')
    start, end, _ = _window(report, config)
    records = _validated_records(source_id, config, records, start, end, now)
    stored_report = {**report, 'source_config': {'parser_version': config.get('parser_version'),
                                                   'timezone': config.get('timezone', 'America/New_York')}}
    db.session.execute(text("""INSERT INTO event_source(id,name,metro,permission_url,last_attempt,last_success,report)
        VALUES(:id,:name,:metro,:permission,:now,:now,CAST(:report AS jsonb))
        ON CONFLICT(id) DO UPDATE SET last_attempt=:now,last_success=:now,last_error=NULL,
        report=CAST(:report AS jsonb),permission_url=:permission,name=:name,metro=:metro"""),
        {'id': source_id, 'name': config['name'], 'metro': config['metro'],
         'permission': config['permission_url'], 'now': now, 'report': json.dumps(stored_report)})
    # Atomic full-window replacement also removes disappeared/cancelled occurrences.
    db.session.execute(text("""DELETE FROM local_event WHERE source_id=:source
        AND (starts_at>=:start AND starts_at<:end OR ends_at<=:now)"""),
        {'source': source_id, 'start': start, 'end': end, 'now': now})
    for record in records:
        db.session.execute(text('INSERT INTO local_event (' + ','.join(EVENT_COLUMNS) + ') VALUES (' +
                                ','.join(':'+c for c in EVENT_COLUMNS) + ') ON CONFLICT(source_id,occurrence_id) DO UPDATE SET ' +
                                ','.join(c+'=EXCLUDED.'+c for c in EVENT_COLUMNS if c not in {'source_id','occurrence_id'})), record)


def listing(db, latitude, longitude, radius=16000, tag='all', now=None):
    import math
    now = now or datetime.now(timezone.utc)
    if not all(math.isfinite(v) for v in (latitude, longitude, radius)) or not \
            (-90<=latitude<=90 and -180<=longitude<=180 and 100<=radius<=50000):
        raise ValueError('Invalid event region or radius (100–50000 metres)')
    if tag != 'all' and tag not in GROUPS:
        raise ValueError('Unknown event tag')
    rows = db.session.execute(text("""SELECT e.*,s.name AS source_name,
        6371000*acos(least(1,greatest(-1,cos(radians(:lat))*cos(radians(latitude))*
        cos(radians(longitude)-radians(:lon))+sin(radians(:lat))*sin(radians(latitude))))) AS distance_meters
        FROM local_event e JOIN event_source s ON s.id=e.source_id
        WHERE e.h3_r8=ANY(:cells) AND e.ends_at>:now AND e.expires_at>:now
          AND e.starts_at<:until
          AND e.verified_at>:oldest AND e.verified_at<=:now
          AND (:tag='all' OR e.category=:tag)
        ORDER BY starts_at,title,source_id,occurrence_id"""),
        {'lat': latitude, 'lon': longitude, 'cells': _cells_for(latitude,longitude,radius),
         'now': now, 'oldest': now-timedelta(hours=24), 'until': now+timedelta(days=14), 'tag': tag}).mappings().all()
    events, seen_entity, seen_fallback, representative_entities = [], {}, {}, {}
    rows = sorted(rows, key=lambda row: (
        row['starts_at'], ' '.join(row['title'].split()).casefold(),
        round(row['latitude'], 5), round(row['longitude'], 5),
        ' '.join(row['venue_name'].split()).casefold(),
        row['entity_id'] is None, row['entity_id'] or '', row['source_id'], row['occurrence_id']))
    for row in rows:
        if row['distance_meters'] > radius:
            continue
        item = {k: v.isoformat() if isinstance(v,datetime) else v for k,v in row.items()}
        title = ' '.join(row['title'].split()).casefold()
        fallback = (title, row['starts_at'], round(row['latitude'], 5), round(row['longitude'], 5),
                    ' '.join(row['venue_name'].split()).casefold())
        entity = (title, row['starts_at'], row['entity_id']) if row['entity_id'] else None
        prior = seen_entity.get(entity) if entity else seen_fallback.get(fallback)
        if prior is None and entity:
            candidate = seen_fallback.get(fallback)
            if candidate is not None and not representative_entities[id(candidate)]:
                prior = candidate
        if prior is not None:
            prior['sources'].append({'name': row['source_name'], 'url': row['source_url']})
            prior['sources'].sort(key=lambda source: (source['name'], source['url']))
            if entity:
                seen_entity[entity] = prior
                representative_entities[id(prior)].add(row['entity_id'])
            seen_fallback[fallback] = prior
            continue
        item['sources'] = [{'name': row['source_name'], 'url': row['source_url']}]
        if entity:
            seen_entity[entity] = item
            representative_entities[id(item)] = {row['entity_id']}
        else:
            representative_entities[id(item)] = set()
        seen_fallback.setdefault(fallback, item)
        events.append(item)
    return {'events': events[:50], 'checked_at': now.isoformat(),
            'coverage_note': 'Limited calendar coverage. No results does not mean no local events.',
            'freshness_note': 'Removed after ending or 24 hours without source verification.'}

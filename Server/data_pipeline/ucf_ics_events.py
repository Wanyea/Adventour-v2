"""Bounded adapter for UCF's documented ICS event feeds.

The feed is consumed as a factual calendar: descriptions are examined only for
access restrictions and are never returned or written to the event index.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone
import html
import re
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import h3

from data_pipeline.ucf_events import location
from data_pipeline.event_http import BoundedSession


USER_AGENT = 'Adventour/0.2 (UCF documented ICS feed consumer)'
RECURRING_PROPERTIES = {'RRULE', 'RDATE', 'EXDATE', 'RECURRENCE-ID', 'DURATION'}
REQUIRED_PROPERTIES = {'UID', 'DTSTART', 'DTEND', 'LOCATION', 'SUMMARY', 'URL'}


def session_for_source(source):
    session = BoundedSession(source['network'])
    session.headers.update({'User-Agent': USER_AGENT})
    return session


def _source_id(source):
    return source['source_id']


def _timezone(source):
    try:
        return ZoneInfo(source.get('timezone', 'America/New_York'))
    except Exception as exc:
        raise ValueError('Invalid UCF source timezone') from exc


def _unfold(text):
    if not isinstance(text, str) or '\x00' in text:
        raise ValueError('Invalid UCF ICS response')
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    unfolded = []
    for line in lines:
        if line.startswith((' ', '\t')):
            if not unfolded:
                raise ValueError('Invalid folded UCF ICS line')
            unfolded[-1] += line[1:]
        elif line:
            unfolded.append(line)
    return unfolded


def _property(line):
    if ':' not in line:
        raise ValueError('Invalid UCF ICS property')
    head, value = line.split(':', 1)
    chunks = head.split(';')
    name = chunks[0].upper()
    if not re.fullmatch(r'[A-Z-]+', name):
        raise ValueError('Invalid UCF ICS property name')
    params = {}
    for chunk in chunks[1:]:
        if '=' not in chunk:
            raise ValueError('Invalid UCF ICS parameter')
        key, param = chunk.split('=', 1)
        key = key.upper()
        if key in params or not re.fullmatch(r'[A-Z-]+', key):
            raise ValueError('Invalid UCF ICS parameter')
        params[key] = param.strip('"')
    return name, params, value


def _parse_time(value, params, zone):
    if params and set(params) != {'TZID'}:
        raise ValueError('Unsupported UCF ICS time parameters')
    if value.endswith('Z'):
        if params:
            raise ValueError('Ambiguous UCF ICS UTC time')
        try:
            return datetime.strptime(value, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise ValueError('Unsupported UCF ICS time format') from exc
    if params.get('TZID') not in (None, zone.key):
        raise ValueError('Unexpected UCF ICS timezone')
    try:
        local = datetime.strptime(value, '%Y%m%dT%H%M%S')
    except ValueError as exc:
        raise ValueError('Unsupported UCF ICS time format') from exc
    # The documented feed supplies local, second-precision times.  Reject the
    # DST fold, whose offset cannot be determined from this representation.
    first = local.replace(tzinfo=zone, fold=0)
    second = local.replace(tzinfo=zone, fold=1)
    if first.utcoffset() != second.utcoffset():
        raise ValueError('Ambiguous UCF ICS local time')
    return first


def parse_calendar(text, source):
    """Return only the VEVENT facts required by normalization.

    This deliberately supports the concrete UCF representation, not general
    iCalendar recurrence or all-day date semantics.
    """
    zone = _timezone(source)
    events, properties, in_event = [], None, False
    saw_calendar, ended_calendar, declared_zone = False, False, False
    for line in _unfold(text):
        if line == 'BEGIN:VCALENDAR':
            if saw_calendar or ended_calendar:
                raise ValueError('Nested UCF ICS calendar')
            saw_calendar = True
            continue
        if line == 'END:VCALENDAR':
            if not saw_calendar or in_event or ended_calendar:
                raise ValueError('Unclosed UCF ICS event')
            ended_calendar = True
            continue
        if ended_calendar:
            raise ValueError('Trailing UCF ICS content')
        if line == 'BEGIN:VEVENT':
            if not saw_calendar or in_event:
                raise ValueError('Invalid UCF ICS event boundary')
            properties, in_event = {}, True
            continue
        if line == 'END:VEVENT':
            if not in_event:
                raise ValueError('Invalid UCF ICS event boundary')
            if not REQUIRED_PROPERTIES <= properties.keys():
                raise ValueError('UCF ICS event fields missing')
            if RECURRING_PROPERTIES & properties.keys():
                raise ValueError('Unsupported UCF ICS recurrence')
            events.append(properties)
            properties, in_event = None, False
            continue
        name, params, value = _property(line)
        if in_event:
            if name in properties:
                raise ValueError('Duplicate UCF ICS event field')
            properties[name] = (params, value)
        elif name == 'TZID' and value == zone.key:
            declared_zone = True
    if not saw_calendar or not ended_calendar or in_event or not declared_zone:
        raise ValueError('UCF ICS calendar or timezone declaration missing')
    return [{
        'uid': properties['UID'][1],
        'title': html.unescape(properties['SUMMARY'][1]).strip(),
        'starts_at': _parse_time(properties['DTSTART'][1], properties['DTSTART'][0], zone),
        'ends_at': _parse_time(properties['DTEND'][1], properties['DTEND'][0], zone),
        'location': html.unescape(properties['LOCATION'][1]).strip(),
        'url': properties['URL'][1].strip(),
        'description': html.unescape(properties.get('DESCRIPTION', ({}, ''))[1]),
        'status': properties.get('STATUS', ({}, ''))[1].strip().upper(),
    } for properties in events]


def read_feed(url, session, source):
    response = session.get(url, timeout=20)
    response.raise_for_status()
    content_type = response.headers.get('content-type', '').lower()
    if 'text/calendar' not in content_type:
        raise ValueError('Unexpected UCF ICS content type')
    return parse_calendar(response.text, source)


def read_categories(url, session):
    """Read only documented JSON category facts transiently for policy parity."""
    response = session.get(url, timeout=20)
    response.raise_for_status()
    rows = response.json()
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('Unexpected UCF category verification feed')
    categories = {}
    for row in rows:
        identity = str(row.get('eventinstance_id', ''))
        category = row.get('category')
        if not re.fullmatch(r'\d{1,20}', identity) or not isinstance(category, str):
            raise ValueError('UCF category verification fields missing')
        if identity in categories and categories[identity] != category:
            raise ValueError('Ambiguous UCF category verification')
        categories[identity] = category
    return categories


def _occurrence_id(url):
    parsed = urlparse(url)
    match = re.fullmatch(r'/event/(\d{1,20})/[^/]+/?', parsed.path)
    return match.group(1) if match else None


def _public_admission(session, source):
    response = session.get(source['access_url'], timeout=20)
    response.raise_for_status()
    visible = re.sub(r'\s+', ' ', re.sub('<[^>]+>', ' ', html.unescape(response.text))).lower()
    if 'the gallery is free and open to the public' not in visible:
        raise ValueError('Gallery public admission could not be reconfirmed')


def _event_url(value):
    parsed = urlparse(value)
    if parsed.scheme != 'https' or parsed.hostname != 'events.ucf.edu' or not re.fullmatch(
            r'/event/\d{1,20}/[^/]+/?', parsed.path):
        return None
    return value


def normalize(raw, source, locations, verified_at):
    identity = raw.get('uid', '').strip()
    title = raw.get('title', '').strip()
    if not identity or not title:
        raise ValueError('UCF ICS occurrence identity or title missing')
    source_url = _event_url(raw.get('url', ''))
    uid_url = _event_url(identity)
    if not source_url or not uid_url or uid_url != source_url:
        return None, 'invalid_source_link_or_identity'
    occurrence = _occurrence_id(source_url)
    if raw.get('category') != 'Arts Exhibit':
        return None, 'category_not_eligible'
    if raw.get('status') == 'CANCELLED' or re.search(r'\b(cancelled|canceled|postponed)\b', title, re.I):
        return None, 'cancelled_or_postponed'
    if raw.get('location') not in locations:
        return None, 'public_access_or_location_not_verified'
    prose = raw.get('description', '')
    if re.search(r'\b(students? only|private event|invitation only|cancelled|canceled|postponed)\b', prose, re.I):
        return None, 'restricted_or_changed'
    start, end = raw.get('starts_at'), raw.get('ends_at')
    if not isinstance(start, datetime) or not isinstance(end, datetime) or not start.tzinfo or not end.tzinfo or end <= start:
        return None, 'invalid_time'
    if end <= verified_at:
        return None, 'ended'
    venue = locations[raw['location']]
    return {
        'source_id': _source_id(source), 'occurrence_id': occurrence,
        'series_id': occurrence, 'title': title[:300], 'starts_at': start, 'ends_at': end,
        'timezone': _timezone(source).key, 'metro': source['metro'], 'category': 'arts_culture',
        'source_url': source_url, 'official_url': source_url, 'access_note': venue['access'],
        'access_url': source['access_url'], 'venue_name': raw['location'],
        'entity_id': venue['entity_id'], 'latitude': float(venue['lat']),
        'longitude': float(venue['lon']), 'h3_r8': h3.latlng_to_cell(venue['lat'], venue['lon'], 8),
        'verified_at': verified_at, 'expires_at': min(end, verified_at + timedelta(hours=24)),
    }, None


def _locations(db, source):
    return {config['feed_name']: {**location(db, config), 'access': config['access']}
            for config in source['locations']}


def collect(db, source, start, days=14, session=None):
    if not 1 <= days <= 31:
        raise ValueError('UCF ICS collection window must be 1-31 days')
    owned_session = session is None
    session = session or session_for_source(source)
    try:
        _public_admission(session, source)
        locations = _locations(db, source)
        verified_at, records, seen, counts = datetime.now(timezone.utc), [], set(), Counter()
        for offset in range(days):
            day = start + timedelta(days=offset)
            root = f'https://events.ucf.edu/{day.year}/{day.month}/{day.day}/feed'
            for raw in read_feed(root+'.ics', session, source):
                counts['source_occurrences'] += 1
                identity = raw['uid']
                if identity in seen:
                    counts['duplicate_occurrences'] += 1
                    continue
                seen.add(identity)
                if raw['location'] in locations and _event_url(raw['url']) and not re.search(
                        r'\b(cancelled|canceled|postponed|students? only|private event|invitation only)\b',
                        raw['title']+' '+raw['description'], re.I) and raw['status'] != 'CANCELLED':
                    categories = read_categories(raw['url'].rstrip('/') + '/feed.json', session)
                    raw['category'] = categories.get(_occurrence_id(raw['url']))
                else:
                    # Preserve normalize's specific rejection reason without
                    # spending a JSON request on an already ineligible event.
                    raw['category'] = 'Arts Exhibit'
                result, reason = normalize(raw, source, locations, verified_at)
                counts[reason or 'eligible'] += 1
                if result:
                    records.append(result)
        return records, {'window_start': start.isoformat(), 'window_days': days,
            'verified_at': verified_at.isoformat(), 'counts': dict(counts),
            'coverage_limit': 'UCF main ICS feed; only the independently verified public gallery location and Arts Exhibit category are enabled. Not metro-wide coverage.'}
    finally:
        if owned_session:
            session.close()


def recheck(db, source, event):
    identity = event['occurrence_id']
    source_url = event.get('source_url', '')
    if not re.fullmatch(r'\d{1,20}', identity) or not _event_url(source_url) or \
            _occurrence_id(source_url) != identity:
        raise ValueError('Invalid UCF ICS occurrence identity')
    session = session_for_source(source)
    try:
        _public_admission(session, source)
        # Event profile feeds use the same documented suffix.  Keep parser and
        # identity validation identical to collection before accepting a recheck.
        rows = read_feed(source_url.rstrip('/') + '/feed.ics', session, source)
        matches = [row for row in rows if row['uid'] == source_url]
        if len(matches) > 1:
            raise ValueError('Ambiguous UCF ICS occurrence')
        if not matches:
            return None
        categories = read_categories(source_url.rstrip('/') + '/feed.json', session)
        matches[0]['category'] = categories.get(event['occurrence_id'])
        return normalize(matches[0], source, _locations(db, source), datetime.now(timezone.utc))[0]
    finally:
        session.close()

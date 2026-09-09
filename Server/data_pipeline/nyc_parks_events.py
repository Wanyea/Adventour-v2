"""NYC Parks factual open-data adapter; prose is inspected, never persisted.

Initial scope: publicly listed park events with a named meeting point, a park ID,
valid NYC coordinates and no detected access restriction. Source publication age
bounds freshness even when repeated downloads succeed.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone
import html
import math
import re
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import h3

from data_pipeline.event_http import BoundedSession

DATASET = 'https://data.cityofnewyork.us/d/w3wp-dpdi'
API = 'https://data.cityofnewyork.us/resource/w3wp-dpdi.json'
METADATA = 'https://data.cityofnewyork.us/api/views/w3wp-dpdi.json'
FIELDS = ('guid,title,link,starttime,endtime,coordinates,parkids,parknames,location,'
          'categories,registration_url,registration_description,description')
ZONE = ZoneInfo('America/New_York')
EXCLUDED_CATEGORIES = {'Best for Kids', 'Recreation Center Programming', 'Sports Camps',
                       'Summer Sports Experience', 'Afterschool Programs', 'Seniors'}


def session_for_source(source):
    """Create the bounded production session for this registered source."""
    session = BoundedSession(source['network'])
    session.headers.update({'User-Agent': 'Adventour/0.2 (NYC Parks Open Data consumer)'})
    return session


def publication(session, now):
    response = session.get(METADATA, timeout=20)
    response.raise_for_status()
    metadata = response.json()
    published = datetime.fromtimestamp(int(metadata['rowsUpdatedAt']), timezone.utc)
    if not now-timedelta(hours=24) < published <= now:
        raise ValueError('NYC Parks publication stale or future-dated; freshness not renewed')
    return published


def read_rows(session, **params):
    response = session.get(API, params={'$select': FIELDS, '$limit': 5000,
                                       '$order': 'starttime,guid', **params}, timeout=25)
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list) or len(rows) >= 5000 or any(not isinstance(r, dict) for r in rows):
        raise ValueError('Unexpected or truncated NYC feed; snapshot not replaced')
    return rows


def category_for(title, categories):
    if categories & {'Art', 'Arts & Crafts', 'History', 'Talks', 'Tours', 'Exhibits'} or \
            re.search(r'\b(poetry|reading|museum|exhibit)\b', title, re.I):
        return 'arts_culture'
    if categories & {'Concerts', 'Theater', 'Dance', 'Movies', 'Games', 'Free Summer Concerts', 'Free Summer Theater'}:
        return 'entertainment'
    if categories & {'Fitness', 'Outdoor Fitness', 'Exercise Classes', 'Yoga & Pilates Classes'}:
        return 'wellness'
    return 'outdoors'


def normalize(raw, source, published, now):
    if not {'guid', 'title', 'starttime', 'endtime', 'link'} <= raw.keys():
        raise ValueError('NYC event schema changed; snapshot not replaced')
    identity = str(raw['guid'])
    if not re.fullmatch(r'\d{1,20}', identity):
        raise ValueError('Invalid NYC occurrence identity')
    title = html.unescape(raw['title'] or '').strip()
    prose = re.sub('<[^>]+>', ' ', html.unescape(raw.get('description') or ''))
    registration = html.unescape(raw.get('registration_description') or '')
    # Cancellation wording in free prose may describe weather contingencies.
    if re.search(r'\b(cancelled|canceled|postponed|sold out)\b', title+' '+registration, re.I) or \
            re.search(r'\b(registration is closed|event (?:is|has been) cancel[le]*d)\b', registration+' '+prose, re.I):
        return None, 'cancelled_or_registration_closed'
    categories = {c.strip() for c in (raw.get('categories') or '').split('|')}
    if categories & EXCLUDED_CATEGORIES or re.search(
            r'\b(members? only|students? only|private event|invitation only|membership required|ages? \d|aged \d)\b',
            title+' '+registration+' '+prose, re.I):
        return None, 'restricted_or_age_program'
    try:
        start = datetime.fromisoformat(raw['starttime']).replace(tzinfo=ZONE)
        end = datetime.fromisoformat(raw['endtime']).replace(tzinfo=ZONE)
    except (TypeError, ValueError):
        return None, 'invalid_time'
    if end <= start or end-start > timedelta(hours=18):
        return None, 'invalid_time'
    if end <= now:
        return None, 'ended'
    try:
        lat, lon = map(float, raw['coordinates'].split(','))
        west, south, east, north = source['bbox']
        if not (math.isfinite(lat) and math.isfinite(lon) and south <= lat <= north and west <= lon <= east):
            raise ValueError('Outside NYC')
    except (KeyError, TypeError, ValueError):
        return None, 'unusable_location'
    venue = (raw.get('location') or '').strip()
    if not venue or not raw.get('parknames') or not re.fullmatch(r'[A-Z]\d{3}[A-Z0-9]*', raw.get('parkids') or ''):
        return None, 'ambiguous_or_nonpark_location'
    link = raw['link'].get('url', '') if isinstance(raw['link'], dict) else ''
    parsed = urlparse(link)
    if parsed.scheme not in ('http', 'https') or parsed.hostname != 'www.nycgovparks.org' or \
            not parsed.path.startswith('/events/') or not title:
        return None, 'invalid_source_link'
    registration_note = 'Registration/fees/eligibility: check organizer.'
    if raw.get('registration_url'):
        registration_note = 'Registration link provided; check availability and requirements with organizer.'
    elif re.search(r'\bregistration (?:is )?not required\b', registration, re.I):
        registration_note = 'No registration required according to the published listing.'
    return {'source_id': 'nyc_parks', 'occurrence_id': identity, 'series_id': identity,
        'title': title[:300], 'starts_at': start, 'ends_at': end, 'timezone': 'America/New_York',
        'metro': source['metro'], 'category': category_for(title, categories),
        'source_url': link, 'official_url': link, 'access_url': DATASET,
        'access_note': 'Public NYC Parks listing. '+registration_note+' Calendar updates daily; check organizer before leaving.',
        'venue_name': venue[:300], 'entity_id': None, 'latitude': lat, 'longitude': lon,
        'h3_r8': h3.latlng_to_cell(lat, lon, 8), 'verified_at': published,
        'expires_at': min(end, published+timedelta(hours=24))}, None


def collect(db, source, start_day, days=14, session=None):
    if not 1 <= days <= 14:
        raise ValueError('NYC publication covers at most 14 days')
    owned = session is None
    session = session or session_for_source(source)
    try:
        now = datetime.now(timezone.utc)
        published = publication(session, now)
        rows = read_rows(session)
        records, seen, counts = [], set(), Counter()
        for raw in rows:
            counts['source_occurrences'] += 1
            result, reason = normalize(raw, source, published, now)
            if result and not start_day <= result['starts_at'].date() < start_day+timedelta(days=days):
                result, reason = None, 'outside_window'
            if result and result['occurrence_id'] in seen:
                result, reason = None, 'duplicate_occurrence'
            counts[reason or 'eligible'] += 1
            if result:
                seen.add(result['occurrence_id'])
                records.append(result)
        return records, {'window_start': start_day.isoformat(), 'window_days': days,
            'fetched_at': now.isoformat(), 'verified_at': published.isoformat(), 'counts': dict(counts),
            'dataset': DATASET, 'dataset_version': published.isoformat(),
            'modifications': 'Factual subset; geographic/time/access filters; category mapping; no prose/images/contacts.',
            'coverage_limit': 'NYC Parks public park listings only; excludes child-focused/restricted and ambiguous locations. Daily publication.'}
    finally:
        if owned and callable(getattr(session, 'close', None)):
            session.close()


def recheck(db, source, event):
    identity = event['occurrence_id']
    if not re.fullmatch(r'\d{1,20}', identity):
        raise ValueError('Invalid NYC occurrence identity')
    session = session_for_source(source)
    try:
        now = datetime.now(timezone.utc)
        published = publication(session, now)
        rows = read_rows(session, guid=identity)
        if len(rows) > 1:
            raise ValueError('Ambiguous NYC occurrence')
        return normalize(rows[0], source, published, now)[0] if rows else None
    finally:
        if callable(getattr(session, 'close', None)):
            session.close()

"""Bounded UCF feed adapter. Descriptions are inspected transiently, never retained.

Only the verified public gallery location is enabled initially. This is explicitly
limited source coverage, not a classifier that equates campus visibility to access.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import html
import re
import time
from urllib.parse import urlparse

import h3
import requests
from sqlalchemy import text

USER_AGENT = 'Adventour/0.2 (UCF documented event-feed consumer)'


def read_json(url, session, single=False):
    response = session.get(url, timeout=20)
    response.raise_for_status()
    data = response.json()
    if single and isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
        raise ValueError('Unexpected UCF feed shape; freshness not renewed')
    return data


def location(db, config):
    west, south, east, north = config['bbox']
    rows = db.session.execute(text("""SELECT DISTINCT ON (COALESCE(canonical_id,id))
        COALESCE(canonical_id,id) AS entity_id,name,websites,
        COALESCE(canonical_lat,lat) AS lat,COALESCE(canonical_lon,lon) AS lon
        FROM places WHERE lower(name)=lower(:name) AND index_active
          AND COALESCE(canonical_lat,lat) BETWEEN :south AND :north
          AND COALESCE(canonical_lon,lon) BETWEEN :west AND :east
        ORDER BY COALESCE(canonical_id,id),id"""),
        {'name': config['owned_name'], 'south': south, 'north': north, 'west': west, 'east': east}).mappings().all()
    matched = [r for r in rows if any(urlparse(u).hostname in config['website_hosts']
                                    for u in (r['websites'] or []))]
    if len(matched) != 1:
        raise ValueError('Event venue needs a unique owned name, geographic and website match')
    return dict(matched[0])


def normalize(raw, source, locations, verified_at):
    required = {'eventinstance_id', 'title', 'starts', 'ends', 'url', 'location', 'category'}
    if not required <= raw.keys():
        raise ValueError('UCF fields missing; do not treat parser drift as a successful empty feed')
    title = html.unescape(raw['title'] or '').strip()
    description = re.sub('<[^>]+>', ' ', html.unescape(raw.get('description') or ''))
    if re.search(r'\b(cancelled|canceled|postponed)\b', title, re.I):
        return None, 'cancelled_or_postponed'
    if raw['category'] != 'Arts Exhibit' or raw['location'] not in locations:
        return None, 'public_access_or_location_not_verified'
    # A specific restriction takes precedence over the venue's normal admission.
    if re.search(r'\b(students? only|private event|invitation only|cancelled|canceled|postponed)\b', description, re.I):
        return None, 'restricted_or_changed'
    start, end = parsedate_to_datetime(raw['starts']), parsedate_to_datetime(raw['ends'])
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        return None, 'invalid_time'
    if end <= verified_at:
        return None, 'ended'
    event_url = urlparse(raw['url'])
    if event_url.scheme != 'https' or event_url.hostname != 'events.ucf.edu':
        return None, 'invalid_source_link'
    venue = locations[raw['location']]
    return {
        'source_id': 'ucf_main', 'occurrence_id': str(raw['eventinstance_id']),
        'series_id': str(raw.get('event_id') or raw['eventinstance_id']),
        'title': title[:300], 'starts_at': start, 'ends_at': end,
        'timezone': 'America/New_York', 'metro': source['metro'],
        'category': 'arts_culture', 'source_url': raw['url'],
        'official_url': raw['url'], 'access_note': venue['access'],
        'access_url': source['access_url'], 'venue_name': raw['location'],
        'entity_id': venue['entity_id'], 'latitude': float(venue['lat']),
        'longitude': float(venue['lon']),
        'h3_r8': h3.latlng_to_cell(venue['lat'], venue['lon'], 8),
        'verified_at': verified_at, 'expires_at': min(end, verified_at + timedelta(hours=24)),
    }, None


def collect(db, source, start_day, days=14, session=None):
    session = session or requests.Session()
    session.headers.update({'User-Agent': USER_AGENT})
    policy = session.get(source['access_url'], timeout=20)
    policy.raise_for_status()
    visible = re.sub(r'\s+', ' ', re.sub('<[^>]+>', ' ', html.unescape(policy.text))).lower()
    if 'the gallery is free and open to the public' not in visible:
        raise ValueError('Gallery public admission could not be reconfirmed')
    locations = {c['feed_name']: {**location(db, c), 'access': c['access']} for c in source['locations']}
    seen, counts, records = set(), Counter(), []
    verified_at = datetime.now(timezone.utc)
    for offset in range(days):
        day = start_day + timedelta(days=offset)
        rows = read_json(f'https://events.ucf.edu/{day.year}/{day.month}/{day.day}/feed.json', session)
        for raw in rows:
            counts['source_occurrences'] += 1
            identity = raw.get('eventinstance_id')
            if identity is None:
                raise ValueError('Missing occurrence identity')
            if identity in seen:
                counts['duplicate_occurrences'] += 1
                continue
            seen.add(identity)
            result, reason = normalize(raw, source, locations, verified_at)
            counts[reason or 'eligible'] += 1
            if result:
                records.append(result)
        time.sleep(.2)
    return records, {'window_start': start_day.isoformat(), 'window_days': days,
                     'verified_at': verified_at.isoformat(), 'counts': dict(counts),
                     'coverage_limit': 'UCF main feed; only public gallery occurrences enabled. Not metro-wide coverage.'}


def recheck(db, source, event):
    session = requests.Session()
    session.headers.update({'User-Agent': USER_AGENT})
    response = session.get(source['access_url'], timeout=20)
    response.raise_for_status()
    visible = re.sub(r'\s+', ' ', re.sub('<[^>]+>', ' ', html.unescape(response.text))).lower()
    if 'the gallery is free and open to the public' not in visible:
        raise ValueError('Public admission could not be reconfirmed')
    rows = read_json(event['source_url'].rstrip('/')+'/feed.json', session, single=True)
    raw = next((r for r in rows if str(r.get('eventinstance_id'))==event['occurrence_id']), None)
    if raw is None:
        return None
    locations = {c['feed_name']: {**location(db,c), 'access':c['access']} for c in source['locations']}
    return normalize(raw, source, locations, datetime.now(timezone.utc))[0]

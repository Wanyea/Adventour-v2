"""Read-only NYC Parks source preview; no database or scheduler changes.

Run: python -m data_pipeline.preview_nyc_events
Prints diagnostics and organizer links, not a production eligibility verdict.
"""

from collections import Counter
from datetime import datetime, timedelta
import json
import math
from zoneinfo import ZoneInfo

import requests


def preview():
    now = datetime.now(ZoneInfo('America/New_York'))
    end = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=14)
    response = requests.get('https://data.cityofnewyork.us/resource/w3wp-dpdi.json',
        params={'$select': 'guid,title,link,starttime,endtime,coordinates,registration_url,registration_description',
                '$limit': 5000, '$order': 'starttime,guid'}, timeout=25)
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list) or len(rows) >= 5000:
        raise ValueError('Unexpected or truncated feed; do not report complete counts')
    counts, seen, links = Counter(), set(), []
    for row in rows:
        try:
            start = datetime.fromisoformat(row['starttime']).replace(tzinfo=now.tzinfo)
            finish = datetime.fromisoformat(row['endtime']).replace(tzinfo=now.tzinfo)
            if finish <= start:
                counts['invalid_time_order'] += 1
                continue
            if finish <= now or start >= end:
                counts['ended_or_outside_window'] += 1
                continue
            lat, lon = map(float, row['coordinates'].split(','))
            if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError('Invalid coordinates')
            a, b = math.radians(40.7127281), math.radians(lat)
            h = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(lon+74.0060152)/2)**2
            meters = 6371000*2*math.asin(min(1, math.sqrt(h)))
            if meters > 50000:
                counts['outside_50km'] += 1
                continue
            key = (row['guid'], row['starttime'])
            if key in seen:
                counts['duplicate_occurrence'] += 1
                continue
            seen.add(key)
            access = (row['title']+' '+row.get('registration_description', '')).lower()
            if any(term in access for term in ('registration is closed', 'sold out', 'cancelled', 'canceled')):
                counts['explicit_closed_registration_or_cancelled'] += 1
                continue
            counts['candidate_occurrences'] += 1
            counts['with_registration_link'] += bool(row.get('registration_url'))
            if len(links) < 10 and any(term in row['title'].lower() for term in
                    ('yoga', 'bird', 'stargaz', 'nature walk', 'garden', 'poetry', 'game night')):
                links.append(row['link']['url'])
        except (KeyError, TypeError, ValueError):
            counts['missing_or_unusable_time_coordinates'] += 1
    return {'checked_at': now.isoformat(), 'source': 'NYC Parks Public Events - Upcoming 14 Days',
        'source_url': 'https://data.cityofnewyork.us/d/w3wp-dpdi',
        'launch': {'latitude': 40.7127281, 'longitude': -74.0060152},
        'radius_meters': 50000, 'window_end_exclusive': end.isoformat(),
        'source_rows': len(rows), 'counts': dict(counts), 'sample_links': links,
        'limitations': ['Read-only preview: no DB writes or scheduler changes.',
            'Candidates still need organizer access checks and location provenance verification.',
            'Repeated sessions count separately; this is source-specific, not city-wide coverage.',
            'The dataset updates daily; a six-hour fetch does not improve upstream publication frequency.']}


if __name__ == '__main__':
    print(json.dumps(preview(), indent=2))

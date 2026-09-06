"""Worldwide launch geocoding, separate from owned-index candidate retrieval.

Photon permits modest public API use. Search results are transient, never written
to the place/event index. The app credits OpenStreetMap contributors.
"""

from collections import OrderedDict
import math
import os
from threading import Lock
import time

import requests

_lock = Lock()
_next_request = 0.0
_cache = OrderedDict()


class SearchUnavailable(Exception):
    pass


def coordinates(latitude, longitude):
    lat, lon = float(latitude), float(longitude)
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('Invalid coordinates.')
    return {'city': 'Current Location', 'state': 'GPS', 'latitude': lat, 'longitude': lon,
            'source': 'device_coordinates'}


def _search(query):
    global _next_request
    now = time.monotonic()
    with _lock:
        cached = _cache.get(query.casefold())
        if cached and cached[0] > now:
            return cached[1]
        wait = max(0, _next_request-now)
        if wait > 1:
            raise SearchUnavailable('Location search is busy. Please try again.')
        _next_request = now+wait+1
    time.sleep(wait)
    try:
        response = requests.get(os.getenv('PHOTON_BASE_URL', 'https://photon.komoot.io').rstrip('/')+'/api/',
            params={'q': query, 'limit': 6, 'lang': 'en'},
            headers={'User-Agent': 'Adventour/0.2 (launch-point search)'}, timeout=8)
        response.raise_for_status()
        features = response.json()['features']
        if not isinstance(features, list):
            raise ValueError('Invalid geocoder response')
    except (requests.RequestException, ValueError, KeyError) as exc:
        raise SearchUnavailable('Location search is temporarily unavailable. Try again or use GPS.') from exc
    results = []
    for feature in features:
        try:
            lon, lat = feature['geometry']['coordinates']
            point = coordinates(lat, lon)
            properties = feature['properties']
            street = ' '.join(str(properties.get(k) or '') for k in ('housenumber', 'street')).strip()
            parts = [properties.get('name') or street, properties.get('district'),
                     properties.get('city'), properties.get('state'), properties.get('country')]
            description = ', '.join(dict.fromkeys(str(p) for p in parts if p))
            if not description:
                continue
            results.append({'description': description, 'latitude': point['latitude'],
                'longitude': point['longitude'], 'source': 'photon_osm',
                'suggestion_id': f"osm:{properties['osm_type']}:{properties['osm_id']}"})
        except (KeyError, TypeError, ValueError):
            continue
    with _lock:
        _cache[query.casefold()] = (time.monotonic()+60, results)
        _cache.move_to_end(query.casefold())
        while len(_cache) > 128:
            _cache.popitem(last=False)
    return results


def suggestions(query):
    query = (query or '').strip()[:160]
    return _search(query) if len(query) >= 3 else []


def resolve(query):
    rows = suggestions(query)
    # The app selects returned coordinates directly. Text-only callers must
    # disambiguate; never substitute a business or a covered metro.
    exact = [r for r in rows if r['description'].casefold() == query.strip().casefold()]
    if len(exact) == 1:
        return exact[0]
    raise ValueError('Choose a location from the suggestions, or use GPS.')

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


def _description(properties):
    layer = properties.get('type')
    place_kind = properties.get('osm_value') if properties.get('osm_key') == 'place' else None
    kind = {'city': 'City', 'town': 'Town', 'village': 'Village', 'hamlet': 'Hamlet',
            'suburb': 'Neighborhood', 'neighbourhood': 'Neighborhood',
            'state': 'State', 'country': 'Country'}.get(place_kind)
    kind = kind or {'city': 'City', 'district': 'District', 'locality': 'Locality',
                    'county': 'County', 'state': 'State', 'country': 'Country',
                    'street': 'Street'}.get(layer)
    street = ' '.join(str(properties.get(k) or '') for k in ('housenumber', 'street')).strip()
    local = [properties.get('name') or street]
    if layer not in ('state', 'country', 'county'):
        local.extend([properties.get('district'), properties.get('city')])
    # Remove redundant settlement fields, but preserve distinct hierarchy levels:
    # New York city and New York state legitimately have the same name.
    parts = list(dict.fromkeys(str(p) for p in local if p))
    if not parts:
        return ''
    if layer not in ('state', 'country') and properties.get('state'):
        parts.append(str(properties['state']))
    if layer != 'country' and properties.get('country'):
        parts.append(str(properties['country']))
    label = ', '.join(parts)
    return f'{label} ({kind})' if kind else label


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
            description = _description(properties)
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

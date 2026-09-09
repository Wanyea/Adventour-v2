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
_LOCALITY_SUFFIXES = ('City', 'Town', 'Village', 'Hamlet', 'Neighborhood', 'Locality')
_LOCALITY_LAYERS = {'city', 'locality'}
_LOCALITY_OSM_VALUES = {'city', 'town', 'village', 'hamlet'}


class SearchUnavailable(Exception):
    pass


def coordinates(latitude, longitude):
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError) as exc:
        raise ValueError('Invalid coordinates.') from exc
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('Invalid coordinates.')
    return {'city': 'Current Location', 'state': 'GPS', 'latitude': lat, 'longitude': lon,
            'source': 'device_coordinates'}


def _normalized_description(value):
    """Normalize the known autocomplete type suffix without changing free text."""
    value = (value or '').strip()
    for suffix in _LOCALITY_SUFFIXES:
        typed_suffix = f' ({suffix})'
        if value.casefold().endswith(typed_suffix.casefold()):
            return value[:-len(typed_suffix)].strip().casefold()
    return value.casefold()


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


def _wait_for_photon():
    global _next_request
    now = time.monotonic()
    with _lock:
        wait = max(0, _next_request-now)
        if wait > 1:
            raise SearchUnavailable('Location search is busy. Please try again.')
        _next_request = now+wait+1
    time.sleep(wait)


def _photon_get(endpoint, params):
    _wait_for_photon()
    try:
        response = requests.get(os.getenv('PHOTON_BASE_URL', 'https://photon.komoot.io').rstrip('/') + endpoint,
            params=params,
            headers={'User-Agent': 'Adventour/0.2 (launch-point search)'}, timeout=8)
        response.raise_for_status()
        features = response.json()['features']
        if not isinstance(features, list):
            raise ValueError('Invalid geocoder response')
    except (requests.RequestException, TypeError, ValueError, KeyError) as exc:
        raise SearchUnavailable('Location search is temporarily unavailable. Try again or use GPS.') from exc
    return features


def _is_locality(properties):
    """Whether Photon identifies the result itself as a settlement locality."""
    return properties.get('type') in _LOCALITY_LAYERS or (
        properties.get('osm_key') == 'place' and properties.get('osm_value') in _LOCALITY_OSM_VALUES
    )


def _search(query, locality_only=False):
    cache_key = (query.casefold(), locality_only)
    now = time.monotonic()
    with _lock:
        cached = _cache.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]

    params = {'q': query, 'limit': 6, 'lang': 'en'}
    if locality_only:
        # Photon can classify a village/hamlet as a district. Keep it in the
        # provider result set, then apply the stricter settlement metadata
        # filter below so ordinary districts and neighborhoods still fail.
        params['layer'] = ['city', 'locality', 'district']
    features = _photon_get('/api/', params)
    results = []
    for feature in features:
        try:
            lon, lat = feature['geometry']['coordinates']
            point = coordinates(lat, lon)
            properties = feature['properties']
            if not isinstance(properties, dict):
                continue
            if locality_only and not _is_locality(properties):
                continue
            description = _description(properties)
            if not description:
                continue
            results.append({'description': description, 'latitude': point['latitude'],
                'longitude': point['longitude'], 'source': 'photon_osm',
                'suggestion_id': f"osm:{properties['osm_type']}:{properties['osm_id']}"})
        except (KeyError, TypeError, ValueError):
            continue
    with _lock:
        _cache[cache_key] = (time.monotonic()+60, results)
        _cache.move_to_end(cache_key)
        while len(_cache) > 128:
            _cache.popitem(last=False)
    return results


def suggestions(query, locality_only=False):
    query = (query or '').strip()[:160]
    return _search(query, locality_only=locality_only) if len(query) >= 3 else []


def resolve(query):
    rows = suggestions(query)
    # The app selects returned coordinates directly. Text-only callers must
    # disambiguate; never substitute a business or a covered metro.
    normalized_query = _normalized_description(query)
    exact = [r for r in rows if _normalized_description(r['description']) == normalized_query]
    if len(exact) == 1:
        return exact[0]
    raise ValueError('Choose a location from the suggestions, or use GPS.')


def resolve_locality(query):
    """Resolve a saved home only when Photon uniquely identifies a locality."""
    rows = suggestions(query, locality_only=True)
    normalized_query = _normalized_description(query)
    exact = [row for row in rows if _normalized_description(row['description']) == normalized_query]
    if len(exact) == 1:
        return exact[0]
    raise ValueError('Choose a city or town from the suggestions, or use GPS.')


def _reverse_label(feature):
    if not isinstance(feature, dict):
        return None
    properties = feature.get('properties') or {}
    if not isinstance(properties, dict):
        return None
    locality = next((str(properties[key]).strip() for key in
                     ('city', 'town', 'village', 'hamlet', 'locality', 'municipality')
                     if properties.get(key)), None)
    if not locality and properties.get('osm_key') == 'place' and properties.get('osm_value') in {
        'city', 'town', 'village', 'hamlet'
    }:
        locality = str(properties.get('name') or '').strip() or None
    if not locality:
        return None
    region = str(properties.get('state') or properties.get('country') or '').strip() or 'GPS'
    return locality, region


def reverse_coordinates(latitude, longitude):
    """Return a transient locality label without altering valid device coordinates."""
    point = coordinates(latitude, longitude)
    try:
        features = _photon_get('/reverse', {
            'lat': point['latitude'], 'lon': point['longitude'], 'limit': 1, 'lang': 'en',
        })
        label = _reverse_label(features[0]) if features else None
    except (SearchUnavailable, TypeError, ValueError):
        label = None
    if not label:
        return point
    return {**point, 'city': label[0], 'state': label[1], 'source': 'photon_reverse'}

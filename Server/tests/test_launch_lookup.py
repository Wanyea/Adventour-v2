"""Worldwide launch coordinates are independent of indexed venue/event coverage."""

from types import SimpleNamespace
import pytest
import requests
from adventour_backend.services import launch_service as launch


@pytest.mark.parametrize('query,lon,lat,state,country', [
    ('New York, NY', -74.0060152, 40.7127281, 'New York', 'United States'),
    ('London', -.1277653, 51.5074456, 'England', 'United Kingdom'),
])
def test_worldwide_lookup_preserves_selected_geography(monkeypatch, query, lon, lat, state, country):
    launch._cache.clear()
    monkeypatch.setattr(launch, '_next_request', 0)
    calls = []
    def get(url, **kwargs):
        calls.append(kwargs)
        assert 'bbox' not in kwargs['params'] and 'lat' not in kwargs['params']
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'features': [{
            'geometry': {'coordinates': [lon, lat]}, 'properties': {'name': query.split(',')[0],
            'state': state, 'country': country, 'osm_type': 'R', 'osm_id': 1}}]})
    monkeypatch.setattr(launch.requests, 'get', get)
    result = launch.suggestions(query)[0]
    assert (result['latitude'], result['longitude']) == (lat, lon)
    assert result['source'] == 'photon_osm' and country in result['description']
    assert launch.suggestions(query.upper()) == [result]
    assert len(calls) == 1  # Bounded transient cache, no second provider lookup on selection.


def test_search_failure_does_not_fall_back_to_an_indexed_city(monkeypatch):
    launch._cache.clear()
    monkeypatch.setattr(launch, '_next_request', 0)
    def failure(*args, **kwargs): raise requests.Timeout()
    monkeypatch.setattr(launch.requests, 'get', failure)
    with pytest.raises(launch.SearchUnavailable): launch.suggestions('New York')
    assert not launch._cache


def test_text_resolution_does_not_select_a_partial_business_match(monkeypatch):
    point = {'description': 'New York Pizza, Orlando, Florida, United States',
             'latitude': 28.53, 'longitude': -81.37}
    monkeypatch.setattr(launch, 'suggestions', lambda query: [point])
    with pytest.raises(ValueError): launch.resolve('New York')
    assert launch.resolve(point['description']) == point


def test_home_resolution_normalizes_autocomplete_type_suffix(monkeypatch):
    point = {'description': 'Orlando, Florida, United States (City)', 'latitude': 28.54, 'longitude': -81.38}
    calls = []
    def suggestions(query, locality_only=False):
        calls.append(locality_only)
        return [point]
    monkeypatch.setattr(launch, 'suggestions', suggestions)
    assert launch.resolve_locality(' Orlando, Florida, United States ') == point
    assert launch.resolve_locality(point['description']) == point
    assert calls == [True, True]


@pytest.mark.parametrize('rows', [[], [
    {'description': 'Springfield, Illinois, United States (City)', 'latitude': 39.8, 'longitude': -89.6},
    {'description': 'Springfield, Illinois, United States (Town)', 'latitude': 39.7, 'longitude': -89.5},
]])
def test_home_resolution_requires_one_exact_normalized_match(monkeypatch, rows):
    monkeypatch.setattr(launch, 'suggestions', lambda query, locality_only=False: rows)
    with pytest.raises(ValueError):
        launch.resolve_locality('Springfield, Illinois, United States')


@pytest.mark.parametrize('properties', [
    {'name': 'New York Pizza', 'type': 'house', 'osm_key': 'amenity', 'osm_value': 'restaurant'},
    {'housenumber': '123', 'street': 'Main Street', 'city': 'Orlando', 'type': 'street'},
    {'name': 'Florida', 'type': 'state', 'osm_key': 'place', 'osm_value': 'state'},
])
def test_locality_only_resolution_rejects_exact_business_street_and_state(monkeypatch, properties):
    monkeypatch.setattr(launch, '_next_request', 0)
    monkeypatch.setattr(launch.time, 'sleep', lambda _: None)
    monkeypatch.setattr(launch.requests, 'get', lambda *args, **kwargs:
                        SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'features': [{
                            'geometry': {'coordinates': [-81.3, 28.5]}, 'properties': {
                                **properties, 'country': 'United States', 'osm_type': 'N', 'osm_id': 1,
                            },
                        }]}))
    with pytest.raises(ValueError):
        launch.resolve_locality(launch._description(dict(properties, country='United States')))


def test_locality_only_accepts_a_photon_district_layer_when_it_is_a_village(monkeypatch):
    launch._cache.clear()
    monkeypatch.setattr(launch, '_next_request', 0)
    monkeypatch.setattr(launch.time, 'sleep', lambda _: None)
    calls = []
    def get(url, **kwargs):
        calls.append(kwargs['params'])
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'features': [{
            'geometry': {'coordinates': [-72.5184, 43.6242]},
            'properties': {
                'name': 'Woodstock', 'city': 'Woodstock', 'state': 'Vermont',
                'country': 'United States', 'type': 'district', 'osm_key': 'place',
                'osm_value': 'village', 'osm_type': 'N', 'osm_id': 1,
            },
        }]})
    monkeypatch.setattr(launch.requests, 'get', get)
    result = launch.resolve_locality('Woodstock, Vermont, United States')
    assert result['description'] == 'Woodstock, Vermont, United States (Village)'
    assert result['latitude'] == 43.6242 and result['longitude'] == -72.5184
    assert calls == [{'q': 'Woodstock, Vermont, United States', 'limit': 6, 'lang': 'en',
                      'layer': ['city', 'locality', 'district']}]


@pytest.mark.parametrize('latitude,longitude', [
    (None, -81), ('not-a-coordinate', -81), (91, -81), (28, -181), (float('nan'), -81),
])
def test_reverse_rejects_malformed_coordinates_before_provider_call(monkeypatch, latitude, longitude):
    monkeypatch.setattr(launch.requests, 'get', lambda *args, **kwargs: pytest.fail('provider called'))
    with pytest.raises(ValueError):
        launch.reverse_coordinates(latitude, longitude)


def test_reverse_uses_photon_locality_but_retains_original_coordinates(monkeypatch):
    monkeypatch.setattr(launch, '_next_request', 0)
    monkeypatch.setattr(launch.time, 'sleep', lambda _: None)
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'features': [{
            'properties': {'city': 'Orlando', 'state': 'Florida'},
        }]})
    monkeypatch.setattr(launch.requests, 'get', get)
    result = launch.reverse_coordinates(28.5383355, -81.3792365)
    assert result == {'city': 'Orlando', 'state': 'Florida', 'latitude': 28.5383355,
                      'longitude': -81.3792365, 'source': 'photon_reverse'}
    assert calls[0][0].endswith('/reverse')
    assert calls[0][1]['params'] == {'lat': 28.5383355, 'lon': -81.3792365, 'limit': 1, 'lang': 'en'}


@pytest.mark.parametrize('response', [
    {'features': []}, {'features': [{'properties': {}}]},
])
def test_reverse_without_locality_keeps_usable_generic_gps(monkeypatch, response):
    monkeypatch.setattr(launch, '_next_request', 0)
    monkeypatch.setattr(launch.time, 'sleep', lambda _: None)
    monkeypatch.setattr(launch.requests, 'get', lambda *args, **kwargs:
                        SimpleNamespace(raise_for_status=lambda: None, json=lambda: response))
    assert launch.reverse_coordinates(28.5, -81.3) == {
        'city': 'Current Location', 'state': 'GPS', 'latitude': 28.5, 'longitude': -81.3,
        'source': 'device_coordinates',
    }


def test_reverse_timeout_keeps_usable_generic_gps(monkeypatch):
    monkeypatch.setattr(launch, '_next_request', 0)
    monkeypatch.setattr(launch.time, 'sleep', lambda _: None)
    monkeypatch.setattr(launch.requests, 'get', lambda *args, **kwargs: (_ for _ in ()).throw(requests.Timeout()))
    assert launch.reverse_coordinates(28.5, -81.3)['source'] == 'device_coordinates'


def test_reverse_malformed_provider_reply_keeps_usable_generic_gps(monkeypatch):
    monkeypatch.setattr(launch, '_next_request', 0)
    monkeypatch.setattr(launch.time, 'sleep', lambda _: None)
    monkeypatch.setattr(launch.requests, 'get', lambda *args, **kwargs:
                        SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'features': 'not-a-list'}))
    assert launch.reverse_coordinates(28.5, -81.3)['source'] == 'device_coordinates'


@pytest.mark.parametrize('properties,expected', [
    ({'name': 'New York', 'state': 'New York', 'type': 'city',
      'osm_key': 'place', 'osm_value': 'city'}, 'New York, New York, United States (City)'),
    ({'name': 'New York', 'type': 'state', 'osm_key': 'place', 'osm_value': 'state'},
     'New York, United States (State)'),
    ({'name': 'Bar Harbor', 'state': 'Maine', 'type': 'city',
      'osm_key': 'place', 'osm_value': 'town'}, 'Bar Harbor, Maine, United States (Town)'),
    ({'name': 'Woodstock', 'city': 'Woodstock', 'state': 'Vermont', 'type': 'district',
      'osm_key': 'place', 'osm_value': 'village'}, 'Woodstock, Vermont, United States (Village)'),
    ({'name': 'Greenwich Village', 'city': 'New York', 'state': 'New York', 'type': 'district',
      'osm_key': 'place', 'osm_value': 'suburb'},
     'Greenwich Village, New York, New York, United States (Neighborhood)'),
    ({'housenumber': '123', 'street': 'Main Street', 'city': 'New York', 'state': 'New York',
      'type': 'house'}, '123 Main Street, New York, New York, United States'),
])
def test_launch_labels_preserve_geographic_levels(properties, expected):
    assert launch._description(dict(properties, country='United States')) == expected

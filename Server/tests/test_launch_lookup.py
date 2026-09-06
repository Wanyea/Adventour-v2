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

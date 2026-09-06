"""Provider requests cannot enter a deck or bypass missing credentials."""

import pytest

from adventour_backend.services.google_services_api import GoogleServicesAPI, deck_boundary


def test_deck_boundary_blocks_even_with_a_key(monkeypatch):
    monkeypatch.setenv('GOOGLE_API_KEY', 'test-key')
    with deck_boundary(), pytest.raises(RuntimeError, match='forbidden'):
        GoogleServicesAPI._request(None, 1, 'GET', 'places/test-id', 'id')


def test_no_key_never_reserves_or_calls_provider(monkeypatch):
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    assert GoogleServicesAPI._request(None, 1, 'GET', 'places/test-id', 'id') is None

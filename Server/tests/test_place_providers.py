from adventour_backend.providers.place_providers import PlaceProvider, ProviderRegistry


class StubProvider(PlaceProvider):
    def __init__(self, name, candidates):
        self.name = name
        self.candidates = candidates

    def search(self, tags, location, radius_meters=3200, constraints=None):
        return self.candidates


def test_local_provider_is_only_used_as_fallback():
    google = StubProvider("google", [{"provider": "google", "place_id": "google-1"}])
    local = StubProvider("local", [{"provider": "local", "place_id": "local-1"}])

    candidates, errors = ProviderRegistry(providers=[google, local]).search(
        tags=["museum"],
        location={"latitude": 1, "longitude": 2},
    )

    assert errors == []
    assert candidates == [{"provider": "google", "place_id": "google-1"}]


def test_local_provider_runs_when_primary_provider_has_no_candidates():
    google = StubProvider("google", [])
    local = StubProvider("local", [{"provider": "local", "place_id": "local-1"}])

    candidates, errors = ProviderRegistry(providers=[google, local]).search(
        tags=["museum"],
        location={"latitude": 1, "longitude": 2},
    )

    assert errors == []
    assert candidates == [{"provider": "local", "place_id": "local-1"}]

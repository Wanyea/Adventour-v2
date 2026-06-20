import os
from abc import ABC, abstractmethod

from adventour_backend.services.google_services_api import GoogleServicesAPI
from adventour_backend.models import Place


class PlaceProvider(ABC):
    """Provider boundary for paid/open/local candidate retrieval."""

    name = "base"

    @abstractmethod
    def search(self, tags, location, radius_meters=3200, constraints=None):
        """Return provider-native place dictionaries."""


class LocalPlaceProvider(PlaceProvider):
    name = "local"

    def search(self, tags, location, radius_meters=3200, constraints=None):
        # Phase 1: simple local candidate source. This deliberately avoids
        # provider display fields and uses only Adventour-owned place identity.
        if not location:
            return []

        places = Place.query.filter(
            Place.latitude.isnot(None),
            Place.longitude.isnot(None)
        ).limit(500).all()

        return [
            {
                "provider": self.name,
                "place_id": f"local:{place.id}",
                "adventour_place_id": place.id,
                "name": place.canonical_name,
                "geometry": {
                    "location": {
                        "lat": place.latitude,
                        "lng": place.longitude,
                    }
                },
                "types": [],
                "rating": None,
                "user_ratings_total": None,
            }
            for place in places
        ]


class GooglePlacesProvider(PlaceProvider):
    name = "google"

    def is_configured(self):
        return bool(os.getenv("GOOGLE_API_KEY"))

    def search(self, tags, location, radius_meters=3200, constraints=None):
        if not self.is_configured():
            return []

        constraints = constraints or {}
        places = GoogleServicesAPI.fetch_places(
            tags,
            location,
            radius_meters=radius_meters,
            max_result_count=constraints.get("limit", 20),
        )
        for place in places:
            place["provider"] = self.name
        return places


class ProviderRegistry:
    """Fan out candidate searches while isolating provider failures."""

    def __init__(self, providers=None):
        self.providers = providers or [
            LocalPlaceProvider(),
            GooglePlacesProvider(),
        ]

    def search(self, tags, location, radius_meters=3200, constraints=None):
        candidates = []
        errors = []

        for provider in self.providers:
            try:
                candidates.extend(provider.search(tags, location, radius_meters, constraints))
            except Exception as exc:
                errors.append({"provider": provider.name, "error": str(exc)})

        return candidates, errors

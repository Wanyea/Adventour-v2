from adventour_backend.services.google_services_api import GoogleServicesAPI


class MockResponse:
    def __init__(self, payload):
        self.payload = payload
        self.text = str(payload)

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_places_new_autocomplete_is_normalized(monkeypatch):
    calls = []

    def mock_post(url, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return MockResponse({
            "suggestions": [
                {
                    "placePrediction": {
                        "placeId": "abc123",
                        "text": {"text": "Local Coffee, Mountain View, CA"},
                    }
                },
                {
                    "queryPrediction": {
                        "text": {"text": "coffee near Mountain View"},
                    }
                },
            ]
        })

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr("requests.post", mock_post)
    GoogleServicesAPI.fetch_autocomplete.cache_clear()

    predictions = GoogleServicesAPI.fetch_autocomplete("coffee", 37.42, -122.08, 1200)

    assert calls[0]["url"].endswith("/places:autocomplete")
    assert calls[0]["headers"]["X-Goog-Api-Key"] == "test-key"
    assert "X-Goog-FieldMask" in calls[0]["headers"]
    assert predictions == [
        {"place_id": "abc123", "description": "Local Coffee, Mountain View, CA"},
        {"place_id": None, "description": "coffee near Mountain View"},
    ]


def test_places_new_nearby_search_is_normalized(monkeypatch):
    calls = []

    def mock_post(url, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return MockResponse({
            "places": [
                {
                    "id": "place-1",
                    "displayName": {"text": "Maya's Corner Cafe"},
                    "formattedAddress": "123 Main St",
                    "location": {"latitude": 37.42, "longitude": -122.08},
                    "types": ["cafe", "restaurant"],
                    "primaryType": "cafe",
                    "rating": 4.8,
                    "userRatingCount": 42,
                    "priceLevel": "PRICE_LEVEL_MODERATE",
                    "businessStatus": "OPERATIONAL",
                }
            ]
        })

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr("requests.post", mock_post)

    places = GoogleServicesAPI.fetch_places(
        ["cafe", "restaurant"],
        {"latitude": 37.42, "longitude": -122.08},
        radius_meters=1200,
        max_result_count=5,
    )

    assert calls[0]["url"].endswith("/places:searchNearby")
    assert calls[0]["json"]["includedTypes"] == ["cafe", "restaurant"]
    assert calls[0]["json"]["maxResultCount"] == 5
    assert places[0]["place_id"] == "place-1"
    assert places[0]["name"] == "Maya's Corner Cafe"
    assert places[0]["user_ratings_total"] == 42
    assert places[0]["price_level"] == 2
    assert places[0]["geometry"]["location"] == {"lat": 37.42, "lng": -122.08}


def test_places_new_text_search_handles_free_form_tags(monkeypatch):
    calls = []

    def mock_post(url, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return MockResponse({"places": []})

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr("requests.post", mock_post)

    GoogleServicesAPI.fetch_places(
        ["cozy", "date night"],
        {"latitude": 37.42, "longitude": -122.08},
        radius_meters=1200,
        max_result_count=5,
    )

    assert calls[0]["url"].endswith("/places:searchText")
    assert calls[0]["json"]["textQuery"] == "cozy date night"
    assert calls[0]["json"]["pageSize"] == 5

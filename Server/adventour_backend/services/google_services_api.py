"""Small Google Maps/Places wrapper used only by the backend.

The mobile app should talk to Adventour routes, not directly to Google. That
keeps keys server-side and gives us one place to control cost and caching rules.
"""

import requests
import os
import re
from functools import lru_cache


GOOGLE_PLACES_BASE_URL = "https://places.googleapis.com/v1"

GOOGLE_PLACE_FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.location",
    "places.types",
    "places.primaryType",
    "places.businessStatus",
    "places.rating",
    "places.userRatingCount",
    "places.priceLevel",
])

GOOGLE_AUTOCOMPLETE_FIELD_MASK = ",".join([
    "suggestions.placePrediction.placeId",
    "suggestions.placePrediction.text.text",
    "suggestions.queryPrediction.text.text",
])

GOOGLE_PRICE_LEVELS = {
    "PRICE_LEVEL_FREE": 0,
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}

GOOGLE_NEARBY_TYPES = {
    "amusement_park",
    "aquarium",
    "art_gallery",
    "bakery",
    "bar",
    "book_store",
    "breakfast_restaurant",
    "brunch_restaurant",
    "cafe",
    "campground",
    "clothing_store",
    "coffee_shop",
    "comedy_club",
    "concert_hall",
    "dessert_restaurant",
    "fast_food_restaurant",
    "fine_dining_restaurant",
    "hiking_area",
    "historical_landmark",
    "ice_cream_shop",
    "library",
    "market",
    "meal_takeaway",
    "mexican_restaurant",
    "movie_theater",
    "museum",
    "night_club",
    "park",
    "performing_arts_theater",
    "pizza_restaurant",
    "restaurant",
    "shopping_mall",
    "spa",
    "steak_house",
    "tea_house",
    "tourist_attraction",
    "visitor_center",
    "zoo",
}


def _is_google_type(value):
    return bool(re.fullmatch(r"[a-z][a-z0-9_]*", value or ""))


def _first_supported_place_type(tags):
    for tag in tags or []:
        if tag in GOOGLE_NEARBY_TYPES:
            return tag
    return None


def _supported_place_types(tags):
    return [
        tag
        for tag in tags or []
        if tag in GOOGLE_NEARBY_TYPES and _is_google_type(tag)
    ][:10]


def _headers(api_key, field_mask):
    return {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": field_mask,
    }


def _display_text(value):
    if isinstance(value, dict):
        return value.get("text")
    return value


def _normalize_new_place(place):
    location = place.get("location") or {}
    display_name = _display_text(place.get("displayName")) or "Unknown place"
    types = place.get("types") or []
    primary_type = place.get("primaryType")
    if primary_type and primary_type not in types:
        types = [primary_type, *types]

    return {
        "provider": "google",
        "place_id": place.get("id") or (place.get("name") or "").replace("places/", ""),
        "name": display_name,
        "vicinity": place.get("formattedAddress"),
        "formatted_address": place.get("formattedAddress"),
        "types": types,
        "rating": place.get("rating"),
        "user_ratings_total": place.get("userRatingCount"),
        "price_level": GOOGLE_PRICE_LEVELS.get(place.get("priceLevel")),
        "business_status": place.get("businessStatus"),
        "geometry": {
            "location": {
                "lat": location.get("latitude"),
                "lng": location.get("longitude"),
            }
        },
    }


def _normalize_new_autocomplete(payload):
    predictions = []
    for suggestion in payload.get("suggestions", []):
        place_prediction = suggestion.get("placePrediction")
        query_prediction = suggestion.get("queryPrediction")
        if place_prediction:
            text = _display_text(place_prediction.get("text"))
            predictions.append({
                "place_id": place_prediction.get("placeId"),
                "description": text,
            })
        elif query_prediction:
            text = _display_text(query_prediction.get("text"))
            predictions.append({
                "place_id": None,
                "description": text,
            })
    return [item for item in predictions if item.get("description")]


class GoogleServicesAPI:
    BASE_URL = GOOGLE_PLACES_BASE_URL

    @staticmethod
    def api_key():
        return os.getenv("GOOGLE_API_KEY")

    @staticmethod
    @lru_cache(maxsize=512)
    def fetch_autocomplete(input_text, latitude=None, longitude=None, radius_meters=3200):
        api_key = GoogleServicesAPI.api_key()
        if not api_key:
            print("[Autocomplete] GOOGLE_API_KEY is not configured.")
            return []

        if not input_text or len(input_text.strip()) < 3:
            return []

        body = {
            "input": input_text.strip(),
            "includeQueryPredictions": True,
        }
        if latitude is not None and longitude is not None:
            body["locationBias"] = {
                "circle": {
                    "center": {
                        "latitude": float(latitude),
                        "longitude": float(longitude),
                    },
                    "radius": float(radius_meters),
                }
            }

        try:
            response = requests.post(
                f"{GoogleServicesAPI.BASE_URL}/places:autocomplete",
                json=body,
                headers=_headers(api_key, GOOGLE_AUTOCOMPLETE_FIELD_MASK),
                timeout=8,
            )
            response.raise_for_status()
            return _normalize_new_autocomplete(response.json())
        except requests.exceptions.RequestException as e:
            print(f"Error fetching autocomplete suggestions: {e}")
            if getattr(e, "response", None) is not None:
                print(f"[Autocomplete] Google response: {e.response.text}")
            return []

    @staticmethod
    def coordinate_fallback(latitude, longitude):
        return {
            "city": "Current Location",
            "state": "GPS",
            "latitude": float(latitude),
            "longitude": float(longitude),
            "source": "coordinate_fallback"
        }

    @staticmethod
    def fetch_places(selected_tags, location, radius_meters=3200, max_result_count=20):
        """
        Fetch one low-cost page of nearby candidates for the recommender.

        Places API (New) uses POST endpoints and field masks. Nearby Search is
        used for known Google types; Text Search handles free-form taste tags.
        """
        api_key = GoogleServicesAPI.api_key()
        if not api_key:
            print("[Places] GOOGLE_API_KEY is not configured.")
            return []

        selected_tags = selected_tags or []
        max_result_count = max(1, min(int(max_result_count or 20), 20))
        included_types = _supported_place_types(selected_tags)

        circle = {
            "center": {
                "latitude": float(location["latitude"]),
                "longitude": float(location["longitude"]),
            },
            "radius": float(radius_meters),
        }

        if included_types:
            url = f"{GoogleServicesAPI.BASE_URL}/places:searchNearby"
            body = {
                "includedTypes": included_types,
                "maxResultCount": max_result_count,
                "locationRestriction": {"circle": circle},
            }
        else:
            url = f"{GoogleServicesAPI.BASE_URL}/places:searchText"
            body = {
                "textQuery": " ".join(selected_tags[:5]) or "local places",
                "pageSize": max_result_count,
                "locationBias": {"circle": circle},
            }

        try:
            response = requests.post(
                url,
                json=body,
                headers=_headers(api_key, GOOGLE_PLACE_FIELD_MASK),
                timeout=8,
            )
            response.raise_for_status()
            return [
                _normalize_new_place(place)
                for place in response.json().get("places", [])
            ]
        except requests.exceptions.RequestException as e:
            print(f"Error fetching places: {e}")
            if getattr(e, "response", None) is not None:
                print(f"[Places] Google response: {e.response.text}")
            raise

    @staticmethod
    def fetch_city_coordinates(city):
        """
        Get latitude and longitude for a city/address using Places API (New).
        """
        api_key = GoogleServicesAPI.api_key()
        if not api_key:
            print("[Geocode] GOOGLE_API_KEY is not configured.")
            return None

        try:
            response = requests.post(
                f"{GoogleServicesAPI.BASE_URL}/places:searchText",
                json={
                    "textQuery": city,
                    "pageSize": 1,
                },
                headers=_headers(
                    api_key,
                    "places.displayName,places.formattedAddress,places.location",
                ),
                timeout=8,
            )
            response.raise_for_status()
            results = response.json().get("places", [])
            if not results:
                print(f"No results from Places Text Search for location: {city}")
                return None
            location = results[0].get("location") or {}
            if location.get("latitude") is None or location.get("longitude") is None:
                print(f"Places Text Search returned no coordinates for location: {city}")
                return None
            return {
                "latitude": location["latitude"],
                "longitude": location["longitude"],
            }
        except requests.exceptions.RequestException as e:
            print(f"Error fetching city coordinates from Places Text Search: {e}")
            if getattr(e, "response", None) is not None:
                print(f"[Geocode] Google response: {e.response.text}")
            raise

    @staticmethod
    def reverse_geocode(latitude, longitude):
        api_key = GoogleServicesAPI.api_key()
        if not api_key:
            print(f"[Geocode] GOOGLE_API_KEY is not configured for {latitude}, {longitude}.")
            return GoogleServicesAPI.coordinate_fallback(latitude, longitude)

        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "latlng": f"{latitude},{longitude}",
            "key": api_key
        }

        response = requests.get(url, params=params)
        data = response.json()

        if not data.get("results"):
            print(f"[Geocode] No results for {latitude}, {longitude}")
            return GoogleServicesAPI.coordinate_fallback(latitude, longitude)

        city = None
        state = None

        for result in data["results"]:
            for component in result["address_components"]:
                types = component.get("types", [])
                if "locality" in types and not city:
                    city = component["long_name"]
                elif "administrative_area_level_1" in types and not state:
                    state = component["short_name"]
            if city and state:
                break

        # Fallbacks
        city = city or "Unknown"
        state = state or "Unknown"

        print(f"[Geocode] Resolved to city: {city}, state: {state}")
        return {"city": city, "state": state}

import requests
import os
from dotenv import load_dotenv 

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

class GoogleServicesAPI:
    BASE_URL = "https://maps.googleapis.com/maps/api"

    @staticmethod
    def fetch_places(selected_tags, location):
        """
        Fetch places based on tags and location coordinates.
        """
        try:
            response = requests.get(f"{GoogleServicesAPI.BASE_URL}/place/nearbysearch/json", params={
                "location": f"{location['latitude']},{location['longitude']}",
                "radius": 10000,  # Search radius in meters
                "type": "|".join(selected_tags),
                "key": GOOGLE_API_KEY,
            })
            response.raise_for_status()
            return response.json().get("results", [])
        except requests.exceptions.RequestException as e:
            print(f"Error fetching places: {e}")
            raise

    @staticmethod
    def fetch_city_coordinates(city):
        """
        Get latitude and longitude for a given city or address.
        """
        try:
            response = requests.get(f"{GoogleServicesAPI.BASE_URL}/geocode/json", params={
                "address": city,
                "key": GOOGLE_API_KEY,
            })
            response.raise_for_status()
            results = response.json().get("results", [])
            if not results:
                print(f"No results from Geocoding API for city: {city}")
                return None
            location = results[0]["geometry"]["location"]
            return {"latitude": location["lat"], "longitude": location["lng"]}
        except requests.exceptions.RequestException as e:
            print(f"Error fetching city coordinates: {e}")
            raise

    @staticmethod
    def reverse_geocode(latitude, longitude):
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "latlng": f"{latitude},{longitude}",
            "key": GOOGLE_API_KEY
        }

        response = requests.get(url, params=params)
        data = response.json()

        if not data.get("results"):
            print(f"[Geocode] No results for {latitude}, {longitude}")
            return None

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
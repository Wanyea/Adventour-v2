import requests

GOOGLE_API_KEY = "AIzaSyD-RpERPi4HTQl3oiTWtbgZTXVu-kyN4as"  

class GooglePlacesServices:
    BASE_URL = "https://maps.googleapis.com/maps/api"

    @staticmethod
    def fetch_places(selected_tags, location):
        """
        Fetch places based on tags and location coordinates.
        """
        try:
            response = requests.get(f"{GooglePlacesServices.BASE_URL}/place/nearbysearch/json", params={
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
            response = requests.get(f"{GooglePlacesServices.BASE_URL}/geocode/json", params={
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
        """
        Reverse geocode coordinates to get a city and state.
        """
        try:
            response = requests.get(f"{GooglePlacesServices.BASE_URL}/geocode/json", params={
                "latlng": f"{latitude},{longitude}",
                "key": GOOGLE_API_KEY,
            })
            response.raise_for_status()
            results = response.json().get("results", [])
            if not results:
                print(f"No results from Geocoding API for coordinates: {latitude}, {longitude}")
                return None

            city = None
            state = None

            # Extract city and state from address components
            for result in results:
                for component in result["address_components"]:
                    if "locality" in component["types"]:  # Look for city/locality
                        city = component["long_name"]
                    if "administrative_area_level_1" in component["types"]:  # Look for state
                        state = component["long_name"]
                if city and state:
                    break  # Exit the loop once both city and state are found

            if not city:
                print(f"City not found in results for coordinates: {latitude}, {longitude}")
            if not state:
                print(f"State not found in results for coordinates: {latitude}, {longitude}")

            return {"city": city, "state": state}
        except requests.exceptions.RequestException as e:
            print(f"Error reverse geocoding coordinates: {e}")
            raise


FOOD_TYPES = {
    "bakery",
    "bar",
    "breakfast_restaurant",
    "brunch_restaurant",
    "cafe",
    "coffee_shop",
    "dessert_restaurant",
    "fast_food_restaurant",
    "fine_dining_restaurant",
    "food",
    "ice_cream_shop",
    "meal_takeaway",
    "mexican_restaurant",
    "pizza_restaurant",
    "restaurant",
    "sandwich_shop",
    "steak_house",
    "tea_house",
}

ACTIVITY_TYPES = {
    "amusement_park",
    "aquarium",
    "art_gallery",
    "book_store",
    "campground",
    "comedy_club",
    "concert_hall",
    "hiking_area",
    "historical_landmark",
    "library",
    "market",
    "movie_theater",
    "museum",
    "night_club",
    "park",
    "performing_arts_theater",
    "shopping_mall",
    "spa",
    "tourist_attraction",
    "visitor_center",
    "zoo",
}

UTILITY_TYPES = {
    "atm",
    "bank",
    "car_dealer",
    "car_rental",
    "car_repair",
    "car_wash",
    "convenience_store",
    "electric_vehicle_charging_station",
    "gas_station",
    "parking",
    "pharmacy",
}

FOOD_NAME_HINTS = {
    "bakery",
    "bar",
    "bbq",
    "bistro",
    "burger",
    "cafe",
    "coffee",
    "culver",
    "deli",
    "diner",
    "donut",
    "grill",
    "kitchen",
    "pizza",
    "restaurant",
    "sandwich",
    "taco",
    "wawa",
}

UTILITY_NAME_HINTS = {
    "racetrac",
    "race trac",
    "speedway",
    "shell",
    "bp",
    "exxon",
    "mobil",
    "chevron",
    "citgo",
    "sunoco",
}


def _normalized_types(types):
    return {
        str(place_type).lower()
        for place_type in (types or [])
        if place_type
    }


def _has_food_signal(name, types):
    normalized_name = (name or "").lower()
    normalized_types = _normalized_types(types)
    return (
        bool(normalized_types.intersection(FOOD_TYPES))
        or any(place_type.endswith("_restaurant") for place_type in normalized_types)
        or any("food" in place_type for place_type in normalized_types)
        or any(hint in normalized_name for hint in FOOD_NAME_HINTS)
    )


def is_discoverable_candidate(name, types):
    """Return False for utility-only provider results Adventour should skip."""
    normalized_name = (name or "").lower()
    normalized_types = _normalized_types(types)

    if any(hint in normalized_name for hint in UTILITY_NAME_HINTS):
        return False
    if normalized_types.intersection(UTILITY_TYPES) and not (
        _has_food_signal(name, types) or normalized_types.intersection(ACTIVITY_TYPES)
    ):
        return False
    return True


def classify_recommendation_lane(name, types):
    """Return the Adventour browsing lane for a place recommendation.

    Provider categories are inconsistent for hybrid businesses like Wawa, so
    use both explicit type signals and conservative name hints.
    """
    if _has_food_signal(name, types):
        return "food"
    return "activity"

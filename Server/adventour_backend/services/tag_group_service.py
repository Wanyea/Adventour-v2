"""Existing app tag groups applied to the full local candidate pool."""

import re

GROUPS = {
    "food_drink": ({"bakery", "bar", "breakfast_restaurant", "brunch_restaurant", "fast_food_restaurant",
                    "fine_dining_restaurant", "meal_takeaway", "mexican_restaurant", "pizza_restaurant",
                    "restaurant", "sandwich_shop", "seafood_restaurant", "steak_house"},
                   ["bbq", "bistro", "burger", "deli", "diner", "grill", "kitchen", "pizza", "restaurant", "taco"]),
    "coffee_sweets": ({"cafe", "coffee_shop", "dessert_restaurant", "ice_cream_shop", "tea_house"},
                      ["cafe", "coffee", "donut", "ice cream", "tea"]),
    "arts_culture": ({"art_gallery", "historical_landmark", "library", "museum", "performing_arts_theater", "tourist_attraction"}, []),
    "outdoors": ({"aquarium", "campground", "hiking_area", "park", "tourist_attraction", "zoo"}, ["garden", "trail"]),
    "nightlife": ({"bar", "comedy_club", "concert_hall", "night_club"}, []),
    "entertainment": ({"amusement_park", "comedy_club", "concert_hall", "movie_theater", "performing_arts_theater"}, []),
    "shopping": ({"book_store", "clothing_store", "market", "shopping_mall"}, ["market", "boutique"]),
    "wellness": ({"spa"}, []),
    # Phase 2 must supply authenticity evidence. Unmapped or unpopular != gem.
    "local_gems": (set(), []),
}


def for_place(name, types):
    types = set(types)
    return [key for key, (allowed, hints) in GROUPS.items()
            if allowed & types or any(re.search(r"\b" + re.escape(hint) + r"\b", name or "", re.I) for hint in hints)]

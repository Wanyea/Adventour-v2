"""Replicate the app's tag matcher and check every category the index serves.

The nightclub bug was invisible from spot-checking one card. This walks every
basic_category actually present in the KEEP set, runs the same matching the app
does (types AND nameHints), and flags combinations that are obviously wrong.
"""

import os
import re
import sys

import psycopg2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "adventour_backend", "services"))
from local_index_service import _types_for  # noqa: E402

DSN = os.environ.get("ADVENTOUR_PG_DSN", "host=localhost port=5432 user=postgres dbname=adventour")

# Mirrored from AdventourApp/src/placeTagGroups.ts
TAG_GROUPS = {
    "food_drink": (["bakery", "bar", "breakfast_restaurant", "brunch_restaurant",
                    "fast_food_restaurant", "fine_dining_restaurant", "meal_takeaway",
                    "mexican_restaurant", "pizza_restaurant", "restaurant", "sandwich_shop",
                    "seafood_restaurant", "steak_house"],
                   ["bbq", "bistro", "burger", "deli", "diner", "grill", "kitchen", "pizza",
                    "restaurant", "taco"]),
    "coffee_sweets": (["cafe", "coffee_shop", "dessert_restaurant", "ice_cream_shop", "tea_house"],
                      ["cafe", "coffee", "donut", "ice cream", "tea"]),
    "arts_culture": (["art_gallery", "historical_landmark", "library", "museum",
                      "performing_arts_theater", "tourist_attraction"], []),
    "outdoors": (["aquarium", "campground", "hiking_area", "park", "tourist_attraction", "zoo"],
                 ["garden", "trail"]),
    "nightlife": (["bar", "comedy_club", "concert_hall", "night_club"], []),
    "entertainment": (["amusement_park", "comedy_club", "concert_hall", "movie_theater",
                       "performing_arts_theater"], []),
    "shopping": (["book_store", "clothing_store", "market", "shopping_mall"], ["market", "boutique"]),
    "wellness": (["spa"], []),
}

# Groups a category must NOT land in. Encodes the actual product meaning.
FORBIDDEN = {
    "night_club": {"arts_culture", "outdoors", "food_drink"},
    "dance_club": {"arts_culture", "outdoors", "food_drink"},
    "bar": {"arts_culture", "outdoors"},
    "restaurant": {"arts_culture", "outdoors", "nightlife"},
    "casual_eatery": {"arts_culture", "outdoors", "nightlife"},
    "museum": {"outdoors", "food_drink", "nightlife"},
    "art_gallery": {"outdoors", "food_drink", "nightlife"},
    "park": {"food_drink", "nightlife", "arts_culture"},
    "movie_theater": {"outdoors", "food_drink"},
    "amusement_park": {"arts_culture", "food_drink", "nightlife"},
    "national_park": {"arts_culture", "food_drink", "nightlife"},
    "beach": {"arts_culture", "food_drink", "nightlife"},
    "coffee_shop": {"arts_culture", "outdoors", "nightlife"},
    "cafe": {"arts_culture", "outdoors", "nightlife"},
}


def groups_for(name, types):
    t = {x.lower().replace(" ", "_") for x in types}
    n = (name or "").lower()
    out = []
    for gid, (gtypes, hints) in TAG_GROUPS.items():
        if any(x in t for x in gtypes) or any(h in n for h in hints):
            out.append(gid)
    return out


def main():
    with psycopg2.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("""SELECT basic_category, taxonomy_bucket, count(*)
                       FROM places WHERE tier='KEEP' AND basic_category IS NOT NULL
                       GROUP BY 1,2 ORDER BY 3 DESC""")
        rows = cur.fetchall()

    problems = 0
    print(f"{'category':<30}{'n':>7}  tag groups")
    for cat, bucket, n in rows:
        types = _types_for(cat, bucket)
        # Neutral name so nameHints cannot mask a bad type mapping.
        g = groups_for("", types)
        bad = FORBIDDEN.get(cat, set()) & set(g)
        flag = "  <-- WRONG: " + ",".join(sorted(bad)) if bad else ""
        if bad:
            problems += 1
        if n >= 40 or bad:
            print(f"  {cat:<28}{n:>7}  {','.join(g) or '(none)'}{flag}")

    print(f"\ncategories checked: {len(rows)}")
    print(f"forbidden-group violations: {problems}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

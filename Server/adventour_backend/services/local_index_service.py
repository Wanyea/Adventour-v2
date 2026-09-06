"""Serve recommendations from the Adventour-owned Postgres index.

This replaces provider-driven candidate retrieval. No paid API call is made to
build a deck -- the whole point of the sourcing decision in
docs/sourcing-cost-decision-brief.md.

It deliberately emits the *existing* /api/recommendations response shape so the
mobile client needs no changes. Per CLAUDE.md the UI is frozen: a recommender
change may alter what data a screen receives, never how the screen looks.

Ordering follows the Gate 8 finding: authenticity is a floor, not a ranker (490
places share one score), so results are filtered by score and then ordered
nearest-first within the radius the user asked for.
"""

import os

import h3
from sqlalchemy import text

# Matches Server/data_pipeline/authenticity.py. Duplicated rather than imported
# because the pipeline is not on the web app's import path; if it moves, these
# must move together.
AUTHENTICITY_FLOOR = 0.30
H3_RESOLUTION = 8

# Overture basic_category -> the Google-style type vocabulary the app's tag
# filters already understand (AdventourApp/src/placeTagGroups.ts). Anything
# unmapped still passes its raw category through, so nothing is silently lost.
CATEGORY_TO_TYPES = {
    "restaurant": ["restaurant"],
    "casual_eatery": ["restaurant"],
    "fast_food_restaurant": ["restaurant"],
    "cafe": ["cafe"],
    "coffee_shop": ["coffee_shop", "cafe"],
    "tea_house": ["tea_house", "cafe"],
    "bakery": ["bakery"],
    "dessert_shop": ["dessert_restaurant"],
    "ice_cream_shop": ["ice_cream_shop"],
    "bar": ["bar"],
    "brewery": ["bar"],
    "winery": ["bar"],
    "lounge": ["bar"],
    # Nightlife only. Mapping this to `bar` as well dragged nightclubs into
    # Food & Drink, which is not what anyone means by a night out.
    "night_club": ["night_club"],
    "dance_club": ["night_club"],
    "park": ["park"],
    "national_park": ["park"],
    "garden": ["park"],
    "beach": ["park"],
    "recreational_trail_or_path": ["hiking_area", "park"],
    "campground": ["campground"],
    "zoo": ["zoo"],
    "aquarium": ["aquarium"],
    "museum": ["museum"],
    "art_gallery": ["art_gallery"],
    "historic_site": ["historical_landmark"],
    "monument": ["historical_landmark"],
    "library": ["library"],
    "performing_arts_venue": ["performing_arts_theater"],
    "theatre_venue": ["performing_arts_theater"],
    "music_venue": ["concert_hall"],
    "comedy_club": ["comedy_club"],
    "movie_theater": ["movie_theater"],
    "amusement_park": ["amusement_park"],
    "water_park": ["amusement_park"],
    "bowling_alley": ["amusement_park"],
    "spa": ["spa"],
    "smoothie_juice_bar": ["cafe"],
    "non_alcoholic_beverage_venue": ["cafe"],
    "juice_bar": ["cafe"],
    "arcade": ["amusement_park"],
    "fairgrounds": ["amusement_park"],
    "playground": ["park"],
    "recreational_equipment_rental": ["hiking_area"],
    "theme_park": ["amusement_park"],
    "book_store": ["book_store"],
    "market": ["market"],
}

FOOD_BUCKETS = {"food_and_drink"}


def _types_for(basic_category, taxonomy_bucket):
    """Map an Overture category onto the app's tag-group vocabulary.

    Note what is NOT here: a blanket `tourist_attraction` for every place in the
    arts/entertainment or cultural buckets. `tourist_attraction` is a member of
    BOTH the Arts & Culture and Outdoors groups, so appending it by bucket put
    `Smiles Nite Club` under Arts & Culture and Outdoors. It is now attached only
    to categories that genuinely are visitor attractions, via CATEGORY_TO_TYPES.

    `taxonomy_bucket` is still accepted so callers need not change, but it no
    longer influences the type list.
    """
    types = list(CATEGORY_TO_TYPES.get(basic_category or "", []))
    if basic_category and basic_category not in types:
        # Keep the raw category for downstream use; it matches no tag group,
        # so it cannot pull a place into the wrong one.
        types.append(basic_category)
    return types


def is_enabled():
    return os.getenv("ADVENTOUR_USE_LOCAL_INDEX", "").lower() in ("1", "true", "yes")


SQL = text(
    """
    WITH candidates AS (
        SELECT DISTINCT ON (COALESCE(canonical_id, id))
               COALESCE(canonical_id, id) AS entity_id,
               id, name, basic_category, taxonomy_bucket, chain_class,
               authenticity, authenticity_why, cluster_size, loc_spread_m,
               COALESCE(canonical_lat, lat) AS lat,
               COALESCE(canonical_lon, lon) AS lon
        FROM places
        WHERE tier = 'KEEP'
          AND h3_r8 = ANY(:cells)
          AND authenticity >= :floor
          AND (:allow_chains OR chain_class <> 'chain')
        ORDER BY COALESCE(canonical_id, id), cluster_size DESC NULLS LAST,
                 authenticity DESC NULLS LAST
    )
    SELECT *,
           (6371000 * acos(least(1, greatest(-1,
                cos(radians(:lat)) * cos(radians(lat)) * cos(radians(lon) - radians(:lon))
              + sin(radians(:lat)) * sin(radians(lat)))))) AS distance_meters
    FROM candidates
    WHERE (6371000 * acos(least(1, greatest(-1,
                cos(radians(:lat)) * cos(radians(lat)) * cos(radians(lon) - radians(:lon))
              + sin(radians(:lat)) * sin(radians(lat)))))) <= :radius
    ORDER BY authenticity DESC, distance_meters ASC
    LIMIT :limit
    """
)


def _cells_for(latitude, longitude, radius_meters):
    """H3 disk covering the radius. r8 cells are ~460m across, so this is the
    cheap prefilter; the haversine clause above does the exact cut."""
    rings = max(1, min(24, int(radius_meters / 400) + 1))
    origin = h3.latlng_to_cell(latitude, longitude, H3_RESOLUTION)
    return list(h3.grid_disk(origin, rings))


def recommend(db, location, radius_meters=3200, constraints=None):
    constraints = constraints or {}
    lat = float(location["latitude"])
    lon = float(location["longitude"])
    limit = int(constraints.get("limit", 20))
    allow_chains = not bool(constraints.get("avoid_chains", False))

    rows = db.session.execute(
        SQL,
        {
            "cells": _cells_for(lat, lon, radius_meters),
            "floor": AUTHENTICITY_FLOOR,
            "allow_chains": allow_chains,
            "lat": lat,
            "lon": lon,
            "radius": float(radius_meters),
            "limit": limit,
        },
    ).mappings().all()

    recommendations = []
    for r in rows:
        distance = int(round(r["distance_meters"]))
        # Location is unreliable when a merged cluster's members disagreed; the
        # deck can still show it, but navigation should re-resolve at accept time.
        approximate = (r["loc_spread_m"] or 0) > 5000
        recommendations.append(
            {
                "place_id": r["entity_id"],
                "provider": "adventour_index",
                "provider_place_id": r["id"],
                "name": r["name"],
                "category": "food" if r["taxonomy_bucket"] in FOOD_BUCKETS else "activity",
                "score": round(float(r["authenticity"] or 0), 3),
                "explanation": r["authenticity_why"] or "",
                "latitude": float(r["lat"]),
                "longitude": float(r["lon"]),
                "distance_meters": distance,
                "approximate_location": approximate,
                "display": {
                    "name": r["name"],
                    "vicinity": f"{distance} m away"
                    + (" · approximate" if approximate else ""),
                    "types": _types_for(r["basic_category"], r["taxonomy_bucket"]),
                },
            }
        )
    return {"recommendations": recommendations, "provider_errors": []}

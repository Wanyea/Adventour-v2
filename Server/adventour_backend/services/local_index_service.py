"""Serve recommendations from the Adventour-owned Postgres index.

This replaces provider-driven candidate retrieval. No paid API call is made to
build a deck -- the whole point of the sourcing decision in
docs/sourcing-cost-decision-brief.md.

Phase 2 keeps the structural eligibility floor and ranks the full pool by
transparent personal fit. Tag and recent-decision exclusions precede the limit.
Structural inputs remain separate; neither score proves authenticity.
"""

import math

import h3
from sqlalchemy import text
from data_pipeline.authenticity import authenticity_score
from . import tag_group_service, personal_ranking_service

# Keep the production floor explicit for evaluation's default serving population.
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


SQL = text(
    """
    WITH candidates AS (
        SELECT DISTINCT ON (COALESCE(canonical_id, id))
               COALESCE(canonical_id, id) AS entity_id,
               id, name, basic_category, taxonomy_bucket, chain_class,
               authenticity, authenticity_why, cluster_size, loc_spread_m, metro,
               confidence, socials, needs_booking, score_components, score_density,
               (SELECT count(*) FROM places q WHERE q.h3_r8=p.h3_r8
                AND q.tier='KEEP' AND q.index_active) AS cell_density,
               COALESCE(canonical_lat, lat) AS lat,
               COALESCE(canonical_lon, lon) AS lon
        FROM places p
        WHERE tier = 'KEEP' AND index_active
          AND canonical_h3_r8 = ANY(:cells)
          AND authenticity >= :floor
          AND (:allow_chains OR chain_class <> 'chain')
          AND NOT EXISTS (SELECT 1 FROM place_provider_ref r JOIN suppressed_place s
                          ON s.google_place_id=r.google_place_id
                          WHERE r.entity_id=COALESCE(p.canonical_id,p.id))
          AND NOT EXISTS (SELECT 1 FROM place_event e WHERE e.entity_id=COALESCE(p.canonical_id,p.id)
                          AND e.event_type='closed_report' AND e.user_id IN (0,:user_id))
        ORDER BY COALESCE(canonical_id, id), cluster_size DESC NULLS LAST,
                 authenticity DESC NULLS LAST, id
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
    """
)


def _cells_for(latitude, longitude, radius_meters):
    """H3 disk covering the radius. r8 cells are ~460m across, so this is the
    cheap prefilter; the haversine clause above does the exact cut."""
    rings = max(1, int(radius_meters / 400) + 2)
    origin = h3.latlng_to_cell(latitude, longitude, H3_RESOLUTION)
    return list(h3.grid_disk(origin, rings))


def recommend(db, location, radius_meters=3200, constraints=None, user_id=0):
    constraints = constraints or {}
    lat = float(location["latitude"])
    lon = float(location["longitude"])
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Invalid latitude or longitude.")
    radius_meters = float(radius_meters)
    if not math.isfinite(radius_meters) or not 100 <= radius_meters <= 16000:
        raise ValueError("Radius must be between 100 and 16000 metres.")
    limit = max(1, min(50, int(constraints.get("limit", 20))))
    allow_chains = not bool(constraints.get("avoid_chains", False))
    selected_tag = constraints.get("tag_group", "all")
    if selected_tag != "all" and selected_tag not in tag_group_service.GROUPS:
        raise ValueError("Unknown tag group.")
    excluded = constraints.get("exclude_entity_ids", [])
    if not isinstance(excluded, list) or len(excluded) > 500 or any(not isinstance(s, str) for s in excluded):
        raise ValueError("exclude_entity_ids must contain at most 500 IDs.")

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
            "user_id": user_id,
        },
    ).mappings().all()

    history = personal_ranking_service.context(db, user_id)
    recommendations = []
    counts = {key: 0 for key in tag_group_service.GROUPS}
    for r in rows:
        if r["entity_id"] in excluded or r["entity_id"] in history['hidden']:
            continue
        types = _types_for(r["basic_category"], r["taxonomy_bucket"])
        groups = tag_group_service.for_place(r["name"], types)
        for group in groups:
            counts[group] += 1
        if selected_tag != "all" and selected_tag not in groups:
            continue
        distance = int(round(r["distance_meters"]))
        # Location is unreliable when a merged cluster's members disagreed; the
        # deck can still show it, but navigation should re-resolve at accept time.
        approximate = (r["loc_spread_m"] or 0) > 5000
        components = r["score_components"]
        if not components:
            reconstructed, candidate_components = authenticity_score(
                r["confidence"], bool(r["socials"]), r["cell_density"], r["chain_class"])
            if abs(reconstructed - float(r["authenticity"])) < .00001:
                components = candidate_components
        recommendations.append(personal_ranking_service.score(
            {
                "place_id": r["entity_id"],
                "provider": "adventour_index",
                "provider_place_id": r["id"],
                "name": r["name"],
                "category": "food" if r["taxonomy_bucket"] in FOOD_BUCKETS else "activity",
                "score": float(r["authenticity"] or 0),
                "structural_score": float(r["authenticity"] or 0),
                "score_components": components,
                "explanation": "Structural index score from source confidence, social-link presence and nearby indexed places. It is not a probability of liking this place.",
                "metro": r["metro"],
                "needs_booking": bool(r["needs_booking"]),
                "tag_groups": groups,
                "latitude": float(r["lat"]),
                "longitude": float(r["lon"]),
                "distance_meters": distance,
                "approximate_location": approximate,
                "display": {
                    "name": r["name"],
                    "vicinity": f"{distance} m away"
                    + (" · approximate" if approximate else ""),
                    "types": types,
                },
            }, history, radius_meters, r['chain_class']
        ))
    recommendations.sort(key=lambda p: (-p['score'], p['distance_meters'], p['place_id']))
    return {"recommendations": recommendations[:limit], "tag_group_counts": counts, "provider_errors": []}

import json
import math
from datetime import datetime

from adventour_backend.models import (
    db,
    Place,
    PlaceFeature,
    PlaceProviderRef,
    User,
    UserPlaceEvent,
    UserPreferenceVector,
)
from adventour_backend.providers.place_providers import ProviderRegistry
from adventour_backend.services.google_services_api import first_photo_url
from adventour_backend.services.place_classification import classify_recommendation_lane, is_discoverable_candidate
from adventour_backend.utils import is_chain, is_hidden_gem, review_sentiment_score


EVENT_WEIGHTS = {
    "impression": 0.1,
    "reject": -1.0,
    "accept": 2.0,
    "navigate": 3.0,
    "arrival": 5.0,
    "rate": 0.0,
    "save": 4.0,
    "share": 4.0,
}

TAG_GROUP_SEARCH_TYPES = {
    "food_drink": [
        "restaurant",
        "breakfast_restaurant",
        "brunch_restaurant",
        "bakery",
        "bar",
    ],
    "coffee_sweets": [
        "cafe",
        "coffee_shop",
        "dessert_restaurant",
        "ice_cream_shop",
        "tea_house",
    ],
    "arts_culture": [
        "museum",
        "art_gallery",
        "historical_landmark",
        "performing_arts_theater",
        "tourist_attraction",
    ],
    "outdoors": [
        "park",
        "hiking_area",
        "garden",
        "zoo",
        "aquarium",
    ],
    "nightlife": [
        "bar",
        "night_club",
        "comedy_club",
        "concert_hall",
    ],
    "entertainment": [
        "amusement_park",
        "movie_theater",
        "concert_hall",
        "performing_arts_theater",
        "comedy_club",
    ],
    "shopping": [
        "market",
        "book_store",
        "clothing_store",
        "shopping_mall",
    ],
    "wellness": [
        "spa",
    ],
    "local_gems": [
        "tourist_attraction",
        "restaurant",
        "park",
        "art_gallery",
        "market",
    ],
}


def _json_loads(value, default=None):
    if not value:
        return default if default is not None else {}
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default if default is not None else {}


def _json_dumps(value):
    return json.dumps(value or {}, sort_keys=True)


def _normalize_name(name):
    return " ".join((name or "").lower().strip().split())


def _haversine_meters(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None

    radius = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _clamp(value, minimum=0.0, maximum=1.0):
    return max(minimum, min(maximum, value))


def _expand_preference_tag(tag):
    normalized = (tag or "").strip()
    return TAG_GROUP_SEARCH_TYPES.get(normalized, [normalized] if normalized else [])


def _travel_time_estimates(distance_meters):
    if distance_meters is None:
        return None

    return {
        "walk_minutes": max(1, round(distance_meters / 80)),
        "drive_minutes": max(1, round(distance_meters / 500)),
        "transit_minutes": max(2, round(distance_meters / 300) + 5),
    }


class RecommendationService:
    """Build preference vectors, score places, and log recommendation events."""

    def __init__(self, provider_registry=None):
        self.provider_registry = provider_registry or ProviderRegistry()

    def recommend(self, user, location, radius_meters=3200, member_ids=None, constraints=None, mode="spontaneous"):
        constraints = constraints or {}
        members = self._resolve_members(user, member_ids or [])

        member_vectors = {
            member.id: self.build_preference_vector(member)
            for member in members
        }
        query_tags = self._query_tags(member_vectors.values(), user)

        raw_candidates, provider_errors = self.provider_registry.search(
            query_tags,
            location,
            radius_meters=radius_meters,
            constraints=constraints,
        )

        decided_place_ids = self._decided_place_ids(user) if constraints.get("exclude_decided", True) else set()
        scored, skipped_decided = self._score_candidates(
            raw_candidates=raw_candidates,
            user=user,
            members=members,
            member_vectors=member_vectors,
            constraints=constraints,
            location=location,
            radius_meters=radius_meters,
            mode=mode,
            decided_place_ids=decided_place_ids,
            allow_decided=False,
        )

        repeated_decided = False
        if not scored and skipped_decided and constraints.get("repeat_decided_on_exhaustion", True):
            scored, _ = self._score_candidates(
                raw_candidates=skipped_decided,
                user=user,
                members=members,
                member_vectors=member_vectors,
                constraints=constraints,
                location=location,
                radius_meters=radius_meters,
                mode=mode,
                decided_place_ids=set(),
                allow_decided=True,
            )
            repeated_decided = bool(scored)

        db.session.commit()
        scored.sort(key=lambda item: item["score"], reverse=True)
        return {
            "mode": mode,
            "member_count": len(members),
            "query_tags": query_tags,
            "provider_errors": provider_errors,
            "repeated_decided": repeated_decided,
            "recommendations": scored[: constraints.get("limit", 20)],
        }

    def record_event(self, user, place, event_type, provider_ref=None, event_value=None, context="solo", metadata=None, commit=True):
        if event_type not in EVENT_WEIGHTS:
            raise ValueError(f"Unsupported event_type: {event_type}")

        event = UserPlaceEvent(
            user_id=user.id,
            place_id=place.id,
            provider_ref_id=provider_ref.id if provider_ref else None,
            event_type=event_type,
            event_value=event_value,
            context=context,
            metadata_json=_json_dumps(metadata),
        )
        db.session.add(event)

        if commit:
            self.rebuild_preference_vector(user, commit=False)
            db.session.commit()

        return event

    def _score_candidates(
        self,
        raw_candidates,
        user,
        members,
        member_vectors,
        constraints,
        location,
        radius_meters,
        mode,
        decided_place_ids,
        allow_decided=False,
    ):
        scored = []
        skipped_decided = []
        seen_place_ids = set()

        for candidate in raw_candidates:
            if not is_discoverable_candidate(
                candidate.get("name"),
                candidate.get("types") or candidate.get("categories") or [],
            ):
                continue

            place, provider_ref, feature = self.upsert_candidate(candidate)
            if not place or place.id in seen_place_ids:
                continue
            seen_place_ids.add(place.id)
            if place.id in decided_place_ids and not allow_decided:
                skipped_decided.append(candidate)
                continue

            distance_meters = _haversine_meters(
                location.get("latitude"),
                location.get("longitude"),
                place.latitude,
                place.longitude,
            )
            if distance_meters is not None and distance_meters > radius_meters:
                continue

            score = self._score_place(
                feature=feature,
                candidate=candidate,
                member_vectors=member_vectors,
                constraints=constraints,
                distance_meters=distance_meters,
                radius_meters=radius_meters,
                mode=mode,
            )
            if score["score"] <= 0:
                continue

            self.record_event(
                user=user,
                place=place,
                provider_ref=provider_ref,
                event_type="impression",
                context="group" if len(members) > 1 else "solo",
                metadata={
                    "mode": mode,
                    "score": score["score"],
                    "repeat_after_exhaustion": allow_decided,
                },
                commit=False,
            )

            scored.append({
                "place_id": place.id,
                "provider": candidate.get("provider"),
                "provider_place_id": candidate.get("place_id") or candidate.get("fsq_id"),
                "name": place.canonical_name,
                "category": self._recommendation_category(candidate),
                "latitude": place.latitude,
                "longitude": place.longitude,
                "distance_meters": round(distance_meters) if distance_meters is not None else None,
                "travel_times": _travel_time_estimates(distance_meters),
                "score": round(score["score"], 3),
                "components": score["components"],
                "explanation": score["explanation"],
                "display": self._display_payload(candidate),
                "repeat_after_exhaustion": allow_decided,
            })

        return scored, skipped_decided

    def build_preference_vector(self, user):
        existing = UserPreferenceVector.query.filter_by(user_id=user.id, vector_type="phase1").first()
        if existing:
            return _json_loads(existing.vector_json, default={})
        return self.rebuild_preference_vector(user)

    def rebuild_preference_vector(self, user, commit=True):
        vector = {
            "categories": {},
            "cuisines": {},
            "activities": {},
            "avoid_chains": 0.75,
            "hidden_gem_affinity": 0.75,
            "price_preference": None,
        }

        if user.preferences:
            for tag in [tag.strip() for tag in user.preferences.split(",") if tag.strip()]:
                expanded_tags = _expand_preference_tag(tag)
                weight = 1.0 / max(len(expanded_tags), 1)
                for expanded_tag in expanded_tags:
                    vector["categories"][expanded_tag] = vector["categories"].get(expanded_tag, 0) + weight

        events = (
            UserPlaceEvent.query
            .filter_by(user_id=user.id)
            .order_by(UserPlaceEvent.occurred_at.asc())
            .all()
        )

        for event in events:
            feature = PlaceFeature.query.filter_by(place_id=event.place_id).first()
            if not feature:
                continue

            weight = EVENT_WEIGHTS.get(event.event_type, 0)
            if event.event_type == "rate" and event.event_value is not None:
                weight = (float(event.event_value) - 3.0) * 2.0

            self._apply_weight(vector["categories"], _json_loads(feature.category_vector), weight)
            self._apply_weight(vector["cuisines"], _json_loads(feature.cuisine_vector), weight)
            self._apply_weight(vector["activities"], _json_loads(feature.activity_vector), weight)

            if feature.chain_probability > 0.7 and weight < 0:
                vector["avoid_chains"] = _clamp(vector["avoid_chains"] + 0.05)
            if feature.hidden_gem_score > 0.6 and weight > 0:
                vector["hidden_gem_affinity"] = _clamp(vector["hidden_gem_affinity"] + 0.05)

        self._normalize_vector(vector["categories"])
        self._normalize_vector(vector["cuisines"])
        self._normalize_vector(vector["activities"])

        row = UserPreferenceVector.query.filter_by(user_id=user.id, vector_type="phase1").first()
        if not row:
            row = UserPreferenceVector(user_id=user.id, vector_type="phase1", vector_json=_json_dumps(vector))
            db.session.add(row)
        else:
            row.vector_json = _json_dumps(vector)
            row.updated_at = datetime.utcnow()

        if commit:
            db.session.commit()

        return vector

    def upsert_candidate(self, candidate):
        provider = candidate.get("provider", "unknown")
        provider_place_id = candidate.get("place_id") or candidate.get("fsq_id") or candidate.get("id")
        adventour_place_id = candidate.get("adventour_place_id")

        if adventour_place_id:
            place = Place.query.get(adventour_place_id)
        else:
            existing_ref = None
            if provider_place_id:
                existing_ref = PlaceProviderRef.query.filter_by(
                    provider=provider,
                    provider_place_id=provider_place_id,
                ).first()
            place = existing_ref.place if existing_ref else None

        if not place:
            name = candidate.get("name") or "Unknown place"
            lat, lng = self._candidate_lat_lng(candidate)
            place = Place(
                canonical_name=name,
                normalized_name=_normalize_name(name),
                latitude=lat,
                longitude=lng,
                source_confidence=0.7 if provider != "local" else 1.0,
            )
            db.session.add(place)
            db.session.flush()

        provider_ref = None
        if provider_place_id:
            provider_ref = PlaceProviderRef.query.filter_by(
                provider=provider,
                provider_place_id=str(provider_place_id),
            ).first()
            if not provider_ref:
                provider_ref = PlaceProviderRef(
                    place_id=place.id,
                    provider=provider,
                    provider_place_id=str(provider_place_id),
                    attribution_required=provider != "local",
                )
                db.session.add(provider_ref)

        feature = PlaceFeature.query.filter_by(place_id=place.id).first()
        derived = self._derive_features(candidate)
        if not feature:
            feature = PlaceFeature(place_id=place.id, **derived)
            db.session.add(feature)
        else:
            for key, value in derived.items():
                setattr(feature, key, value)

        return place, provider_ref, feature

    def _resolve_members(self, user, member_ids):
        ids = {user.id}
        ids.update(int(member_id) for member_id in member_ids if member_id)
        return User.query.filter(User.id.in_(ids)).all()

    def _decided_place_ids(self, user):
        events = (
            UserPlaceEvent.query
            .filter(
                UserPlaceEvent.user_id == user.id,
                UserPlaceEvent.event_type.in_(["accept", "reject"]),
            )
            .all()
        )
        return {event.place_id for event in events}

    def _query_tags(self, vectors, fallback_user):
        scores = {}
        for vector in vectors:
            for tag, value in vector.get("categories", {}).items():
                scores[tag] = scores.get(tag, 0) + value

        if not scores and fallback_user.preferences:
            expanded = []
            for tag in [tag.strip() for tag in fallback_user.preferences.split(",") if tag.strip()]:
                expanded.extend(_expand_preference_tag(tag))
            return list(dict.fromkeys(expanded))[:5]

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return [tag for tag, _ in ranked[:5]] or ["restaurant", "tourist_attraction", "park"]

    def _score_place(self, feature, candidate, member_vectors, constraints, distance_meters, radius_meters, mode):
        member_fits = [
            self._member_fit(feature, vector)
            for vector in member_vectors.values()
        ]
        personal_fit = member_fits[0] if member_fits else 0
        group_average = sum(member_fits) / len(member_fits) if member_fits else personal_fit
        disagreement = max(member_fits) - min(member_fits) if len(member_fits) > 1 else 0
        group_fit = _clamp(group_average - (0.35 * disagreement))

        authenticity = _clamp(
            (feature.authenticity_score or 0)
            + (feature.hidden_gem_score or 0) * 0.25
            - (feature.chain_probability or 0) * 0.35
            - (feature.tourist_trap_score or 0) * 0.25
        )
        quality = self._quality_score(feature, candidate)
        context_fit = self._context_fit(distance_meters, radius_meters, mode)
        novelty = 0.5

        chain_penalty = 0.25 if constraints.get("avoid_chains", True) and feature.chain_probability > 0.7 else 0
        price_penalty = self._price_penalty(feature, constraints)

        score = (
            personal_fit * 0.30
            + group_fit * 0.20
            + authenticity * 0.20
            + quality * 0.15
            + context_fit * 0.10
            + novelty * 0.05
            - chain_penalty
            - price_penalty
        )

        components = {
            "personal_fit": round(personal_fit, 3),
            "group_fit": round(group_fit, 3),
            "authenticity": round(authenticity, 3),
            "quality": round(quality, 3),
            "context_fit": round(context_fit, 3),
            "novelty": round(novelty, 3),
            "chain_penalty": round(chain_penalty, 3),
            "price_penalty": round(price_penalty, 3),
        }
        return {
            "score": _clamp(score),
            "components": components,
            "explanation": self._explain(components, feature),
        }

    def _member_fit(self, feature, vector):
        category_fit = self._cosine_like(_json_loads(feature.category_vector), vector.get("categories", {}))
        cuisine_fit = self._cosine_like(_json_loads(feature.cuisine_vector), vector.get("cuisines", {}))
        activity_fit = self._cosine_like(_json_loads(feature.activity_vector), vector.get("activities", {}))
        return _clamp((category_fit * 0.65) + (cuisine_fit * 0.20) + (activity_fit * 0.15))

    def _derive_features(self, candidate):
        types = candidate.get("types") or candidate.get("categories") or []
        if isinstance(types, str):
            types = [types]

        category_vector = {str(tag): 1.0 for tag in types}
        name = candidate.get("name", "")
        chain_probability = 1.0 if is_chain(name) else 0.0
        hidden_gem = 1.0 if is_hidden_gem(candidate) else 0.0
        sentiment = review_sentiment_score(candidate.get("reviews", []))
        rating = candidate.get("rating") or 0
        ratings_total = candidate.get("user_ratings_total") or 0
        quality = _clamp((float(rating) / 5.0) if rating else 0.5)
        popularity = _clamp(math.log10(ratings_total + 1) / 4.0)
        authenticity = _clamp(0.65 + hidden_gem * 0.25 + sentiment * 0.2 - chain_probability * 0.5 - popularity * 0.1)

        return {
            "category_vector": _json_dumps(category_vector),
            "cuisine_vector": _json_dumps({}),
            "activity_vector": _json_dumps({}),
            "price_band": candidate.get("price_level") or candidate.get("price"),
            "chain_probability": chain_probability,
            "authenticity_score": authenticity,
            "hidden_gem_score": hidden_gem,
            "tourist_trap_score": _clamp(popularity - 0.65),
            "quality_score_adventour": quality,
            "popularity_score_adventour": popularity,
            "feature_version": "phase1",
        }

    def _candidate_lat_lng(self, candidate):
        geometry = candidate.get("geometry") or {}
        location = geometry.get("location") or {}
        geocodes = candidate.get("geocodes") or {}
        main = geocodes.get("main") or {}
        return (
            location.get("lat") or main.get("latitude"),
            location.get("lng") or main.get("longitude"),
        )

    def _display_payload(self, candidate):
        photos = candidate.get("photos") or []
        return {
            "name": candidate.get("name"),
            "vicinity": candidate.get("vicinity") or (candidate.get("location") or {}).get("formatted_address"),
            "rating": candidate.get("rating"),
            "user_ratings_total": candidate.get("user_ratings_total"),
            "price_level": candidate.get("price_level") or candidate.get("price"),
            "business_status": candidate.get("business_status"),
            "types": candidate.get("types") or candidate.get("categories") or [],
            "photo_url": first_photo_url(photos),
            "photo_attributions": photos[0].get("author_attributions", []) if photos else [],
        }

    def _recommendation_category(self, candidate):
        return classify_recommendation_lane(
            candidate.get("name"),
            candidate.get("types") or candidate.get("categories") or [],
        )

    def _quality_score(self, feature, candidate):
        provider_rating = candidate.get("rating")
        if provider_rating:
            return _clamp(float(provider_rating) / 5.0)
        return _clamp(feature.quality_score_adventour or 0.5)

    def _context_fit(self, distance_meters, radius_meters, mode):
        if distance_meters is None or not radius_meters:
            return 0.5
        closeness = 1 - (distance_meters / radius_meters)
        if mode == "spontaneous":
            return _clamp(closeness)
        return _clamp(0.5 + closeness * 0.5)

    def _price_penalty(self, feature, constraints):
        price_max = constraints.get("price_max")
        if price_max is None or feature.price_band is None:
            return 0
        return 0.2 if feature.price_band > price_max else 0

    def _explain(self, components, feature):
        reasons = []
        if components["personal_fit"] >= 0.7:
            reasons.append("strong match for your saved taste")
        if components["group_fit"] >= 0.7:
            reasons.append("good fit for the group")
        if components["authenticity"] >= 0.7:
            reasons.append("local/authentic signal is high")
        if feature.hidden_gem_score >= 0.7:
            reasons.append("hidden-gem candidate")
        if components["chain_penalty"] > 0:
            reasons.append("chain penalty applied")
        if components["context_fit"] >= 0.7:
            reasons.append("close enough for this Adventour")

        if not reasons:
            reasons.append("balanced recommendation across taste, quality, and context")
        return "; ".join(reasons) + "."

    def _apply_weight(self, target, source, weight):
        for key, value in source.items():
            target[key] = target.get(key, 0) + (float(value) * weight)

    def _normalize_vector(self, vector):
        if not vector:
            return
        max_abs = max(abs(value) for value in vector.values()) or 1
        for key in list(vector.keys()):
            normalized = vector[key] / max_abs
            if abs(normalized) < 0.05:
                del vector[key]
            else:
                vector[key] = round(normalized, 4)

    def _cosine_like(self, left, right):
        if not left or not right:
            return 0.0
        numerator = sum(float(left.get(key, 0)) * float(right.get(key, 0)) for key in left.keys())
        left_norm = math.sqrt(sum(float(value) ** 2 for value in left.values()))
        right_norm = math.sqrt(sum(float(value) ** 2 for value in right.values()))
        if not left_norm or not right_norm:
            return 0.0
        return _clamp((numerator / (left_norm * right_norm) + 1) / 2)

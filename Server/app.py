from flask import Flask, request, jsonify, g, redirect
from flask_cors import CORS
from adventour_backend.services.google_services_api import GoogleServicesAPI
from adventour_backend.models import (
    db,
    User,
    UserTagFeedback,
    PlaceRating,
    Place,
    PlaceProviderRef,
    UserPlaceEvent,
    PlaceFeature,
    LocalEvent,
    LocalEventInterest,
    AdventourSession,
    AdventourStop,
    TravelReservation,
)
from adventour_backend.auth import require_auth, optional_auth
from adventour_backend.social_routes import accepted_friend_ids, social_bp
from adventour_backend.services.recommender_service import RecommendationService, SCORING_PROFILES
from adventour_backend.services.itinerary_service import ItineraryRecommendationService
from adventour_backend.services.local_event_service import LocalEventRecommendationService
from adventour_backend.services.recommender_evaluation_service import RecommendationEvaluationService
from adventour_backend.services.travel_logistics_service import TravelLogisticsService
from adventour_backend.services.google_services_api import first_photo_url
from adventour_backend.services.account_service import delete_user_account_data

from dotenv import load_dotenv
from urllib.parse import quote_plus
from datetime import date, datetime, timezone
from sqlalchemy import func, inspect, text
from copy import deepcopy
import os
import logging
import json

env_file = os.getenv("ENV_FILE")
if env_file:
    load_dotenv(env_file, override=True)
else:
    local_env_file = os.path.join(os.path.dirname(__file__), ".env.local")
    load_dotenv(local_env_file if os.path.exists(local_env_file) else None, override=True)

logger = logging.getLogger(__name__)
GROUP_ROUTE_UNDERSERVED_FIT_THRESHOLD = 0.55


def place_display_payload(candidate):
    photos = candidate.get("photos") or []
    return {
        "name": candidate.get("name"),
        "vicinity": candidate.get("vicinity") or candidate.get("formatted_address") or (candidate.get("location") or {}).get("formatted_address"),
        "rating": candidate.get("rating"),
        "user_ratings_total": candidate.get("user_ratings_total"),
        "price_level": candidate.get("price_level") or candidate.get("price"),
        "business_status": candidate.get("business_status"),
        "types": candidate.get("types") or candidate.get("categories") or [],
        "photo_url": first_photo_url(photos),
        "photo_attributions": photos[0].get("author_attributions", []) if photos else [],
    }

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = quote_plus(os.getenv("DB_PASSWORD") or "")
DB_NAME = os.getenv("DB_NAME")
CONNECTION_NAME = os.getenv("DB_CONNECTION_NAME")

if os.getenv("DATABASE_URL"):
    DATABASE_URI = os.getenv("DATABASE_URL")
elif DB_USER and DB_NAME and os.getenv("GAE_ENV", "").startswith("standard"):
    DB_HOST = "localhost"
    DATABASE_URI = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"
elif DB_USER and DB_NAME:
    DB_HOST = "127.0.0.1"
    DATABASE_URI = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:3306/{DB_NAME}"
else:
    DATABASE_URI = "sqlite:///adventour_dev.db"

# Debug
print(f"Connecting to database: {DATABASE_URI}")

# Flask app setup
app = Flask(__name__)
CORS(app)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URI
if os.getenv("GAE_ENV", "").startswith("standard"):
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {
            "unix_socket": f"/cloudsql/{CONNECTION_NAME}"
        }
    }

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

# Register blueprints
app.register_blueprint(social_bp, url_prefix='/api')
recommendation_service = RecommendationService()
local_event_service = LocalEventRecommendationService()
recommendation_evaluation_service = RecommendationEvaluationService()
travel_logistics_service = TravelLogisticsService()
itinerary_service = ItineraryRecommendationService(recommendation_service, local_event_service, travel_logistics_service)


def ensure_local_schema():
    """Keep existing local dev databases usable until proper migrations land."""
    inspector = inspect(db.engine)
    user_columns = {column["name"] for column in inspector.get_columns(User.__tablename__)}
    if "date_of_birth" in user_columns:
        return

    table_name = db.engine.dialect.identifier_preparer.quote(User.__tablename__)
    with db.engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN date_of_birth DATE"))


# Initialize the database
with app.app_context():
    db.create_all()
    ensure_local_schema()

@app.route('/')
def home():
    """
    Root route to inform users about API usage.
    """
    return jsonify({
        "message": "This is the Adventour API. Refer to the documentation for available endpoints."
    })

@app.route('/api/dev/config', methods=['GET'])
def dev_config():
    if os.getenv("ADVENTOUR_DEV_AUTH") != "true":
        return jsonify({"error": "Dev tools are disabled"}), 403

    google_key = os.getenv("GOOGLE_API_KEY") or ""
    return jsonify({
        "database_url": app.config["SQLALCHEMY_DATABASE_URI"],
        "google_api_key_configured": bool(google_key),
        "google_api_key_preview": f"{google_key[:4]}...{google_key[-4:]}" if google_key else None,
    })

def get_request_user(allow_legacy_id=False):
    if hasattr(g, 'current_user'):
        return g.current_user

    if allow_legacy_id:
        user_id = (request.json or {}).get('user_id') if request.is_json else request.args.get('user_id')
        if user_id:
            return User.query.filter_by(uuid=user_id).first()

    return None

def parse_json_object(value, fallback=None):
    if not value:
        return fallback if fallback is not None else {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else (fallback if fallback is not None else {})
    except (TypeError, ValueError):
        return fallback if fallback is not None else {}

def compact_metadata_value(value):
    if isinstance(value, dict):
        cleaned = compact_metadata(value)
        return cleaned if cleaned else None
    if isinstance(value, list):
        cleaned_items = []
        for item in value:
            cleaned_item = compact_metadata_value(item)
            if cleaned_item is not None:
                cleaned_items.append(cleaned_item)
        return cleaned_items if cleaned_items else None
    if value is None or value == "":
        return None
    return value

def compact_metadata(metadata):
    cleaned = {}
    for key, value in (metadata or {}).items():
        cleaned_value = compact_metadata_value(value)
        if cleaned_value is not None:
            cleaned[key] = cleaned_value
    return cleaned

def isoformat_or_none(value):
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")

def booking_summary_from_reservations(reservations, party_size=1):
    party_size = max(1, int(party_size or 1))
    type_counts = {}
    type_costs = {}
    total_known_cost = 0.0
    known_cost_count = 0
    confirmation_count = 0
    booking_link_count = 0
    currencies = set()

    for reservation in reservations:
        reservation_type = reservation.reservation_type or "other"
        type_counts[reservation_type] = type_counts.get(reservation_type, 0) + 1
        if reservation.confirmation_code:
            confirmation_count += 1
        if reservation.booking_url:
            booking_link_count += 1
        if reservation.currency:
            currencies.add(reservation.currency)
        if reservation.cost_total is not None:
            cost = float(reservation.cost_total or 0)
            total_known_cost += cost
            known_cost_count += 1
            type_costs[reservation_type] = round(type_costs.get(reservation_type, 0.0) + cost, 2)

    currency = next(iter(currencies)) if len(currencies) == 1 else ("mixed" if currencies else "USD")
    readiness_score = 0.0
    if reservations:
        readiness_score = min(
            1.0,
            0.35
            + (confirmation_count / len(reservations)) * 0.3
            + (booking_link_count / len(reservations)) * 0.15
            + (known_cost_count / len(reservations)) * 0.2,
        )

    if not reservations:
        status = "empty"
        message = "No booking details have been saved for this Adventour yet."
    elif readiness_score >= 0.85:
        status = "ready"
        message = "Saved booking details include confirmations, links, and costs."
    elif confirmation_count or booking_link_count or known_cost_count:
        status = "partial"
        message = "Some booking details are saved; add missing confirmations, links, or costs when available."
    else:
        status = "needs_details"
        message = "Booking placeholders are saved, but confirmations, links, and costs are still missing."

    return {
        "status": status,
        "message": message,
        "party_size": party_size,
        "reservation_count": len(reservations),
        "confirmation_count": confirmation_count,
        "booking_link_count": booking_link_count,
        "known_cost_count": known_cost_count,
        "currency": currency,
        "total_known_cost": round(total_known_cost, 2),
        "known_cost_per_person": round(total_known_cost / party_size, 2),
        "type_counts": type_counts,
        "type_costs": type_costs,
        "readiness_score": round(readiness_score, 3),
    }

def booking_component_reservation_types(component):
    component_type = (component or {}).get("type")
    if component_type == "event_or_place":
        return ["place", "event"]
    return [component_type] if component_type else []

def booking_component_needs_reservation(component):
    if not (component or {}).get("stores_reservation"):
        return False
    return (component or {}).get("status") not in {"not_needed_for_day_trip", "optional_for_day_trip"}

def booking_component_label(component):
    component = component or {}
    component_type = component.get("type")
    if component_type == "local_transport":
        return "Local travel"
    if component_type == "event_or_place":
        return "Tickets/events"
    return component.get("label") or str(component_type or "Booking detail").replace("_", " ").title()

def reservation_type_for_coverage_item(item):
    reservation_types = item.get("reservation_types") or []
    if "event" in reservation_types:
        return "event"
    if reservation_types:
        return reservation_types[0]
    return "other"

def trip_packet_command_center_with_reservation_coverage(command_center, missing_items):
    command_center = dict(command_center or {})
    existing_commands = [
        command
        for command in command_center.get("commands") or []
        if not str(command.get("id") or "").startswith("missing_booking_")
    ]
    reservation_commands = [
        {
            "id": f"missing_booking_{item.get('id') or index}",
            "phase": "save",
            "label": f"Save {item.get('label') or 'booking detail'}",
            "detail": "Add the confirmation, booking link, or cost so this Adventour can travel with the details.",
            "status": "action_needed",
            "action": "Save booking details in Adventour",
            "component_type": item.get("id") or "reservation",
            "reservation_type": reservation_type_for_coverage_item(item),
            "provider_label": None,
            "source_url": None,
            "priority": 2 + index,
            "can_open": False,
            "can_save": True,
        }
        for index, item in enumerate(missing_items or [], start=1)
    ]

    if not reservation_commands and not command_center:
        return command_center

    commands = [*reservation_commands, *existing_commands]
    visible_commands = commands[:6]
    primary_action = visible_commands[0] if visible_commands else None
    ready_count = sum(1 for item in visible_commands if item.get("status") == "ready")
    action_count = sum(1 for item in visible_commands if item.get("status") == "action_needed")
    open_count = sum(1 for item in visible_commands if item.get("can_open"))
    save_count = sum(1 for item in visible_commands if item.get("can_save"))
    status = "action_needed" if reservation_commands else command_center.get("status", "manual")

    return {
        **command_center,
        "status": status,
        "headline": (
            f"Next best move: {primary_action.get('label')}."
            if reservation_commands and primary_action
            else command_center.get("headline")
        ),
        "primary_action": primary_action,
        "commands": visible_commands,
        "command_count": len(commands),
        "ready_count": ready_count,
        "action_needed_count": action_count,
        "open_link_count": open_count,
        "save_prompt_count": save_count,
    }

def trip_packet_with_reservation_coverage(trip_packet, booking_plan, reservations, party_size=1):
    trip_packet = dict(trip_packet or {})
    booking_plan = booking_plan or {}
    reservations = list(reservations or [])
    components = [
        component
        for component in booking_plan.get("components") or []
        if booking_component_needs_reservation(component)
    ]

    coverage_items = []
    for component in components:
        reservation_types = booking_component_reservation_types(component)
        matched = [
            reservation
            for reservation in reservations
            if reservation.reservation_type in reservation_types
        ]
        confirmed_count = sum(
            1
            for reservation in matched
            if reservation.confirmation_code or reservation.booking_url or reservation.cost_total is not None
        )
        coverage_items.append({
            "id": component.get("id") or component.get("type"),
            "label": booking_component_label(component),
            "reservation_types": reservation_types,
            "saved_count": len(matched),
            "confirmed_count": confirmed_count,
            "status": "saved" if matched else "missing",
        })

    saved_count = sum(1 for item in coverage_items if item["saved_count"] > 0)
    confirmed_count = sum(1 for item in coverage_items if item["confirmed_count"] > 0)
    missing_items = [
        item
        for item in coverage_items
        if item["saved_count"] == 0
    ]
    missing_labels = [item["label"] for item in missing_items]
    reservation_summary = booking_summary_from_reservations(reservations, party_size)
    coverage = {
        "required_count": len(coverage_items),
        "saved_count": saved_count,
        "confirmed_count": confirmed_count,
        "attached_count": len(reservations),
        "missing_labels": missing_labels,
        "items": coverage_items,
        "summary": reservation_summary,
    }

    existing_stats = [
        stat
        for stat in trip_packet.get("quick_stats") or []
        if stat.get("id") not in {"attached_reservations", "saved_reservations", "confirmed_reservations"}
    ]
    quick_stats = [
        {
            "id": "attached_reservations",
            "label": "Saved bookings",
            "value": len(reservations),
            "status": "ready" if reservations else "manual",
        },
        {
            "id": "saved_reservations",
            "label": "Trip pieces saved",
            "value": f"{saved_count}/{len(coverage_items)}" if coverage_items else len(reservations),
            "status": "ready" if coverage_items and not missing_labels else "manual",
        },
        {
            "id": "confirmed_reservations",
            "label": "Confirmed",
            "value": reservation_summary["confirmation_count"],
            "status": "ready" if reservation_summary["confirmation_count"] else "manual",
        },
        *existing_stats,
    ]

    reservation_actions = [
        {
            "id": f"missing_booking_{index}",
            "label": f"Save {label}",
            "detail": "Add the confirmation, booking link, or cost so this Adventour can travel with the details.",
            "status": "action_needed",
        }
        for index, label in enumerate(missing_labels, start=1)
    ]
    existing_actions = [
        action
        for action in trip_packet.get("required_actions") or []
        if not str(action.get("id") or "").startswith("missing_booking_")
    ]

    current_checklist = trip_packet.get("booking_checklist") or {}
    checklist_items = [
        item
        for item in current_checklist.get("items") or []
        if item.get("id") != "saved_confirmations"
    ]
    if coverage_items or reservations:
        confirmation_item = {
            "id": "saved_confirmations",
            "label": "Saved confirmations",
            "status": "action_needed" if missing_labels else "ready",
            "detail": (
                f"{saved_count}/{len(coverage_items)} trip pieces saved. Missing {', '.join(missing_labels[:3])}."
                if missing_labels
                else f"{len(reservations)} booking detail{'s' if len(reservations) != 1 else ''} attached to this Adventour."
            ),
            "action": (
                f"Save {missing_labels[0]} details before launch."
                if missing_labels
                else "Review saved booking details, then launch this Adventour."
            ),
            "blocking": False,
            "required_count": len(coverage_items),
            "saved_count": saved_count,
            "confirmed_count": confirmed_count,
            "missing_labels": missing_labels,
        }
        checklist_items.append(confirmation_item)

    if current_checklist and checklist_items:
        ready_count = sum(1 for item in checklist_items if item.get("status") == "ready")
        action_count = sum(1 for item in checklist_items if item.get("status") in {"action_needed", "manual"})
        blocking_count = sum(1 for item in checklist_items if item.get("blocking"))
        trip_packet["booking_checklist"] = {
            **current_checklist,
            "items": checklist_items,
            "ready_count": ready_count,
            "action_count": action_count,
            "blocking_count": blocking_count,
            "status": "needs_details" if blocking_count else ("ready_with_manual_steps" if action_count else "ready"),
            "next_action": (
                f"Save {missing_labels[0]} details before launch."
                if missing_labels
                else current_checklist.get("next_action")
            ),
        }

    trip_packet["reservation_coverage"] = coverage
    trip_packet["quick_stats"] = quick_stats[:7]
    trip_packet["required_actions"] = [*reservation_actions, *existing_actions][:5]
    if missing_items or trip_packet.get("booking_command_center"):
        trip_packet["booking_command_center"] = trip_packet_command_center_with_reservation_coverage(
            trip_packet.get("booking_command_center"),
            missing_items,
        )
    if missing_labels:
        trip_packet["status"] = "action_needed" if trip_packet.get("status") != "blocked" else "blocked"
        trip_packet["headline"] = "Save booking details so this Adventour can travel with confirmations."
        primary_action = (trip_packet.get("booking_command_center") or {}).get("primary_action") or {}
        trip_packet["next_step"] = primary_action.get("label") or f"Save {missing_labels[0]} details before launch."
    elif reservations and trip_packet.get("status") not in {"blocked", "needs_details"}:
        trip_packet["status"] = "ready"
        trip_packet["headline"] = trip_packet.get("headline") or "Saved booking details are attached to this Adventour packet."
        trip_packet["next_step"] = trip_packet.get("next_step") or "Review saved booking details, then launch this Adventour."

    return trip_packet

def date_or_none(value):
    if not value:
        return None
    return value.isoformat()

def parse_birthdate(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None

def is_at_least_13(birthdate):
    today = date.today()
    age = today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))
    return age >= 13

def display_name_taken(display_name, user_id=None):
    normalized = display_name.strip().lower()
    query = User.query.filter(func.lower(User.display_name) == normalized)
    if user_id:
        query = query.filter(User.id != user_id)
    return query.first() is not None

def serialize_user(user):
    preferences = user.preferences.split(',') if user.preferences else []
    return {
        "id": user.id,
        "firebase_uid": user.firebase_uid,
        "email": user.email,
        "username": user.username,
        "display_name": user.display_name,
        "date_of_birth": date_or_none(user.date_of_birth),
        "profile_picture": user.profile_picture,
        "preferences": preferences,
        "profile_complete": bool(user.display_name and user.date_of_birth),
    }

def resolve_place_reference(data):
    adventour_place_id = data.get("place_id")
    provider = data.get("provider")
    provider_place_id = data.get("provider_place_id")

    place = db.session.get(Place, adventour_place_id) if adventour_place_id else None
    provider_ref = None
    if provider and provider_place_id:
        provider_ref = PlaceProviderRef.query.filter_by(
            provider=provider,
            provider_place_id=str(provider_place_id),
        ).first()
        if not place and provider_ref:
            place = provider_ref.place

    if not provider_ref and place:
        provider_ref = PlaceProviderRef.query.filter_by(place_id=place.id).first()

    return place, provider_ref

def recommendation_metadata_snapshot(recommendation, include_swap_context=False):
    recommendation = recommendation or {}
    display = recommendation.get("display") or {}
    if not display.get("name") and recommendation.get("name"):
        display = {**display, "name": recommendation.get("name")}

    snapshot = {
        "place_id": recommendation.get("place_id"),
        "provider": recommendation.get("provider"),
        "provider_place_id": recommendation.get("provider_place_id"),
        "name": recommendation.get("name"),
        "score": recommendation.get("score"),
        "display": display,
        "diversity_groups": recommendation.get("diversity_groups"),
        "tag_groups": recommendation.get("tag_groups"),
        "tags": recommendation.get("tags"),
        "authenticity_evidence": recommendation.get("authenticity_evidence"),
        "party_fit_summary": recommendation.get("party_fit_summary"),
        "score_components": recommendation.get("score_components") or recommendation.get("components"),
        "distance_meters": recommendation.get("distance_meters"),
        "estimated_duration_minutes": recommendation.get("estimated_duration_minutes"),
        "estimated_cost": recommendation.get("estimated_cost"),
        "price_level": recommendation.get("price_level"),
    }
    if include_swap_context:
        snapshot.update({
            "swap_impact": recommendation.get("swap_impact"),
            "why_this_stop": recommendation.get("why_this_stop"),
            "local_event_matches": recommendation.get("local_event_matches"),
        })
    return compact_metadata(snapshot)

def itinerary_stop_metadata(stop_payload, recommendation, source="planned_itinerary"):
    stop_payload = stop_payload or {}
    recommendation = recommendation or stop_payload
    metadata = {
        "source": source,
        "slot_id": stop_payload.get("slot_id"),
        "slot_label": stop_payload.get("label"),
        "time_window": stop_payload.get("time_window"),
        "role": stop_payload.get("role"),
        "day": stop_payload.get("day"),
        "day_title": stop_payload.get("day_title"),
        "swap_history": stop_payload.get("swap_history"),
        "swap_hint": stop_payload.get("swap_hint"),
        "why_this_stop": stop_payload.get("why_this_stop") or recommendation.get("why_this_stop"),
        "party_fit_summary": stop_payload.get("party_fit_summary") or recommendation.get("party_fit_summary"),
        "local_event_matches": (stop_payload.get("local_event_matches") or recommendation.get("local_event_matches") or [])[:3],
    }
    metadata.update(recommendation_metadata_snapshot(recommendation))

    alternatives = stop_payload.get("alternatives") or recommendation.get("alternatives") or []
    if alternatives:
        metadata["alternatives"] = [
            recommendation_metadata_snapshot(alternative, include_swap_context=True)
            for alternative in alternatives[:3]
        ]

    return compact_metadata(metadata)

def resolve_or_upsert_recommendation_place(recommendation):
    place, provider_ref = resolve_place_reference(recommendation)
    if place:
        return place, provider_ref

    candidate = dict(recommendation or {})
    display = candidate.get("display") or {}
    if not candidate.get("name") and display.get("name"):
        candidate["name"] = display.get("name")
    if not candidate.get("provider_place_id") and candidate.get("id"):
        candidate["provider_place_id"] = candidate.get("id")
    if candidate.get("provider_place_id") and not candidate.get("place_id"):
        candidate["place_id"] = candidate.get("provider_place_id")
    if display.get("latitude") is not None and candidate.get("latitude") is None:
        candidate["latitude"] = display.get("latitude")
    if display.get("longitude") is not None and candidate.get("longitude") is None:
        candidate["longitude"] = display.get("longitude")

    if not candidate.get("name"):
        return None, None

    place, provider_ref, _ = recommendation_service.upsert_candidate(candidate)
    return place, provider_ref

def serialize_adventour_stop(stop):
    metadata = parse_json_object(stop.metadata_json)
    display = metadata.get("display") or {}
    place = stop.place
    provider_ref = stop.provider_ref
    duration_seconds = None
    if stop.arrived_at:
        end_time = stop.departed_at or datetime.utcnow()
        duration_seconds = max(0, int((end_time - stop.arrived_at).total_seconds()))

    return {
        "id": stop.id,
        "session_id": stop.session_id,
        "place_id": stop.place_id,
        "provider": provider_ref.provider if provider_ref else metadata.get("provider"),
        "provider_place_id": provider_ref.provider_place_id if provider_ref else metadata.get("provider_place_id"),
        "order_index": stop.order_index,
        "status": stop.status,
        "selected_at": isoformat_or_none(stop.selected_at),
        "navigation_started_at": isoformat_or_none(stop.navigation_started_at),
        "arrived_at": isoformat_or_none(stop.arrived_at),
        "departed_at": isoformat_or_none(stop.departed_at),
        "duration_seconds": duration_seconds,
        "rating": stop.rating,
        "notes": stop.notes,
        "metadata": metadata,
        "display": {
            "name": display.get("name") or (place.canonical_name if place else None),
            "vicinity": display.get("vicinity"),
            "types": display.get("types") or [],
            "photo_url": display.get("photo_url"),
            "photo_attributions": display.get("photo_attributions") or [],
            "rating": display.get("rating"),
            "user_ratings_total": display.get("user_ratings_total"),
            "price_level": display.get("price_level"),
            "latitude": display.get("latitude") or (place.latitude if place else None),
            "longitude": display.get("longitude") or (place.longitude if place else None),
        },
    }

def first_active_adventour_stop(session):
    return (
        AdventourStop.query
        .filter(
            AdventourStop.session_id == session.id,
            AdventourStop.status.in_(("planned", "navigating", "arrived")),
        )
        .order_by(AdventourStop.order_index.asc())
        .first()
    )

def append_stop_swap_summary(session, stop_metadata, previous_snapshot, alternative_snapshot):
    summary = parse_json_object(session.summary_json)
    swap_summary = summary.get("swap_summary") if isinstance(summary.get("swap_summary"), dict) else {}
    swapped_slots = list(swap_summary.get("swapped_slots") or [])
    slot_id = stop_metadata.get("slot_id")
    swapped_at = datetime.utcnow().isoformat() + "Z"
    swap_entry = {
        "day": stop_metadata.get("day"),
        "slot_id": slot_id,
        "slot_label": stop_metadata.get("slot_label"),
        "from_place_id": previous_snapshot.get("place_id"),
        "from_name": previous_snapshot.get("name") or (previous_snapshot.get("display") or {}).get("name"),
        "to_place_id": alternative_snapshot.get("place_id"),
        "to_name": alternative_snapshot.get("name") or (alternative_snapshot.get("display") or {}).get("name"),
        "swapped_at": swapped_at,
        "impact": alternative_snapshot.get("swap_impact"),
    }
    if slot_id:
        swapped_slots = [
            existing for existing in swapped_slots
            if existing.get("slot_id") != slot_id
        ]
    swapped_slots.append(compact_metadata(swap_entry))
    swap_summary["swapped_slots"] = swapped_slots
    swap_summary["swapped_stop_count"] = len(swapped_slots)
    summary["swap_summary"] = compact_metadata(swap_summary)
    session.summary_json = json.dumps(summary)
    return swap_entry

def serialize_adventour_session(session, include_stops=True):
    stops = session.stops.all() if include_stops else []
    active_stops = [
        stop for stop in stops
        if stop.status in ("planned", "navigating", "arrived")
    ]
    active_stop = active_stops[0] if active_stops else None
    reservations = session.travel_reservations.order_by(
        TravelReservation.starts_at.asc().nullslast(),
        TravelReservation.created_at.desc(),
    ).all()
    summary = parse_json_object(session.summary_json)
    planned_party_size = (
        ((summary.get("price_breakdown") or {}).get("party_size"))
        or (len(parse_json_object(session.companion_user_ids_json, {"ids": []}).get("ids", [])) + 1)
    )
    return {
        "id": session.id,
        "title": session.title,
        "status": session.status,
        "started_at": isoformat_or_none(session.started_at),
        "ended_at": isoformat_or_none(session.ended_at),
        "companion_user_ids": parse_json_object(session.companion_user_ids_json, {"ids": []}).get("ids", []),
        "summary": summary,
        "stops": [serialize_adventour_stop(stop) for stop in stops],
        "active_stop": serialize_adventour_stop(active_stop) if active_stop else None,
        "reservations": [serialize_travel_reservation(reservation) for reservation in reservations],
        "booking_summary": booking_summary_from_reservations(reservations, planned_party_size),
    }

def serialize_travel_reservation(reservation):
    return {
        "id": reservation.id,
        "user_id": reservation.user_id,
        "adventour_session_id": reservation.adventour_session_id,
        "reservation_type": reservation.reservation_type,
        "title": reservation.title,
        "provider": reservation.provider,
        "confirmation_code": reservation.confirmation_code,
        "starts_at": isoformat_or_none(reservation.starts_at),
        "ends_at": isoformat_or_none(reservation.ends_at),
        "cost_total": reservation.cost_total,
        "currency": reservation.currency,
        "booking_url": reservation.booking_url,
        "notes": reservation.notes,
        "metadata": parse_json_object(reservation.metadata_json),
        "created_at": isoformat_or_none(reservation.created_at),
        "updated_at": isoformat_or_none(reservation.updated_at),
    }

def local_event_social_payload(event_id, user_id=None):
    counts = {
        "interested_count": 0,
        "going_count": 0,
        "viewer_status": None,
    }
    rows = (
        db.session.query(LocalEventInterest.status, func.count(LocalEventInterest.id))
        .filter(LocalEventInterest.event_id == event_id)
        .group_by(LocalEventInterest.status)
        .all()
    )
    for status, count in rows:
        if status == "going":
            counts["going_count"] = int(count)
        elif status == "interested":
            counts["interested_count"] = int(count)

    if user_id:
        viewer_interest = LocalEventInterest.query.filter_by(
            event_id=event_id,
            user_id=user_id,
        ).first()
        counts["viewer_status"] = viewer_interest.status if viewer_interest else None
    return counts

def parse_optional_datetime(value, field_name):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO timestamp") from exc

def apply_reservation_payload(reservation, data):
    if "title" in data:
        title = (data.get("title") or "").strip()
        if not title:
            raise ValueError("title is required")
        reservation.title = title

    if "reservation_type" in data:
        reservation_type = (data.get("reservation_type") or "").strip()
        supported_types = {"flight", "stay", "local_transport", "event", "place"}
        if reservation_type not in supported_types:
            raise ValueError(f"reservation_type must be one of {', '.join(sorted(supported_types))}")
        reservation.reservation_type = reservation_type

    if "adventour_session_id" in data:
        reservation.adventour_session_id = data.get("adventour_session_id")
    if "provider" in data:
        reservation.provider = data.get("provider")
    if "confirmation_code" in data:
        reservation.confirmation_code = data.get("confirmation_code")
    if "starts_at" in data:
        reservation.starts_at = parse_optional_datetime(data.get("starts_at"), "starts_at")
    if "ends_at" in data:
        reservation.ends_at = parse_optional_datetime(data.get("ends_at"), "ends_at")
    if "cost_total" in data:
        cost_total = data.get("cost_total")
        if cost_total in (None, ""):
            reservation.cost_total = None
        else:
            try:
                reservation.cost_total = float(cost_total)
            except (TypeError, ValueError) as exc:
                raise ValueError("cost_total must be numeric") from exc
    if "currency" in data:
        reservation.currency = data.get("currency") or "USD"
    if "booking_url" in data:
        reservation.booking_url = data.get("booking_url")
    if "notes" in data:
        reservation.notes = data.get("notes")
    if "metadata" in data:
        reservation.metadata_json = json.dumps(data.get("metadata") if isinstance(data.get("metadata"), dict) else {})

def refresh_adventour_booking_packet(session):
    if not session:
        return None

    summary = parse_json_object(session.summary_json)
    if not summary:
        return None

    reservations = session.travel_reservations.order_by(
        TravelReservation.starts_at.asc().nullslast(),
        TravelReservation.created_at.desc(),
    ).all()
    party_size = (
        (summary.get("price_breakdown") or {}).get("party_size")
        or (summary.get("trip_packet") or {}).get("party_size")
        or (len(parse_json_object(session.companion_user_ids_json, {"ids": []}).get("ids", [])) + 1)
        or 1
    )
    summary["booking_summary"] = booking_summary_from_reservations(reservations, party_size)
    summary["trip_packet"] = trip_packet_with_reservation_coverage(
        summary.get("trip_packet"),
        summary.get("booking_plan"),
        reservations,
        party_size,
    )
    session.summary_json = json.dumps(summary)
    return summary

@app.route('/onboarding', methods=['POST'])
@optional_auth
def onboarding():
    data = request.json
    tags = data.get('initial_tags', [])

    if not tags:
        return jsonify({"error": "Missing tags"}), 400

    # Try to get authenticated user first
    user = None
    if hasattr(g, 'current_user'):
        user = g.current_user
    else:
        # Fallback to old user_id parameter
        user_id = data.get('user_id')
        if user_id:
            user = User.query.filter_by(uuid=user_id).first()
            if not user:
                user = User(uuid=user_id, preferences=",".join(tags))
                db.session.add(user)
    
    if not user:
        return jsonify({"error": "User authentication required"}), 401

    user.preferences = ",".join(tags)
    recommendation_service.rebuild_preference_vector(user, commit=False)
    db.session.commit()
    return jsonify({"message": "Onboarding preferences saved"}), 200

@app.route('/user/<user_id>', methods=['GET'])
@optional_auth
def get_user_info(user_id):
    # Try to get authenticated user first
    user = None
    if hasattr(g, 'current_user'):
        user = g.current_user
    else:
        # Fallback to user_id parameter
        user = User.query.filter_by(uuid=user_id).first()
    
    if not user:
        return jsonify({"onboarded": False, "profile_complete": False}), 200
    
    return jsonify({
        "onboarded": bool(user.preferences),
        "preferences": user.preferences.split(',') if user.preferences else [],
        "profile_complete": bool(user.display_name and user.date_of_birth),
        "user_id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "user": serialize_user(user),
    }), 200

@app.route('/user', methods=['POST'])
@require_auth
def create_user():
    """Create a new user from Firebase data"""
    data = request.json
    user = g.current_user
    
    # Update user with provided data
    if data.get('display_name'):
        display_name = data['display_name'].strip()
        if not display_name:
            return jsonify({"error": "display_name is required"}), 400
        if display_name_taken(display_name, user.id):
            return jsonify({"error": "That display name is already taken"}), 409
        user.display_name = display_name
    if data.get('profile_picture'):
        user.profile_picture = data['profile_picture']
    if data.get('date_of_birth'):
        birthdate = parse_birthdate(data.get('date_of_birth'))
        if not birthdate:
            return jsonify({"error": "date_of_birth must be YYYY-MM-DD"}), 400
        if not is_at_least_13(birthdate):
            return jsonify({"error": "You must be at least 13 to use Adventour"}), 400
        user.date_of_birth = birthdate
    
    db.session.commit()
    
    return jsonify({
        "message": "User created successfully",
        "user": serialize_user(user),
    }), 201

@app.route('/user/dev', methods=['POST'])
def create_dev_user():
    """Create or return a local development user without Firebase."""
    if os.getenv("ADVENTOUR_DEV_AUTH") != "true":
        return jsonify({"error": "Dev auth is disabled"}), 403

    data = request.json or {}
    email = data.get("email") or "dev@adventour.local"
    display_name = data.get("display_name") or email.split("@")[0]
    firebase_uid = f"dev-{email.split('@')[0]}"

    user = User.query.filter_by(firebase_uid=firebase_uid).first()
    if not user:
        username = email.split("@")[0]
        user = User(
            firebase_uid=firebase_uid,
            email=email,
            username=username,
            display_name=display_name,
        )
        db.session.add(user)
    else:
        user.email = email
        user.display_name = display_name

    db.session.commit()

    return jsonify({
        "user": serialize_user(user)
    }), 200

@app.route('/user/profile', methods=['PUT'])
@require_auth
def update_user_profile():
    """Update user profile"""
    data = request.json
    user = g.current_user
    
    if data.get('display_name'):
        display_name = data['display_name'].strip()
        if not display_name:
            return jsonify({"error": "display_name is required"}), 400
        if display_name_taken(display_name, user.id):
            return jsonify({"error": "That display name is already taken"}), 409
        user.display_name = display_name
    if data.get('profile_picture'):
        user.profile_picture = data['profile_picture']
    if data.get('date_of_birth'):
        birthdate = parse_birthdate(data.get('date_of_birth'))
        if not birthdate:
            return jsonify({"error": "date_of_birth must be YYYY-MM-DD"}), 400
        if not is_at_least_13(birthdate):
            return jsonify({"error": "You must be at least 13 to use Adventour"}), 400
        user.date_of_birth = birthdate
    
    db.session.commit()
    
    return jsonify({
        "message": "Profile updated successfully",
        "user": serialize_user(user),
    }), 200

@app.route('/user/me', methods=['DELETE'])
@app.route('/user/me/reset', methods=['POST'])
@require_auth
def delete_current_user():
    """Delete the current user's Adventour account data from the backend."""
    user = g.current_user
    deleted = delete_user_account_data(user)
    db.session.commit()

    return jsonify({
        "message": "User account deleted",
        "deleted": deleted,
    }), 200

@app.route('/feedback', methods=['POST'])
@optional_auth
def save_feedback():
    data = request.json
    user_uuid = data.get('user_id')
    
    # Try to get authenticated user first
    user = None
    if hasattr(g, 'current_user'):
        user = g.current_user
    elif user_uuid:
        # Fallback to old UUID-based system
        user = User.query.filter_by(uuid=user_uuid).first()
        if not user:
            user = User(uuid=user_uuid)
            db.session.add(user)
            db.session.commit()
    
    if not user:
        return jsonify({"error": "User authentication required"}), 401

    feedback = UserTagFeedback(
        user_id=user.id,
        place_id=data['place_id'],
        verdict=data['feedback'],  # 'accept' or 'reject'
        place_tags=",".join(data['tags']),
    )
    db.session.add(feedback)

    place = None
    provider_ref = None
    provider_place_id = data.get('provider_place_id') or data.get('place_id')
    provider = data.get('provider', 'google')
    if provider_place_id:
        provider_ref = PlaceProviderRef.query.filter_by(
            provider=provider,
            provider_place_id=str(provider_place_id)
        ).first()
        place = provider_ref.place if provider_ref else None
    if place:
        recommendation_service.record_event(
            user=user,
            place=place,
            provider_ref=provider_ref,
            event_type=data['feedback'],
            context=data.get('context', 'solo'),
            metadata={"legacy_feedback": True, "tags": data.get('tags', [])},
            commit=False,
        )
        recommendation_service.rebuild_preference_vector(user, commit=False)

    db.session.commit()
    return jsonify({"message": "Feedback saved successfully!"}), 201

@app.route('/places/rate', methods=['POST'])
@require_auth
def rate_place():
    """Rate a place with 1-5 stars and optional review"""
    data = request.json
    user = g.current_user
    
    place_id = data.get('place_id')
    rating = data.get('rating')
    review = data.get('review', '')
    
    if not place_id or not rating:
        return jsonify({"error": "Place ID and rating are required"}), 400
    
    if not isinstance(rating, int) or rating < 1 or rating > 5:
        return jsonify({"error": "Rating must be an integer between 1 and 5"}), 400
    
    # Check if user already rated this place
    existing_rating = PlaceRating.query.filter_by(
        user_id=user.id, 
        place_id=place_id
    ).first()
    
    if existing_rating:
        # Update existing rating
        existing_rating.rating = rating
        existing_rating.review = review
        existing_rating.updated_at = datetime.utcnow()
    else:
        # Create new rating
        place_rating = PlaceRating(
            user_id=user.id,
            place_id=place_id,
            rating=rating,
            review=review
        )
        db.session.add(place_rating)

    provider = data.get('provider', 'google')
    provider_ref = PlaceProviderRef.query.filter_by(
        provider=provider,
        provider_place_id=str(place_id)
    ).first()
    if provider_ref:
        recommendation_service.record_event(
            user=user,
            place=provider_ref.place,
            provider_ref=provider_ref,
            event_type="rate",
            event_value=rating,
            context=data.get('context', 'solo'),
            metadata={"review_present": bool(review)},
            commit=False,
        )
        recommendation_service.rebuild_preference_vector(user, commit=False)
    
    db.session.commit()
    return jsonify({"message": "Place rated successfully!"}), 201

@app.route('/api/events', methods=['POST'])
@require_auth
def record_place_event():
    data = request.json or {}
    user = g.current_user
    event_type = data.get("event_type")
    adventour_place_id = data.get("place_id")
    provider = data.get("provider")
    provider_place_id = data.get("provider_place_id")

    if not event_type:
        return jsonify({"error": "event_type is required"}), 400

    place = None
    provider_ref = None

    if adventour_place_id:
        place = Place.query.get(adventour_place_id)
    if provider and provider_place_id:
        provider_ref = PlaceProviderRef.query.filter_by(
            provider=provider,
            provider_place_id=str(provider_place_id)
        ).first()
        if not place and provider_ref:
            place = provider_ref.place

    if not place:
        return jsonify({"error": "Unknown place. Request recommendations before recording events."}), 404

    try:
        recommendation_service.record_event(
            user=user,
            place=place,
            provider_ref=provider_ref,
            event_type=event_type,
            event_value=data.get("event_value"),
            context=data.get("context", "solo"),
            metadata=data.get("metadata", {}),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"message": "Event recorded"}), 201

@app.route('/api/adventours/active', methods=['GET'])
@require_auth
def get_active_adventour():
    session = (
        AdventourSession.query
        .filter_by(user_id=g.current_user.id, status="active")
        .order_by(AdventourSession.started_at.desc())
        .first()
    )
    return jsonify({"adventour": serialize_adventour_session(session) if session else None}), 200

@app.route('/api/adventours', methods=['POST'])
@require_auth
def start_adventour():
    data = request.json or {}
    user = g.current_user

    existing = AdventourSession.query.filter_by(user_id=user.id, status="active").first()
    if existing:
        return jsonify({"adventour": serialize_adventour_session(existing), "message": "Active Adventour resumed"}), 200

    title = data.get("title") or f"{user.display_name or user.username or 'My'} Adventour"
    companion_ids = data.get("companion_user_ids") or []
    session = AdventourSession(
        user_id=user.id,
        title=title,
        companion_user_ids_json=json.dumps({"ids": companion_ids}),
    )
    db.session.add(session)
    db.session.commit()

    return jsonify({"adventour": serialize_adventour_session(session), "message": "Adventour started"}), 201

@app.route('/api/adventours/<int:session_id>/stops', methods=['POST'])
@require_auth
def add_adventour_stop(session_id):
    data = request.json or {}
    user = g.current_user
    session = AdventourSession.query.filter_by(id=session_id, user_id=user.id, status="active").first()
    if not session:
        return jsonify({"error": "Active Adventour not found"}), 404

    place, provider_ref = resolve_place_reference(data)
    if not place:
        return jsonify({"error": "Unknown place. Request recommendations before adding a stop."}), 404

    active_stop = (
        AdventourStop.query
        .filter(
            AdventourStop.session_id == session.id,
            AdventourStop.status.in_(("planned", "navigating", "arrived")),
        )
        .order_by(AdventourStop.order_index.desc())
        .first()
    )
    if active_stop:
        return jsonify({
            "error": "Finish or skip the current stop before choosing another place.",
            "active_stop": serialize_adventour_stop(active_stop),
        }), 409

    order_index = session.stops.count()
    display = data.get("display") or {}
    metadata = itinerary_stop_metadata(
        data,
        data,
        source=data.get("source") or "recommendation_deck",
    )
    stop = AdventourStop(
        session_id=session.id,
        place_id=place.id,
        provider_ref_id=provider_ref.id if provider_ref else None,
        order_index=order_index,
        status="navigating",
        navigation_started_at=datetime.utcnow(),
        metadata_json=json.dumps(metadata),
    )
    db.session.add(stop)
    recommendation_service.record_event(
        user=user,
        place=place,
        provider_ref=provider_ref,
        event_type="navigate",
        context="adventour",
        metadata={"adventour_session_id": session.id, "display": display},
        commit=False,
    )
    db.session.commit()

    return jsonify({
        "adventour": serialize_adventour_session(session),
        "stop": serialize_adventour_stop(stop),
        "message": "Stop added",
    }), 201

@app.route('/api/adventours/from-itinerary', methods=['POST'])
@require_auth
def start_adventour_from_itinerary():
    data = request.json or {}
    user = g.current_user

    existing = AdventourSession.query.filter_by(user_id=user.id, status="active").first()
    if existing:
        return jsonify({
            "error": "End your active Adventour before starting a planned route.",
            "adventour": serialize_adventour_session(existing),
        }), 409

    stops = data.get("stops") or []
    if not stops:
        return jsonify({"error": "At least one itinerary stop is required"}), 400

    summary_payload = {
        "source": "planned_itinerary",
        "destination": data.get("destination"),
        "scoring_profile": data.get("scoring_profile"),
        "trip_style": data.get("trip_style"),
        "pace": data.get("pace"),
        "budget_profile": data.get("budget_profile"),
        "query_tags": data.get("query_tags") or [],
        "route_readiness": data.get("route_readiness"),
        "route_explanation": data.get("route_explanation"),
        "launch_checklist": data.get("launch_checklist"),
        "local_events": data.get("local_events"),
        "filter_summary": data.get("filter_summary"),
        "learned_rerank": data.get("learned_rerank"),
        "swap_summary": data.get("swap_summary"),
        "scenario_readiness": data.get("scenario_readiness"),
        "destination_scout": data.get("destination_scout"),
        "price_breakdown": data.get("price_breakdown"),
        "booking_plan": data.get("booking_plan"),
        "trip_packet": data.get("trip_packet"),
    }

    session = AdventourSession(
        user_id=user.id,
        title=data.get("title") or f"{user.display_name or user.username or 'My'} Planned Adventour",
        companion_user_ids_json=json.dumps({"ids": data.get("companion_user_ids") or []}),
        summary_json=json.dumps(summary_payload),
    )
    db.session.add(session)
    db.session.flush()

    created_stops = []
    for index, stop_payload in enumerate(stops):
        recommendation = stop_payload.get("recommendation") or stop_payload
        place, provider_ref = resolve_place_reference(recommendation)
        if not place:
            db.session.rollback()
            return jsonify({"error": "Unknown itinerary place. Rebuild the plan and try again."}), 404

        display = recommendation.get("display") or {}
        if not display.get("name"):
            display["name"] = recommendation.get("name")
            recommendation["display"] = display
        metadata = itinerary_stop_metadata(stop_payload, recommendation)
        created_stop = AdventourStop(
            session_id=session.id,
            place_id=place.id,
            provider_ref_id=provider_ref.id if provider_ref else None,
            order_index=index,
            status="planned",
            metadata_json=json.dumps(metadata),
        )
        db.session.add(created_stop)
        created_stops.append(created_stop)

    reservation_ids = data.get("reservation_ids") or []
    claimed_reservation_count = 0
    reservations = []
    if reservation_ids:
        reservations = (
            TravelReservation.query
            .filter(
                TravelReservation.user_id == user.id,
                TravelReservation.id.in_(reservation_ids),
            )
            .all()
        )
        found_ids = {reservation.id for reservation in reservations}
        missing_ids = [reservation_id for reservation_id in reservation_ids if reservation_id not in found_ids]
        if missing_ids:
            db.session.rollback()
            return jsonify({"error": "One or more reservations were not found"}), 404

        already_attached = [
            reservation.id
            for reservation in reservations
            if reservation.adventour_session_id is not None
        ]
        if already_attached:
            db.session.rollback()
            return jsonify({"error": "One or more reservations are already attached to an Adventour"}), 409

        for reservation in reservations:
            reservation.adventour_session_id = session.id
            claimed_reservation_count += 1

    if reservations:
        party_size = (
            (summary_payload.get("price_breakdown") or {}).get("party_size")
            or (summary_payload.get("trip_packet") or {}).get("party_size")
            or 1
        )
        summary_payload["booking_summary"] = booking_summary_from_reservations(reservations, party_size)
        summary_payload["trip_packet"] = trip_packet_with_reservation_coverage(
            summary_payload.get("trip_packet"),
            summary_payload.get("booking_plan"),
            reservations,
            party_size,
        )
        session.summary_json = json.dumps(summary_payload)

    db.session.commit()

    return jsonify({
        "message": "Planned Adventour started",
        "adventour": serialize_adventour_session(session),
        "stops": [serialize_adventour_stop(stop) for stop in created_stops],
        "claimed_reservation_count": claimed_reservation_count,
    }), 201

@app.route('/api/adventours/<int:session_id>/stops/<int:stop_id>/swap', methods=['POST'])
@require_auth
def swap_adventour_stop(session_id, stop_id):
    data = request.json or {}
    user = g.current_user
    session = AdventourSession.query.filter_by(id=session_id, user_id=user.id, status="active").first()
    stop = AdventourStop.query.filter_by(id=stop_id, session_id=session_id).first() if session else None
    if not session or not stop:
        return jsonify({"error": "Active Adventour stop not found"}), 404
    if stop.status != "planned":
        return jsonify({"error": "Only planned stops can be swapped before navigation starts."}), 409

    metadata = parse_json_object(stop.metadata_json)
    alternatives = metadata.get("alternatives") or []
    if not alternatives:
        return jsonify({"error": "This stop does not have saved swap alternatives."}), 404

    try:
        alternative_index = int(data.get("alternative_index", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "alternative_index must be an integer"}), 400
    if alternative_index < 0 or alternative_index >= len(alternatives):
        return jsonify({"error": "Swap alternative not found"}), 404

    alternative = alternatives[alternative_index]
    if not isinstance(alternative, dict):
        return jsonify({"error": "Swap alternative is invalid"}), 400

    place, provider_ref = resolve_or_upsert_recommendation_place(alternative)
    if not place:
        return jsonify({"error": "Swap alternative could not be resolved as a place"}), 404

    previous_snapshot = recommendation_metadata_snapshot(metadata, include_swap_context=True)
    alternative_snapshot = recommendation_metadata_snapshot(alternative, include_swap_context=True)
    swap_entry = append_stop_swap_summary(session, metadata, previous_snapshot, alternative_snapshot)
    next_alternatives = [
        previous_snapshot,
        *[
            recommendation_metadata_snapshot(item, include_swap_context=True)
            for index, item in enumerate(alternatives)
            if index != alternative_index and isinstance(item, dict)
        ],
    ][:3]

    metadata.update(alternative_snapshot)
    metadata.update({
        "source": metadata.get("source") or "planned_itinerary",
        "provider": provider_ref.provider if provider_ref else alternative_snapshot.get("provider"),
        "provider_place_id": (
            provider_ref.provider_place_id
            if provider_ref
            else alternative_snapshot.get("provider_place_id")
        ),
        "previous_stop": previous_snapshot,
        "alternatives": next_alternatives,
        "swap_history": {
            "swapped": True,
            "from_place_id": previous_snapshot.get("place_id"),
            "from_name": previous_snapshot.get("name") or (previous_snapshot.get("display") or {}).get("name"),
            "to_place_id": alternative_snapshot.get("place_id"),
            "to_name": alternative_snapshot.get("name") or (alternative_snapshot.get("display") or {}).get("name"),
            "swapped_at": swap_entry.get("swapped_at"),
            "impact": alternative_snapshot.get("swap_impact"),
        },
    })

    stop.place_id = place.id
    stop.provider_ref_id = provider_ref.id if provider_ref else None
    stop.metadata_json = json.dumps(compact_metadata(metadata))
    recommendation_service.record_event(
        user=user,
        place=place,
        provider_ref=provider_ref,
        event_type="swap",
        context="adventour",
        metadata={
            "adventour_session_id": session.id,
            "adventour_stop_id": stop.id,
            "from": previous_snapshot,
            "to": alternative_snapshot,
        },
        commit=False,
    )
    db.session.commit()

    return jsonify({
        "message": "Stop swapped",
        "adventour": serialize_adventour_session(session),
        "stop": serialize_adventour_stop(stop),
        "swap": compact_metadata(swap_entry),
    }), 200

@app.route('/api/adventours/<int:session_id>/stops/<int:stop_id>/arrive', methods=['POST'])
@require_auth
def arrive_adventour_stop(session_id, stop_id):
    user = g.current_user
    session = AdventourSession.query.filter_by(id=session_id, user_id=user.id, status="active").first()
    stop = AdventourStop.query.filter_by(id=stop_id, session_id=session_id).first() if session else None
    if not session or not stop:
        return jsonify({"error": "Active Adventour stop not found"}), 404

    stop.status = "arrived"
    stop.arrived_at = stop.arrived_at or datetime.utcnow()
    recommendation_service.record_event(
        user=user,
        place=stop.place,
        provider_ref=stop.provider_ref,
        event_type="arrival",
        context="adventour",
        metadata={"adventour_session_id": session.id, "adventour_stop_id": stop.id},
        commit=False,
    )
    db.session.commit()

    return jsonify({"adventour": serialize_adventour_session(session), "stop": serialize_adventour_stop(stop)}), 200

@app.route('/api/adventours/<int:session_id>/stops/<int:stop_id>/complete', methods=['POST'])
@require_auth
def complete_adventour_stop(session_id, stop_id):
    data = request.json or {}
    user = g.current_user
    session = AdventourSession.query.filter_by(id=session_id, user_id=user.id, status="active").first()
    stop = AdventourStop.query.filter_by(id=stop_id, session_id=session_id).first() if session else None
    if not session or not stop:
        return jsonify({"error": "Active Adventour stop not found"}), 404

    rating = data.get("rating")
    if rating is not None:
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            return jsonify({"error": "rating must be an integer between 1 and 5"}), 400
        if rating < 1 or rating > 5:
            return jsonify({"error": "rating must be an integer between 1 and 5"}), 400

    now = datetime.utcnow()
    stop.status = "completed"
    stop.arrived_at = stop.arrived_at or now
    stop.departed_at = stop.departed_at or now
    stop.rating = rating
    if "notes" in data:
        stop.notes = data.get("notes")

    if rating:
        recommendation_service.record_event(
            user=user,
            place=stop.place,
            provider_ref=stop.provider_ref,
            event_type="rate",
            event_value=rating,
            context="adventour",
            metadata={"adventour_session_id": session.id, "adventour_stop_id": stop.id},
            commit=False,
        )
        recommendation_service.rebuild_preference_vector(user, commit=False)
    db.session.commit()

    return jsonify({"adventour": serialize_adventour_session(session), "stop": serialize_adventour_stop(stop)}), 200

@app.route('/api/adventours/<int:session_id>/complete', methods=['POST'])
@require_auth
def complete_adventour(session_id):
    user = g.current_user
    session = AdventourSession.query.filter_by(id=session_id, user_id=user.id, status="active").first()
    if not session:
        return jsonify({"error": "Active Adventour not found"}), 404

    now = datetime.utcnow()
    for stop in session.stops.all():
        if stop.status in ("planned", "navigating", "arrived"):
            stop.status = "skipped" if not stop.arrived_at else "completed"
            stop.departed_at = stop.departed_at or now

    completed_stops = [stop for stop in session.stops.all() if stop.status == "completed"]
    duration_seconds = int((now - session.started_at).total_seconds()) if session.started_at else 0
    session.status = "completed"
    session.ended_at = now
    summary = parse_json_object(session.summary_json)
    summary.update({
        "stop_count": len(completed_stops),
        "duration_seconds": max(0, duration_seconds),
        "rated_stop_count": len([stop for stop in completed_stops if stop.rating]),
        "completion": {
            "stop_count": len(completed_stops),
            "duration_seconds": max(0, duration_seconds),
            "rated_stop_count": len([stop for stop in completed_stops if stop.rating]),
        },
    })
    session.summary_json = json.dumps(summary)
    db.session.commit()

    return jsonify({"adventour": serialize_adventour_session(session), "message": "Adventour completed"}), 200

@app.route('/api/adventours/history', methods=['GET'])
@require_auth
def adventour_history():
    limit = min(int(request.args.get("limit", 20)), 100)
    sessions = (
        AdventourSession.query
        .filter_by(user_id=g.current_user.id)
        .order_by(AdventourSession.started_at.desc())
        .limit(limit)
        .all()
    )
    return jsonify({"adventours": [serialize_adventour_session(session) for session in sessions]}), 200

@app.route('/api/reservations', methods=['GET'])
@require_auth
def list_travel_reservations():
    query = TravelReservation.query.filter_by(user_id=g.current_user.id)
    session_id = request.args.get("session_id")
    if session_id:
        try:
            query = query.filter_by(adventour_session_id=int(session_id))
        except ValueError:
            return jsonify({"error": "session_id must be an integer"}), 400

    reservations = query.order_by(TravelReservation.starts_at.asc().nullslast(), TravelReservation.created_at.desc()).all()
    return jsonify({"reservations": [serialize_travel_reservation(item) for item in reservations]}), 200

@app.route('/api/reservations', methods=['POST'])
@require_auth
def create_travel_reservation():
    data = request.json or {}
    if not data.get("reservation_type") or not (data.get("title") or "").strip():
        return jsonify({"error": "reservation_type and title are required"}), 400

    session_id = data.get("adventour_session_id")
    session = None
    if session_id is not None:
        session = AdventourSession.query.filter_by(id=session_id, user_id=g.current_user.id).first()
        if not session:
            return jsonify({"error": "Adventour session not found"}), 404

    try:
        reservation = TravelReservation(
            user_id=g.current_user.id,
            title="Reservation draft",
        )
        apply_reservation_payload(reservation, data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    db.session.add(reservation)
    db.session.flush()
    refreshed_adventour = None
    if reservation.adventour_session_id:
        affected_session = session or reservation.session
        refresh_adventour_booking_packet(affected_session)
        refreshed_adventour = serialize_adventour_session(affected_session) if affected_session else None
    db.session.commit()

    return jsonify({
        "message": "Reservation saved",
        "reservation": serialize_travel_reservation(reservation),
        "adventour": refreshed_adventour,
    }), 201

@app.route('/api/reservations/<int:reservation_id>', methods=['PATCH'])
@require_auth
def update_travel_reservation(reservation_id):
    reservation = TravelReservation.query.filter_by(id=reservation_id, user_id=g.current_user.id).first()
    if not reservation:
        return jsonify({"error": "Reservation not found"}), 404

    data = request.json or {}
    previous_session = reservation.session
    next_session = None
    if "adventour_session_id" in data and data.get("adventour_session_id") is not None:
        next_session = AdventourSession.query.filter_by(id=data.get("adventour_session_id"), user_id=g.current_user.id).first()
        if not next_session:
            return jsonify({"error": "Adventour session not found"}), 404

    try:
        apply_reservation_payload(reservation, data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    db.session.flush()
    refresh_sessions = {
        session
        for session in (previous_session, next_session or reservation.session)
        if session is not None
    }
    for session in refresh_sessions:
        refresh_adventour_booking_packet(session)
    refreshed_adventours = [serialize_adventour_session(session) for session in refresh_sessions]
    current_adventour = (
        serialize_adventour_session(reservation.session)
        if reservation.session is not None
        else (refreshed_adventours[0] if len(refreshed_adventours) == 1 else None)
    )
    db.session.commit()
    return jsonify({
        "message": "Reservation updated",
        "reservation": serialize_travel_reservation(reservation),
        "adventour": current_adventour,
        "adventours": refreshed_adventours,
    }), 200

@app.route('/api/reservations/<int:reservation_id>', methods=['DELETE'])
@require_auth
def delete_travel_reservation(reservation_id):
    reservation = TravelReservation.query.filter_by(id=reservation_id, user_id=g.current_user.id).first()
    if not reservation:
        return jsonify({"error": "Reservation not found"}), 404

    session = reservation.session
    db.session.delete(reservation)
    db.session.flush()
    refreshed_adventour = None
    if session:
        refresh_adventour_booking_packet(session)
        refreshed_adventour = serialize_adventour_session(session)
    db.session.commit()
    return jsonify({"message": "Reservation deleted", "adventour": refreshed_adventour}), 200

@app.route('/api/profile/history', methods=['GET'])
@require_auth
def profile_history():
    user = g.current_user
    event_type = request.args.get("event_type", "accept")
    limit = min(int(request.args.get("limit", 30)), 100)

    if event_type not in ("accept", "reject"):
        return jsonify({"error": "event_type must be accept or reject"}), 400

    events = (
        UserPlaceEvent.query
        .filter_by(user_id=user.id, event_type=event_type)
        .order_by(UserPlaceEvent.occurred_at.desc())
        .limit(limit)
        .all()
    )

    places = []
    for event in events:
        place = db.session.get(Place, event.place_id)
        if not place:
            continue

        provider_ref = None
        if event.provider_ref_id:
            provider_ref = db.session.get(PlaceProviderRef, event.provider_ref_id)
        if not provider_ref:
            provider_ref = PlaceProviderRef.query.filter_by(place_id=place.id).first()

        feature = PlaceFeature.query.filter_by(place_id=place.id).first()
        metadata = json.loads(event.metadata_json or "{}")
        display = metadata.get("display") or {}
        types = display.get("types") or list((feature and json.loads(feature.category_vector or "{}") or {}).keys())
        places.append({
            "event_id": event.id,
            "place_id": place.id,
            "provider": provider_ref.provider if provider_ref else None,
            "provider_place_id": provider_ref.provider_place_id if provider_ref else None,
            "name": display.get("name") or place.canonical_name,
            "vicinity": display.get("vicinity"),
            "latitude": place.latitude,
            "longitude": place.longitude,
            "event_type": event.event_type,
            "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
            "category": display.get("category") or (event.context if event.context in ("food", "activity") else None),
            "types": types,
            "rating": display.get("rating"),
            "user_ratings_total": display.get("user_ratings_total"),
            "price_level": display.get("price_level"),
            "photo_url": display.get("photo_url"),
            "photo_attributions": display.get("photo_attributions") or [],
        })

    return jsonify({
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "date_of_birth": date_or_none(user.date_of_birth),
            "profile_picture": user.profile_picture,
            "preferences": user.preferences.split(",") if user.preferences else [],
        },
        "places": places,
    }), 200

@app.route('/api/places/details', methods=['GET'])
@require_auth
def place_details():
    provider = request.args.get("provider")
    provider_place_id = request.args.get("provider_place_id")
    adventour_place_id = request.args.get("place_id")

    place = db.session.get(Place, adventour_place_id) if adventour_place_id else None
    provider_ref = None
    if provider and provider_place_id:
        provider_ref = PlaceProviderRef.query.filter_by(
            provider=provider,
            provider_place_id=str(provider_place_id)
        ).first()
        if not place and provider_ref:
            place = provider_ref.place

    candidate = None
    if provider == "google" and provider_place_id:
        candidate = GoogleServicesAPI.fetch_place_details(provider_place_id)

    feature = PlaceFeature.query.filter_by(place_id=place.id).first() if place else None
    display = place_display_payload(candidate) if candidate else {}
    types = display.get("types") or list((feature and json.loads(feature.category_vector or "{}") or {}).keys())

    if not place and not display:
        return jsonify({"error": "Unknown place"}), 404

    return jsonify({
        "place_id": place.id if place else None,
        "provider": provider_ref.provider if provider_ref else provider,
        "provider_place_id": provider_ref.provider_place_id if provider_ref else provider_place_id,
        "name": display.get("name") or (place.canonical_name if place else None),
        "vicinity": display.get("vicinity"),
        "latitude": place.latitude if place else None,
        "longitude": place.longitude if place else None,
        "types": types,
        "rating": display.get("rating"),
        "user_ratings_total": display.get("user_ratings_total"),
        "price_level": display.get("price_level"),
        "photo_url": display.get("photo_url"),
        "photo_attributions": display.get("photo_attributions") or [],
    }), 200

@app.route('/api/places/photo', methods=['GET'])
def place_photo():
    photo_name = request.args.get("name")
    max_width_px = int(request.args.get("max_width_px", 640))
    max_height_px = int(request.args.get("max_height_px", 420))

    photo_uri = GoogleServicesAPI.fetch_photo_uri(
        photo_name,
        max_width_px=max_width_px,
        max_height_px=max_height_px,
    )
    if not photo_uri:
        return jsonify({"error": "Unable to load place photo"}), 404
    return redirect(photo_uri, code=302)

@app.route('/api/recommendations', methods=['POST'])
@require_auth
def create_recommendations():
    data = request.json or {}
    user = g.current_user
    location = data.get("location") or {}
    latitude = location.get("latitude")
    longitude = location.get("longitude")

    if latitude is None or longitude is None:
        return jsonify({"error": "location.latitude and location.longitude are required"}), 400

    try:
        logger.info(
            "Recommendation request user=%s latitude=%s longitude=%s constraints=%s",
            user.id,
            latitude,
            longitude,
            data.get("constraints", {}),
        )
        result = recommendation_service.recommend(
            user=user,
            location={"latitude": float(latitude), "longitude": float(longitude)},
            radius_meters=int(data.get("radius_meters", 3200)),
            member_ids=data.get("member_ids", []),
            constraints=data.get("constraints", {}),
            mode=data.get("mode", "spontaneous"),
        )
        result["scenario_readiness"] = recommendation_evaluation_service.scenario_readiness_report(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Recommendation request failed")
        return jsonify({"error": "Recommendation request failed", "detail": str(exc)}), 500

    return jsonify(result), 200

@app.route('/api/recommendations/preferences', methods=['GET'])
@require_auth
def recommendation_preference_insights():
    user = g.current_user
    try:
        requested_member_ids = []
        raw_member_ids = request.args.getlist("member_id")
        if request.args.get("member_ids"):
            raw_member_ids.extend(str(request.args.get("member_ids")).split(","))
        accepted_ids = set(accepted_friend_ids(user.id))
        for member_id in raw_member_ids:
            try:
                parsed_id = int(member_id)
            except (TypeError, ValueError):
                continue
            if parsed_id in accepted_ids and parsed_id not in requested_member_ids:
                requested_member_ids.append(parsed_id)

        members = [user]
        if requested_member_ids:
            friends = (
                User.query
                .filter(User.id.in_(requested_member_ids))
                .all()
            )
            friend_by_id = {friend.id: friend for friend in friends}
            members.extend(
                friend_by_id[member_id]
                for member_id in requested_member_ids
                if member_id in friend_by_id
            )

        insights = []
        for member in members:
            vector = recommendation_service.build_preference_vector(member)
            insights.append(recommendation_service.preference_insights(member, vector))

        return jsonify({
            "preference_insights": insights[0] if len(insights) == 1 else insights,
            "members": [
                {
                    "id": member.id,
                    "display_name": member.display_name or member.username,
                    "is_viewer": member.id == user.id,
                }
                for member in members
            ],
        }), 200
    except Exception as exc:
        logger.exception("Preference insight request failed")
        return jsonify({"error": "Preference insight request failed", "detail": str(exc)}), 500

@app.route('/api/recommendations/learned-ranker/status', methods=['GET'])
@require_auth
def learned_ranker_status():
    try:
        return jsonify({
            "learned_rerank": recommendation_service.learned_ranker_status(),
        }), 200
    except Exception as exc:
        logger.exception("Learned ranker status request failed")
        return jsonify({"error": "Learned ranker status request failed", "detail": str(exc)}), 500

def _itinerary_request_payload(data):
    location = data.get("location") or {}
    latitude = location.get("latitude")
    longitude = location.get("longitude")

    if latitude is None or longitude is None:
        raise ValueError("location.latitude and location.longitude are required")

    return {
        "location": {"latitude": float(latitude), "longitude": float(longitude)},
        "radius_meters": int(data.get("radius_meters", 8000)),
        "member_ids": data.get("member_ids", []),
        "constraints": data.get("constraints", {}),
        "party_size": int(data.get("party_size", 1)),
        "days": int(data.get("days", 1)),
        "destination_label": data.get("destination_label"),
    }


def _destination_compare_request_payload(data):
    raw_destinations = data.get("destinations") or []
    if not isinstance(raw_destinations, list) or not raw_destinations:
        raise ValueError("At least one destination is required")
    if len(raw_destinations) > 8:
        raise ValueError("Compare up to 8 destinations at a time")

    destinations = []
    for index, raw_destination in enumerate(raw_destinations):
        if not isinstance(raw_destination, dict):
            raise ValueError("Each destination must include a label and location")

        location = raw_destination.get("location") or {}
        latitude = location.get("latitude")
        longitude = location.get("longitude")
        if latitude is None or longitude is None:
            raise ValueError("Each destination requires location.latitude and location.longitude")

        label = (
            raw_destination.get("label")
            or raw_destination.get("destination_label")
            or raw_destination.get("name")
            or f"Destination {index + 1}"
        )
        destinations.append({
            "id": raw_destination.get("id") or raw_destination.get("place_id") or f"destination_{index + 1}",
            "label": str(label),
            "location": {"latitude": float(latitude), "longitude": float(longitude)},
            "radius_meters": int(raw_destination.get("radius_meters") or data.get("radius_meters", 8000)),
            "constraints": raw_destination.get("constraints") or {},
            "source": raw_destination.get("source"),
        })

    return {
        "destinations": destinations,
        "member_ids": data.get("member_ids", []),
        "constraints": data.get("constraints", {}),
        "party_size": int(data.get("party_size", 1)),
        "days": int(data.get("days", 2)),
        "include_plans": bool(data.get("include_plans")),
        "include_profile_comparisons": bool(data.get("include_profile_comparisons")),
        "scoring_profiles": data.get("scoring_profiles"),
    }


def _recommendation_request_payload(data):
    location = data.get("location") or {}
    latitude = location.get("latitude")
    longitude = location.get("longitude")

    if latitude is None or longitude is None:
        raise ValueError("location.latitude and location.longitude are required")

    return {
        "location": {"latitude": float(latitude), "longitude": float(longitude)},
        "radius_meters": int(data.get("radius_meters", 3200)),
        "member_ids": data.get("member_ids", []),
        "constraints": data.get("constraints", {}),
        "mode": data.get("mode", "spontaneous"),
    }


def _basket_summary(result, include_recommendations=False):
    recommendations = result.get("recommendations") or []
    first_pick = recommendations[0] if recommendations else None
    quality = result.get("recommendation_quality") or {}
    scenario_readiness = result.get("scenario_readiness") or recommendation_evaluation_service.scenario_readiness_report(result)
    rank = _basket_comparison_rank(result)
    summary = {
        "scoring_profile": result.get("scoring_profile"),
        "scenario_readiness": scenario_readiness,
        "recommendation_quality": quality,
        "group_fit_summary": result.get("group_fit_summary"),
        "slate_summary": result.get("slate_summary"),
        "pipeline_diagnostic": _pipeline_issue_summary_from_quality(quality),
        "comparison_rank": rank,
        "comparison_explanation": _basket_comparison_explanation(result, rank),
        "first_pick": {
            "name": first_pick.get("name"),
            "score": first_pick.get("score"),
            "diversity_groups": first_pick.get("diversity_groups", []),
            "authenticity_label": (first_pick.get("authenticity_evidence") or {}).get("label"),
        } if first_pick else None,
        "query_tags": result.get("query_tags", []),
        "learned_rerank": result.get("learned_rerank"),
        "warnings": quality.get("warnings", []),
        "strengths": quality.get("strengths", []),
    }
    if include_recommendations:
        summary["recommendations"] = recommendations
        summary["result"] = result
    return summary


def _comparison_profile_variants(requested_profiles, base_constraints):
    variants = []
    seen = set()
    for raw_profile in requested_profiles or []:
        profile_name = str(raw_profile or "").strip()
        if not profile_name:
            continue
        if profile_name in seen:
            continue
        seen.add(profile_name)

        if profile_name == "learned_beta":
            variants.append({
                "id": "learned_beta",
                "constraints": {
                    **base_constraints,
                    "scoring_profile": "phase1_balanced",
                    "learned_rerank": True,
                    "record_impressions": False,
                },
            })
            continue

        variants.append({
            "id": profile_name,
            "constraints": {
                **base_constraints,
                "scoring_profile": profile_name,
                "record_impressions": False,
            },
        })
    return variants


def _basket_comparison_rank(result):
    quality = result.get("recommendation_quality") or {}
    metrics = quality.get("metrics") or {}
    scenario = result.get("scenario_readiness") or recommendation_evaluation_service.scenario_readiness_report(result)
    group_fit = result.get("group_fit_summary") or {}
    slate_metrics = (result.get("slate_summary") or {}).get("metrics") or {}
    warnings = quality.get("warnings") or []
    strengths = quality.get("strengths") or []
    learned = result.get("learned_rerank") or {}
    learned_reason = learned.get("reason")
    learned_training_health = learned.get("training_data_health") or {}
    learned_requested = bool(learned.get("applied") or (learned_reason and learned_reason != "not_enabled"))
    learned_inactive = bool(learned_requested and not learned.get("applied"))
    pipeline_issue = _pipeline_issue_summary_from_quality(quality) or {}
    pipeline_issue_status = pipeline_issue.get("status")
    pipeline_issue_severity = _pipeline_issue_severity(pipeline_issue_status)
    pipeline_health_score = (
        1.0
        if not pipeline_issue.get("name")
        else max(0, min(1, _safe_float(pipeline_issue.get("score"))))
    )
    member_coverage_share = metrics.get("member_coverage_share", slate_metrics.get("member_coverage_share"))
    average_group_fit = _safe_float(metrics.get("average_group_fit"))
    group_fairness_score = _safe_float(group_fit.get("fairness_score"))
    group_lowest_fit = _safe_float(group_fit.get("lowest_fit"))
    underserved_count = len(group_fit.get("underserved_members") or [])
    party_readiness_score = None
    if (
        result.get("member_count", 1) > 1
        or average_group_fit > 0
        or member_coverage_share is not None
    ):
        coverage = _safe_float(member_coverage_share)
        party_readiness_score = max(
            0,
            (
                coverage * 0.42
                + group_lowest_fit * 0.25
                + group_fairness_score * 0.20
                + average_group_fit * 0.13
            )
            - min(0.30, underserved_count * 0.12)
        )
    return {
        "beta_testable": bool(scenario.get("beta_testable")),
        "status": scenario.get("status"),
        "returned": int(metrics.get("returned") or 0),
        "average_score": round(_safe_float(metrics.get("average_score")), 3),
        "local_feeling_share": round(_safe_float(metrics.get("local_feeling_share")), 3),
        "hidden_gem_count": int(metrics.get("hidden_gem_count") or 0),
        "hidden_gem_share": round(_safe_float(metrics.get("hidden_gem_share")), 3),
        "generic_risk_share": round(_safe_float(metrics.get("generic_risk_share")), 3),
        "diversity_coverage": round(_safe_float(metrics.get("diversity_coverage")), 3),
        "dominant_group_share": round(_safe_float(metrics.get("dominant_group_share")), 3),
        "missing_intent_count": int(metrics.get("missing_intent_count") or 0),
        "first_page_local_discovery_count": int(
            metrics.get("first_page_local_discovery_count")
            or slate_metrics.get("first_page_local_discovery_count")
            or 0
        ),
        "local_discovery_rescue_count": int(
            metrics.get("local_discovery_rescue_count")
            or slate_metrics.get("local_discovery_rescue_count")
            or 0
        ),
        "local_event_backed_count": int(metrics.get("local_event_backed_count") or 0),
        "local_event_reservation_ready_count": int(metrics.get("local_event_reservation_ready_count") or 0),
        "local_event_source_ready_count": int(metrics.get("local_event_source_ready_count") or 0),
        "local_event_friend_signal_count": int(metrics.get("local_event_friend_signal_count") or 0),
        "local_event_social_score": round(_safe_float(metrics.get("local_event_social_score")), 3),
        "member_coverage_share": (
            round(_safe_float(member_coverage_share), 3)
            if member_coverage_share is not None else None
        ),
        "average_group_fit": round(average_group_fit, 3),
        "group_fairness_score": round(group_fairness_score, 3),
        "group_lowest_fit": round(group_lowest_fit, 3),
        "party_readiness_score": round(party_readiness_score, 3) if party_readiness_score is not None else None,
        "underserved_count": underserved_count,
        "provider_error_count": int(metrics.get("provider_error_count") or 0),
        "pipeline_health_score": round(pipeline_health_score, 3),
        "pipeline_issue_name": pipeline_issue.get("name"),
        "pipeline_issue_label": pipeline_issue.get("label"),
        "pipeline_issue_status": pipeline_issue_status,
        "pipeline_issue_severity": pipeline_issue_severity,
        "learned_requested": learned_requested,
        "learned_active": bool(learned.get("applied")),
        "learned_inactive": learned_inactive,
        "learned_reason": learned_reason,
        "learned_training_data_status": learned_training_health.get("status"),
        "learned_training_data_summary": learned_training_health.get("summary"),
        "warning_count": len(warnings),
        "strength_count": len(strengths),
    }


def _basket_comparison_sort_key(item):
    rank = item.get("comparison_rank") or {}
    return (
        0 if rank.get("learned_inactive") else 1,
        1 if rank.get("beta_testable") else 0,
        rank.get("party_readiness_score") if rank.get("party_readiness_score") is not None else 0,
        rank.get("returned") or 0,
        rank.get("local_feeling_share") or 0,
        rank.get("hidden_gem_count") or 0,
        rank.get("hidden_gem_share") or 0,
        rank.get("first_page_local_discovery_count") or 0,
        rank.get("local_discovery_rescue_count") or 0,
        rank.get("local_event_backed_count") or 0,
        rank.get("local_event_reservation_ready_count") or 0,
        rank.get("local_event_friend_signal_count") or 0,
        rank.get("local_event_social_score") or 0,
        rank.get("local_event_source_ready_count") or 0,
        rank.get("average_score") or 0,
        rank.get("diversity_coverage") or 0,
        -(rank.get("dominant_group_share") or 0),
        -(rank.get("missing_intent_count") or 0),
        -(rank.get("generic_risk_share") or 0),
        rank.get("member_coverage_share") if rank.get("member_coverage_share") is not None else 0,
        rank.get("group_fairness_score") if (rank.get("average_group_fit") or 0) > 0 else 0,
        rank.get("group_lowest_fit") if (rank.get("average_group_fit") or 0) > 0 else 0,
        -(rank.get("underserved_count") or 0),
        -(rank.get("provider_error_count") or 0),
        -(rank.get("pipeline_issue_severity") or 0),
        rank.get("pipeline_health_score") or 0,
        -(rank.get("warning_count") or 0),
        rank.get("strength_count") or 0,
    )


def _basket_comparison_explanation(result, rank):
    quality = result.get("recommendation_quality") or {}
    scenario = result.get("scenario_readiness") or recommendation_evaluation_service.scenario_readiness_report(result)
    tradeoffs = []
    tradeoffs.append({
        "kind": "readiness",
        "label": "Beta",
        "value": "Ready" if rank.get("beta_testable") else scenario.get("status", "Review").replace("_", " ").title(),
        "tone": "positive" if rank.get("beta_testable") else "caution",
    })
    if rank.get("learned_requested"):
        tradeoffs.append({
            "kind": "learned",
            "label": "Learning",
            "value": "Active" if rank.get("learned_active") else "Paused",
            "tone": "positive" if rank.get("learned_active") else "caution",
        })
    if rank.get("average_group_fit"):
        tradeoffs.append({
            "kind": "party",
            "label": "Party",
            "value": f"{round(rank['average_group_fit'] * 100)}%",
            "tone": "caution" if rank.get("underserved_count") else "positive",
        })
    if rank.get("local_feeling_share"):
        tradeoffs.append({
            "kind": "local",
            "label": "Local",
            "value": f"{round(rank['local_feeling_share'] * 100)}%",
            "tone": "positive" if rank["local_feeling_share"] >= 0.65 else "neutral",
        })
    if rank.get("hidden_gem_count"):
        tradeoffs.append({
            "kind": "hidden_gems",
            "label": "Gems",
            "value": str(rank["hidden_gem_count"]),
            "tone": "positive",
        })
    if rank.get("first_page_local_discovery_count") or rank.get("local_discovery_rescue_count"):
        tradeoffs.append({
            "kind": "local_discovery",
            "label": "Local opener",
            "value": (
                f"{rank.get('local_discovery_rescue_count')} rescued"
                if rank.get("local_discovery_rescue_count")
                else f"{rank.get('first_page_local_discovery_count')} early"
            ),
            "tone": "positive",
        })
    if rank.get("local_event_backed_count"):
        tradeoffs.append({
            "kind": "local_events",
            "label": "Event anchor",
            "value": (
                f"{rank.get('local_event_reservation_ready_count')} bookable"
                if rank.get("local_event_reservation_ready_count")
                else f"{rank.get('local_event_backed_count')} nearby"
            ),
            "tone": "positive",
        })
    if rank.get("diversity_coverage"):
        tradeoffs.append({
            "kind": "variety",
            "label": "Variety",
            "value": f"{round(rank['diversity_coverage'] * 100)}%",
            "tone": "positive" if rank["diversity_coverage"] >= 0.8 else "caution",
        })
    if rank.get("generic_risk_share"):
        tradeoffs.append({
            "kind": "generic",
            "label": "Generic risk",
            "value": f"{round(rank['generic_risk_share'] * 100)}%",
            "tone": "caution" if rank["generic_risk_share"] >= 0.35 else "neutral",
        })
    if rank.get("pipeline_issue_name"):
        tradeoffs.append({
            "kind": "pipeline",
            "label": "Pipeline",
            "value": str(rank.get("pipeline_issue_label") or "Tune"),
            "tone": "caution" if rank.get("pipeline_issue_severity") else "neutral",
        })
    if rank.get("learned_inactive"):
        headline = "Learned beta is not active yet; compare this as the balanced fallback."
    elif rank.get("pipeline_issue_status") == "fail":
        headline = f"Best basket, but tune {str(rank.get('pipeline_issue_label') or 'pipeline').lower()} first."
    elif rank.get("local_discovery_rescue_count"):
        if rank.get("beta_testable") or scenario.get("status") == "ready":
            headline = "Best test basket with local discoveries in the opening cards."
        else:
            headline = "Best basket with local discoveries in the opening cards."
    elif rank.get("local_event_backed_count") and (
        rank.get("local_event_reservation_ready_count")
        or rank.get("local_event_friend_signal_count")
        or rank.get("local_event_social_score", 0) >= 0.45
    ):
        headline = "Best basket for anchoring the Adventour around a timely local event."
    elif rank.get("beta_testable") and rank.get("local_feeling_share", 0) >= 0.65:
        headline = "Best test basket with strong local texture."
    elif rank.get("beta_testable"):
        headline = "Most testable basket for this scout style."
    elif rank.get("average_group_fit", 0) and rank.get("underserved_count"):
        headline = "Useful basket, but one traveler needs stronger matches."
    elif quality.get("headline"):
        headline = quality["headline"]
    else:
        headline = "Best available basket from this comparison."

    return {
        "headline": headline,
        "tradeoffs": tradeoffs[:5],
        "cautions": _compact_unique_strings([
            _learned_inactive_caution(rank),
            (_pipeline_issue_summary_from_quality(quality) or {}).get("next_action"),
            *(quality.get("warnings") or []),
        ], limit=2),
    }


def _itinerary_summary(result, include_plan=False):
    recommendations = _itinerary_selected_recommendations(result)
    first_stop = recommendations[0] if recommendations else None
    readiness = result.get("route_readiness") or {}
    launch_checklist = result.get("launch_checklist") or {}
    scenario_readiness = result.get("scenario_readiness") or recommendation_evaluation_service.scenario_readiness_report(result)
    result["scenario_readiness"] = scenario_readiness
    _attach_itinerary_friend_test_packet(result)
    friend_test_packet = (result.get("trip_packet") or {}).get("friend_test_packet")
    group_fit_summary = _itinerary_group_fit_summary(result)
    rank = _itinerary_comparison_rank(result)
    summary = {
        "scoring_profile": result.get("scoring_profile"),
        "route_readiness": readiness,
        "scenario_readiness": scenario_readiness,
        "friend_test_packet": friend_test_packet,
        "launch_checklist": launch_checklist,
        "authenticity_summary": _itinerary_authenticity_summary(result),
        "group_fit_summary": group_fit_summary,
        "group_compromise_brief": group_fit_summary.get("compromise_brief"),
        "pipeline_diagnostic": _pipeline_issue_summary_from_quality(result.get("recommendation_quality") or {}),
        "comparison_rank": rank,
        "comparison_explanation": _itinerary_comparison_explanation(result, rank),
        "learned_rerank": result.get("learned_rerank"),
        "first_stop": {
            "name": first_stop.get("name"),
            "score": first_stop.get("score"),
            "diversity_groups": first_stop.get("diversity_groups", []),
        } if first_stop else None,
        "known_per_person": (result.get("price_breakdown") or {}).get("per_person"),
        "warnings": readiness.get("warnings", []),
        "strengths": readiness.get("strengths", []),
    }
    if include_plan:
        summary["plan"] = result
    return summary


def _destination_profile_comparison_payload(summary):
    return {
        key: value
        for key, value in summary.items()
        if key not in {"plan", "profile_comparisons"}
    }


def _itinerary_selected_recommendations(result):
    return [
        stop.get("recommendation") or {}
        for day in result.get("days", [])
        for stop in day.get("stops", [])
        if stop.get("recommendation")
    ]


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _compact_unique_strings(values, limit=4):
    compacted = []
    for value in values or []:
        if not value:
            continue
        text = str(value).strip()
        if text and text not in compacted:
            compacted.append(text)
        if len(compacted) >= limit:
            break
    return compacted


def _learned_inactive_caution(rank, mode="basket"):
    if not rank.get("learned_inactive"):
        return None

    reason = rank.get("learned_reason")
    health_status = rank.get("learned_training_data_status")
    health_summary = rank.get("learned_training_data_summary")
    scope = "route Auto scout" if mode == "route" else "Auto scout"

    if reason == "training_data_needs_data" or health_status == "needs_data":
        return health_summary or f"Learned beta needs more representative training data before it should win {scope}."
    if reason == "training_data_unknown" or health_status == "unknown":
        return f"Refresh the learned-ranker artifact so Adventour can inspect training-data health before {scope}."
    if reason == "no_model":
        return f"Learned beta needs a loaded model before it should win {scope}."
    if reason == "promotion_gate_missing":
        return f"Evaluate the learned model against Adventour quality gates before it should win {scope}."
    if str(reason or "").startswith("promotion_gate_"):
        return f"Learned beta needs passing promotion gates before it should win {scope}."
    return f"Learned beta needs a ready model before it should win {scope}."


def _pipeline_issue_summary_from_quality(quality):
    diagnostic = (quality or {}).get("diagnostic") or {}
    if not diagnostic:
        return None

    issue = diagnostic.get("primary_issue") or {}
    if not issue:
        return {
            "status": diagnostic.get("status") or "ready",
            "name": None,
            "label": "Pipeline healthy",
            "score": 1.0,
            "summary": diagnostic.get("headline") or "Recommendation pipeline looks healthy for this run.",
            "next_action": None,
        }

    return {
        "status": issue.get("status") or diagnostic.get("status") or "watch",
        "name": issue.get("name"),
        "label": issue.get("label") or issue.get("name") or "Pipeline",
        "score": round(_safe_float(issue.get("score")), 3),
        "summary": issue.get("summary") or diagnostic.get("headline"),
        "next_action": issue.get("next_action") or (diagnostic.get("next_actions") or [None])[0],
    }


def _pipeline_issue_severity(status):
    return {
        "fail": 2,
        "needs_attention": 2,
        "warn": 1,
        "watch": 1,
        "unknown": 1,
    }.get(status or "ready", 0)


def _friend_test_packet_from_itinerary(result):
    scenario = result.get("scenario_readiness") or recommendation_evaluation_service.scenario_readiness_report(result)
    test_verdict = scenario.get("test_verdict") or {}
    friend_readiness = scenario.get("friend_readiness") or {}
    metrics = scenario.get("metrics") or {}
    dimensions = test_verdict.get("dimensions") or []
    group_fit = _itinerary_group_fit_summary(result)

    if not scenario and not test_verdict and not friend_readiness:
        return None

    suggested_swaps = []
    for swap in friend_readiness.get("suggested_swaps") or []:
        if swap:
            suggested_swaps.append(swap)
    for member in friend_readiness.get("underserved_members") or []:
        for swap in member.get("suggested_swaps") or []:
            if swap:
                suggested_swaps.append(swap)

    status = test_verdict.get("status") or scenario.get("status") or friend_readiness.get("status") or "watch"
    headline = (
        test_verdict.get("headline")
        or friend_readiness.get("headline")
        or scenario.get("headline")
        or "Adventour checked whether this route is ready to test with friends."
    )
    score = test_verdict.get("score")
    friend_testable = bool(
        test_verdict.get("friend_testable")
        or scenario.get("ready_for_friend_testing")
        or friend_readiness.get("status") == "ready"
    )
    blockers = [] if friend_testable else _compact_unique_strings(
        test_verdict.get("blockers") or scenario.get("warnings") or [],
        limit=3,
    )
    next_actions = _compact_unique_strings(
        (test_verdict.get("next_actions") or [])
        + (friend_readiness.get("next_actions") or [])
        + (scenario.get("next_actions") or []),
        limit=4,
    )

    return {
        "status": status,
        "headline": headline,
        "score": round(_safe_float(score), 3) if score is not None else None,
        "friend_testable": friend_testable,
        "beta_testable": bool(scenario.get("beta_testable")),
        "member_count": int(friend_readiness.get("member_count") or metrics.get("member_count") or 0),
        "covered_member_count": int(friend_readiness.get("covered_member_count") or 0),
        "underserved_count": int(friend_readiness.get("underserved_count") or 0),
        "coverage_share": round(_safe_float(friend_readiness.get("coverage_share") or metrics.get("member_coverage_share")), 3),
        "average_group_fit": round(_safe_float(friend_readiness.get("average_group_fit") or metrics.get("average_group_fit")), 3),
        "friend_readiness_status": friend_readiness.get("status"),
        "friend_readiness_headline": friend_readiness.get("headline"),
        "blockers": blockers,
        "next_actions": next_actions,
        "dimensions": dimensions[:6],
        "suggested_swaps": suggested_swaps[:3],
        "compromise_brief": group_fit.get("compromise_brief"),
    }


def _attach_itinerary_friend_test_packet(result):
    packet = _friend_test_packet_from_itinerary(result)
    if not packet:
        return result

    trip_packet = dict(result.get("trip_packet") or {})
    quick_stats = [
        stat
        for stat in trip_packet.get("quick_stats") or []
        if stat.get("id") != "friend_test_packet"
    ]
    status_label = str(packet.get("status") or "watch").replace("_", " ").title()
    quick_stats.append({
        "id": "friend_test_packet",
        "label": "Friend test",
        "value": "Ready" if packet.get("friend_testable") else status_label,
        "status": "ready" if packet.get("friend_testable") else "manual",
    })
    trip_packet["friend_test_packet"] = packet
    trip_packet["quick_stats"] = quick_stats
    result["trip_packet"] = trip_packet
    return result


def _itinerary_authenticity_summary(result):
    recommendations = _itinerary_selected_recommendations(result)
    authenticity_scores = []
    hidden_gem_scores = []
    chain_risks = []

    for recommendation in recommendations:
        components = recommendation.get("components") or {}
        evidence = recommendation.get("authenticity_evidence") or {}

        authenticity = components.get("authenticity", evidence.get("score"))
        if authenticity is not None:
            authenticity_scores.append(_safe_float(authenticity))

        hidden_gem = evidence.get("hidden_gem_score")
        if hidden_gem is not None:
            hidden_gem_scores.append(_safe_float(hidden_gem))

        chain_risk = evidence.get("chain_risk")
        if chain_risk is not None:
            chain_risks.append(_safe_float(chain_risk))

    average_authenticity = (
        sum(authenticity_scores) / len(authenticity_scores)
        if authenticity_scores else 0
    )
    average_hidden_gem = (
        sum(hidden_gem_scores) / len(hidden_gem_scores)
        if hidden_gem_scores else 0
    )
    max_chain_risk = max(chain_risks) if chain_risks else 0
    hidden_gem_count = len([score for score in hidden_gem_scores if score >= 0.62])

    if average_authenticity >= 0.78 and max_chain_risk <= 0.28:
        label = "Strong local signal"
    elif average_authenticity >= 0.65:
        label = "Promising local signal"
    elif recommendations:
        label = "Needs stronger local texture"
    else:
        label = "No local signal yet"

    return {
        "score": round(average_authenticity, 3),
        "label": label,
        "hidden_gem_score": round(average_hidden_gem, 3),
        "hidden_gem_count": hidden_gem_count,
        "chain_risk": round(max_chain_risk, 3),
    }


def _itinerary_group_compromise_brief(members, underserved_members, fairness_score, coverage_share):
    if not members:
        return {
            "status": "unknown",
            "headline": "Group balance needs preference data.",
            "message": "Adventour needs member taste signals before it can explain the compromise.",
            "next_action": "Have each traveler swipe on a few places before relying on this route.",
            "balance_chips": [
                {"label": "Coverage", "value": "learning", "tone": "neutral"},
            ],
        }

    ordered = sorted(members, key=lambda item: item.get("average_fit", 0))
    most_compromised = ordered[0]
    dominant = ordered[-1]
    fit_gap = max(0, _safe_float(dominant.get("average_fit")) - _safe_float(most_compromised.get("average_fit")))
    coverage_percent = round((coverage_share or 0) * 100)
    gap_percent = round(fit_gap * 100)
    underserved_names = ", ".join(member["display_name"] for member in underserved_members[:2])

    if len(members) == 1:
        status = "solo"
        headline = f"Built around {dominant['display_name']}."
        message = "This route is personalized for one traveler right now."
        next_action = "Add friends when you want Adventour to blend tastes."
    elif underserved_members:
        status = "needs_coverage"
        headline = f"{underserved_names} need a stronger match."
        message = "This route has a clear favorite, but not every traveler has enough personal coverage yet."
        next_action = f"Swap in a stop that better matches {underserved_names}."
    elif coverage_share >= 1 and fairness_score is not None and fairness_score >= 0.85 and fit_gap <= 0.18:
        status = "balanced"
        headline = "Balanced for the whole party."
        message = "Every traveler is covered and the route is not leaning too hard toward one person."
        next_action = "This is a strong route to start or share."
    elif coverage_share >= 1:
        status = "covered_but_uneven"
        headline = f"{dominant['display_name']} may love this most."
        message = "Everyone has coverage, but one traveler is carrying more of the route fit."
        next_action = f"Use swaps if you want {most_compromised['display_name']} to feel more centered."
    elif fairness_score is not None and fairness_score < 0.7:
        status = "uneven"
        headline = "This route needs a fairer blend."
        message = f"{dominant['display_name']} is better served than {most_compromised['display_name']}."
        next_action = "Try a different scout style or swap the weakest match."
    else:
        status = "watch"
        headline = "Good blend, worth checking."
        message = "The route looks usable, but Adventour should keep watching for stronger personal coverage."
        next_action = "Review the weakest traveler fit before starting."

    return {
        "status": status,
        "headline": headline,
        "message": message,
        "dominant_member": {
            "user_id": dominant.get("user_id"),
            "display_name": dominant.get("display_name"),
            "average_fit": dominant.get("average_fit"),
        },
        "most_compromised_member": {
            "user_id": most_compromised.get("user_id"),
            "display_name": most_compromised.get("display_name"),
            "average_fit": most_compromised.get("average_fit"),
        },
        "fit_gap": round(fit_gap, 3),
        "coverage_share": round(coverage_share or 0, 3),
        "fairness_score": round(fairness_score, 3) if fairness_score is not None else None,
        "next_action": next_action,
        "balance_chips": [
            {"label": "Coverage", "value": f"{coverage_percent}%", "tone": "positive" if coverage_share >= 1 else "caution"},
            {"label": "Gap", "value": f"{gap_percent} pts", "tone": "positive" if fit_gap <= 0.18 else "caution"},
            {"label": "Needs match", "value": str(len(underserved_members)), "tone": "positive" if not underserved_members else "caution"},
        ],
    }


def _itinerary_group_fit_summary(result):
    day_fits = [
        day.get("party_fit") or {}
        for day in result.get("days", [])
        if day.get("party_fit")
    ]
    member_totals = {}
    member_counts = {}
    member_names = {}
    fairness_scores = []

    for party_fit in day_fits:
        fairness = party_fit.get("fairness_score")
        if fairness is not None:
            fairness_scores.append(_safe_float(fairness))
        for member in party_fit.get("members") or []:
            user_id = member.get("user_id")
            average_fit = member.get("average_fit")
            if user_id is None or average_fit is None:
                continue
            member_totals[user_id] = member_totals.get(user_id, 0) + _safe_float(average_fit)
            member_counts[user_id] = member_counts.get(user_id, 0) + 1
            member_names[user_id] = member.get("display_name") or "Traveler"

    if not member_totals:
        for recommendation in _itinerary_selected_recommendations(result):
            for member in recommendation.get("member_fit") or []:
                user_id = member.get("user_id")
                fit = member.get("fit")
                if user_id is None or fit is None:
                    continue
                member_totals[user_id] = member_totals.get(user_id, 0) + _safe_float(fit)
                member_counts[user_id] = member_counts.get(user_id, 0) + 1
                member_names[user_id] = member.get("display_name") or "Traveler"

    members = [
        {
            "user_id": user_id,
            "display_name": member_names[user_id],
            "average_fit": round(member_totals[user_id] / member_counts[user_id], 3),
            "matched_days": member_counts[user_id],
        }
        for user_id in member_totals
        if member_counts.get(user_id)
    ]
    members.sort(key=lambda item: item["average_fit"])

    fairness_score = (
        sum(fairness_scores) / len(fairness_scores)
        if fairness_scores else None
    )
    lowest_fit = members[0]["average_fit"] if members else None
    highest_fit = members[-1]["average_fit"] if members else None
    if fairness_score is None and lowest_fit is not None and highest_fit is not None:
        fairness_score = max(0, 1 - (highest_fit - lowest_fit))
    underserved_members = [
        member for member in members
        if member["average_fit"] < GROUP_ROUTE_UNDERSERVED_FIT_THRESHOLD
    ]
    covered_member_count = len(members) - len(underserved_members)
    coverage_share = covered_member_count / len(members) if members else None

    if not members:
        message = "Group fit will appear once Adventour has preference data for this travel party."
    elif len(members) == 1:
        message = f"Built around {members[0]['display_name']}'s Adventour taste."
    elif fairness_score is not None and fairness_score >= 0.85 and not underserved_members:
        message = "Strongly balanced for this travel party."
    elif underserved_members:
        names = ", ".join(member["display_name"] for member in underserved_members[:2])
        message = f"{names} may need a stronger match before this feels fair."
    else:
        message = "Good party balance with a few stronger personal matches."

    compromise_brief = _itinerary_group_compromise_brief(
        members,
        underserved_members,
        fairness_score,
        coverage_share,
    )

    return {
        "member_count": len(members),
        "fairness_score": round(fairness_score, 3) if fairness_score is not None else None,
        "lowest_fit": lowest_fit,
        "highest_fit": highest_fit,
        "covered_member_count": covered_member_count,
        "coverage_share": round(coverage_share, 3) if coverage_share is not None else None,
        "underserved_count": len(underserved_members),
        "members": list(reversed(members)),
        "underserved_members": underserved_members,
        "compromise_brief": compromise_brief,
        "message": message,
    }


def _itinerary_party_rescue_summary(result):
    rescues = []
    seen = set()
    for day in result.get("days", []):
        for stop in day.get("stops", []):
            recommendation = stop.get("recommendation") or {}
            summary = stop.get("party_fit_summary") or {}
            rescue = summary.get("coverage_rescue") or {}
            ranking = recommendation.get("ranking") or {}
            if not rescue and ranking.get("party_coverage_rescue"):
                rescue = {
                    "member": ranking.get("rescued_member"),
                    "fit": ranking.get("rescued_member_fit"),
                    "replaced_pick": ranking.get("replaced_pick"),
                    "reason": ranking.get("rescue_reason"),
                    "score_gap": ranking.get("score_gap"),
                }
            if not rescue:
                continue

            member = rescue.get("member") or "Traveler"
            key = (
                member,
                recommendation.get("place_id"),
                recommendation.get("name"),
            )
            if key in seen:
                continue
            seen.add(key)
            rescues.append({
                "member": member,
                "fit": round(_safe_float(rescue.get("fit")), 3) if rescue.get("fit") is not None else None,
                "stop_name": recommendation.get("name"),
                "replaced_pick": rescue.get("replaced_pick"),
                "reason": rescue.get("reason"),
                "score_gap": rescue.get("score_gap"),
            })

    members = []
    for rescue in rescues:
        if rescue["member"] not in members:
            members.append(rescue["member"])

    return {
        "count": len(rescues),
        "members": members,
        "stops": rescues[:4],
    }


def _itinerary_comparison_rank(result):
    readiness = result.get("route_readiness") or {}
    launch_checklist = result.get("launch_checklist") or {}
    scenario_readiness = result.get("scenario_readiness") or {}
    friend_readiness = scenario_readiness.get("friend_readiness") or {}
    authenticity = _itinerary_authenticity_summary(result)
    group_fit = _itinerary_group_fit_summary(result)
    party_rescue = _itinerary_party_rescue_summary(result)
    price_breakdown = result.get("price_breakdown") or {}
    per_person = price_breakdown.get("per_person") or {}
    trip_packet = result.get("trip_packet") or {}
    friend_test_packet = trip_packet.get("friend_test_packet") or _friend_test_packet_from_itinerary(result) or {}
    booking_command_center = trip_packet.get("booking_command_center") or {}
    cost_confidence = trip_packet.get("cost_confidence") or {}
    quote_plan = price_breakdown.get("quote_plan") or trip_packet.get("quote_plan") or cost_confidence.get("quote_plan") or {}
    booking_plan = result.get("booking_plan") or {}
    route_model_confidence = result.get("route_model_confidence") or trip_packet.get("route_model_confidence") or {}
    swap_guide = result.get("swap_guide") or trip_packet.get("swap_guide") or {}
    route_learned = route_model_confidence.get("learned_rerank") or result.get("learned_rerank") or {}
    learned_reason = route_learned.get("reason")
    learned_training_health = route_learned.get("training_data_health") or {}
    learned_requested = bool(route_learned.get("applied") or (learned_reason and learned_reason != "not_enabled"))
    learned_inactive = bool(learned_requested and not route_learned.get("applied"))
    recommendation_quality = result.get("recommendation_quality") or {}
    pipeline_issue = _pipeline_issue_summary_from_quality(recommendation_quality) or {}
    pipeline_issue_status = pipeline_issue.get("status")
    pipeline_issue_severity = _pipeline_issue_severity(pipeline_issue_status)
    pipeline_health_score = (
        1.0
        if not pipeline_issue.get("name")
        else max(0, min(1, _safe_float(pipeline_issue.get("score"))))
    )
    logistics_readiness = result.get("trip_logistics_readiness") or trip_packet.get("trip_logistics_readiness") or {}
    trip_style_fit = result.get("trip_style_fit") or trip_packet.get("trip_style_fit") or {}
    reservation_coverage = trip_packet.get("reservation_coverage") or {}
    planning_burden = booking_plan.get("planning_burden") or {}
    booking_action_links = booking_plan.get("booking_action_links") or []
    booking_timeline_items = ((booking_plan.get("booking_timeline") or {}).get("items") or [])
    warnings = readiness.get("warnings") or []
    strengths = readiness.get("strengths") or []
    known_high = per_person.get("total_known_high")
    known_low = per_person.get("total_known_low")
    known_cost = known_high if known_high is not None else known_low
    cost_tiebreaker = -float(known_cost or 0) / 1000
    route_score = _safe_float(readiness.get("score"))
    stop_coverage = _safe_float(readiness.get("stop_coverage"))
    route_model_score = _safe_float(route_model_confidence.get("score"))
    route_model_warning_count = len(route_model_confidence.get("warnings") or [])
    route_model_basis_count = len(route_model_confidence.get("basis") or [])
    route_model_stop_coverage = _safe_float(route_model_confidence.get("stop_coverage"))
    route_model_authenticity_score = _safe_float(route_model_confidence.get("authenticity_score"))
    route_model_party_score = _safe_float(route_model_confidence.get("party_score"))
    route_model_booking_score = _safe_float(route_model_confidence.get("booking_score"))
    route_model_swap_coverage = _safe_float(route_model_confidence.get("swap_coverage"))
    swap_stop_count = int(swap_guide.get("stop_count") or 0)
    swap_alternative_count = int(swap_guide.get("alternative_count") or 0)
    swap_coverage = _safe_float(swap_guide.get("swap_coverage"))
    swap_recommended_count = int(swap_guide.get("recommended_swap_count") or 0)
    swap_low_friction_count = int(swap_guide.get("low_friction_count") or 0)
    swap_route_risk_count = int(swap_guide.get("route_risk_count") or 0)
    swap_cost_caution_count = int(swap_guide.get("cost_caution_count") or 0)
    swap_cost_saving_count = int(swap_guide.get("cost_saving_count") or 0)
    swap_consensus_upgrade_count = int(swap_guide.get("consensus_upgrade_count") or 0)
    swap_party_plan = swap_guide.get("party_coverage_plan") or {}
    swap_party_actionable_member_count = int(swap_party_plan.get("actionable_member_count") or 0)
    swap_party_underserved_member_count = int(swap_party_plan.get("underserved_member_count") or 0)
    swap_party_plan_status = swap_party_plan.get("status")
    swap_party_coverage_score = (
        min(1, swap_party_actionable_member_count / max(1, swap_party_underserved_member_count))
        if swap_party_underserved_member_count > 0
        else 1.0
        if swap_party_plan_status == "covered"
        else 0
    )
    swap_safety_score = _itinerary_swap_safety_score(
        swap_guide,
        stop_count=swap_stop_count,
        alternative_count=swap_alternative_count,
    )
    logistics_readiness_score = _safe_float(logistics_readiness.get("score"))
    logistics_missing_input_count = int(logistics_readiness.get("missing_input_count") or 0)
    logistics_blocking_count = int(logistics_readiness.get("blocking_count") or 0)
    logistics_provider_link_count = int(logistics_readiness.get("provider_link_count") or 0)
    logistics_quote_ready_count = int(logistics_readiness.get("quote_ready_count") or 0)
    logistics_save_ready_count = int(logistics_readiness.get("save_ready_count") or 0)
    logistics_setup_ready_count = int(logistics_readiness.get("setup_ready_count") or 0)
    booking_command_items = booking_command_center.get("commands") or []
    booking_command_count = int(booking_command_center.get("command_count") or len(booking_command_items))
    booking_command_ready_count = int(
        booking_command_center.get("ready_count")
        or sum(1 for item in booking_command_items if item.get("status") == "ready")
    )
    booking_command_action_count = int(
        booking_command_center.get("action_needed_count")
        or sum(1 for item in booking_command_items if item.get("status") == "action_needed")
    )
    booking_command_open_link_count = int(
        booking_command_center.get("open_link_count")
        or sum(1 for item in booking_command_items if item.get("can_open"))
    )
    booking_command_save_prompt_count = int(
        booking_command_center.get("save_prompt_count")
        or sum(1 for item in booking_command_items if item.get("can_save"))
    )
    booking_command_center_status = booking_command_center.get("status")
    booking_command_primary_action = booking_command_center.get("primary_action") or {}
    trip_style_fit_score = _safe_float(trip_style_fit.get("score"))
    trip_style_fit_status = trip_style_fit.get("status")
    trip_style_duration_fit = _safe_float(trip_style_fit.get("duration_fit"))
    trip_style_quote_coverage = _safe_float(trip_style_fit.get("quote_coverage"))
    trip_style_event_density = _safe_float(trip_style_fit.get("event_density"))
    quote_required_count = int(quote_plan.get("required_count") or 0)
    quote_ready_count = int(quote_plan.get("ready_count") or 0)
    quote_missing_input_count = len(quote_plan.get("missing_inputs") or [])
    quote_ready_coverage = (
        min(1, quote_ready_count / quote_required_count)
        if quote_required_count > 0
        else 0
    )
    quote_readiness_score = (
        max(0, min(1, quote_ready_coverage - min(0.4, quote_missing_input_count * 0.16)))
        if quote_required_count > 0
        else 0
    )
    booking_score = _safe_float(readiness.get("booking_score"))
    event_score = _safe_float(readiness.get("event_score"))
    event_social_score = _safe_float(readiness.get("event_social_score"))
    event_summary = readiness.get("event_summary") or {}
    event_friend_signal_count = (
        int(event_summary.get("route_friend_signal_count"))
        if event_summary.get("route_friend_signal_count") is not None
        else int(event_summary.get("friend_interested_count") or 0) + int(event_summary.get("friend_going_count") or 0)
    )
    event_count = int(event_summary.get("event_count") or 0)
    event_route_match_count = int(event_summary.get("route_match_count") or 0)
    event_actionable_count = int(event_summary.get("route_actionable_event_count") or 0)
    event_reservation_ready_count = int(event_summary.get("route_reservation_ready_count") or 0)
    event_social_anchor_count = int(event_summary.get("route_social_anchor_count") or event_summary.get("social_anchor_count") or 0)
    event_route_anchor = event_summary.get("route_social_anchor") or {}
    event_route_anchor_score = _safe_float(event_route_anchor.get("score"))
    event_route_match_share = min(1, event_route_match_count / max(1, event_count))
    event_actionable_share = min(1, event_actionable_count / max(1, event_count or event_route_match_count or 1))
    event_reservation_share = min(1, event_reservation_ready_count / max(1, event_count or event_route_match_count or 1))
    event_actionability_score = max(0, min(1, (
        event_score * 0.34
        + event_social_score * 0.16
        + event_route_anchor_score * 0.20
        + event_route_match_share * 0.12
        + event_actionable_share * 0.08
        + event_reservation_share * 0.10
    )))
    party_score = _safe_float(readiness.get("party_score"))
    planning_burden_score = _safe_float(planning_burden.get("score"))
    booking_action_link_count = int(readiness.get("booking_action_link_count") or len(booking_action_links))
    booking_saveable_item_count = int(
        readiness.get("booking_saveable_item_count")
        or sum(1 for item in booking_timeline_items if item.get("stores_reservation"))
    )
    booking_action_coverage = min(1, booking_action_link_count / 3)
    booking_saveable_coverage = min(1, booking_saveable_item_count / 2)
    saved_required_count = int(reservation_coverage.get("required_count") or 0)
    saved_detail_count = int(reservation_coverage.get("saved_count") or 0)
    confirmed_detail_count = int(reservation_coverage.get("confirmed_count") or 0)
    booking_saved_coverage = (
        min(1, saved_detail_count / saved_required_count) * 0.65
        + min(1, confirmed_detail_count / saved_required_count) * 0.35
        if saved_required_count > 0
        else 0
    )
    booking_actionable_score = (
        booking_score * 0.52
        + booking_action_coverage * 0.20
        + booking_saveable_coverage * 0.12
        + booking_saved_coverage * 0.10
        + (1 - planning_burden_score) * 0.06
    )
    booking_actionable_score = max(0, min(1, booking_actionable_score))
    booking_command_open_coverage = min(1, booking_command_open_link_count / 3)
    booking_command_save_coverage = min(1, booking_command_save_prompt_count / 2)
    booking_command_ready_coverage = (
        min(1, booking_command_ready_count / booking_command_count)
        if booking_command_count > 0
        else 0
    )
    booking_command_action_penalty = min(0.34, booking_command_action_count * 0.085)
    booking_handoff_score = max(0, min(1, (
        booking_command_open_coverage * 0.30
        + booking_command_save_coverage * 0.24
        + booking_command_ready_coverage * 0.18
        + booking_actionable_score * 0.14
        + logistics_readiness_score * 0.10
        + (1 - planning_burden_score) * 0.04
        - booking_command_action_penalty
    )))
    friend_member_count = int(friend_readiness.get("member_count") or 0)
    friend_coverage_share = _safe_float(friend_readiness.get("coverage_share"))
    friend_average_fit = _safe_float(friend_readiness.get("average_group_fit"))
    friend_underserved_count = int(friend_readiness.get("underserved_count") or 0)
    if friend_member_count > 1:
        group_ready_score = (
            friend_coverage_share * 0.52
            + friend_average_fit * 0.48
            - min(0.18, friend_underserved_count * 0.06)
        )
    elif group_fit["member_count"] > 1:
        group_ready_score = (
            (_safe_float(group_fit["fairness_score"]) * 0.6)
            + (_safe_float(group_fit["lowest_fit"]) * 0.4)
        )
    else:
        group_ready_score = party_score
    group_ready_score = max(0, min(1, group_ready_score))
    underserved_penalty_count = friend_underserved_count if friend_member_count > 1 else group_fit["underserved_count"]
    effective_underserved_penalty_count = max(0, underserved_penalty_count - swap_party_actionable_member_count)
    swap_weight = 0.04 if swap_stop_count > 0 else 0
    group_swap_weight = 0.035 if (friend_member_count > 1 or group_fit["member_count"] > 1) and swap_stop_count > 0 else 0
    planning_weight = 0.03 if swap_stop_count > 0 else 0.07
    trip_readiness_score = (
        route_score * 0.27
        + stop_coverage * 0.10
        + authenticity["score"] * 0.18
        + group_ready_score * 0.16
        + booking_actionable_score * 0.11
        + quote_readiness_score * 0.04
        + event_score * 0.055
        + event_social_score * 0.025
        + event_actionability_score * 0.03
        + swap_safety_score * swap_weight
        + swap_party_coverage_score * group_swap_weight
        + route_model_score * 0.06
        + logistics_readiness_score * 0.05
        + booking_handoff_score * 0.035
        + trip_style_fit_score * 0.035
        + (1 - planning_burden_score) * planning_weight
        - min(0.12, effective_underserved_penalty_count * 0.05)
    )
    trip_readiness_score = max(0, min(1, trip_readiness_score))

    return {
        "can_start": launch_checklist.get("can_start") is not False,
        "blocking_count": int(launch_checklist.get("blocking_count") or 0),
        "action_count": int(launch_checklist.get("action_count") or 0),
        "trip_readiness_score": round(trip_readiness_score, 3),
        "route_score": round(route_score, 3),
        "route_model_confidence_score": round(route_model_score, 3),
        "route_model_status": route_model_confidence.get("status"),
        "route_model_learning_status": route_model_confidence.get("learning_status"),
        "route_model_warning_count": route_model_warning_count,
        "route_model_basis_count": route_model_basis_count,
        "route_model_stop_coverage": round(route_model_stop_coverage, 3),
        "route_model_authenticity_score": round(route_model_authenticity_score, 3),
        "route_model_party_score": round(route_model_party_score, 3),
        "route_model_booking_score": round(route_model_booking_score, 3),
        "route_model_swap_coverage": round(route_model_swap_coverage, 3),
        "route_model_learned_guard_status": route_learned.get("guard_status"),
        "swap_safety_score": round(swap_safety_score, 3),
        "swap_coverage": round(swap_coverage, 3),
        "swap_stop_count": swap_stop_count,
        "swap_alternative_count": swap_alternative_count,
        "swap_recommended_count": swap_recommended_count,
        "swap_low_friction_count": swap_low_friction_count,
        "swap_route_risk_count": swap_route_risk_count,
        "swap_cost_caution_count": swap_cost_caution_count,
        "swap_cost_saving_count": swap_cost_saving_count,
        "swap_consensus_upgrade_count": swap_consensus_upgrade_count,
        "swap_party_coverage_status": swap_party_plan_status,
        "swap_party_actionable_member_count": swap_party_actionable_member_count,
        "swap_party_underserved_member_count": swap_party_underserved_member_count,
        "swap_party_coverage_score": round(swap_party_coverage_score, 3),
        "effective_underserved_count": effective_underserved_penalty_count,
        "learned_requested": learned_requested,
        "learned_active": bool(route_learned.get("applied")),
        "learned_inactive": learned_inactive,
        "learned_reason": learned_reason,
        "learned_training_data_status": learned_training_health.get("status"),
        "learned_training_data_summary": learned_training_health.get("summary"),
        "pipeline_health_score": round(pipeline_health_score, 3),
        "pipeline_issue_name": pipeline_issue.get("name"),
        "pipeline_issue_label": pipeline_issue.get("label"),
        "pipeline_issue_status": pipeline_issue_status,
        "pipeline_issue_severity": pipeline_issue_severity,
        "logistics_readiness_score": round(logistics_readiness_score, 3),
        "logistics_status": logistics_readiness.get("status"),
        "logistics_missing_input_count": logistics_missing_input_count,
        "logistics_blocking_count": logistics_blocking_count,
        "logistics_provider_link_count": logistics_provider_link_count,
        "logistics_quote_ready_count": logistics_quote_ready_count,
        "logistics_save_ready_count": logistics_save_ready_count,
        "logistics_setup_ready_count": logistics_setup_ready_count,
        "logistics_local_transport_status": logistics_readiness.get("local_transport_status"),
        "logistics_reservation_storage_ready": bool(logistics_readiness.get("reservation_storage_ready")),
        "booking_handoff_score": round(booking_handoff_score, 3),
        "booking_command_center_status": booking_command_center_status,
        "booking_command_count": booking_command_count,
        "booking_command_ready_count": booking_command_ready_count,
        "booking_command_action_count": booking_command_action_count,
        "booking_command_open_link_count": booking_command_open_link_count,
        "booking_command_save_prompt_count": booking_command_save_prompt_count,
        "booking_command_primary_action_label": booking_command_primary_action.get("label"),
        "trip_style_fit_score": round(trip_style_fit_score, 3),
        "trip_style_fit_status": trip_style_fit_status,
        "trip_style": trip_style_fit.get("trip_style") or result.get("trip_style"),
        "trip_style_suggested": trip_style_fit.get("suggested_style"),
        "trip_style_duration_fit": round(trip_style_duration_fit, 3),
        "trip_style_quote_coverage": round(trip_style_quote_coverage, 3),
        "trip_style_event_density": round(trip_style_event_density, 3),
        "trip_style_route_days": int(trip_style_fit.get("route_days") or len(result.get("days") or [])),
        "trip_style_nights": int(trip_style_fit.get("nights") or (result.get("price_breakdown") or {}).get("nights") or 0),
        "travel_quote_status": quote_plan.get("status"),
        "travel_quote_required_count": quote_required_count,
        "travel_quote_ready_count": quote_ready_count,
        "travel_quote_missing_input_count": quote_missing_input_count,
        "travel_quote_ready_coverage": round(quote_ready_coverage, 3),
        "travel_quote_readiness_score": round(quote_readiness_score, 3),
        "planned_stop_count": int(readiness.get("planned_stop_count") or 0),
        "stop_coverage": round(stop_coverage, 3),
        "authenticity_score": authenticity["score"],
        "hidden_gem_count": authenticity["hidden_gem_count"],
        "chain_risk": authenticity["chain_risk"],
        "group_member_count": group_fit["member_count"],
        "group_fairness_score": group_fit["fairness_score"] or 0,
        "group_lowest_fit": group_fit["lowest_fit"] or 0,
        "underserved_count": group_fit["underserved_count"],
        "friend_member_count": friend_member_count,
        "friend_testable": bool(friend_test_packet.get("friend_testable")),
        "friend_test_status": friend_test_packet.get("friend_readiness_status") or friend_test_packet.get("status"),
        "friend_test_score": friend_test_packet.get("score"),
        "friend_test_blocker_count": len(friend_test_packet.get("blockers") or []),
        "friend_test_next_action_count": len(friend_test_packet.get("next_actions") or []),
        "friend_coverage_share": round(friend_coverage_share, 3),
        "friend_average_fit": round(friend_average_fit, 3),
        "friend_underserved_count": friend_underserved_count,
        "friend_covered_member_count": int(friend_readiness.get("covered_member_count") or 0),
        "friend_rescue_count": party_rescue["count"],
        "friend_rescued_members": party_rescue["members"],
        "event_score": round(event_score, 3),
        "event_social_score": round(event_social_score, 3),
        "event_actionability_score": round(event_actionability_score, 3),
        "event_count": event_count,
        "event_route_match_count": event_route_match_count,
        "event_actionable_count": event_actionable_count,
        "event_reservation_ready_count": event_reservation_ready_count,
        "event_social_anchor_count": event_social_anchor_count,
        "event_friend_signal_count": event_friend_signal_count,
        "event_route_anchor_score": round(event_route_anchor_score, 3),
        "event_route_anchor_title": event_route_anchor.get("title"),
        "event_route_anchor_reservation_ready": bool(event_route_anchor.get("reservation_ready")),
        "event_route_anchor_action_url": event_route_anchor.get("action_url"),
        "event_top_social_title": event_summary.get("top_route_social_event_title") or event_summary.get("top_route_event_title") or event_summary.get("top_event_title"),
        "booking_score": round(booking_score, 3),
        "booking_actionable_score": round(booking_actionable_score, 3),
        "booking_action_coverage": round(booking_action_coverage, 3),
        "booking_saveable_coverage": round(booking_saveable_coverage, 3),
        "booking_saved_coverage": round(booking_saved_coverage, 3),
        "booking_action_link_count": booking_action_link_count,
        "booking_saveable_item_count": booking_saveable_item_count,
        "booking_saved_required_count": saved_required_count,
        "booking_saved_detail_count": saved_detail_count,
        "booking_confirmed_detail_count": confirmed_detail_count,
        "party_score": round(party_score, 3),
        "planning_burden_score": round(planning_burden_score, 3),
        "planning_burden_level": planning_burden.get("level"),
        "planning_action_needed_count": int(planning_burden.get("action_needed_count") or 0),
        "planning_manual_count": int(planning_burden.get("manual_count") or 0),
        "planning_setup_count": int(planning_burden.get("setup_count") or 0),
        "planning_provider_action_count": int(planning_burden.get("provider_action_count") or 0),
        "warning_count": len(warnings),
        "strength_count": len(strengths),
        "known_cost_tiebreaker": round(cost_tiebreaker, 3),
    }


def _itinerary_swap_safety_score(swap_guide, stop_count=0, alternative_count=0):
    swap_guide = swap_guide or {}
    stop_count = int(stop_count or swap_guide.get("stop_count") or 0)
    alternative_count = int(alternative_count or swap_guide.get("alternative_count") or 0)
    if stop_count <= 0:
        return 0

    swap_coverage = _safe_float(swap_guide.get("swap_coverage"))
    recommended_share = min(1, int(swap_guide.get("recommended_swap_count") or 0) / max(1, stop_count))
    low_friction_share = min(1, int(swap_guide.get("low_friction_count") or 0) / max(1, stop_count))
    risk_share = min(1, int(swap_guide.get("route_risk_count") or 0) / max(1, alternative_count or stop_count))
    cost_caution_share = min(1, int(swap_guide.get("cost_caution_count") or 0) / max(1, alternative_count or stop_count))
    cost_saving_share = min(1, int(swap_guide.get("cost_saving_count") or 0) / max(1, alternative_count or stop_count))

    score = (
        swap_coverage * 0.44
        + low_friction_share * 0.24
        + recommended_share * 0.20
        + cost_saving_share * 0.06
        - risk_share * 0.18
        - cost_caution_share * 0.12
    )
    return max(0, min(1, score))


def _itinerary_comparison_sort_key(item):
    rank = item.get("comparison_rank") or {}
    return (
        0 if rank.get("learned_inactive") else 1,
        1 if rank.get("can_start") else 0,
        -(rank.get("blocking_count") or 0),
        -(rank.get("action_count") or 0),
        rank.get("trip_readiness_score") or 0,
        rank.get("route_model_confidence_score") or 0,
        -(rank.get("pipeline_issue_severity") or 0),
        rank.get("pipeline_health_score") or 0,
        -(rank.get("route_model_warning_count") or 0),
        rank.get("route_model_basis_count") or 0,
        rank.get("swap_safety_score") or 0,
        rank.get("swap_coverage") or 0,
        rank.get("swap_low_friction_count") or 0,
        rank.get("swap_recommended_count") or 0,
        rank.get("swap_party_coverage_score") or 0,
        rank.get("swap_party_actionable_member_count") or 0,
        rank.get("swap_consensus_upgrade_count") or 0,
        -(rank.get("swap_route_risk_count") or 0),
        -(rank.get("swap_cost_caution_count") or 0),
        rank.get("swap_cost_saving_count") or 0,
        rank.get("logistics_readiness_score") or 0,
        -(rank.get("logistics_blocking_count") or 0),
        -(rank.get("logistics_missing_input_count") or 0),
        rank.get("booking_handoff_score") or 0,
        rank.get("booking_command_open_link_count") or 0,
        rank.get("booking_command_save_prompt_count") or 0,
        rank.get("booking_command_ready_count") or 0,
        -(rank.get("booking_command_action_count") or 0),
        rank.get("trip_style_fit_score") or 0,
        rank.get("trip_style_duration_fit") or 0,
        rank.get("trip_style_quote_coverage") or 0,
        rank.get("travel_quote_readiness_score") or 0,
        rank.get("travel_quote_ready_coverage") or 0,
        -(rank.get("travel_quote_missing_input_count") or 0),
        rank.get("logistics_provider_link_count") or 0,
        rank.get("logistics_save_ready_count") or 0,
        rank.get("route_score") or 0,
        rank.get("planned_stop_count") or 0,
        rank.get("stop_coverage") or 0,
        rank.get("authenticity_score") or 0,
        rank.get("hidden_gem_count") or 0,
        -(rank.get("chain_risk") or 0),
        rank.get("friend_coverage_share") if (rank.get("friend_member_count") or 0) > 1 else 0,
        rank.get("friend_average_fit") if (rank.get("friend_member_count") or 0) > 1 else 0,
        1 if rank.get("friend_testable") and (rank.get("friend_member_count") or 0) > 1 else 0,
        (rank.get("friend_test_score") or 0) if (rank.get("friend_member_count") or 0) > 1 else 0,
        -(rank.get("friend_test_blocker_count") or 0) if (rank.get("friend_member_count") or 0) > 1 else 0,
        rank.get("friend_rescue_count") if (rank.get("friend_member_count") or 0) > 1 else 0,
        -(rank.get("effective_underserved_count", rank.get("friend_underserved_count") or 0)),
        rank.get("group_fairness_score") if (rank.get("group_member_count") or 0) > 1 else 0,
        rank.get("group_lowest_fit") if (rank.get("group_member_count") or 0) > 1 else 0,
        -(rank.get("effective_underserved_count", rank.get("underserved_count") or 0)),
        rank.get("event_score") or 0,
        rank.get("event_social_score") or 0,
        rank.get("event_actionability_score") or 0,
        rank.get("event_reservation_ready_count") or 0,
        rank.get("event_actionable_count") or 0,
        rank.get("event_friend_signal_count") or 0,
        rank.get("event_social_anchor_count") or 0,
        rank.get("booking_actionable_score") or 0,
        rank.get("booking_saved_coverage") or 0,
        rank.get("booking_confirmed_detail_count") or 0,
        rank.get("booking_saved_detail_count") or 0,
        rank.get("booking_action_coverage") or 0,
        rank.get("booking_saveable_coverage") or 0,
        rank.get("booking_score") or 0,
        rank.get("party_score") or 0,
        -(rank.get("planning_burden_score") or 0),
        -(rank.get("planning_action_needed_count") or 0),
        -(rank.get("planning_manual_count") or 0),
        -(rank.get("planning_setup_count") or 0),
        -(rank.get("warning_count") or 0),
        rank.get("strength_count") or 0,
        rank.get("known_cost_tiebreaker") or 0,
    )


def _itinerary_comparison_explanation(result, rank):
    readiness = result.get("route_readiness") or {}
    launch_checklist = result.get("launch_checklist") or {}
    scenario_readiness = result.get("scenario_readiness") or {}
    friend_readiness = scenario_readiness.get("friend_readiness") or {}
    authenticity = _itinerary_authenticity_summary(result)
    group_fit = _itinerary_group_fit_summary(result)
    party_rescue = _itinerary_party_rescue_summary(result)
    per_person = ((result.get("price_breakdown") or {}).get("per_person") or {})
    warnings = readiness.get("warnings") or []
    tradeoffs = []

    if rank.get("can_start"):
        tradeoffs.append({
            "kind": "launch",
            "label": "Launch",
            "value": "Ready",
            "tone": "positive",
        })
    else:
        fix_count = (rank.get("blocking_count") or 0) + (rank.get("action_count") or 0)
        tradeoffs.append({
            "kind": "launch",
            "label": "Launch",
            "value": f"{fix_count or 1} fix{'es' if fix_count != 1 else ''}",
            "tone": "caution",
        })

    if authenticity.get("score"):
        tradeoffs.append({
            "kind": "authenticity",
            "label": "Local signal",
            "value": f"{round(authenticity['score'] * 100)}%",
            "tone": "positive" if authenticity["score"] >= 0.7 else "neutral",
        })

    if rank.get("route_model_confidence_score"):
        model_score = rank.get("route_model_confidence_score") or 0
        tradeoffs.append({
            "kind": "model_signal",
            "label": "Model signal",
            "value": f"{round(model_score * 100)}%",
            "tone": "positive" if model_score >= 0.72 else "caution" if model_score < 0.46 or rank.get("route_model_warning_count") else "neutral",
        })
    if rank.get("learned_requested"):
        tradeoffs.append({
            "kind": "learned",
            "label": "Learning",
            "value": "Active" if rank.get("learned_active") else "Paused",
            "tone": "positive" if rank.get("learned_active") else "caution",
        })
    if rank.get("pipeline_issue_name"):
        tradeoffs.append({
            "kind": "pipeline",
            "label": "Pipeline",
            "value": str(rank.get("pipeline_issue_label") or "Tune"),
            "tone": "caution" if rank.get("pipeline_issue_severity") else "neutral",
        })

    if (rank.get("friend_member_count") or 0) > 1:
        friend_test_status = str(rank.get("friend_test_status") or "watch").replace("_", " ").title()
        tradeoffs.append({
            "kind": "friend_test",
            "label": "Friend test",
            "value": "Ready" if rank.get("friend_testable") else friend_test_status,
            "tone": (
                "positive"
                if rank.get("friend_testable")
                else "caution"
                if rank.get("friend_test_blocker_count")
                else "neutral"
            ),
        })
        tradeoffs.append({
            "kind": "friend_coverage",
            "label": "Friend coverage",
            "value": f"{round((rank.get('friend_coverage_share') or 0) * 100)}%",
            "tone": "positive" if rank.get("friend_coverage_share", 0) >= 1 and not rank.get("friend_underserved_count") else "caution",
        })
        if rank.get("friend_average_fit"):
            tradeoffs.append({
                "kind": "friend_fit",
                "label": "Route fit",
                "value": f"{round(rank['friend_average_fit'] * 100)}%",
                "tone": "positive" if rank["friend_average_fit"] >= 0.7 else "neutral",
            })
        if rank.get("friend_rescue_count"):
            rescued_names = ", ".join((rank.get("friend_rescued_members") or [])[:2])
            tradeoffs.append({
                "kind": "friend_rescue",
                "label": "Made room",
                "value": rescued_names or f"{rank['friend_rescue_count']} stop",
                "tone": "positive",
            })
        if rank.get("swap_party_actionable_member_count"):
            tradeoffs.append({
                "kind": "group_swaps",
                "label": "Group swaps",
                "value": f"{rank.get('swap_party_actionable_member_count')} ready",
                "tone": "positive",
            })
    elif group_fit.get("member_count", 0) > 1 and group_fit.get("fairness_score") is not None:
        tradeoffs.append({
            "kind": "party",
            "label": "Party fair",
            "value": f"{round(group_fit['fairness_score'] * 100)}%",
            "tone": "caution" if group_fit.get("underserved_count") else "positive",
        })
        if rank.get("swap_party_actionable_member_count"):
            tradeoffs.append({
                "kind": "group_swaps",
                "label": "Group swaps",
                "value": f"{rank.get('swap_party_actionable_member_count')} ready",
                "tone": "positive",
            })
    elif rank.get("party_score"):
        tradeoffs.append({
            "kind": "party",
            "label": "Party fit",
            "value": f"{round(rank['party_score'] * 100)}%",
            "tone": "positive" if rank["party_score"] >= 0.75 else "neutral",
        })

    if rank.get("event_score"):
        tradeoffs.append({
            "kind": "events",
            "label": "Events",
            "value": f"{round(rank['event_score'] * 100)}%",
            "tone": "positive" if rank["event_score"] >= 0.75 else "neutral",
        })
    if rank.get("event_actionability_score") and (rank.get("event_route_match_count") or rank.get("event_actionable_count")):
        event_value = (
            f"{rank.get('event_reservation_ready_count')} RSVP"
            if rank.get("event_reservation_ready_count")
            else f"{rank.get('event_actionable_count') or 0} linked"
        )
        tradeoffs.append({
            "kind": "event_actionability",
            "label": "Event plan",
            "value": event_value,
            "tone": "positive" if rank.get("event_reservation_ready_count") else "neutral",
        })
    if rank.get("event_social_score") or rank.get("event_social_anchor_count"):
        social_value = (
            f"{rank.get('event_friend_signal_count')} friend"
            if rank.get("event_friend_signal_count")
            else f"{rank.get('event_social_anchor_count') or 0} anchor"
        )
        tradeoffs.append({
            "kind": "event_social",
            "label": "Social",
            "value": social_value,
            "tone": "positive" if (rank.get("event_social_score") or 0) >= 0.5 else "neutral",
        })

    if rank.get("swap_stop_count"):
        swap_value = f"{rank.get('swap_low_friction_count') or 0}/{rank.get('swap_stop_count') or 0} easy"
        tradeoffs.append({
            "kind": "swap_safety",
            "label": "Swap safety",
            "value": swap_value,
            "tone": (
                "positive"
                if (rank.get("swap_safety_score") or 0) >= 0.65 and not rank.get("swap_route_risk_count")
                else "caution"
                if rank.get("swap_route_risk_count") or rank.get("swap_cost_caution_count")
                else "neutral"
            ),
        })
        if rank.get("swap_cost_saving_count"):
            tradeoffs.append({
                "kind": "swap_cost",
                "label": "Cheaper swaps",
                "value": str(rank.get("swap_cost_saving_count")),
                "tone": "positive",
            })
        elif rank.get("swap_cost_caution_count"):
            tradeoffs.append({
                "kind": "swap_cost",
                "label": "Pricier swaps",
                "value": str(rank.get("swap_cost_caution_count")),
                "tone": "caution",
            })

    if rank.get("travel_quote_required_count"):
        tradeoffs.append({
            "kind": "travel_quotes",
            "label": "Travel quotes",
            "value": f"{rank.get('travel_quote_ready_count') or 0}/{rank.get('travel_quote_required_count') or 0} ready",
            "tone": "positive" if rank.get("travel_quote_readiness_score", 0) >= 0.85 else "caution" if rank.get("travel_quote_missing_input_count") else "neutral",
        })

    if rank.get("trip_style_fit_score"):
        style_score = rank.get("trip_style_fit_score") or 0
        tradeoffs.append({
            "kind": "trip_style",
            "label": "Style fit",
            "value": f"{round(style_score * 100)}%",
            "tone": "positive" if style_score >= 0.78 else "caution" if style_score < 0.55 or rank.get("trip_style_fit_status") == "needs_attention" else "neutral",
        })

    if rank.get("booking_actionable_score"):
        tradeoffs.append({
            "kind": "booking",
            "label": "Bookable",
            "value": f"{round(rank['booking_actionable_score'] * 100)}%",
            "tone": "positive" if rank["booking_actionable_score"] >= 0.75 else "neutral",
        })

    if rank.get("logistics_readiness_score"):
        logistics_score = rank.get("logistics_readiness_score") or 0
        tradeoffs.append({
            "kind": "trip_logistics",
            "label": "Trip logistics",
            "value": f"{round(logistics_score * 100)}%",
            "tone": "positive" if logistics_score >= 0.78 and not rank.get("logistics_missing_input_count") else "caution" if rank.get("logistics_missing_input_count") or logistics_score < 0.52 else "neutral",
        })

    if rank.get("booking_handoff_score"):
        handoff_value = (
            f"{rank.get('booking_command_open_link_count') or 0} open / {rank.get('booking_command_save_prompt_count') or 0} save"
            if rank.get("booking_command_open_link_count") or rank.get("booking_command_save_prompt_count")
            else f"{round((rank.get('booking_handoff_score') or 0) * 100)}%"
        )
        tradeoffs.append({
            "kind": "booking_handoff",
            "label": "Trip handoff",
            "value": handoff_value,
            "tone": (
                "positive"
                if (rank.get("booking_handoff_score") or 0) >= 0.72 and not rank.get("booking_command_action_count")
                else "caution"
                if rank.get("booking_command_action_count") or (rank.get("booking_handoff_score") or 0) < 0.45
                else "neutral"
            ),
        })

    saved_required_count = rank.get("booking_saved_required_count") or 0
    saved_detail_count = rank.get("booking_saved_detail_count") or 0
    if saved_required_count > 0:
        tradeoffs.append({
            "kind": "saved_booking_details",
            "label": "Saved details",
            "value": f"{saved_detail_count}/{saved_required_count} saved",
            "tone": "positive" if rank.get("booking_saved_coverage", 0) >= 0.85 else "caution",
        })

    link_count = rank.get("booking_action_link_count") or 0
    if link_count > 0:
        tradeoffs.append({
            "kind": "booking_links",
            "label": "Booking links",
            "value": f"{link_count} ready",
            "tone": "positive" if link_count >= 2 else "caution",
        })

    if rank.get("planning_burden_level"):
        tradeoffs.append({
            "kind": "planning",
            "label": "Planning",
            "value": str(rank["planning_burden_level"]).title(),
            "tone": "caution" if rank.get("planning_burden_score", 0) >= 0.5 else "positive",
        })

    known_low = per_person.get("total_known_low")
    known_high = per_person.get("total_known_high")
    if known_low is not None and known_high is not None:
        tradeoffs.append({
            "kind": "cost",
            "label": "Known cost",
            "value": f"${round(known_low)}-${round(known_high)}",
            "tone": "neutral",
        })

    if rank.get("learned_inactive"):
        headline = "Learned beta is not active yet; compare this as the balanced route fallback."
    elif not rank.get("can_start"):
        headline = launch_checklist.get("headline") or "Strong idea, but it needs route work before launch."
    elif rank.get("pipeline_issue_status") == "fail":
        headline = f"Best route, but tune {str(rank.get('pipeline_issue_label') or 'pipeline').lower()} first."
    elif (
        (rank.get("friend_member_count") or 0) > 1
        and (rank.get("friend_coverage_share") or 0) >= 1
        and (rank.get("friend_average_fit") or 0) >= 0.7
        and (rank.get("booking_saved_coverage") or 0) >= 0.85
    ):
        headline = "Best saved-booking route with every friend covered."
    elif (
        (rank.get("event_actionability_score") or 0) >= 0.72
        and (rank.get("event_route_match_count") or 0) > 0
        and (rank.get("event_reservation_ready_count") or 0) > 0
        and (
            (rank.get("event_social_score") or 0) >= 0.45
            or (rank.get("event_friend_signal_count") or 0) > 0
        )
    ):
        headline = "Best route with an actionable local-event anchor."
    elif (
        (
            (rank.get("friend_underserved_count") or 0) > 0
            or (rank.get("swap_party_underserved_member_count") or 0) > 0
        )
        and (rank.get("swap_party_actionable_member_count") or 0) > 0
    ):
        headline = "Best route with group swaps ready for weaker friend fits."
    elif (
        (rank.get("booking_saved_coverage") or 0) >= 0.85
        and rank.get("planning_burden_level") == "low"
    ):
        headline = "Best route with booking details already saved."
    elif (
        (rank.get("booking_handoff_score") or 0) >= 0.72
        and (rank.get("booking_command_open_link_count") or 0) >= 2
        and (rank.get("booking_command_save_prompt_count") or 0) >= 1
        and rank.get("planning_burden_level") == "low"
    ):
        headline = "Best route with booking handoff ready."
    elif (
        (rank.get("friend_member_count") or 0) > 1
        and (rank.get("friend_coverage_share") or 0) >= 1
        and (rank.get("friend_average_fit") or 0) >= 0.7
        and rank.get("planning_burden_level") == "low"
        and (rank.get("booking_action_link_count") or 0) >= 2
    ):
        headline = "Best bookable route with every friend covered."
    elif (
        (rank.get("booking_actionable_score") or 0) >= 0.75
        and (rank.get("booking_action_link_count") or 0) >= 2
        and rank.get("planning_burden_level") == "low"
    ):
        headline = "Best route to book and launch with less planning."
    elif (
        (rank.get("swap_safety_score") or 0) >= 0.65
        and (rank.get("swap_low_friction_count") or 0) >= max(1, min(2, rank.get("swap_stop_count") or 0))
        and not rank.get("swap_route_risk_count")
    ):
        headline = "Best route with safer swap flexibility."
    elif (
        (rank.get("logistics_readiness_score") or 0) >= 0.78
        and not rank.get("logistics_missing_input_count")
        and not rank.get("logistics_blocking_count")
        and (rank.get("travel_quote_required_count") or 0) > 0
        and (rank.get("travel_quote_readiness_score") or 0) >= 0.85
    ):
        headline = "Best route with travel quotes ready to compare."
    elif (
        (rank.get("logistics_readiness_score") or 0) >= 0.78
        and not rank.get("logistics_missing_input_count")
        and not rank.get("logistics_blocking_count")
    ):
        headline = "Best route with travel logistics ready to share."
    elif (
        (rank.get("friend_member_count") or 0) > 1
        and (rank.get("friend_coverage_share") or 0) >= 1
        and (rank.get("friend_average_fit") or 0) >= 0.7
        and (rank.get("friend_rescue_count") or 0) > 0
    ):
        names = ", ".join((party_rescue.get("members") or [])[:2])
        headline = f"Best route that made room for {names or 'the group'}."
    elif (
        (rank.get("friend_member_count") or 0) > 1
        and (rank.get("friend_coverage_share") or 0) >= 1
        and (rank.get("friend_average_fit") or 0) >= 0.7
    ):
        headline = "Best route with a strong stop for every friend."
    elif (rank.get("friend_member_count") or 0) > 1 and rank.get("friend_underserved_count"):
        names = ", ".join(
            member.get("display_name")
            for member in (friend_readiness.get("underserved_members") or [])[:2]
            if member.get("display_name")
        )
        headline = f"Good route shell, but {names or 'one traveler'} needs a stronger stop."
    elif (
        rank.get("planning_burden_level") == "low"
        and group_fit.get("member_count", 0) > 1
        and (group_fit.get("fairness_score") or 0) >= 0.75
    ):
        headline = "Best low-friction route for the whole travel party."
    elif rank.get("planning_burden_level") == "low" and rank.get("trip_readiness_score", 0) >= 0.75:
        headline = "Best low-friction route to book and launch."
    elif authenticity.get("score", 0) >= 0.75:
        headline = "Best launchable route with strong local texture."
    elif (rank.get("event_social_score") or 0) >= 0.5 or (rank.get("event_friend_signal_count") or 0) > 0:
        title = rank.get("event_top_social_title")
        headline = f"Best route with a social event anchor{f' at {title}' if title else ''}."
    elif (
        (rank.get("route_model_confidence_score") or 0) >= 0.72
        and (rank.get("route_model_warning_count") or 0) == 0
    ):
        headline = "Best route with a trustworthy model signal."
    elif group_fit.get("member_count", 0) > 1 and group_fit.get("underserved_count"):
        headline = "Good route shell, but one traveler may need a stronger match."
    elif group_fit.get("member_count", 0) > 1 and (group_fit.get("fairness_score") or 0) >= 0.85:
        headline = "Best launchable route for the whole travel party."
    elif rank.get("party_score", 0) >= 0.8:
        headline = "Best launchable route for the travel party."
    elif rank.get("event_score", 0) >= 0.8:
        headline = "Best launchable route for local events."
    elif rank.get("route_score", 0) >= 0.8:
        headline = "Best overall route shape for this scout style."
    else:
        headline = "Most complete option from this comparison."

    return {
        "headline": headline,
        "tradeoffs": tradeoffs[:10],
        "cautions": _compact_unique_strings([
            _learned_inactive_caution(rank, mode="route"),
            (_pipeline_issue_summary_from_quality(result.get("recommendation_quality") or {}) or {}).get("next_action"),
            *warnings,
        ], limit=2),
    }


COMPARISON_NON_PROVIDER_CONSTRAINT_KEYS = {
    "scoring_profile",
    "record_impressions",
    "learned_rerank",
    "use_learned_rerank",
    "allow_unpromoted_learned_rerank",
}


class _CachedProviderRegistry:
    """Reuse one provider candidate fetch across scoring-profile comparisons."""

    def __init__(self, provider_registry):
        self.provider_registry = provider_registry
        self.cache = {}
        self.search_count = 0
        self.provider_fetch_count = 0
        self.cache_hit_count = 0
        self.stripped_constraint_keys = set()

    def search(self, tags, location, radius_meters=3200, constraints=None):
        constraints = constraints or {}
        self.search_count += 1
        self.stripped_constraint_keys.update(
            key for key in constraints.keys()
            if key in COMPARISON_NON_PROVIDER_CONSTRAINT_KEYS
        )
        provider_constraints = {
            key: value
            for key, value in constraints.items()
            if key not in COMPARISON_NON_PROVIDER_CONSTRAINT_KEYS
        }
        cache_key = json.dumps({
            "tags": sorted(tags or []),
            "location": location or {},
            "radius_meters": radius_meters,
            "constraints": provider_constraints,
        }, sort_keys=True, default=str)

        if cache_key not in self.cache:
            self.provider_fetch_count += 1
            self.cache[cache_key] = self.provider_registry.search(
                tags,
                location,
                radius_meters=radius_meters,
                constraints=provider_constraints,
            )
        else:
            self.cache_hit_count += 1
        return deepcopy(self.cache[cache_key])

    def usage_summary(self):
        return {
            "search_count": self.search_count,
            "provider_fetch_count": self.provider_fetch_count,
            "cache_hit_count": self.cache_hit_count,
            "cache_entry_count": len(self.cache),
            "saved_fetch_count": max(0, self.search_count - self.provider_fetch_count),
            "stripped_constraint_keys": sorted(self.stripped_constraint_keys),
        }


def _provider_usage_summary(service):
    registry = getattr(service, "provider_registry", None)
    if registry is None and hasattr(service, "recommendation_service"):
        registry = getattr(service.recommendation_service, "provider_registry", None)
    if hasattr(registry, "usage_summary"):
        return registry.usage_summary()
    return None


def _comparison_itinerary_service():
    if not hasattr(itinerary_service, "recommendation_service"):
        return itinerary_service

    cached_recommendation_service = RecommendationService(
        provider_registry=_CachedProviderRegistry(itinerary_service.recommendation_service.provider_registry)
    )
    return ItineraryRecommendationService(
        cached_recommendation_service,
        itinerary_service.local_event_service,
        itinerary_service.travel_logistics_service,
    )


def _comparison_recommendation_service():
    if not hasattr(recommendation_service, "provider_registry"):
        return recommendation_service
    return RecommendationService(
        provider_registry=_CachedProviderRegistry(recommendation_service.provider_registry),
        learned_model=getattr(recommendation_service, "learned_model", None),
    )


@app.route('/api/recommendations/compare', methods=['POST'])
@require_auth
def compare_recommendation_baskets():
    data = request.json or {}
    user = g.current_user

    try:
        payload = _recommendation_request_payload(data)
        base_constraints = dict(payload.get("constraints") or {})
        requested_profiles = data.get("scoring_profiles") or sorted(SCORING_PROFILES.keys())
        include_recommendations = bool(data.get("include_recommendations"))
        compare_service = _comparison_recommendation_service()
        comparisons = []
        for variant in _comparison_profile_variants(requested_profiles, base_constraints):
            result = compare_service.recommend(
                user=user,
                **{
                    **payload,
                    "constraints": variant["constraints"],
                },
            )
            result["scenario_readiness"] = recommendation_evaluation_service.scenario_readiness_report(result)
            summary = _basket_summary(result, include_recommendations=include_recommendations)
            summary["scoring_profile"] = variant["id"]
            if include_recommendations and summary.get("result"):
                summary["result"] = {
                    **summary["result"],
                    "comparison_profile": variant["id"],
                }
            comparisons.append(summary)

        comparisons.sort(
            key=_basket_comparison_sort_key,
            reverse=True,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Recommendation basket comparison request failed")
        return jsonify({"error": "Recommendation basket comparison request failed", "detail": str(exc)}), 500

    return jsonify({
        "recommended_profile": comparisons[0]["scoring_profile"] if comparisons else None,
        "comparisons": comparisons,
        "provider_usage": _provider_usage_summary(compare_service),
    }), 200


@app.route('/api/recommendations/itinerary', methods=['POST'])
@require_auth
def create_itinerary_recommendation():
    data = request.json or {}
    user = g.current_user

    try:
        payload = _itinerary_request_payload(data)
        result = itinerary_service.recommend_itinerary(
            user=user,
            **payload,
        )
        result["scenario_readiness"] = recommendation_evaluation_service.scenario_readiness_report(result)
        _attach_itinerary_friend_test_packet(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Itinerary recommendation request failed")
        return jsonify({"error": "Itinerary recommendation request failed", "detail": str(exc)}), 500

    return jsonify(result), 200

@app.route('/api/recommendations/itinerary/compare', methods=['POST'])
@require_auth
def compare_itinerary_recommendations():
    data = request.json or {}
    user = g.current_user

    try:
        payload = _itinerary_request_payload(data)
        base_constraints = dict(payload.get("constraints") or {})
        requested_profiles = data.get("scoring_profiles") or sorted(SCORING_PROFILES.keys())
        include_plans = bool(data.get("include_plans"))
        compare_service = _comparison_itinerary_service()
        comparisons = []
        for variant in _comparison_profile_variants(requested_profiles, base_constraints):
            result = compare_service.recommend_itinerary(
                user=user,
                **{
                    **payload,
                    "constraints": variant["constraints"],
                },
            )
            result["scenario_readiness"] = recommendation_evaluation_service.scenario_readiness_report(result)
            _attach_itinerary_friend_test_packet(result)
            summary = _itinerary_summary(result, include_plan=include_plans)
            summary["scoring_profile"] = variant["id"]
            if include_plans and summary.get("plan"):
                summary["plan"] = {
                    **summary["plan"],
                    "comparison_profile": variant["id"],
                }
            comparisons.append(summary)

        comparisons.sort(
            key=_itinerary_comparison_sort_key,
            reverse=True,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Itinerary comparison request failed")
        return jsonify({"error": "Itinerary comparison request failed", "detail": str(exc)}), 500

    return jsonify({
        "recommended_profile": comparisons[0]["scoring_profile"] if comparisons else None,
        "comparisons": comparisons,
        "provider_usage": _provider_usage_summary(compare_service),
    }), 200


@app.route('/api/recommendations/destinations/compare', methods=['POST'])
@require_auth
def compare_destination_recommendations():
    data = request.json or {}
    user = g.current_user

    try:
        payload = _destination_compare_request_payload(data)
        base_constraints = dict(payload.get("constraints") or {})
        requested_profiles = payload.get("scoring_profiles")
        include_plans = payload.get("include_plans")
        include_profile_comparisons = payload.get("include_profile_comparisons")
        compare_service = _comparison_itinerary_service()
        comparisons = []

        for destination in payload["destinations"]:
            destination_constraints = {
                **base_constraints,
                **(destination.get("constraints") or {}),
            }
            destination_profiles = requested_profiles or [
                destination_constraints.get("scoring_profile") or "phase1_balanced"
            ]
            profile_summaries = []
            for variant in _comparison_profile_variants(destination_profiles, destination_constraints):
                result = compare_service.recommend_itinerary(
                    user=user,
                    location=destination["location"],
                    radius_meters=destination["radius_meters"],
                    member_ids=payload["member_ids"],
                    constraints=variant["constraints"],
                    party_size=payload["party_size"],
                    days=payload["days"],
                    destination_label=destination["label"],
                )
                result["scenario_readiness"] = recommendation_evaluation_service.scenario_readiness_report(result)
                _attach_itinerary_friend_test_packet(result)
                summary = _itinerary_summary(result, include_plan=include_plans)
                summary["destination"] = destination
                summary["destination_id"] = destination["id"]
                summary["destination_label"] = destination["label"]
                summary["destination_rank"] = summary.get("comparison_rank")
                summary["comparison_mode"] = "destination"
                summary["scoring_profile"] = variant["id"]
                if include_plans and summary.get("plan"):
                    summary["plan"] = {
                        **summary["plan"],
                        "comparison_profile": variant["id"],
                        "comparison_destination": destination,
                        "comparison_destination_rank": summary.get("comparison_rank"),
                        "comparison_destination_explanation": summary.get("comparison_explanation"),
                    }
                profile_summaries.append(summary)

            profile_summaries.sort(key=_itinerary_comparison_sort_key, reverse=True)
            if profile_summaries:
                best_summary = profile_summaries[0]
                if include_profile_comparisons:
                    best_summary["profile_comparisons"] = [
                        _destination_profile_comparison_payload(profile_summary)
                        for profile_summary in profile_summaries
                    ]
                comparisons.append(best_summary)

        comparisons.sort(key=_itinerary_comparison_sort_key, reverse=True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Destination comparison request failed")
        return jsonify({"error": "Destination comparison request failed", "detail": str(exc)}), 500

    return jsonify({
        "recommended_destination": comparisons[0]["destination"] if comparisons else None,
        "recommended_destination_label": comparisons[0]["destination_label"] if comparisons else None,
        "recommended_profile": comparisons[0]["scoring_profile"] if comparisons else None,
        "comparisons": comparisons,
        "provider_usage": _provider_usage_summary(compare_service),
    }), 200

@app.route('/api/local-events/recommendations', methods=['POST'])
@require_auth
def recommend_local_events():
    data = request.json or {}
    location = data.get("location") or {}
    latitude = location.get("latitude")
    longitude = location.get("longitude")
    if latitude is None or longitude is None:
        return jsonify({"error": "location.latitude and location.longitude are required"}), 400

    accepted_ids = set(accepted_friend_ids(g.current_user.id))
    requested_member_ids = data.get("member_ids") or []
    friend_user_ids = []
    if requested_member_ids:
        for member_id in requested_member_ids:
            try:
                parsed_id = int(member_id)
            except (TypeError, ValueError):
                continue
            if parsed_id in accepted_ids:
                friend_user_ids.append(parsed_id)
    else:
        friend_user_ids = list(accepted_ids)

    result = local_event_service.recommend_events(
        location={"latitude": float(latitude), "longitude": float(longitude)},
        radius_meters=int(data.get("radius_meters", 8000)),
        destination_label=data.get("destination_label"),
        limit=int(data.get("limit", 6)),
        date_window=data.get("travel_dates"),
        preference_tags=data.get("preference_tags") or data.get("query_tags") or [],
        viewer_user_id=g.current_user.id,
        friend_user_ids=friend_user_ids,
    )
    return jsonify(result), 200

@app.route('/api/local-events', methods=['POST'])
@require_auth
def create_local_event():
    data = request.json or {}
    user = g.current_user
    title = (data.get("title") or "").strip()
    starts_at = data.get("starts_at")
    if not title or not starts_at:
        return jsonify({"error": "title and starts_at are required"}), 400

    try:
        starts_at_dt = datetime.fromisoformat(starts_at.replace("Z", "+00:00")).replace(tzinfo=None)
        ends_at_dt = None
        if data.get("ends_at"):
            ends_at_dt = datetime.fromisoformat(data["ends_at"].replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return jsonify({"error": "starts_at and ends_at must be ISO timestamps"}), 400

    event = LocalEvent(
        title=title,
        description=data.get("description"),
        city=data.get("city"),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        starts_at=starts_at_dt,
        ends_at=ends_at_dt,
        category=data.get("category"),
        source_name=data.get("source_name") or "Community submission",
        source_url=data.get("source_url"),
        reservation_url=data.get("reservation_url"),
        price_low=data.get("price_low"),
        price_high=data.get("price_high"),
        authenticity_score=data.get("authenticity_score", 0.8),
        host_user_id=user.id,
    )
    db.session.add(event)
    db.session.commit()

    return jsonify({
        "message": "Local event submitted",
        "event": local_event_service._event_payload(
            event,
            score=1.0,
            distance_meters=None,
            social_context=local_event_social_payload(event.id, user.id),
        ),
    }), 201

@app.route('/api/local-events/<int:event_id>/interest', methods=['POST'])
@require_auth
def upsert_local_event_interest(event_id):
    data = request.json or {}
    user = g.current_user
    event = LocalEvent.query.filter_by(id=event_id, status="active").first()
    if not event:
        return jsonify({"error": "Local event not found"}), 404

    status = (data.get("status") or "interested").strip().lower()
    if status not in {"interested", "going"}:
        return jsonify({"error": "status must be interested or going"}), 400

    interest = LocalEventInterest.query.filter_by(event_id=event.id, user_id=user.id).first()
    if not interest:
        interest = LocalEventInterest(event_id=event.id, user_id=user.id)
        db.session.add(interest)
    interest.status = status
    interest.note = data.get("note")
    db.session.commit()

    return jsonify({
        "message": "Event interest saved",
        "event_id": event.id,
        "status": status,
        "social": local_event_social_payload(event.id, user.id),
    }), 200

@app.route('/api/local-events/<int:event_id>/interest', methods=['DELETE'])
@require_auth
def delete_local_event_interest(event_id):
    user = g.current_user
    event = LocalEvent.query.filter_by(id=event_id, status="active").first()
    if not event:
        return jsonify({"error": "Local event not found"}), 404

    interest = LocalEventInterest.query.filter_by(event_id=event.id, user_id=user.id).first()
    if interest:
        db.session.delete(interest)
        db.session.commit()

    return jsonify({
        "message": "Event interest removed",
        "event_id": event.id,
        "social": local_event_social_payload(event.id, user.id),
    }), 200

@app.route('/api/dev/seed-place', methods=['POST'])
def seed_dev_place():
    """Create a local development place near a coordinate for recommender smoke tests."""
    if os.getenv("ADVENTOUR_DEV_AUTH") != "true":
        return jsonify({"error": "Dev tools are disabled"}), 403

    data = request.json or {}
    name = data.get("name") or "Adventour Local Test Cafe"
    latitude = float(data.get("latitude", 37.421998333333335))
    longitude = float(data.get("longitude", -122.084))

    place = Place.query.filter_by(normalized_name=name.lower()).first()
    if not place:
        place = Place(
            canonical_name=name,
            normalized_name=name.lower(),
            latitude=latitude,
            longitude=longitude,
            source_confidence=1.0,
        )
        db.session.add(place)
    else:
        place.latitude = latitude
        place.longitude = longitude

    db.session.commit()

    return jsonify({
        "place": {
            "id": place.id,
            "name": place.canonical_name,
            "latitude": place.latitude,
            "longitude": place.longitude,
        }
    }), 201

@app.route('/places/<place_id>/ratings', methods=['GET'])
def get_place_ratings(place_id):
    """Get all ratings for a specific place"""
    ratings = PlaceRating.query.filter_by(place_id=place_id).all()
    
    rating_data = []
    for rating in ratings:
        user = User.query.get(rating.user_id)
        rating_data.append({
            'id': rating.id,
            'rating': rating.rating,
            'review': rating.review,
            'created_at': rating.created_at.isoformat(),
            'user': {
                'id': user.id,
                'username': user.username,
                'display_name': user.display_name
            }
        })
    
    # Calculate average rating
    if ratings:
        avg_rating = sum(r.rating for r in ratings) / len(ratings)
        total_ratings = len(ratings)
    else:
        avg_rating = 0
        total_ratings = 0
    
    return jsonify({
        'place_id': place_id,
        'average_rating': round(avg_rating, 2),
        'total_ratings': total_ratings,
        'ratings': rating_data
    })

@app.route('/geocode', methods=['GET'])
def geocode():    
    address = request.args.get('address')
    latitude = request.args.get('latitude')
    longitude = request.args.get('longitude')

    logger.info("Received geocode request address=%s latitude=%s longitude=%s", address, latitude, longitude)

    if address:
        try:
            coordinates = GoogleServicesAPI.fetch_city_coordinates(address)
            if not coordinates:
                return jsonify({"error": "Unable to resolve address to coordinates"}), 404
            return jsonify(coordinates)
        except Exception as e:
            return jsonify({"error": f"Error resolving address: {str(e)}"}), 500
    elif latitude and longitude:
        try:
            location = GoogleServicesAPI.reverse_geocode(latitude, longitude)
            if not location:
                location = GoogleServicesAPI.coordinate_fallback(latitude, longitude)
            return jsonify(location)
        except Exception as e:
                logger.exception("Error resolving coordinates")
                return jsonify({"error": f"Error resolving coordinates: {str(e)}"}), 500
    else:
        return jsonify({"error": "Either address or coordinates must be provided"}), 400

@app.route('/api/places/autocomplete', methods=['GET'])
def places_autocomplete():
    input_text = request.args.get('input', '').strip()
    latitude = request.args.get('latitude')
    longitude = request.args.get('longitude')
    radius_meters = int(request.args.get('radius_meters', 3200))

    if len(input_text) < 3:
        return jsonify({"predictions": []})

    predictions = GoogleServicesAPI.fetch_autocomplete(
        input_text,
        latitude,
        longitude,
        radius_meters,
    )
    return jsonify({"predictions": predictions})

@app.route('/fetch-places', methods=['POST'])
def fetch_places():
    """
    Fetch places from Google Places API based on tags and location.
    Only return places with business_status 'OPERATIONAL'.
    """
    data = request.json
    tags = data.get("tags", [])
    location = data.get("location")

    if not tags or not location:
        return jsonify({"error": "Tags and location are required"}), 400

    try:
        # Fetch places using GoogleServicesAPI
        all_places = GoogleServicesAPI.fetch_places(tags, location)

        # Filter places with 'business_status' as 'OPERATIONAL'
        operational_places = [
            place for place in all_places
            if place.get('business_status') == 'OPERATIONAL'
        ]

        return jsonify(operational_places)
    except Exception as e:
        return jsonify({"error": f"Error fetching places: {str(e)}"}), 500

@app.route('/recommendations', methods=['GET'])
@optional_auth
def get_recommendations():
    # Try to get authenticated user first
    user = None
    if hasattr(g, 'current_user'):
        user = g.current_user
    else:
        # Fallback to old user_id parameter
        user_id = request.args.get('user_id')
        if user_id:
            user = User.query.filter_by(uuid=user_id).first()
    
    address = request.args.get('address')
    latitude = request.args.get('latitude')
    longitude = request.args.get('longitude')

    if not user:
        return jsonify({"error": "User authentication required"}), 401

    # Resolve coordinates
    if latitude and longitude:
        try:
            lat, lng = float(latitude), float(longitude)
            coordinates = {"latitude": lat, "longitude": lng}
        except ValueError:
            return jsonify({"error": "Invalid latitude or longitude format"}), 400
    elif address:
        try:
            coordinates = GoogleServicesAPI.fetch_city_coordinates(address)
            if not coordinates:
                return jsonify({"error": "Unable to resolve address to coordinates"}), 404
        except Exception as e:
            return jsonify({"error": f"Error resolving address: {str(e)}"}), 500
    else:
        return jsonify({"error": "Either coordinates or address must be provided"}), 400

    feedback_entries = UserTagFeedback.query.filter_by(user_id=user.id).all()

    tag_scores = {}
    rejected_place_ids = set()

    if feedback_entries:
        for fb in feedback_entries:
            tags = fb.place_tags.split(',')
            weight = 3 if fb.verdict == 'accept' else -1
            for i, tag in enumerate(tags[:3]):
                tag_scores[tag] = tag_scores.get(tag, 0) + (3 - i) * weight
            if fb.verdict == 'reject':
                rejected_place_ids.add(fb.place_id)

        max_score = max(tag_scores.values(), default=1)
        tag_scores = {tag: score / max_score for tag, score in tag_scores.items()}
    else:
        # Fallback to onboarding preferences
        if user.preferences:
            tags = user.preferences.split(',')
            tag_scores = {tag: 1.0 for tag in tags}
        else:
            return jsonify({"error": "No feedback or preferences available"}), 404

    # Fetch and score places
    try:
        places = GoogleServicesAPI.fetch_places(list(tag_scores.keys()), coordinates)
    except Exception as e:
        return jsonify({"error": f"Error fetching places: {str(e)}"}), 500

    scored_places = []
    for place in places:
        place_id = place.get('place_id')
        if place_id in rejected_place_ids:
            continue

        types = place.get('types', [])
        raw_score = sum(tag_scores.get(tag, 0) for tag in types)
        max_possible = len(types) * max(tag_scores.values(), default=1)
        relevance = raw_score / max_possible if max_possible else 0

        # Authenticity & sentiment boosts
        boost = 1.0
        if is_hidden_gem(place):
            boost = 2.0  # Highest boost for hidden gems
        else:
            # Sentiment analysis on reviews (if available)
            sentiment = 0
            if 'reviews' in place:
                sentiment = review_sentiment_score(place['reviews'])
            if sentiment > 0.1:  # threshold for positive sentiment
                boost = 1.5  # Slightly lower than hidden gem

        # Down-rank if chain
        if is_chain(place.get('name', '')):
            boost *= 0.5

        final_score = relevance * boost

        # --- Composite likelihood score ---
        likelihood = relevance
        if is_hidden_gem(place):
            likelihood += 0.4
        likelihood += 0.3 * (sentiment if 'sentiment' in locals() else 0)
        if is_chain(place.get('name', '')):
            likelihood -= 0.3
        likelihood = max(0, min(likelihood, 1))

        # --- Fun label --- (not in use yet)
        if likelihood >= 0.9:
            fun_label = "Perfect for you! 😍"
        elif likelihood >= 0.7:
            fun_label = "Great match! 👍"
        elif likelihood >= 0.5:
            fun_label = "Worth a try! 🤔"
        else:
            fun_label = "Maybe not your vibe 😐"

        if final_score > 0:
            scored_places.append({
                "place": place,
                "relevance": round(final_score, 2),
                "hidden_gem": is_hidden_gem(place),
                "sentiment_score": sentiment if 'sentiment' in locals() else 0,
                "likelihood": round(likelihood, 2)
            })

    scored_places.sort(key=lambda x: x["relevance"], reverse=True)
    return jsonify(scored_places)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))

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
    AdventourSession,
    AdventourStop,
)
from adventour_backend.auth import require_auth, optional_auth
from adventour_backend.social_routes import social_bp
from adventour_backend.services.recommender_service import RecommendationService
from adventour_backend.services.google_services_api import first_photo_url

from dotenv import load_dotenv
from urllib.parse import quote_plus
from datetime import datetime
import os
import logging
import json

env_file = os.getenv("ENV_FILE")
if env_file:
    load_dotenv(env_file, override=True)
else:
    load_dotenv()

logger = logging.getLogger(__name__)


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

# Initialize the database
with app.app_context():
    db.create_all()

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

def isoformat_or_none(value):
    return value.isoformat() if value else None

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

def serialize_adventour_session(session, include_stops=True):
    stops = session.stops.all() if include_stops else []
    return {
        "id": session.id,
        "title": session.title,
        "status": session.status,
        "started_at": isoformat_or_none(session.started_at),
        "ended_at": isoformat_or_none(session.ended_at),
        "companion_user_ids": parse_json_object(session.companion_user_ids_json, {"ids": []}).get("ids", []),
        "summary": parse_json_object(session.summary_json),
        "stops": [serialize_adventour_stop(stop) for stop in stops],
        "active_stop": serialize_adventour_stop(stops[-1]) if stops and stops[-1].status in ("planned", "navigating", "arrived") else None,
    }
    
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
        return jsonify({"onboarded": False}), 200
    
    return jsonify({
        "onboarded": bool(user.preferences),
        "preferences": user.preferences.split(',') if user.preferences else [],
        "user_id": user.id,
        "username": user.username,
        "display_name": user.display_name
    }), 200

@app.route('/user', methods=['POST'])
@require_auth
def create_user():
    """Create a new user from Firebase data"""
    data = request.json
    user = g.current_user
    
    # Update user with provided data
    if data.get('display_name'):
        user.display_name = data['display_name']
    if data.get('profile_picture'):
        user.profile_picture = data['profile_picture']
    
    db.session.commit()
    
    return jsonify({
        "message": "User created successfully",
        "user": {
            "id": user.id,
            "firebase_uid": user.firebase_uid,
            "email": user.email,
            "username": user.username,
            "display_name": user.display_name,
            "profile_picture": user.profile_picture
        }
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
        "user": {
            "id": user.id,
            "firebase_uid": user.firebase_uid,
            "email": user.email,
            "username": user.username,
            "display_name": user.display_name,
            "profile_picture": user.profile_picture,
            "preferences": user.preferences.split(',') if user.preferences else [],
        }
    }), 200

@app.route('/user/profile', methods=['PUT'])
@require_auth
def update_user_profile():
    """Update user profile"""
    data = request.json
    user = g.current_user
    
    if data.get('display_name'):
        user.display_name = data['display_name']
    if data.get('profile_picture'):
        user.profile_picture = data['profile_picture']
    
    db.session.commit()
    
    return jsonify({
        "message": "Profile updated successfully",
        "user": {
            "id": user.id,
            "firebase_uid": user.firebase_uid,
            "email": user.email,
            "username": user.username,
            "display_name": user.display_name,
            "profile_picture": user.profile_picture
        }
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
    metadata = {
        "source": data.get("source", "recommendation_deck"),
        "provider": data.get("provider"),
        "provider_place_id": data.get("provider_place_id"),
        "display": display,
    }
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

    stop.status = "completed"
    stop.arrived_at = stop.arrived_at or datetime.utcnow()
    stop.departed_at = datetime.utcnow()
    stop.rating = rating
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
    session.summary_json = json.dumps({
        "stop_count": len(completed_stops),
        "duration_seconds": max(0, duration_seconds),
        "rated_stop_count": len([stop for stop in completed_stops if stop.rating]),
    })
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
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Recommendation request failed")
        return jsonify({"error": "Recommendation request failed", "detail": str(exc)}), 500

    return jsonify(result), 200

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

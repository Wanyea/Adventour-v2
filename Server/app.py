from flask import Flask, request, jsonify, g, redirect
from flask_cors import CORS
from adventour_backend.services.google_services_api import GoogleServicesAPI
from adventour_backend.models import (
    db,
    User,
    PlaceRating,
    AdventourSession,
    AdventourStop,
)
from adventour_backend.auth import require_auth, optional_auth
from adventour_backend.social_routes import social_bp
from adventour_backend.services.google_services_api import first_photo_url
from adventour_backend.services.account_service import delete_user_account_data
from adventour_backend.services import local_index_service
from adventour_backend.services import place_event_service

from dotenv import load_dotenv
from urllib.parse import quote_plus
from datetime import date, datetime, timezone
from sqlalchemy import func, inspect, text
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

# Connection URLs can contain credentials; never print or expose them.

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
        "database_configured": bool(app.config["SQLALCHEMY_DATABASE_URI"]),
        "google_api_key_configured": bool(google_key),
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
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")

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

def serialize_adventour_stop(stop):
    metadata = parse_json_object(stop.metadata_json)
    display = metadata.get("display") or {}
    duration_seconds = None
    if stop.arrived_at:
        end_time = stop.departed_at or datetime.utcnow()
        duration_seconds = max(0, int((end_time - stop.arrived_at).total_seconds()))

    return {
        "id": stop.id,
        "session_id": stop.session_id,
        "place_id": stop.entity_id,
        "provider": metadata.get("provider"),
        "provider_place_id": metadata.get("provider_place_id"),
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
            "name": display.get("name"),
            "vicinity": display.get("vicinity"),
            "types": display.get("types") or [],
            "photo_url": display.get("photo_url"),
            "photo_attributions": display.get("photo_attributions") or [],
            "rating": display.get("rating"),
            "user_ratings_total": display.get("user_ratings_total"),
            "price_level": display.get("price_level"),
            # Coordinates come from the snapshot taken when the card was shown.
            # The index is rebuilt independently, so a stop must not depend on a
            # record still existing to render its own history.
            "latitude": display.get("latitude"),
            "longitude": display.get("longitude"),
        },
    }

def serialize_adventour_session(session, include_stops=True):
    stops = session.stops.all() if include_stops else []
    active_stops = [
        stop for stop in stops
        if stop.status in ("planned", "navigating", "arrived")
    ]
    active_stop = active_stops[-1] if active_stops else None
    return {
        "id": session.id,
        "title": session.title,
        "status": session.status,
        "started_at": isoformat_or_none(session.started_at),
        "ended_at": isoformat_or_none(session.ended_at),
        "companion_user_ids": parse_json_object(session.companion_user_ids_json, {"ids": []}).get("ids", []),
        "summary": parse_json_object(session.summary_json),
        "stops": [serialize_adventour_stop(stop) for stop in stops],
        "active_stop": serialize_adventour_stop(active_stop) if active_stop else None,
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

    try:
        stored = place_event_service.record(
            db=db,
            user_id=user.id,
            place_id=adventour_place_id or provider_place_id,
            event_type=event_type,
            event_value=data.get("event_value"),
            context=data.get("context", "solo"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        logger.exception("Event recording failed")
        return jsonify({"error": "Event recording failed"}), 500

    return jsonify({"message": "Event recorded", "event": stored}), 201

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

    entity_id = data.get("place_id")
    if not entity_id:
        return jsonify({"error": "place_id is required"}), 400

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
        entity_id=str(entity_id),
        record_id=str(data.get("provider_place_id")) if data.get("provider_place_id") else None,
        order_index=order_index,
        status="navigating",
        navigation_started_at=datetime.utcnow(),
        metadata_json=json.dumps(metadata),
    )
    db.session.add(stop)
    place_event_service.record(
        db=db, user_id=user.id, place_id=entity_id,
        event_type="navigate", context="adventour",
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
    place_event_service.record(
        db=db, user_id=user.id, place_id=stop.entity_id,
        event_type="arrival", context="adventour",
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
        place_event_service.record(
            db=db, user_id=user.id, place_id=stop.entity_id,
            event_type="rate", event_value=rating, context="adventour",
        )
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

    rows = db.session.execute(text("""
        SELECT e.id AS event_id, e.entity_id, e.event_type, e.occurred_at, e.score_snapshot,
               p.name, p.basic_category, p.taxonomy_bucket,
               COALESCE(p.canonical_lat, p.lat) AS lat, COALESCE(p.canonical_lon, p.lon) AS lon
        FROM place_event e
        LEFT JOIN places p ON p.id = e.record_id OR p.id = e.entity_id
        WHERE e.user_id = :uid AND e.event_type = :etype
        ORDER BY e.occurred_at DESC
        LIMIT :lim
    """), {"uid": user.id, "etype": event_type, "lim": limit}).mappings().all()

    places = []
    seen = set()
    for r in rows:
        if r["entity_id"] in seen:
            continue
        seen.add(r["entity_id"])
        places.append({
            "event_id": r["event_id"],
            "place_id": r["entity_id"],
            "provider": "adventour_index",
            "provider_place_id": r["entity_id"],
            "name": r["name"],
            "vicinity": None,
            "latitude": float(r["lat"]) if r["lat"] is not None else None,
            "longitude": float(r["lon"]) if r["lon"] is not None else None,
            "event_type": r["event_type"],
            "occurred_at": r["occurred_at"].isoformat() if r["occurred_at"] else None,
            "category": "food" if r["taxonomy_bucket"] == "food_and_drink" else "activity",
            "types": local_index_service._types_for(r["basic_category"], r["taxonomy_bucket"]),
            "rating": None,
            "user_ratings_total": None,
            "price_level": None,
            "photo_url": None,
            "photo_attributions": [],
            "score": float(r["score_snapshot"]) if r["score_snapshot"] is not None else None,
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

    indexed = None
    if adventour_place_id:
        indexed = db.session.execute(text("""
            SELECT COALESCE(canonical_id, id) AS entity_id, name, basic_category,
                   taxonomy_bucket, authenticity, authenticity_why,
                   COALESCE(canonical_lat, lat) AS lat, COALESCE(canonical_lon, lon) AS lon
            FROM places WHERE id = :pid OR canonical_id = :pid LIMIT 1
        """), {"pid": str(adventour_place_id)}).mappings().first()

    candidate = None
    if provider == "google" and provider_place_id:
        candidate = GoogleServicesAPI.fetch_place_details(provider_place_id)

    display = place_display_payload(candidate) if candidate else {}
    types = display.get("types") or (
        local_index_service._types_for(indexed["basic_category"], indexed["taxonomy_bucket"])
        if indexed else []
    )

    if not indexed and not display:
        return jsonify({"error": "Unknown place"}), 404

    return jsonify({
        "place_id": indexed["entity_id"] if indexed else None,
        "provider": provider or "adventour_index",
        "provider_place_id": provider_place_id,
        "name": display.get("name") or (indexed["name"] if indexed else None),
        "vicinity": display.get("vicinity"),
        "latitude": float(indexed["lat"]) if indexed and indexed["lat"] is not None else None,
        "longitude": float(indexed["lon"]) if indexed and indexed["lon"] is not None else None,
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
        # Candidate retrieval runs against our own index. No paid API call ever
        # populates a deck -- see docs/sourcing-cost-decision-brief.md.
        result = local_index_service.recommend(
            db=db,
            location={"latitude": float(latitude), "longitude": float(longitude)},
            radius_meters=int(data.get("radius_meters", 3200)),
            constraints=data.get("constraints", {}),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Recommendation request failed")
        return jsonify({"error": "Recommendation request failed", "detail": str(exc)}), 500

    return jsonify(result), 200

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))

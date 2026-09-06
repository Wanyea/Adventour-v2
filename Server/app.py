from flask import Flask, request, jsonify, g
from flask_cors import CORS
from adventour_backend.services.google_services_api import GoogleServicesAPI, deck_boundary
from adventour_backend.models import (
    db,
    User,
    PlaceRating,
    AdventourSession,
    AdventourStop,
)
from adventour_backend.auth import require_auth
from adventour_backend.social_routes import social_bp
from adventour_backend.routes.local_events import blueprint as local_events_bp
from adventour_backend.services.account_service import delete_user_account_data
from adventour_backend.services import tag_group_service, local_index_service
from adventour_backend.services import place_event_service
from adventour_backend.services import decision_service, index_schema_service, launch_service

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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
app.register_blueprint(local_events_bp)


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
    index_schema_service.ensure(db.engine)

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
        "decision_id": metadata.get("decision_id"),
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
@require_auth
def onboarding():
    data = request.json or {}
    tags = data.get('initial_tags', [])
    if not isinstance(tags, list) or not tags or any(not isinstance(t, str) or t not in tag_group_service.GROUPS for t in tags):
        return jsonify({"error": "Choose one or more travel mood tags"}), 400
    g.current_user.preferences = ",".join(dict.fromkeys(tags))
    db.session.commit()
    return jsonify({"message": "Onboarding preferences saved"}), 200

@app.route('/user/<user_id>', methods=['GET'])
@require_auth
def get_user_info(user_id):
    user = g.current_user
    if user_id not in (user.firebase_uid, str(user.id)):
        return jsonify({"error": "Profile does not belong to this user"}), 403
    
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
        if data.get("display_name"):
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
    data = request.json or {}
    user = g.current_user
    
    place_id = data.get('place_id')
    rating = data.get('rating')
    review = data.get('review', '')
    
    if not place_id or not rating:
        return jsonify({"error": "Place ID and rating are required"}), 400
    
    if type(rating) is not int or rating < 1 or rating > 5:
        return jsonify({"error": "Rating must be an integer between 1 and 5"}), 400
    if not isinstance(review, str) or len(review) > 4000:
        return jsonify({"error": "Review must be text of at most 4000 characters"}), 400
    try:
        event = place_event_service.record(db, user.id, place_id, "rate", event_value=rating,
                                           decision_id=data.get("decision_id"))
        place_id = event["entity_id"]
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    
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
            decision_id=data.get("decision_id"),
            test_activity=bool(getattr(g, "test_activity", False)),
        )
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception:
        db.session.rollback()
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
    session = AdventourSession.query.filter_by(id=session_id, user_id=user.id, status="active").with_for_update().first()
    if not session:
        return jsonify({"error": "Active Adventour not found"}), 404

    entity_id = data.get("place_id")
    if not entity_id:
        return jsonify({"error": "place_id is required"}), 400

    try:
        decision = decision_service.get(db, user.id, data.get("decision_id"), entity_id, lock=True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    for existing in session.stops.all():
        if json.loads(existing.metadata_json or "{}").get("decision_id") == decision["id"]:
            return jsonify({"adventour": serialize_adventour_session(session),
                            "stop": serialize_adventour_stop(existing), "message": "Stop already added"}), 200
    if decision["verdict"] == "reject":
        return jsonify({"error": "This card was already rejected"}), 409

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

    picked = decision["payload"]
    entity_id = decision["entity_id"]
    order_index = session.stops.count()
    display = {**picked["display"], "latitude": picked["latitude"], "longitude": picked["longitude"],
               "category": picked["category"], "approximate_location": picked["approximate_location"]}
    metadata = {
        "source": "recommendation_deck",
        "provider": "adventour_index",
        "provider_place_id": decision["record_id"],
        "decision_id": decision["id"],
        "display": display,
    }
    stop = AdventourStop(
        session_id=session.id,
        entity_id=str(entity_id),
        record_id=decision["record_id"],
        order_index=order_index,
        status="navigating",
        navigation_started_at=datetime.utcnow(),
        metadata_json=json.dumps(metadata),
    )
    db.session.add(stop)
    for event_type in ("accept", "save"):
        place_event_service.record(db=db, user_id=user.id, place_id=entity_id,
                                   event_type=event_type, context="adventour", decision_id=decision["id"])
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

    if stop.status not in ("navigating", "arrived"):
        return jsonify({"error": "Only a navigating stop can be marked arrived"}), 409
    stop.status = "arrived"
    stop.arrived_at = stop.arrived_at or datetime.utcnow()
    place_event_service.record(
        db=db, user_id=user.id, place_id=stop.entity_id,
        event_type="arrival", context="adventour",
        decision_id=decision_service.for_stop(db, user.id, stop),
    )
    db.session.commit()

    return jsonify({"adventour": serialize_adventour_session(session), "stop": serialize_adventour_stop(stop)}), 200

@app.route('/api/adventours/<int:session_id>/stops/<int:stop_id>/navigate', methods=['POST'])
@require_auth
def navigate_adventour_stop(session_id, stop_id):
    user = g.current_user
    session = AdventourSession.query.filter_by(id=session_id, user_id=user.id, status="active").first()
    stop = AdventourStop.query.filter_by(id=stop_id, session_id=session_id).first() if session else None
    if not stop or stop.status not in ("navigating", "arrived"):
        return jsonify({"error": "Active stop not found"}), 404
    place_event_service.record(db, user.id, stop.entity_id, "navigate", context="adventour",
                               decision_id=decision_service.for_stop(db, user.id, stop))
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

    if stop.status not in ("arrived", "completed"):
        return jsonify({"error": "Mark arrival before completing this stop"}), 409

    rating = data.get("rating")
    if rating is not None:
        if type(rating) is not int or rating < 1 or rating > 5:
            return jsonify({"error": "rating must be an integer between 1 and 5"}), 400

    now = datetime.utcnow()
    stop.status = "completed"
    stop.arrived_at = stop.arrived_at or now
    stop.departed_at = stop.departed_at or now
    stop.rating = rating
    if "notes" in data:
        stop.notes = str(data.get("notes") or "")[:4000]

    if rating:
        place_event_service.record(
            db=db, user_id=user.id, place_id=stop.entity_id,
            event_type="rate", event_value=rating, context="adventour",
            decision_id=decision_service.for_stop(db, user.id, stop),
        )
        review = PlaceRating.query.filter_by(user_id=user.id, place_id=stop.entity_id).first()
        if not review:
            review = PlaceRating(user_id=user.id, place_id=stop.entity_id, rating=rating)
            db.session.add(review)
        review.rating = rating
        review.review = stop.notes
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
               e.decision_id, e.components_snapshot, e.explanation_snapshot, d.payload,
               review.rating AS own_rating, review.review AS own_review,
               p.name, p.basic_category, p.taxonomy_bucket,
               COALESCE(p.canonical_lat, p.lat) AS lat, COALESCE(p.canonical_lon, p.lon) AS lon
        FROM place_event e
        LEFT JOIN LATERAL (SELECT * FROM places
            WHERE id=e.record_id OR id=e.entity_id ORDER BY (id=e.record_id) DESC LIMIT 1) p ON true
        LEFT JOIN recommendation_decision d ON d.id=e.decision_id
        LEFT JOIN place_rating review ON review.user_id=e.user_id AND review.place_id=e.entity_id
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
            "decision_id": r["decision_id"],
            "score_components": r["components_snapshot"],
            "ranking_components": (r["payload"] or {}).get("ranking_components"),
            "structural_score": (r["payload"] or {}).get("structural_score"),
            "model": (r["payload"] or {}).get("model"),
            "explanation": r["explanation_snapshot"],
            "own_rating": r["own_rating"], "own_review": r["own_review"],
            "place_id": r["entity_id"],
            "provider": "adventour_index",
            "provider_place_id": r["entity_id"],
            "name": (r["payload"] or {}).get("name") or r["name"] or "Saved place",
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
    place_id = request.args.get('place_id')
    try:
        verification = GoogleServicesAPI.verify_accepted(db, g.current_user.id, place_id)
        if verification.get("verification") == "suppressed":
            active_ids = [s.id for s in AdventourSession.query.filter_by(user_id=g.current_user.id, status="active")]
            for stop in AdventourStop.query.filter(AdventourStop.session_id.in_(active_ids),
                    AdventourStop.entity_id == place_id, AdventourStop.status == "navigating"):
                stop.status = "skipped"
                stop.departed_at = datetime.utcnow()
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    response = jsonify({'place_id': place_id, **verification})
    response.headers['Cache-Control'] = 'no-store'
    return response

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
        with deck_boundary():
            result = local_index_service.recommend(
                db=db,
                location={"latitude": float(latitude), "longitude": float(longitude)},
                radius_meters=int(data.get("radius_meters", 3200)),
                constraints=data.get("constraints", {}),
                user_id=user.id,
            )
        decision_service.attach(db, user.id, result["recommendations"], getattr(g, "test_activity", False))
        db.session.commit()
        logger.info("deck_served user=%s cards=%s provider_requests=0", user.id, len(result["recommendations"]))
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
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
@require_auth
def geocode():
    try:
        if request.args.get('address'):
            result = launch_service.resolve(request.args['address'])
        else:
            result = launch_service.coordinates(request.args.get('latitude'), request.args.get('longitude'))
        return jsonify(result)
    except (ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    except launch_service.SearchUnavailable as exc:
        return jsonify({'error': str(exc)}), 503

@app.route('/api/places/autocomplete', methods=['GET'])
@require_auth
def places_autocomplete():
    try:
        response = jsonify({'predictions': launch_service.suggestions(request.args.get('input', ''))})
        response.headers['Cache-Control'] = 'no-store'
        return response
    except launch_service.SearchUnavailable as exc:
        return jsonify({'error': str(exc)}), 503

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))

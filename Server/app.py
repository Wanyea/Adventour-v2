from flask import Flask, request, jsonify, g
from flask_cors import CORS
from google_services_api import GoogleServicesAPI  # Custom module
from models import db, User, UserTagFeedback, PlaceRating
from utils import is_chain, is_hidden_gem, review_sentiment_score
from auth import require_auth, optional_auth
from social_routes import social_bp

from dotenv import load_dotenv
from urllib.parse import quote_plus
from datetime import datetime
import os

load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = quote_plus(os.getenv("DB_PASSWORD"))
DB_NAME = os.getenv("DB_NAME")
CONNECTION_NAME = os.getenv("DB_CONNECTION_NAME")

if os.getenv("GAE_ENV", "").startswith("standard"):
    DB_HOST = "localhost"
    DATABASE_URI = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"
else:
    DB_HOST = "127.0.0.1"
    DATABASE_URI = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:3306/{DB_NAME}"

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
    
    db.session.commit()
    return jsonify({"message": "Place rated successfully!"}), 201

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

    logger.info("Received geocode request: %s, %s", latitude, longitude)

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
                return jsonify({"error": "Unable to resolve coordinates to a city and state"}), 404
            return jsonify(location)
        except Exception as e:
                logger.exception("Error resolving coordinates")
                return jsonify({"error": f"Error resolving coordinates: {str(e)}"}), 500
    else:
        return jsonify({"error": "Either address or coordinates must be provided"}), 400

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

    # Get user
    user = User.query.filter_by(uuid=user_id).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

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
    app.run(host="0.0.0.0", port=8080)
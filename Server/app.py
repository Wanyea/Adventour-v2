from flask import Flask, request, jsonify
from flask_cors import CORS
from google_services_api import GoogleServicesAPI  # Custom module
from models import db, Feedback, User

DATABASE_URI = "sqlite:///local_adventour.db"

# Debug: Verify the connection string
print(f"Connecting to database: {DATABASE_URI}")

# Flask app setup
app = Flask(__name__)
CORS(app)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

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

@app.route('/feedback', methods=['POST'])
def save_feedback():
    data = request.json
    user_uuid = data['user_id']

    user = User.query.filter_by(uuid=user_uuid).first()
    if not user:
        user = User(uuid=user_uuid)
        db.session.add(user)
        db.session.commit()

    feedback = Feedback(
        user_id=user.id,
        place_id=data['place_id'],
        feedback=data['feedback'],
        tags=",".join(data['tags']),
    )
    db.session.add(feedback)
    db.session.commit()
    return jsonify({"message": "Feedback saved successfully!"}), 201

@app.route('/geocode', methods=['GET'])
def geocode():
    address = request.args.get('address')
    latitude = request.args.get('latitude')
    longitude = request.args.get('longitude')

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
def get_recommendations():
    user_id = request.args.get('user_id')
    address = request.args.get('address')
    latitude = request.args.get('latitude')
    longitude = request.args.get('longitude')

    if not user_id:
        return jsonify({"error": "User ID is required"}), 400

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

    user = User.query.filter_by(uuid=user_id).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    feedback = Feedback.query.filter_by(user_id=user.id).all()

    rejected_place_ids = set()
    tag_scores = {}
    for fb in feedback:
        tags = fb.tags.split(',')
        weight = 3 if fb.feedback == 'accept' else -1
        for i, tag in enumerate(tags[:3]):
            tag_scores[tag] = tag_scores.get(tag, 0) + (3 - i) * weight
        if fb.feedback == 'reject':
            rejected_place_ids.add(fb.place_id)

    max_score = max(tag_scores.values(), default=1)
    tag_scores = {tag: score / max_score for tag, score in tag_scores.items()}

    try:
        places = GoogleServicesAPI.fetch_places(list(tag_scores.keys()), coordinates)
    except Exception as e:
        return jsonify({"error": f"Error fetching places: {str(e)}"}), 500

    scored_places = []
    for place in places:
        place_id = place.get('place_id')
        if place_id in rejected_place_ids:
            continue
        score = sum(tag_scores.get(tag, 0) for tag in place.get('types', []))
        if score > 0:
            scored_places.append({"place": place, "score": score})

    scored_places.sort(key=lambda x: x["score"], reverse=True)
    return jsonify([sp["place"] for sp in scored_places])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

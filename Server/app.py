from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from urllib.parse import quote_plus
from google_services_api import GoogleServicesAPI  # Custom module
from models import db, Feedback

# Cloud SQL configuration
DB_USER = "root"
DB_PASSWORD = "[(BYC0eJx3myR@|8"  
DB_NAME = "adventour"
CLOUD_SQL_CONNECTION_NAME = "adventour-73dfb:us-east1:adventour-sql"
DATABASE_URI = (
    f"mysql+pymysql://{DB_USER}:{quote_plus(DB_PASSWORD)}@34.74.250.90:3306/{DB_NAME}"
)

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


@app.route('/feedback', methods=['POST'])
def save_feedback():
    data = request.json
    feedback = Feedback(
        user_id=data['user_id'],
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
    data = request.json
    tags = data.get("tags", [])
    location = data.get("location")

    if not tags or not location:
        return jsonify({"error": "Tags and location are required"}), 400

    try:
        places = GoogleServicesAPI.fetch_places(tags, location)
        return jsonify(places)
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

    feedback = Feedback.query.filter_by(user_id=user_id).all()
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

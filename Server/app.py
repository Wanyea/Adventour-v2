import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from models import db, Feedback
from google_services_api import GoogleServicesAPI  

app = Flask(__name__)
CORS(app)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///feedback.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Initialize the database
with app.app_context():
    db.create_all()

@app.route('/feedback', methods=['POST'])
def save_feedback():
    """
    Save user feedback (accept/reject) with tags to the database.
    """
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
    """
    Handle geocoding for an address or reverse geocoding for coordinates.
    """
    address = request.args.get('address')  # Address for geocoding
    latitude = request.args.get('latitude')  # Latitude for reverse geocoding
    longitude = request.args.get('longitude')  # Longitude for reverse geocoding

    if address:
        # Geocode the address to coordinates
        try:
            coordinates = GoogleServicesAPI.fetch_city_coordinates(address)
            if not coordinates:
                return jsonify({"error": "Unable to resolve address to coordinates"}), 404
            return jsonify(coordinates)  # Return latitude and longitude
        except Exception as e:
            return jsonify({"error": f"Error resolving address: {str(e)}"}), 500
    elif latitude and longitude:
        # Reverse geocode the coordinates to a city and state
        try:
            location = GoogleServicesAPI.reverse_geocode(latitude, longitude)
            if not location:
                return jsonify({"error": "Unable to resolve coordinates to a city and state"}), 404
            return jsonify(location)  # Return city and state
        except Exception as e:
            return jsonify({"error": f"Error resolving coordinates: {str(e)}"}), 500
    else:
        return jsonify({"error": "Either address or coordinates must be provided"}), 400

@app.route('/fetch-places', methods=['POST'])
def fetch_places():
    """
    Fetch places from Google Places API based on tags and location.
    """
    data = request.json  # Extract the JSON payload
    print("Incoming data:", data)  # Debug log

    tags = data.get("tags", [])
    location = data.get("location")

    if not tags or not location:
        print("Missing parameters: tags or location")
        return jsonify({"error": "Tags and location are required"}), 400

    try:
        # Fetch places using GoogleServicesAPI
        places = GoogleServicesAPI.fetch_places(tags, location)
        return jsonify(places)
    except Exception as e:
        print(f"Error in fetch_places: {e}")
        return jsonify({"error": f"Error fetching places: {str(e)}"}), 500

@app.route('/recommendations', methods=['GET'])
def get_recommendations():
    """
    Generate recommendations based on user feedback with weighted tags,
    penalized rejected tags, and excluded rejected places.
    """
    user_id = request.args.get('user_id')
    address = request.args.get('address')
    latitude = request.args.get('latitude')
    longitude = request.args.get('longitude')

    if not user_id:
        return jsonify({"error": "User ID is required"}), 400

    # Determine coordinates
    if latitude and longitude:
        try:
            lat, lng = float(latitude), float(longitude)
        except ValueError:
            return jsonify({"error": "Invalid latitude or longitude format"}), 400
        coordinates = {"latitude": lat, "longitude": lng}
    elif address:
        try:
            coordinates = GoogleServicesAPI.fetch_city_coordinates(address)
            if not coordinates:
                return jsonify({"error": "Unable to resolve address to coordinates"}), 404
        except Exception as e:
            return jsonify({"error": f"Error resolving address: {str(e)}"}), 500
    else:
        return jsonify({"error": "Either coordinates or address must be provided"}), 400

    # Retrieve user feedback
    feedback = Feedback.query.filter_by(user_id=user_id).all()

    # Track rejected place IDs and calculate tag scores
    rejected_place_ids = set()
    tag_scores = {}
    for fb in feedback:
        tags = fb.tags.split(',')
        if fb.feedback == 'accept':
            weight = 3  # Positive weight for accepted places
        elif fb.feedback == 'reject':
            weight = -1  # Negative weight for rejected places
            rejected_place_ids.add(fb.place_id)  # Track rejected place IDs
        else:
            continue  # Skip unknown feedback types

        for i, tag in enumerate(tags[:3]):  # Consider top 3 tags
            score_adjustment = (3 - i) * weight  # Higher weight for first tag
            if tag in tag_scores:
                tag_scores[tag] += score_adjustment
            else:
                tag_scores[tag] = score_adjustment

    # Normalize tag scores (optional for consistency)
    max_score = max(tag_scores.values(), default=1)
    tag_scores = {tag: score / max_score for tag, score in tag_scores.items()}

    # Fetch places using Google Places API
    try:
        places = GoogleServicesAPI.fetch_places(list(tag_scores.keys()), coordinates)
    except Exception as e:
        return jsonify({"error": f"Error fetching places: {str(e)}"}), 500

    # Score and filter places
    scored_places = []
    for place in places:
        place_id = place.get('place_id')
        place_tags = place.get('types', [])
        rating = place.get('rating', 0)  # Default to 0 if no rating is available

        if place_id in rejected_place_ids or rating < 4.0:  # Exclude rejected places and low-rated places
            continue

        score = sum(tag_scores.get(tag, 0) for tag in place_tags)
        if score > 0:
            scored_places.append({"place": place, "score": score})

    # Sort places by score in descending order
    scored_places.sort(key=lambda x: x["score"], reverse=True)

    # Return the top recommendations
    return jsonify([sp["place"] for sp in scored_places])

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5005)


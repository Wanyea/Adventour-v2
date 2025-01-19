from flask import Flask, request, jsonify
from flask_cors import CORS
from models import db, Feedback
from google_places_services import GooglePlacesServices  

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
            coordinates = GooglePlacesServices.fetch_city_coordinates(address)
            if not coordinates:
                return jsonify({"error": "Unable to resolve address to coordinates"}), 404
            return jsonify(coordinates)  # Return latitude and longitude
        except Exception as e:
            return jsonify({"error": f"Error resolving address: {str(e)}"}), 500
    elif latitude and longitude:
        # Reverse geocode the coordinates to a city and state
        try:
            location = GooglePlacesServices.reverse_geocode(latitude, longitude)
            if not location:
                return jsonify({"error": "Unable to resolve coordinates to a city and state"}), 404
            return jsonify(location)  # Return city and state
        except Exception as e:
            return jsonify({"error": f"Error resolving coordinates: {str(e)}"}), 500
    else:
        return jsonify({"error": "Either address or coordinates must be provided"}), 400

@app.route('/recommendations', methods=['GET'])
def get_recommendations():
    """
    Generate recommendations based on user feedback.
    """
    user_id = request.args.get('user_id')
    address = request.args.get('address')
    latitude = request.args.get('latitude')
    longitude = request.args.get('longitude')

    if not user_id:
        return jsonify({"error": "User ID is required"}), 400

    if latitude and longitude:
        try:
            lat, lng = float(latitude), float(longitude)
        except ValueError:
            return jsonify({"error": "Invalid latitude or longitude format"}), 400
        coordinates = {"latitude": lat, "longitude": lng}
    elif address:
        try:
            coordinates = GooglePlacesServices.fetch_city_coordinates(address)
            if not coordinates:
                return jsonify({"error": "Unable to resolve address to coordinates"}), 404
        except Exception as e:
            return jsonify({"error": f"Error resolving address: {str(e)}"}), 500
    else:
        return jsonify({"error": "Either coordinates or address must be provided"}), 400

    feedback = Feedback.query.filter_by(user_id=user_id).all()
    accepted_tags = set()
    rejected_tags = set()
    for fb in feedback:
        tags = fb.tags.split(',')
        if fb.feedback == 'accept':
            accepted_tags.update(tags)
        elif fb.feedback == 'reject':
            rejected_tags.update(tags)

    filtered_tags = accepted_tags - rejected_tags

    try:
        places = GooglePlacesServices.fetch_places(list(filtered_tags), coordinates)
        return jsonify(places)
    except Exception as e:
        return jsonify({"error": f"Error fetching places: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(debug=True)

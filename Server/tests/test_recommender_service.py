import pytest
from flask import Flask

from adventour_backend.models import db, Place, User, UserPlaceEvent
from adventour_backend.services.recommender_service import RecommendationService


class MockProviderRegistry:
    def __init__(self, candidates):
        self.candidates = candidates

    def search(self, tags, location, radius_meters=3200, constraints=None):
        return self.candidates, []


@pytest.fixture()
def app_context():
    app = Flask(__name__)

    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def create_user(email, preferences):
    username = email.split("@")[0]
    user = User(
        firebase_uid=f"test-{username}",
        email=email,
        username=username,
        display_name=username,
        preferences=",".join(preferences),
    )
    db.session.add(user)
    db.session.commit()
    return user


def candidate(name, place_id, types, rating, ratings_total, lat=37.422, lng=-122.084, price_level=2):
    return {
        "provider": "mock",
        "place_id": place_id,
        "name": name,
        "types": types,
        "rating": rating,
        "user_ratings_total": ratings_total,
        "price_level": price_level,
        "geometry": {"location": {"lat": lat, "lng": lng}},
        "business_status": "OPERATIONAL",
    }


def recommend_for(user, candidates, member_ids=None, constraints=None):
    service = RecommendationService(MockProviderRegistry(candidates))
    return service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        radius_meters=3200,
        member_ids=member_ids or [],
        constraints=constraints or {"limit": 10, "avoid_chains": True},
    )


def test_hidden_gem_beats_chain_for_local_food_user(app_context):
    user = create_user("local@example.com", ["restaurant", "cafe"])
    candidates = [
        candidate("Starbucks", "chain-1", ["cafe", "restaurant"], 4.7, 5000),
        candidate("Maya's Corner Cafe", "gem-1", ["cafe", "restaurant"], 4.8, 42),
    ]

    result = recommend_for(user, candidates)

    assert result["recommendations"][0]["name"] == "Maya's Corner Cafe"
    assert result["recommendations"][0]["components"]["authenticity"] > result["recommendations"][1]["components"]["authenticity"]
    assert result["recommendations"][1]["components"]["chain_penalty"] > 0


def test_accept_event_increases_matching_category(app_context):
    user = create_user("food@example.com", ["restaurant"])
    candidates = [
        candidate("Local Taco Stand", "taco-1", ["restaurant", "mexican_restaurant"], 4.7, 55),
        candidate("Quiet Sculpture Garden", "garden-1", ["park", "tourist_attraction"], 4.8, 40),
    ]

    service = RecommendationService(MockProviderRegistry(candidates))
    first = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": True},
    )
    taco = next(item for item in first["recommendations"] if item["name"] == "Local Taco Stand")
    taco_place = db.session.get(Place, taco["place_id"])

    service.record_event(user=user, place=taco_place, event_type="accept")
    vector = service.build_preference_vector(user)

    assert vector["categories"]["restaurant"] > 0
    assert vector["categories"]["mexican_restaurant"] > 0


def test_group_scoring_penalizes_split_preferences(app_context):
    food_user = create_user("food@example.com", ["restaurant", "cafe"])
    art_user = create_user("art@example.com", ["museum", "art_gallery"])
    candidates = [
        candidate("Cafe Gallery", "balanced-1", ["cafe", "art_gallery"], 4.7, 75),
        candidate("Only Burgers", "food-only-1", ["restaurant"], 4.9, 80),
        candidate("Only Museum", "art-only-1", ["museum"], 4.9, 80),
    ]

    result = recommend_for(food_user, candidates, member_ids=[art_user.id])

    assert result["member_count"] == 2
    assert result["recommendations"][0]["name"] == "Cafe Gallery"
    assert result["recommendations"][0]["components"]["group_fit"] >= result["recommendations"][1]["components"]["group_fit"]


def test_impressions_are_logged_for_returned_recommendations(app_context):
    user = create_user("impressions@example.com", ["park"])
    candidates = [
        candidate("Neighborhood Park", "park-1", ["park"], 4.6, 20),
    ]

    result = recommend_for(user, candidates)

    assert len(result["recommendations"]) == 1
    events = UserPlaceEvent.query.filter_by(user_id=user.id, event_type="impression").all()
    assert len(events) == 1


def test_price_constraint_applies_penalty(app_context):
    user = create_user("budget@example.com", ["restaurant"])
    candidates = [
        candidate("Affordable Noodles", "cheap-1", ["restaurant"], 4.5, 60, price_level=1),
        candidate("Expensive Tasting Room", "expensive-1", ["restaurant"], 4.8, 50, price_level=4),
    ]

    result = recommend_for(user, candidates, constraints={"limit": 10, "avoid_chains": True, "price_max": 2})
    expensive = next(item for item in result["recommendations"] if item["name"] == "Expensive Tasting Room")

    assert expensive["components"]["price_penalty"] > 0

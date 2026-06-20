import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from flask import Flask

from adventour_backend.models import User, db
from adventour_backend.providers.place_providers import GooglePlacesProvider, ProviderRegistry
from adventour_backend.services.google_services_api import GoogleServicesAPI
from adventour_backend.services.recommender_service import RecommendationService


SERVER_DIR = Path(__file__).resolve().parents[1]


def _load_local_env():
    env_file = os.getenv("ENV_FILE")
    if env_file:
        load_dotenv(env_file, override=True)
        return
    load_dotenv(SERVER_DIR / ".env.local", override=True)


_load_local_env()


def _real_place_tests_enabled():
    return (
        os.getenv("ADVENTOUR_RUN_REAL_PLACE_TESTS", "").lower() == "true"
        and bool(os.getenv("GOOGLE_API_KEY"))
    )


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _real_place_tests_enabled(),
        reason="Set ADVENTOUR_RUN_REAL_PLACE_TESTS=true and GOOGLE_API_KEY to call Places API (New).",
    ),
]


@pytest.fixture()
def app_context():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def create_user():
    user = User(
        firebase_uid="real-place-test-user",
        email="real-place-test@adventour.local",
        username="real_place_test",
        display_name="Real Place Test",
        preferences="cafe,restaurant,park",
    )
    db.session.add(user)
    db.session.commit()
    return user


def test_google_autocomplete_can_return_real_predictions():
    predictions = GoogleServicesAPI.fetch_autocomplete(
        "coffee",
        latitude=37.421998333333335,
        longitude=-122.084,
        radius_meters=1200,
    )

    assert isinstance(predictions, list)
    assert predictions, "Google returned no autocomplete predictions near the emulator's default location."


def test_recommender_can_rank_real_google_places(app_context):
    user = create_user()
    service = RecommendationService(
        ProviderRegistry(providers=[GooglePlacesProvider()])
    )

    result = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        radius_meters=1200,
        constraints={"limit": 5, "avoid_chains": True},
    )

    assert result["provider_errors"] == []
    assert result["recommendations"], "Google returned no recommendation candidates."
    assert all(item["provider"] == "google" for item in result["recommendations"])

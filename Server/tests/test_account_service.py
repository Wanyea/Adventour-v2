from datetime import datetime

from flask import Flask

from adventour_backend.models import (
    db,
    AdventourSession,
    AdventourStop,
    Friendship,
    LocalEvent,
    LocalEventInterest,
    Place,
    PlaceProviderRef,
    PlaceRating,
    Trip,
    TripMember,
    TripPlace,
    TravelReservation,
    User,
    UserPlaceEvent,
    UserPlaceInteraction,
    UserPreferenceVector,
    UserTagFeedback,
)
from adventour_backend.services.account_service import delete_user_account_data


def create_test_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app


def test_delete_user_account_data_removes_private_rows_but_keeps_place_cache():
    app = create_test_app()

    with app.app_context():
        db.create_all()
        user = User(firebase_uid="reset-user", email="reset@example.com", username="reset")
        friend = User(firebase_uid="friend-user", email="friend@example.com", username="friend")
        place = Place(canonical_name="Local Cafe", normalized_name="local cafe")
        db.session.add_all([user, friend, place])
        db.session.flush()

        provider_ref = PlaceProviderRef(
            place_id=place.id,
            provider="google",
            provider_place_id="places/local-cafe",
        )
        db.session.add(provider_ref)
        db.session.flush()

        event = LocalEvent(
            title="Reset Event",
            starts_at=datetime.utcnow(),
            latitude=28.0,
            longitude=-81.0,
        )
        db.session.add(event)
        db.session.flush()

        trip = Trip(name="Reset Trip", created_by=user.id)
        db.session.add(trip)
        db.session.flush()

        session = AdventourSession(user_id=user.id, title="Reset Adventour")
        db.session.add(session)
        db.session.flush()

        db.session.add_all([
            Friendship(user_id=user.id, friend_id=friend.id, status="accepted"),
            Friendship(user_id=friend.id, friend_id=user.id, status="pending"),
            TripMember(trip_id=trip.id, user_id=user.id, role="owner"),
            TripMember(trip_id=trip.id, user_id=friend.id, role="member"),
            TripPlace(trip_id=trip.id, place_id="legacy-place", added_by=user.id),
            PlaceRating(user_id=user.id, place_id="legacy-place", rating=5),
            UserTagFeedback(user_id=user.id, place_id="legacy-place", verdict="accept"),
            UserPlaceInteraction(user_id=user.id, place_id="legacy-place", interaction_type="accept"),
            UserPlaceEvent(user_id=user.id, place_id=place.id, provider_ref_id=provider_ref.id, event_type="accept"),
            UserPreferenceVector(user_id=user.id, vector_json="{}"),
            AdventourStop(session_id=session.id, place_id=place.id, provider_ref_id=provider_ref.id, order_index=0),
            TravelReservation(user_id=user.id, adventour_session_id=session.id, reservation_type="stay", title="Reset Hotel"),
            LocalEventInterest(event_id=event.id, user_id=user.id, status="going"),
        ])
        db.session.commit()

        deleted = delete_user_account_data(user)
        db.session.commit()

        assert deleted["users"] == 1
        assert User.query.filter_by(firebase_uid="reset-user").first() is None
        assert User.query.filter_by(firebase_uid="friend-user").first() is not None
        assert Friendship.query.count() == 0
        assert Trip.query.count() == 0
        assert TripMember.query.count() == 0
        assert TripPlace.query.count() == 0
        assert PlaceRating.query.count() == 0
        assert UserTagFeedback.query.count() == 0
        assert UserPlaceInteraction.query.count() == 0
        assert UserPlaceEvent.query.count() == 0
        assert UserPreferenceVector.query.count() == 0
        assert TravelReservation.query.count() == 0
        assert LocalEventInterest.query.count() == 0
        assert LocalEvent.query.count() == 1
        assert AdventourSession.query.count() == 0
        assert AdventourStop.query.count() == 0
        assert Place.query.count() == 1
        assert PlaceProviderRef.query.count() == 1

        db.session.remove()
        db.drop_all()

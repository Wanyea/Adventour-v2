import os

from flask import Flask

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from adventour_backend.models import AdventourSession, AdventourStop, Place, User, db
from app import serialize_adventour_session


def create_test_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app


def test_active_stop_can_be_earlier_than_latest_completed_stop():
    app = create_test_app()

    with app.app_context():
        db.create_all()
        user = User(firebase_uid="adventour-serialize-user", email="serialize@example.com", username="serialize")
        first_place = Place(canonical_name="First Place", normalized_name="first place")
        second_place = Place(canonical_name="Second Place", normalized_name="second place")
        db.session.add_all([user, first_place, second_place])
        db.session.flush()

        session = AdventourSession(user_id=user.id, title="Serialization Adventour")
        db.session.add(session)
        db.session.flush()

        active_stop = AdventourStop(
            session_id=session.id,
            place_id=first_place.id,
            order_index=0,
            status="navigating",
        )
        completed_stop = AdventourStop(
            session_id=session.id,
            place_id=second_place.id,
            order_index=1,
            status="completed",
        )
        db.session.add_all([active_stop, completed_stop])
        db.session.commit()

        payload = serialize_adventour_session(session)

        assert payload["active_stop"]["id"] == active_stop.id
        assert payload["active_stop"]["status"] == "navigating"

        db.session.remove()
        db.drop_all()

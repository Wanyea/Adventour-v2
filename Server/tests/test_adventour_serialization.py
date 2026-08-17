import os
import json

from flask import Flask

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from adventour_backend.models import AdventourSession, AdventourStop, Place, TravelReservation, User, db
from app import apply_reservation_payload, booking_summary_from_reservations, serialize_adventour_session, serialize_travel_reservation


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


def test_planned_route_surfaces_first_unfinished_stop():
    app = create_test_app()

    with app.app_context():
        db.create_all()
        user = User(firebase_uid="planned-route-user", email="planned@example.com", username="planned")
        first_place = Place(canonical_name="Morning Coffee", normalized_name="morning coffee")
        second_place = Place(canonical_name="Lunch Market", normalized_name="lunch market")
        db.session.add_all([user, first_place, second_place])
        db.session.flush()

        session = AdventourSession(user_id=user.id, title="Planned Route")
        db.session.add(session)
        db.session.flush()

        first_stop = AdventourStop(
            session_id=session.id,
            place_id=first_place.id,
            order_index=0,
            status="planned",
        )
        second_stop = AdventourStop(
            session_id=session.id,
            place_id=second_place.id,
            order_index=1,
            status="planned",
        )
        db.session.add_all([first_stop, second_stop])
        db.session.add(TravelReservation(
            user_id=user.id,
            adventour_session_id=session.id,
            reservation_type="stay",
            title="Downtown Hotel",
            provider="Manual",
            confirmation_code="STAY123",
        ))
        db.session.commit()

        payload = serialize_adventour_session(session)

        assert payload["active_stop"]["id"] == first_stop.id
        assert payload["active_stop"]["display"]["name"] == "Morning Coffee"
        assert payload["reservations"][0]["title"] == "Downtown Hotel"
        assert payload["reservations"][0]["confirmation_code"] == "STAY123"

        db.session.remove()
        db.drop_all()


def test_travel_reservation_payload_can_be_serialized_and_updated():
    app = create_test_app()

    with app.app_context():
        db.create_all()
        user = User(firebase_uid="reservation-user", email="reservation@example.com", username="reservation")
        db.session.add(user)
        db.session.flush()

        reservation = TravelReservation(
            user_id=user.id,
            reservation_type="flight",
            title="Flight to Austin",
            provider="Manual",
            confirmation_code="ABC123",
        )
        db.session.add(reservation)
        db.session.commit()

        apply_reservation_payload(reservation, {
            "reservation_type": "stay",
            "title": "Hotel stay",
            "cost_total": "240.50",
            "metadata": {"source": "test"},
        })
        db.session.commit()

        payload = serialize_travel_reservation(reservation)

        assert payload["reservation_type"] == "stay"
        assert payload["title"] == "Hotel stay"
        assert payload["cost_total"] == 240.5
        assert payload["metadata"] == {"source": "test"}

        db.session.remove()
        db.drop_all()


def test_adventour_session_includes_booking_cost_summary_per_person():
    app = create_test_app()

    with app.app_context():
        db.create_all()
        user = User(firebase_uid="booking-summary-user", email="booking-summary@example.com", username="bookings")
        db.session.add(user)
        db.session.flush()

        session = AdventourSession(
            user_id=user.id,
            title="Booked Austin Adventour",
            companion_user_ids_json=json.dumps({"ids": [101, 202]}),
            summary_json=json.dumps({"price_breakdown": {"party_size": 3}}),
        )
        db.session.add(session)
        db.session.flush()

        db.session.add_all([
            TravelReservation(
                user_id=user.id,
                adventour_session_id=session.id,
                reservation_type="stay",
                title="Downtown Hotel",
                provider="Manual",
                confirmation_code="HOTEL123",
                booking_url="https://example.com/hotel",
                cost_total=600,
                currency="USD",
            ),
            TravelReservation(
                user_id=user.id,
                adventour_session_id=session.id,
                reservation_type="event",
                title="Night Market Tickets",
                confirmation_code="MARKET9",
                cost_total=90,
                currency="USD",
            ),
            TravelReservation(
                user_id=user.id,
                adventour_session_id=session.id,
                reservation_type="local_transport",
                title="Transit card",
                currency="USD",
            ),
        ])
        db.session.commit()

        payload = serialize_adventour_session(session)
        summary = payload["booking_summary"]

        assert summary["status"] == "partial"
        assert summary["party_size"] == 3
        assert summary["reservation_count"] == 3
        assert summary["confirmation_count"] == 2
        assert summary["booking_link_count"] == 1
        assert summary["total_known_cost"] == 690
        assert summary["known_cost_per_person"] == 230
        assert summary["type_counts"] == {"stay": 1, "event": 1, "local_transport": 1}
        assert summary["type_costs"] == {"stay": 600, "event": 90}

        db.session.remove()
        db.drop_all()


def test_booking_summary_handles_empty_and_mixed_currency_reservations():
    class Reservation:
        def __init__(self, reservation_type, cost_total=None, currency="USD", confirmation_code=None, booking_url=None):
            self.reservation_type = reservation_type
            self.cost_total = cost_total
            self.currency = currency
            self.confirmation_code = confirmation_code
            self.booking_url = booking_url

    assert booking_summary_from_reservations([], party_size=0)["status"] == "empty"

    summary = booking_summary_from_reservations([
        Reservation("flight", 120, "USD", confirmation_code="FLY"),
        Reservation("stay", 200, "EUR", booking_url="https://example.com/stay"),
    ], party_size=2)

    assert summary["currency"] == "mixed"
    assert summary["total_known_cost"] == 320
    assert summary["known_cost_per_person"] == 160
    assert summary["status"] == "partial"

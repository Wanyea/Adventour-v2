from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


# Go-forward schema only.
#
# The Phase-1 recommendation tables (Place, PlaceProviderRef, PlaceFeature,
# UserPlaceEvent, UserPreferenceVector) were removed on 2026-08-18. They modelled
# an integer-keyed place identity that this architecture no longer has: places
# now live in the Postgres index built by Server/data_pipeline/, keyed by Overture
# entity id, and interactions live in `place_event` (see create_events_table.py).
#
# Also removed: UserTagFeedback and UserPlaceInteraction -- v1-era feedback
# tables superseded by place_event.
#
# KEPT, despite looking v1-era: Trip / TripMember / TripPlace / PlaceRating.
# These are not dead. social_routes.py uses them for the Friends & Trips screen,
# which is live in the app. Note their `place_id` is a free-text provider id, not
# a foreign key into the removed Place table, so they carry no legacy coupling.


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(128), unique=True, nullable=True)  # legacy v1/v2 client id
    firebase_uid = db.Column(db.String(128), unique=True, nullable=True)
    email = db.Column(db.String(255), unique=True, nullable=True)
    username = db.Column(db.String(100), unique=True, nullable=True)
    display_name = db.Column(db.String(100))
    date_of_birth = db.Column(db.Date)
    profile_picture = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    preferences = db.Column(db.String(500))  # fallback from onboarding
    is_active = db.Column(db.Boolean, default=True)

    friends = db.relationship('Friendship', foreign_keys='Friendship.user_id', backref='user', lazy='dynamic')
    friend_of = db.relationship('Friendship', foreign_keys='Friendship.friend_id', backref='friend', lazy='dynamic')
    trips = db.relationship('TripMember', backref='user', lazy='dynamic')
    place_ratings = db.relationship('PlaceRating', backref='user', lazy='dynamic')


class Friendship(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    friend_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # 'pending', 'accepted', 'blocked'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'friend_id', name='unique_friendship'),)


class Trip(db.Model):
    """Planned group trip. Backs the Friends & Trips screen via social_routes."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    destination = db.Column(db.String(255))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    members = db.relationship('TripMember', backref='trip', lazy='dynamic')
    places = db.relationship('TripPlace', backref='trip', lazy='dynamic')


class TripMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    role = db.Column(db.String(20), default='member')  # 'owner', 'admin', 'member'
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('trip_id', 'user_id', name='unique_trip_member'),)


class TripPlace(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), nullable=False)
    place_id = db.Column(db.String(50), nullable=False)  # free-text provider id, not a FK
    place_name = db.Column(db.String(255))
    place_address = db.Column(db.String(500))
    place_types = db.Column(db.String(500))
    added_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    day_number = db.Column(db.Integer)
    order_in_day = db.Column(db.Integer)
    status = db.Column(db.String(20), default='suggested')


class PlaceRating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    place_id = db.Column(db.String(50), nullable=False)  # free-text provider id, not a FK
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stars
    review = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'place_id', name='unique_user_place_rating'),)


class AdventourSession(db.Model):
    """A spontaneous trip-by-trip Adventour that can be resumed, completed, and shared."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(30), default='active', index=True)  # active, completed, abandoned
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime)
    companion_user_ids_json = db.Column(db.Text)
    summary_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('adventour_sessions', lazy='dynamic'))
    stops = db.relationship(
        'AdventourStop',
        backref='session',
        lazy='dynamic',
        order_by='AdventourStop.order_index',
        cascade='all, delete-orphan',
    )


class AdventourStop(db.Model):
    """One place visited or skipped during an Adventour session.

    `entity_id` is the resolved id from the Postgres place index -- the same key
    `place_event.entity_id` uses, so a stop and its swipe history join directly.
    It is deliberately *not* a foreign key: the index is rebuilt independently of
    the app, and a stop must survive a re-ingest that changes record ids.

    Display fields for the card live in `metadata_json`, captured at selection
    time. That is required rather than convenient -- provider display content may
    not be stored, so what is kept here is the snapshot the user actually saw.
    """
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('adventour_session.id'), nullable=False, index=True)
    entity_id = db.Column(db.String(128), nullable=False, index=True)
    record_id = db.Column(db.String(128))
    order_index = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), default='planned')  # planned, navigating, arrived, completed, skipped
    selected_at = db.Column(db.DateTime, default=datetime.utcnow)
    navigation_started_at = db.Column(db.DateTime)
    arrived_at = db.Column(db.DateTime)
    departed_at = db.Column(db.DateTime)
    rating = db.Column(db.Integer)
    notes = db.Column(db.Text)
    metadata_json = db.Column(db.Text)

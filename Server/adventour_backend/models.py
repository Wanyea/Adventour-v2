from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


# Phase 1 keeps classic app/social tables and the new recommendation tables in
# one module. Split by domain once migrations and route blueprints are in place.
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(128), unique=True, nullable=True)  # legacy v1/v2 client id
    firebase_uid = db.Column(db.String(128), unique=True, nullable=True)
    email = db.Column(db.String(255), unique=True, nullable=True)
    username = db.Column(db.String(100), unique=True, nullable=True)
    display_name = db.Column(db.String(100))
    profile_picture = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    preferences = db.Column(db.String(500))  # fallback from onboarding
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
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
    
    # Relationships
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
    place_id = db.Column(db.String(50), nullable=False)
    place_name = db.Column(db.String(255))
    place_address = db.Column(db.String(500))
    place_types = db.Column(db.String(500))  # comma-separated types
    added_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    day_number = db.Column(db.Integer)  # which day of the trip
    order_in_day = db.Column(db.Integer)  # order within the day
    status = db.Column(db.String(20), default='suggested')  # 'suggested', 'confirmed', 'rejected'

class PlaceRating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    place_id = db.Column(db.String(50), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stars
    review = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'place_id', name='unique_user_place_rating'),)

class UserTagFeedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    place_id = db.Column(db.String(50), nullable=False)
    verdict = db.Column(db.String(10), nullable=False)  # 'accept' or 'reject'
    place_tags = db.Column(db.String(500))  # comma-separated Google types
    rating = db.Column(db.Integer)  # 1-5, nullable
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UserPlaceInteraction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    place_id = db.Column(db.String(50), nullable=False)
    interaction_type = db.Column(db.String(20), nullable=False)  # 'view', 'accept', 'reject', 'rate'
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    rating = db.Column(db.Integer)  # nullable, only for 'rate'

class Place(db.Model):
    """Adventour-owned place identity, separate from third-party display data."""
    id = db.Column(db.Integer, primary_key=True)
    canonical_name = db.Column(db.String(255), nullable=False)
    normalized_name = db.Column(db.String(255), index=True)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    geohash = db.Column(db.String(32), index=True)
    source_confidence = db.Column(db.Float, default=0.5)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class PlaceProviderRef(db.Model):
    """Provider ids and attribution metadata. Store provider content only when allowed."""
    id = db.Column(db.Integer, primary_key=True)
    place_id = db.Column(db.Integer, db.ForeignKey('place.id'), nullable=False)
    provider = db.Column(db.String(50), nullable=False)
    provider_place_id = db.Column(db.String(255), nullable=False)
    attribution_required = db.Column(db.Boolean, default=True)
    last_verified_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    place = db.relationship('Place', backref=db.backref('provider_refs', lazy='dynamic'))
    __table_args__ = (
        db.UniqueConstraint('provider', 'provider_place_id', name='unique_provider_place'),
    )

class PlaceFeature(db.Model):
    """Adventour-owned/derived ranking features."""
    id = db.Column(db.Integer, primary_key=True)
    place_id = db.Column(db.Integer, db.ForeignKey('place.id'), nullable=False, unique=True)
    category_vector = db.Column(db.Text)  # JSON object: {"restaurant": 1.0}
    cuisine_vector = db.Column(db.Text)
    activity_vector = db.Column(db.Text)
    price_band = db.Column(db.Integer)
    chain_probability = db.Column(db.Float, default=0.0)
    authenticity_score = db.Column(db.Float, default=0.5)
    hidden_gem_score = db.Column(db.Float, default=0.0)
    tourist_trap_score = db.Column(db.Float, default=0.0)
    quality_score_adventour = db.Column(db.Float, default=0.5)
    popularity_score_adventour = db.Column(db.Float, default=0.0)
    feature_version = db.Column(db.String(50), default='phase1')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    place = db.relationship('Place', backref=db.backref('features', uselist=False))

class UserPlaceEvent(db.Model):
    """Normalized user event stream for recommendations and future model training."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    place_id = db.Column(db.Integer, db.ForeignKey('place.id'), nullable=False)
    provider_ref_id = db.Column(db.Integer, db.ForeignKey('place_provider_ref.id'))
    event_type = db.Column(db.String(30), nullable=False)  # impression, accept, reject, rate, navigate
    event_value = db.Column(db.Float)
    context = db.Column(db.String(30), default='solo')  # solo, group, trip
    metadata_json = db.Column(db.Text)
    occurred_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship('User', backref=db.backref('place_events', lazy='dynamic'))
    place = db.relationship('Place', backref=db.backref('user_events', lazy='dynamic'))
    provider_ref = db.relationship('PlaceProviderRef')

class UserPreferenceVector(db.Model):
    """Materialized user taste vector rebuilt from onboarding and interaction events."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    vector_type = db.Column(db.String(50), default='phase1')
    vector_json = db.Column(db.Text, nullable=False)
    version = db.Column(db.String(50), default='phase1')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('preference_vectors', lazy='dynamic'))
    __table_args__ = (
        db.UniqueConstraint('user_id', 'vector_type', name='unique_user_vector_type'),
    )

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
    """One place visited or skipped during an Adventour session."""
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('adventour_session.id'), nullable=False, index=True)
    place_id = db.Column(db.Integer, db.ForeignKey('place.id'), nullable=False)
    provider_ref_id = db.Column(db.Integer, db.ForeignKey('place_provider_ref.id'))
    order_index = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), default='planned')  # planned, navigating, arrived, completed, skipped
    selected_at = db.Column(db.DateTime, default=datetime.utcnow)
    navigation_started_at = db.Column(db.DateTime)
    arrived_at = db.Column(db.DateTime)
    departed_at = db.Column(db.DateTime)
    rating = db.Column(db.Integer)
    notes = db.Column(db.Text)
    metadata_json = db.Column(db.Text)

    place = db.relationship('Place')
    provider_ref = db.relationship('PlaceProviderRef')

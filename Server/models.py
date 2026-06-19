from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    firebase_uid = db.Column(db.String(128), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    username = db.Column(db.String(100), unique=True, nullable=False)
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

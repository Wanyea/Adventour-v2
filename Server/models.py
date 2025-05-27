from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    preferences = db.Column(db.String(500))  # fallback from onboarding

class UserTagFeedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    place_id = db.Column(db.String(50), nullable=False)
    verdict = db.Column(db.String(10), nullable=False)  # 'accept' or 'reject'
    place_tags = db.Column(db.String(500))  # comma-separated Google types

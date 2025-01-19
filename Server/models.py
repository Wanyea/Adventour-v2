from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), nullable=False)  # For identifying the user
    place_id = db.Column(db.String(50), nullable=False)
    feedback = db.Column(db.String(10), nullable=False)  # 'accept' or 'reject'
    tags = db.Column(db.String(500))  # Store tags as a comma-separated string

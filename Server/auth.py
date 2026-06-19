import firebase_admin
from firebase_admin import credentials, auth
from functools import wraps
from flask import request, jsonify, g
from models import db, User
import os

# Initialize Firebase Admin SDK
# In production, you'll need to set up Firebase service account
# For now, we'll use a placeholder - you'll need to configure this
try:
    # Check if already initialized
    firebase_admin.get_app()
except ValueError:
    # Initialize with service account key (you'll need to set this up)
    # For development, you can use a service account JSON file
    if os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH'):
        cred = credentials.Certificate(os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH'))
        firebase_admin.initialize_app(cred)
    else:
        # For now, we'll use a placeholder - you'll need to configure Firebase
        print("Warning: Firebase not configured. Please set up Firebase service account.")
        firebase_admin.initialize_app()

def verify_firebase_token(token):
    """Verify Firebase ID token and return user info"""
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        print(f"Token verification failed: {e}")
        return None

def get_or_create_user(firebase_uid, email, display_name=None):
    """Get existing user or create new one from Firebase data"""
    user = User.query.filter_by(firebase_uid=firebase_uid).first()
    
    if not user:
        # Create new user
        username = email.split('@')[0]  # Use email prefix as username
        # Ensure username is unique
        base_username = username
        counter = 1
        while User.query.filter_by(username=username).first():
            username = f"{base_username}{counter}"
            counter += 1
            
        user = User(
            firebase_uid=firebase_uid,
            email=email,
            username=username,
            display_name=display_name or username
        )
        db.session.add(user)
        db.session.commit()
    
    return user

def require_auth(f):
    """Decorator to require authentication for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "No valid authorization header"}), 401
        
        token = auth_header.split('Bearer ')[1]
        decoded_token = verify_firebase_token(token)
        
        if not decoded_token:
            return jsonify({"error": "Invalid token"}), 401
        
        # Get or create user
        user = get_or_create_user(
            decoded_token['uid'],
            decoded_token['email'],
            decoded_token.get('name')
        )
        
        # Store user in Flask's g object for use in route
        g.current_user = user
        
        return f(*args, **kwargs)
    
    return decorated_function

def optional_auth(f):
    """Decorator for routes that can work with or without authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split('Bearer ')[1]
            decoded_token = verify_firebase_token(token)
            
            if decoded_token:
                user = get_or_create_user(
                    decoded_token['uid'],
                    decoded_token['email'],
                    decoded_token.get('name')
                )
                g.current_user = user
        
        return f(*args, **kwargs)
    
    return decorated_function

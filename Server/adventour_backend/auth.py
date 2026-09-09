from functools import wraps
from flask import request, jsonify, g
from adventour_backend.models import db, User
import os
import time

import jwt
import requests
from dotenv import load_dotenv
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

env_file = os.getenv("ENV_FILE")
if env_file:
    load_dotenv(env_file, override=True)
else:
    load_dotenv()

try:
    import firebase_admin
    from firebase_admin import credentials, auth
except ImportError:
    firebase_admin = None
    credentials = None
    auth = None

# Initialize Firebase Admin SDK
# In production, you'll need to set up Firebase service account
# For now, we'll use a placeholder - you'll need to configure this
if firebase_admin:
    try:
        # Check if already initialized
        firebase_admin.get_app()
    except ValueError:
        project_id = (
            os.getenv("FIREBASE_PROJECT_ID")
            or os.getenv("GOOGLE_CLOUD_PROJECT")
            or os.getenv("GCLOUD_PROJECT")
        )
        firebase_options = {"projectId": project_id} if project_id else None
        # Initialize with service account key (you'll need to set this up)
        # For development, you can use a service account JSON file
        if os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH'):
            cred = credentials.Certificate(os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH'))
            firebase_admin.initialize_app(cred, firebase_options)
        else:
            print("Firebase service account not configured. Using Firebase public token verification.")
            auth = None
else:
    print("Warning: firebase-admin is not installed. Only ADVENTOUR_DEV_AUTH=true tokens will work.")

FIREBASE_CERTS_URL = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
# Firebase recommends a small tolerance for clock differences between clients and servers.
FIREBASE_CLOCK_SKEW_SECONDS = 60
_firebase_public_certs = None
_firebase_public_certs_expires_at = 0


def _firebase_project_id():
    return (
        os.getenv("FIREBASE_PROJECT_ID")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GCLOUD_PROJECT")
    )


def _fetch_firebase_public_certs():
    global _firebase_public_certs, _firebase_public_certs_expires_at

    now = time.time()
    if _firebase_public_certs and now < _firebase_public_certs_expires_at:
        return _firebase_public_certs

    response = requests.get(FIREBASE_CERTS_URL, timeout=5)
    response.raise_for_status()

    cache_control = response.headers.get("cache-control", "")
    max_age = 3600
    for directive in cache_control.split(","):
        directive = directive.strip()
        if directive.startswith("max-age="):
            try:
                max_age = int(directive.split("=", 1)[1])
            except ValueError:
                max_age = 3600

    _firebase_public_certs = response.json()
    _firebase_public_certs_expires_at = now + max_age
    return _firebase_public_certs


def _public_key_from_x509_cert(cert):
    certificate = x509.load_pem_x509_certificate(cert.encode("utf-8"))
    return certificate.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _verify_firebase_token_with_public_certs(token):
    project_id = _firebase_project_id()
    if not project_id:
        print("Token verification failed: FIREBASE_PROJECT_ID is not configured.")
        return None

    try:
        header = jwt.get_unverified_header(token)
        key_id = header.get("kid")
        cert = _fetch_firebase_public_certs().get(key_id)
        if not cert:
            print(f"Token verification failed: no Firebase public cert for key id {key_id}.")
            return None

        public_key = _public_key_from_x509_cert(cert)
        decoded = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=project_id,
            issuer=f"https://securetoken.google.com/{project_id}",
            leeway=FIREBASE_CLOCK_SKEW_SECONDS,
        )
        decoded["uid"] = decoded.get("uid") or decoded.get("user_id") or decoded.get("sub")

        return decoded
    except Exception as e:
        print(f"Token verification failed via Firebase public certs: {e}")
        return None


def verify_firebase_token(token):
    """Verify Firebase ID token and return user info"""
    if os.getenv('ADVENTOUR_DEV_AUTH') == 'true' and token.startswith('dev:'):
        email = token.replace('dev:', '', 1) or 'dev@adventour.local'
        username = email.split('@')[0]
        return {
            'uid': f'dev-{username}',
            'email': email,
            'name': username,
        }

    if not auth:
        return _verify_firebase_token_with_public_certs(token)

    try:
        return auth.verify_id_token(token, clock_skew_seconds=FIREBASE_CLOCK_SKEW_SECONDS)
    except Exception as e:
        print(f"Token verification failed via Firebase Admin SDK: {e}")
        return _verify_firebase_token_with_public_certs(token)

def _unique_username_from_email(email):
    username = (email or "user").split('@')[0]
    base_username = username
    counter = 1
    while User.query.filter_by(username=username).first():
        username = f"{base_username}{counter}"
        counter += 1
    return username


def get_or_create_user(firebase_uid, email, display_name=None):
    """Get existing user or create new one from Firebase data"""
    normalized_email = (email or f"{firebase_uid}@firebase.local").strip().lower()
    user = User.query.filter_by(firebase_uid=firebase_uid).first()

    if not user and normalized_email:
        user = User.query.filter(func.lower(User.email) == normalized_email).first()
        if user:
            user.firebase_uid = firebase_uid
            user.email = normalized_email
            if display_name:
                user.display_name = display_name
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                user = User.query.filter_by(firebase_uid=firebase_uid).first() or User.query.filter(func.lower(User.email) == normalized_email).first()

    if not user:
        # Create new user
        user = User(
            firebase_uid=firebase_uid,
            email=normalized_email,
            username=_unique_username_from_email(normalized_email),
            display_name=display_name or normalized_email.split('@')[0]
        )
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            user = User.query.filter_by(firebase_uid=firebase_uid).first() or User.query.filter(func.lower(User.email) == normalized_email).first()
            if not user:
                raise
    
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

        firebase_uid = decoded_token.get('uid')
        if not firebase_uid:
            print("Token verification failed: decoded Firebase token did not contain uid.")
            return jsonify({"error": "Invalid token"}), 401
        
        # Get or create user
        user = get_or_create_user(
            firebase_uid,
            decoded_token.get('email'),
            decoded_token.get('name')
        )
        
        # Store user in Flask's g object for use in route
        g.current_user = user
        g.test_activity = os.getenv('ADVENTOUR_DEV_AUTH') == 'true' and token.startswith('dev:')
        
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
            
            if decoded_token and decoded_token.get('uid'):
                user = get_or_create_user(
                    decoded_token.get('uid'),
                    decoded_token.get('email'),
                    decoded_token.get('name')
                )
                g.current_user = user
        
        return f(*args, **kwargs)
    
    return decorated_function

from flask import Blueprint, request, jsonify, g
from adventour_backend.models import db, User, Friendship, Trip, TripMember, TripPlace, PlaceRating, AdventourSession, AdventourStop
from adventour_backend.auth import require_auth, optional_auth
from datetime import datetime, date
import json
from sqlalchemy import and_, func, or_

social_bp = Blueprint('social', __name__)


def profile_payload(user):
    return {
        'id': user.id,
        'username': user.username,
        'display_name': user.display_name,
        'profile_picture': user.profile_picture,
    }


def accepted_friend_ids(user_id):
    friendships = Friendship.query.filter(
        and_(
            or_(Friendship.user_id == user_id, Friendship.friend_id == user_id),
            Friendship.status == 'accepted'
        )
    ).all()
    return [
        friendship.friend_id if friendship.user_id == user_id else friendship.user_id
        for friendship in friendships
    ]


def adventour_payload(session):
    owner = db.session.get(User, session.user_id)
    stops = session.stops.all()
    completed_stops = [stop for stop in stops if stop.status == 'completed']
    return {
        'id': session.id,
        'title': session.title,
        'status': session.status,
        'started_at': session.started_at.isoformat() if session.started_at else None,
        'ended_at': session.ended_at.isoformat() if session.ended_at else None,
        'summary': json.loads(session.summary_json or '{}'),
        'stop_count': len(completed_stops),
        'owner': profile_payload(owner) if owner else None,
        'stops': [
            {
                'id': stop.id,
                'place_id': stop.place_id,
                'provider_ref_id': stop.provider_ref_id,
                'order_index': stop.order_index,
                'metadata': json.loads(stop.metadata_json or '{}'),
            }
            for stop in completed_stops
        ],
    }

def metadata_for_taken_friend_stop(source_stop, source_session):
    try:
        metadata = json.loads(source_stop.metadata_json or '{}')
        if not isinstance(metadata, dict):
            metadata = {}
    except (TypeError, ValueError):
        metadata = {}

    metadata.update({
        'source': metadata.get('source') or 'friend_adventour',
        'source_friend_adventour_id': source_session.id,
        'source_friend_stop_id': source_stop.id,
        'source_friend_user_id': source_session.user_id,
    })
    return metadata

# Friend Management Routes
@social_bp.route('/friends', methods=['GET'])
@require_auth
def get_friends():
    """Get user's friends list"""
    user = g.current_user
    
    # Get accepted friendships
    friendships = Friendship.query.filter(
        and_(
            or_(Friendship.user_id == user.id, Friendship.friend_id == user.id),
            Friendship.status == 'accepted'
        )
    ).all()
    
    friends = []
    for friendship in friendships:
        if friendship.user_id == user.id:
            friend_user = User.query.get(friendship.friend_id)
        else:
            friend_user = User.query.get(friendship.user_id)
        
        friends.append({
            'id': friend_user.id,
            'username': friend_user.username,
            'display_name': friend_user.display_name,
            'profile_picture': friend_user.profile_picture,
            'friendship_id': friendship.id,
            'friendship_date': friendship.created_at.isoformat()
        })
    
    return jsonify({'friends': friends})

@social_bp.route('/friends/search', methods=['GET'])
@require_auth
def search_users():
    """Search for users to add as friends"""
    query = request.args.get('q', '').strip()
    if not query or len(query) < 2:
        return jsonify({'error': 'Search query must be at least 2 characters'}), 400
    
    user = g.current_user
    
    # Search by display name first. Username remains a fallback for older dev data.
    users = User.query.filter(
        and_(
            User.id != user.id,
            User.is_active == True,
            or_(
                User.display_name.ilike(f'%{query}%'),
                User.username.ilike(f'%{query}%')
            )
        )
    ).order_by(func.lower(User.display_name)).limit(10).all()
    
    results = []
    for found_user in users:
        # Check if friendship already exists
        existing_friendship = Friendship.query.filter(
            and_(
                or_(
                    and_(Friendship.user_id == user.id, Friendship.friend_id == found_user.id),
                    and_(Friendship.user_id == found_user.id, Friendship.friend_id == user.id)
                )
            )
        ).first()
        
        results.append({
            'id': found_user.id,
            'username': found_user.username,
            'display_name': found_user.display_name,
            'profile_picture': found_user.profile_picture,
            'friendship_status': existing_friendship.status if existing_friendship else None
        })
    
    return jsonify({'users': results})

@social_bp.route('/friends/adventours', methods=['GET'])
@require_auth
def get_friend_adventours():
    """Get completed Adventours taken by accepted friends."""
    user = g.current_user
    friend_ids = accepted_friend_ids(user.id)
    if not friend_ids:
        return jsonify({'adventours': []})

    limit = min(int(request.args.get('limit', 20)), 100)
    sessions = (
        AdventourSession.query
        .filter(
            AdventourSession.user_id.in_(friend_ids),
            AdventourSession.status == 'completed',
        )
        .order_by(AdventourSession.ended_at.desc(), AdventourSession.started_at.desc())
        .limit(limit)
        .all()
    )

    return jsonify({'adventours': [adventour_payload(session) for session in sessions]})

@social_bp.route('/friends/adventours/<int:session_id>/take', methods=['POST'])
@require_auth
def take_friend_adventour(session_id):
    """Create an active Adventour draft from a friend's completed Adventour."""
    user = g.current_user
    friend_ids = accepted_friend_ids(user.id)
    source = AdventourSession.query.filter(
        AdventourSession.id == session_id,
        AdventourSession.user_id.in_(friend_ids),
        AdventourSession.status == 'completed',
    ).first()
    if not source:
        return jsonify({'error': 'Friend Adventour not found'}), 404

    active = AdventourSession.query.filter_by(user_id=user.id, status='active').first()
    if active:
        return jsonify({'error': 'End your active Adventour before taking a friend Adventour'}), 409

    owner = db.session.get(User, source.user_id)
    source_summary = json.loads(source.summary_json or '{}')
    source_summary.update({
        'source': source_summary.get('source') or 'friend_adventour',
        'source_friend_adventour_id': source.id,
        'source_friend_user_id': source.user_id,
    })
    new_session = AdventourSession(
        user_id=user.id,
        title=f"{source.title} by {owner.display_name if owner else 'a friend'}",
        companion_user_ids_json=json.dumps({'ids': [source.user_id]}),
        summary_json=json.dumps(source_summary),
    )
    db.session.add(new_session)
    db.session.flush()

    for index, source_stop in enumerate([stop for stop in source.stops.all() if stop.status == 'completed']):
        db.session.add(AdventourStop(
            session_id=new_session.id,
            place_id=source_stop.place_id,
            provider_ref_id=source_stop.provider_ref_id,
            order_index=index,
            status='planned',
            metadata_json=json.dumps(metadata_for_taken_friend_stop(source_stop, source)),
        ))

    db.session.commit()
    return jsonify({'message': 'Friend Adventour added to your active trip', 'adventour': adventour_payload(new_session)}), 201

@social_bp.route('/friends/request', methods=['POST'])
@require_auth
def send_friend_request():
    """Send a friend request"""
    data = request.json
    friend_id = data.get('friend_id')
    
    if not friend_id:
        return jsonify({'error': 'Friend ID is required'}), 400
    
    user = g.current_user
    
    if user.id == friend_id:
        return jsonify({'error': 'Cannot send friend request to yourself'}), 400
    
    # Check if friendship already exists
    existing_friendship = Friendship.query.filter(
        and_(
            or_(
                and_(Friendship.user_id == user.id, Friendship.friend_id == friend_id),
                and_(Friendship.user_id == friend_id, Friendship.friend_id == user.id)
            )
        )
    ).first()
    
    if existing_friendship:
        if existing_friendship.status == 'accepted':
            return jsonify({'error': 'Already friends'}), 400
        elif existing_friendship.status == 'pending':
            return jsonify({'error': 'Friend request already sent'}), 400
        else:
            # Update blocked friendship to pending
            existing_friendship.status = 'pending'
            db.session.commit()
            return jsonify({'message': 'Friend request sent'})
    
    # Create new friendship
    friendship = Friendship(user_id=user.id, friend_id=friend_id, status='pending')
    db.session.add(friendship)
    db.session.commit()
    
    return jsonify({'message': 'Friend request sent'})

@social_bp.route('/friends/requests', methods=['GET'])
@require_auth
def get_friend_requests():
    """Get pending friend requests"""
    user = g.current_user
    
    pending_requests = Friendship.query.filter(
        and_(Friendship.friend_id == user.id, Friendship.status == 'pending')
    ).all()
    
    requests = []
    for friendship in pending_requests:
        requester = User.query.get(friendship.user_id)
        requests.append({
            'friendship_id': friendship.id,
            'user_id': requester.id,
            'username': requester.username,
            'display_name': requester.display_name,
            'profile_picture': requester.profile_picture,
            'request_date': friendship.created_at.isoformat()
        })
    
    return jsonify({'requests': requests})

@social_bp.route('/friends/respond', methods=['POST'])
@require_auth
def respond_to_friend_request():
    """Accept or reject a friend request"""
    data = request.json
    friendship_id = data.get('friendship_id')
    action = data.get('action')  # 'accept' or 'reject'
    
    if not friendship_id or action not in ['accept', 'reject']:
        return jsonify({'error': 'Friendship ID and action (accept/reject) are required'}), 400
    
    user = g.current_user
    
    friendship = Friendship.query.filter(
        and_(Friendship.id == friendship_id, Friendship.friend_id == user.id)
    ).first()
    
    if not friendship:
        return jsonify({'error': 'Friend request not found'}), 404
    
    if action == 'accept':
        friendship.status = 'accepted'
        message = 'Friend request accepted'
    else:
        friendship.status = 'rejected'
        message = 'Friend request rejected'
    
    db.session.commit()
    return jsonify({'message': message})

# Trip Management Routes
@social_bp.route('/trips', methods=['GET'])
@require_auth
def get_trips():
    """Get user's trips"""
    user = g.current_user
    
    trip_memberships = TripMember.query.filter_by(user_id=user.id).all()
    trips = []
    
    for membership in trip_memberships:
        trip = membership.trip
        if trip.is_active:
            trips.append({
                'id': trip.id,
                'name': trip.name,
                'description': trip.description,
                'destination': trip.destination,
                'start_date': trip.start_date.isoformat() if trip.start_date else None,
                'end_date': trip.end_date.isoformat() if trip.end_date else None,
                'role': membership.role,
                'member_count': trip.members.count(),
                'created_at': trip.created_at.isoformat()
            })
    
    return jsonify({'trips': trips})

@social_bp.route('/trips', methods=['POST'])
@require_auth
def create_trip():
    """Create a new trip"""
    data = request.json
    user = g.current_user
    
    name = data.get('name')
    description = data.get('description')
    destination = data.get('destination')
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    
    if not name:
        return jsonify({'error': 'Trip name is required'}), 400
    
    # Parse dates
    start_date_obj = None
    end_date_obj = None
    if start_date:
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid start date format. Use YYYY-MM-DD'}), 400
    
    if end_date:
        try:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid end date format. Use YYYY-MM-DD'}), 400
    
    # Create trip
    trip = Trip(
        name=name,
        description=description,
        destination=destination,
        start_date=start_date_obj,
        end_date=end_date_obj,
        created_by=user.id
    )
    db.session.add(trip)
    db.session.commit()
    
    # Add creator as owner
    trip_member = TripMember(
        trip_id=trip.id,
        user_id=user.id,
        role='owner'
    )
    db.session.add(trip_member)
    db.session.commit()
    
    return jsonify({
        'message': 'Trip created successfully',
        'trip_id': trip.id
    })

@social_bp.route('/trips/<int:trip_id>', methods=['GET'])
@require_auth
def get_trip_details(trip_id):
    """Get detailed trip information"""
    user = g.current_user
    
    # Check if user is member of trip
    membership = TripMember.query.filter_by(trip_id=trip_id, user_id=user.id).first()
    if not membership:
        return jsonify({'error': 'Trip not found or access denied'}), 404
    
    trip = membership.trip
    if not trip.is_active:
        return jsonify({'error': 'Trip not found'}), 404
    
    # Get trip members
    members = []
    for member in trip.members:
        member_user = User.query.get(member.user_id)
        members.append({
            'id': member_user.id,
            'username': member_user.username,
            'display_name': member_user.display_name,
            'role': member.role,
            'joined_at': member.joined_at.isoformat()
        })
    
    # Get trip places
    places = []
    for place in trip.places:
        places.append({
            'id': place.id,
            'place_id': place.place_id,
            'place_name': place.place_name,
            'place_address': place.place_address,
            'place_types': place.place_types.split(',') if place.place_types else [],
            'day_number': place.day_number,
            'order_in_day': place.order_in_day,
            'status': place.status,
            'added_by': place.added_by,
            'added_at': place.added_at.isoformat()
        })
    
    return jsonify({
        'trip': {
            'id': trip.id,
            'name': trip.name,
            'description': trip.description,
            'destination': trip.destination,
            'start_date': trip.start_date.isoformat() if trip.start_date else None,
            'end_date': trip.end_date.isoformat() if trip.end_date else None,
            'created_by': trip.created_by,
            'created_at': trip.created_at.isoformat(),
            'members': members,
            'places': places
        }
    })

@social_bp.route('/trips/<int:trip_id>/invite', methods=['POST'])
@require_auth
def invite_to_trip(trip_id):
    """Invite a friend to a trip"""
    data = request.json
    friend_id = data.get('friend_id')
    
    if not friend_id:
        return jsonify({'error': 'Friend ID is required'}), 400
    
    user = g.current_user
    
    # Check if user is trip admin/owner
    membership = TripMember.query.filter_by(trip_id=trip_id, user_id=user.id).first()
    if not membership or membership.role not in ['owner', 'admin']:
        return jsonify({'error': 'Insufficient permissions'}), 403
    
    # Check if friend is already a member
    existing_member = TripMember.query.filter_by(trip_id=trip_id, user_id=friend_id).first()
    if existing_member:
        return jsonify({'error': 'User is already a member of this trip'}), 400
    
    # Check if they are friends
    friendship = Friendship.query.filter(
        and_(
            or_(
                and_(Friendship.user_id == user.id, Friendship.friend_id == friend_id),
                and_(Friendship.user_id == friend_id, Friendship.friend_id == user.id)
            ),
            Friendship.status == 'accepted'
        )
    ).first()
    
    if not friendship:
        return jsonify({'error': 'Can only invite friends'}), 400
    
    # Add friend to trip
    trip_member = TripMember(
        trip_id=trip_id,
        user_id=friend_id,
        role='member'
    )
    db.session.add(trip_member)
    db.session.commit()
    
    return jsonify({'message': 'Friend invited to trip'})

@social_bp.route('/trips/<int:trip_id>/places', methods=['POST'])
@require_auth
def add_place_to_trip(trip_id):
    """Add a place to a trip"""
    data = request.json
    user = g.current_user
    
    place_id = data.get('place_id')
    place_name = data.get('place_name')
    place_address = data.get('place_address')
    place_types = data.get('place_types', [])
    day_number = data.get('day_number')
    order_in_day = data.get('order_in_day')
    
    if not place_id or not place_name:
        return jsonify({'error': 'Place ID and name are required'}), 400
    
    # Check if user is member of trip
    membership = TripMember.query.filter_by(trip_id=trip_id, user_id=user.id).first()
    if not membership:
        return jsonify({'error': 'Trip not found or access denied'}), 404
    
    # Add place to trip
    trip_place = TripPlace(
        trip_id=trip_id,
        place_id=place_id,
        place_name=place_name,
        place_address=place_address,
        place_types=','.join(place_types) if place_types else '',
        day_number=day_number,
        order_in_day=order_in_day,
        added_by=user.id
    )
    db.session.add(trip_place)
    db.session.commit()
    
    return jsonify({
        'message': 'Place added to trip',
        'trip_place_id': trip_place.id
    })

# Collaborative Recommendations
@social_bp.route('/trips/<int:trip_id>/recommendations', methods=['GET'])
@require_auth
def get_collaborative_recommendations(trip_id):
    """Get collaborative place recommendations for a trip"""
    user = g.current_user
    
    # Check if user is member of trip
    membership = TripMember.query.filter_by(trip_id=trip_id, user_id=user.id).first()
    if not membership:
        return jsonify({'error': 'Trip not found or access denied'}), 404
    
    trip = membership.trip
    if not trip.is_active:
        return jsonify({'error': 'Trip not found'}), 404
    
    # Get all trip members
    member_ids = [member.user_id for member in trip.members]
    
    # Get all place ratings from trip members
    member_ratings = PlaceRating.query.filter(
        PlaceRating.user_id.in_(member_ids)
    ).all()
    
    # Calculate collaborative scores
    place_scores = {}
    for rating in member_ratings:
        if rating.place_id not in place_scores:
            place_scores[rating.place_id] = {
                'total_rating': 0,
                'rating_count': 0,
                'raters': []
            }
        
        place_scores[rating.place_id]['total_rating'] += rating.rating
        place_scores[rating.place_id]['rating_count'] += 1
        place_scores[rating.place_id]['raters'].append(rating.user_id)
    
    # Calculate average ratings and collaborative scores
    collaborative_places = []
    for place_id, score_data in place_scores.items():
        avg_rating = score_data['total_rating'] / score_data['rating_count']
        
        # Collaborative score: higher if more members rated it positively
        collaborative_score = avg_rating * (score_data['rating_count'] / len(member_ids))
        
        collaborative_places.append({
            'place_id': place_id,
            'average_rating': round(avg_rating, 2),
            'rating_count': score_data['rating_count'],
            'collaborative_score': round(collaborative_score, 2),
            'rated_by_members': score_data['raters']
        })
    
    # Sort by collaborative score
    collaborative_places.sort(key=lambda x: x['collaborative_score'], reverse=True)
    
    return jsonify({
        'trip_id': trip_id,
        'member_count': len(member_ids),
        'recommendations': collaborative_places[:20]  # Top 20 recommendations
    })

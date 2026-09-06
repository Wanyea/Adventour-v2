from sqlalchemy import text

from adventour_backend.models import (
    db,
    AdventourSession,
    AdventourStop,
    Friendship,
    PlaceRating,
    Trip,
    TripMember,
    TripPlace,
    User,
)


def _delete_query(query):
    return query.delete(synchronize_session=False)


def delete_user_account_data(user):
    """Delete one user's private Adventour data while keeping the shared owned index."""
    deleted = {}

    created_trip_ids = [
        trip_id for (trip_id,) in db.session.query(Trip.id)
        .filter(Trip.created_by == user.id)
        .all()
    ]
    session_ids = [
        session_id for (session_id,) in db.session.query(AdventourSession.id)
        .filter(AdventourSession.user_id == user.id)
        .all()
    ]

    if session_ids:
        deleted["adventour_stops"] = _delete_query(
            AdventourStop.query.filter(AdventourStop.session_id.in_(session_ids))
        )
    else:
        deleted["adventour_stops"] = 0

    deleted["adventour_sessions"] = _delete_query(
        AdventourSession.query.filter(AdventourSession.user_id == user.id)
    )
    # Interactions now live in the index-backed `place_event` table.
    deleted["place_events"] = db.session.execute(
        text("DELETE FROM place_event WHERE user_id = :uid"), {"uid": user.id}
    ).rowcount
    for table in ("recommendation_decision", "provider_usage"):
        deleted[table] = db.session.execute(
            text(f"DELETE FROM {table} WHERE user_id=:uid"), {"uid": user.id}
        ).rowcount
    deleted["place_ratings"] = _delete_query(
        PlaceRating.query.filter(PlaceRating.user_id == user.id)
    )
    deleted["friendships"] = _delete_query(
        Friendship.query.filter(
            (Friendship.user_id == user.id) | (Friendship.friend_id == user.id)
        )
    )

    trip_place_filter = TripPlace.added_by == user.id
    trip_member_filter = TripMember.user_id == user.id
    if created_trip_ids:
        trip_place_filter = trip_place_filter | TripPlace.trip_id.in_(created_trip_ids)
        trip_member_filter = trip_member_filter | TripMember.trip_id.in_(created_trip_ids)

    deleted["trip_places"] = _delete_query(TripPlace.query.filter(trip_place_filter))
    deleted["trip_members"] = _delete_query(TripMember.query.filter(trip_member_filter))

    if created_trip_ids:
        deleted["trips"] = _delete_query(Trip.query.filter(Trip.id.in_(created_trip_ids)))
    else:
        deleted["trips"] = 0

    db.session.delete(user)
    db.session.flush()
    deleted["users"] = 1

    return deleted

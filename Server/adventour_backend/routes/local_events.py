"""Event list reads our index; explicit selection rechecks the free official source."""

from flask import Blueprint, jsonify, request
from sqlalchemy import text

from adventour_backend.models import db
from adventour_backend.services import local_event_service as events
from adventour_backend.auth import require_auth

blueprint = Blueprint('local_events', __name__)


@blueprint.get('/api/local-events')
@require_auth
def listing():
    try:
        result = events.listing(db, float(request.args['latitude']), float(request.args['longitude']),
                                float(request.args.get('radius_meters', 50000)), request.args.get('tag_group','all'))
        response = jsonify(result)
        response.headers['Cache-Control'] = 'no-store'
        return response
    except (ValueError, KeyError):
        return jsonify(error='Valid latitude, longitude and radius are required'), 400


@blueprint.post('/api/local-events/<source_id>/<occurrence_id>/verify')
@require_auth
def verify(source_id, occurrence_id):
    from data_pipeline.event_adapters import adapter
    config = events.sources().get(source_id)
    row = db.session.execute(text('SELECT * FROM local_event WHERE source_id=:s AND occurrence_id=:o'),
                             {'s':source_id,'o':occurrence_id}).mappings().first()
    if config is None or row is None:
        return jsonify(error='Event no longer listed; refresh the list'), 404
    try:
        checked = adapter(config).recheck(db, config, row)
    except Exception:
        db.session.rollback()
        return jsonify(error='Organizer could not be checked. Try again before leaving.'), 503
    if checked is None:
        db.session.execute(text('DELETE FROM local_event WHERE source_id=:s AND occurrence_id=:o'),
                           {'s':source_id,'o':occurrence_id})
        db.session.commit()
        return jsonify(error='Event ended, changed or is no longer available'), 410
    # Return fresh fields without persisting a partial source refresh. The regular
    # source snapshot remains the only writer/owner of its verification window.
    response = jsonify(event={k:v.isoformat() if hasattr(v,'isoformat') else v for k,v in checked.items()})
    response.headers['Cache-Control'] = 'no-store'
    return response

"""Study writes require an authenticated enrolled pilot request, not just an ID."""
from flask import Blueprint, g, jsonify, request
from sqlalchemy import text
from adventour_backend.auth import require_auth
from adventour_backend.models import db
from adventour_backend.services import pilot_service as pilot
from adventour_backend.services import pilot_feedback_service as feedback

blueprint = Blueprint('pilot', __name__)


@blueprint.post('/api/pilot/decisions/<decision_id>/<operation>')
@require_auth
def write(decision_id, operation):
    try:
        row = pilot.decision(db, g.current_user.id, decision_id)
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError('Expected an object')
        if operation == 'signals':
            result = feedback.signal(db, row, data)
        elif operation == 'feedback':
            result = feedback.answer(db, row, data)
        elif operation == 'invite':
            result = {'invitation': feedback.invitation(db, row, 'voluntary')}
        elif operation == 'present':
            ident = pilot.uid(data.get('invitation_id'))
            changed = db.session.execute(text("""UPDATE pilot_invitation SET presented_at=COALESCE(presented_at,now())
                WHERE id=:id AND decision_id=:d RETURNING id"""), {'id': ident, 'd': row['id']}).first()
            if not changed:
                raise ValueError('Invitation does not belong to decision')
            result = {'status': 'presented'}
        elif operation == 'skip':
            ident = pilot.uid(data.get('invitation_id'))
            inv = db.session.execute(text('SELECT status FROM pilot_invitation WHERE id=:id AND decision_id=:d'),
                                     {'id': ident, 'd': row['id']}).scalar()
            if inv is None or inv == 'answered':
                raise ValueError('Invitation unavailable or already answered')
            db.session.execute(text("UPDATE pilot_invitation SET status='skipped' WHERE id=:id"), {'id': ident})
            result = {'status': 'skipped'}
        else:
            return jsonify(error='Unknown pilot operation'), 404
        db.session.commit()
        response = jsonify(result)
        response.headers['Cache-Control'] = 'no-store'
        return response
    except PermissionError as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 403
    except ValueError as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 400

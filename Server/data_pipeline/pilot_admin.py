"""Owner-run pilot enrollment/export/replay. No public enrollment endpoint.

Run with ENV_FILE selecting the intended database; never prints credentials.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import uuid

from sqlalchemy import text


def replay(trace):
    from adventour_backend.services import personal_ranking_service as ranking
    if trace.get('model') != ranking.MODEL:
        raise ValueError('Replay requires the recorded model version')
    from adventour_backend.services.pilot_service import source_fingerprint
    if trace['rules'] != source_fingerprint():
        raise ValueError('Scoring source differs; check out the recorded rules before replay')
    history = trace['history']
    history = {**history, **{k: set(history[k]) for k in ('hidden', 'impressed', 'preferences')}}
    rows = [ranking.score({k:v for k,v in item.items() if k != 'chain_class'}, history,
                          trace['radius_meters'], item['chain_class']) for item in trace['scoring_inputs']]
    rows.sort(key=lambda p: (-p['score'], p['distance_meters'], p['place_id']))
    actual = [{'id': p['place_id'], 'score': p['score'], 'components': p['ranking_components']} for p in rows]
    return {'matches': actual == trace['ranked'], 'candidates': len(rows),
            'scope': 'SQL-eligible scoring/order replay, not original acquisition replay'}


def export(db, pilot_id):
    members = db.session.execute(text('SELECT participant_id,user_id FROM pilot_enrollment WHERE pilot_id=:p'),
                                 {'p': pilot_id}).mappings().all()
    people = {r['user_id']: r['participant_id'] for r in members}
    output = {'schema_version': 'pilot_export_v1', 'pilot_id': pilot_id,
              'exported_at': datetime.now(timezone.utc), 'requests': [], 'decisions': []}
    requests = db.session.execute(text('SELECT * FROM pilot_request WHERE pilot_id=:p ORDER BY created_at,id'),
                                  {'p': pilot_id}).mappings().all()
    for row in requests:
        item = dict(row)
        item['participant_id'] = people[item.pop('user_id')]
        output['requests'].append(item)
    rows = db.session.execute(text("""SELECT d.* FROM pilot_decision d
        JOIN pilot_request r ON r.id=d.request_id WHERE r.pilot_id=:p ORDER BY d.created_at,d.rank"""),
        {'p': pilot_id}).mappings().all()
    for row in rows:
        item = dict(row)
        item['signals'] = [dict(r) for r in db.session.execute(text('SELECT * FROM pilot_signal WHERE decision_id=:d ORDER BY received_at'), {'d': row['id']}).mappings()]
        item['invitations'] = [dict(r) for r in db.session.execute(text('SELECT * FROM pilot_invitation WHERE decision_id=:d ORDER BY offered_at'), {'d': row['id']}).mappings()]
        item['feedback'] = [dict(r) for r in db.session.execute(text('SELECT f.* FROM pilot_feedback f JOIN pilot_invitation i ON i.id=f.invitation_id WHERE i.decision_id=:d ORDER BY f.received_at'), {'d': row['id']}).mappings()]
        item['core_actions'] = [dict(r) for r in db.session.execute(text('SELECT event_type,event_value,occurred_at FROM place_event WHERE decision_id=:d ORDER BY occurred_at'), {'d': row['core_decision_id']}).mappings()] if row['core_decision_id'] else []
        output['decisions'].append(item)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['enroll', 'revoke', 'allow-build', 'export', 'purge', 'replay'])
    parser.add_argument('--pilot', required=True)
    parser.add_argument('--user-id', type=int)
    parser.add_argument('--build')
    parser.add_argument('--consent-version')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--request-id')
    args = parser.parse_args()
    from app import app, db
    from adventour_backend.services.pilot_service import encode
    with app.app_context():
        if args.operation == 'enroll':
            if not args.user_id or not args.consent_version:
                parser.error('enroll requires --user-id and --consent-version after participant agreement')
            db.session.execute(text("""INSERT INTO pilot_enrollment(pilot_id,user_id,participant_id,consent_version)
                VALUES(:p,:u,:id,:c) ON CONFLICT(pilot_id,user_id)
                DO UPDATE SET active=true,consent_version=EXCLUDED.consent_version"""),
                {'p': args.pilot, 'u': args.user_id, 'id': str(uuid.uuid4()), 'c': args.consent_version})
        elif args.operation == 'revoke':
            if not args.user_id:
                parser.error('revoke requires --user-id')
            db.session.execute(text('UPDATE pilot_enrollment SET active=false WHERE pilot_id=:p AND user_id=:u'),
                               {'p': args.pilot, 'u': args.user_id})
        elif args.operation == 'allow-build':
            if not args.build:
                parser.error('allow-build requires --build')
            db.session.execute(text('INSERT INTO pilot_build(pilot_id,build_id) VALUES(:p,:b) ON CONFLICT(pilot_id,build_id) DO UPDATE SET active=true'), {'p': args.pilot, 'b': args.build})
        elif args.operation == 'export':
            if not args.output:
                parser.error('export requires --output')
            # Refuse overwrite; exports contain private launch/feedback evidence.
            with args.output.open('x', encoding='utf-8') as stream:
                stream.write(encode(export(db, args.pilot)) + '\n')
        elif args.operation == 'replay':
            row = db.session.execute(text('SELECT trace FROM pilot_request WHERE id=:id AND pilot_id=:p'), {'id': args.request_id, 'p': args.pilot}).scalar()
            if row is None:
                parser.error('request not found')
            result = replay(row)
            print(json.dumps(result))
            if not result['matches']:
                raise SystemExit(1)
        elif args.operation == 'purge':
            count = db.session.execute(text('DELETE FROM pilot_request WHERE pilot_id=:p AND created_at<:cutoff'),
                                       {'p': args.pilot, 'cutoff': datetime.now(timezone.utc)-timedelta(days=30)}).rowcount
            print(json.dumps({'deleted_expired_study_requests': count}))
        db.session.commit()


if __name__ == '__main__':
    main()

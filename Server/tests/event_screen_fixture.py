"""Manual emulator fixture; refuses any database except the isolated ingest check.

From Server: python tests/event_screen_fixture.py seed|expire|cancel|clean
Temporarily stop the local backend, then run it with ENV_FILE=.env.ingest-check
on port 8080. Restore ENV_FILE=.env.local after the walkthrough. The native app
uses 10.0.2.2:8080; adb reverse does not change that address.
Never add these occurrences to the source roster or human evaluation labels.
"""

import argparse
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['ENV_FILE'] = '.env.ingest-check'
import app as backend
import h3
from sqlalchemy import text
from sqlalchemy.engine import make_url
from adventour_backend.services import local_event_service as events

SOURCE = 'synthetic-screen-check'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['seed', 'expire', 'cancel', 'clean'])
    args = parser.parse_args()
    database = make_url(backend.app.config['SQLALCHEMY_DATABASE_URI']).database
    if not database.startswith('adventour_ingest_check_'):
        raise SystemExit('Refusing to modify a non-isolated database')
    now = datetime.now(timezone.utc)
    config = {**events.sources()['ucf_main'], 'name': 'SYNTHETIC TEST calendar'}
    report = {'window_start': now.astimezone(ZoneInfo('America/New_York')).date().isoformat(), 'window_days': 14}
    with backend.app.app_context():
        if args.action in {'seed', 'expire'}:
            end = now + timedelta(seconds=90 if args.action == 'expire' else 3600)
            records = []
            for occurrence, title, ends in [('expiry', 'SYNTHETIC TEST: timed expiry', end),
                                           ('cancel', 'SYNTHETIC TEST: cancellation control', now+timedelta(hours=2))]:
                records.append(dict(source_id=SOURCE, occurrence_id=occurrence, series_id=occurrence,
                    title=title, starts_at=now-timedelta(minutes=1), ends_at=ends,
                    timezone='America/New_York', metro='orlando', category='arts_culture',
                    source_url='https://example.invalid/test', official_url='https://example.invalid/test',
                    access_note='Isolated test data. Not a real event.', access_url='https://example.invalid/test',
                    venue_name='SYNTHETIC Orlando location', entity_id=None,
                    latitude=28.5383, longitude=-81.3792, h3_r8=h3.latlng_to_cell(28.5383,-81.3792,8),
                    verified_at=now, expires_at=ends))
            events.replace_window(backend.db, SOURCE, config, records, report, now)
        elif args.action == 'cancel':
            events.replace_window(backend.db, SOURCE, config, [], report, now)
        else:
            backend.db.session.execute(text('DELETE FROM local_event WHERE source_id=:s'), {'s': SOURCE})
            backend.db.session.execute(text('DELETE FROM event_source WHERE id=:s'), {'s': SOURCE})
        backend.db.session.commit()
        print({'database': database, 'action': args.action, 'at': now.isoformat()})


if __name__ == '__main__':
    main()

"""Refresh permitted regional sources: python -m data_pipeline.refresh_events [--watch]."""

import argparse
from datetime import date, datetime, timezone
import json
import os
import time
from zoneinfo import ZoneInfo

from sqlalchemy import text


def refresh(backend, start, days):
    from adventour_backend.services import local_event_service as events
    from data_pipeline.event_adapters import adapter
    reports = {}
    with backend.app.app_context():
        for source_id, config in events.sources().items():
            try:
                records, report = adapter(config).collect(backend.db, config, start, days)
                events.replace_window(backend.db, source_id, config, records, report)
                backend.db.session.commit()
                reports[source_id] = report
            except Exception as exc:
                backend.db.session.rollback()
                # Do not persist response bodies, query credentials or arbitrary error text.
                backend.db.session.execute(text("""INSERT INTO event_source(id,name,metro,permission_url,last_attempt,last_error)
                    VALUES(:id,:name,:metro,:url,:now,:error) ON CONFLICT(id) DO UPDATE
                    SET last_attempt=:now,last_error=:error"""),
                    {'id': source_id, 'name': config['name'], 'metro': config['metro'],
                     'url': config['permission_url'], 'now': datetime.now(timezone.utc),
                     'error': type(exc).__name__})
                backend.db.session.commit()
                reports[source_id] = {'error': type(exc).__name__, 'freshness_renewed': False}
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=date.fromisoformat)
    parser.add_argument('--days', type=int, default=14)
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    if not 1<=args.days<=31 or args.watch and args.start:
        parser.error('Use 1–31 days; watch must follow the current date')
    os.environ.setdefault('ENV_FILE', '.env.local')
    import app as backend
    while True:
        start = args.start or datetime.now(ZoneInfo('America/New_York')).date()
        result = refresh(backend, start, args.days)
        print(json.dumps(result, indent=2), flush=True)
        if not args.watch:
            return 1 if any('error' in r for r in result.values()) else 0
        time.sleep(6*60*60)


if __name__ == '__main__':
    raise SystemExit(main())

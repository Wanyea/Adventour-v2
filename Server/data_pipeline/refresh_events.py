"""Refresh configured regional event sources with bounded, source-specific polling."""

import argparse
from datetime import date, datetime, timedelta, timezone
import json
import os
import time
from zoneinfo import ZoneInfo

from sqlalchemy import text

from data_pipeline import event_registry


def _last_attempt(db, source_id):
    return db.session.execute(text('SELECT last_attempt FROM event_source WHERE id=:id'),
                              {'id': source_id}).scalar()


def due(db, source_id, config, now):
    """Failures back off too: last_attempt, rather than last_success, sets eligibility."""
    attempted = _last_attempt(db, source_id)
    return attempted is None or attempted <= now-timedelta(hours=config['refresh_hours'])


def _lock(db, source_id):
    return bool(db.session.execute(text('SELECT pg_try_advisory_xact_lock(hashtext(:id))'),
                                   {'id': source_id}).scalar())


def _failure(db, source_id, config, now, exc):
    # Do not store response bodies, URLs with query parameters, credentials, or arbitrary error text.
    db.session.execute(text("""INSERT INTO event_source(id,name,metro,permission_url,last_attempt,last_error)
        VALUES(:id,:name,:metro,:url,:now,:error) ON CONFLICT(id) DO UPDATE
        SET last_attempt=:now,last_error=:error"""),
        {'id': source_id, 'name': config['name'], 'metro': config['metro'],
         'url': config['permission_url'], 'now': now, 'error': type(exc).__name__})
    db.session.commit()


def _collect(backend, config, start, days):
    from data_pipeline.event_adapters import adapter
    from data_pipeline.event_http import BoundedSession
    session = BoundedSession(config['network'])
    try:
        records, report = adapter(config).collect(backend.db, config, start, days, session=session)
        return records, {**report, 'network': session.metrics()}
    finally:
        session.close()


def refresh(backend, start, days, *, region=None, source_id=None, dry_run=False, due_only=False, now=None):
    """Refresh due configured sources. Existing three-argument callers remain supported."""
    supplied_now = now is not None
    now = now or datetime.now(timezone.utc)
    events = None
    # The original three-argument API is an operator-forced refresh, which is
    # still needed for cancellation/outage checks. Region/source scheduling uses
    # the validated registry and may opt into due-only behavior.
    selected = event_registry.selected(region, source_id) if region or source_id else None
    if not selected:
        if region or source_id:
            return {'_selection': {'region': region, 'source': source_id,
                                   'status': 'no_configured_source', 'sources': 0,
                                   'network': {'requests': 0, 'bytes': 0, 'elapsed_seconds': 0}}}
        event_registry.sources()  # Validate the checked-in operator registry before a forced run.
        from adventour_backend.services import local_event_service as events
        selected = {key: {**config, 'source_id': key} for key, config in events.sources().items()}
    from adventour_backend.services import local_event_service as events
    reports = {}
    with backend.app.app_context():
        for key, config in selected.items():
            if not dry_run and not _lock(backend.db, key):
                backend.db.session.rollback()
                reports[key] = {'status': 'locked', 'freshness_renewed': False}
                continue
            if due_only and not due(backend.db, key, config, now):
                backend.db.session.rollback()
                reports[key] = {'status': 'not_due', 'freshness_renewed': False}
                continue
            savepoint = None if dry_run else backend.db.session.begin_nested()
            try:
                source_start = start or now.astimezone(ZoneInfo(config['timezone'])).date()
                records, report = _collect(backend, config, source_start, days)
                report = {**report, 'status': 'dry_run' if dry_run else 'refreshed',
                          'source_id': key, 'records': len(records),
                          'parser_version': config['parser_version'], 'timezone': config['timezone']}
                if not dry_run:
                    # Collection verification can occur after the due-clock read.
                    # A supplied clock keeps isolated tests deterministic.
                    persisted_at = now if supplied_now else datetime.now(timezone.utc)
                    events.replace_window(backend.db, key, config, records, report, persisted_at)
                    savepoint.commit()
                    backend.db.session.commit()
                reports[key] = report
            except Exception as exc:
                if dry_run:
                    backend.db.session.rollback()
                else:
                    savepoint.rollback()
                    _failure(backend.db, key, config, now, exc)
                reports[key] = {'error': type(exc).__name__, 'freshness_renewed': False}
    return reports


def _next_poll(registry):
    return max(1, min(int(config['refresh_hours'] * 3600) for config in registry.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=date.fromisoformat)
    parser.add_argument('--days', type=int, default=14)
    parser.add_argument('--region', help='Exact configured metro, e.g. orlando')
    parser.add_argument('--source', dest='source_id', help='Configured source ID')
    parser.add_argument('--dry-run', action='store_true', help='Fetch and report without database writes')
    parser.add_argument('--due', action='store_true', help='Refresh only sources whose backoff has elapsed')
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.days <= 14 or args.watch and args.start:
        parser.error('Use 1-14 days; watch must follow the current date')
    os.environ.setdefault('ENV_FILE', '.env.local')
    registry = event_registry.selected(args.region, args.source_id)
    if (args.region or args.source_id) and not registry:
        print(json.dumps({'_selection': {'region': args.region, 'source': args.source_id,
                                         'status': 'no_configured_source', 'sources': 0,
                                         'network': {'requests': 0, 'bytes': 0, 'elapsed_seconds': 0}}}, indent=2))
        return 0
    import app as backend
    while True:
        start = args.start
        result = refresh(backend, start, args.days, region=args.region, source_id=args.source_id,
                         dry_run=args.dry_run, due_only=args.due or args.watch)
        print(json.dumps(result, indent=2), flush=True)
        if not args.watch:
            return 1 if any('error' in report for report in result.values()) else 0
        time.sleep(_next_poll(registry) if registry else 60)


if __name__ == '__main__':
    raise SystemExit(main())

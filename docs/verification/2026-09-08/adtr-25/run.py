"""Repeat ADTR-25 live evidence using an isolated Postgres ENV_FILE only."""

import json
from pathlib import Path
import sys
import time
from unittest.mock import patch


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'Server'))
    import app
    from sqlalchemy import text
    from sqlalchemy.engine import make_url
    from data_pipeline.refresh_events import refresh
    from adventour_backend.services.local_event_service import listing

    assert make_url(app.app.config['SQLALCHEMY_DATABASE_URI']).database.startswith('adventour_ingest_check_')
    out = {'acquisitions': {}, 'repeat': {}, 'listing': {}}
    for region in ('new_york', 'orlando'):
        out['acquisitions'][region] = refresh(app, None, 14, region=region)
        out['repeat'][region] = refresh(app, None, 14, region=region)
    out['unconfigured'] = refresh(app, None, 14, region='seattle')
    with app.app.app_context():
        out['stored_counts'] = dict(app.db.session.execute(text(
            'SELECT source_id,count(*) FROM local_event GROUP BY source_id')).all())
        with patch('requests.sessions.Session.request', side_effect=AssertionError('Listing attempted HTTP')):
            for name, lat, lon in [('nyc',40.7128,-74.006), ('ucf',28.6027,-81.2038), ('empty',47.6062,-122.3321)]:
                started = time.perf_counter()
                result = listing(app.db, lat, lon, 50000)
                out['listing'][name] = {
                    'returned': len(result['events']),
                    'latency_ms': round((time.perf_counter()-started)*1000,2),
                    'provider_calls': 0,
                    'source_ids': sorted({r['source_id'] for r in result['events']}),
                    'sample_titles': [r['title'] for r in result['events'][:3]],
                    'coverage_note': result['coverage_note'],
                }
        from data_pipeline.event_adapters import adapter
        from data_pipeline.event_registry import sources
        out['rechecks'] = {}
        for source_id, config in sources().items():
            row = app.db.session.execute(text(
                'SELECT * FROM local_event WHERE source_id=:source ORDER BY starts_at LIMIT 1'),
                {'source': source_id}).mappings().first()
            started = time.perf_counter()
            checked = adapter(config).recheck(app.db, config, row) if row else None
            out['rechecks'][source_id] = {
                'matched_occurrence': bool(checked and checked['occurrence_id']==row['occurrence_id']),
                'elapsed_seconds': round(time.perf_counter()-started,3),
            }
    Path(__file__).with_name('runtime.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
    print(json.dumps(out,indent=2))
    return int(any('error' in result for group in ('acquisitions','repeat')
                   for region in out[group].values() for result in region.values()))


if __name__ == '__main__':
    raise SystemExit(main())

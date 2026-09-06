"""Regression: an Orlando POI address must not manufacture a New York city launch."""

import os
import pytest
from sqlalchemy import text


def test_city_launch_uses_acquired_metro_not_poi_address():
    if os.getenv('ENV_FILE') != '.env.ingest-check':
        pytest.skip('Isolated database only')
    import app as backend
    from sqlalchemy.engine import make_url
    from adventour_backend.services import launch_service as launch
    assert make_url(backend.app.config['SQLALCHEMY_DATABASE_URI']).database.startswith('adventour_ingest_check_')
    with backend.app.app_context():
        try:
            # Session-local shadow: the real places table and its rows are untouched.
            backend.db.session.execute(text('''CREATE TEMP TABLE places (
                metro text, locality text, region text, name text, lat double precision,
                lon double precision, canonical_lat double precision, canonical_lon double precision,
                index_active boolean DEFAULT true, tier text DEFAULT 'KEEP') ON COMMIT DROP'''))
            backend.db.session.execute(text('''INSERT INTO places(metro,locality,region,name,lat,lon) VALUES
                ('orlando','New York','NY','Address mismatch',28.55,-81.37),
                ('orlando','Orlando','FL','New York Pizza',28.53,-81.38),
                ('orlando','ORLANDO','FL','Local cafe',28.54,-81.39),
                ('palm_coast','Palm Coast','FL','Local park',29.58,-81.20)'''))
            assert [r['description'] for r in launch.suggestions(backend.db,'New York')] == ['New York Pizza, FL']
            for query in ('New York', 'New York, NY', 'New York New York', 'New York Pizz'):
                with pytest.raises(ValueError): launch.resolve(backend.db,query)
            assert launch.resolve(backend.db,'New York Pizza, FL')['latitude'] == 28.53
            assert launch.resolve(backend.db,'Orlando, FL')['latitude'] == pytest.approx(28.54)
            assert launch.resolve(backend.db,'Palm Coast')['latitude'] == 29.58
        finally:
            backend.db.session.rollback()

"""Additive Postgres upgrade shared by backend startup and local verification."""

import h3
from psycopg2.extras import execute_values

from data_pipeline.create_events_table import DDL
from data_pipeline.postgres_index import SCHEMA


def ensure(engine):
    if engine.dialect.name != "postgresql":
        return
    connection = engine.raw_connection()
    try:
        with connection.cursor() as cur:
            cur.execute(SCHEMA)
            cur.execute(DDL)
            cur.execute("""SELECT id,COALESCE(canonical_lat,lat),COALESCE(canonical_lon,lon)
                FROM places WHERE canonical_h3_r8 IS NULL""")
            updates = [(pid, h3.latlng_to_cell(lat, lon, 8)) for pid, lat, lon in cur.fetchall()]
            if updates:
                execute_values(cur, "UPDATE places p SET canonical_h3_r8=v.h FROM (VALUES %s) v(id,h) WHERE p.id=v.id", updates)
            # Previous emulator events are known test activity; keep their original contents.
            cur.execute("""UPDATE place_event e SET test_activity=true FROM \"user\" u
                WHERE e.user_id=u.id AND u.firebase_uid LIKE 'dev-%%' AND NOT e.test_activity""")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

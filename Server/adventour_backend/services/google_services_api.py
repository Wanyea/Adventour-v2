"""Uncached Google ID/status verification, usable only after a recorded accept.

Returned content is transient. Only the place ID and our editorial suppression
flag may be persisted by the caller; no provider display data enters a deck.
"""

import logging
import os
import re
import unicodedata
from contextlib import contextmanager
from contextvars import ContextVar

import requests
from sqlalchemy import text

from data_pipeline.dedup import haversine_m

logger = logging.getLogger(__name__)
_in_deck = ContextVar('in_deck', default=False)


@contextmanager
def deck_boundary():
    token = _in_deck.set(True)
    try:
        yield
    finally:
        _in_deck.reset(token)


def _name(value):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', value or '').casefold())


class GoogleServicesAPI:
    BASE_URL = 'https://places.googleapis.com/v1'

    @staticmethod
    def _request(db, user_id, method, path, field_mask, body=None):
        if _in_deck.get():
            raise RuntimeError('Provider access is forbidden while building a deck')
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            return None
        limit = max(0, min(20, int(os.getenv('GOOGLE_DAILY_CALL_LIMIT', '6'))))
        # Reserve in its own transaction before network I/O. Failures still cost a
        # request; rolling back an application transaction cannot refund the quota.
        with db.engine.begin() as connection:
            reserved = connection.execute(text("""INSERT INTO provider_usage(user_id,usage_day,calls)
                SELECT :uid,(now() AT TIME ZONE 'UTC')::date,1 WHERE :limit>0
                ON CONFLICT(user_id,usage_day) DO UPDATE SET calls=provider_usage.calls+1
                WHERE provider_usage.calls<:limit RETURNING calls"""),
                {'uid': user_id, 'limit': limit}).scalar()
        if reserved is None:
            logger.info('provider_request denied=quota user=%s', user_id)
            return None
        logger.info('provider_request provider=google user=%s operation=%s daily_count=%s', user_id, path.split('/')[0], reserved)
        try:
            response = requests.request(method, f'{GoogleServicesAPI.BASE_URL}/{path}',
                headers={'X-Goog-Api-Key': api_key, 'X-Goog-FieldMask': field_mask}, json=body, timeout=8)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            # URLs/bodies can expose keys or provider content. Log neither.
            logger.warning('provider_request failed provider=google user=%s', user_id)
            return None

    @staticmethod
    def verify_accepted(db, user_id, place_id):
        accepted = db.session.execute(text("""SELECT d.entity_id,d.payload
            FROM recommendation_decision d WHERE d.user_id=:uid AND d.entity_id=:id AND d.verdict='accept'
            ORDER BY d.served_at DESC LIMIT 1"""), {'uid': user_id, 'id': place_id}).mappings().first()
        if not accepted:
            raise ValueError('Accept the place before requesting provider verification.')
        owned = accepted['payload']
        suppressed_id = db.session.execute(text("""SELECT r.google_place_id FROM place_provider_ref r
            JOIN suppressed_place s ON s.google_place_id=r.google_place_id WHERE r.entity_id=:id"""),
            {'id': place_id}).scalar()
        if suppressed_id:
            return {'verification': 'suppressed', 'google_place_id': suppressed_id}
        if not os.getenv('GOOGLE_API_KEY') or owned.get('snapshot_origin') == 'legacy_unsnapshotted':
            return {'verification': 'unavailable'}
        google_id = db.session.execute(text('SELECT google_place_id FROM place_provider_ref WHERE entity_id=:id'),
                                       {'id': place_id}).scalar()
        if not google_id:
            search = GoogleServicesAPI._request(db, user_id, 'POST', 'places:searchText', 'places.id', {
                'textQuery': owned['name'], 'pageSize': 1,
                'locationBias': {'circle': {'center': {'latitude': owned['latitude'], 'longitude': owned['longitude']}, 'radius': 150.0}},
            })
            candidates = (search or {}).get('places') or []
            google_id = candidates[0].get('id') if candidates else None
        if not google_id or not re.fullmatch(r'[A-Za-z0-9_-]+', google_id):
            return {'verification': 'unavailable'}
        details = GoogleServicesAPI._request(db, user_id, 'GET', f'places/{google_id}',
                                             'id,displayName,location,businessStatus')
        if not details:
            return {'verification': 'unavailable'}
        location = details.get('location') or {}
        if not (_name((details.get('displayName') or {}).get('text')) == _name(owned['name'])
                and location.get('latitude') is not None and location.get('longitude') is not None
                and haversine_m(owned['latitude'], owned['longitude'], location['latitude'], location['longitude']) <= 150):
            return {'verification': 'unmatched'}
        db.session.execute(text("""INSERT INTO place_provider_ref(entity_id,google_place_id) VALUES(:id,:gid)
            ON CONFLICT(entity_id) DO NOTHING"""), {'id': place_id, 'gid': google_id})
        if details.get('businessStatus') == 'CLOSED_PERMANENTLY':
            db.session.execute(text("""INSERT INTO suppressed_place(google_place_id) VALUES(:gid)
                ON CONFLICT(google_place_id) DO NOTHING"""), {'gid': google_id})
            return {'verification': 'suppressed', 'google_place_id': google_id}
        return {'verification': 'matched', 'google_place_id': google_id}

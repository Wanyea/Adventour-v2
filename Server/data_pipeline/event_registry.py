"""Validated, operator-configured regional event-source registry."""

from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


SOURCES = Path(__file__).with_name('event_sources.json')
NETWORK_FIELDS = ('allowed_hosts', 'max_requests', 'max_pages', 'max_bytes',
                  'min_interval_seconds', 'connect_timeout_seconds',
                  'read_timeout_seconds', 'total_timeout_seconds')


def _positive(value, name):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ValueError(f'Event source {name} must be positive')


def _nonnegative(value, name):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ValueError(f'Event source {name} must be non-negative')


def _validate(source_id, config):
    required = ('source_id', 'name', 'metro', 'method', 'timezone', 'parser_version',
                'permission_url', 'permission_checked', 'permission_basis',
                'refresh_hours', 'max_age_hours', 'retention', 'access_url', 'network')
    missing = [field for field in required if not config.get(field)]
    if missing:
        raise ValueError(f'Event source {source_id} missing ' + ', '.join(missing))
    if config['source_id'] != source_id:
        raise ValueError(f'Event source {source_id} has mismatched source_id')
    try:
        ZoneInfo(config['timezone'])
    except Exception as exc:
        raise ValueError(f'Event source {source_id} has invalid timezone') from exc
    for field in ('permission_url', 'access_url'):
        parsed = urlparse(config[field])
        if parsed.scheme != 'https' or not parsed.hostname:
            raise ValueError(f'Event source {source_id} has invalid {field}')
    for field in ('refresh_hours', 'max_age_hours'):
        _positive(config[field], f'{source_id}.{field}')
    if config['max_age_hours'] > 24:
        raise ValueError(f'Event source {source_id}.max_age_hours may not exceed 24')
    network = config['network']
    if not isinstance(network, dict):
        raise ValueError(f'Event source {source_id} network must be an object')
    missing = [field for field in NETWORK_FIELDS if field not in network]
    if missing:
        raise ValueError(f'Event source {source_id} network missing ' + ', '.join(missing))
    hosts = network['allowed_hosts']
    if not isinstance(hosts, list) or not hosts or any(not isinstance(host, str) or not host for host in hosts):
        raise ValueError(f'Event source {source_id} needs allowed hosts')
    for field in NETWORK_FIELDS[1:]:
        if field == 'min_interval_seconds':
            continue
        _positive(network[field], f'{source_id}.network.{field}')
    _nonnegative(network['min_interval_seconds'], f'{source_id}.network.min_interval_seconds')


def sources(path=SOURCES):
    """Return a validated copy of the checked-in source registry."""
    try:
        raw = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError('Event source registry is unreadable') from exc
    if not isinstance(raw, dict):
        raise ValueError('Event source registry must be an object')
    for source_id, config in raw.items():
        if not isinstance(source_id, str) or not source_id or not isinstance(config, dict):
            raise ValueError('Event source registry has an invalid source entry')
        _validate(source_id, config)
    return deepcopy(raw)


def selected(region=None, source_id=None, registry=None):
    """Select one configured source or all sources in an exact configured metro."""
    registry = sources() if registry is None else registry
    if source_id:
        config = registry.get(source_id)
        if config is None or region and config['metro'] != region:
            return {}
        return {source_id: {**config, 'source_id': source_id}}
    if region:
        return {key: {**value, 'source_id': key} for key, value in registry.items()
                if value['metro'] == region}
    return {key: {**value, 'source_id': key} for key, value in registry.items()}

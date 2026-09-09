"""Contracts for the bounded regional event refresh scheduler."""

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone

import pytest

from data_pipeline import event_registry
from data_pipeline import refresh_events


def test_registry_selects_exact_configured_region_and_requires_network_budget(tmp_path):
    registry = event_registry.sources()
    assert set(event_registry.selected('orlando', registry=registry)) == {'ucf_main'}
    assert event_registry.selected('not_a_configured_region', registry=registry) == {}
    assert registry['ucf_main']['timezone'] == 'America/New_York'
    assert registry['nyc_parks']['network']['allowed_hosts'] == ['data.cityofnewyork.us']

    bad = {**registry['ucf_main']}
    bad['source_id'] = 'bad'
    bad['network'] = {**bad['network']}
    del bad['network']['max_bytes']
    path = tmp_path / 'sources.json'
    path.write_text(__import__('json').dumps({'bad': bad}), encoding='utf-8')
    with pytest.raises(ValueError, match='max_bytes'):
        event_registry.sources(path)


def test_due_uses_last_attempt_for_success_and_failure_backoff():
    now = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)

    class Result:
        def __init__(self, value): self.value = value
        def scalar(self): return self.value

    class Session:
        def __init__(self, value): self.value = value
        def execute(self, *_args, **_kwargs): return Result(self.value)

    class Db:
        def __init__(self, value): self.session = Session(value)

    config = {'refresh_hours': 6}
    assert not refresh_events.due(Db(now-timedelta(hours=5)), 'source', config, now)
    assert refresh_events.due(Db(now-timedelta(hours=6)), 'source', config, now)
    assert refresh_events.due(Db(None), 'source', config, now)


def test_unknown_region_reports_no_configured_source_without_opening_app_context():
    class Backend:
        class App:
            def app_context(self):
                raise AssertionError('unconfigured region must not touch the database')
        app = App()

    result = refresh_events.refresh(Backend(), datetime(2026, 9, 8).date(), 14, region='unknown')
    assert result == {'_selection': {'region': 'unknown', 'source': None,
                                     'status': 'no_configured_source', 'sources': 0,
                                     'network': {'requests': 0, 'bytes': 0, 'elapsed_seconds': 0}}}


def test_dry_run_collects_but_never_commits_or_replaces(monkeypatch):
    calls = []

    class Session:
        def commit(self): raise AssertionError('dry run must not commit')
        def rollback(self): calls.append('rollback')

    class Backend:
        class App:
            def app_context(self): return nullcontext()
        app = App()
        class Db:
            session = Session()
        db = Db()

    config = event_registry.selected('orlando')['ucf_main']
    monkeypatch.setattr(event_registry, 'selected', lambda *_args: {'test_source': config})
    monkeypatch.setattr(refresh_events, '_collect', lambda *_args: ([{'occurrence_id': 'one'}], {'counts': {}}))
    result = refresh_events.refresh(Backend(), datetime(2026, 9, 8).date(), 14,
                                    region='orlando', dry_run=True)
    assert result['test_source']['status'] == 'dry_run'
    assert result['test_source']['records'] == 1
    assert calls == []

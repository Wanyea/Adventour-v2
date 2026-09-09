"""Bounded event-source HTTP transport checks, using no network access."""

import multiprocessing
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from data_pipeline.event_http import (BoundedSession, ConditionalResponseError,
                                      HostNotAllowedError, TransportLimitError)


POLICY = {'allowed_hosts': ['events.example.test'], 'max_requests': 3, 'max_pages': 2,
          'max_bytes': 12, 'min_interval_seconds': 0, 'connect_timeout_seconds': 4,
          'read_timeout_seconds': 5, 'total_timeout_seconds': 10}


class Clock:
    def __init__(self): self.now = 0
    def __call__(self): return self.now
    def sleep(self, seconds): self.now += seconds


class Response:
    def __init__(self, status=200, body=b'{}', headers=None, url='https://events.example.test/feed'):
        self.status_code, self._body, self.headers, self.url, self.closed = status, body, headers or {}, url, False
        self.is_redirect = status in (301, 302, 303, 307, 308)
        self.is_permanent_redirect = status in (301, 308)
        self.encoding = 'utf-8'
    def iter_content(self, chunk_size):
        yield from (self._body[offset:offset+chunk_size] for offset in range(0, len(self._body), chunk_size))
    def close(self): self.closed = True


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls, self.headers, self.closed = list(responses), [], {}, False
    def get(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.responses.pop(0)
    def close(self): self.closed = True


def session(responses, policy=POLICY, clock=None):
    clock = clock or Clock()
    return BoundedSession(policy, FakeSession(responses), clock=clock, sleep=clock.sleep)


def test_headers_timeout_response_and_metrics_are_requests_compatible():
    raw = FakeSession([Response(body=b'{"ok": true}')])
    transport = BoundedSession(POLICY, raw)
    transport.headers.update({'User-Agent': 'Adventour test', 'If-None-Match': 'etag'})
    response = transport.get('https://events.example.test/feed', params={'day': '2026-09-08'}, timeout=(9, 2))
    assert response.json() == {'ok': True} and response.text == '{"ok": true}'
    response.raise_for_status()
    assert raw.headers['If-None-Match'] == 'etag'
    assert raw.calls[0][1]['timeout'] == (4.0, 2.0)
    assert raw.calls[0][1]['stream'] is True and raw.calls[0][1]['allow_redirects'] is False
    assert transport.metrics()['requests'] == 1 and transport.metrics()['bytes'] == len(response.content)
    transport.close()
    assert raw.closed


def test_rejects_unapproved_redirect_and_oversized_stream():
    with pytest.raises(HostNotAllowedError):
        session([Response(302, headers={'Location': 'https://elsewhere.test/feed'})]).get('https://events.example.test/feed')
    response = Response(body=b'0123456789abc')
    with pytest.raises(TransportLimitError, match='byte'):
        session([response]).get('https://events.example.test/feed')
    assert response.closed


def test_request_page_and_elapsed_budgets_are_enforced():
    redirects = [Response(302, headers={'Location': '/one'}), Response(302, headers={'Location': '/two'})]
    with pytest.raises(TransportLimitError, match='Page'):
        session(redirects).get('https://events.example.test/feed')
    policy = {**POLICY, 'max_requests': 1}
    transport = session([Response(), Response()], policy)
    transport.get('https://events.example.test/one')
    with pytest.raises(TransportLimitError, match='Request'):
        transport.get('https://events.example.test/two')
    clock = Clock()
    policy = {**POLICY, 'min_interval_seconds': 11}
    transport = session([Response(), Response()], policy, clock)
    transport.get('https://events.example.test/one')
    with pytest.raises(TransportLimitError, match='elapsed'):
        transport.get('https://events.example.test/two')


def test_not_modified_exposes_status_and_headers_without_empty_payload():
    with pytest.raises(ConditionalResponseError) as caught:
        session([Response(304, body=b'', headers={'ETag': 'new-tag'})]).get('https://events.example.test/feed')
    assert caught.value.response.status_code == 304
    assert caught.value.response.headers['ETag'] == 'new-tag'
    assert caught.value.response.content == b''


def test_real_request_cannot_outlive_total_deadline_or_leave_worker():
    class SlowHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/ok':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
                return
            time.sleep(.4)
            self.send_response(200)
            self.end_headers()
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), SlowHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        policy = {**POLICY, 'allowed_hosts': ['127.0.0.1'], 'total_timeout_seconds': .1}
        transport = BoundedSession(policy)
        started = time.monotonic()
        with pytest.raises(TransportLimitError, match='elapsed'):
            transport.get('http://127.0.0.1:'+str(server.server_port)+'/slow')
        assert time.monotonic()-started < .35
        assert not [p for p in multiprocessing.active_children() if p.name == 'event-http-request']
    finally:
        server.shutdown()
        server.server_close()


def test_real_worker_returns_a_usable_response():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        transport = BoundedSession({**POLICY, 'allowed_hosts': ['127.0.0.1']})
        response = transport.get('http://127.0.0.1:'+str(server.server_port)+'/ok')
        assert response.status_code == 200 and response.json() == {'ok': True}
        response.raise_for_status()
        assert transport.metrics()['bytes'] == len(b'{"ok":true}')
    finally:
        server.shutdown()
        server.server_close()

"""Bounded, requests-compatible HTTP transport for permitted event sources.

The adapter owns parsing and freshness decisions.  This module only makes a
small, explicitly configured sequence of HTTP requests and retains bodies in
memory for the duration of that request.
"""

from __future__ import annotations

import math
import multiprocessing
import time
from threading import RLock
from urllib.parse import urljoin, urlparse

import requests


def _worker_fetch(send, url, params, headers, timeout, byte_limit):
    """Perform one real request in a process the caller can terminate."""
    response = None
    try:
        session = requests.Session()
        session.headers.update(headers)
        response = session.get(url, params=params, timeout=timeout, stream=True, allow_redirects=False)
        body = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            body.extend(chunk)
            if len(body) > byte_limit:
                send.send({'error': 'bytes'})
                return
        send.send({'status': response.status_code, 'headers': dict(response.headers),
                   'url': response.url, 'reason': response.reason, 'encoding': response.encoding,
                   'body': bytes(body)})
    except Exception as exc:
        send.send({'error': 'request', 'kind': type(exc).__name__})
    finally:
        if response is not None:
            response.close()
        send.close()


class TransportLimitError(RuntimeError):
    """A source exceeded its approved network budget."""


class HostNotAllowedError(ValueError):
    """A request or redirect did not target an approved host."""


class ConditionalResponseError(RuntimeError):
    """A conditional request received 304, which cannot renew freshness."""

    def __init__(self, response):
        super().__init__('Conditional request returned 304; source must fetch a fresh payload')
        self.response = response


class BoundedSession:
    """A sequential Session with host, rate, elapsed-time and body-size limits.

    ``network`` uses ``allowed_hosts``, ``max_requests``, ``max_pages``,
    ``max_bytes``, ``min_interval_seconds``, ``connect_timeout_seconds``,
    ``read_timeout_seconds`` and ``total_timeout_seconds``.  A caller may add
    source headers through the normal ``headers.update`` interface.
    """

    def __init__(self, network, session=None, *, clock=time.monotonic, sleep=time.sleep):
        required = ('allowed_hosts', 'max_requests', 'max_pages', 'max_bytes',
                    'min_interval_seconds', 'connect_timeout_seconds',
                    'read_timeout_seconds', 'total_timeout_seconds')
        missing = [key for key in required if key not in network]
        if missing:
            raise ValueError('Network policy missing: '+', '.join(missing))
        self._hosts = {str(host).lower() for host in network['allowed_hosts']}
        if not self._hosts:
            raise ValueError('Network policy requires allowed_hosts')
        self._max_requests = self._positive(network['max_requests'], 'max_requests', integer=True)
        self._max_pages = self._positive(network['max_pages'], 'max_pages', integer=True)
        self._max_bytes = self._positive(network['max_bytes'], 'max_bytes', integer=True)
        self._interval = self._nonnegative(network['min_interval_seconds'], 'min_interval_seconds')
        self._connect_timeout = self._positive(network['connect_timeout_seconds'], 'connect_timeout_seconds')
        self._read_timeout = self._positive(network['read_timeout_seconds'], 'read_timeout_seconds')
        self._total_timeout = self._positive(network['total_timeout_seconds'], 'total_timeout_seconds')
        self._session = session or requests.Session()
        self._worker_mode = session is None
        self.headers = self._session.headers
        self.headers.update(network.get('headers', {}))
        self._clock, self._sleep, self._lock = clock, sleep, RLock()
        self._started = clock()
        self._last_request = None
        self._requests = self._pages = self._bytes = 0

    @staticmethod
    def _positive(value, name, integer=False):
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0 or (integer and int(value) != value):
            raise ValueError(name+' must be positive')
        return int(value) if integer else float(value)

    @staticmethod
    def _nonnegative(value, name):
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
            raise ValueError(name+' must be non-negative')
        return float(value)

    def _elapsed(self):
        return self._clock()-self._started

    def _check_time(self):
        if self._elapsed() >= self._total_timeout:
            raise TransportLimitError('Total elapsed-time budget exceeded')

    def _approved_url(self, url):
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.hostname.lower() not in self._hosts:
            raise HostNotAllowedError('URL host is not approved')
        return url

    def _timeout(self, supplied):
        if supplied is None:
            return self._connect_timeout, self._read_timeout
        if isinstance(supplied, (int, float)):
            supplied = (supplied, supplied)
        if not isinstance(supplied, tuple) or len(supplied) != 2:
            raise ValueError('timeout must be a number or (connect, read) pair')
        try:
            connect, read = float(supplied[0]), float(supplied[1])
        except (TypeError, ValueError) as exc:
            raise ValueError('timeout must be positive') from exc
        if not math.isfinite(connect) or not math.isfinite(read) or connect <= 0 or read <= 0:
            raise ValueError('timeout must be positive')
        return min(connect, self._connect_timeout), min(read, self._read_timeout)

    def _send(self, url, params, timeout):
        self._check_time()
        if self._requests >= self._max_requests:
            raise TransportLimitError('Request budget exceeded')
        if self._pages >= self._max_pages:
            raise TransportLimitError('Page budget exceeded')
        if self._last_request is not None:
            delay = self._interval-(self._clock()-self._last_request)
            if delay > 0:
                self._sleep(delay)
        self._check_time()
        self._requests += 1
        self._pages += 1
        self._last_request = self._clock()
        remaining = self._total_timeout-self._elapsed()
        bounded_timeout = min(timeout[0], remaining), min(timeout[1], remaining)
        if self._worker_mode:
            return self._worker_request(url, params, bounded_timeout, remaining)
        return self._session.get(url, params=params, timeout=bounded_timeout, stream=True, allow_redirects=False)

    def _worker_request(self, url, params, timeout, remaining):
        receive, send = multiprocessing.get_context('spawn').Pipe(duplex=False)
        process = multiprocessing.get_context('spawn').Process(
            target=_worker_fetch, args=(send, url, params, dict(self.headers), timeout,
                                        self._max_bytes-self._bytes), name='event-http-request')
        process.start()
        send.close()
        payload = None
        try:
            remaining = min(remaining, self._total_timeout-self._elapsed())
            if remaining <= 0:
                process.terminate()
                raise TransportLimitError('Total elapsed-time budget exceeded')
            if not receive.poll(remaining):
                process.terminate()
                raise TransportLimitError('Total elapsed-time budget exceeded')
            payload = receive.recv()
        finally:
            receive.close()
            process.join(timeout=.2)
            if process.is_alive():
                process.terminate()
                process.join()
        self._check_time()
        if payload is None:
            raise requests.exceptions.RequestException('HTTP worker ended without a response')
        if payload.get('error') == 'bytes':
            raise TransportLimitError('Response-byte budget exceeded')
        if payload.get('error'):
            raise requests.exceptions.RequestException('HTTP worker failed: '+payload['kind'])
        self._bytes += len(payload['body'])
        response = requests.Response()
        response.status_code = payload['status']
        response.headers = requests.structures.CaseInsensitiveDict(payload['headers'])
        response.url, response.reason, response.encoding, response._content = (
            payload['url'], payload['reason'], payload['encoding'], payload['body'])
        response._content_consumed = True
        response._adventour_materialized = True
        return response

    def _materialize(self, raw):
        chunks = []
        for chunk in raw.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            self._check_time()
            self._bytes += len(chunk)
            if self._bytes > self._max_bytes:
                raise TransportLimitError('Response-byte budget exceeded')
            chunks.append(chunk)
        self._check_time()
        response = requests.Response()
        response.status_code = raw.status_code
        response.headers = requests.structures.CaseInsensitiveDict(raw.headers)
        response.url = getattr(raw, 'url', '')
        response.reason = getattr(raw, 'reason', None)
        response.encoding = getattr(raw, 'encoding', None)
        response._content = b''.join(chunks)
        return response

    def get(self, url, params=None, timeout=None):
        """Fetch one approved URL, following only approved redirects sequentially."""
        with self._lock:
            current, params, pages = self._approved_url(url), params, 0
            effective_timeout = self._timeout(timeout)
            while True:
                if pages >= self._max_pages:
                    raise TransportLimitError('Page budget exceeded')
                raw = self._send(current, params, effective_timeout)
                pages += 1
                close = getattr(raw, 'close', None)
                try:
                    response = raw if getattr(raw, '_adventour_materialized', False) else self._materialize(raw)
                finally:
                    if close:
                        close()
                if raw.is_redirect or raw.is_permanent_redirect:
                    location = raw.headers.get('Location')
                    if not location:
                        return response
                    current = self._approved_url(urljoin(current, location))
                    params = None
                    continue
                if response.status_code == 304:
                    raise ConditionalResponseError(response)
                return response

    def metrics(self):
        return {'requests': self._requests, 'bytes': self._bytes,
                'elapsed_seconds': self._elapsed()}

    @property
    def counters(self):
        return self.metrics()

    def close(self):
        self._session.close()

"""Bounded discovery of first-party Event JSON-LD pages.

This module is deliberately lead-only.  It never writes provider content or
admits a source to the registry; callers must apply the normal permission and
retention checks before publishing facts.
"""
import json
import re
from urllib.parse import urljoin, urlparse, urlunparse


def canonical(url):
    p = urlparse(url)
    return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path or '/', '', p.query, ''))


def _nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values(): yield from _nodes(child)
    elif isinstance(value, list):
        for child in value: yield from _nodes(child)


def _events(page):
    found = []
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page,
                            re.I | re.S):
        try: value = json.loads(block)
        except (ValueError, TypeError): continue
        found.extend(n for n in _nodes(value)
                     if str(n.get('@type', '')).split('/')[-1] == 'Event')
    return found


def _candidate(node, url, source, window):
    start = node.get('startDate')
    location = node.get('location') or {}
    address = location.get('address') if isinstance(location, dict) else {}
    locality = ' '.join(str(address.get(k, '')) for k in ('addressLocality', 'addressRegion')).lower()
    terms = [str(t).lower() for t in source.get('city_terms', [])]
    local = any(term in locality for term in terms) if terms else False
    dated = isinstance(start, str) and 'T' in start
    in_window = dated and window['start'] <= start[:10] < window['end_exclusive']
    if not (local and in_window): return None
    return {'name': str(node.get('name', ''))[:500], 'source_url': url,
            'start': start, 'end': node.get('endDate'), 'locality': locality}


def _links(page, base):
    return [canonical(urljoin(base, href)) for href in
            re.findall(r'href=["\']([^"\']+)', page, re.I)]


def discover(session, roots, *, source, window, max_pages=10, max_bytes=2_000_000):
    """Fetch same-host calendar/detail pages and return reviewable candidates.

    ``session`` is the existing bounded HTTP session.  Roots are operator
    supplied URLs.  External links are returned as leads only and are never
    fetched.  A page is accepted only when the existing calendar pilot proves
    an explicit event time and matching locality.
    """
    queue = [canonical(url) for url in roots]
    seen, records, external = set(), [], []
    bytes_read = 0
    while queue and len(seen) < max_pages:
        url = queue.pop(0)
        if url in seen:
            continue
        parsed = urlparse(url)
        if parsed.scheme != 'https' or not parsed.hostname:
            continue
        seen.add(url)
        response = session.get(url)
        body = response.text
        bytes_read += len(response.content)
        if bytes_read > max_bytes:
            break
        for node in _events(body):
            row = _candidate(node, url, source, window)
            if row:
                records.append(row)
        for link in _links(body, url):
            if urlparse(link).netloc == parsed.netloc:
                if link not in seen and link not in queue:
                    queue.append(link)
            elif link not in external:
                external.append(link)
    return {
        'records': records,
        'pages': len(seen),
        'bytes': bytes_read,
        'external_leads': external,
        'status': 'budget_exhausted' if queue and len(seen) >= max_pages else 'complete',
    }

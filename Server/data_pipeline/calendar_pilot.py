"""Repeatable bounded calendar traversal; offline diagnostics, no database writes.

Retains factual event candidates and evidence flags, never source prose/images.
Candidates require review; parsed dates and public pages do not prove attendance.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlparse, urlunparse
from zoneinfo import ZoneInfo

import requests
from .website_audit import Fetcher, public_url
from .extraction_spike import SCRIPT_RE, LINK_RE, visible_text


class PilotFetcher(Fetcher):
    """Use existing robots policy with bounded response size and host delays."""
    def request(self, url):
        if not public_url(url):
            raise ValueError('unsupported_or_nonpublic_url')
        host = urlparse(url).netloc
        time.sleep(max(0, 1.5 - (time.monotonic() - self.last.get(host, 0))))
        self.last[host] = time.monotonic()
        self.requests += 1
        response = self.session.get(url, timeout=10, allow_redirects=False, stream=True)
        parts, size = [], 0
        try:
            for part in response.iter_content(65536):
                size += len(part)
                self.bytes += len(part)
                if size > 3_000_000:
                    raise ValueError('response_size_limit')
                parts.append(part)
            response._content = b''.join(parts)
            response._content_consumed = True
            return response
        finally:
            response.close()


def canonical(url):
    p = urlparse(html.unescape(url))
    return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path or '/', '', p.query, ''))


def nodes(value, depth=0):
    if depth > 40:
        return
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child, depth + 1)


def event_nodes(page):
    found, errors = [], 0
    for block in SCRIPT_RE.findall(page):
        try:
            value = json.loads(block)
        except (ValueError, TypeError):
            errors += 1
            continue
        for node in nodes(value):
            types = node.get('@type', [])
            if not isinstance(types, list):
                types = [types]
            if any(str(t).split('/')[-1].endswith('Event') for t in types):
                found.append(node)
    return found, errors


def strings(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return ' '.join(strings(v) for k, v in value.items() if k not in {'image', 'telephone', 'email', 'url'})
    if isinstance(value, list):
        return ' '.join(strings(v) for v in value)
    return ''


def timestamp(value, zone):
    if not isinstance(value, str) or 'T' not in value:
        return None, 'missing_or_date_only'
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None, 'invalid_time'
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=zone), 'assumed_source_timezone'
    return parsed.astimezone(zone), None


def candidate(node, url, source, window):
    zone = ZoneInfo(window['timezone'])
    start, start_note = timestamp(node.get('startDate'), zone)
    end, end_note = timestamp(node.get('endDate'), zone)
    low = datetime.fromisoformat(window['start']).replace(tzinfo=zone)
    high = datetime.fromisoformat(window['end_exclusive']).replace(tzinfo=zone)
    location = strings(node.get('location')).lower()
    region = any(re.search(r'\b' + re.escape(city) + r'\b', location) for city in source['city_terms'])
    text = html.unescape(visible_text(strings(node.get('description'))))
    title = html.unescape(strings(node.get('name')))[:200]
    restricted = bool(re.search(r'\b(private event|invitation only|members? only|students? only|ages? \d|\d{2}\+)\b', title+' '+text, re.I))
    public_phrase = bool(re.search(r'\b(open to (?:the )?public|open invite|everyone (?:is )?welcome|all are welcome)\b', text, re.I))
    cancelled = str(node.get('eventStatus', '')).split('/')[-1] in {'EventCancelled', 'EventPostponed'}
    flags = []
    if start_note:
        flags.append('start_' + start_note)
    if end_note:
        flags.append('end_' + end_note)
    if start and end and end <= start:
        flags.append('invalid_duration')
    if not region:
        flags.append('region_unconfirmed')
    if not public_phrase:
        flags.append('public_access_unconfirmed')
    if restricted:
        flags.append('access_restriction_detected')
    if cancelled:
        flags.append('cancelled_or_postponed')
    overlap = bool(start and start < high and (end > low if end else start >= low))
    if not overlap:
        flags.append('outside_window_or_unknown')
    identity = hashlib.sha256((title.casefold()+'|'+str(start)+'|'+location).encode()).hexdigest()[:20]
    return {'id': identity, 'title': title, 'source_url': url,
            'start_local': start.isoformat() if start else None,
            'end_local': end.isoformat() if end else None,
            'region_evidence': region, 'overlaps_window': overlap,
            'public_phrase_detected': public_phrase, 'restriction_detected': restricted,
            'cancelled_or_postponed': cancelled,
            'coffee_activity_text_signal': bool(re.search(r'\b(coffee|espresso|matcha|latte|cafe|caf\u00e9)\b', title+' '+text, re.I)),
            'flags': flags, 'status': 'review_required',
            'storage_permission': 'not_established', 'precise_venue_verified': False}


def links(page, base):
    same, external = {}, set()
    for href, anchor in LINK_RE.findall(page):
        url = canonical(urljoin(base, href.strip()))
        parsed = urlparse(url)
        if parsed.scheme not in {'http', 'https'}:
            continue
        text = parsed.path + ' ' + visible_text(anchor)
        if not re.search(r'event|calendar|workshop|ticket', text, re.I):
            continue
        if parsed.hostname != urlparse(base).hostname:
            external.add(url)
            continue
        if url == canonical(base) or re.search(r'\.(pdf|jpg|png|ics)$', parsed.path, re.I):
            continue
        # Event-detail paths before collection pages, then URL lexical order.
        priority = 0 if re.search(r'/(?:events?|workshops?)/[^/]+', parsed.path, re.I) else 1
        same[url] = priority
    return sorted(same, key=lambda u: (same[u], u)), sorted(external)


def run_source(source, protocol, fetcher):
    cap = protocol['limits']
    queue, visited, candidates, external = [source['url']], set(), {}, set()
    result = {'id': source['id'], 'region': source['region'], 'seed_url': source['url'],
              'pages': [], 'event_nodes_seen': 0, 'duplicate_nodes': 0,
              'reuse_basis': source['reuse']}
    while queue and len(result['pages']) < cap['pages_per_source']:
        url = queue.pop(0)
        if canonical(url) in visited:
            continue
        visited.add(canonical(url))
        record = {'requested_url': url}
        result['pages'].append(record)
        try:
            response = fetcher.get(url)
            record.update({'status': 'http_'+str(response.status_code), 'resolved_url': response.url})
            visited.add(canonical(response.url))
            if response.status_code != 200:
                continue
            if 'html' not in response.headers.get('Content-Type', ''):
                record['status'] = 'not_html'
                continue
            page = response.text
            found, errors = event_nodes(page)
            next_urls, other_urls = links(page, response.url)
            external.update(other_urls)
            queue.extend(u for u in next_urls if u not in visited and u not in queue)
            text = visible_text(page)
            record.update({'status': 'parsed', 'event_nodes': len(found), 'jsonld_parse_errors': errors,
                           'discovered_same_host_links': len(next_urls),
                           'visible_date_signal': bool(re.search(r'2026|September|October', text, re.I)),
                           'visible_event_signal': bool(re.search(r'event|workshop|calendar', text, re.I))})
            result['event_nodes_seen'] += len(found)
            for node in found:
                row = candidate(node, response.url, source, protocol['window'])
                if row['id'] in candidates:
                    result['duplicate_nodes'] += 1
                elif len(candidates) < cap['event_nodes_per_source']:
                    candidates[row['id']] = row
        except (requests.RequestException, ValueError) as exc:
            record['status'] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
    result['candidates'] = list(candidates.values())
    result['pending_same_host_links'] = len(queue)
    result['candidate_cap_reached'] = len(candidates) >= cap['event_nodes_per_source']
    result['external_leads'] = sorted(external)[:cap['linked_leads_per_source']]
    result['external_leads_total'] = len(external)
    result['counts'] = {'parsed_pages': sum(p['status'] == 'parsed' for p in result['pages']),
                        'unique_retained_candidates': len(candidates),
                        'dated_in_region': sum(c['overlaps_window'] and c['region_evidence'] and not c['cancelled_or_postponed'] and not c['restriction_detected'] and 'invalid_duration' not in c['flags'] for c in candidates.values()),
                        'production_ready': 0}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = args.protocol.read_bytes().replace(b'\r\n', b'\n')
    protocol = json.loads(raw)
    fetcher, started = PilotFetcher(), time.monotonic()
    report = {'version': protocol['version'], 'protocol_sha256': hashlib.sha256(raw).hexdigest(),
              'started_at': datetime.now(timezone.utc).isoformat(), 'sources': [],
              'limitation': 'Factual extraction diagnostics; no acquired source prose, verified attendance, storage permission, ranking quality or production writes.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for source in protocol['sources']:
        result = run_source(source, protocol, fetcher)
        report['sources'].append(result)
        report.update({'requests': fetcher.requests, 'response_bytes': fetcher.bytes,
                       'elapsed_seconds': round(time.monotonic()-started, 2)})
        args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print(json.dumps({'source': source['id'], **result['counts'],
                          'page_statuses': dict(Counter(p['status'] for p in result['pages']))}), flush=True)


if __name__ == '__main__':
    main()

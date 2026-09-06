"""Bounded, robots-aware website experiment. Stores counts/URLs, never page text.

Input is the frozen discovery_audit sample. No production enrichment or closure
suppression occurs. Finding hours in a page is not verification of current hours.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import re
import socket
import time
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from .extraction_spike import SCRIPT_RE, LINK_RE, classify, visible_text, find_subpage

USER_AGENT='AdventourResearch/0.2 (bounded venue website evaluation)'
BLOCKED_HOSTS=('facebook.com','instagram.com','tiktok.com','substack.com','partiful.com','google.com','nextdoor.com')


def public_url(url):
    parsed=urlparse(url)
    if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password:
        return False
    host=parsed.hostname.lower()
    if any(host==b or host.endswith('.'+b) for b in BLOCKED_HOSTS): return False
    try:
        addresses=socket.getaddrinfo(host,parsed.port or (443 if parsed.scheme=='https' else 80))
        return bool(addresses) and all(ipaddress.ip_address(a[4][0]).is_global for a in addresses)
    except (OSError,ValueError): return False


class Fetcher:
    def __init__(self):
        self.session=requests.Session(); self.session.headers['User-Agent']=USER_AGENT
        self.robots={}; self.last={}; self.requests=0; self.bytes=0

    def request(self,url):
        if not public_url(url): raise ValueError('unsupported_or_nonpublic_url')
        host=urlparse(url).netloc
        time.sleep(max(0,1.5-(time.monotonic()-self.last.get(host,0))))
        self.last[host]=time.monotonic(); self.requests+=1
        response=self.session.get(url,timeout=10,allow_redirects=False)
        self.bytes+=len(response.content)
        return response

    def allowed(self,url):
        parsed=urlparse(url); origin=f'{parsed.scheme}://{parsed.netloc}'
        if origin not in self.robots:
            response=self.request(origin+'/robots.txt')
            # Follow a robots redirect only to the same host; uncertainty skips.
            if response.is_redirect:
                target=urljoin(response.url,response.headers.get('Location',''))
                if urlparse(target).hostname != parsed.hostname: return False
                response=self.request(target)
            if response.status_code==404: self.robots[origin]=True
            elif response.status_code==200:
                parser=RobotFileParser(); parser.parse(response.text.splitlines()); self.robots[origin]=parser
            else: self.robots[origin]=False
        policy=self.robots[origin]
        return policy if isinstance(policy,bool) else policy.can_fetch(USER_AGENT,url)

    def get(self,url):
        for _ in range(5):
            if not self.allowed(url): raise ValueError('robots_denied_or_unavailable')
            response=self.request(url)
            if response.is_redirect:
                url=urljoin(url,response.headers['Location']); continue
            return response
        raise ValueError('redirect_limit')


def inspect(page):
    nodes=[]
    def walk(value):
        if isinstance(value,dict):
            nodes.append(value)
            for child in value.values(): walk(child)
        elif isinstance(value,list):
            for child in value: walk(child)
    for block in SCRIPT_RE.findall(page):
        try: walk(json.loads(block))
        except (ValueError,TypeError): pass
    text=visible_text(page)
    events=[n for n in nodes if any(str(t).endswith('Event') for t in
            (n.get('@type',[]) if isinstance(n.get('@type'),list) else [n.get('@type','')]))]
    return {'hours_class':classify(page)[0],
            'structured_hours_nodes':sum(bool(n.get('openingHoursSpecification') or n.get('openingHours')) for n in nodes),
            'event_nodes':len(events),'dated_event_nodes':sum(bool(n.get('startDate')) for n in events),
            'public_access_phrase':bool(re.search(r'\bopen to the public\b',text,re.I)),
            'explicit_closure_phrase':bool(re.search(r'\b(permanently closed|closed permanently|closed for good)\b',text,re.I)),
            'visible_characters':len(text)}


def audit_one(record,fetcher):
    result={k:record[k] for k in ('id','name','metro')}
    if 'human_note' in record: result['human_note']=record['human_note']
    urls=record.get('websites') or []
    if not urls: return {**result,'outcome':'no_website','pages':[]}, None
    result['requested_url']=urls[0]; result['pages']=[]
    render=None
    try:
        response=fetcher.get(urls[0])
        if response.status_code!=200: return {**result,'outcome':f'http_{response.status_code}'},None
        content_type=response.headers.get('Content-Type','')
        if 'html' not in content_type: return {**result,'outcome':'not_html'},None
        home=response.url; pages=[(home,response.text)]
        sub=find_subpage(response.text,home)
        candidates=[sub] if sub else []
        for href,anchor in LINK_RE.findall(response.text):
            target=urljoin(home,href)
            if urlparse(target).netloc==urlparse(home).netloc and re.search('event|calendar',target+' '+visible_text(anchor),re.I):
                candidates.append(target); break
        for target in list(dict.fromkeys(candidates))[:2]:
            try:
                page=fetcher.get(target)
                if page.status_code==200 and urlparse(page.url).netloc==urlparse(home).netloc:
                    pages.append((page.url,page.text))
                else: result.setdefault('subpage_failures',[]).append({'url':target,'status':page.status_code})
            except (requests.RequestException,ValueError) as exc:
                result.setdefault('subpage_failures',[]).append({'url':target,'error':type(exc).__name__})
        for url,page in pages:
            facts=inspect(page); result['pages'].append({'url':url,**facts})
            if facts['hours_class']=='js_rendered' and render is None: render=url
        result['outcome']='readable'; result['production_storage']='not_authorized_by_this_experiment'
    except (requests.RequestException,ValueError) as exc:
        result['outcome']=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
    return result,render


def render_page(url,fetcher):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        context=browser.new_context(user_agent=USER_AGENT)
        page=context.new_page(); requests_seen=0
        def route(request):
            nonlocal requests_seen
            requests_seen+=1
            if requests_seen>100 or request.request.resource_type in {'image','font','media'} or \
                    not public_url(request.request.url):
                request.abort(); return
            if request.request.is_navigation_request() and not fetcher.allowed(request.request.url):
                request.abort(); return
            request.continue_()
        page.route('**/*',route)
        try:
            response=page.goto(url,wait_until='domcontentloaded',timeout=20000)
            if response is None or response.status!=200: return {'outcome':'render_http_error'}
            page.wait_for_timeout(2500)
            return {'outcome':'rendered','url':page.url,'requests_seen':requests_seen,**inspect(page.content())}
        finally: context.close(); browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); sample=json.loads(args.sample.read_text(encoding='utf-8'))
    fetcher=Fetcher(); started=time.monotonic(); render_count=0
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'sample_file':str(args.sample),
            'limitation':'Counts are acquisition diagnostics, not verified hours, event coverage or closure predictions.',
            'website_sample':[],'closed_sample':[]}
    for group in ('website_sample','closed_sample'):
        for record in sample[group]:
            result,render=audit_one(record,fetcher)
            if render and render_count<6:
                render_count+=1
                try: result['render']=render_page(render,fetcher)
                except Exception as exc: result['render']={'outcome':type(exc).__name__}
            report[group].append(result)
            report.update({'requests':fetcher.requests,'response_bytes':fetcher.bytes,'elapsed_seconds':round(time.monotonic()-started,1)})
            args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(f'{group} {len(report[group])}/{len(sample[group])}: {result["outcome"]}',flush=True)
    print(json.dumps({'outcomes':dict(Counter(r['outcome'] for r in report['website_sample'])),
                      'render_attempts':render_count,'requests':fetcher.requests,'seconds':report['elapsed_seconds']}))

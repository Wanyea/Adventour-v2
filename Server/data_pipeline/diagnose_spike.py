"""Is the spike measuring the web, or measuring my crawler?

Three suspicions from the first run:
  - tier1_jsonld = 0/21. schema.org markup is common; zero is implausible.
  - robots_disallowed = 24%. RobotFileParser treats a 401/403 robots.txt as
    deny-all, and CDNs commonly 403 unknown bots -- so this may be UA blocking.
  - fetch_failed = 22%. Same suspicion.

For a handful of known sites, report the raw facts separately.
"""

import re
import urllib.robotparser
from urllib.parse import urlparse

import requests

BOT_UA = "AdventourBot/0.1 (+place hours collection; contact: set-me@example.com)"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

SITES = [
    "https://theislandgrille.com",
    "http://www.thaibythai.com",
    "http://www.lacreperiekafe.com/",
    "http://Coquinacoastbrewingcompany.com/",
    "https://yescoffeeco.square.site/",
    "https://www.epictheatres.com/",
    "https://www.marineland.net/",
    "https://captainsbbq.com/",
]


def robots_status(url, ua):
    parsed = urlparse(url)
    host = f"{parsed.scheme}://{parsed.netloc}"
    try:
        resp = requests.get(f"{host}/robots.txt", timeout=10, headers={"User-Agent": ua})
        code = resp.status_code
    except Exception as exc:
        return f"unreachable({type(exc).__name__})", None
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(resp.text.splitlines() if code == 200 else [])
    allowed = parser.can_fetch(ua, url) if code == 200 else "n/a"
    return f"HTTP {code}", allowed


for site in SITES:
    print(f"\n{'='*70}\n{site}")
    for label, ua in (("bot-UA", BOT_UA), ("browser-UA", BROWSER_UA)):
        code, allowed = robots_status(site, ua)
        print(f"  robots.txt [{label:<10}] {code:<24} can_fetch={allowed}")

    for label, ua in (("bot-UA", BOT_UA), ("browser-UA", BROWSER_UA)):
        try:
            resp = requests.get(site, timeout=12, headers={"User-Agent": ua}, allow_redirects=True)
            html = resp.text
            has_ldjson = "ld+json" in html.lower()
            # Does the word appear ANYWHERE in raw HTML, regardless of my regex?
            has_oh = bool(re.search(r"openingHours", html, re.IGNORECASE))
            n_scripts = len(re.findall(r"ld\+json", html, re.IGNORECASE))
            print(f"  page       [{label:<10}] HTTP {resp.status_code}  bytes={len(html):>7,}  "
                  f"ld+json={has_ldjson}({n_scripts})  openingHours={has_oh}")
        except Exception as exc:
            print(f"  page       [{label:<10}] {type(exc).__name__}: {str(exc)[:60]}")

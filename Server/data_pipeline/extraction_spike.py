"""Extraction spike: how many business sites publish machine-readable hours?

Samples independent places from the seed, fetches each site once, and measures:
  Tier 1  schema.org JSON-LD with openingHoursSpecification -> exact parse, free
  Tier 2  hours visible in page text but not structured    -> needs model extraction
  Tier 3  no hours found                                    -> falls back to category priors

That split is what sets the real cost of the hours seed.

Crawl etiquette: robots.txt honoured per host, one request per host, sequential
with a delay, short timeout, identifying User-Agent. Read-only.
"""

import argparse
import json
import re
import time
import urllib.robotparser
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin, urlparse

import duckdb
import requests

# Set a contact address here before running any crawl larger than this spike --
# it is what a site owner will look for if our traffic bothers them.
USER_AGENT = "AdventourBot/0.1 (+place hours collection; contact: set-me@example.com)"

DELAY_SECONDS = 1.5
TIMEOUT = 10

HERE = Path(__file__).resolve().parent / "data"
PLACES = f"read_parquet('{(HERE / 'seed_places.parquet').as_posix()}')"
NAMES = f"read_parquet('{(HERE / 'florida_names.parquet').as_posix()}')"

RELEVANT = ("food_and_drink", "arts_and_entertainment", "cultural_and_historic", "sports_and_recreation")
EXCLUDED = ("christian_place_of_worship", "place_of_worship", "cemetery", "school",
            "gym", "fitness_studio", "sport_or_fitness_facility", "swimming_pool")

SCRIPT_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
TAG_RE = re.compile(r"<(script|style)\b.*?</\1>", re.DOTALL | re.IGNORECASE)
# Day name near a clock time -- crude, but enough to tell "hours are on this page"
# from "this page has no hours at all".
TEXT_HOURS_RE = re.compile(
    r"(mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?\s*[-–—:]?\s*"
    r"(?:[a-z]*\s*)?\d{1,2}(:\d{2})?\s*(am|pm|a\.m|p\.m|:00)",
    re.IGNORECASE,
)


def sample_places(limit, metro):
    con = duckdb.connect()
    con.execute(f"CREATE VIEW name_freq AS SELECT name_norm, count(*) fl_count FROM {NAMES} GROUP BY 1")
    metro_clause = f"AND p.metro = '{metro}'" if metro != "both" else ""
    return con.execute(
        f"""
        SELECT p.name, p.basic_category, p.websites[1] AS site, p.metro
        FROM {PLACES} p
        LEFT JOIN name_freq f
          ON lower(trim(regexp_replace(p.name,
             '\\s+(at|of|in|-|–|—|@|\\|)\\s+.*$|\\s+\\(.*\\)$', '', 'i'))) = f.name_norm
        WHERE p.taxonomy_hierarchy[1] IN {RELEVANT}
          AND coalesce(p.basic_category,'') NOT IN {EXCLUDED}
          AND coalesce(p.operating_status,'open') <> 'closed'
          AND p.brand_wikidata IS NULL
          AND coalesce(f.fl_count, 1) < 3
          AND p.websites IS NOT NULL AND len(p.websites) > 0
          {metro_clause}
        ORDER BY hash(p.id)
        LIMIT {limit}
        """
    ).fetchall()


def walk_for_hours(node):
    """JSON-LD nests arbitrarily -- objects, arrays, @graph. Walk all of it."""
    found = []
    if isinstance(node, dict):
        for key in ("openingHoursSpecification", "openingHours"):
            if node.get(key):
                found.append(node[key])
        for value in node.values():
            found.extend(walk_for_hours(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(walk_for_hours(item))
    return found


def robots_allows(url, cache):
    """Fetch robots.txt with requests, not urllib.

    RobotFileParser.read() uses urllib, whose default User-Agent is widely 403'd
    by CDNs -- and the parser treats a 403 as deny-all. That produced a fake 24%
    'disallowed' rate on the first run. Only an explicit Disallow blocks us; a
    missing or unreachable robots.txt means allowed, per convention.
    """
    parsed = urlparse(url)
    host = f"{parsed.scheme}://{parsed.netloc}"
    if host not in cache:
        parser = None
        try:
            resp = requests.get(
                f"{host}/robots.txt", timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}
            )
            if resp.status_code == 200 and resp.text.strip():
                parser = urllib.robotparser.RobotFileParser()
                parser.parse(resp.text.splitlines())
        except requests.exceptions.RequestException:
            parser = None
        cache[host] = parser
    parser = cache[host]
    if parser is None:
        return True
    try:
        return parser.can_fetch(USER_AGENT, url)
    except Exception:
        return True


# A Wix/Squarespace/React shell ships almost no server-rendered text -- the hours
# exist only after JS runs, so a static fetch cannot see them.
JS_SHELL_MARKERS = ("__NEXT_DATA__", "id=\"root\"", "id=\"app\"", "wix-", "squarespace")


def visible_text(html):
    text = TAG_RE.sub(" ", html)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


LINK_RE = re.compile(r'<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', re.DOTALL | re.IGNORECASE)

# Ordered by how likely the page is to carry hours. Restaurants put them on a
# contact or hours page far more often than on the homepage.
SUBPAGE_KEYWORDS = (
    ("hour", 10), ("visit", 7), ("contact", 6), ("location", 5),
    ("about", 4), ("info", 3), ("menu", 2), ("plan-your", 6),
)


def find_subpage(html, base_url):
    """Pick the single internal link most likely to carry opening hours."""
    base = urlparse(base_url)
    best, best_score = None, 0
    for href, anchor in LINK_RE.findall(html):
        target = urljoin(base_url, href.strip())
        parsed = urlparse(target)
        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.netloc != base.netloc:  # same host only
            continue
        if parsed.path.rstrip("/") == base.path.rstrip("/"):
            continue
        haystack = f"{parsed.path.lower()} {visible_text(anchor).lower()}"
        score = sum(weight for kw, weight in SUBPAGE_KEYWORDS if kw in haystack)
        if score > best_score:
            best, best_score = target, score
    return best


def classify(html):
    has_ldjson = False
    for block in SCRIPT_RE.findall(html):
        has_ldjson = True
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        hours = walk_for_hours(data)
        if hours:
            return "tier1_jsonld", hours[0]

    text = visible_text(html)
    if TEXT_HOURS_RE.search(text):
        return ("tier2_text_ldjson_no_hours" if has_ldjson else "tier2_text"), None

    # Distinguish "no hours published" from "we could not see the page at all".
    if len(text) < 500 and any(m in html for m in JS_SHELL_MARKERS):
        return "js_rendered", None
    if len(text) < 200:
        return "js_rendered", None
    return "tier3_none", None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--metro", default="palm_coast", choices=["palm_coast", "orlando", "both"])
    ap.add_argument("--follow", action="store_true",
                    help="when the homepage yields no hours, follow one likely internal link")
    args = ap.parse_args()

    places = sample_places(args.limit, args.metro)
    print(f"sampling {len(places)} independent places ({args.metro})\n")

    counts = Counter()
    robots_cache = {}
    examples = []

    for i, (name, category, site, metro) in enumerate(places, 1):
        label = f"[{i:>3}/{len(places)}] {name[:38]:<38}"
        if not robots_allows(site, robots_cache):
            counts["robots_disallowed"] += 1
            print(f"{label} robots: disallowed")
            continue
        try:
            resp = requests.get(
                site, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, allow_redirects=True
            )
            if resp.status_code != 200:
                counts[f"http_{resp.status_code}"] += 1
                print(f"{label} HTTP {resp.status_code}")
                continue
            tier, sample = classify(resp.text)

            # Homepage gave nothing -- try the one internal page most likely to
            # carry hours. This is the 49% bucket from the homepage-only run.
            followed = ""
            if args.follow and tier in ("tier3_none", "js_rendered"):
                sub = find_subpage(resp.text, resp.url)
                if sub and robots_allows(sub, robots_cache):
                    time.sleep(DELAY_SECONDS)
                    try:
                        sub_resp = requests.get(
                            sub, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT},
                            allow_redirects=True,
                        )
                        if sub_resp.status_code == 200:
                            sub_tier, sub_sample = classify(sub_resp.text)
                            counts["subpage_attempted"] += 1
                            if sub_tier.startswith("tier1") or sub_tier.startswith("tier2"):
                                counts["subpage_rescued"] += 1
                                tier, sample = sub_tier, sub_sample
                                followed = f"  <- {urlparse(sub).path[:28]}"
                    except requests.exceptions.RequestException:
                        pass

            counts[tier] += 1
            print(f"{label} {tier}{followed}", flush=True)
            if tier == "tier1_jsonld" and len(examples) < 3:
                examples.append((name, sample))
        except requests.exceptions.SSLError:
            counts["ssl_error"] += 1
            print(f"{label} SSL error")
        except requests.exceptions.RequestException as exc:
            counts["fetch_failed"] += 1
            print(f"{label} failed: {type(exc).__name__}")
        time.sleep(DELAY_SECONDS)

    # These two are bookkeeping about the follow step, not per-site outcomes --
    # counting them in the total would corrupt every percentage below.
    BOOKKEEPING = ("subpage_attempted", "subpage_rescued")
    total = sum(n for k, n in counts.items() if k not in BOOKKEEPING)
    t1 = counts["tier1_jsonld"]
    t2 = counts["tier2_text"] + counts["tier2_text_ldjson_no_hours"]
    t3 = counts["tier3_none"]
    js = counts["js_rendered"]
    fetched = t1 + t2 + t3 + js

    print(f"\n{'='*62}\nRESULTS  (n={total}{', subpage following ON' if args.follow else ''})\n{'='*62}")
    for key, n in counts.most_common():
        if key in BOOKKEEPING:
            continue
        print(f"  {key:<30}{n:>5}   {100.0*n/total:>5.1f}%")

    if args.follow and counts["subpage_attempted"]:
        att, res = counts["subpage_attempted"], counts["subpage_rescued"]
        print(f"\n  subpage followed on {att} dead homepages, rescued {res} "
              f"({100.0*res/att:.1f}% of attempts)")

    if fetched:
        print(f"\nOf {fetched} pages we successfully fetched:")
        print(f"  structured hours, free to parse : {t1:>4}  {100.0*t1/fetched:>5.1f}%")
        print(f"  hours in text, needs a model    : {t2:>4}  {100.0*t2/fetched:>5.1f}%")
        print(f"  fetched but no hours in HTML    : {t3:>4}  {100.0*t3/fetched:>5.1f}%")
        print(f"  JS-rendered, static fetch blind : {js:>4}  {100.0*js/fetched:>5.1f}%")
        print(f"\n  hours obtainable statically     : {100.0*(t1+t2)/fetched:>5.1f}% of fetched")
        print(f"  would need a headless browser   : {100.0*js/fetched:>5.1f}% of fetched")
    print(f"  fetch success rate              : {100.0*fetched/total:>5.1f}% of sampled")

    for name, sample in examples:
        print(f"\n--- structured hours: {name} ---")
        print(json.dumps(sample, indent=2)[:400])


if __name__ == "__main__":
    main()

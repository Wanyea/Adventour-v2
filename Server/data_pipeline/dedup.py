"""Entity resolution over the seed index.

The problem, from Gate 9: `Washington Oaks Gardens State Park` exists as six
records whose coordinates span 21 km, and ~13% of non-chain KEEP records sit in
exact-name duplicate clusters. A deck would deal the same place repeatedly.

The tension that shapes the design: Washington Oaks' duplicates are 21 km apart,
so tight spatial blocking would miss them -- but two Subways 200 m apart are
genuinely two places, so loose spatial matching would merge distinct venues.
Resolution: **name distinctiveness sets the distance tolerance.**

A first version of this file failed its dry run in three ways, all fixed here and
recorded because each is a standard entity-resolution trap:

1. **Unstable blocking.** Blocking on the alphabetically-first token put
   "Washington Oaks State Park" (first token `oaks`) and "Washington Oaks Gardens
   State Park" (first token `gardens`) in different blocks, so the very case this
   was built for was never compared. Now blocks on the *rarest* token, which does
   not move when a word is added.

2. **No IDF.** Plain Jaccard treats `park` and `washington` as equally
   informative, so "Avalon Park", "Avalon Park Lake" and "Century Park" looked
   alike. Tokens are now weighted by inverse document frequency.

3. **Transitive over-merge.** Union-find is single-linkage: if a record named
   merely "Sports Bar" exists, every `X Sports Bar` links through it and 14
   unrelated bars collapse into one. Clusters are now validated against their
   survivor and anything not directly similar is split back out.
"""

import math
import re
from collections import Counter, defaultdict

STOPWORDS = {"at", "the", "of", "and", "in", "on", "a", "an", "&", "florida", "fl",
             "llc", "inc", "co", "corp"}

TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokens(name):
    t = {w for w in TOKEN_RE.findall((name or "").lower()) if w not in STOPWORDS and len(w) > 1}
    return t or {(name or "").lower().strip()}


def build_idf(rows):
    """Inverse document frequency per token, over the whole index.

    This is what stops `park`, `bar` and `grill` from driving matches. In Orlando
    `park` appears in hundreds of names and carries almost no information;
    `washington` appears in a handful and carries most of it.
    """
    df = Counter()
    for r in rows:
        for t in tokens(r["name"]):
            df[t] += 1
    n = max(len(rows), 1)
    return {t: math.log(n / c) for t, c in df.items()}, math.log(n), df


def similarity(a, b, idf, default_idf):
    """IDF-weighted Jaccard over significant tokens."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    inter = sum(idf.get(t, default_idf) for t in ta & tb)
    union = sum(idf.get(t, default_idf) for t in ta | tb)
    return inter / union if union else 0.0


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def distance_tolerance_m(row, df, chain_class):
    """A distinctive name may merge across a metro; a chain name must be same-building.

    Distinctiveness comes from corpus document frequency, NOT from `fl_name_count`.
    That was a self-defeating bug: duplicate records inflate their own statewide
    name count, which tightened the tolerance and blocked the very merge that
    would have removed them. Washington Oaks merged 2 of 6 records for exactly
    this reason.
    """
    if chain_class == "chain":
        return 120.0
    t = tokens(row["name"])
    rarest_df = min((df.get(w, 1) for w in t), default=1)
    if rarest_df <= 3:
        return 30_000.0
    if rarest_df <= 12:
        return 5_000.0
    if rarest_df <= 40:
        return 1_000.0
    return 250.0


NAME_THRESHOLD = 0.65
NEAR_EXACT = 0.90
SINGLETON_NEAR_EXACT = 0.75
NEAR_EXACT_TOLERANCE_M = 60_000.0

# The long-distance merge is restricted to categories that can only exist once.
#
# Without this, "Sus Hi Eatstation" merged 7 records across 17 km and "Mecatos
# Bakery" merged 6 across 23 km -- those are real multi-location businesses, and
# collapsing them destroys exactly the `regional` places the Palm Coast labels
# showed are gems. A state park does not have seven branches; a restaurant does.
SINGLETON_CATEGORIES = {
    "park", "national_park", "state_park", "nature_preserve", "garden",
    "botanical_garden", "beach", "recreational_trail_or_path", "hiking_trail",
    "museum", "historic_site", "monument", "landmark", "zoo", "aquarium",
    "amusement_park", "theme_park", "water_park", "lake", "island",
    "scenic_lookout", "skate_park", "campground", "marina",
}


class Union:
    def __init__(self, ids):
        self.parent = {i: i for i in ids}

    def find(self, i):
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def rarest_token(name, idf, default_idf):
    """Blocking key: the most informative token in the name.

    Stable under word insertion, unlike alphabetical-first ordering.
    """
    t = tokens(name)
    return max(t, key=lambda w: (idf.get(w, default_idf), w)) if t else ""


def pair_matches(a, b, idf, default_idf, df):
    sim = similarity(a["name"], b["name"], idf, default_idf)
    if sim < NAME_THRESHOLD:
        return False
    tol = min(distance_tolerance_m(a, df, a["chain_class"]),
              distance_tolerance_m(b, df, b["chain_class"]))
    singular = ((a.get("basic_category") or "") in SINGLETON_CATEGORIES
                and (b.get("basic_category") or "") in SINGLETON_CATEGORIES)
    # A lower bar for singular categories: a park cannot have branches, so
    # "Washington Oaks State Park" vs "Washington Oaks Gardens State Park"
    # (sim 0.77) is one place, while the same gap between two restaurants is not.
    bar = SINGLETON_NEAR_EXACT if singular else NEAR_EXACT
    if (sim >= bar and singular
            and a["chain_class"] != "chain" and b["chain_class"] != "chain"):
        tol = max(tol, NEAR_EXACT_TOLERANCE_M)
    return haversine_m(a["lat"], a["lon"], b["lat"], b["lon"]) <= tol


def build_clusters(rows):
    idf, default_idf, df = build_idf(rows)

    by_block = defaultdict(list)
    for r in rows:
        by_block[(r["metro"], rarest_token(r["name"], idf, default_idf))].append(r)

    u = Union([r["id"] for r in rows])
    comparisons = 0
    for block in by_block.values():
        if len(block) < 2 or len(block) > 400:   # runaway blocks are not real entities
            continue
        for i in range(len(block)):
            for j in range(i + 1, len(block)):
                comparisons += 1
                if pair_matches(block[i], block[j], idf, default_idf, df):
                    u.union(block[i]["id"], block[j]["id"])

    raw = defaultdict(list)
    for r in rows:
        raw[u.find(r["id"])].append(r)

    # Split transitive chains: every member must match the survivor directly.
    clusters, split_off = {}, 0
    for key, members in raw.items():
        if len(members) < 3:
            clusters[key] = members
            continue
        survivor = max(members, key=lambda r: (completeness(r), len(r["name"] or "")))
        kept = [m for m in members
                if m is survivor or pair_matches(survivor, m, idf, default_idf, df)]
        clusters[key] = kept
        kept_ids = {id(m) for m in kept}
        for m in members:
            if id(m) not in kept_ids:
                # Namespaced key. Using the bare record id collides with the
                # union-find root -- when a split-off member *was* the root, it
                # overwrote its own cluster and silently destroyed it.
                clusters[("split", m["id"])] = [m]
                split_off += 1

    return clusters, comparisons, split_off, idf, default_idf


def medoid(members):
    """The member minimising total distance to the others -- robust to outliers."""
    if len(members) <= 2:
        return members[0]
    best, best_total = members[0], float("inf")
    for m in members:
        total = sum(haversine_m(m["lat"], m["lon"], o["lat"], o["lon"])
                    for o in members if o is not m)
        if total < best_total:
            best, best_total = m, total
    return best


def completeness(r):
    return (bool(r.get("websites")) + bool(r.get("socials")) + bool(r.get("phones"))
            + bool(r.get("basic_category")))


def choose_survivor(members):
    """Richest record wins the identity; the medoid supplies the location.

    Split on purpose: the most complete record is often not the one with the most
    plausible coordinates. `confidence` is not used -- for Washington Oaks the
    0.58 and 0.97 records disagree by 20 km and neither is obviously right.
    """
    ranked = sorted(members, key=lambda r: (completeness(r), float(r.get("authenticity") or 0),
                                            len(r["name"] or "")), reverse=True)
    survivor = ranked[0]
    loc = medoid(members)
    spread = max((haversine_m(loc["lat"], loc["lon"], m["lat"], m["lon"]) for m in members),
                 default=0.0)
    return survivor, loc, spread

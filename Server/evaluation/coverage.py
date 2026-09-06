"""Resolve named must-haves; fuzzy candidates are suggestions, never claimed hits."""

import re
import unicodedata
from difflib import SequenceMatcher

import psycopg2
from psycopg2.extras import RealDictCursor

from .datasets import DSN


def normalize(name):
    text = unicodedata.normalize("NFKD", name).casefold().replace("’", "'")
    return re.sub(r"[^a-z0-9]+", " ", text.replace("'", "")).strip()


def resolve(metro, freeform):
    names = list(dict.fromkeys(s.strip() for s in freeform.get("missing", "").split(",") if s.strip()))
    with psycopg2.connect(DSN) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT name, COALESCE(canonical_id,id) AS entity_id FROM places WHERE metro=%s", (metro,))
        indexed = [dict(r) for r in cur.fetchall()]
    normalized = [(normalize(p["name"]), p) for p in indexed]
    matches = []
    for name in names:
        key = normalize(name)
        exact = {p["entity_id"]: p for n, p in normalized if n == key}
        suggestions = []
        if not exact:
            ranked = sorted(((SequenceMatcher(None, key, n).ratio(), p) for n, p in normalized),
                            key=lambda pair: pair[0], reverse=True)
            seen = set()
            for similarity, place in ranked:
                if similarity < .5 or len(suggestions) >= 3:
                    break
                if place["entity_id"] not in seen:
                    suggestions.append(place)
                    seen.add(place["entity_id"])
        matches.append({"requested": name, "exact_matches": list(exact.values()), "suggestions": suggestions})
    return {"named": len(names), "exact": sum(bool(m["exact_matches"]) for m in matches),
            "matches": matches}

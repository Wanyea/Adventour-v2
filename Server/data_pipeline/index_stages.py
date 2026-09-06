"""Ordered filter, score and dedup stages inside the loader's transaction."""

from collections import defaultdict

import h3
from psycopg2.extras import Json, RealDictCursor, execute_values

from data_pipeline.authenticity import authenticity_score, explain
from data_pipeline.dedup import build_clusters, choose_survivor
from data_pipeline.junk_filter import classify, needs_booking


def filter_places(conn, metros):
    with conn.cursor() as cur:
        cur.execute("SELECT id,name,basic_category FROM places WHERE metro=ANY(%s) AND index_active", (metros,))
        updates = [(pid, *classify(name, cat), needs_booking(name, cat)) for pid, name, cat in cur.fetchall()]
        if updates:
            execute_values(cur, """UPDATE places p SET tier=v.t, tier_reason=v.r, needs_booking=v.b
                FROM (VALUES %s) v(id,t,r,b) WHERE p.id=v.id""", updates)
    return len(updates)


def score_places(conn, metros):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""SELECT p.id,p.name,p.confidence,p.socials,p.chain_class,
            (SELECT count(*) FROM places q WHERE q.h3_r8=p.h3_r8 AND q.tier='KEEP'
             AND q.index_active) AS density
            FROM places p WHERE p.metro=ANY(%s) AND p.index_active AND p.tier='KEEP'""", (metros,))
        updates = []
        for row in cur.fetchall():
            score, components = authenticity_score(row["confidence"], bool(row["socials"]),
                                                     row["density"], row["chain_class"])
            updates.append((row["id"], score, explain(row["name"], score, components, row["chain_class"]),
                            Json(components), row["density"]))
        if updates:
            execute_values(cur, """UPDATE places p SET authenticity=v.s, authenticity_why=v.w,
                score_components=v.c::jsonb, score_density=v.d
                FROM (VALUES %s) v(id,s,w,c,d) WHERE p.id=v.id""", updates)
    return len(updates)


def deduplicate(conn, metros, previous):
    """Keep existing entity identities; infer merges only for newly seen records.

    When a proposed cluster spans two existing entities, leave them separate and
    keep ambiguous new members separate. Do not silently rewrite user history.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""SELECT id,name,metro,lat,lon,chain_class,fl_name_count,
            basic_category,websites,socials,phones,authenticity,tier
            FROM places WHERE metro=ANY(%s) AND index_active AND tier='KEEP' ORDER BY id""", (metros,))
        rows = [dict(r) for r in cur.fetchall()]
        clusters, _, _, _, _ = build_clusters(rows)
        groups = defaultdict(list)
        for members in clusters.values():
            old_ids = {previous[m["id"]] for m in members if m["id"] in previous}
            if not old_ids:
                root = choose_survivor(members)[0]["id"]
            elif len(old_ids) == 1:
                root = next(iter(old_ids))
            else:
                root = None
            for member in members:
                entity = previous.get(member["id"], root or member["id"])
                groups[entity].append(member)
        updates = []
        for entity, members in groups.items():
            _, location, spread = choose_survivor(members)
            cell = h3.latlng_to_cell(location["lat"], location["lon"], 8)
            for member in members:
                updates.append((member["id"], entity, len(members), round(spread, 1),
                                location["lat"], location["lon"], cell))
        if updates:
            execute_values(cur, """UPDATE places p SET canonical_id=v.c, cluster_size=v.n,
                loc_spread_m=v.s, canonical_lat=v.la, canonical_lon=v.lo, canonical_h3_r8=v.h
                FROM (VALUES %s) v(id,c,n,s,la,lo,h) WHERE p.id=v.id""", updates)
    return len(groups)

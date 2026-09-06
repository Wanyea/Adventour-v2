"""Owned-index launch lookup. No paid geocoding, autocomplete or candidate calls."""

import math

from sqlalchemy import text


def suggestions(db, query):
    query = (query or '').strip()[:160]
    if len(query) < 3:
        return []
    rows = db.session.execute(text("""
        WITH locations AS (
            SELECT initcap(lower(trim(locality))) AS label,upper(trim(region)) AS region,
                   avg(lat) AS lat,avg(lon) AS lon,0 AS priority
            FROM places WHERE index_active AND locality IS NOT NULL
            GROUP BY lower(trim(locality)),upper(trim(region))
            UNION ALL
            SELECT initcap(replace(metro,'_',' ')),region,avg(lat),avg(lon),1
            FROM places WHERE index_active GROUP BY metro,region
            UNION ALL
            SELECT name,region,COALESCE(canonical_lat,lat),COALESCE(canonical_lon,lon),2
            FROM places WHERE index_active AND tier='KEEP'
        )
        SELECT DISTINCT label,region,lat,lon,priority FROM locations
        WHERE strpos(lower(label),lower(:query))>0
           OR lower(concat(label,', ',region))=lower(:query)
        ORDER BY priority,label,lat,lon LIMIT 8
    """), {"query": query}).mappings().all()
    seen, result = set(), []
    qualified = {row['label'].casefold() for row in rows if row['region']}
    for row in rows:
        if not row['region'] and row['label'].casefold() in qualified:
            continue
        description = f"{row['label']}, {row['region']}" if row['region'] else row['label']
        if description.casefold() in seen:
            continue
        seen.add(description.casefold())
        result.append({"description": description, "latitude": row['lat'], "longitude": row['lon'],
                       "source": "adventour_index", "place_id": None})
    return result


def resolve(db, query):
    rows = suggestions(db, query)
    exact = [r for r in rows if r['description'].lower() == query.strip().lower()
             or r['description'].split(',')[0].lower() == query.strip().lower()]
    if len(exact) == 1:
        return exact[0]
    if len(rows) == 1:
        return rows[0]
    raise ValueError("Choose a suggested indexed city or place; this launch point is ambiguous or not covered.")


def coordinates(latitude, longitude):
    lat, lon = float(latitude), float(longitude)
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Invalid coordinates.")
    return {"city": "Current Location", "state": "GPS", "latitude": lat, "longitude": lon,
            "source": "device_coordinates"}

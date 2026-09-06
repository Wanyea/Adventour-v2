"""Render what the filtered, scored index would feed a swipe deck.

This is a DATA preview, not the app. The RN client still talks to the old SQLite
backend; wiring it to this index is a later step.

Both orderings are shown deliberately. Distance ordering is what a deck would
actually do today. Score ordering exposes the Gate 8 finding -- 490 places share
one score, so sorting by it produces near-arbitrary order at the top.
"""

import json
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

from authenticity import AUTHENTICITY_FLOOR

DSN = os.environ.get("ADVENTOUR_PG_DSN", "host=localhost port=5432 user=postgres dbname=adventour")
OUT = Path(__file__).resolve().parent / "qa" / "deck_preview.html"

CENTER = (29.5844, -81.2079)  # downtown Palm Coast
RADIUS_M = 8000

QUERY = """
SELECT name, basic_category, chain_class, tier, tier_reason, confidence,
       fl_name_count, websites[1] AS website, lat, lon,
       authenticity, authenticity_why,
       (6371000 * acos(least(1, greatest(-1,
            cos(radians(%(lat)s)) * cos(radians(clat)) * cos(radians(clon) - radians(%(lon)s))
          + sin(radians(%(lat)s)) * sin(radians(clat)))))) AS meters
FROM (
  SELECT DISTINCT ON (COALESCE(canonical_id, id)) *,
         COALESCE(canonical_lat, lat) AS clat, COALESCE(canonical_lon, lon) AS clon
  FROM places WHERE metro = 'palm_coast'
  ORDER BY COALESCE(canonical_id, id), cluster_size DESC NULLS LAST, authenticity DESC NULLS LAST
) places
WHERE tier = %(tier)s
  AND (%(cls)s IS NULL OR chain_class = ANY(%(cls)s))
  AND (%(tier)s <> 'KEEP' OR authenticity >= %(floor)s)
ORDER BY meters
LIMIT %(limit)s
"""


def fetch(cur, tier, cls, limit):
    cur.execute(QUERY, dict(lat=CENTER[0], lon=CENTER[1], tier=tier, cls=cls,
                            limit=limit, floor=AUTHENTICITY_FLOOR))
    out = []
    for r in cur.fetchall():
        d = dict(r)
        d["meters"] = round(float(d["meters"]))
        d["confidence"] = round(float(d["confidence"]), 2) if d["confidence"] is not None else None
        d["authenticity"] = round(float(d["authenticity"]), 3) if d["authenticity"] is not None else None
        d["lat"], d["lon"] = float(d["lat"]), float(d["lon"])
        out.append(d)
    return [p for p in out if p["meters"] <= RADIUS_M]


HTML = """<!doctype html>
<meta charset="utf-8">
<title>Adventour — Palm Coast deck preview</title>
<style>
  :root { --bg:#faf9f7; --card:#fff; --ink:#1a1a1a; --muted:#6b6b6b; --line:#e4e1dc;
          --accent:#1a6b5a; --warn:#b45309; --bad:#a13d3d; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#16181a; --card:#1f2224; --ink:#eceae7; --muted:#9a9a9a; --line:#33383b;
            --accent:#4db6a0; --warn:#e0a34a; --bad:#e08585; } }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:15px/1.55 ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif; }
  header { padding:26px 20px 12px; max-width:960px; margin:0 auto; }
  h1 { font-size:20px; margin:0 0 6px; }
  .note { color:var(--muted); font-size:13.5px; max-width:680px; }
  .note b { color:var(--warn); }
  main { max-width:960px; margin:0 auto; padding:8px 20px 80px; }
  h2 { font-size:14px; text-transform:uppercase; letter-spacing:.07em; color:var(--muted);
       margin:34px 0 10px; font-weight:650; }
  .deck { display:grid; gap:12px; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); }
  .card { background:var(--card); border:1px solid var(--line); border-radius:13px; padding:16px;
          position:relative; }
  .card.drop { opacity:.6; }
  .rank { color:var(--muted); font-size:11.5px; letter-spacing:.05em; }
  .name { font-size:16.5px; font-weight:640; margin:3px 0 2px; line-height:1.25; }
  .cat { color:var(--muted); font-size:13px; }
  .row { display:flex; gap:6px; flex-wrap:wrap; margin-top:11px; align-items:center; }
  .chip { font-size:11.5px; padding:2.5px 8px; border-radius:20px; border:1px solid var(--line);
          color:var(--muted); }
  .chip.ind, .chip.reg { border-color:var(--accent); color:var(--accent); }
  .chip.chain { border-color:var(--warn); color:var(--warn); }
  .chip.why { border-color:var(--bad); color:var(--bad); }
  .meta { position:absolute; top:14px; right:16px; text-align:right; }
  .score { font-size:19px; font-weight:660; font-variant-numeric:tabular-nums; color:var(--accent); }
  .dist { color:var(--muted); font-size:12px; font-variant-numeric:tabular-nums; }
  .why { color:var(--muted); font-size:12.5px; margin-top:9px; font-style:italic; }
  a { color:var(--accent); font-size:12.5px; text-decoration:none; margin-right:12px; }
  .legend { background:var(--card); border:1px solid var(--line); border-radius:11px;
            padding:14px 16px; font-size:13.5px; color:var(--muted); margin-top:10px; }
  .tabs { display:flex; gap:8px; margin:18px 0 4px; }
  .tabs button { font:inherit; font-size:13px; padding:7px 14px; border-radius:8px; cursor:pointer;
                 border:1px solid var(--line); background:transparent; color:var(--ink); }
  .tabs button.on { background:var(--accent); border-color:var(--accent); color:#fff; }
  .tied { color:var(--bad); font-size:12.5px; margin-top:8px; }
</style>

<header>
  <h1>Palm Coast deck preview</h1>
  <div class="note">
    Everything within 8&nbsp;km of downtown, after the Gate&nbsp;7 filter and Gate&nbsp;8 scoring.
    <b>This is the data, not the app</b> — the phone client still reads the old backend.
  </div>
  <div class="legend" id="legend"></div>
  <div class="tabs">
    <button id="t-dist" class="on" onclick="setSort('dist')">Order by distance</button>
    <button id="t-score" onclick="setSort('score')">Order by authenticity score</button>
  </div>
  <div class="tied" id="tied"></div>
</header>
<main id="main"></main>

<script>
const DATA = __DATA__;
let SORT = "dist";

function chips(p) {
  const c = [];
  const cls = { independent:"ind", regional:"reg", chain:"chain" }[p.chain_class] || "";
  c.push(`<span class="chip ${cls}">${p.chain_class}</span>`);
  if (p.fl_name_count > 1) c.push(`<span class="chip">${p.fl_name_count}x in FL</span>`);
  if (p.confidence != null) c.push(`<span class="chip">conf ${p.confidence}</span>`);
  if (p.tier !== "KEEP") c.push(`<span class="chip why">${p.tier_reason}</span>`);
  return c.join("");
}

function card(p, i) {
  const maps = `https://www.google.com/maps/search/?api=1&query=${p.lat},${p.lon}`;
  const why = p.authenticity_why ? p.authenticity_why.split("—").slice(1).join("—").trim() : "";
  return `<div class="card ${p.tier === 'DROP' ? 'drop' : ''}">
    <div class="meta">
      ${p.authenticity != null ? `<div class="score">${p.authenticity.toFixed(2)}</div>` : ""}
      <div class="dist">${p.meters} m</div>
    </div>
    <div class="rank">${String(i + 1).padStart(2, "0")}</div>
    <div class="name">${esc(p.name)}</div>
    <div class="cat">${esc(p.basic_category || "no category")}</div>
    <div class="row">${chips(p)}</div>
    ${why ? `<div class="why">${esc(why)}</div>` : ""}
    <div class="row"><a href="${maps}" target="_blank" rel="noopener">Maps &#8599;</a>
      ${p.website ? `<a href="${esc(p.website)}" target="_blank" rel="noopener">Site &#8599;</a>` : ""}</div>
  </div>`;
}

function sorted(rows) {
  const r = rows.slice();
  if (SORT === "score") r.sort((a, b) => (b.authenticity ?? -1) - (a.authenticity ?? -1)
                                       || a.meters - b.meters);
  else r.sort((a, b) => a.meters - b.meters);
  return r;
}

function section(title, sub, rows) {
  if (!rows.length) return "";
  return `<h2>${title} &middot; ${rows.length}</h2>
    <div class="note" style="margin-bottom:10px">${sub}</div>
    <div class="deck">${sorted(rows).map(card).join("")}</div>`;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
}

function setSort(s) {
  SORT = s;
  document.getElementById("t-dist").className = s === "dist" ? "on" : "";
  document.getElementById("t-score").className = s === "score" ? "on" : "";
  render();
}

function render() {
  // Make the Gate 8 ceiling visible rather than described.
  const counts = {};
  DATA.keep.forEach(p => { const k = (p.authenticity ?? 0).toFixed(2);
                           counts[k] = (counts[k] || 0) + 1; });
  const worst = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
  document.getElementById("tied").textContent = SORT === "score" && worst && worst[1] > 1
    ? `Note the ties: ${worst[1]} of these ${DATA.keep.length} share the score ${worst[0]}. `
      + `Across the whole index 490 places share one value — the score is a quality floor, `
      + `not an ordering.`
    : "";

  document.getElementById("main").innerHTML =
    section("The deck", "Independents and regionals — what a user would swipe through.", DATA.keep)
  + section("Gated", "Real places, shown only to someone who asked for this kind of thing.", DATA.gated)
  + section("Mobile", "Real, but no fixed address to navigate to.", DATA.mobile)
  + section("Filtered out", "Rejected by the Gate 7 filter, with the reason. Scan for mistakes.", DATA.dropped);
}

document.getElementById("legend").innerHTML =
  `<b>${DATA.keep.length}</b> places would be dealt to a user standing downtown. ` +
  `<b>${DATA.dropped.length}</b> nearby records were filtered out — shown at the bottom so you can ` +
  `check nothing good was thrown away. The big number on each card is the authenticity score.`;

render();
</script>
"""


def main():
    with psycopg2.connect(DSN) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        data = {
            "keep": fetch(cur, "KEEP", ["independent", "regional"], 40),
            "gated": fetch(cur, "GATED", None, 12),
            "mobile": fetch(cur, "MOBILE", None, 12),
            "dropped": fetch(cur, "DROP", None, 40),
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(HTML.replace("__DATA__", json.dumps(data)), encoding="utf-8")
    print(f"-> {OUT}")
    for k, v in data.items():
        print(f"  {k:<9}{len(v):>4}")


if __name__ == "__main__":
    main()

"""Generate a local ground-truth labeling tool for a seed metro.

Produces a self-contained HTML file. Open it in a browser, label, export JSON.
Runs from the filesystem so the export can actually download -- no server needed.

The sample is stratified so the labels test specific things:
  - independent/normal   -> the authenticity signal itself (the core unknown)
  - corp-name / junk-ish -> whether the junk heuristic is catching the right rows
  - chain / regional     -> whether the chain classifier is right
"""

import json
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

DSN = os.environ.get("ADVENTOUR_PG_DSN", "host=localhost port=5432 user=postgres dbname=adventour")
METRO = os.environ.get("LABEL_METRO", "palm_coast")
ZIPS = [z for z in os.environ.get("LABEL_ZIPS", "").split(",") if z]
METRO_LABEL = os.environ.get("LABEL_METRO_NAME") or METRO.replace("_", " ").title()
OUT = Path(__file__).resolve().parent / "qa" / f"{METRO}_labeling.html"

STRATA = [
    ("independent", "normal", 26),   # per ZIP when ZIPS is set
    ("independent", "corp-name", 4),
    ("regional", "normal", 4),
    ("chain", "normal", 3),
]

KIND_SQL = """
    CASE WHEN name ~* '(hoa|homeowners|condominium|condo assoc|property owners|association, inc|apartments|realty|property manag)'
              THEN 'junk-ish'
         WHEN name ~* '(llc|inc\\.?$|corp|holdings)' THEN 'corp-name'
         ELSE 'normal' END
"""

QUERY = f"""
SELECT id, name, basic_category, category, taxonomy_bucket, confidence,
       chain_class, fl_name_count, websites, lat, lon, postcode,
       authenticity, tier, {KIND_SQL} AS kind
FROM places
WHERE metro = %(metro)s AND chain_class = %(cls)s AND {KIND_SQL} = %(kind)s
  AND (%(zip)s IS NULL OR postcode = %(zip)s)
  AND tier IN ('KEEP','GATED')
ORDER BY md5(id)
LIMIT %(lim)s
"""


def fetch_sample():
    rows = []
    zips = ZIPS or [None]
    with psycopg2.connect(DSN) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        for z in zips:
            for chain_class, kind, n in STRATA:
                cur.execute(QUERY, dict(metro=METRO, cls=chain_class, kind=kind, zip=z, lim=n))
                rows.extend(dict(r) for r in cur.fetchall())
    for r in rows:
        r["confidence"] = round(float(r["confidence"]), 2) if r["confidence"] is not None else None
        r["website"] = (r.pop("websites") or [None])[0]
        r["authenticity"] = round(float(r["authenticity"]), 2) if r["authenticity"] is not None else None
        r["lat"], r["lon"] = float(r["lat"]), float(r["lon"])
    # Interleave strata so the labeller is not primed by long runs of one kind.
    rows.sort(key=lambda r: r["id"])
    return rows


HTML = """<!doctype html>
<meta charset="utf-8">
<title>Adventour — ground truth</title>
<style>
  :root {
    --bg:#faf9f7; --card:#fff; --ink:#1a1a1a; --muted:#6b6b6b; --line:#e4e1dc;
    --accent:#1a6b5a; --warn:#b45309;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#16181a; --card:#1f2224; --ink:#eceae7; --muted:#9a9a9a;
            --line:#33383b; --accent:#4db6a0; --warn:#e0a34a; }
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:15px/1.5 ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif; }
  header { position:sticky; top:0; background:var(--bg); border-bottom:1px solid var(--line);
           padding:12px 20px; z-index:10; }
  .bar { height:5px; background:var(--line); border-radius:3px; overflow:hidden; margin-top:8px; }
  .bar div { height:100%; background:var(--accent); width:0; transition:width .2s; }
  main { max-width:720px; margin:0 auto; padding:24px 20px 120px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px;
          padding:22px; margin-bottom:16px; }
  h1 { font-size:17px; margin:0; font-weight:650; }
  h2 { font-size:22px; margin:0 0 6px; line-height:1.25; }
  .meta { color:var(--muted); font-size:13px; margin-bottom:4px; }
  .tags { display:flex; gap:6px; flex-wrap:wrap; margin:12px 0 18px; }
  .tag { font-size:12px; padding:3px 9px; border:1px solid var(--line); border-radius:20px;
         color:var(--muted); }
  .links a { color:var(--accent); margin-right:14px; font-size:13px; }
  .opts { display:grid; gap:7px; margin-top:16px; }
  button.opt { text-align:left; padding:11px 14px; border:1px solid var(--line); background:transparent;
        color:var(--ink); border-radius:9px; cursor:pointer; font-size:14px; font-family:inherit; }
  button.opt:hover { border-color:var(--accent); }
  button.opt.sel { background:var(--accent); border-color:var(--accent); color:#fff; }
  button.opt kbd { float:right; opacity:.55; font-size:11px; }
  textarea { width:100%; margin-top:12px; padding:10px; border:1px solid var(--line);
             border-radius:8px; background:transparent; color:var(--ink); font-family:inherit;
             font-size:14px; resize:vertical; }
  nav { display:flex; gap:10px; margin-top:18px; align-items:center; }
  nav button { padding:9px 16px; border-radius:8px; border:1px solid var(--line);
               background:transparent; color:var(--ink); cursor:pointer; font-family:inherit; }
  .primary { background:var(--accent) !important; color:#fff !important; border-color:var(--accent) !important; }
  .free label { display:block; font-weight:600; margin:18px 0 4px; }
  .free p { color:var(--muted); font-size:13px; margin:0 0 6px; }
  .done { text-align:center; padding:40px 20px; }
  .hint { color:var(--muted); font-size:12.5px; }
  .hrow { display:flex; align-items:center; gap:10px; }
  .spacer { flex:1; }
  button.mini { font-size:12px; padding:5px 11px; border-radius:7px; border:1px solid var(--line);
                background:transparent; color:var(--ink); cursor:pointer; font-family:inherit; }
  .saved { font-size:12px; color:var(--accent); opacity:0; transition:opacity .25s; }
  .saved.show { opacity:1; }
  .noterow { display:flex; align-items:center; gap:10px; margin-top:6px; }
</style>

<header>
  <div class="hrow">
    <h1>Adventour — __METRO_LABEL__ ground truth</h1>
    <span class="spacer"></span>
    <span class="saved" id="saved">saved</span>
    <button class="mini" onclick="document.getElementById('importer').click()">Import progress</button>
    <button class="mini" onclick="i = PLACES.length; render();">Skip to questions</button>
    <button class="mini" onclick="exportAll()">Export progress</button>
    <input type="file" id="importer" accept="application/json,.json"
           style="display:none" onchange="importFile(this)">
  </div>
  <div class="hint" id="prog">…</div>
  <div class="bar"><div id="pbar"></div></div>
</header>

<main>
  <div id="view"></div>
</main>

<script>
const PLACES = __DATA__;
const METRO_NAME = "__METRO__";
const METRO_LABEL = "__METRO_LABEL__";
const ZIPS = __ZIPS__;
// Question 1 asks about what the sample MISSED, so it must name the
// neighbourhoods actually sampled -- not the whole metro.
const AREA = ZIPS.length ? METRO_LABEL + " (" + ZIPS.join(", ") + ")" : METRO_LABEL;
const OPTIONS = [
  ["gem",       "Local gem — authentic, I'd send a friend here"],
  ["solid",     "Solid local spot — real, but not special"],
  ["generic",   "Generic — fine, forgettable"],
  ["not_worth", "Real place, but I'd never recommend it to anyone"],
  ["chain",     "Chain or franchise"],
  ["trap",      "Tourist trap"],
  ["junk",      "Not a real destination (office, HOA, condo, etc.)"],
  ["unknown",   "Don't know it"],
];
const KEY = "adventour_" + METRO_NAME + "_labels_v1";
let state = JSON.parse(localStorage.getItem(KEY) || "{}");
let i = 0;
let savedTimer;

// Everything persists on every keystroke and every click. The visible flash
// exists so that is believable rather than merely true.
function save() {
  localStorage.setItem(KEY, JSON.stringify(state));
  const el = document.getElementById("saved");
  if (!el) return;
  el.textContent = "saved " + new Date().toLocaleTimeString();
  el.classList.add("show");
  clearTimeout(savedTimer);
  savedTimer = setTimeout(() => el.classList.remove("show"), 1500);
}

function setNote(id, text) {
  state[id] = Object.assign({}, state[id], { note: text });
  save();
}
function go(n) { if (n >= 0 && n <= PLACES.length - 1) { i = n; render(); } }

function setLabel(id, val) {
  state[id] = Object.assign({}, state[id], { label: val });
  save(); render();
  setTimeout(() => { if (i < PLACES.length - 1) { i++; render(); } }, 130);
}

function render() {
  const done = PLACES.filter(p => state[p.id] && state[p.id].label).length;
  const noted = PLACES.filter(p => state[p.id] && state[p.id].note).length;
  document.getElementById("prog").textContent =
    `${done} of ${PLACES.length} labeled` + (noted ? ` · ${noted} with notes` : "")
    + (done === PLACES.length ? " — done, finish the questions at the end" : "");
  document.getElementById("pbar").style.width = (100 * done / PLACES.length) + "%";

  if (i >= PLACES.length) return renderFinish();
  const p = PLACES[i], cur = (state[p.id] || {}).label;
  const maps = `https://www.google.com/maps/search/?api=1&query=${p.lat},${p.lon}`;
  document.getElementById("view").innerHTML = `
    <div class="card">
      <div class="meta">${i + 1} of ${PLACES.length}</div>
      <h2>${esc(p.name)}</h2>
      <div class="tags">
        <span class="tag">${esc(p.basic_category || "no category")}</span>
        <span class="tag">we guessed: ${esc(p.chain_class)}</span>
        <span class="tag">confidence ${p.confidence ?? "?"}</span>
        ${p.postcode ? `<span class="tag">${p.postcode}</span>` : ""}
        ${p.authenticity != null ? `<span class="tag">we scored ${p.authenticity}</span>` : ""}
        ${p.tier === "GATED" ? `<span class="tag">gated</span>` : ""}
        ${p.fl_name_count > 1 ? `<span class="tag">${p.fl_name_count}× in FL</span>` : ""}
      </div>
      <div class="links">
        <a href="${maps}" target="_blank" rel="noopener">Look up on Maps ↗</a>
        ${p.website ? `<a href="${esc(p.website)}" target="_blank" rel="noopener">Website ↗</a>` : ""}
      </div>
      <div class="opts">
        ${OPTIONS.map(([v, lbl], n) => `
          <button class="opt ${cur === v ? "sel" : ""}" onclick="setLabel('${p.id}', '${v}')">
            ${lbl}<kbd>${n + 1}</kbd></button>`).join("")}
      </div>
      <textarea rows="2" placeholder="Why? What's wrong with it? (optional — saves on its own)"
        oninput="setNote('${p.id}', this.value)"
      >${esc(((state[p.id] || {}).note) || "")}</textarea>
      <div class="noterow hint">
        A note is saved on its own — you don't have to pick an option to keep it.
      </div>
      <nav>
        <button onclick="go(i-1)">← Back</button>
        <button onclick="${i < PLACES.length - 1 ? "go(i+1)" : "i=PLACES.length;render()"}">
          Next — no label needed →</button>
        <span class="hint">press 1–${OPTIONS.length}</span>
      </nav>
    </div>`;
}

function renderFinish() {
  document.getElementById("view").innerHTML = `
    <div class="card free">
      <h2>Last part — the questions the data can't answer</h2>
      <p class="hint">This section matters more than the labels above. Take your time.</p>

      <label>1. Which ${AREA} places should Adventour absolutely recommend?</label>
      <p>List them even if you didn't see them above — especially then. This tells me what the
         dataset is <em>missing</em>, which I can't measure any other way.</p>
      <textarea rows="6" id="f_missing"></textarea>

      <label>2. What would a tourist wrongly be sent to?</label>
      <p>Places that look good online but locals know better.</p>
      <textarea rows="4" id="f_traps"></textarea>

      <label>3. Where do locals actually go, by area?</label>
      <p>Neighborhoods, strips, or corners. Helps me build the "tourist density" signal.</p>
      <textarea rows="4" id="f_areas"></textarea>

      <label>4. What makes a place feel authentic to you?</label>
      <p>In your words — this becomes the scoring definition.</p>
      <textarea rows="4" id="f_auth"></textarea>

      <label>5. Anything above that I got badly wrong?</label>
      <textarea rows="3" id="f_wrong"></textarea>

      <h2 style="margin-top:34px">Local events &amp; third spaces</h2>
      <p class="hint">Separate feature, being scoped now. These answers shape whether it is worth building.</p>

      <label>6. Where do locals actually find out about events in ${METRO_LABEL}?</label>
      <p>Instagram accounts, newsletters, flyers, a specific venue's calendar, word of mouth —
         be specific. This tells me which sources are worth ingesting.</p>
      <textarea rows="5" id="f_evsources"></textarea>

      <label>7. Name recurring local events worth recommending.</label>
      <p>Art markets, run clubs, open mics, first-Friday things. The recurring ones matter most —
         they are the ones a visitor could reliably catch.</p>
      <textarea rows="5" id="f_events"></textarea>

      <label>8. Which places in the list above actually host events?</label>
      <p>If venues we already index are the event hosts, we may not need an events provider at all.</p>
      <textarea rows="4" id="f_venues"></textarea>

      <label>9. Would you use Adventour to find an event, or is that a different app in your head?</label>
      <p>An honest no is more useful than a polite yes.</p>
      <textarea rows="3" id="f_evwould"></textarea>

      <nav>
        <button onclick="i=PLACES.length-1;render();">← Back to places</button>
        <button class="primary" onclick="exportAll()">Download JSON</button>
      </nav>
    </div>`;
  const saved = JSON.parse(localStorage.getItem(KEY + "_free") || "{}");
  ["missing","traps","areas","auth","wrong","evsources","events","venues","evwould"].forEach(k => {
    const el = document.getElementById("f_" + k);
    el.value = saved[k] || "";
    el.oninput = () => {
      const s = JSON.parse(localStorage.getItem(KEY + "_free") || "{}");
      s[k] = el.value; localStorage.setItem(KEY + "_free", JSON.stringify(s));
    };
  });
}

function importFile(input) {
  const file = input.files && input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    let data;
    try { data = JSON.parse(reader.result); }
    catch (e) { alert("That file is not valid JSON."); return; }

    const rows = Array.isArray(data.labels) ? data.labels : [];
    const known = new Set(PLACES.map(p => p.id));
    let restored = 0, unknown = 0;
    for (const r of rows) {
      if (!r || !r.id) continue;
      if (!known.has(r.id)) { unknown++; continue; }   // e.g. a different metro's export
      if (r.label || r.note) {
        state[r.id] = Object.assign({}, state[r.id],
          r.label ? { label: r.label } : {}, r.note ? { note: r.note } : {});
        restored++;
      }
    }
    if (data.freeform && typeof data.freeform === "object") {
      const cur = JSON.parse(localStorage.getItem(KEY + "_free") || "{}");
      localStorage.setItem(KEY + "_free", JSON.stringify(Object.assign(cur, data.freeform)));
    }
    save();
    input.value = "";
    const msg = [restored + " labels restored"];
    if (unknown) msg.push(unknown + " entries skipped (not in this sample -- wrong metro?)");
    msg.push("Use the “Skip to questions” button for the written section.");
    alert(msg.join(String.fromCharCode(10)));
    render();
  };
  reader.readAsText(file);
}

function exportAll() {
  // Read free-text from storage, not the DOM, so Export works from the header
  // mid-run when those fields are not on screen.
  const free = JSON.parse(localStorage.getItem(KEY + "_free") || "{}");
  ["missing","traps","areas","auth","wrong","evsources","events","venues","evwould"].forEach(k => {
    const el = document.getElementById("f_" + k); if (el) free[k] = el.value;
  });
  const out = {
    generated_at: new Date().toISOString(),
    metro: METRO_NAME,
    labels: PLACES.map(p => ({
      id: p.id, name: p.name, basic_category: p.basic_category,
      our_chain_class: p.chain_class, confidence: p.confidence,
      label: (state[p.id] || {}).label || null, note: (state[p.id] || {}).note || null,
    })),
    freeform: free,
  };
  const blob = new Blob([JSON.stringify(out, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "adventour_" + METRO_NAME + "_labels.json";
  a.click();
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
}

addEventListener("keydown", e => {
  if (e.target.tagName === "TEXTAREA") return;
  if (i >= PLACES.length) return;
  const n = parseInt(e.key, 10);
  if (n >= 1 && n <= OPTIONS.length) setLabel(PLACES[i].id, OPTIONS[n - 1][0]);
  if (e.key === "ArrowLeft" && i > 0) { i--; render(); }
  if (e.key === "ArrowRight" && i < PLACES.length - 1) { i++; render(); }
});

render();
</script>
"""


def main():
    rows = fetch_sample()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        HTML.replace("__DATA__", json.dumps(rows))
            .replace("__METRO_LABEL__", METRO_LABEL)
            .replace("__METRO__", METRO)
            .replace("__ZIPS__", json.dumps(ZIPS)),
        encoding="utf-8")

    by = {}
    for r in rows:
        by[(r["chain_class"], r["kind"])] = by.get((r["chain_class"], r["kind"]), 0) + 1
    print(f"{len(rows)} places -> {OUT}")
    for (cls, kind), n in sorted(by.items()):
        print(f"  {cls:<12}{kind:<12}{n:>4}")


if __name__ == "__main__":
    main()

"""Build a single self-contained HTML file you can email to anyone.

The recipient picks the ZIP codes they actually know, gets a deck built from
those, labels it, answers the written questions, and exports one JSON back.

Design constraint that shapes everything: **it must work as an email attachment
with no server and no internet.** So a stratified sample for every covered ZIP is
embedded up front and the deck is assembled in the browser. That caps coverage at
the metros already ingested -- adding a new city means ingesting it, not changing
this file.

    python make_field_kit.py                    # every ZIP with enough places
    python make_field_kit.py --per-zip 40       # bigger decks, bigger file
"""

import argparse
import json
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

DSN = os.environ.get("ADVENTOUR_PG_DSN", "host=localhost port=5432 user=postgres dbname=adventour")
OUT = Path(__file__).resolve().parent / "qa" / "adventour_field_kit.html"
MIN_PER_ZIP = 25

# Mirrors the labelling tool's strata so the returned data is directly comparable
# with the Palm Coast and Orlando sets.
SQL = """
WITH ranked AS (
    SELECT DISTINCT ON (COALESCE(canonical_id, id))
           COALESCE(canonical_id, id) AS id, name, basic_category, chain_class,
           postcode, metro, round(authenticity::numeric, 2) AS score,
           needs_booking,
           COALESCE(canonical_lat, lat) AS lat, COALESCE(canonical_lon, lon) AS lon
    FROM places
    WHERE tier = 'KEEP' AND authenticity >= 0.30
      AND postcode IS NOT NULL AND postcode <> ''
    ORDER BY COALESCE(canonical_id, id), cluster_size DESC NULLS LAST
), counted AS (
    SELECT *, count(*) OVER (PARTITION BY postcode) AS zip_total,
           row_number() OVER (PARTITION BY postcode, chain_class ORDER BY md5(id)) AS rn
    FROM ranked
)
SELECT id, name, basic_category, chain_class, postcode, metro, score, needs_booking, lat, lon
FROM counted
WHERE zip_total >= %(min_zip)s
  AND rn <= CASE chain_class
              WHEN 'independent' THEN %(indep)s
              WHEN 'regional'    THEN %(reg)s
              ELSE %(chain)s END
ORDER BY postcode, md5(id)
"""

HTML = """<!doctype html>
<meta charset="utf-8">
<title>Adventour — help us find the real places</title>
<style>
 :root{--bg:#faf9f7;--card:#fff;--ink:#1a1a1a;--muted:#6b6b6b;--line:#e4e1dc;--accent:#1a6b5a;--bad:#a13d3d}
 @media(prefers-color-scheme:dark){:root{--bg:#16181a;--card:#1f2224;--ink:#eceae7;--muted:#9a9a9a;--line:#33383b;--accent:#4db6a0;--bad:#e08585}}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif}
 header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 20px;z-index:10}
 .hrow{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
 h1{font-size:17px;margin:0;font-weight:650}.spacer{flex:1}
 main{max-width:720px;margin:0 auto;padding:24px 20px 120px}
 .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:22px;margin-bottom:16px}
 h2{font-size:21px;margin:0 0 6px;line-height:1.25}
 .meta{color:var(--muted);font-size:13px}
 .tags{display:flex;gap:6px;flex-wrap:wrap;margin:12px 0 16px}
 .tag{font-size:12px;padding:3px 9px;border:1px solid var(--line);border-radius:20px;color:var(--muted)}
 .opts{display:grid;gap:7px;margin-top:14px}
 button.opt{text-align:left;padding:11px 14px;border:1px solid var(--line);background:transparent;color:var(--ink);border-radius:9px;cursor:pointer;font:inherit;font-size:14px}
 button.opt:hover{border-color:var(--accent)} button.opt.sel{background:var(--accent);border-color:var(--accent);color:#fff}
 button.opt kbd{float:right;opacity:.55;font-size:11px}
 textarea,input[type=text]{width:100%;margin-top:10px;padding:10px;border:1px solid var(--line);border-radius:8px;background:transparent;color:var(--ink);font:inherit;font-size:14px}
 nav{display:flex;gap:10px;margin-top:16px;align-items:center;flex-wrap:wrap}
 nav button,button.mini{padding:9px 15px;border-radius:8px;border:1px solid var(--line);background:transparent;color:var(--ink);cursor:pointer;font:inherit}
 button.mini{font-size:12px;padding:5px 11px}
 .primary{background:var(--accent)!important;color:#fff!important;border-color:var(--accent)!important}
 .hint{color:var(--muted);font-size:12.5px}
 .bar{height:5px;background:var(--line);border-radius:3px;overflow:hidden;margin-top:8px}.bar div{height:100%;background:var(--accent);width:0;transition:width .2s}
 .zipgrid{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}
 .zip{padding:7px 12px;border:1px solid var(--line);border-radius:20px;cursor:pointer;font-size:13.5px}
 .zip.on{background:var(--accent);border-color:var(--accent);color:#fff}
 .free label{display:block;font-weight:600;margin:18px 0 4px}.free p{color:var(--muted);font-size:13px;margin:0 0 6px}
 a{color:var(--accent)}
 .saved{font-size:12px;color:var(--accent);opacity:0;transition:opacity .25s}.saved.show{opacity:1}
</style>

<header>
 <div class="hrow">
  <h1>Adventour — help us find the real places</h1><span class="spacer"></span>
  <span class="saved" id="saved">saved</span>
  <button class="mini" onclick="document.getElementById('imp').click()">Import</button>
  <button class="mini" onclick="goEnd()">Skip to questions</button>
  <button class="mini primary" onclick="exportAll()">Export &amp; send</button>
  <input type="file" id="imp" accept=".json,application/json" style="display:none" onchange="importFile(this)">
 </div>
 <div class="hint" id="prog"></div><div class="bar"><div id="pbar"></div></div>
</header>
<main id="view"></main>

<script>
const DATA = __DATA__;
const OPTIONS = [
 ["gem","Local gem — authentic, I'd send a friend here"],
 ["solid","Solid local spot — real, but not special"],
 ["generic","Generic — fine, forgettable"],
 ["not_worth","Real place, but I'd never recommend it"],
 ["chain","Chain or franchise"],
 ["trap","Tourist trap"],
 ["junk","Not a real destination (office, campus, condo…)"],
 ["unknown","Don't know it"]];
const KEY="adventour_fieldkit_v1";
let state=JSON.parse(localStorage.getItem(KEY)||"{}");
let picked=JSON.parse(localStorage.getItem(KEY+"_zips")||"[]");
let deck=[], i=0, phase=picked.length?"deck":"pick", t0;

const ZIPS=[...new Set(DATA.map(p=>p.postcode))].sort();
function save(){localStorage.setItem(KEY,JSON.stringify(state));localStorage.setItem(KEY+"_zips",JSON.stringify(picked));
 const e=document.getElementById("saved");if(!e)return;e.textContent="saved";e.classList.add("show");clearTimeout(t0);t0=setTimeout(()=>e.classList.remove("show"),1400);}
function buildDeck(){deck=DATA.filter(p=>picked.includes(p.postcode));}
function esc(s){return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function goEnd(){if(!picked.length){alert("Pick at least one ZIP code first.");return;}phase="end";render();}

function pickView(){
 const byZip={};DATA.forEach(p=>byZip[p.postcode]=(byZip[p.postcode]||0)+1);
 return `<div class="card">
  <h2>Which areas do you actually know?</h2>
  <p class="meta">Pick the ZIP codes you could give someone real advice about. Only pick places you
   know well — a guess is worse than nothing here.</p>
  <div class="zipgrid">${ZIPS.map(z=>`<div class="zip ${picked.includes(z)?"on":""}" onclick="toggleZip('${z}')">${z} <span class="hint">${byZip[z]}</span></div>`).join("")}</div>
  <nav><button class="primary" onclick="startDeck()">Start — ${picked.length} area(s)</button></nav>
  <p class="hint" style="margin-top:14px">Don't see your area? We only cover cities we've loaded so far.
   Reply and tell us where you are.</p></div>`;
}
function toggleZip(z){picked=picked.includes(z)?picked.filter(x=>x!==z):[...picked,z];save();render();}
function startDeck(){if(!picked.length){alert("Pick at least one ZIP code.");return;}buildDeck();phase="deck";i=0;render();}

function deckView(){
 const p=deck[i];if(!p)return endView();
 const cur=(state[p.id]||{}).label;
 const maps=`https://www.google.com/maps/search/?api=1&query=${p.lat},${p.lon}`;
 return `<div class="card">
  <div class="meta">${i+1} of ${deck.length} &middot; ${p.postcode}</div>
  <h2>${esc(p.name)}</h2>
  <div class="meta">${esc(p.basic_category||"")}</div>
  <div class="tags"><span class="tag">${p.chain_class}</span>${p.needs_booking?'<span class="tag">ticket / booking</span>':""}</div>
  <div><a href="${maps}" target="_blank" rel="noopener">Look it up on Maps &#8599;</a></div>
  <div class="opts">${OPTIONS.map(([v,l],n)=>`<button class="opt ${cur===v?"sel":""}" onclick="setLabel('${p.id}','${v}')">${l}<kbd>${n+1}</kbd></button>`).join("")}</div>
  <textarea rows="2" placeholder="Anything worth saying? (optional — saves on its own)"
   oninput="setNote('${p.id}',this.value)">${esc((state[p.id]||{}).note||"")}</textarea>
  <nav><button onclick="if(i>0){i--;render()}">← Back</button>
   <button onclick="next()">Next — no label needed →</button>
   <span class="hint">press 1–8</span></nav></div>`;
}
function setLabel(id,v){state[id]=Object.assign({},state[id],{label:v});save();render();setTimeout(next,120);}
function setNote(id,v){state[id]=Object.assign({},state[id],{note:v});save();}
function next(){if(i<deck.length-1){i++;render()}else{phase="end";render()}}

const FREE=[["missing","Which places here should we absolutely recommend?","List them even if you didn't see them above — especially then. This tells us what we're missing."],
 ["traps","What would a visitor wrongly be sent to?","Places that look good online but locals know better."],
 ["areas","Where do locals actually go?","Streets, strips, neighbourhoods."],
 ["auth","What makes a place feel authentic to you?","In your words."],
 ["events","Any recurring local events worth knowing about?","Art markets, run clubs, open mics, first-Friday things."],
 ["evsources","Where do locals find out about those events?","Instagram accounts, newsletters, flyers, word of mouth."]];

function endView(){
 const f=JSON.parse(localStorage.getItem(KEY+"_free")||"{}");
 return `<div class="card free">
  <h2>Nearly done — the part that helps most</h2>
  <p class="hint">These written answers are more useful than the cards. Skip any that don't apply.</p>
  ${FREE.map(([k,q,h])=>`<label>${q}</label><p>${h}</p><textarea rows="4" id="f_${k}"
    oninput="saveFree('${k}',this.value)">${esc(f[k]||"")}</textarea>`).join("")}
  <nav><button onclick="phase='deck';i=Math.max(0,deck.length-1);render()">← Back to places</button>
   <button class="primary" onclick="exportAll()">Download my answers</button></nav>
  <p class="hint" style="margin-top:14px">This downloads one file. Email it back — it contains only
   your answers, no personal information.</p></div>`;
}
function saveFree(k,v){const f=JSON.parse(localStorage.getItem(KEY+"_free")||"{}");f[k]=v;localStorage.setItem(KEY+"_free",JSON.stringify(f));save();}

function importFile(input){const file=input.files&&input.files[0];if(!file)return;
 const r=new FileReader();r.onload=()=>{let d;try{d=JSON.parse(r.result)}catch(e){alert("Not a valid file.");return}
  const known=new Set(DATA.map(p=>p.id));let n=0;
  (d.labels||[]).forEach(x=>{if(x&&x.id&&known.has(x.id)&&(x.label||x.note)){state[x.id]=Object.assign({},state[x.id],x.label?{label:x.label}:{},x.note?{note:x.note}:{});n++}});
  if(d.zips)picked=[...new Set([...picked,...d.zips])];
  if(d.freeform)localStorage.setItem(KEY+"_free",JSON.stringify(Object.assign(JSON.parse(localStorage.getItem(KEY+"_free")||"{}"),d.freeform)));
  save();buildDeck();input.value="";alert(n+" answers restored.");render();};r.readAsText(file);}

function exportAll(){
 const f=JSON.parse(localStorage.getItem(KEY+"_free")||"{}");
 const out={kit_version:DATA.length,generated_at:new Date().toISOString(),zips:picked,
  labels:DATA.filter(p=>state[p.id]&&(state[p.id].label||state[p.id].note))
    .map(p=>({id:p.id,name:p.name,basic_category:p.basic_category,our_chain_class:p.chain_class,
              postcode:p.postcode,metro:p.metro,our_score:p.score,
              label:(state[p.id]||{}).label||null,note:(state[p.id]||{}).note||null})),
  freeform:f};
 const a=document.createElement("a");
 a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,2)],{type:"application/json"}));
 a.download="adventour_answers.json";a.click();}

function render(){
 const done=deck.filter(p=>state[p.id]&&state[p.id].label).length;
 document.getElementById("prog").textContent = phase==="pick" ? "Step 1 of 2 — choose your areas"
   : `${done} of ${deck.length} labelled${picked.length?" · "+picked.join(", "):""}`;
 document.getElementById("pbar").style.width = deck.length?(100*done/deck.length)+"%":"0%";
 document.getElementById("view").innerHTML =
   phase==="pick"?pickView():phase==="end"?endView():deckView();
}
addEventListener("keydown",e=>{if(e.target.tagName==="TEXTAREA"||phase!=="deck")return;
 const n=parseInt(e.key,10);if(n>=1&&n<=OPTIONS.length&&deck[i])setLabel(deck[i].id,OPTIONS[n-1][0]);
 if(e.key==="ArrowLeft"&&i>0){i--;render()} if(e.key==="ArrowRight")next();});
if(picked.length)buildDeck();
render();
</script>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-zip", type=int, default=30, help="independents sampled per ZIP")
    args = ap.parse_args()

    with psycopg2.connect(DSN) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(SQL, {"min_zip": MIN_PER_ZIP, "indep": args.per_zip,
                          "reg": max(3, args.per_zip // 6), "chain": max(2, args.per_zip // 10)})
        rows = [dict(r) for r in cur.fetchall()]

    for r in rows:
        r["score"] = float(r["score"]) if r["score"] is not None else None
        r["lat"], r["lon"] = round(float(r["lat"]), 5), round(float(r["lon"]), 5)
        r["needs_booking"] = bool(r["needs_booking"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(HTML.replace("__DATA__", json.dumps(rows, separators=(",", ":"))), encoding="utf-8")

    zips = sorted({r["postcode"] for r in rows})
    print(f"{len(rows):,} places across {len(zips)} ZIPs -> {OUT.name}")
    print(f"file size: {OUT.stat().st_size/1024:.0f} KB")
    print(f"ZIPs: {', '.join(zips[:14])}{' …' if len(zips) > 14 else ''}")


if __name__ == "__main__":
    main()

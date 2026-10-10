"""Public portal pages. No browser console logging."""

from __future__ import annotations

import html
from urllib.parse import quote

from sonicmatch.hosted.install_link import INSTALL_CONFIG, cursor_install_link
from sonicmatch.hosted.pricing import GITHUB_REPO, TRIAL_CREDITS

_FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="8" fill="#0c0b09"/>'
    '<g fill="#f0b429">'
    '<circle cx="8" cy="8" r="2.35"/>'
    '<circle cx="16" cy="8" r="2.35" fill="#ffe7a3"/>'
    '<circle cx="24" cy="8" r="2.35"/>'
    '<circle cx="24" cy="16" r="2.35"/>'
    '<circle cx="24" cy="24" r="2.35"/>'
    '<circle cx="16" cy="24" r="2.35"/>'
    '<circle cx="8" cy="24" r="2.35"/>'
    '<circle cx="8" cy="16" r="2.35"/>'
    "</g></svg>"
)
_FAVICON = "data:image/svg+xml," + quote(_FAVICON_SVG, safe="")

_CSS = """
:root {
  color-scheme: dark;
  --bg: #0c0b09;
  --bg-2: #16140f;
  --ink: #f6f1e7;
  --muted: #b7ad9d;
  --line: rgba(246, 241, 231, 0.12);
  --amber: #f0b429;
  --amber-2: #ffe7a3;
  --card: #1a1814;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  min-height: 100vh;
  overflow-x: hidden;
  font: 16px/1.5 "Avenir Next", "Segoe UI", ui-sans-serif, system-ui, sans-serif;
  color: var(--ink);
  background:
    radial-gradient(900px 420px at 85% -10%, rgba(240, 180, 41, 0.18), transparent 60%),
    radial-gradient(700px 380px at -10% 20%, rgba(120, 92, 40, 0.22), transparent 55%),
    var(--bg);
}
a { color: inherit; }
.bar {
  position: sticky; top: 0; z-index: 5;
  display: flex; align-items: center; justify-content: space-between; gap: 1rem;
  padding: 0.85rem 1.4rem;
  background: rgba(12, 11, 9, 0.78);
  backdrop-filter: blur(16px);
  border-bottom: 1px solid var(--line);
}
.brand { display: flex; align-items: center; gap: 0.55rem; text-decoration: none; font-weight: 650; letter-spacing: -0.03em; }
.mark {
  width: 1.55rem; height: 1.55rem; border-radius: 999px;
  background: conic-gradient(from 120deg, var(--amber), #fff6d8, #8a5a12, var(--amber));
  box-shadow: 0 0 0 4px rgba(240, 180, 41, 0.12);
}
nav { display: flex; flex-wrap: wrap; gap: 0.35rem; }
nav a {
  text-decoration: none; color: var(--muted);
  padding: 0.35rem 0.7rem; border-radius: 999px; font-size: 0.92rem;
}
nav a:hover { color: var(--ink); background: rgba(255,255,255,0.04); }
nav a[aria-current="page"] { color: #1a1408; background: var(--amber); }
main { max-width: 68rem; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }
.hero { display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 1.5rem; align-items: end; margin-bottom: 1.25rem; }
h1 {
  margin: 0 0 0.45rem;
  font-family: "Iowan Old Style", Palatino, Georgia, serif;
  font-size: clamp(2.4rem, 5vw, 4.4rem);
  font-weight: 560; letter-spacing: -0.045em; line-height: 0.95;
}
.lede { margin: 0; max-width: 36rem; color: var(--muted); font-size: 1.05rem; }
.kicker { margin: 0 0 0.7rem; color: var(--amber-2); font-size: 0.78rem; letter-spacing: 0.16em; text-transform: uppercase; }
.stage, .panel, .card, .pack, .info {
  background: linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.015));
  border: 1px solid var(--line);
  border-radius: 22px;
  box-shadow: 0 20px 50px rgba(0,0,0,0.22);
}
.stage { padding: 1rem; }
.drop {
  position: relative;
  min-height: 11rem;
  border-radius: 16px;
  border: 1px dashed rgba(240, 180, 41, 0.45);
  background: rgba(240, 180, 41, 0.05);
  display: flex; align-items: center; justify-content: center; text-align: center; padding: 1.4rem;
  overflow: hidden;
}
.drop input { position: absolute; inset: 0; opacity: 0; cursor: pointer; z-index: 2; }
.drop .thumb {
  position: absolute; inset: 0; width: 100%; height: 100%;
  object-fit: cover; pointer-events: none; z-index: 0;
}
.drop .thumb[hidden] { display: none; }
.drop .caption { position: relative; z-index: 1; pointer-events: none; width: 100%; }
.drop.has-thumb {
  min-height: 16rem;
  padding: 0;
  border-style: solid;
  background: #100e0b;
  align-items: flex-end;
}
.drop.has-thumb .caption {
  padding: 2.4rem 1rem 0.9rem;
  text-align: left;
  background: linear-gradient(to top, rgba(8, 7, 5, 0.9), rgba(8, 7, 5, 0));
}
.drop strong { display: block; font-size: 1.15rem; }
.drop span, .hint { color: var(--muted); }
.drop.has-thumb strong, .drop.has-thumb span { color: #f6f1e7; text-shadow: 0 1px 2px rgba(0,0,0,0.5); }
.controls { display: grid; grid-template-columns: 1fr auto; gap: 0.6rem; align-items: end; }
.sample-row { margin: 0.75rem 0 0; text-align: center; }
.sample-row button { background: transparent; color: var(--ink); border: 1px solid var(--line); }
.or { margin: 0.85rem 0 0.15rem; color: var(--muted); font-size: 0.82rem; letter-spacing: 0.14em; text-transform: uppercase; text-align: center; }
label { display: block; margin: 0 0 0.35rem; color: var(--muted); font-size: 0.82rem; }
input, select, button { font: inherit; color: var(--ink); }
input[type="url"], input[type="search"], select {
  width: 100%; padding: 0.75rem 0.85rem; border-radius: 12px;
  border: 1px solid var(--line); background: #100e0b;
}
button, .btn {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 0.75rem 1.05rem; border: 0; border-radius: 12px; cursor: pointer;
  background: var(--amber); color: #1a1408; font-weight: 680; text-decoration: none;
  white-space: nowrap;
}
button.ghost, a.ghost { background: transparent; color: var(--ink); border: 1px solid var(--line); }
.searchbar { display: grid; grid-template-columns: 1fr auto; gap: 0.6rem; align-items: end; }
.note { min-height: 1.4rem; margin: 1rem 0 0.4rem; color: var(--amber-2); }
.results { display: grid; gap: 0.75rem; }
.card { padding: 1rem 1.05rem 1rem 1.1rem; display: grid; grid-template-columns: auto 1fr; gap: 0.9rem; }
.rank {
  width: 2.3rem; height: 2.3rem; border-radius: 10px;
  display: grid; place-items: center; background: #2a2418; color: var(--amber-2); font-weight: 700;
}
.card h3 { margin: 0; font-size: 1.12rem; letter-spacing: -0.02em; }
.meta { margin: 0.2rem 0 0; color: var(--muted); font-size: 0.92rem; }
.chips { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.55rem; }
.chip { font-size: 0.75rem; padding: 0.18rem 0.5rem; border-radius: 999px; background: rgba(255,255,255,0.06); color: var(--muted); }
.chip.lic { color: #1a1408; background: var(--amber-2); }
.why { margin: 0.55rem 0 0; }
.price-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.8rem; margin-top: 1.2rem; }
.price-card { padding: 1.3rem 1.35rem 1.4rem; }
.price-card .usd { font-family: "Iowan Old Style", Palatino, Georgia, serif; font-size: 2.4rem; letter-spacing: -0.04em; margin: 0.2rem 0; }
.price-card p { color: var(--muted); margin: 0.2rem 0 0; }
details { margin-top: 0.9rem; color: var(--muted); }
details summary { cursor: pointer; }
.info { padding: 1.15rem 1.2rem 1.3rem; box-shadow: none; }
.info h2 { margin: 0 0 0.4rem; font-family: "Iowan Old Style", Palatino, Georgia, serif; font-size: 1.7rem; font-weight: 560; }
.info p { color: var(--muted); }
.packs { display: grid; gap: 0.45rem; margin: 0.8rem 0; }
.pack { padding: 0.7rem 0.8rem; border-radius: 14px; display: flex; justify-content: space-between; box-shadow: none; }
pre, code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
pre { background: #100e0b; padding: 0.9rem; overflow: auto; border-radius: 12px; border: 1px solid var(--line); }
.foot { margin-top: 2rem; color: var(--muted); font-size: 0.85rem; }
.drawer-back { display: none; }
body.split { padding-right: min(420px, 100vw); }
.drawer {
  display: none;
  position: fixed; top: 0; right: 0; bottom: 0; z-index: 30;
  width: min(420px, 100vw); height: 100%;
  margin: 0; padding: 0; border-radius: 0;
  background: #14120e; color: var(--ink);
  border: 0; border-left: 1px solid var(--line);
  flex-direction: column; overflow: hidden;
  box-shadow: none;
}
body.split .drawer { display: flex; }
.drawer-head {
  display: flex; align-items: center; justify-content: space-between; gap: 0.8rem;
  padding: 1rem 1rem 0.7rem; border-bottom: 1px solid var(--line);
}
.drawer-head h2 { margin: 0; font-family: "Iowan Old Style", Palatino, Georgia, serif; font-size: 1.6rem; font-weight: 560; }
.drawer-body { overflow: auto; padding: 1rem 1rem 2rem; flex: 1; }
.lattice-stage { display: flex; flex-direction: column; align-items: flex-start; gap: 0.85rem; min-height: 7rem; padding-top: 0.35rem; }
.lattice-detail { margin: 0; color: var(--muted); max-width: 28rem; }
.lattice-loader {
  --ll-n: 3; --ll-cell: 6px; --ll-gap: 2px; --ll-font: 14px;
  --ll-color: currentColor; --ll-mark: #22c55e; --ll-idle: 0.15;
  --ll-glow: currentColor; --ll-mark-glow: #22c55e; --ll-peak: 1; --ll-cycle: 864ms;
  --ll-ease-out: cubic-bezier(0.23, 1, 0.32, 1);
  --ll-ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);
  position: relative; display: inline-flex; align-items: center;
  gap: calc(var(--ll-font) * 0.625); font-family: inherit; font-size: var(--ll-font); line-height: 1;
  color: var(--ll-color);
}
.lattice-loader__grid { display: grid; flex: none; }
.lattice-loader__layer { grid-area: 1 / 1; display: grid; grid-template-columns: repeat(var(--ll-n), var(--ll-cell)); gap: var(--ll-gap); }
.lattice-loader__cell { width: var(--ll-cell); height: var(--ll-cell); border-radius: max(1px, calc(var(--ll-cell) * 0.25)); background: var(--ll-color); opacity: var(--ll-idle); }
.lattice-loader[data-shape="round"] .lattice-loader__cell { border-radius: 50%; }
.lattice-loader[data-glow] .lattice-loader__run .lattice-loader__cell:not([data-hole]) { box-shadow: 0 0 calc(var(--ll-cell) * 1.2) calc(var(--ll-cell) * 0.12) var(--ll-glow); }
.lattice-loader[data-glow] .lattice-loader__mark .lattice-loader__cell[data-on] { box-shadow: 0 0 calc(var(--ll-cell) * 1.2) calc(var(--ll-cell) * 0.12) var(--ll-mark-glow); }
.lattice-loader__run { transition: opacity 200ms ease; }
.lattice-loader__run .lattice-loader__cell { animation: lattice-on var(--ll-cycle) var(--ll-ease-in-out) infinite; }
.lattice-loader__run .lattice-loader__cell[data-lit="45"] { animation-name: lattice-on-45; }
.lattice-loader__run .lattice-loader__cell[data-lit="35"] { animation-name: lattice-on-35; }
.lattice-loader__run .lattice-loader__cell[data-lit="25"] { animation-name: lattice-on-25; }
.lattice-loader__run .lattice-loader__cell[data-hole] { animation: none; opacity: calc(var(--ll-idle) * 0.47); }
.lattice-loader__mark { opacity: 0; transform: scale(0.9); transform-origin: center; transition: opacity 160ms var(--ll-ease-out), transform 160ms var(--ll-ease-out); }
.lattice-loader__mark .lattice-loader__cell { transition: opacity 200ms ease, background-color 200ms ease; }
.lattice-loader__mark .lattice-loader__cell[data-on] { background: var(--ll-mark); opacity: var(--ll-peak); }
.lattice-loader:not([data-status="working"]) .lattice-loader__run { opacity: 0; }
.lattice-loader:not([data-status="working"]) .lattice-loader__run .lattice-loader__cell { animation-play-state: paused; }
.lattice-loader:not([data-status="working"]) .lattice-loader__mark { opacity: 1; transform: none; transition: opacity 200ms ease, transform 200ms var(--ll-ease-out); }
.lattice-loader__label { position: relative; display: inline-block; font-weight: 500; }
.lattice-loader__text { position: absolute; top: 0; left: 0; white-space: nowrap; opacity: 0; filter: blur(2px); transition: opacity 200ms ease, filter 200ms ease; }
.lattice-loader__text[data-active] { position: static; opacity: 1; filter: blur(0); }
.lattice-loader__timer { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: calc(var(--ll-font) * 0.875); font-variant-numeric: tabular-nums; opacity: 0.6; }
.lattice-loader__sr { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; border: 0; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
@keyframes lattice-on { 0%, 100% { opacity: var(--ll-idle); } 18%, 42% { opacity: var(--ll-peak); } 62% { opacity: var(--ll-idle); } }
@keyframes lattice-on-45 { 0%, 100% { opacity: var(--ll-idle); } 13%, 31% { opacity: var(--ll-peak); } 45% { opacity: var(--ll-idle); } }
@keyframes lattice-on-35 { 0%, 100% { opacity: var(--ll-idle); } 10%, 24% { opacity: var(--ll-peak); } 35% { opacity: var(--ll-idle); } }
@keyframes lattice-on-25 { 0%, 100% { opacity: var(--ll-idle); } 7%, 17% { opacity: var(--ll-peak); } 25% { opacity: var(--ll-idle); } }
@media (prefers-reduced-motion: reduce) {
  .lattice-loader__run { --ll-peak: 0.7; }
  .lattice-loader__run .lattice-loader__cell { animation-delay: 0ms !important; animation-duration: 1400ms !important; }
  .lattice-loader .lattice-loader__mark { transform: none; }
  .lattice-loader .lattice-loader__text { filter: none; }
}
.steps { display: grid; gap: 0.55rem; margin: 0; padding: 0; list-style: none; }
.steps li { padding: 0.75rem 0.85rem; border-radius: 12px; border: 1px solid var(--line); color: var(--muted); }
.steps li.on { color: var(--ink); border-color: rgba(240, 180, 41, 0.55); }
.section-card { border: 1px solid var(--line); border-radius: 16px; padding: 0.9rem; margin: 0 0 0.7rem; }
.section-card h3 { margin: 0; font-size: 1rem; }
.actions { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.7rem; }
.actions button { padding: 0.4rem 0.7rem; border-radius: 999px; background: transparent; color: var(--ink); border: 1px solid var(--line); font-weight: 560; }
.actions button[aria-pressed="true"] { background: var(--amber); color: #1a1408; border-color: transparent; }
.copy-row { margin: 0 0 0.9rem; }
.plans { max-width: 68rem; }
.plans-top { display: flex; justify-content: space-between; align-items: flex-end; gap: 1.5rem; margin: 0 0 1.35rem; }
.plans h1 { margin: 0; }
.plans .sub { margin: 0.7rem 0 0; max-width: 32rem; color: var(--muted); }
.bill { display: inline-flex; align-items: center; gap: 0.2rem; flex-wrap: wrap; background: rgba(255,255,255,0.04); border: 1px solid var(--line); padding: 0.28rem; border-radius: 999px; }
.bill button { border: 0; background: transparent; color: var(--muted); border-radius: 999px; padding: 0.48rem 0.85rem; font-weight: 650; box-shadow: none; }
.bill button[aria-pressed="true"] { background: var(--amber); color: #1a1408; }
.save { display: inline-block; margin-left: 0.35rem; background: #1a1408; color: var(--amber-2); border-radius: 999px; font-size: 0.72rem; padding: 0.12rem 0.45rem; font-weight: 650; }
.bill button[aria-pressed="true"] .save { background: rgba(26, 20, 8, 0.16); color: #1a1408; }
.plan-board { display: grid; grid-template-columns: 1fr 1fr 1.08fr; gap: 0.8rem; align-items: stretch; }
.plan {
  background: linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.015));
  border: 1px solid var(--line);
  color: var(--ink);
  border-radius: 22px;
  padding: 1.35rem 1.25rem 1.15rem;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 50px rgba(0,0,0,0.22);
}
.plan.pop {
  background:
    radial-gradient(420px 180px at 80% 0%, rgba(240, 180, 41, 0.18), transparent 60%),
    linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02));
  border-color: rgba(240, 180, 41, 0.55);
}
.badge { align-self: flex-start; background: var(--amber); color: #1a1408; border-radius: 999px; font-size: 0.75rem; padding: 0.22rem 0.6rem; margin-bottom: 0.85rem; font-weight: 680; }
.plan .amt { margin: 0.15rem 0 0.15rem; font-family: "Iowan Old Style", Palatino, Georgia, serif; font-size: clamp(2.2rem, 4vw, 2.8rem); font-weight: 560; letter-spacing: -0.05em; line-height: 1; }
.plan .amt span { font-family: "Avenir Next", "Segoe UI", ui-sans-serif, system-ui, sans-serif; font-size: 1rem; font-weight: 560; color: var(--muted); letter-spacing: 0; }
.plan h2 { margin: 0.45rem 0 0.25rem; font-family: "Iowan Old Style", Palatino, Georgia, serif; font-size: 1.7rem; font-weight: 560; letter-spacing: -0.03em; }
.plan .blurb { margin: 0; color: var(--muted); min-height: 3.2rem; }
.plan .includes { margin: 1rem 0 0.35rem; font-weight: 650; color: var(--amber-2); }
.plan ul { list-style: none; padding: 0; margin: 0 0 1.2rem; }
.plan li { display: flex; align-items: flex-start; gap: 0.55rem; margin: 0.48rem 0; }
.tick { width: 1.15rem; height: 1.15rem; border-radius: 999px; background: rgba(240, 180, 41, 0.16); color: var(--amber); display: inline-grid; place-items: center; flex: none; font-size: 0.72rem; margin-top: 0.15rem; }
.plan form { margin-top: auto; }
.plan-btn, .plan form button { width: 100%; margin-top: auto; }
.plan-note { min-height: 1.3rem; margin: 0.8rem 0 0; color: var(--amber-2); font-size: 0.92rem; }
@media (max-width: 860px) {
  .hero, .sections, .controls, .price-grid, .searchbar { grid-template-columns: 1fr; }
  .bar { align-items: flex-start; flex-direction: column; padding: 0.75rem 1rem; gap: 0.55rem; }
  nav { width: 100%; }
  main { padding: 1.35rem 0.9rem 2.8rem; }
  h1 { font-size: clamp(2.05rem, 11vw, 3.1rem); }
  .lede, .plans .sub { font-size: 1rem; }
  .drop { min-height: 8.5rem; padding: 1rem; }
  .controls button, .searchbar button, .btn { width: 100%; }
  button, .btn { white-space: normal; }
  body.split { padding-right: 0; }
  body.split .drawer { width: 100%; border-left: 0; }
  pre { font-size: 0.82rem; white-space: pre-wrap; overflow-wrap: anywhere; }
  .pack { flex-direction: column; align-items: flex-start; gap: 0.25rem; }
  .card { grid-template-columns: auto 1fr; }
  .plan-board { grid-template-columns: 1fr; }
  .plans-top { flex-direction: column; align-items: flex-start; }
  .bill { width: 100%; }
  .bill button { flex: 1 1 auto; }
  .plan .blurb { min-height: 0; }
  .info .btn { margin-top: 0.2rem; }
}
@media (max-width: 420px) {
  .bar { padding: 0.65rem 0.75rem; }
  nav a { font-size: 0.84rem; padding: 0.32rem 0.5rem; }
  .plan { padding: 1.1rem 1rem 1rem; }
}
"""

_JS = r"""
<script>
(function () {
  var note = document.getElementById("note");
  var results = document.getElementById("results");
  var fileInput = document.getElementById("file");
  var fileLabel = document.getElementById("file-label");
  function say(text) { if (note) note.textContent = text || ""; }
  function trackLine(track) {
    var bits = [];
    if (track.artist) bits.push(track.artist);
    if (track.bpm) bits.push(track.bpm + " BPM");
    if (track.license) bits.push(track.license);
    if (track.moods && track.moods.length) bits.push(track.moods.join(", "));
    return bits.join(" · ");
  }
  function chip(text, extra) {
    var el = document.createElement("span");
    el.className = "chip" + (extra ? " " + extra : "");
    el.textContent = text;
    return el;
  }
  function paintTracks(tracks, kind) {
    results.textContent = "";
    results.className = "results";
    if (!tracks.length) {
      say("No matches in the catalog for that.");
      return;
    }
    say(tracks.length + (kind === "search" ? " catalog tracks" : " matches"));
    tracks.forEach(function (item, index) {
      var track = item.track || item;
      var card = document.createElement("article");
      card.className = "card";
      var rank = document.createElement("div");
      rank.className = "rank";
      rank.textContent = String(index + 1);
      var body = document.createElement("div");
      var title = document.createElement("h3");
      title.textContent = track.title || "Untitled";
      var meta = document.createElement("p");
      meta.className = "meta";
      meta.textContent = trackLine(track);
      body.appendChild(title);
      body.appendChild(meta);
      var chips = document.createElement("div");
      chips.className = "chips";
      if (track.license) chips.appendChild(chip(track.license, "lic"));
      if (track.instrumental) chips.appendChild(chip("Instrumental"));
      if (item.hook_out) chips.appendChild(chip("Hook " + item.hook_in + "–" + item.hook_out + "s"));
      if (item.ducking && item.ducking !== "off") chips.appendChild(chip("Ducking " + item.ducking));
      if (chips.childNodes.length) body.appendChild(chips);
      if (item.reason) {
        var why = document.createElement("p");
        why.className = "why";
        why.textContent = item.reason;
        body.appendChild(why);
      }
      if (track.attribution_text) {
        var attr = document.createElement("p");
        attr.className = "meta";
        attr.textContent = track.attribution_text;
        body.appendChild(attr);
      }
      if (track.preview_url) {
        var link = document.createElement("a");
        link.href = track.preview_url;
        link.textContent = "Preview";
        body.appendChild(link);
      }
      card.appendChild(rank);
      card.appendChild(body);
      results.appendChild(card);
    });
  }
  var drop = document.getElementById("drop");
  var thumb = document.getElementById("thumb");
  var urlInput = document.getElementById("url");
  var thumbUrl = "";
  function youtubeId(value) {
    var match = String(value || "").match(/(?:youtube\.com\/(?:watch\?v=|shorts\/|embed\/)|youtu\.be\/)([A-Za-z0-9_-]{6,})/);
    return match ? match[1] : "";
  }
  function showThumb(src) {
    if (!thumb || !drop || !src) return;
    thumb.hidden = false;
    thumb.src = src;
    drop.className = "drop has-thumb";
  }
  function clearThumb() {
    if (thumbUrl) URL.revokeObjectURL(thumbUrl);
    thumbUrl = "";
    if (thumb) {
      thumb.removeAttribute("src");
      thumb.hidden = true;
    }
    if (drop) drop.className = "drop";
  }
  function frameFromFile(file) {
    if (thumbUrl) URL.revokeObjectURL(thumbUrl);
    thumbUrl = URL.createObjectURL(file);
    var video = document.createElement("video");
    video.muted = true;
    video.playsInline = true;
    video.preload = "auto";
    video.src = thumbUrl;
    var painted = false;
    function paintFrame() {
      if (painted) return;
      var width = video.videoWidth || 0;
      var height = video.videoHeight || 0;
      if (!width || !height) return;
      var scale = Math.min(1, 720 / width);
      var canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(width * scale));
      canvas.height = Math.max(1, Math.round(height * scale));
      var ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      painted = true;
      showThumb(canvas.toDataURL("image/jpeg", 0.82));
      video.onerror = null;
      video.pause();
      video.removeAttribute("src");
      try { video.load(); } catch (err) {}
    }
    video.addEventListener("loadeddata", function () {
      var duration = video.duration;
      var at = duration && isFinite(duration) ? Math.min(1, duration * 0.12) : 0;
      if (at > 0.05) {
        try { video.currentTime = at; } catch (err) { paintFrame(); }
        return;
      }
      paintFrame();
    });
    video.addEventListener("seeked", paintFrame);
    video.addEventListener("error", function () {
      if (!painted) clearThumb();
    });
  }
  function previewLink() {
    var file = fileInput && fileInput.files && fileInput.files[0];
    if (file) return;
    var id = youtubeId(urlInput && urlInput.value);
    if (!id) {
      clearThumb();
      if (fileLabel) fileLabel.textContent = "Drop a clip or choose a file";
      return;
    }
    if (fileLabel) fileLabel.textContent = "YouTube clip";
    showThumb("https://i.ytimg.com/vi/" + id + "/hqdefault.jpg");
  }
  if (fileInput && fileLabel) {
    fileInput.addEventListener("change", function () {
      var file = fileInput.files && fileInput.files[0];
      fileLabel.textContent = file ? file.name : "Drop a clip or choose a file";
      if (file) frameFromFile(file);
      else previewLink();
    });
  }
  if (urlInput) urlInput.addEventListener("input", previewLink);
  var sampleButton = document.getElementById("use-sample");
  if (sampleButton && fileInput) {
    sampleButton.addEventListener("click", function () {
      sampleButton.disabled = true;
      fetch("/samples/sample-clip.mp4").then(function (res) {
        if (!res.ok) throw new Error("missing");
        return res.blob();
      }).then(function (blob) {
        var file = new File([blob], "sample-clip.mp4", { type: "video/mp4" });
        var bag = new DataTransfer();
        bag.items.add(file);
        fileInput.files = bag.files;
        fileInput.dispatchEvent(new Event("change"));
        if (urlInput) urlInput.value = "";
      }).catch(function () {
        say("The sample clip is not available.");
      }).then(function () {
        sampleButton.disabled = false;
      });
    });
  }
  if (thumb) {
    thumb.addEventListener("error", function () {
      if ((thumb.src || "").indexOf("ytimg.com") !== -1) clearThumb();
    });
  }
  function openDrawer(title) {
    var drawer = document.getElementById("drawer");
    var back = document.getElementById("drawer-back");
    var heading = document.getElementById("drawer-title");
    if (!drawer) return;
    if (heading && title) heading.textContent = title;
    drawer.className = "drawer open";
    drawer.setAttribute("aria-hidden", "false");
    document.body.classList.add("split");
    if (back) back.hidden = true;
  }
  function closeDrawer() {
    var drawer = document.getElementById("drawer");
    var back = document.getElementById("drawer-back");
    if (!drawer) return;
    drawer.className = "drawer";
    drawer.setAttribute("aria-hidden", "true");
    document.body.classList.remove("split");
    if (back) back.hidden = true;
  }
  var liveLattice = null;
  function mountLattice(parent) {
    var cells = [0, 1, 2, 7, null, 3, 6, 5, 4];
    var doneCells = [2, 3, 5, 7];
    var errorCells = [0, 2, 4, 6, 8];
    var stepMs = 90;
    var scale = 1.2;
    var delay = stepMs * scale;
    var cycle = Math.round(8 * delay);
    var status = "working";
    var started = performance.now();
    var frozen = 0;
    var root = document.createElement("span");
    root.className = "lattice-loader";
    root.setAttribute("role", "status");
    root.setAttribute("data-status", "working");
    root.setAttribute("data-shape", "round");
    root.style.setProperty("--ll-n", "3");
    root.style.setProperty("--ll-cell", "8px");
    root.style.setProperty("--ll-gap", "3px");
    root.style.setProperty("--ll-font", "16px");
    root.style.setProperty("--ll-color", "#f0b429");
    root.style.setProperty("--ll-mark", "#22c55e");
    root.style.setProperty("--ll-idle", "0.15");
    root.style.setProperty("--ll-cycle", cycle + "ms");
    var grid = document.createElement("span");
    grid.className = "lattice-loader__grid";
    grid.setAttribute("aria-hidden", "true");
    var run = document.createElement("span");
    run.className = "lattice-loader__layer lattice-loader__run";
    var mark = document.createElement("span");
    mark.className = "lattice-loader__layer lattice-loader__mark";
    cells.forEach(function (unit, index) {
      var cell = document.createElement("span");
      cell.className = "lattice-loader__cell";
      if (unit == null) cell.setAttribute("data-hole", "");
      else cell.style.animationDelay = Math.round(unit * delay) + "ms";
      run.appendChild(cell);
      var markCell = document.createElement("span");
      markCell.className = "lattice-loader__cell";
      mark.appendChild(markCell);
    });
    grid.appendChild(run);
    grid.appendChild(mark);
    var label = document.createElement("span");
    label.className = "lattice-loader__label";
    label.setAttribute("aria-hidden", "true");
    var workingText = document.createElement("span");
    workingText.className = "lattice-loader__text";
    workingText.setAttribute("data-active", "");
    workingText.textContent = "Reading frames";
    var doneText = document.createElement("span");
    doneText.className = "lattice-loader__text";
    doneText.textContent = "Done in";
    var errorText = document.createElement("span");
    errorText.className = "lattice-loader__text";
    errorText.textContent = "Failed after";
    label.appendChild(workingText);
    label.appendChild(doneText);
    label.appendChild(errorText);
    var timer = document.createElement("span");
    timer.className = "lattice-loader__timer";
    timer.setAttribute("aria-hidden", "true");
    timer.textContent = "0.0s";
    var sr = document.createElement("span");
    sr.className = "lattice-loader__sr";
    sr.textContent = "Reading frames, in progress";
    root.appendChild(grid);
    root.appendChild(label);
    root.appendChild(timer);
    root.appendChild(sr);
    parent.appendChild(root);
    function tenths() {
      return status === "working" ? Math.floor((performance.now() - started) / 100) : frozen;
    }
    function paintClock() {
      var ds = tenths();
      timer.textContent = ds < 600 ? (ds / 10).toFixed(1) + "s" : Math.floor(ds / 600) + "m " + ((ds % 600) / 10).toFixed(1) + "s";
    }
    var clock = setInterval(function () {
      if (status !== "working") return;
      paintClock();
    }, 100);
    function paintMark() {
      var on = status === "error" ? errorCells : doneCells;
      var nodes = mark.querySelectorAll(".lattice-loader__cell");
      for (var i = 0; i < nodes.length; i++) {
        if (on.indexOf(i) !== -1) nodes[i].setAttribute("data-on", "");
        else nodes[i].removeAttribute("data-on");
      }
      root.style.setProperty("--ll-mark", status === "error" ? "#ef4444" : "#22c55e");
    }
    return {
      status: function () { return status; },
      setLabel: function (text) {
        if (status !== "working") return;
        workingText.textContent = text;
        sr.textContent = text + ", in progress";
      },
      setStatus: function (next) {
        if (status !== "working") return;
        frozen = tenths();
        status = next === "error" ? "error" : "done";
        clearInterval(clock);
        paintClock();
        paintMark();
        root.setAttribute("data-status", status);
        workingText.removeAttribute("data-active");
        if (status === "error") errorText.setAttribute("data-active", "");
        else doneText.setAttribute("data-active", "");
        var spoken = frozen < 600 ? (frozen / 10).toFixed(1) + " seconds" : Math.floor(frozen / 600) + " minutes " + ((frozen % 600) / 10).toFixed(1) + " seconds";
        sr.textContent = (status === "error" ? "Failed after " : "Done in ") + spoken;
      }
    };
  }
  function showProcessing() {
    openDrawer("Processing");
    var body = document.getElementById("drawer-body");
    if (!body) return;
    body.textContent = "";
    var stage = document.createElement("div");
    stage.className = "lattice-stage";
    body.appendChild(stage);
    liveLattice = mountLattice(stage);
    var labels = ["Reading frames", "Reading sound", "Mapping the timeline"];
    var step = 0;
    var timer = setInterval(function () {
      var drawer = document.getElementById("drawer");
      if (!drawer || drawer.getAttribute("aria-hidden") === "true" || !liveLattice || liveLattice.status() !== "working") {
        clearInterval(timer);
        return;
      }
      step = (step + 1) % labels.length;
      liveLattice.setLabel(labels[step]);
    }, 1600);
  }
  function failProcess(message) {
    say(message);
    if (liveLattice && liveLattice.status() === "working") {
      liveLattice.setStatus("error");
      openDrawer("Process failed");
      var body = document.getElementById("drawer-body");
      if (!body) return;
      var detail = document.createElement("p");
      detail.className = "lattice-detail";
      detail.textContent = message;
      body.appendChild(detail);
      return;
    }
    openDrawer("Process failed");
    var fail = document.getElementById("drawer-body");
    if (fail) fail.textContent = message;
  }
  function agentText(data) {
    var lines = [
      location.origin + "/?t=" + (data.asset_id || ""),
      "Video " + (data.duration_label || "") + ". One BGM per span. Sound names are references only."
    ];
    (data.sections || []).forEach(function (section) {
      var bgm = section.bgm || {};
      var sfx = (section.sfx || []).map(function (item) { return item.name; }).join(", ");
      lines.push(section.label + " " + (section.name || "") + " — " + (bgm.title || "no bed") + " (" + (bgm.license || "see track") + "). SFX reference: " + (sfx || "none") + ".");
    });
    return lines.join("\n");
  }
  function copyText(text, button) {
    var done = function () {
      if (!button) return;
      var previous = button.textContent;
      button.textContent = "Copied";
      setTimeout(function () { button.textContent = previous; }, 1200);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(function () {
        var area = document.createElement("textarea");
        area.value = text;
        document.body.appendChild(area);
        area.select();
        try { document.execCommand("copy"); } catch (err) {}
        area.remove();
        done();
      });
      return;
    }
    var area = document.createElement("textarea");
    area.value = text;
    document.body.appendChild(area);
    area.select();
    try { document.execCommand("copy"); } catch (err) {}
    area.remove();
    done();
  }
  function vote(assetId, index, choice, button) {
    var key = "sonic-vote:" + assetId + ":" + index;
    var next = button.getAttribute("aria-pressed") === "true" ? "" : choice;
    var row = button.parentNode.querySelectorAll("button[data-vote]");
    for (var i = 0; i < row.length; i++) row[i].setAttribute("aria-pressed", "false");
    if (next) button.setAttribute("aria-pressed", "true");
    try { localStorage.setItem(key, next); } catch (err) {}
    if (!next) return;
    fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ asset_id: assetId, section: index, vote: next })
    }).catch(function () {});
  }
  function paintTimeline(data) {
    openDrawer(data.duration_label ? data.duration_label + " timeline" : "Timeline");
    var body = document.getElementById("drawer-body");
    if (!body) return;
    body.textContent = "";
    var copy = document.createElement("div");
    copy.className = "copy-row";
    var copyButton = document.createElement("button");
    copyButton.type = "button";
    copyButton.className = "btn";
    copyButton.textContent = "Copy link for agents";
    copyButton.addEventListener("click", function () { copyText(agentText(data), copyButton); });
    copy.appendChild(copyButton);
    body.appendChild(copy);
    var hint = document.createElement("p");
    hint.className = "meta";
    hint.textContent = "Frames come from scene cuts and the sound curve. Sound names are references, not files in the catalog.";
    body.appendChild(hint);
    (data.sections || []).forEach(function (section) {
      var card = document.createElement("article");
      card.className = "section-card";
      var title = document.createElement("h3");
      title.textContent = section.label + "  " + (section.name || "");
      var meta = document.createElement("p");
      meta.className = "meta";
      var bgm = section.bgm || {};
      meta.textContent = (bgm.title || "No bed yet") + (bgm.license ? " · " + bgm.license : "");
      card.appendChild(title);
      card.appendChild(meta);
      if (bgm.reason) {
        var why = document.createElement("p");
        why.className = "why";
        why.textContent = bgm.reason;
        card.appendChild(why);
      }
      if (section.alt && section.alt.title) {
        var alt = document.createElement("p");
        alt.className = "meta";
        alt.textContent = "Also " + section.alt.title;
        card.appendChild(alt);
      }
      var sfx = document.createElement("p");
      sfx.className = "meta";
      var names = (section.sfx || []).map(function (item) { return item.name; }).join(", ");
      sfx.textContent = "SFX reference: " + names;
      card.appendChild(sfx);
      var actions = document.createElement("div");
      actions.className = "actions";
      ["up", "down"].forEach(function (choice) {
        var button = document.createElement("button");
        button.type = "button";
        button.setAttribute("data-vote", choice);
        button.textContent = choice === "up" ? "Thumb up" : "Thumb down";
        var saved = "";
        try { saved = localStorage.getItem("sonic-vote:" + data.asset_id + ":" + section.index) || ""; } catch (err) { saved = ""; }
        if (saved === choice) button.setAttribute("aria-pressed", "true");
        button.addEventListener("click", function () { vote(data.asset_id, section.index, choice, button); });
        actions.appendChild(button);
      });
      card.appendChild(actions);
      body.appendChild(card);
    });
  }
  var matchForm = document.getElementById("match-form");
  if (matchForm) {
    matchForm.addEventListener("submit", function (event) {
      event.preventDefault();
      say("");
      showProcessing();
      var body = new FormData(matchForm);
      function finish(packed) {
        if (!packed.ok || packed.data.ok === false) {
          failProcess((packed.data && (packed.data.error || packed.data.message)) || "Process failed");
          return;
        }
        var timeline = packed.data.timeline || {};
        say(timeline.duration_label ? "Timeline ready · " + timeline.duration_label : "Timeline ready");
        if (liveLattice && liveLattice.status() === "working") liveLattice.setStatus("done");
        setTimeout(function () {
          var drawer = document.getElementById("drawer");
          if (!drawer || drawer.getAttribute("aria-hidden") === "true") return;
          paintTimeline(timeline);
        }, 700);
        if (timeline.asset_id && history.replaceState) {
          history.replaceState(null, "", "/?t=" + timeline.asset_id);
        }
      }
      function poll(jobId) {
        var drawer = document.getElementById("drawer");
        if (!drawer || drawer.getAttribute("aria-hidden") === "true") return;
        fetch("/api/match/" + jobId).then(function (res) {
          return res.json().then(function (data) { return { ok: res.ok, data: data }; });
        }).then(function (packed) {
          if (packed.data && packed.data.status === "working") {
            setTimeout(function () { poll(jobId); }, 2000);
            return;
          }
          finish(packed);
        }).catch(function () {
          failProcess("The download took too long and the page closed. Upload the clip instead.");
        });
      }
      fetch("/api/match", { method: "POST", body: body }).then(function (res) {
        return res.json().then(function (data) { return { ok: res.ok, data: data }; });
      }).then(function (packed) {
        if (packed.data && packed.data.job_id && packed.data.status === "working") {
          poll(packed.data.job_id);
          return;
        }
        finish(packed);
      }).catch(function () {
        failProcess("The download took too long and the page closed. Upload the clip instead.");
      });
    });
  }
  var closer = document.getElementById("drawer-close");
  var back = document.getElementById("drawer-back");
  if (closer) closer.addEventListener("click", closeDrawer);
  if (back) back.addEventListener("click", closeDrawer);
  var params = new URLSearchParams(location.search);
  var existing = params.get("t") || "";
  if (/^[a-f0-9]{16}$/.test(existing)) {
    fetch("/api/timeline/" + existing).then(function (res) { return res.json(); }).then(function (data) {
      if (data && data.sections) paintTimeline(data);
    }).catch(function () {});
  }
})();
</script>
"""


def _header(current: str = "home") -> str:
    def item(href: str, label: str, key: str) -> str:
        current_attr = ' aria-current="page"' if key == current else ""
        return f'<a href="{href}"{current_attr}>{html.escape(label)}</a>'

    return f"""<header class="bar">
  <a class="brand" href="/"><span class="mark" aria-hidden="true"></span>Sonic</a>
  <nav>
    {item("/", "Home", "home")}
    {item("/open-source", "Open source", "open-source")}
    {item("/pricing", "Pricing", "pricing")}
  </nav>
</header>"""


def _shell(title: str, body: str, current: str = "home", theme: str = "") -> str:
    klass = f' class="{html.escape(theme)}"' if theme else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="{_FAVICON}" type="image/svg+xml">
<title>{html.escape(title)}</title>
<style>{_CSS}</style>
</head>
<body{klass}>
{_header(current)}
<main>
{body}
</main>
</body>
</html>
"""


def render_home() -> str:
    body = f"""
  <div class="board">
  <div class="work">
  <section class="hero">
    <div>
      <p class="kicker">License on every row</p>
      <h1>Match the footage to a track</h1>
      <p class="lede">Drop a clip, paste a public link, or load the sample. Sonic watches the picture and lists the music that fits, with the license on every match.</p>
    </div>
  </section>
  <form id="match-form" class="stage" action="/api/match" method="post" enctype="multipart/form-data">
    <div class="drop" id="drop">
      <input id="file" name="file" type="file" accept="video/mp4,video/quicktime,video/webm,video/x-matroska,.mp4,.mov,.webm,.mkv,.m4v">
      <img id="thumb" class="thumb" alt="" hidden>
      <div class="caption">
        <strong id="file-label">Drop a clip or choose a file</strong>
        <span>mp4, mov, webm, mkv</span>
      </div>
    </div>
    <p class="sample-row"><button type="button" id="use-sample">Use the sample clip</button></p>
    <p class="or">or</p>
    <div class="controls">
      <div>
        <label for="url">Public https link</label>
        <input id="url" name="url" type="url" placeholder="https://">
      </div>
      <button type="submit">Process</button>
    </div>
  </form>
  <p id="note" class="note" role="status"></p>
  </div>
  <div id="drawer-back" class="drawer-back" hidden></div>
  <aside id="drawer" class="drawer" aria-hidden="true">
    <div class="drawer-head">
      <h2 id="drawer-title">Processing</h2>
      <button type="button" id="drawer-close" class="ghost">Close</button>
    </div>
    <div id="drawer-body" class="drawer-body"></div>
  </aside>
  </div>
  {_JS}
"""
    return _shell("Sonic — match music to the footage", body)


def render_open_source() -> str:
    repo = html.escape(GITHUB_REPO)
    body = f"""
  <section class="hero">
    <div>
      <p class="kicker">MIT</p>
      <h1>Open source</h1>
      <p class="lede">The matcher is free to run yourself. The hosted credit meter does not apply when you run the repo on your own machine.</p>
    </div>
  </section>
  <article class="info">
    <h2>Run it</h2>
    <pre>uvx --from git+{repo}.git sonicmatch-mcp</pre>
    <p><a class="btn" href="{repo}">View on GitHub</a></p>
    <p class="hint">Track licenses stay on each track. The code license is MIT.</p>
  </article>
"""
    return _shell("Sonic — open source", body, current="open-source")


def _ticks(items: list[str]) -> str:
    rows = []
    for item in items:
        rows.append(f"<li><span class=\"tick\" aria-hidden=\"true\">✓</span>{html.escape(item)}</li>")
    return "\n".join(rows)


def render_pricing() -> str:
    body = f"""
  <section class="plans">
    <div class="plans-top">
      <div>
        <h1>Plans &amp; Pricing</h1>
        <p class="sub">Pick a credit pack for hosted calls. The website process stays open, and the matcher itself is free to run.</p>
      </div>
      <div class="bill" role="group" aria-label="Billing period">
        <button type="button" id="bill-month" aria-pressed="true">Monthly</button>
        <button type="button" id="bill-year" aria-pressed="false">Yearly <span class="save">Save 20%</span></button>
      </div>
    </div>
    <div class="plan-board">
      <article class="plan">
        <p class="amt"><strong data-month="$0" data-year="$0">$0</strong><span>/month</span></p>
        <h2>Trial</h2>
        <p class="blurb">Try a clip on the site before you put the matcher on an agent.</p>
        <p class="includes">Free includes:</p>
        <ul>
          {_ticks([f"{TRIAL_CREDITS} credits", "Upload or a public link", "Timeline in the drawer"])}
        </ul>
        <form method="post" action="/v1/trial"><button type="submit">Get started</button></form>
      </article>
      <article class="plan">
        <p class="amt"><strong data-month="$9" data-year="$7">$9</strong><span>/month</span></p>
        <h2>Reel</h2>
        <p class="blurb">For editors who want hosted matches without running the server.</p>
        <p class="includes">Everything in Trial, plus:</p>
        <ul>
          {_ticks(["500 credits", "Hosted agent calls", "Copy link for agents"])}
        </ul>
        <button type="button" class="plan-btn" data-plan="Reel">Get started</button>
      </article>
      <article class="plan pop">
        <span class="badge">Popular</span>
        <p class="amt"><strong data-month="$39" data-year="$31">$39</strong><span>/month</span></p>
        <h2>Studio</h2>
        <p class="blurb">The larger pack when a batch of clips needs its own timeline.</p>
        <p class="includes">Everything in Reel, plus:</p>
        <ul>
          {_ticks(["3000 credits", "Section-by-section BGM", "Sound references on the timeline"])}
        </ul>
        <button type="button" class="plan-btn" data-plan="Studio">Get started</button>
      </article>
    </div>
    <p id="plan-note" class="plan-note" role="status"></p>
  </section>
  <script>
  (function () {{
    var month = document.getElementById("bill-month");
    var year = document.getElementById("bill-year");
    var note = document.getElementById("plan-note");
    function setPeriod(yearly) {{
      if (month) month.setAttribute("aria-pressed", yearly ? "false" : "true");
      if (year) year.setAttribute("aria-pressed", yearly ? "true" : "false");
      var nodes = document.querySelectorAll(".amt strong");
      for (var i = 0; i < nodes.length; i++) {{
        nodes[i].textContent = nodes[i].getAttribute(yearly ? "data-year" : "data-month") || "";
      }}
    }}
    if (month) month.addEventListener("click", function () {{ setPeriod(false); }});
    if (year) year.addEventListener("click", function () {{ setPeriod(true); }});
    var buttons = document.querySelectorAll(".plan-btn");
    for (var j = 0; j < buttons.length; j++) {{
      buttons[j].addEventListener("click", function (event) {{
        var name = event.currentTarget.getAttribute("data-plan") || "This pack";
        if (note) note.textContent = name + " checkout is not connected yet. Start with the trial key.";
      }});
    }}
  }})();
  </script>
"""
    return _shell("Sonic — pricing", body, current="pricing")


def render_key(raw_key: str, credits: int) -> str:
    body = f"""
  <h1>Trial key</h1>
  <p>{credits} credits. This is the only time this key is shown.</p>
  <pre>{html.escape(raw_key)}</pre>
  <pre>export SONICMATCH_API_KEY={html.escape(raw_key)}</pre>
  <p><a href="{html.escape(cursor_install_link())}">Add to Cursor</a></p>
  <p><a href="/">Back to match</a></p>
"""
    return _shell("Sonic trial key", body, current="pricing")


def render_message(title: str, body: str, status_hint: str = "") -> str:
    extra = f"<p>{html.escape(status_hint)}</p>" if status_hint else ""
    inner = f"<h1>{html.escape(title)}</h1><p>{html.escape(body)}</p>{extra}<p><a href=\"/\">Back to match</a></p>"
    return _shell(title, inner)


_ = INSTALL_CONFIG

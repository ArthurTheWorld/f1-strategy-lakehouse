"""Replay da corrida: cada piloto é uma marca que anda pela diferença real para o líder.

Os dados vêm de `silver.stg_laps`: tempos de volta acumulados e posição oficial ao fim de cada volta.
A animação só move marcas com `transform`, pausa fora da tela e começa parada na posição final quando
o sistema pede movimento reduzido.
"""

from __future__ import annotations

import html
import json

import pandas as pd

MAX_GAP_S = 120
ROW_H = 12
CHROME_H = 96


def payload(laps: pd.DataFrame, race_median_s: float, colors: dict[str, str]) -> dict:
    """Monta tempos acumulados por piloto. Volta sem tempo usa a mediana do pelotão naquela volta."""
    d = laps.sort_values(["driver", "lap_number"]).copy()
    d["lap_time_s"] = d["lap_time_s"].fillna(d.groupby("lap_number")["lap_time_s"].transform("median")).fillna(race_median_s)
    d["cum"] = d.groupby("driver")["lap_time_s"].cumsum()
    computed = d.groupby("lap_number")["cum"].rank(method="first")
    d["pos"] = d["position"].fillna(computed).astype(int)
    drivers = [
        {
            "c": str(code),
            "k": colors.get(str(g["team"].iloc[0]), "#9da2a8"),
            "t": [0.0, *[round(float(v), 3) for v in g["cum"]]],
            "p": [int(v) for v in g["pos"]],
            "s": [int(v) for v in g.loc[g["pit_in_time_s"].notna(), "lap_number"]],
        }
        for code, g in d.groupby("driver", sort=True)
    ]
    return {"n": int(d["lap_number"].max()), "d": drivers}


_CSS = """
:root{--paper:#0d1013;--paper-2:#15191c;--paper-3:#06080b;--ink:#eceff2;--muted:#9da2a8;--rule:#2d3135;--rule-2:#484e54;--amber:#f7b83d;
  --font:'Host Grotesk',system-ui,sans-serif;--mono:'Atkinson Hyperlegible Mono',Consolas,monospace;--dur:220ms;--ease:cubic-bezier(.16,1,.3,1)}
*{box-sizing:border-box}
html,body{margin:0;height:100%;overflow-x:clip;background:var(--paper);color:var(--ink);font:400 12px/1 var(--font)}
#replay{height:100%;display:flex;flex-direction:column;gap:10px;padding:12px 14px;border:1px solid var(--rule);border-radius:10px;background:var(--paper-2)}
.bar{display:flex;align-items:center;gap:12px}
button{min-height:32px;padding:0 12px;border:1px solid var(--rule-2);border-radius:6px;background:var(--paper-2);color:var(--ink);font:500 13px var(--font);cursor:pointer;transition:background-color var(--dur) var(--ease)}
@media (hover:hover) and (pointer:fine){button:hover{background:var(--rule)}}
button:active{background:var(--rule-2)}
:focus-visible{outline:2px solid var(--amber);outline-offset:2px}
input[type=range]{flex:1;min-width:0;height:32px;margin:0;accent-color:var(--amber);cursor:pointer}
#lap{flex:none;white-space:nowrap;text-align:right;font:400 14px var(--mono);font-variant-numeric:tabular-nums slashed-zero}
#plot{position:relative;flex:1;min-height:0;margin-left:38px}
.grid{position:absolute;top:0;bottom:0;width:1px;background:var(--rule)}
.row{position:absolute;left:-38px;right:0;top:0;height:12px;transition:transform var(--dur) var(--ease)}
.row span{position:absolute;left:0;top:0;width:32px;font:500 11px/12px var(--font);color:var(--muted)}
.row i{position:absolute;left:-4px;top:2px;width:8px;height:8px;border-radius:50%;background:var(--k);will-change:transform}
.track{position:absolute;left:38px;right:0;top:0;bottom:0}
.row.pit i{box-shadow:0 0 0 2px var(--amber)}
.row.out{opacity:.35}
#axis{position:relative;height:14px;margin-left:38px;font:400 12px/14px var(--mono);color:var(--muted)}
#axis b{position:absolute;font-weight:400;transform:translateX(-50%)}
#axis b:first-child{transform:none}#axis b:last-of-type{transform:translateX(-100%)}
#note{font-size:12px;color:var(--muted)}
@media (prefers-reduced-motion:reduce){.row,button{transition:none}}
"""

_JS = """
const D = JSON.parse(document.getElementById("data").textContent), MAX = %MAX%, ROW = %ROW%, FULL_MS = 45000;
const plot = document.getElementById("plot"), axis = document.getElementById("axis"), btn = document.getElementById("play"),
  range = document.getElementById("range"), lapEl = document.getElementById("lap");
for (const s of [0, 30, 60, 90, MAX]) {
  const g = document.createElement("div"); g.className = "grid"; g.style.left = s / MAX * 100 + "%"; plot.append(g);
  const b = document.createElement("b"); b.textContent = s + (s === MAX ? "+ s" : ""); b.style.left = s / MAX * 100 + "%"; axis.append(b);
}
const drivers = D.d.map(d => {
  const row = document.createElement("div"); row.className = "row"; row.style.setProperty("--k", d.k);
  const code = document.createElement("span"); code.textContent = d.c;
  const track = document.createElement("div"); track.className = "track";
  const dot = document.createElement("i"); track.append(dot); row.append(code, track); plot.append(row);
  return {...d, row, dot, last: d.t[d.t.length - 1], y: -1, x: -1, pit: false, out: false};
});
const total = Math.max(...drivers.map(d => d.last));
function progress(d, t) {
  t = Math.min(t, d.last);
  let lo = 0, hi = d.t.length - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (d.t[m] <= t) lo = m; else hi = m; }
  return lo + (hi > lo ? (t - d.t[lo]) / (d.t[hi] - d.t[lo]) : 0);
}
function timeAt(d, p) {
  const i = Math.min(Math.floor(p), d.t.length - 1), j = Math.min(i + 1, d.t.length - 1);
  return d.t[i] + (d.t[j] - d.t[i]) * (p - i);
}
let width = plot.clientWidth;
new ResizeObserver(() => { width = plot.clientWidth; for (const d of drivers) d.x = -1; draw(); }).observe(plot);
let time = 0;
function draw() {
  const states = drivers.map(d => ({d, prog: progress(d, time)}));
  // Quem chegou primeiro ao ponto mais avançado: no fim da corrida vários empatam na última volta.
  const lead = states.reduce((a, b) => b.prog > a.prog || (b.prog === a.prog && b.d.last < a.d.last) ? b : a);
  const lap = Math.floor(lead.prog);
  const ordered = states.map(s => {
    const out = time > s.d.last && s.d.t.length - 1 < D.n;
    const i = Math.max(0, Math.min(lap, s.d.p.length) - 1);
    return {...s, out, pos: s.d.p[lap ? i : 0]};
  }).sort((a, b) => a.out - b.out || a.pos - b.pos || a.d.c.localeCompare(b.d.c));
  ordered.forEach((s, rank) => {
    const d = s.d, gap = Math.max(0, Math.min(time, d.last) - timeAt(lead.d, s.prog));
    const x = Math.round(Math.min(gap, MAX) / MAX * width), y = rank * ROW;
    if (x !== d.x) { d.x = x; d.dot.style.transform = `translate3d(${x}px,0,0)`; }
    if (y !== d.y) { d.y = y; d.row.style.transform = `translate3d(0,${y}px,0)`; }
    const pit = d.s.includes(lap + 1);
    if (pit !== d.pit) { d.pit = pit; d.row.classList.toggle("pit", pit); }
    if (s.out !== d.out) { d.out = s.out; d.row.classList.toggle("out", s.out); }
  });
  lapEl.textContent = `Volta ${Math.min(lap + (time < total ? 1 : 0), D.n)}/${D.n}`;
  range.value = Math.round(time / total * 1000);
}
let playing = false, visible = true, raf = 0, last = 0;
function frame(now) {
  const dt = Math.min(100, now - last); last = now;
  time = Math.min(total, time + dt / FULL_MS * total);
  draw();
  if (time >= total) { setPlaying(false); return; }
  raf = requestAnimationFrame(frame);
}
function sync() {
  cancelAnimationFrame(raf); raf = 0;
  if (playing && visible) { last = performance.now(); raf = requestAnimationFrame(frame); }
}
function setPlaying(on) { playing = on; btn.textContent = on ? "Pausar" : time >= total ? "Rever" : "Reproduzir"; sync(); }
btn.addEventListener("click", () => { if (!playing && time >= total) time = 0; setPlaying(!playing); });
range.addEventListener("input", () => { setPlaying(false); time = range.value / 1000 * total; draw(); btn.textContent = "Reproduzir"; });
new IntersectionObserver(e => { visible = e[0].isIntersecting; sync(); }).observe(document.getElementById("replay"));
if (matchMedia("(prefers-reduced-motion: reduce)").matches) { time = total; draw(); setPlaying(false); }
else { draw(); setPlaying(true); }
"""


def height(data: dict) -> int:
    return CHROME_H + ROW_H * len(data["d"])


def replay_html(data: dict, circuit: str) -> str:
    blob = json.dumps(data, separators=(",", ":")).replace("<", "\\u003c")
    js = _JS.replace("%MAX%", str(MAX_GAP_S)).replace("%ROW%", str(ROW_H))
    fonts = "https://fonts.googleapis.com/css2?family=Host+Grotesk:wght@400;500&family=Atkinson+Hyperlegible+Mono&display=swap"
    return (
        f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><link href='{fonts}' rel='stylesheet'><style>{_CSS}</style></head><body>"
        f"<div id='replay' role='group' aria-label='Replay da corrida em {html.escape(circuit)}'>"
        "<div class='bar'><button id='play' type='button'>Reproduzir</button>"
        "<input id='range' type='range' min='0' max='1000' value='0' aria-label='Momento da corrida'><div id='lap'></div></div>"
        "<div id='plot'></div><div id='axis'></div><div id='note'>Diferença para o líder. Anel âmbar: volta de parada.</div>"
        f"<noscript>O replay precisa de JavaScript.</noscript></div><script type='application/json' id='data'>{blob}</script><script>{js}</script></body></html>"
    )

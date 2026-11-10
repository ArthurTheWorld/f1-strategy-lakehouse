"""Cena 2D do topo do dashboard: carro em SVG e pista com parallax.

O carro é genérico, desenhado à mão em SVG e pintado só com a cor da equipe: sem logo nem réplica de modelo real.
Tudo fica no próprio HTML (sem internet). As camadas e as rodas animam só `transform`, a cena pausa fora da
tela e fica parada quando o sistema pede movimento reduzido.
"""

from __future__ import annotations

import html
import random
import zlib

CAR_VIEWBOX = "0 0 1000 280"
REAR_X, FRONT_X, WHEEL_Y, WHEEL_R = 190, 830, 198, 64
TILE = 1600  # largura de cada ladrilho das camadas; múltiplo dos padrões para não haver emenda

_DEFS = """
<defs>
  <linearGradient id="shade" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#fff" stop-opacity=".3"/>
    <stop offset=".38" stop-color="#fff" stop-opacity="0"/>
    <stop offset="1" stop-color="#000" stop-opacity=".58"/>
  </linearGradient>
  <linearGradient id="carbon" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#2a2a2e"/><stop offset="1" stop-color="#0d0d0f"/>
  </linearGradient>
  <linearGradient id="visor" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#111"/><stop offset="1" stop-color="#55555c"/>
  </linearGradient>
</defs>
"""

_BODY = "M128 178 L230 150 C300 122 370 84 420 68 L478 66 L490 100 L590 112 C660 120 740 150 800 168 L960 196 C985 202 985 214 965 216 L760 222 L300 232 L130 222 Z"
_POD = "M300 160 C350 135 520 130 585 150 L622 150 C632 175 626 215 610 228 L310 232 Z"

_CAR = f"""
{_DEFS}
<g class="line">
  <!-- braços de suspensão, atrás das rodas -->
  <path d="M262 168 L190 182 M262 212 L190 212 M236 190 L190 150" fill="none" stroke="#55555c" stroke-width="4"/>
  <path d="M772 172 L830 182 M762 214 L830 214 M780 200 L830 150" fill="none" stroke="#55555c" stroke-width="4"/>
  <!-- assoalho e difusor -->
  <path d="M118 238 L752 234 L760 244 L132 250 Z" fill="url(#carbon)"/>
  <path d="M118 206 L150 206 L150 240 L128 248 Z" fill="url(#carbon)"/>
  <!-- asa traseira -->
  <path d="M104 120 L168 168 M60 168 L130 178" fill="none" stroke="#3c3c42" stroke-width="7"/>
  <path d="M26 62 L112 56 L118 184 L44 196 Z" fill="url(#carbon)" stroke="#3c3c42" stroke-width="1.5"/>
  <path d="M30 78 L112 68 L112 84 L34 96 Z" fill="var(--team)"/>
  <path d="M34 58 L112 48 L112 60 L36 72 Z" fill="var(--team)"/>
  <!-- barbatana da tampa do motor -->
  <path d="M190 156 L300 76 L420 66 L420 76 L306 92 L208 156 Z" fill="url(#carbon)" opacity=".9"/>
  <!-- carroceria -->
  <path d="{_BODY}" fill="var(--team)"/>
  <path d="{_BODY}" fill="url(#shade)"/>
  <path d="M230 150 C300 122 370 84 420 68 L478 66" fill="none" stroke="#fff" stroke-opacity=".45" stroke-width="1.5"/>
  <!-- sidepod, entrada e guelras -->
  <path d="{_POD}" fill="var(--team)"/>
  <path d="{_POD}" fill="url(#shade)"/>
  <path d="M300 160 C350 135 520 130 585 150" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="1.5"/>
  <path d="M590 150 L622 150 L628 200 L600 190 Z" fill="#08080a"/>
  <path d="M352 158 L372 182 M382 152 L402 180 M412 148 L432 178 M442 146 L462 176" fill="none" stroke="#000" stroke-opacity=".55" stroke-width="4" stroke-linecap="round"/>
  <!-- linhas de painel -->
  <path d="M700 150 L700 220 M240 160 L240 228 M520 224 L520 232" fill="none" stroke="#000" stroke-opacity=".4" stroke-width="1.5"/>
  <!-- entrada de ar e cockpit -->
  <path d="M470 68 L488 68 L494 100 L474 100 Z" fill="#08080a"/>
  <path d="M492 102 L596 112 L600 122 L494 120 Z" fill="#08080a"/>
  <!-- capacete -->
  <circle cx="538" cy="92" r="25" fill="#f0f0f2"/>
  <path d="M540 80 L563 84 C564 92 563 98 560 101 L540 98 Z" fill="url(#visor)"/>
  <path d="M514 94 C526 110 546 116 561 112" fill="none" stroke="#9c9ca3" stroke-width="2"/>
  <!-- halo -->
  <path d="M488 92 C520 66 588 66 626 92 L612 122" fill="none" stroke="#17171a" stroke-width="9" stroke-linejoin="round"/>
  <path d="M492 88 C522 66 586 66 622 89" fill="none" stroke="#6b6b73" stroke-width="1.5"/>
  <!-- retrovisor e câmera -->
  <path d="M634 124 L650 116" stroke="#17171a" stroke-width="4"/>
  <path d="M642 110 l28 -4 l2 11 l-27 4 z" fill="url(#carbon)" stroke="#55555c" stroke-width="1"/>
  <path d="M742 148 l28 6 l-2 7 l-28 -6 z" fill="url(#carbon)"/>
  <!-- asa dianteira -->
  <path d="M905 212 L915 240 M936 214 L944 238" stroke="#17171a" stroke-width="6"/>
  <path d="M858 248 L982 240 M866 238 L982 228 M878 228 L982 218" fill="none" stroke="var(--team)" stroke-width="6" stroke-linecap="round"/>
  <path d="M900 216 L986 222 L986 256 L900 256 Z" fill="url(#carbon)" stroke="#3c3c42" stroke-width="1.5"/>
</g>
"""


def _wheel() -> str:
    """Roda centrada em (0,0). A marca assimétrica no aro é o que deixa o giro visível."""
    spokes = "".join(
        f'<rect x="-3" y="-36" width="6" height="27" fill="#a5a5ad" transform="rotate({a})"/>' for a in range(0, 360, 60)
    )
    return (
        f'<circle r="{WHEEL_R}" fill="#0b0b0d"/>'
        f'<circle r="{WHEEL_R - 1}" fill="none" stroke="#333338" stroke-width="2"/>'
        '<circle r="51" fill="none" stroke="#6b6b73" stroke-width="1.5" stroke-dasharray="46 14"/>'
        '<circle r="39" fill="#17171a" stroke="#a5a5ad" stroke-width="3"/>'
        f"{spokes}"
        '<rect x="-4" y="-47" width="8" height="10" rx="2" fill="#f3f3f4"/>'
        '<circle r="11" fill="#f3f3f4"/><circle r="4" fill="#17171a"/>'
    )


def _svg(body: str, height: int) -> str:
    return f'<svg width="{TILE}" height="{height}" viewBox="0 0 {TILE} {height}" aria-hidden="true">{body}</svg>'


def _skyline(rng: random.Random) -> str:
    h = 150
    parts = []
    x = 30
    while x < TILE - 130:
        w, top = rng.randint(50, 120), rng.randint(62, 122)
        parts.append(f'<rect x="{x}" y="{top}" width="{w}" height="{h - top}" fill="#111113" stroke="#242428"/>')
        x += w + rng.randint(4, 70)
    for mast in range(120, TILE, 400):
        parts.append(
            f'<path d="M{mast} {h} V34" stroke="#2c2c31" stroke-width="2"/>'
            f'<rect x="{mast - 18}" y="24" width="36" height="12" fill="#1b1b1f" stroke="#3c3c42"/>'
        )
    return _svg("".join(parts), h)


def _stands(rng: random.Random) -> str:
    h = 112
    parts = []
    for x in range(40, TILE - 200, 520):
        w = rng.randint(330, 440)
        parts.append(f'<path d="M{x} {h} L{x + 24} 34 H{x + w - 24} L{x + w} {h} Z" fill="#0e0e10" stroke="#333338"/>')
        parts.append(f'<path d="M{x + 10} 28 H{x + w - 10} L{x + w - 4} 18 H{x + 4} Z" fill="#1a1a1e" stroke="#44444a"/>')
        for row in range(44, h - 6, 11):
            parts.append(f'<path d="M{x + 18} {row} H{x + w - 18}" stroke="#222226"/>')
            for seat in range(x + 26, x + w - 26, 9):
                if rng.random() < 0.62:
                    tone = rng.choice(("#55555c", "#77777f", "#a5a5ad"))
                    parts.append(f'<circle cx="{seat}" cy="{row - 3}" r="1.5" fill="{tone}"/>')
    return _svg("".join(parts), h)


def _fence() -> str:
    h = 74
    pattern = (
        '<defs><pattern id="mesh" width="20" height="20" patternUnits="userSpaceOnUse">'
        '<path d="M0 0 L20 20 M20 0 L0 20" stroke="#fff" stroke-opacity=".08"/></pattern></defs>'
    )
    boards = "".join(
        f'<rect x="{x}" y="44" width="150" height="30" fill="#17171a" stroke="#333338"/>'
        f'<path d="M{x + 14} 54 H{x + 112} M{x + 14} 64 H{x + 72}" stroke="#44444a" stroke-width="3"/>'
        for x in range(10, TILE, 200)
    )
    posts = "".join(f'<rect x="{x}" y="0" width="3" height="{h}" fill="#44444a"/>' for x in range(0, TILE, 80))
    body = f'{pattern}<rect width="{TILE}" height="44" fill="url(#mesh)"/><rect width="{TILE}" height="2" fill="#55555c"/>{posts}{boards}'
    return _svg(body, h)


def _road() -> str:
    h = 58
    kerb = "".join(
        f'<rect x="{x}" y="4" width="40" height="9" fill="{"#e8e8e8" if x % 80 == 0 else "#26262a"}"/>'
        for x in range(0, TILE, 40)
    )
    dashes = "".join(f'<rect x="{x}" y="38" width="90" height="3" fill="#3c3c42"/>' for x in range(30, TILE, 200))
    body = f'<rect width="{TILE}" height="{h}" fill="#101012"/><rect width="{TILE}" height="2" fill="#ff2db4"/>{kerb}{dashes}'
    return _svg(body, h)


def _streaks(rng: random.Random) -> str:
    h = 30
    parts = [
        f'<rect x="{rng.randint(0, TILE - 200)}" y="{rng.randint(3, h - 3)}" width="{rng.randint(50, 180)}" height="1.5" fill="#fff" opacity="{rng.uniform(0.08, 0.2):.2f}"/>'
        for _ in range(12)
    ]
    return _svg("".join(parts), h)


_TOKENS = ":root{--paper:#0d1013;--paper-2:#15191c;--paper-3:#06080b;--ink:#eceff2;--ink-2:#c3c8cc;--muted:#9da2a8;--rule:#2d3135;--rule-2:#484e54;--font:'Host Grotesk',system-ui,sans-serif}"
_FONT_LINK = "<link href='https://fonts.googleapis.com/css2?family=Host+Grotesk:wght@400;500&display=swap' rel='stylesheet'>"
# Tudo passa pelos tokens do tema Console: os tons do desenho viram variáveis na saída.
_TONES = {
    "paper-3": "#0b0b0d #08080a #0d0d0f #0e0e10 #101012",
    "paper-2": "#111113 #17171a #1a1a1e #1b1b1f",
    "paper": "#09090a",
    "rule": "#222226 #242428 #26262a #2a2a2e #2b2b2f #2c2c31 #333338",
    "rule-2": "#3c3c42 #44444a #4a4a50 #55555c #ff2db4",
    "muted": "#6b6b73 #77777f #9c9ca3",
    "ink-2": "#a5a5ad #e8e8e8",
    "ink": "#f0f0f2 #f3f3f4",
}


def _tone(markup: str) -> str:
    for token, values in _TONES.items():
        for value in values.split():
            markup = markup.replace(value, f"var(--{token})")
    return markup.replace("#111", "var(--paper-3)").replace("#fff", "var(--ink)").replace("#000", "var(--paper-3)")


_CSS = """
*{box-sizing:border-box}
html,body{margin:0;height:100%;overflow:hidden;background:#09090a}
#scene{position:relative;height:100%;overflow:hidden;border:1px solid #2b2b2f;border-radius:10px;
  background:#09090a;animation:appear 240ms cubic-bezier(.23,1,.32,1) both}
.layer{position:absolute;left:-60px;right:-60px;will-change:transform;line-height:0}
.run{display:flex;width:max-content;will-change:transform;animation:scroll var(--t) linear infinite}
.run svg{flex:none;display:block}
.vignette{position:absolute;inset:0;pointer-events:none;
  background:linear-gradient(90deg,#09090a 0,transparent 16%,transparent 84%,#09090a 100%)}
#car{position:absolute;left:50%;bottom:14px;width:min(500px,62%);margin-left:calc(min(500px,62%) / -2);will-change:transform}
#enter{animation:enter 420ms cubic-bezier(.23,1,.32,1) both}
#bob{position:relative;animation:bob 1.7s cubic-bezier(.45,0,.55,1) infinite alternate}
#bob>svg.body{display:block;width:100%;height:auto}
.wheel{position:absolute;width:12.8%;top:47.86%;aspect-ratio:1;animation:spin var(--w) linear infinite;will-change:transform}
.wheel.rear{left:12.6%}.wheel.front{left:76.6%}
.shadow{position:absolute;left:4%;right:0;bottom:2%;height:12%;background:radial-gradient(closest-side,#000,transparent)}
.tag{position:absolute;left:18px;top:14px;font:500 12px/1.5 var(--font);color:#9c9ca3;z-index:5}
.tag b{display:block;font-weight:500;font-size:14px;color:#f3f3f4}
.tag i{display:inline-block;width:9px;height:9px;margin-right:8px;background:var(--team)}
.paused *{animation-play-state:paused!important}
@keyframes scroll{to{transform:translate3d(-1600px,0,0)}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes bob{from{transform:translate3d(0,0,0)}to{transform:translate3d(0,1.5px,0)}}
@keyframes enter{from{opacity:0;transform:translate3d(-5%,0,0)}to{opacity:1;transform:none}}
@keyframes appear{from{opacity:0}to{opacity:1}}
@media (prefers-reduced-motion:reduce){.run,.wheel,#bob,#enter{animation:none}}
"""

_JS = """
const root = document.documentElement;
new IntersectionObserver(e => root.classList.toggle("paused", !e[0].isIntersecting)).observe(document.getElementById("scene"));
const still = matchMedia("(prefers-reduced-motion: reduce)").matches, fine = matchMedia("(hover: hover) and (pointer: fine)").matches;
if (!still && fine) {
  const items = [...document.querySelectorAll("[data-depth]")].map(el => ({el, depth: +el.dataset.depth}));
  let x = 0, target = 0, last = 0, raf = 0;
  const frame = now => {
    const dt = Math.min(.05, (now - last) / 1000 || .016); last = now;
    x += (target - x) * (1 - Math.exp(-dt * 7));  // amortecimento independente da taxa de quadros
    for (const {el, depth} of items) el.style.transform = `translate3d(${(x * depth).toFixed(2)}px,0,0)`;
    raf = Math.abs(target - x) > .001 ? requestAnimationFrame(frame) : 0;
  };
  const wake = () => { if (!raf) { last = performance.now(); raf = requestAnimationFrame(frame); } };
  addEventListener("pointermove", e => { target = .5 - e.clientX / innerWidth; wake(); });
  document.documentElement.addEventListener("pointerleave", () => { target = 0; wake(); });
}
"""


def _layer(svg: str, bottom: int, seconds: float, depth: int) -> str:
    copies = svg * 3  # cobre telas de até 3200 px; o laço anda exatamente um ladrilho
    return f'<div class="layer" data-depth="{depth}" style="bottom:{bottom}px"><div class="run" style="--t:{seconds:.2f}s">{copies}</div></div>'


def speed_from_pace(lap_seconds: float) -> float:
    """Volta mais curta, cena mais rápida. O expoente deixa visível a diferença entre circuitos."""
    return max(0.7, min(1.7, (95.0 / lap_seconds) ** 3))


def scene_html(circuit: str, team: str | None, color: str, lap_seconds: float) -> str:
    """Faixa animada: a velocidade vem do ritmo base da corrida e a cor, da equipe mais rápida."""
    rng = random.Random(zlib.crc32(circuit.encode("utf-8")))  # o cenário muda com o circuito, mas é estável
    speed = speed_from_pace(lap_seconds)
    road_h = 58
    layers = (
        _layer(_skyline(rng), road_h, 90 / speed, 8)
        + _layer(_stands(rng), road_h, 42 / speed, 16)
        + _layer(_fence(), road_h, 15 / speed, 30)
        + _layer(_road(), 0, 4.2 / speed, 44)
    )
    front = _layer(_streaks(rng), 0, 1.8 / speed, 70)
    rear = f'<svg class="wheel rear" viewBox="-64 -64 128 128" aria-hidden="true">{_wheel()}</svg>'
    wheel_front = rear.replace("wheel rear", "wheel front")
    car = (
        f'<div id="car" data-depth="20"><div id="enter"><div id="bob"><div class="shadow"></div>'
        f'<svg class="body" viewBox="{CAR_VIEWBOX}" aria-hidden="true">{_CAR}</svg>{rear}{wheel_front}</div></div></div>'
    )
    label = html.escape(team or "Sem equipe identificada")
    tag = f'<div class="tag"><b><i></i>{label}</b>melhor ritmo em {html.escape(circuit)}</div>'
    return _tone(
        f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>{_FONT_LINK}<style>{_TOKENS}{_CSS}</style></head>"
        f'<body><div id="scene" style="--team:{html.escape(color)};--w:{0.55 / speed:.3f}s">{layers}{car}{front}'
        f'<div class="vignette"></div>{tag}</div><script>{_JS}</script></body></html>'
    )


def car_html(color: str) -> str:
    """Desenho técnico estático do carro, usado na aba Equipes."""
    wheels = "".join(f'<g transform="translate({x} {WHEEL_Y})">{_wheel()}</g>' for x in (REAR_X, FRONT_X))
    notes = [
        (70, 50, 70, -22, "Asa traseira", "middle"),
        (430, 66, 430, -22, "Entrada de ar", "middle"),
        (610, 76, 610, -22, "Halo", "middle"),
        (450, 232, 450, 292, "Sidepod", "middle"),
        (650, 246, 650, 292, "Assoalho", "middle"),
        (945, 256, 945, 292, "Asa dianteira", "end"),
    ]
    callouts = "".join(
        f'<path d="M{x1} {y1} V{y2}" stroke="#4a4a50" stroke-dasharray="3 4"/><circle cx="{x1}" cy="{y1}" r="3" fill="#f3f3f4"/>'
        f'<text x="{x2}" y="{y2 + (-8 if y2 < 0 else 20)}" text-anchor="{anchor}">{text}</text>'
        for x1, y1, x2, y2, text, anchor in notes
    )
    svg = (
        f'<svg viewBox="0 -56 1000 376" role="img" aria-label="Carro de corrida genérico na cor da equipe">{_CAR}{wheels}'
        f'<path d="M20 {WHEEL_Y + WHEEL_R} H990" stroke="#333338"/>{callouts}</svg>'
    )
    return _tone(
        f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>{_FONT_LINK}<style>{_TOKENS}"
        "html,body{margin:0;height:100%;background:transparent}"
        "body{display:flex;align-items:center}"
        "svg{width:100%;height:auto;max-height:100%;font:500 22px var(--font);fill:#9c9ca3}"
        f"</style></head><body style='--team:{html.escape(color)}'>{svg}</body></html>"
    )

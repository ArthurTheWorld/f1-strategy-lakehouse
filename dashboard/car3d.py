"""Carro de F1 genérico em 3D (Three.js), desenhado por código e pintado com a cor da equipe.

Só a COR da equipe é usada: não há logo, patrocinador nem modelo oficial de nenhum carro real.
O Three.js (MIT) vai embutido em `assets/three.min.js`, então funciona sem internet.
"""

from __future__ import annotations

from pathlib import Path

_ASSETS = Path(__file__).resolve().parent / "assets"

# cores aproximadas das equipes (só cor; sem marca). Chave: trecho do nome em minúsculas.
TEAM_COLORS = {
    "mercedes": "#27F4D2",
    "ferrari": "#E8002D",
    "red bull": "#3671C6",
    "mclaren": "#FF8000",
    "aston": "#229971",
    "alpine": "#FF87BC",
    "williams": "#64C4FF",
    "racing bulls": "#6692FF",
    "rb": "#6692FF",
    "sauber": "#52E252",
    "haas": "#B6BABD",
}
FALLBACK = ["#e10600", "#2f80ed", "#27ae60", "#f2994a", "#bb6bd9", "#56ccf2", "#f2c94c", "#eb5757", "#6fcf97", "#9b9fb0"]


def team_color(team: str, index: int = 0) -> str:
    t = team.lower()
    for key, color in TEAM_COLORS.items():
        if key in t:
            return color
    return FALLBACK[index % len(FALLBACK)]


_JS = r"""
const renderer = new THREE.WebGLRenderer({antialias: true, alpha: true});
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 100);

// luz de estúdio: principal quente, contraluz frio, preenchimento suave
scene.add(new THREE.HemisphereLight(0xdfe6ff, 0x14161d, 0.75));
const key = new THREE.DirectionalLight(0xfff1e0, 1.5); key.position.set(4, 7, 5); key.castShadow = true;
key.shadow.mapSize.set(1024, 1024); Object.assign(key.shadow.camera, {left: -5, right: 5, top: 5, bottom: -5, near: 1, far: 20});
key.shadow.bias = -0.0005; scene.add(key);
const back = new THREE.DirectionalLight(0x7f9bff, 0.9); back.position.set(-5, 3, -5); scene.add(back);

const TEAM = new THREE.Color(TEAM_COLOR);
const mat = (c, r, m) => new THREE.MeshStandardMaterial({color: c, roughness: r, metalness: m});
const paint = mat(TEAM, 0.38, 0.15), carbon = mat(0x101116, 0.45, 0.35), tyre = mat(0x0a0a0c, 0.85, 0), steel = mat(0xb4b8c4, 0.3, 0.9);
const car = new THREE.Group();
const place3 = (o, x, y, z, rx = 0, ry = 0, rz = 0) => { o.position.set(x, y, z); o.rotation.set(rx, ry, rz); o.castShadow = true; car.add(o); return o; };
const box = (w, h, d, m, x, y, z, rx, ry, rz) => place3(new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m), x, y, z, rx, ry, rz);

// fuselagem em seções: cada estação define largura e altura; a seção transversal é uma superelipse
function loft(st, zc, m, n = 2.6) {
  const R = 20, pos = [], idx = [];
  for (const s of st) {
    for (let i = 0; i < R; i++) {
      const t = (i / R) * Math.PI * 2, c = Math.cos(t), si = Math.sin(t);
      pos.push(s.x, (s.yt + s.yb) / 2 + (s.yt - s.yb) / 2 * Math.sign(si) * Math.pow(Math.abs(si), 2 / n),
               zc + s.w * Math.sign(c) * Math.pow(Math.abs(c), 2 / n));
    }
  }
  for (let k = 0; k < st.length - 1; k++) for (let i = 0; i < R; i++) {
    const a = k * R + i, b = k * R + (i + 1) % R, c = (k + 1) * R + i, d = (k + 1) * R + (i + 1) % R;
    idx.push(a, c, b, b, c, d);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); g.setIndex(idx); g.computeVertexNormals();
  const o = new THREE.Mesh(g, m); o.castShadow = true; car.add(o); return o;
}
loft([
  {x: 2.35, w: 0.025, yb: 0.2, yt: 0.27}, {x: 2.0, w: 0.08, yb: 0.19, yt: 0.31}, {x: 1.4, w: 0.15, yb: 0.17, yt: 0.4},
  {x: 0.8, w: 0.24, yb: 0.15, yt: 0.47}, {x: 0.2, w: 0.3, yb: 0.14, yt: 0.52}, {x: -0.35, w: 0.27, yb: 0.14, yt: 0.66},
  {x: -1.0, w: 0.2, yb: 0.15, yt: 0.58}, {x: -1.7, w: 0.1, yb: 0.17, yt: 0.42}, {x: -2.15, w: 0.05, yb: 0.2, yt: 0.32},
], 0, paint);
for (const sgn of [-1, 1]) loft([
  {x: 0.75, w: 0.05, yb: 0.2, yt: 0.34}, {x: 0.3, w: 0.16, yb: 0.15, yt: 0.46}, {x: -0.4, w: 0.2, yb: 0.15, yt: 0.44},
  {x: -1.1, w: 0.14, yb: 0.16, yt: 0.34}, {x: -1.65, w: 0.05, yb: 0.18, yt: 0.26},
], sgn * 0.5, paint);
box(4.7, 0.04, 1.55, carbon, 0, 0.12, 0);                                    // assoalho
box(0.5, 0.05, 1.36, carbon, -1.9, 0.14, 0, 0, 0, 0.12);                     // difusor
// cockpit
place3(new THREE.Mesh(new THREE.SphereGeometry(0.115, 24, 18), mat(0xf4f4f6, 0.25, 0.1)), 0.12, 0.6, 0);
place3(new THREE.Mesh(new THREE.TorusGeometry(0.23, 0.02, 10, 32, Math.PI), carbon), 0.1, 0.56, 0, 0, Math.PI / 2, 0);
box(0.035, 0.2, 0.035, carbon, 0.36, 0.52, 0, 0, 0, -0.35);
box(0.28, 0.3, 0.26, paint, -0.5, 0.74, 0);                                  // entrada de ar
// asa dianteira: dois elementos e placas laterais
box(0.3, 0.025, 2.05, carbon, 2.35, 0.1, 0);
box(0.22, 0.02, 2.0, paint, 2.2, 0.17, 0, 0, 0, 0.08);
for (const sgn of [-1, 1]) { box(0.55, 0.22, 0.025, carbon, 2.3, 0.18, sgn * 1.03); box(0.04, 0.05, 0.28, carbon, 2.1, 0.12, sgn * 0.12); }
// asa traseira: dois elementos, placas laterais e pilares
box(0.34, 0.025, 1.5, carbon, -2.3, 0.92, 0);
box(0.28, 0.025, 1.46, paint, -2.22, 1.08, 0, 0, 0, -0.12);
for (const sgn of [-1, 1]) box(0.68, 0.5, 0.025, carbon, -2.26, 0.95, sgn * 0.76);
box(0.05, 0.5, 0.05, carbon, -2.0, 0.66, 0);
// rodas: pneu, aro metálico, miolo escuro e braços de suspensão
const wheel = (x, z, r, w) => {
  const sgn = Math.sign(z), g = new THREE.Group();
  const t = new THREE.Mesh(new THREE.CylinderGeometry(r, r, w, 40), tyre); g.add(t);
  const rimM = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.62, r * 0.62, w + 0.012, 32), steel); g.add(rimM);
  const hub = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.28, r * 0.28, w + 0.03, 20), carbon); g.add(hub);
  g.children.forEach(o => (o.castShadow = true));
  g.rotation.x = Math.PI / 2; g.position.set(x, r, z); car.add(g);
  const arm = (dy, dx) => { const a = new THREE.Mesh(new THREE.CylinderGeometry(0.011, 0.011, Math.abs(z) - 0.28, 6), carbon);
    a.rotation.x = Math.PI / 2; a.position.set(x + dx, r + dy, sgn * (Math.abs(z) / 2 + 0.14)); car.add(a); };
  arm(0.05, 0.14); arm(-0.06, -0.1);
};
for (const sgn of [-1, 1]) { wheel(1.5, sgn * 0.98, 0.34, 0.38); wheel(-1.4, sgn * 1.0, 0.37, 0.52); }
car.position.y = 0.0; scene.add(car);

// palco: disco escuro que recebe sombra e um anel na cor da equipe
const gtex = (() => { const c = document.createElement("canvas"); c.width = c.height = 256; const g = c.getContext("2d");
  const gr = g.createRadialGradient(128, 128, 10, 128, 128, 128); gr.addColorStop(0, "#232326"); gr.addColorStop(1, "#101012");
  g.fillStyle = gr; g.fillRect(0, 0, 256, 256); return new THREE.CanvasTexture(c); })();
const ground = new THREE.Mesh(new THREE.CircleGeometry(3.3, 72), new THREE.MeshStandardMaterial({map: gtex, roughness: 0.8, metalness: 0}));
ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true; scene.add(ground);
const ring = new THREE.Mesh(new THREE.RingGeometry(3.2, 3.26, 96), new THREE.MeshBasicMaterial({color: TEAM, side: THREE.DoubleSide}));
ring.rotation.x = -Math.PI / 2; ring.position.y = 0.005; scene.add(ring);

// câmera: arrastar gira, roda do mouse dá zoom, gira sozinho quando solto
let yaw = 0.75, pitch = 0.36, dist = 13.5, drag = false, lx = 0, ly = 0, idle = 0, curW = 0, curH = 0, fit = 1;
const resize = () => {  // o iframe pode abrir com tamanho 0: confere a cada quadro
  const w = innerWidth, h = innerHeight;
  if (!w || !h || (w === curW && h === curH)) return;
  curW = w; curH = h; renderer.setSize(w, h); camera.aspect = w / h; camera.updateProjectionMatrix();
  fit = Math.max(6.7, 6.2 / (0.536 * camera.aspect)) / 10.5;  // distância que faz o carro caber na largura e na altura
};
const placeCam = () => {
  const d = dist * fit;
  camera.position.set(Math.cos(yaw) * Math.cos(pitch) * d, Math.sin(pitch) * d + 0.35, Math.sin(yaw) * Math.cos(pitch) * d);
  camera.lookAt(0, 0.35, 0);
};
const el = renderer.domElement; el.style.cursor = "grab"; el.style.touchAction = "none";
el.addEventListener("pointerdown", e => { drag = true; lx = e.clientX; ly = e.clientY; el.setPointerCapture(e.pointerId); el.style.cursor = "grabbing"; });
el.addEventListener("pointerup", () => { drag = false; idle = 0; el.style.cursor = "grab"; });
el.addEventListener("pointermove", e => {
  if (!drag) return;
  yaw -= (e.clientX - lx) * 0.008; pitch = Math.max(0.04, Math.min(1.2, pitch + (e.clientY - ly) * 0.006));
  lx = e.clientX; ly = e.clientY;
});
el.addEventListener("wheel", e => { e.preventDefault(); dist = Math.max(6, Math.min(18, dist + e.deltaY * 0.01)); }, {passive: false});
(function loop() {
  requestAnimationFrame(loop);
  if (!drag) { idle += 1; if (idle > 50) yaw += 0.0035; }
  resize(); placeCam(); renderer.render(scene, camera);
})();
"""


def car_html(color: str, label: str = "", height: int = 420) -> str:
    """HTML autocontido com o carro 3D. `color` é um hex como '#27F4D2'."""
    three = (_ASSETS / "three.min.js").read_text(encoding="utf-8")
    js = _JS.replace("TEAM_COLOR", repr(color))
    safe = label.replace("<", "").replace(">", "").replace("&", "")
    return (
        "<!doctype html><html><head><meta charset='utf-8'><style>"
        "html,body{margin:0;height:100%;overflow:hidden;background:transparent;font-family:Segoe UI,system-ui,sans-serif}"
        ".tag{position:absolute;left:14px;top:10px;color:#ececef;font-size:15px;font-weight:600}"
        ".tag i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:8px;background:" + color + "}"
        ".hint{position:absolute;right:14px;bottom:10px;color:#9a9ca8;font-size:12px}"
        "</style></head><body>"
        f"<div class='hint'>arraste para girar, role para aproximar. Modelo genérico, sem marca.</div>"
        f"<script>{three}</script><script>{js}</script></body></html>"
    )

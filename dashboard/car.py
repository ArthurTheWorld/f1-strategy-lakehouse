"""Desenho técnico de um carro de F1 genérico, em vista superior.

As coordenadas estão em milímetros e seguem os limites do regulamento de 2022 a 2025: 2.000 mm de largura,
3.600 mm de entre-eixos, pneus de 305 mm (dianteiros) e 405 mm (traseiros). O traço é chapado, sem degradê
nem sombra. Só a cor da equipe é usada: não há logo, patrocinador nem réplica de um carro real.
"""

from __future__ import annotations

import html

Point = tuple[float, float]

WHEELBASE_MM = 3600
HALF_WIDTH_MM = 1000

# Metade de cada contorno (y >= 0), do bico para a traseira; a outra metade é espelhada.
_BODY: list[Point] = [
    (1160, 0),
    (1150, 60),
    (800, 85),
    (350, 125),
    (0, 170),
    (-400, 225),
    (-750, 290),
    (-1050, 330),
    (-1180, 430),
    (-1215, 735),
    (-1260, 765),
    (-1600, 775),
    (-2200, 760),
    (-2700, 700),
    (-3050, 520),
    (-3250, 330),
    (-3600, 200),
    (-4020, 120),
    (-4060, 0),
]
_FLOOR: list[Point] = [
    (-700, 0),
    (-700, 330),
    (-760, 790),
    (-900, 810),
    (-2850, 810),
    (-3150, 740),
    (-3235, 570),
    (-3920, 545),
    (-3960, 0),
]
_SPINE: list[Point] = [(-1490, 0), (-1520, 125), (-1950, 150), (-2650, 105), (-3400, 50), (-3880, 22), (-3900, 0)]
# Asa dianteira: bordo de ataque e bordo de fuga em três estações (centro, meio, ponta).
_WING_LEAD: list[Point] = [(1215, 0), (1150, 420), (880, 980)]
_WING_TRAIL: list[Point] = [(820, 0), (700, 450), (560, 980)]


def _mirror(half: list[Point]) -> list[Point]:
    return half + [(x, -y) for x, y in reversed(half) if y]


def _smooth(points: list[Point]) -> str:
    """Contorno fechado e suave: cada ponto vira o controle de uma curva entre os pontos médios vizinhos."""
    n = len(points)

    def mid(a: Point, b: Point) -> str:
        return f"{(a[0] + b[0]) / 2:.0f} {(a[1] + b[1]) / 2:.0f}"

    path = f"M{mid(points[-1], points[0])}"
    for i, p in enumerate(points):
        path += f"Q{p[0]:.0f} {p[1]:.0f} {mid(p, points[(i + 1) % n])}"
    return path + "Z"


def _polygon(points: list[Point]) -> str:
    return " ".join(f"{x:.0f},{y:.0f}" for x, y in points)


def _span(half: list[Point]) -> list[Point]:
    """Linha de ponta a ponta da asa, a partir das estações de um dos lados."""
    return [(x, -y) for x, y in reversed(half[1:])] + half


def _wing_element(t: float) -> str:
    """Linha de um elemento da asa, a uma fração t entre o bordo de ataque e o de fuga."""
    return _polygon(
        _span([(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for a, b in zip(_WING_LEAD, _WING_TRAIL, strict=True)])
    )


def _both(markup: str) -> str:
    """Repete um trecho dos dois lados do carro."""
    return f"{markup}<g transform='scale(1 -1)'>{markup}</g>"


_CSS = """
:root{--paper:#0d1013;--paper-3:#06080b;--ink:#eceff2;--ink-2:#c3c8cc;--muted:#9da2a8;--rule:#2d3135;--rule-2:#484e54;
  --font:'Host Grotesk',system-ui,sans-serif}
html,body{margin:0;height:100%;background:transparent}
body{display:flex;align-items:center}
svg{display:block;width:100%;height:auto;max-height:100%}
.body{fill:var(--team);stroke:var(--paper);stroke-width:14}
.carbon{fill:var(--paper-3);stroke:var(--rule-2);stroke-width:12;stroke-linejoin:round}
.tyre{fill:var(--paper-3);stroke:var(--muted);stroke-width:12}
.arm{fill:none;stroke:var(--rule-2);stroke-width:18;stroke-linecap:round}
.shaft{fill:none;stroke:var(--rule-2);stroke-width:34;stroke-linecap:round}
.seam{fill:none;stroke:var(--paper);stroke-width:12;stroke-linejoin:round;opacity:.55}
.element{fill:none;stroke:var(--rule-2);stroke-width:10;stroke-linejoin:round}
.cockpit{fill:var(--paper-3)}
.halo{fill:none;stroke:var(--rule-2);stroke-width:52;stroke-linecap:round}
.helmet{fill:var(--ink)}
.visor{fill:none;stroke:var(--paper-3);stroke-width:42;stroke-linecap:round}
.dim{fill:none;stroke:var(--muted);stroke-width:8}
text{font:400 180px var(--font);fill:var(--muted)}
"""


def car_html(color: str) -> str:
    """HTML autocontido com o carro em vista superior. `color` é um hex como '#27F4D2'."""
    front_tyre = "<rect class='tyre' x='-360' y='695' width='720' height='305' rx='70'/>"
    rear_tyre = f"<rect class='tyre' x='{-WHEELBASE_MM - 360}' y='595' width='720' height='405' rx='80'/>"
    arms = (
        "<path class='arm' d='M330 150L40 700M-330 205L40 700M210 140L-70 700M-470 240L-70 700'/>"
        "<path class='arm' d='M-3250 265L-3560 600M-3800 150L-3560 600M-3350 250L-3650 600'/>"
        "<path class='shaft' d='M-3600 150V600'/>"
    )
    endplates = (
        "<rect class='carbon' x='530' y='962' width='370' height='38' rx='10'/>"
        "<rect class='carbon' x='-4390' y='520' width='600' height='40' rx='10'/>"
    )
    mirror = "<path class='arm' d='M-930 320V440'/><rect class='body' x='-975' y='430' width='80' height='140' rx='24'/>"
    inlet = "<path class='visor' d='M-1232 450L-1242 715'/>"
    elements = "".join(f"<polyline class='element' points='{_wing_element(t)}'/>" for t in (0.3, 0.55, 0.8))
    wing = _polygon(_span(_WING_LEAD) + list(reversed(_span(_WING_TRAIL))))
    dims = (
        f"<path class='dim' d='M{-WHEELBASE_MM} 1060V1190M0 1060V1190M{-WHEELBASE_MM} 1125H0'/>"
        f"<text x='{-WHEELBASE_MM / 2:.0f}' y='1330' text-anchor='middle'>Entre-eixos, até 3.600 mm</text>"
        f"<path class='dim' d='M1330 {-HALF_WIDTH_MM}H1460M1330 {HALF_WIDTH_MM}H1460M1395 {-HALF_WIDTH_MM}V{HALF_WIDTH_MM}'/>"
        "<text transform='translate(1590 0) rotate(-90)' text-anchor='middle'>Largura, 2.000 mm</text>"
    )
    svg = (
        "<svg viewBox='-4500 -1090 6200 2500' role='img' aria-label='Carro de corrida genérico em vista superior, na cor da equipe'>"
        f"<path class='carbon' d='{_smooth(_mirror(_FLOOR))}'/>"
        f"{_both(arms)}{_both(front_tyre + rear_tyre)}"
        f"<polygon class='carbon' points='{wing}'/>{elements}{_both(endplates)}"
        f"{_both(mirror)}"
        f"<path class='body' d='{_smooth(_mirror(_BODY))}'/>"
        f"{_both(inlet)}"
        f"<path class='seam' d='{_smooth(_mirror(_SPINE))}'/>"
        "<ellipse class='cockpit' cx='-1160' cy='0' rx='345' ry='205'/>"
        "<ellipse class='cockpit' cx='-1575' cy='0' rx='60' ry='85'/>"
        "<circle class='helmet' cx='-1215' cy='0' r='128'/>"
        "<path class='visor' d='M-1150 -70A95 95 0 0 1 -1150 70'/>"
        "<path class='halo' d='M-1490 250C-1250 300 -900 215 -770 0C-900 -215 -1250 -300 -1490 -250'/>"
        "<rect class='carbon' x='-4330' y='-525' width='430' height='1050' rx='14'/>"
        "<path class='element' d='M-4170 -525V525M-4040 -525V525'/>"
        f"{dims}</svg>"
    )
    return (
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
        "<link href='https://fonts.googleapis.com/css2?family=Host+Grotesk:wght@400;500&display=swap' rel='stylesheet'>"
        f"<style>{_CSS}</style></head><body style='--team:{html.escape(color)}'>{svg}</body></html>"
    )

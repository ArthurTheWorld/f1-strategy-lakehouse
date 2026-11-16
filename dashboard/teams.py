"""Cor de cada equipe nos gráficos. Só a cor: nenhuma logo ou marca.

As cores de 2026 são as que a OpenF1 publica no campo `team_colour` dos pilotos. Algumas ficam parecidas
(Audi e Ferrari, Cadillac e Haas, quatro azuis); os gráficos escrevem o nome do piloto na ponta de cada linha
e o de ritmo destaca só a equipe escolhida, então a cor nunca é a única pista.
"""

from __future__ import annotations

# chave: trecho do nome da equipe em minúsculas. A ordem importa: a primeira chave contida no nome vence.
TEAM_COLORS = {
    "racing bulls": "#6C98FF",
    "red bull": "#4781D7",
    "mercedes": "#00D7B6",
    "ferrari": "#ED1131",
    "mclaren": "#F47600",
    "aston": "#229971",
    "alpine": "#00A1E8",
    "williams": "#1868DB",
    "audi": "#F50537",
    "cadillac": "#909090",
    "haas": "#9C9FA2",
    # nomes de 2024 e 2025, para quem rodar outra temporada
    "visa cash app rb": "#6692FF",
    "sauber": "#52E252",
}
FALLBACK = ["#e10600", "#2f80ed", "#27ae60", "#f2994a", "#bb6bd9", "#56ccf2", "#f2c94c", "#eb5757", "#6fcf97", "#9b9fb0"]


def team_color(team: str, index: int = 0) -> str:
    t = team.lower()
    for key, color in TEAM_COLORS.items():
        if key in t:
            return color
    return FALLBACK[index % len(FALLBACK)]

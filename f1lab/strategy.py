"""Simulador de estratégia de pit stop.

Enumera todas as estratégias de 1 e 2 paradas (todas as voltas de parada, todas as sequências de compostos),
soma o tempo previsto pelo modelo volta a volta e a perda de cada parada, e devolve as melhores.

Regras aplicadas (as mesmas do regulamento de pista seca):
  - pelo menos 2 compostos diferentes na corrida;
  - stint mínimo configurável (padrão 8 voltas);
  - nenhum stint maior que a idade máxima com suporte nos dados do modelo (`model.max_age`), porque o modelo
    não extrapola; isso evita "descobrir" um pneu que dura 60 voltas só porque o modelo ficou plano.

O que NÃO é simulado: tráfego, ultrapassagens, safety car, clima, pit stop sob bandeira amarela, temperatura.
O resultado compara estratégias entre si em pista livre; não é uma previsão de tempo de corrida.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd

from .schema import COMPOUNDS


@dataclass(frozen=True)
class Strategy:
    compounds: tuple[str, ...]
    pit_laps: tuple[int, ...]  # volta de ENTRADA nos boxes de cada parada
    total_time_s: float

    @property
    def label(self) -> str:
        parts = []
        bounds = (0, *self.pit_laps)
        for i, c in enumerate(self.compounds):
            end = self.pit_laps[i] if i < len(self.pit_laps) else None
            parts.append(f"{c[0]}{bounds[i] + 1}-{end if end else 'fim'}")
        return " / ".join(parts)


def _cost_table(model, n_laps: int, compounds, max_age: dict[str, int], start_age: int = 1):
    """cost[c][s, e] = soma do efeito previsto das voltas s..e (1-indexadas) num stint que começa em s.

    NaN onde o stint passa da idade máxima suportada.
    """
    table = {}
    for c in compounds:
        cost = np.full((n_laps + 2, n_laps + 2), np.nan)
        limit = max_age.get(c, 10**9)
        starts, ages, laps, idx = [], [], [], []
        for s in range(1, n_laps + 1):
            for e in range(s, n_laps + 1):
                if e - s + start_age > limit:
                    break
                starts.append(s)
                ages.append(e - s + start_age)
                laps.append(e)
                idx.append(e)
        pred = np.asarray(model.predict(np.full(len(ages), c), np.array(ages), np.array(laps)))
        starts_a = np.array(starts)
        for s in range(1, n_laps + 1):
            m = starts_a == s
            if m.any():
                es = np.array(idx)[m]
                cost[s, es] = np.cumsum(pred[m])
        # cost[c][s,e] ja é a soma acumulada de s até e (cumsum dentro do mesmo s)
        table[c] = cost
    return table


def enumerate_strategies(
    model,
    n_laps: int,
    base_lap_s: float,
    pit_loss_s: float,
    compounds=COMPOUNDS,
    max_stops: int = 2,
    min_stint: int = 8,
    top: int = 10,
) -> pd.DataFrame:
    max_age = getattr(model, "max_age", {}) or {}
    cost = _cost_table(model, n_laps, compounds, max_age)
    base_total = base_lap_s * n_laps
    results: list[Strategy] = []

    def stint(c, s, e):
        v = cost[c][s, e]
        return v

    # 1 parada
    for p in range(min_stint, n_laps - min_stint + 1):
        for c1, c2 in product(compounds, repeat=2):
            if c1 == c2:
                continue
            a, b = stint(c1, 1, p), stint(c2, p + 1, n_laps)
            if np.isnan(a) or np.isnan(b):
                continue
            results.append(Strategy((c1, c2), (p,), base_total + a + b + pit_loss_s))
    # 2 paradas
    if max_stops >= 2:
        for p1 in range(min_stint, n_laps - 2 * min_stint + 1):
            for p2 in range(p1 + min_stint, n_laps - min_stint + 1):
                for c1, c2, c3 in product(compounds, repeat=3):
                    if len({c1, c2, c3}) < 2:
                        continue
                    a, b, c = stint(c1, 1, p1), stint(c2, p1 + 1, p2), stint(c3, p2 + 1, n_laps)
                    if np.isnan(a) or np.isnan(b) or np.isnan(c):
                        continue
                    results.append(Strategy((c1, c2, c3), (p1, p2), base_total + a + b + c + 2 * pit_loss_s))
    if not results:
        return pd.DataFrame(columns=["rank", "strategy", "stops", "total_time_s", "gap_s"])
    results.sort(key=lambda s: s.total_time_s)
    best = results[0].total_time_s
    return pd.DataFrame(
        [
            {
                "rank": i + 1,
                "strategy": s.label,
                "stops": len(s.pit_laps),
                "compounds": s.compounds,
                "pit_laps": s.pit_laps,
                "total_time_s": s.total_time_s,
                "gap_s": s.total_time_s - best,
            }
            for i, s in enumerate(results[:top])
        ]
    )


def strategy_time(model, compounds, pit_laps, n_laps: int, base_lap_s: float, pit_loss_s: float) -> float:
    """Tempo de UMA estratégia segundo `model` (usado para medir o arrependimento com o modelo verdadeiro)."""
    bounds = [0, *pit_laps, n_laps]
    total = base_lap_s * n_laps + pit_loss_s * len(pit_laps)
    for i, c in enumerate(compounds):
        laps = np.arange(bounds[i] + 1, bounds[i + 1] + 1)
        ages = np.arange(1, len(laps) + 1)
        total += float(np.sum(model.predict(np.full(len(laps), c), ages, laps)))
    return total


def regret(model, oracle, n_laps: int, base_lap_s: float, pit_loss_s: float, **kw) -> dict:
    """Quanto a estratégia escolhida pelo `model` perde, medida com o `oracle` (a verdade), para a melhor do oráculo."""
    chosen = enumerate_strategies(model, n_laps, base_lap_s, pit_loss_s, top=1, **kw).iloc[0]
    best = enumerate_strategies(oracle, n_laps, base_lap_s, pit_loss_s, top=1, **kw).iloc[0]
    t_chosen = strategy_time(oracle, chosen["compounds"], chosen["pit_laps"], n_laps, base_lap_s, pit_loss_s)
    t_best = strategy_time(oracle, best["compounds"], best["pit_laps"], n_laps, base_lap_s, pit_loss_s)
    return {"regret_s": t_chosen - t_best, "chosen": chosen["strategy"], "best": best["strategy"]}

"""Corridas sintéticas com VERDADE CONHECIDA, no formato das voltas do FastF1.

Serve para validar o pipeline, o modelo e o simulador: como os parâmetros físicos usados na geração são
conhecidos, dá para medir se o modelo os recupera. Nada aqui imita uma corrida real específica; os pilotos
são D01..D20 e os circuitos são "Synth GP".

Modelo gerador de uma volta limpa:
    tempo = base_do_circuito + driver_offset - fuel * (volta - 1)
            + offset[composto] + lin[composto]*idade*k + quad[composto]*idade^2*k + ruído
com k = abrasividade da pista (varia por corrida) e `idade` = TyreLife (voltas do jogo de pneus).

Eventos que o gerador inclui de propósito, para o pipeline ter o que limpar:
    volta 1 lenta, voltas de entrada e saída dos boxes, safety car, VSC, bandeira amarela, tráfego,
    pneus usados, velocidades ausentes e falhas de potência (anomalias com rótulo).

`IsAccurate` é DE PROPÓSITO independente do status da pista e das voltas de box: em 60% das voltas sob
safety car, VSC, amarela ou de box ele vem verdadeiro. Assim, cada regra de limpeza do dbt precisa
funcionar sozinha (nos dados reais do FastF1 isso também não é garantido).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .schema import BRONZE_LAP_COLUMNS, COMPOUNDS, SPEED_COLUMNS, make_race_id

# ---- parâmetros físicos "da população" (a verdade que o modelo deve recuperar) ------------------
COMPOUND_OFFSET = {"SOFT": -0.70, "MEDIUM": 0.00, "HARD": 0.45}
DEG_LIN = {"SOFT": 0.060, "MEDIUM": 0.035, "HARD": 0.020}
DEG_QUAD = {"SOFT": 0.0030, "MEDIUM": 0.0012, "HARD": 0.0006}
FUEL_S_PER_LAP = 0.032
PIT_IN_EXTRA_S = 3.0
PIT_OUT_EXTRA_S = 18.0
POPULATION_PIT_LOSS_S = PIT_IN_EXTRA_S + PIT_OUT_EXTRA_S  # 21.0


@dataclass(frozen=True)
class RaceTruth:
    race_id: str
    circuit: str
    n_laps: int
    base_lap_s: float
    abrasiveness: float
    pit_in_extra_s: float
    pit_out_extra_s: float

    @property
    def pit_loss_s(self) -> float:
        return self.pit_in_extra_s + self.pit_out_extra_s


def true_tyre_delta(compound, tyre_life, abrasiveness: float = 1.0):
    """Efeito do pneu (offset + degradação) em segundos, verdade da população quando abrasiveness=1."""
    compound = np.asarray(compound)
    age = np.asarray(tyre_life, dtype=float)
    out = np.zeros(np.broadcast(compound, age).shape)
    for c in COMPOUNDS:
        m = compound == c
        if np.any(m):
            a = np.broadcast_to(age, out.shape)[m]
            out[m] = COMPOUND_OFFSET[c] + abrasiveness * (DEG_LIN[c] * a + DEG_QUAD[c] * a * a)
    return out


class TruthModel:
    """Mesma interface do modelo treinado, mas devolve a verdade (pneu + combustível). Usado como oráculo."""

    max_age = {c: 60 for c in COMPOUNDS}

    def predict(self, compound, tyre_life, lap_number):
        return true_tyre_delta(compound, tyre_life) - FUEL_S_PER_LAP * (np.asarray(lap_number, dtype=float) - 1)


def _plan_stints(rng: np.random.Generator, n_laps: int):
    """Sorteia 1 ou 2 paradas respeitando stint mínimo de 8 voltas e pelo menos 2 compostos."""
    stops = int(rng.choice([1, 2], p=[0.6, 0.4]))
    if stops == 1:
        pits = [int(rng.integers(int(n_laps * 0.25), int(n_laps * 0.70)))]
    else:
        p1 = int(rng.integers(int(n_laps * 0.15), int(n_laps * 0.40)))
        p2 = int(rng.integers(p1 + 8, int(n_laps * 0.88)))
        pits = [p1, p2]
    compounds = [str(rng.choice(COMPOUNDS))]
    for _ in pits:
        compounds.append(str(rng.choice([c for c in COMPOUNDS if c != compounds[-1]])))
    return pits, compounds


def _safety_events(rng: np.random.Generator, n_laps: int) -> dict[int, tuple[str, float]]:
    """lap -> (TrackStatus, multiplicador do tempo de volta). Safety car e VSC."""
    ev: dict[int, tuple[str, float]] = {}
    for _ in range(int(rng.choice([0, 1, 2], p=[0.35, 0.45, 0.20]))):
        start = int(rng.integers(6, n_laps - 8))
        length = int(rng.integers(3, 6))
        for i in range(length):
            code = "14" if i == 0 else ("41" if i == length - 1 else "4")
            ev[start + i] = (code, 1.40)
    if rng.random() < 0.3:
        start = int(rng.integers(6, n_laps - 6))
        for i, code in enumerate(["6", "67"]):
            ev.setdefault(start + i, (code, 1.22))
    return ev


def generate_race(
    year: int,
    round_: int,
    rng: np.random.Generator,
    anomaly_events: int | None = None,
    n_drivers: int = 20,
):
    """Devolve (laps_bronze, race_row, truth, anomaly_labels)."""
    n_laps = int(rng.integers(50, 72))
    race_id = make_race_id(year, round_)
    truth = RaceTruth(
        race_id=race_id,
        circuit=f"Synth GP {round_:02d}",
        n_laps=n_laps,
        base_lap_s=float(rng.uniform(78, 98)),
        abrasiveness=float(np.clip(rng.normal(1.0, 0.15), 0.6, 1.5)),
        pit_in_extra_s=float(rng.normal(PIT_IN_EXTRA_S, 0.6)),
        pit_out_extra_s=float(rng.normal(PIT_OUT_EXTRA_S, 1.0)),
    )
    base_speeds = {
        c: float(rng.uniform(lo, hi))
        for c, (lo, hi) in zip(SPEED_COLUMNS, [(255, 300), (240, 290), (270, 315), (285, 335)], strict=True)
    }
    safety = _safety_events(rng, n_laps)
    drivers = [f"D{i + 1:02d}" for i in range(n_drivers)]
    driver_offset = {d: float(rng.normal(0, 0.25)) for d in drivers}
    driver_speed_offset = {d: float(rng.normal(0, 2.0)) for d in drivers}

    n_events = int(rng.choice([0, 1, 2], p=[0.3, 0.45, 0.25])) if anomaly_events is None else anomaly_events
    anomalies = []  # (driver, start, length, drop_kmh)
    for d in rng.choice(drivers, size=n_events, replace=False) if n_events else []:
        anomalies.append((str(d), int(rng.integers(8, n_laps - 12)), int(rng.integers(3, 10)), float(rng.uniform(9, 20))))

    rows = []
    for d in drivers:
        pits, comps = _plan_stints(rng, n_laps)
        bounds = [0, *pits, n_laps]
        for s_idx, comp in enumerate(comps):
            used = rng.random() < (0.25 if s_idx == 0 else 0.15)
            start_age = int(rng.integers(2, 6)) if used else 1
            for k, lap in enumerate(range(bounds[s_idx] + 1, bounds[s_idx + 1] + 1)):
                age = start_age + k
                t = (
                    truth.base_lap_s
                    + driver_offset[d]
                    - FUEL_S_PER_LAP * (lap - 1)
                    + float(true_tyre_delta(np.array([comp]), np.array([age]), truth.abrasiveness)[0])
                    + rng.normal(0, 0.18)
                )
                if rng.random() < 0.04:  # tráfego
                    t += rng.uniform(0.4, 1.5)
                status, speed_penalty = "1", 0.0
                if lap == 1:
                    t += 5.5
                if lap in safety:
                    status, mult = safety[lap]
                    t *= mult
                    speed_penalty = 0.45
                elif rng.random() < 0.03:  # amarela
                    status, t = "12", t + 0.3
                pit_in = lap == bounds[s_idx + 1] and s_idx < len(comps) - 1
                pit_out = k == 0 and s_idx > 0
                if pit_in:
                    t += truth.pit_in_extra_s
                if pit_out:
                    t += truth.pit_out_extra_s

                slip = rng.normal(0, 2.0)
                speeds = {c: base_speeds[c] + driver_speed_offset[d] + slip + rng.normal(0, 1.2) for c in SPEED_COLUMNS}
                is_anom = False
                for ad, a_start, a_len, a_drop in anomalies:
                    if d == ad and a_start <= lap < a_start + a_len and status == "1" and not (pit_in or pit_out):
                        is_anom = True
                        for c in SPEED_COLUMNS:
                            speeds[c] -= a_drop
                        t += 0.25
                for c in SPEED_COLUMNS:
                    if speed_penalty:
                        speeds[c] *= 1 - speed_penalty
                    if pit_in or pit_out or rng.random() < 0.03:
                        speeds[c] = np.nan

                s1 = t * 0.30 + rng.normal(0, 0.05)
                s2 = t * 0.38 + rng.normal(0, 0.05)
                rows.append(
                    {
                        "race_id": race_id,
                        "Driver": d,
                        "DriverNumber": str(int(d[1:])),
                        "Team": f"Team {(int(d[1:]) - 1) // 2 + 1}",
                        "LapNumber": float(lap),
                        "Stint": float(s_idx + 1),
                        "Compound": comp,
                        "TyreLife": float(age),
                        "FreshTyre": not used,
                        "LapTime_s": t,
                        "Sector1Time_s": s1,
                        "Sector2Time_s": s2,
                        "Sector3Time_s": t - s1 - s2,
                        "PitInTime_s": np.nan,
                        "PitOutTime_s": np.nan,
                        **speeds,
                        "TrackStatus": status,
                        "Position": np.nan,
                        "IsAccurate": lap > 1
                        and (True if (status == "1" and not (pit_in or pit_out)) else bool(rng.random() < 0.6)),
                        "Deleted": False,
                        "IsPersonalBest": False,
                        "_pit_in": pit_in,
                        "_pit_out": pit_out,
                        "_anom": is_anom,
                    }
                )
    df = pd.DataFrame(rows)

    # posição pelo tempo acumulado; marcas de box (tempo de sessão aproximado)
    df = df.sort_values(["Driver", "LapNumber"]).reset_index(drop=True)
    df["_cum"] = df.groupby("Driver")["LapTime_s"].cumsum()
    df["Position"] = df.groupby("LapNumber")["_cum"].rank(method="first").astype(float)
    df.loc[df["_pit_in"], "PitInTime_s"] = df["_cum"]
    df.loc[df["_pit_out"], "PitOutTime_s"] = df["_cum"] - df["LapTime_s"] + 5.0

    labels = df.loc[:, ["race_id", "Driver", "LapNumber", "_anom"]].rename(columns={"_anom": "is_anomaly"})
    laps = df[BRONZE_LAP_COLUMNS].copy()
    race = {"race_id": race_id, "year": year, "round": round_, "circuit": truth.circuit, "n_laps": n_laps, "source": "synthetic"}
    return laps, race, truth, labels


def generate_season(n_races: int = 8, seed: int = 7, year: int = 2024, anomaly_events: int | None = None):
    rng = np.random.default_rng(seed)
    laps, races, truths, labels = [], [], [], []
    for r in range(1, n_races + 1):
        lp, race, truth, lab = generate_race(year, r, rng, anomaly_events=anomaly_events)
        laps.append(lp)
        races.append(race)
        truths.append(asdict(truth))
        labels.append(lab)
    return pd.concat(laps, ignore_index=True), pd.DataFrame(races), truths, pd.concat(labels, ignore_index=True)

"""Detecção de anomalias nas velocidades de reta (SpeedI1, SpeedI2, SpeedFL, SpeedST) por piloto.

Um problema de potência aparece como queda sustentada de velocidade nas retas. Comparamos dois detectores,
com um critério de avaliação explícito (rótulos injetados no gerador sintético):

  - robust_z: z-score robusto (mediana e MAD) do piloto na corrida, média das 4 velocidades; marca quedas;
  - iforest: Isolation Forest sobre os resíduos das 4 velocidades (multivariado).

Por que não LSTM: não há volume nem rótulos reais para justificar; um detector simples e explicável é o
ponto de partida honesto. Se não ganhar do simples, a rede não merece existir.

Só voltas limpas com as 4 velocidades presentes entram (gold.fct_laps_model): safety car e voltas de box
derrubam a velocidade por motivos que não são falha.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from .schema import SPEED_COLUMNS

_SPEED = [c.lower().replace("speed", "speed_") for c in SPEED_COLUMNS]  # speed_i1, speed_i2, speed_fl, speed_st
MAD_SCALE = 1.4826


def prepare(laps: pd.DataFrame) -> pd.DataFrame:
    """Resíduo de cada velocidade em relação à mediana do piloto na corrida."""
    df = laps.dropna(subset=_SPEED).copy()
    for c in _SPEED:
        med = df.groupby(["race_id", "driver"])[c].transform("median")
        df[f"res_{c}"] = df[c] - med
    return df


def detect_robust_z(df: pd.DataFrame, threshold: float = 3.0, min_consecutive: int = 2) -> pd.DataFrame:
    """Marca quedas: z robusto médio abaixo de -threshold, em pelo menos `min_consecutive` voltas seguidas."""
    out = df.sort_values(["race_id", "driver", "lap_number"]).copy()
    z_cols = []
    for c in _SPEED:
        mad = out.groupby(["race_id", "driver"])[f"res_{c}"].transform(lambda s: (s - s.median()).abs().median())
        mad = mad.replace(0, np.nan) * MAD_SCALE
        out[f"z_{c}"] = out[f"res_{c}"] / mad
        z_cols.append(f"z_{c}")
    out["score"] = out[z_cols].mean(axis=1)
    hit = out["score"] < -threshold
    # exige voltas consecutivas (reduz alarme falso por ruído isolado)
    grp = (out["race_id"] + out["driver"]).values
    lap = out["lap_number"].to_numpy()
    flag = np.zeros(len(out), dtype=bool)
    h = hit.to_numpy()
    start = 0
    for i in range(1, len(out) + 1):
        if i == len(out) or grp[i] != grp[start]:
            run_start = None
            for j in range(start, i + 1):
                active = j < i and h[j] and (run_start is None or lap[j] - lap[j - 1] <= 2)
                if active and run_start is None:
                    run_start = j
                if (not active) and run_start is not None:
                    if j - run_start >= min_consecutive:
                        flag[run_start:j] = True
                    run_start = j if (j < i and h[j]) else None
            start = i
    out["is_flagged"] = flag
    return out[["race_id", "driver", "lap_number", "score", "is_flagged"]]


def detect_iforest(df: pd.DataFrame, contamination: float = 0.02, seed: int = 0) -> pd.DataFrame:
    out = df.sort_values(["race_id", "driver", "lap_number"]).copy()
    x = out[[f"res_{c}" for c in _SPEED]].to_numpy()
    iso = IsolationForest(n_estimators=200, contamination=contamination, random_state=seed, n_jobs=1).fit(x)
    out["score"] = iso.score_samples(x)
    # só interessa queda de velocidade: ignora anomalias para cima (velocidade maior que o normal)
    drop = out[[f"res_{c}" for c in _SPEED]].mean(axis=1) < 0
    out["is_flagged"] = (iso.predict(x) == -1) & drop.to_numpy()
    return out[["race_id", "driver", "lap_number", "score", "is_flagged"]]


def evaluate(flags: pd.DataFrame, labels: pd.DataFrame) -> dict:
    """Precisão, revocação, F1 por volta e taxa de alarme falso. `labels` vem do gerador (verdade)."""
    m = flags.merge(
        labels.rename(columns={"LapNumber": "lap_number", "Driver": "driver"}), on=["race_id", "driver", "lap_number"], how="left"
    )
    m["is_anomaly"] = m["is_anomaly"].fillna(False).astype(bool)
    tp = int((m.is_flagged & m.is_anomaly).sum())
    fp = int((m.is_flagged & ~m.is_anomaly).sum())
    fn = int((~m.is_flagged & m.is_anomaly).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    n_normal = int((~m.is_anomaly).sum())
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_alarm_rate": fp / n_normal if n_normal else 0.0,
        "n_laps": int(len(m)),
        "n_anomalous": tp + fn,
    }

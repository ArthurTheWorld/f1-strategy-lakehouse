"""Modelo de tempo de volta: quanto cada volta se afasta do ritmo base da corrida.

Alvo: `lap_delta_s` (tempo da volta - mediana das voltas limpas da corrida), o que remove circuito e ritmo base.
Variáveis: idade do pneu, número da volta (proxy de combustível) e composto.

Dois modelos, para a comparação ser honesta:
  - baseline: regressão linear com interação composto x idade (o que um analista faria numa planilha);
  - XGBoost com restrições monotônicas: mais idade nunca deixa a volta mais rápida; mais voltas
    (menos combustível) nunca deixa mais lenta. É conhecimento físico embutido no modelo.

Árvores não extrapolam: o modelo guarda a maior idade de pneu vista por composto (`max_age`) e o simulador
de estratégia não propõe stints além disso.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import xgboost as xgb

from .schema import COMPOUNDS

FEATURES = ["tyre_life", "lap_number", "c_SOFT", "c_MEDIUM", "c_HARD"]
MONOTONE = (1, -1, 0, 0, 0)


def load_training(db_path: str | Path) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return con.execute("select race_id, driver, lap_number, compound, tyre_life, lap_delta_s from gold.fct_laps_model").df()
    finally:
        con.close()


def design_matrix(compound, tyre_life, lap_number) -> pd.DataFrame:
    compound = np.asarray(compound)
    unknown = set(np.unique(compound)) - set(COMPOUNDS)
    if unknown:
        raise ValueError(f"composto desconhecido: {sorted(unknown)} (aceitos: {COMPOUNDS})")
    x = pd.DataFrame({"tyre_life": np.asarray(tyre_life, dtype=float), "lap_number": np.asarray(lap_number, dtype=float)})
    for c in COMPOUNDS:
        x[f"c_{c}"] = (compound == c).astype(float)
    return x[FEATURES]


class BaselineModel:
    """OLS: delta ~ composto + lap_number + composto*tyre_life."""

    def __init__(self):
        self.coef = None

    @staticmethod
    def _x(compound, tyre_life, lap_number):
        d = design_matrix(compound, tyre_life, lap_number)
        cols = [d[f"c_{c}"].to_numpy() for c in COMPOUNDS]
        cols += [d[f"c_{c}"].to_numpy() * d["tyre_life"].to_numpy() for c in COMPOUNDS]
        cols.append(d["lap_number"].to_numpy())
        return np.column_stack(cols)

    def fit(self, df: pd.DataFrame):
        x = self._x(df["compound"], df["tyre_life"], df["lap_number"])
        self.coef, *_ = np.linalg.lstsq(x, df["lap_delta_s"].to_numpy(), rcond=None)
        return self

    def predict(self, compound, tyre_life, lap_number):
        return self._x(compound, tyre_life, lap_number) @ self.coef


class LapModel:
    """XGBoost monotônico + limites de validade."""

    def __init__(self, n_estimators=400, max_depth=3, learning_rate=0.05, seed=0):
        self.params = dict(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            subsample=0.9,
            min_child_weight=5,
            monotone_constraints=MONOTONE,
            random_state=seed,
            n_jobs=1,
            tree_method="hist",
        )
        self.reg = xgb.XGBRegressor(**self.params)
        self.max_age: dict[str, int] = {}

    def fit(self, df: pd.DataFrame):
        x = design_matrix(df["compound"], df["tyre_life"], df["lap_number"])
        self.reg.fit(x, df["lap_delta_s"].to_numpy())
        # idade máxima com suporte nos dados (p99, para não confiar em 1 ou 2 pontos extremos)
        self.max_age = {
            c: int(np.ceil(df.loc[df["compound"] == c, "tyre_life"].quantile(0.99)))
            for c in COMPOUNDS
            if (df["compound"] == c).any()
        }
        return self

    def predict(self, compound, tyre_life, lap_number):
        return self.reg.predict(design_matrix(compound, tyre_life, lap_number))

    def save(self, directory: str | Path) -> None:
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        self.reg.save_model(d / "lap_model.json")
        (d / "meta.json").write_text(json.dumps({"max_age": self.max_age, "features": FEATURES}, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, directory: str | Path) -> LapModel:
        d = Path(directory)
        m = cls()
        m.reg.load_model(d / "lap_model.json")
        m.max_age = json.loads((d / "meta.json").read_text(encoding="utf-8"))["max_age"]
        return m


def _scores(y, p) -> dict:
    err = np.asarray(y) - np.asarray(p)
    return {"rmse": float(np.sqrt(np.mean(err**2))), "mae": float(np.mean(np.abs(err)))}


def leave_one_race_out(df: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """Treina sem uma corrida e avalia nela. É o teste que importa: o modelo vai rodar em corridas novas."""
    rows = []
    for race in sorted(df["race_id"].unique()):
        tr, te = df[df["race_id"] != race], df[df["race_id"] == race]
        base, gbm = BaselineModel().fit(tr), LapModel(seed=seed).fit(tr)
        zero = _scores(te["lap_delta_s"], np.full(len(te), tr["lap_delta_s"].mean()))
        b = _scores(te["lap_delta_s"], base.predict(te["compound"], te["tyre_life"], te["lap_number"]))
        g = _scores(te["lap_delta_s"], gbm.predict(te["compound"], te["tyre_life"], te["lap_number"]))
        rows.append(
            {
                "race_id": race,
                "n": len(te),
                "rmse_mean": zero["rmse"],
                "rmse_baseline": b["rmse"],
                "rmse_xgb": g["rmse"],
                "mae_baseline": b["mae"],
                "mae_xgb": g["mae"],
            }
        )
    return pd.DataFrame(rows)


def tyre_curve(model, compound: str, ages, lap_number: float = 25.0) -> np.ndarray:
    """Efeito do pneu relativo à idade 1 do MESMO composto, na volta de referência (isola a degradação)."""
    ages = np.asarray(ages, dtype=float)
    comp = np.full(ages.shape, compound)
    lap = np.full(ages.shape, lap_number)
    p = np.asarray(model.predict(comp, ages, lap))
    p1 = np.asarray(model.predict(np.array([compound]), np.array([1.0]), np.array([lap_number])))[0]
    return p - p1


def estimate_pit_loss(model, pit_stops: pd.DataFrame, laps_by_race: pd.DataFrame | None = None) -> dict:
    """Perda média por parada = (volta de entrada + volta de saída) - o que o modelo diz que seriam sem parar.

    `in_lap_delta_s`/`out_lap_delta_s` já vêm normalizados pela mediana da corrida (gold.fct_pit_stops).
    Subtrai-se a previsão do modelo para o estado de pneu e a volta de cada uma, o que retira o efeito de o
    pneu novo ser mais rápido. Devolve média, mediana e n; a mediana é a mais robusta a tráfego.
    """
    if pit_stops.empty:
        return {"mean_s": float("nan"), "median_s": float("nan"), "n": 0}
    exp_in = model.predict(pit_stops["compound_before"], pit_stops["tyre_life_in"], pit_stops["in_lap"])
    exp_out = model.predict(pit_stops["compound_after"], pit_stops["tyre_life_out"], pit_stops["out_lap"])
    loss = (pit_stops["in_lap_delta_s"] + pit_stops["out_lap_delta_s"]) - (exp_in + exp_out)
    return {"mean_s": float(loss.mean()), "median_s": float(loss.median()), "n": int(len(loss))}

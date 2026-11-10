"""Protocolo de avaliação contra a VERDADE CONHECIDA do gerador sintético.

Separação honesta: os parâmetros dos detectores de anomalia são escolhidos na temporada de AJUSTE
(`TUNE_SEED`) e avaliados em temporadas de TESTE com sementes diferentes. Além disso, mede-se o alarme
falso em temporadas SEM nenhuma anomalia.

    python -m f1lab.evaluate --dbt-bin /caminho/para/dbt --out artifacts/evaluation.json
"""

from __future__ import annotations

import argparse
import json
import tempfile
from itertools import product
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from . import anomaly as anom
from . import model as mdl
from . import strategy as st
from .pipeline import build, synth
from .schema import COMPOUNDS
from .synth import FUEL_S_PER_LAP, TruthModel, true_tyre_delta

TUNE_SEED = 101
TEST_SEEDS = [11, 12, 13, 14, 15]
NO_ANOMALY_SEEDS = [21, 22]


def _season(workdir: Path, seed: int, races: int, anomaly_events: int | None, dbt_bin: str | None):
    d = workdir / f"season_{seed}"
    synth(d, races, seed, anomaly_events)
    db = build(d, dbt_bin)
    con = duckdb.connect(str(db), read_only=True)
    try:
        laps = con.execute("select * from gold.fct_laps_model").df()
        pits = con.execute("select * from gold.fct_pit_stops").df()
    finally:
        con.close()
    return laps, pits, pd.read_parquet(d / "labels.parquet"), json.loads((d / "truth.json").read_text(encoding="utf-8"))


def _row(d):
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}


def recovery(model, baseline) -> dict:
    """Quão perto o modelo chega dos parâmetros físicos usados para gerar os dados."""
    ages = np.arange(2, 23)
    out = {"tyre_curve_mae_s": {}, "baseline_tyre_curve_mae_s": {}}
    for c in COMPOUNDS:
        truth = true_tyre_delta(np.full(ages.shape, c), ages) - true_tyre_delta(np.array([c]), np.array([1.0]))[0]
        out["tyre_curve_mae_s"][c] = float(np.mean(np.abs(mdl.tyre_curve(model, c, ages) - truth)))
        out["baseline_tyre_curve_mae_s"][c] = float(np.mean(np.abs(mdl.tyre_curve(baseline, c, ages) - truth)))
    d = model.predict(np.array(["MEDIUM"]), np.array([8.0]), np.array([40.0])) - model.predict(
        np.array(["MEDIUM"]), np.array([8.0]), np.array([10.0])
    )
    out["fuel_effect_10_to_40_s"] = float(d[0])
    out["fuel_effect_truth_s"] = -FUEL_S_PER_LAP * 30
    return out


def run(workdir: Path, races: int, dbt_bin: str | None) -> dict:
    result: dict = {
        "protocol": {
            "tune_seed": TUNE_SEED,
            "test_seeds": TEST_SEEDS,
            "no_anomaly_seeds": NO_ANOMALY_SEEDS,
            "races_per_season": races,
        }
    }

    # 1) modelo e simulador: uma temporada de teste, treino leave-one-race-out + modelo final
    laps, pits, _, truths = _season(workdir, TEST_SEEDS[0], races, None, dbt_bin)
    train_df = laps[["race_id", "driver", "lap_number", "compound", "tyre_life", "lap_delta_s"]]
    cv = mdl.leave_one_race_out(train_df)
    model, baseline = mdl.LapModel().fit(train_df), mdl.BaselineModel().fit(train_df)
    result["model_cv"] = {
        "rmse_naive_mean": float(cv["rmse_mean"].mean()),
        "rmse_baseline": float(cv["rmse_baseline"].mean()),
        "rmse_xgb": float(cv["rmse_xgb"].mean()),
    }
    result["recovery"] = recovery(model, baseline)
    pl = mdl.estimate_pit_loss(model, pits)
    truth_pl = float(np.mean([t["pit_in_extra_s"] + t["pit_out_extra_s"] for t in truths]))
    result["pit_loss"] = {**pl, "truth_mean_s": truth_pl, "abs_error_median_s": abs(pl["median_s"] - truth_pl)}

    oracle = TruthModel()
    rng = np.random.default_rng(0)

    class RandomModel:
        max_age = {c: 45 for c in COMPOUNDS}

        def predict(self, compound, tyre_life, lap_number):
            return rng.normal(0, 0.5, np.asarray(tyre_life).shape)

    regrets = [st.regret(model, oracle, n, 90.0, truth_pl)["regret_s"] for n in (52, 57, 62, 66, 70)]
    rand = [st.regret(RandomModel(), oracle, n, 90.0, truth_pl)["regret_s"] for n in (52, 57, 62, 66, 70)]
    result["strategy_regret_s"] = {
        "model": [round(x, 3) for x in regrets],
        "model_max": float(max(regrets)),
        "random_model_min": float(min(rand)),
    }

    # 2) anomalias: ajuste numa temporada, teste em outras, alarme falso em temporadas sem anomalia
    t_laps, _, t_labels, _ = _season(workdir, TUNE_SEED, races, 2, dbt_bin)
    tuning = anom.prepare(t_laps)
    grid_z = {
        (t, m): anom.evaluate(anom.detect_robust_z(tuning, t, m), t_labels)["f1"] for t, m in product([2.5, 3.0, 3.5], [1, 2, 3])
    }
    grid_i = {c: anom.evaluate(anom.detect_iforest(tuning, c), t_labels)["f1"] for c in [0.005, 0.01, 0.02]}
    (best_t, best_m), best_c = max(grid_z, key=grid_z.get), max(grid_i, key=grid_i.get)
    result["anomaly_tuning"] = {
        "robust_z": {"threshold": best_t, "min_consecutive": best_m, "f1_tune": grid_z[(best_t, best_m)]},
        "iforest": {"contamination": best_c, "f1_tune": grid_i[best_c]},
    }

    z_rows, i_rows = [], []
    for seed in TEST_SEEDS:
        lp, _, lab, _ = _season(workdir, seed, races, 2, dbt_bin)
        prep = anom.prepare(lp)
        z_rows.append(anom.evaluate(anom.detect_robust_z(prep, best_t, best_m), lab))
        i_rows.append(anom.evaluate(anom.detect_iforest(prep, best_c), lab))

    def pooled(rows):
        tp, fp, fn = (sum(r[k] for r in rows) for k in ("tp", "fp", "fn"))
        p, r = tp / (tp + fp) if tp + fp else 0.0, tp / (tp + fn) if tp + fn else 0.0
        return {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": p,
            "recall": r,
            "f1": 2 * p * r / (p + r) if p + r else 0.0,
            "n_anomalous": tp + fn,
        }

    result["anomaly_test"] = {"robust_z": pooled(z_rows), "iforest": pooled(i_rows)}
    fa_z, fa_i = 0, 0
    n_laps = 0
    for seed in NO_ANOMALY_SEEDS:
        lp, _, lab, _ = _season(workdir, seed, races, 0, dbt_bin)
        prep = anom.prepare(lp)
        fa_z += int(anom.detect_robust_z(prep, best_t, best_m)["is_flagged"].sum())
        fa_i += int(anom.detect_iforest(prep, best_c)["is_flagged"].sum())
        n_laps += len(prep)
    result["anomaly_clean_seasons"] = {"laps": n_laps, "false_alarms_robust_z": fa_z, "false_alarms_iforest": fa_i}
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dbt-bin", default=None)
    p.add_argument("--races", type=int, default=8)
    p.add_argument("--out", default="artifacts/evaluation.json")
    args = p.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        res = run(Path(tmp), args.races, args.dbt_bin)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()

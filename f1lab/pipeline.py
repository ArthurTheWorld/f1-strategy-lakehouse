"""Orquestração: dados -> Bronze -> dbt (Silver, Gold) -> treino -> publicação das análises.

    python -m f1lab.pipeline synth  --races 8 --seed 7        # gera corridas sintéticas em data/bronze
    python -m f1lab.pipeline build                            # carrega no DuckDB e roda o dbt
    python -m f1lab.pipeline train                            # treina, estima perda no pit, detecta anomalias
    python -m f1lab.pipeline all    --races 8 --seed 7        # tudo, em sequência

O dbt roda em um ambiente separado (conflito de dependências com o Streamlit): informe o executável em
`--dbt-bin` ou na variável DBT_BIN. Para dados reais, use `python -m f1lab.fetch_fastf1` no lugar de `synth`.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from . import anomaly as anom
from . import model as mdl
from .bronze import load_into_duckdb, write_bronze
from .schema import COMPOUNDS
from .synth import generate_season

ROOT = Path(__file__).resolve().parent.parent
DBT_DIR = ROOT / "dbt_project"

# parâmetros dos detectores, escolhidos na temporada de AJUSTE (ver evaluate.py), nunca na de teste
ROBUST_Z = {"threshold": 2.5, "min_consecutive": 2}
IFOREST = {"contamination": 0.01}


def run_dbt(db_path: Path, dbt_bin: str | None = None, command: str = "build") -> subprocess.CompletedProcess:
    exe = dbt_bin or os.environ.get("DBT_BIN") or shutil.which("dbt")
    if not exe:
        raise RuntimeError("dbt não encontrado: passe --dbt-bin ou defina DBT_BIN (ambiente com dbt-duckdb)")
    env = {**os.environ, "DBT_PROFILES_DIR": str(DBT_DIR), "F1_DB": str(Path(db_path).resolve())}
    proc = subprocess.run([exe, command, "--project-dir", str(DBT_DIR)], env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"dbt {command} falhou:\n{proc.stdout[-3000:]}\n{proc.stderr[-1000:]}")
    return proc


def synth(data_dir: Path, races: int, seed: int, anomaly_events: int | None = None) -> None:
    laps, races_df, truths, labels = generate_season(races, seed=seed, anomaly_events=anomaly_events)
    write_bronze(laps, races_df, data_dir / "bronze")
    labels.to_parquet(data_dir / "labels.parquet", index=False)  # verdade fica FORA do bronze
    (data_dir / "truth.json").write_text(json.dumps(truths, indent=1), encoding="utf-8")


def build(data_dir: Path, dbt_bin: str | None = None) -> Path:
    db = data_dir / "f1.duckdb"
    load_into_duckdb(db, data_dir / "bronze")
    run_dbt(db, dbt_bin)
    return db


def train(db_path: Path, artifacts_dir: Path) -> dict:
    """Treina o modelo, estima a perda no pit, detecta anomalias e publica as tabelas `analytics.*`."""
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    df = mdl.load_training(db_path)
    cv = mdl.leave_one_race_out(df)
    model = mdl.LapModel().fit(df)
    model.save(artifacts_dir / "model")

    con = duckdb.connect(str(db_path))
    try:
        pits = con.execute("select * from gold.fct_pit_stops").df()
        laps = con.execute("select * from gold.fct_laps_model").df()
        pit_loss = mdl.estimate_pit_loss(model, pits)

        ages = np.arange(1, 36)
        curves = pd.concat(
            [
                pd.DataFrame(
                    {
                        "compound": c,
                        "tyre_life": ages,
                        "effect_s": mdl.tyre_curve(model, c, ages),
                        "supported": ages <= model.max_age.get(c, 0),
                    }
                )
                for c in COMPOUNDS
            ],
            ignore_index=True,
        )

        prepared = anom.prepare(laps)
        z = anom.detect_robust_z(prepared, **ROBUST_Z).assign(detector="robust_z")
        iso = anom.detect_iforest(prepared, **IFOREST).assign(detector="iforest")
        flags = pd.concat([z, iso], ignore_index=True)

        con.execute("create schema if not exists analytics")
        for name, frame in (("tyre_curves", curves), ("anomaly_flags", flags), ("cv_by_race", cv)):
            con.register("tmp_frame", frame)
            con.execute(f"create or replace table analytics.{name} as select * from tmp_frame")
            con.unregister("tmp_frame")
        con.execute(
            "create or replace table analytics.pit_loss as select ? as mean_s, ? as median_s, ? as n",
            [pit_loss["mean_s"], pit_loss["median_s"], pit_loss["n"]],
        )
    finally:
        con.close()

    summary = {
        "cv_rmse_naive_mean": float(cv["rmse_mean"].mean()),
        "cv_rmse_baseline": float(cv["rmse_baseline"].mean()),
        "cv_rmse_xgb": float(cv["rmse_xgb"].mean()),
        "pit_loss": pit_loss,
        "max_age": model.max_age,
        "n_training_laps": int(len(df)),
        "n_races": int(df["race_id"].nunique()),
    }
    (artifacts_dir / "metrics.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["synth", "build", "train", "all"])
    p.add_argument("--data-dir", default=str(ROOT / "data"))
    p.add_argument("--artifacts-dir", default=str(ROOT / "artifacts"))
    p.add_argument("--races", type=int, default=8)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--dbt-bin", default=None)
    args = p.parse_args(argv)
    data, art = Path(args.data_dir), Path(args.artifacts_dir)

    if args.command in ("synth", "all"):
        synth(data, args.races, args.seed)
        print(f"bronze sintético gravado em {data / 'bronze'}")
    if args.command in ("build", "all"):
        db = build(data, args.dbt_bin)
        print(f"silver e gold prontos em {db}")
    if args.command in ("train", "all"):
        s = train(data / "f1.duckdb", art)
        print(json.dumps(s, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

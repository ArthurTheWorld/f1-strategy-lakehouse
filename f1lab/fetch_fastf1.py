"""Conector de DADOS REAIS via FastF1.

ESTADO DE VALIDAÇÃO (leia antes de confiar):
- `laps_to_bronze` (a conversão) É testada, com um DataFrame no formato do `fastf1.core.Laps`.
- `fetch_race` (a chamada de rede ao FastF1) NÃO foi executada: o ambiente onde este projeto foi construído
  bloqueia os servidores da F1. Rode localmente e confira antes de usar os resultados.

Uso:
    python -m f1lab.fetch_fastf1 --year 2024 --rounds 1 2 3 --out data/bronze
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from .bronze import write_bronze
from .schema import BRONZE_LAP_COLUMNS, BRONZE_RACE_COLUMNS, make_race_id

_TIMEDELTA_TO_SECONDS = {
    "LapTime": "LapTime_s",
    "Sector1Time": "Sector1Time_s",
    "Sector2Time": "Sector2Time_s",
    "Sector3Time": "Sector3Time_s",
    "PitInTime": "PitInTime_s",
    "PitOutTime": "PitOutTime_s",
}


def laps_to_bronze(laps: pd.DataFrame, year: int, round_: int, circuit: str):
    """Converte um `Laps` do FastF1 no contrato Bronze. Devolve (laps_bronze, race_row)."""
    required = [
        "Driver",
        "DriverNumber",
        "Team",
        "LapNumber",
        "Stint",
        "Compound",
        "TyreLife",
        "FreshTyre",
        "TrackStatus",
        "Position",
        "IsAccurate",
        "IsPersonalBest",
        "SpeedI1",
        "SpeedI2",
        "SpeedFL",
        "SpeedST",
        *_TIMEDELTA_TO_SECONDS,
    ]
    missing = [c for c in required if c not in laps.columns]
    if missing:
        raise ValueError(f"o objeto de voltas não tem as colunas esperadas do FastF1: {missing}")

    df = pd.DataFrame(index=laps.index)
    race_id = make_race_id(year, round_)
    df["race_id"] = race_id
    for col in ["Driver", "DriverNumber", "Team", "Compound", "TrackStatus"]:
        df[col] = laps[col].astype("string").astype(object).where(laps[col].notna(), None)
    for col in ["LapNumber", "Stint", "TyreLife", "Position", "SpeedI1", "SpeedI2", "SpeedFL", "SpeedST"]:
        df[col] = pd.to_numeric(laps[col], errors="coerce").astype(float)
    for src, dst in _TIMEDELTA_TO_SECONDS.items():
        df[dst] = pd.to_timedelta(laps[src], errors="coerce").dt.total_seconds()
    df["FreshTyre"] = laps["FreshTyre"].fillna(False).astype(bool)
    df["IsAccurate"] = laps["IsAccurate"].fillna(False).astype(bool)
    df["IsPersonalBest"] = laps["IsPersonalBest"].fillna(False).astype(bool)
    df["Deleted"] = laps["Deleted"].fillna(False).astype(bool) if "Deleted" in laps.columns else False
    df["Compound"] = df["Compound"].str.upper()

    df = df[df["LapNumber"].notna()].reset_index(drop=True)
    race = {
        "race_id": race_id,
        "year": year,
        "round": round_,
        "circuit": circuit,
        "n_laps": int(np.nanmax(df["LapNumber"])),
        "source": "fastf1",
    }
    return df[BRONZE_LAP_COLUMNS], {k: race[k] for k in BRONZE_RACE_COLUMNS}


def fetch_race(year: int, round_: int, cache_dir: str = ".fastf1_cache"):  # pragma: no cover - precisa de rede
    import os

    import fastf1

    os.makedirs(cache_dir, exist_ok=True)  # o FastF1 exige que a pasta exista
    fastf1.Cache.enable_cache(cache_dir)
    session = fastf1.get_session(year, round_, "R")
    session.load(laps=True, telemetry=False, weather=False, messages=False)
    circuit = str(session.event.get("Location", f"round {round_}"))
    return laps_to_bronze(session.laps, year, round_, circuit)


def main(argv=None):  # pragma: no cover - precisa de rede
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--rounds", type=int, nargs="+", required=True)
    p.add_argument("--out", default="data/bronze")
    args = p.parse_args(argv)
    laps, races = [], []
    for rnd in args.rounds:
        lp, race = fetch_race(args.year, rnd)
        laps.append(lp)
        races.append(race)
        print(f"rodada {rnd}: {len(lp)} voltas")
    write_bronze(pd.concat(laps, ignore_index=True), pd.DataFrame(races), args.out)
    print(f"bronze gravado em {args.out}")


if __name__ == "__main__":  # pragma: no cover
    main()

"""Camada Bronze: grava o que chegou, sem limpar, com metadados de carga."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd

from .schema import BRONZE_LAP_COLUMNS, BRONZE_RACE_COLUMNS


def validate_bronze(laps: pd.DataFrame, races: pd.DataFrame) -> None:
    """Falha cedo se o contrato mudou (coluna faltando) ou se a chave está duplicada."""
    missing = [c for c in BRONZE_LAP_COLUMNS if c not in laps.columns]
    if missing:
        raise ValueError(f"laps sem as colunas do contrato: {missing}")
    missing = [c for c in BRONZE_RACE_COLUMNS if c not in races.columns]
    if missing:
        raise ValueError(f"races sem as colunas do contrato: {missing}")
    if laps.duplicated(["race_id", "Driver", "LapNumber"]).any():
        raise ValueError("chave (race_id, Driver, LapNumber) duplicada no bronze")
    unknown = set(laps["race_id"]) - set(races["race_id"])
    if unknown:
        raise ValueError(f"voltas de corridas ausentes em races: {sorted(unknown)}")


def write_bronze(laps: pd.DataFrame, races: pd.DataFrame, out_dir: str | Path) -> Path:
    """Parquet particionado por corrida + metadados `_ingested_at`."""
    validate_bronze(laps, races)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).replace(tzinfo=None)
    (laps.assign(_ingested_at=stamp)[[*BRONZE_LAP_COLUMNS, "_ingested_at"]]).to_parquet(out / "laps.parquet", index=False)
    races[BRONZE_RACE_COLUMNS].assign(_ingested_at=stamp).to_parquet(out / "races.parquet", index=False)
    return out


def load_into_duckdb(db_path: str | Path, bronze_dir: str | Path) -> None:
    """Cria o schema `bronze` no DuckDB lendo os Parquets. Recria as tabelas (carga completa)."""
    bronze = Path(bronze_dir)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        con.execute("create schema if not exists bronze")
        for name in ("laps", "races"):
            parquet = (bronze / f"{name}.parquet").as_posix()
            con.execute(f"create or replace table bronze.{name} as select * from read_parquet('{parquet}')")
    finally:
        con.close()

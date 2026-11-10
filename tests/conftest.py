import os
import shutil
from pathlib import Path

import duckdb
import pytest

from f1lab import pipeline
from f1lab.synth import generate_season


def _dbt_bin():
    return os.environ.get("DBT_BIN") or shutil.which("dbt")


requires_dbt = pytest.mark.skipif(_dbt_bin() is None, reason="dbt não encontrado (defina DBT_BIN)")


@pytest.fixture(scope="session")
def season_raw():
    """(laps, races, truths, labels) brutos do gerador, sem passar pelo dbt."""
    return generate_season(8, seed=7)


@pytest.fixture(scope="session")
def season_db(tmp_path_factory):
    """Temporada completa passada pelo pipeline real: Bronze -> DuckDB -> dbt build."""
    if _dbt_bin() is None:
        pytest.skip("dbt não encontrado (defina DBT_BIN)")
    d = tmp_path_factory.mktemp("season")
    pipeline.synth(d, 8, 7)
    return pipeline.build(d, _dbt_bin())


@pytest.fixture(scope="session")
def gold(season_db):
    con = duckdb.connect(str(season_db), read_only=True)
    try:
        return {
            t: con.execute(f"select * from gold.{t}").df() for t in ("fct_laps_model", "fct_pit_stops", "fct_stints", "dim_races")
        }
    finally:
        con.close()


@pytest.fixture(scope="session")
def trained(season_db, tmp_path_factory):
    art = tmp_path_factory.mktemp("artifacts")
    # copia o banco: train() grava as tabelas analytics.*
    db = Path(tmp_path_factory.mktemp("trained")) / "f1.duckdb"
    shutil.copy(season_db, db)
    summary = pipeline.train(db, art)
    return db, art, summary

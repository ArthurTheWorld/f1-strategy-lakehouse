"""O dbt passou? Isso não basta: aqui o Gold é recalculado de forma independente em pandas e comparado."""

import duckdb
import numpy as np
import pandas as pd
import pytest

from f1lab import pipeline
from f1lab.bronze import load_into_duckdb, write_bronze
from tests.conftest import _dbt_bin, requires_dbt

pytestmark = requires_dbt


def _bronze(season_db):
    con = duckdb.connect(str(season_db), read_only=True)
    try:
        return con.execute("select * from bronze.laps").df()
    finally:
        con.close()


def _independent_clean(b: pd.DataFrame) -> pd.DataFrame:
    ok = (
        (b["LapNumber"] > 1)
        & b["LapTime_s"].notna()
        & ~b["Deleted"]
        & b["IsAccurate"]
        & (b["TrackStatus"] == "1")
        & b["PitInTime_s"].isna()
        & b["PitOutTime_s"].isna()
        & b["Compound"].isin(["SOFT", "MEDIUM", "HARD"])
    )
    return b[ok]


def test_gold_laps_match_an_independent_pandas_filter(season_db, gold):
    clean = _independent_clean(_bronze(season_db))
    g = gold["fct_laps_model"]
    assert len(g) == len(clean)
    key = ["race_id", "Driver", "LapNumber"]
    assert set(map(tuple, clean[key].to_numpy())) == set(
        map(tuple, g.rename(columns={"driver": "Driver", "lap_number": "LapNumber"})[key].to_numpy())
    )


def test_gold_normalisation_matches_pandas_median(season_db, gold):
    clean = _independent_clean(_bronze(season_db))
    med = clean.groupby("race_id")["LapTime_s"].median()
    d = gold["dim_races"].set_index("race_id")["race_median_lap_s"]
    np.testing.assert_allclose(d.sort_index().to_numpy(), med.sort_index().to_numpy())
    g = gold["fct_laps_model"]
    np.testing.assert_allclose(g["lap_delta_s"], g["lap_time_s"] - g["race_id"].map(med))
    for _race, grp in g.groupby("race_id"):
        assert abs(grp["lap_delta_s"].median()) < 1e-9


def test_gold_pit_stops_match_pandas(season_db, gold):
    b = _bronze(season_db)
    ins = b[b["PitInTime_s"].notna() & (b["TrackStatus"] == "1")][["race_id", "Driver", "LapNumber"]]
    outs = b[b["PitOutTime_s"].notna() & (b["TrackStatus"] == "1")][["race_id", "Driver", "LapNumber"]].assign(
        LapNumber=lambda d: d.LapNumber - 1
    )
    expected = ins.merge(outs, on=["race_id", "Driver", "LapNumber"])
    assert len(gold["fct_pit_stops"]) == len(expected)
    assert (gold["fct_pit_stops"]["out_lap"] == gold["fct_pit_stops"]["in_lap"] + 1).all()


def test_gold_stints_cover_every_lap_exactly_once(season_db, gold):
    b = _bronze(season_db)
    assert gold["fct_stints"]["n_laps"].sum() == len(b)


def test_clean_laps_exclude_everything_the_rules_exclude(gold):
    g = gold["fct_laps_model"]
    assert (g["lap_number"] > 1).all() and g["lap_time_s"].notna().all()


def test_dbt_fails_when_the_data_is_corrupted(season_raw, tmp_path):
    """Controle negativo: com uma chave duplicada no Silver, o dbt build TEM que falhar."""
    laps, races = season_raw[0], season_raw[1]
    write_bronze(laps, races, tmp_path / "bronze")
    load_into_duckdb(tmp_path / "f1.duckdb", tmp_path / "bronze")
    con = duckdb.connect(str(tmp_path / "f1.duckdb"))
    con.execute("insert into bronze.laps select * from bronze.laps limit 1")  # duplica uma volta
    con.close()
    with pytest.raises(RuntimeError, match="falhou"):
        pipeline.run_dbt(tmp_path / "f1.duckdb", _dbt_bin())

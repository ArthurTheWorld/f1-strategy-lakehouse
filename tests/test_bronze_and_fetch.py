import numpy as np
import pandas as pd
import pytest

from f1lab.bronze import load_into_duckdb, validate_bronze, write_bronze
from f1lab.fetch_fastf1 import laps_to_bronze
from f1lab.schema import BRONZE_LAP_COLUMNS


def test_validate_rejects_missing_column(season_raw):
    laps, races = season_raw[0], season_raw[1]
    with pytest.raises(ValueError, match="sem as colunas"):
        validate_bronze(laps.drop(columns=["TyreLife"]), races)


def test_validate_rejects_duplicate_key(season_raw):
    laps, races = season_raw[0], season_raw[1]
    with pytest.raises(ValueError, match="duplicada"):
        validate_bronze(pd.concat([laps, laps.head(1)], ignore_index=True), races)


def test_validate_rejects_laps_of_unknown_race(season_raw):
    laps, races = season_raw[0], season_raw[1]
    with pytest.raises(ValueError, match="ausentes em races"):
        validate_bronze(laps, races.iloc[1:])


def test_write_and_load_roundtrip_keeps_every_row(season_raw, tmp_path):
    import duckdb

    laps, races = season_raw[0], season_raw[1]
    write_bronze(laps, races, tmp_path / "bronze")
    load_into_duckdb(tmp_path / "f1.duckdb", tmp_path / "bronze")
    con = duckdb.connect(str(tmp_path / "f1.duckdb"), read_only=True)
    assert con.execute("select count(*) from bronze.laps").fetchone()[0] == len(laps)
    assert con.execute("select count(*) from bronze.races").fetchone()[0] == len(races)
    assert con.execute("select count(*) from bronze.laps where _ingested_at is null").fetchone()[0] == 0


def _as_fastf1(laps: pd.DataFrame) -> pd.DataFrame:
    """Reconstrói o formato do fastf1.core.Laps: tempos em timedelta, nomes sem sufixo _s."""
    df = laps.copy()
    for col in ["LapTime", "Sector1Time", "Sector2Time", "Sector3Time", "PitInTime", "PitOutTime"]:
        df[col] = pd.to_timedelta(df[f"{col}_s"], unit="s")
        df = df.drop(columns=f"{col}_s")
    return df.drop(columns="race_id")


def test_laps_to_bronze_roundtrips_a_fastf1_shaped_frame(season_raw):
    laps = season_raw[0]
    one = laps[laps["race_id"] == "2024-02-R"].reset_index(drop=True)
    out, race = laps_to_bronze(_as_fastf1(one), 2024, 2, "Synth GP 02")
    assert list(out.columns) == BRONZE_LAP_COLUMNS
    for col in ["LapTime_s", "PitInTime_s", "SpeedST"]:
        np.testing.assert_allclose(out[col].to_numpy(), one[col].to_numpy(), atol=1e-6, equal_nan=True)
    assert race["source"] == "fastf1" and race["race_id"] == "2024-02-R" and race["n_laps"] == int(one["LapNumber"].max())


def test_laps_to_bronze_handles_nat_none_and_lowercase_compounds(season_raw):
    one = season_raw[0].query("race_id == '2024-01-R' and Driver == 'D01'").reset_index(drop=True)
    ff = _as_fastf1(one)
    ff.loc[0, "LapTime"] = pd.NaT
    ff.loc[1, "Compound"] = None
    ff["Compound"] = ff["Compound"].str.lower()
    out, _ = laps_to_bronze(ff, 2024, 1, "X")
    assert np.isnan(out.loc[0, "LapTime_s"])
    assert out.loc[1, "Compound"] is None or pd.isna(out.loc[1, "Compound"])
    assert out.loc[2, "Compound"] in ("SOFT", "MEDIUM", "HARD")


def test_laps_to_bronze_rejects_unexpected_schema(season_raw):
    one = season_raw[0].query("race_id == '2024-01-R'")
    with pytest.raises(ValueError, match="colunas esperadas"):
        laps_to_bronze(_as_fastf1(one).drop(columns=["TrackStatus"]), 2024, 1, "X")

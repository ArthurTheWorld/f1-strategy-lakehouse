import numpy as np
import pandas as pd

from f1lab.schema import BRONZE_LAP_COLUMNS, COMPOUNDS
from f1lab.synth import FUEL_S_PER_LAP, generate_season, true_tyre_delta


def test_laps_follow_the_bronze_contract(season_raw):
    laps = season_raw[0]
    assert list(laps.columns) == BRONZE_LAP_COLUMNS
    assert not laps.duplicated(["race_id", "Driver", "LapNumber"]).any()


def test_same_seed_is_deterministic_and_other_seed_differs():
    a, _, _, _ = generate_season(2, seed=3)
    b, _, _, _ = generate_season(2, seed=3)
    c, _, _, _ = generate_season(2, seed=4)
    pd.testing.assert_frame_equal(a, b)
    assert not a["LapTime_s"].equals(c["LapTime_s"])


def test_every_driver_runs_every_lap_with_at_least_two_compounds(season_raw):
    laps, races, _, _ = season_raw
    n = races.set_index("race_id")["n_laps"]
    for (race, drv), g in laps.groupby(["race_id", "Driver"]):
        assert sorted(g["LapNumber"]) == list(range(1, int(n[race]) + 1))
        assert g["Compound"].nunique() >= 2, (race, drv)


def test_pit_in_and_out_laps_pair_up(season_raw):
    laps = season_raw[0]
    for _, g in laps.groupby(["race_id", "Driver"]):
        ins = set(g.loc[g["PitInTime_s"].notna(), "LapNumber"])
        outs = set(g.loc[g["PitOutTime_s"].notna(), "LapNumber"])
        assert {i + 1 for i in ins} == outs


def test_tyre_life_resets_on_new_stint_and_grows_inside_it(season_raw):
    laps = season_raw[0].sort_values(["race_id", "Driver", "LapNumber"])
    step = laps.groupby(["race_id", "Driver", "Stint"])["TyreLife"].diff().dropna()
    assert (step == 1).all()


def test_track_status_codes_are_known_and_safety_laps_are_slow(season_raw):
    laps = season_raw[0]
    assert set(laps["TrackStatus"]).issubset({"1", "12", "14", "4", "41", "6", "67"})
    sc = laps[laps["TrackStatus"] == "4"]["LapTime_s"].median()
    clear = laps[(laps["TrackStatus"] == "1") & laps["PitInTime_s"].isna() & laps["PitOutTime_s"].isna()]["LapTime_s"].median()
    assert sc > clear * 1.2


def test_anomaly_labels_never_fall_on_pit_or_safety_laps(season_raw):
    laps, _, _, labels = season_raw
    m = laps.merge(labels, on=["race_id", "Driver", "LapNumber"])
    bad = m[m["is_anomaly"] & ((m["TrackStatus"] != "1") | m["PitInTime_s"].notna() | m["PitOutTime_s"].notna())]
    assert bad.empty
    assert labels["is_anomaly"].sum() > 0


def test_anomalous_laps_are_really_slower_in_the_straights(season_raw):
    laps, _, _, labels = season_raw
    m = laps.merge(labels, on=["race_id", "Driver", "LapNumber"]).dropna(subset=["SpeedST"])
    m = m[m["TrackStatus"] == "1"]
    assert m[m["is_anomaly"]]["SpeedST"].mean() < m[~m["is_anomaly"]]["SpeedST"].mean() - 5


def test_zero_anomaly_option_really_has_none():
    _, _, _, labels = generate_season(3, seed=9, anomaly_events=0)
    assert labels["is_anomaly"].sum() == 0


def test_truth_function_is_monotone_in_age_and_ranks_compounds():
    ages = np.arange(1, 40, dtype=float)
    for c in COMPOUNDS:
        assert (np.diff(true_tyre_delta(np.full(ages.shape, c), ages)) > 0).all()
    one = {c: float(true_tyre_delta(np.array([c]), np.array([1.0]))[0]) for c in COMPOUNDS}
    assert one["SOFT"] < one["MEDIUM"] < one["HARD"]
    assert FUEL_S_PER_LAP > 0

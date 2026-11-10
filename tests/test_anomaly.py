import numpy as np
import pandas as pd
import pytest

from f1lab import anomaly as A


def _frame(speed_drop_laps=(), n=40, seed=0, noise=1.2):
    rng = np.random.default_rng(seed)
    rows = []
    for lap in range(2, n + 2):
        base = 300 + rng.normal(0, 2)
        drop = 15.0 if lap in speed_drop_laps else 0.0
        rows.append(
            {"race_id": "R1", "driver": "D01", "lap_number": lap, **{c: base - drop + rng.normal(0, noise) for c in A._SPEED}}
        )
    return pd.DataFrame(rows)


def test_prepare_drops_laps_with_missing_speeds_and_centers_per_driver():
    df = _frame()
    df.loc[3, "speed_st"] = np.nan
    out = A.prepare(df)
    assert len(out) == len(df) - 1
    assert abs(out["res_speed_st"].median()) < 1e-9


def test_sustained_speed_drop_is_flagged_and_normal_laps_are_not():
    df = A.prepare(_frame(speed_drop_laps=range(15, 21)))
    f = A.detect_robust_z(df, threshold=2.5, min_consecutive=2).set_index("lap_number")["is_flagged"]
    assert f.loc[15:20].all()
    assert not f.loc[2:12].any() and not f.loc[25:].any()


def test_a_single_lap_spike_is_ignored_when_two_consecutive_laps_are_required():
    df = A.prepare(_frame(speed_drop_laps=[20]))
    assert not A.detect_robust_z(df, 2.5, 2)["is_flagged"].any()
    assert A.detect_robust_z(df, 2.5, 1)["is_flagged"].any()  # com exigência 1, o pico isolado aparece


def test_speed_above_normal_is_not_an_anomaly_for_the_detectors():
    df = _frame()
    df.loc[df["lap_number"].between(15, 20), A._SPEED] += 15  # mais rápido, não falha
    prepared = A.prepare(df)
    assert not A.detect_robust_z(prepared, 2.5, 2)["is_flagged"].any()


def test_clean_driver_has_no_false_alarms_over_many_seeds():
    alarms = sum(int(A.detect_robust_z(A.prepare(_frame(seed=s, n=60)), 2.5, 2)["is_flagged"].sum()) for s in range(30))
    assert alarms == 0


def test_evaluate_counts_by_hand():
    flags = pd.DataFrame({"race_id": "R", "driver": "D", "lap_number": [1, 2, 3, 4], "is_flagged": [True, True, False, False]})
    labels = pd.DataFrame({"race_id": "R", "Driver": "D", "LapNumber": [1, 2, 3, 4], "is_anomaly": [True, False, True, False]})
    m = A.evaluate(flags, labels)
    assert (m["tp"], m["fp"], m["fn"]) == (1, 1, 1)
    assert m["precision"] == pytest.approx(0.5) and m["recall"] == pytest.approx(0.5) and m["f1"] == pytest.approx(0.5)
    assert m["false_alarm_rate"] == pytest.approx(0.5)


def test_evaluate_with_no_flags_gives_zero_not_a_division_error():
    flags = pd.DataFrame({"race_id": ["R"], "driver": ["D"], "lap_number": [1], "is_flagged": [False]})
    labels = pd.DataFrame({"race_id": ["R"], "Driver": ["D"], "LapNumber": [1], "is_anomaly": [False]})
    assert A.evaluate(flags, labels)["f1"] == 0.0


def test_on_the_pipeline_data_the_default_detector_finds_most_injected_faults(season_raw, gold):
    labels = season_raw[3]
    res = A.evaluate(A.detect_robust_z(A.prepare(gold["fct_laps_model"]), 2.5, 2), labels)
    # Esperado: ~1 alarme falso por temporada de 8 corridas (taxa medida ~1,4e-4 por volta; 6 temporadas
    # diferentes deram de 0 a 2). Por isso o limite é em ALARMES FALSOS, não em precisão: com ~10 voltas
    # anômalas numa temporada, 2 falsos derrubam a precisão para 0,8 sem que o detector tenha piorado.
    assert res["recall"] > 0.6 and res["fp"] <= 4 and res["false_alarm_rate"] < 0.001

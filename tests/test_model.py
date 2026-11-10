import json

import duckdb
import numpy as np
import pytest

from f1lab import model as M
from f1lab.schema import COMPOUNDS
from f1lab.synth import FUEL_S_PER_LAP, true_tyre_delta
from tests.conftest import requires_dbt

pytestmark = requires_dbt


@pytest.fixture(scope="module")
def df(season_db):
    return M.load_training(season_db)


@pytest.fixture(scope="module")
def fitted(df):
    return M.LapModel().fit(df), M.BaselineModel().fit(df)


def test_design_matrix_rejects_unknown_compound():
    with pytest.raises(ValueError, match="composto desconhecido"):
        M.design_matrix(np.array(["WET"]), [3], [10])


def test_leave_one_race_out_beats_the_naive_mean_and_the_baseline(df):
    cv = M.leave_one_race_out(df)
    assert (cv["rmse_xgb"] < cv["rmse_mean"]).all()  # em TODAS as corridas deixadas de fora, melhor que prever a média
    assert cv["rmse_xgb"].mean() < 0.6 * cv["rmse_mean"].mean()  # observado em 7 temporadas: razão entre 0,38 e 0,46
    assert cv["rmse_xgb"].mean() < cv["rmse_baseline"].mean()  # e melhor que a regressão linear


def test_model_is_monotone_in_tyre_age_and_fuel(fitted):
    gbm, _ = fitted
    ages = np.arange(1, 40, dtype=float)
    for c in COMPOUNDS:
        p = gbm.predict(np.full(ages.shape, c), ages, np.full(ages.shape, 30.0))
        assert (np.diff(p) >= -1e-9).all(), c  # mais idade nunca acelera
    laps = np.arange(2, 70, dtype=float)
    p = gbm.predict(np.full(laps.shape, "MEDIUM"), np.full(laps.shape, 10.0), laps)
    assert (np.diff(p) <= 1e-9).all()  # menos combustível nunca desacelera


def test_recovers_the_tyre_degradation_that_generated_the_data(fitted):
    gbm, base = fitted
    ages = np.arange(2, 23)
    for c in COMPOUNDS:
        truth = true_tyre_delta(np.full(ages.shape, c), ages) - true_tyre_delta(np.array([c]), np.array([1.0]))[0]
        mae_gbm = np.mean(np.abs(M.tyre_curve(gbm, c, ages) - truth))
        mae_base = np.mean(np.abs(M.tyre_curve(base, c, ages) - truth))
        assert mae_gbm < 0.25, (c, mae_gbm)
        assert mae_gbm < mae_base, (c, mae_gbm, mae_base)  # o linear erra porque a verdade tem termo quadrático


def test_recovers_the_fuel_effect(fitted):
    gbm, _ = fitted
    d = gbm.predict(np.array(["MEDIUM"]), np.array([8.0]), np.array([40.0])) - gbm.predict(
        np.array(["MEDIUM"]), np.array([8.0]), np.array([10.0])
    )
    assert abs(d[0] - (-FUEL_S_PER_LAP * 30)) < 0.25


def test_pit_loss_estimate_is_close_to_the_truth(season_db, df, fitted):
    gbm, _ = fitted
    con = duckdb.connect(str(season_db), read_only=True)
    pits = con.execute("select * from gold.fct_pit_stops").df()
    con.close()
    truths = json.loads((season_db.parent / "truth.json").read_text(encoding="utf-8"))
    truth = np.mean([t["pit_in_extra_s"] + t["pit_out_extra_s"] for t in truths])
    est = M.estimate_pit_loss(gbm, pits)
    assert est["n"] > 100 and abs(est["median_s"] - truth) < 1.0


def test_pit_loss_with_no_stops_is_nan_not_an_exception(fitted, gold):
    out = M.estimate_pit_loss(fitted[0], gold["fct_pit_stops"].iloc[0:0])
    assert out["n"] == 0 and np.isnan(out["median_s"])


def test_max_age_comes_from_the_data(df, fitted):
    gbm, _ = fitted
    for c in COMPOUNDS:
        assert gbm.max_age[c] <= df.loc[df["compound"] == c, "tyre_life"].max()
        assert gbm.max_age[c] >= 20


def test_save_and_load_give_identical_predictions(fitted, tmp_path):
    gbm, _ = fitted
    gbm.save(tmp_path)
    again = M.LapModel.load(tmp_path)
    c, a, lap = np.array(["SOFT", "HARD", "MEDIUM"]), np.array([3.0, 20.0, 11.0]), np.array([5.0, 40.0, 22.0])
    np.testing.assert_allclose(gbm.predict(c, a, lap), again.predict(c, a, lap))
    assert again.max_age == gbm.max_age

import numpy as np
import pytest

from f1lab import strategy as ST
from f1lab.schema import COMPOUNDS
from f1lab.synth import TruthModel
from tests.conftest import requires_dbt

pytestmark = requires_dbt


@pytest.fixture(scope="module")
def model(trained):
    from f1lab.model import LapModel

    return LapModel.load(trained[1] / "model")


def test_table_total_equals_an_independent_stint_by_stint_sum(model):
    top = ST.enumerate_strategies(model, 57, 90.0, 21.0, top=5)
    for _, r in top.iterrows():
        again = ST.strategy_time(model, r["compounds"], r["pit_laps"], 57, 90.0, 21.0)
        assert again == pytest.approx(r["total_time_s"], abs=1e-3)  # float32 do XGBoost


def test_every_strategy_respects_the_rules(model):
    res = ST.enumerate_strategies(model, 60, 90.0, 21.0, top=200, min_stint=10)
    assert len(res) == 200
    for _, r in res.iterrows():
        assert len(set(r["compounds"])) >= 2
        bounds = [0, *r["pit_laps"], 60]
        lengths = np.diff(bounds)
        assert (lengths >= 10).all()
        assert all(n <= model.max_age[c] for n, c in zip(lengths, r["compounds"], strict=True))
    assert res["total_time_s"].is_monotonic_increasing and res["gap_s"].iloc[0] == 0


def test_pit_loss_changes_the_answer_the_right_way(model):
    cheap = ST.enumerate_strategies(model, 57, 90.0, 5.0, top=1).iloc[0]
    costly = ST.enumerate_strategies(model, 57, 90.0, 60.0, top=1).iloc[0]
    assert costly["stops"] <= cheap["stops"]
    assert costly["stops"] == 1  # parada cara: só uma


def test_no_valid_strategy_returns_empty_instead_of_crashing(model):
    assert ST.enumerate_strategies(model, 10, 90.0, 21.0, min_stint=8).empty


def test_oracle_has_zero_regret_against_itself():
    assert ST.regret(TruthModel(), TruthModel(), 57, 90.0, 21.0)["regret_s"] == pytest.approx(0.0, abs=1e-9)


def test_trained_model_picks_near_optimal_strategies_and_a_random_one_does_not(model):
    oracle = TruthModel()
    good = [ST.regret(model, oracle, n, 90.0, 21.0)["regret_s"] for n in (52, 57, 62, 66)]
    # segundos perdidos (de ~5.700 s de corrida) contra a melhor estratégia da verdade. Observado em 7
    # temporadas: pior caso de 0,01 a 3,2 s; o erro cresce nas corridas longas, onde falta dado de pneu velho.
    assert max(good) < 4.5

    class RandomModel:
        max_age = {c: 45 for c in COMPOUNDS}

        def __init__(self, seed):
            self.rng = np.random.default_rng(seed)

        def predict(self, compound, tyre_life, lap_number):
            return self.rng.normal(0, 0.5, np.asarray(tyre_life).shape)

    bad = [ST.regret(RandomModel(s), oracle, 57, 90.0, 21.0)["regret_s"] for s in range(4)]
    assert min(bad) > 2.5 * max(good)  # controle negativo: o teste distingue modelo bom de modelo ruim

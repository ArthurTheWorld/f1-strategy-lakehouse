import json
from pathlib import Path

import duckdb
import pytest

from f1lab import pipeline
from tests.conftest import requires_dbt

APP = str(Path(__file__).resolve().parent.parent / "dashboard" / "app.py")

pytestmark = requires_dbt


def test_train_publishes_every_artifact_and_table(trained):
    db, art, summary = trained
    assert (art / "model" / "lap_model.json").exists() and (art / "metrics.json").exists()
    assert json.loads((art / "metrics.json").read_text(encoding="utf-8"))["n_races"] == 8
    con = duckdb.connect(str(db), read_only=True)
    tables = {
        r[0] for r in con.execute("select table_name from information_schema.tables where table_schema='analytics'").fetchall()
    }
    assert tables == {"tyre_curves", "anomaly_flags", "cv_by_race", "pit_loss"}
    assert set(con.execute("select distinct detector from analytics.anomaly_flags").df()["detector"]) == {"robust_z", "iforest"}
    assert con.execute("select count(*) from analytics.cv_by_race").fetchone()[0] == 8
    con.close()
    assert summary["cv_rmse_xgb"] < summary["cv_rmse_baseline"] < summary["cv_rmse_naive_mean"]


def test_run_dbt_without_a_binary_gives_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.delenv("DBT_BIN", raising=False)
    monkeypatch.setattr(pipeline.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="dbt não encontrado"):
        pipeline.run_dbt(tmp_path / "x.duckdb")


def test_dashboard_renders_every_tab_without_errors(trained, monkeypatch):
    from streamlit.testing.v1 import AppTest

    db, art, _ = trained
    monkeypatch.setenv("F1_DB", str(db))
    monkeypatch.setenv("F1_ARTIFACTS", str(art))
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert not at.exception
    assert [t.label for t in at.tabs] == ["Corrida", "Equipes", "Degradação", "Estratégia", "Anomalias"]
    assert any("SINTÉTICOS" in w.value for w in at.warning)  # nunca esconder que os dados são sintéticos
    at.button_group(key="detector").set_value("iforest").run()
    assert not at.exception
    race_ids = at.selectbox(key="race").options
    at.selectbox(key="race").select(race_ids[-1]).run()
    assert not at.exception


def test_dashboard_without_data_shows_an_instruction_instead_of_crashing(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("F1_DB", str(tmp_path / "nao_existe.duckdb"))
    monkeypatch.setenv("F1_ARTIFACTS", str(tmp_path / "nada"))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception and any("pipeline" in e.value for e in at.error)

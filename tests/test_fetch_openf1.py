"""Conector OpenF1: conversão para o contrato Bronze, sem rede.

O arquivo de teste é um recorte real de Shanghai 2024 (pilotos 1, 2 e 27): um VSC que virou safety car sem a
mensagem de "VSC ENDING", dois períodos de safety car e voltas anuladas. Nessa corrida, a Bronze da OpenF1
bate com a do FastF1 em 99,9% das voltas quanto ao status da pista.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from f1lab.bronze import validate_bronze
from f1lab.fetch_openf1 import openf1_to_bronze
from f1lab.schema import BRONZE_LAP_COLUMNS

FIXTURE = Path(__file__).parent / "fixtures" / "openf1_shanghai_2024.json"


@pytest.fixture(scope="module")
def shanghai():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return openf1_to_bronze(raw, 2024, 5)


def test_output_follows_the_bronze_contract(shanghai):
    laps, race = shanghai
    assert list(laps.columns) == BRONZE_LAP_COLUMNS
    validate_bronze(laps, pd.DataFrame([race]))
    assert race == {"race_id": "2024-05-R", "year": 2024, "round": 5, "circuit": "Shanghai", "n_laps": 56, "source": "openf1"}
    assert set(laps["Driver"]) == {"VER", "SAR", "HUL"}


def test_vsc_that_turns_into_safety_car_does_not_last_until_the_flag(shanghai):
    laps, _ = shanghai
    ver = laps[laps["Driver"] == "VER"].set_index("LapNumber")["TrackStatus"]
    assert "6" in ver[22]  # VSC
    assert all("4" in ver[lap] for lap in range(24, 31))  # safety car
    assert all(ver[lap] == "1" for lap in range(33, 57))  # pista livre até o fim


def test_tyres_and_pit_laps(shanghai):
    laps, _ = shanghai
    ver = laps[laps["Driver"] == "VER"].set_index("LapNumber")
    assert ver.loc[2, "TyreLife"] == ver.loc[1, "TyreLife"] + 1
    pit_in = ver.index[ver["PitInTime_s"].notna()].tolist()
    assert pit_in, "a volta de entrada nos boxes precisa estar marcada"
    out = pit_in[0] + 1
    assert pd.notna(ver.loc[out, "PitOutTime_s"])
    assert ver.loc[out, "Stint"] == ver.loc[pit_in[0], "Stint"] + 1  # a volta de entrada fica no stint antigo
    assert ver.loc[out, "FreshTyre"] and ver.loc[out, "TyreLife"] == 1


def _minimal(stints, pit, race_control=()):
    t = pd.Timestamp("2026-01-01T12:00:00")
    laps = [
        {
            "driver_number": 7,
            "lap_number": n,
            "date_start": (t + pd.Timedelta(seconds=90 * (n - 1))).isoformat(),
            "lap_duration": 90.0,
            "duration_sector_1": 30.0,
            "duration_sector_2": 30.0,
            "duration_sector_3": 30.0,
            "i1_speed": 280,
            "i2_speed": 290,
            "st_speed": 310,
            "is_pit_out_lap": n == 3,
        }
        for n in range(1, 5)
    ]
    return {
        "session": {"session_key": 1, "circuit_short_name": "Teste"},
        "drivers": [{"driver_number": 7, "name_acronym": "TST", "team_name": "Equipe"}],
        "laps": laps,
        "stints": stints,
        "pit": pit,
        "position": [],
        "race_control": list(race_control),
    }


def test_stint_that_starts_on_the_pit_lap_moves_to_the_next_lap():
    """Melbourne 2024: a OpenF1 começa alguns stints na própria volta de entrada, uma antes do FastF1."""
    raw = _minimal(
        stints=[
            {"driver_number": 7, "stint_number": 1, "lap_start": 1, "lap_end": 1, "compound": "MEDIUM", "tyre_age_at_start": 0},
            {"driver_number": 7, "stint_number": 2, "lap_start": 2, "lap_end": 4, "compound": "HARD", "tyre_age_at_start": 0},
        ],
        pit=[{"driver_number": 7, "lap_number": 2, "date": "2026-01-01T12:02:55"}],
    )
    laps, _ = openf1_to_bronze(raw, 2026, 1)
    by_lap = laps.set_index("LapNumber")
    assert by_lap.loc[2, ["Stint", "Compound", "TyreLife"]].tolist() == [1, "MEDIUM", 2]
    assert by_lap.loc[3, ["Stint", "Compound", "TyreLife"]].tolist() == [2, "HARD", 1]


def test_deleted_lap_and_reinstated_lap():
    raw = _minimal(
        stints=[
            {"driver_number": 7, "stint_number": 1, "lap_start": 1, "lap_end": 4, "compound": "SOFT", "tyre_age_at_start": 0}
        ],
        pit=[],
        race_control=[
            {
                "date": "2026-01-01T12:03:10",
                "message": "CAR 7 (TST) TIME 1:30.000 DELETED - TRACK LIMITS AT TURN 1 LAP 2 12:03:10",
            },
            {
                "date": "2026-01-01T12:04:40",
                "message": "CAR 7 (TST) TIME 1:30.000 DELETED - TRACK LIMITS AT TURN 4 LAP 3 12:04:40",
            },
            {"date": "2026-01-01T12:06:00", "message": "CAR 7 (TST) LAP 3 REINSTATED"},
        ],
    )
    laps, _ = openf1_to_bronze(raw, 2026, 1)
    assert laps.set_index("LapNumber")["Deleted"].to_dict() == {1: False, 2: True, 3: False, 4: False}


def test_session_without_laps_fails_with_a_clear_message():
    raw = _minimal(stints=[], pit=[])
    raw["laps"] = []
    with pytest.raises(ValueError, match="ainda não publicou"):
        openf1_to_bronze(raw, 2026, 21)

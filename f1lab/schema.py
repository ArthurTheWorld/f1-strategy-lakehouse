"""Contrato de dados da camada Bronze.

Os nomes das colunas seguem o `fastf1.core.Laps` (FastF1 3.9.2, conferido no código-fonte instalado).
Os intervalos de tempo (timedelta no FastF1) viram segundos (float) com o sufixo `_s`.

TrackStatus (string com os códigos vistos durante a volta, ex.: "1", "12", "124"):
    1 pista livre | 2 amarela | 4 safety car | 5 bandeira vermelha | 6 VSC | 7 VSC terminando
Uma volta só é considerada "limpa" quando o status é exatamente "1".
"""

COMPOUNDS = ("SOFT", "MEDIUM", "HARD")
CLEAN_TRACK_STATUS = "1"

BRONZE_LAP_COLUMNS = [
    "race_id",
    "Driver",
    "DriverNumber",
    "Team",
    "LapNumber",
    "Stint",
    "Compound",
    "TyreLife",
    "FreshTyre",
    "LapTime_s",
    "Sector1Time_s",
    "Sector2Time_s",
    "Sector3Time_s",
    "PitInTime_s",
    "PitOutTime_s",
    "SpeedI1",
    "SpeedI2",
    "SpeedFL",
    "SpeedST",
    "TrackStatus",
    "Position",
    "IsAccurate",
    "Deleted",
    "IsPersonalBest",
]

BRONZE_RACE_COLUMNS = ["race_id", "year", "round", "circuit", "n_laps", "source"]

SPEED_COLUMNS = ["SpeedI1", "SpeedI2", "SpeedFL", "SpeedST"]


def make_race_id(year: int, round_: int) -> str:
    return f"{year}-{round_:02d}-R"

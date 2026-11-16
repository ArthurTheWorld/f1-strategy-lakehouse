"""Conector de dados reais via OpenF1 (https://openf1.org), sem login.

Por que existe: desde o fim de 2026 o FastF1 exige login numa conta da Fórmula 1 até para os tempos de volta.
A OpenF1 publica os mesmos dados de cronometragem de graça. Este conector gera exatamente o contrato Bronze
do FastF1 (`schema.BRONZE_LAP_COLUMNS`), então Silver, Gold, modelo e dashboard não mudam.

Fluxo: as respostas da API são gravadas cruas em `data/raw/openf1/<session_key>/` (aterrissagem) e só depois
convertidas. Reprocessar não precisa de rede.

Como cada coluna é montada:
- LapTime, setores e velocidades: endpoint `laps`. A OpenF1 não tem `SpeedFL`, que fica nulo.
- Stint, Compound, TyreLife, FreshTyre: endpoint `stints` (idade do pneu = idade na saída + voltas no stint).
- PitInTime / PitOutTime: `pit` marca a volta de entrada; `laps.is_pit_out_lap` marca a de saída.
- Position: a última posição publicada antes do fim da volta.
- TrackStatus: reconstruído das mensagens da direção de prova (`race_control`): 2 amarela, 4 safety car,
  5 bandeira vermelha, 6 VSC, 7 VSC terminando; "1" quando nada disso ocorreu durante a volta.
- Deleted: mensagens "... DELETED ..." da direção de prova (desfeitas por "REINSTATED").
- IsAccurate: a OpenF1 não tem essa marca; vale True quando a volta tem tempo.

Uso:
    python -m f1lab.fetch_openf1 --year 2026 --rounds 20 21 --out data/bronze
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from .bronze import write_bronze
from .schema import BRONZE_LAP_COLUMNS, BRONZE_RACE_COLUMNS, make_race_id

API = "https://api.openf1.org/v1"
ENDPOINTS = ("drivers", "laps", "stints", "pit", "position", "race_control")
VSC_ENDING_S = 15.0  # o status 7 (VSC terminando) dura poucos segundos antes da bandeira verde
_CAR = re.compile(r"CAR (\d+)")
_LAP = re.compile(r"LAP (\d+)")


# ---------------------------------------------------------------- rede (aterrissagem crua)


def _get(path: str, **params) -> list | dict:  # pragma: no cover - precisa de rede
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    last: Exception | None = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "f1-strategy-lakehouse"})
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.load(r)
            if isinstance(data, dict) and "detail" in data:  # "No results found."
                return []
            return data
        except Exception as e:  # limite de requisições da API: espera e tenta de novo
            last = e
            time.sleep(2 + attempt * 3)
    raise RuntimeError(f"OpenF1 não respondeu: {url}") from last


def race_sessions(year: int) -> list[dict]:  # pragma: no cover - precisa de rede
    """Corridas do ano em ordem de data, sem as canceladas: a posição na lista é a rodada (igual ao FastF1)."""
    sessions = [s for s in _get("sessions", year=year, session_name="Race") if not s.get("is_cancelled")]
    return sorted(sessions, key=lambda s: s["date_start"])


def land_session(session: dict, raw_dir: str | Path) -> Path:  # pragma: no cover - precisa de rede
    """Grava cada endpoint cru em disco. Se já existe, não baixa de novo."""
    out = Path(raw_dir) / str(session["session_key"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "session.json").write_text(json.dumps(session), encoding="utf-8")
    for name in ENDPOINTS:
        path = out / f"{name}.json"
        if not path.exists():
            path.write_text(json.dumps(_get(name, session_key=session["session_key"])), encoding="utf-8")
            time.sleep(0.5)
    return out


def read_landed(session_dir: str | Path) -> dict:
    d = Path(session_dir)
    return {name: json.loads((d / f"{name}.json").read_text(encoding="utf-8")) for name in ("session", *ENDPOINTS)}


# ---------------------------------------------------------------- conversão (sem rede, testada)


def _ts(values) -> pd.Series:
    return pd.to_datetime(pd.Series(values), utc=True, format="ISO8601").dt.tz_localize(None)


def _status_intervals(race_control: list[dict], laps: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.Timestamp, str]]:
    """Intervalos (início, fim, código) de amarela, safety car, VSC e bandeira vermelha."""
    rc = pd.DataFrame(race_control)
    if rc.empty:
        return []
    for col in ("flag", "scope", "sector", "lap_number", "message"):
        if col not in rc:  # sem nenhuma bandeira na corrida, a API nem manda a coluna
            rc[col] = None
    rc = rc.assign(t=_ts(rc["date"])).sort_values("t").reset_index(drop=True)
    msg = rc["message"].fillna("").str.upper()
    end_of_race = laps["end"].max()
    leader_lap_end = laps.groupby("lap_number")["end"].min()  # fim de cada volta para o primeiro carro
    out: list[tuple[pd.Timestamp, pd.Timestamp, str]] = []

    def next_after(t, mask):
        later = rc[(rc["t"] > t) & mask]
        return later["t"].iloc[0] if len(later) else end_of_race

    green_track = (rc["flag"] == "GREEN") & (rc["scope"] == "Track")
    clear_track = (rc["flag"] == "CLEAR") & (rc["scope"] == "Track")
    sc_deployed = msg.str.contains("SAFETY CAR DEPLOYED") & ~msg.str.contains("VIRTUAL")
    vsc_ending = msg.str.contains("VIRTUAL SAFETY CAR ENDING")
    for _, row in rc[msg.str.contains("VIRTUAL SAFETY CAR DEPLOYED")].iterrows():
        ending = next_after(row["t"], vsc_ending)
        # um VSC pode virar safety car sem a mensagem de "VSC ENDING" (Shanghai 2024)
        ending = min(ending, next_after(row["t"], sc_deployed | green_track | clear_track))
        out.append((row["t"], ending, "6"))
        if len(rc[(rc["t"] == ending) & vsc_ending]):
            out.append((ending, ending + pd.Timedelta(seconds=VSC_ENDING_S), "7"))
    sc_in = msg.str.contains("SAFETY CAR IN THIS LAP") & ~msg.str.contains("VIRTUAL")
    for _, row in rc[sc_deployed].iterrows():
        later_in = rc[(rc["t"] > row["t"]) & sc_in]
        if len(later_in) and pd.notna(later_in["lap_number"].iloc[0]):
            lap = int(later_in["lap_number"].iloc[0])  # o safety car entra no fim desta volta
            end = leader_lap_end.get(lap, next_after(row["t"], green_track | clear_track))
        else:
            end = next_after(row["t"], green_track | clear_track)
        out.append((row["t"], end, "4"))
    for _, row in rc[rc["flag"] == "RED"].iterrows():
        resume = msg.str.contains("RESUME|SESSION STARTED") | green_track | clear_track
        out.append((row["t"], next_after(row["t"], resume), "5"))
    if rc["sector"].notna().any():
        yellow = rc[rc["flag"].isin(["YELLOW", "DOUBLE YELLOW"]) & rc["sector"].notna()]
        for _, row in yellow.iterrows():
            same_sector_clear = (rc["flag"] == "CLEAR") & ((rc["sector"] == row["sector"]) | (rc["scope"] == "Track"))
            out.append((row["t"], next_after(row["t"], same_sector_clear), "2"))
    return out


def openf1_to_bronze(raw: dict, year: int, round_: int):
    """Converte as respostas cruas da OpenF1 de uma corrida no contrato Bronze. Devolve (laps, race_row)."""
    session = raw["session"]
    drivers = {d["driver_number"]: d for d in raw["drivers"]}
    laps = pd.DataFrame(raw["laps"])
    if laps.empty:
        raise ValueError(f"a OpenF1 ainda não publicou voltas da sessão {session.get('session_key')}")
    laps = laps.sort_values(["driver_number", "lap_number"]).reset_index(drop=True)
    laps["start"] = _ts(laps["date_start"])
    # fim da volta: início + duração; sem duração, o início da volta seguinte do mesmo piloto
    nxt = laps.groupby("driver_number")["start"].shift(-1)
    laps["end"] = (laps["start"] + pd.to_timedelta(laps["lap_duration"], unit="s")).fillna(nxt)
    t0 = laps["start"].min()

    # pneus. A volta de entrada nos boxes pertence ao stint antigo: em algumas corridas (Melbourne 2024) a
    # OpenF1 começa o stint novo já nessa volta, uma antes do FastF1. Esses stints começam na volta seguinte.
    pit = pd.DataFrame(raw["pit"])
    pit_laps = (
        set() if pit.empty else {(int(n), int(lap)) for n, lap in zip(pit["driver_number"], pit["lap_number"], strict=True)}
    )
    stints = pd.DataFrame(raw["stints"])
    laps["Stint"] = np.nan
    laps["Compound"] = None
    laps["TyreLife"] = np.nan
    laps["FreshTyre"] = False
    stints = stints.dropna(subset=["lap_start", "lap_end"]).sort_values(["driver_number", "stint_number"]).reset_index(drop=True)
    stints["start"] = stints["lap_start"].astype(int)
    stints["end"] = stints["lap_end"].astype(int)
    for i, s in stints.iterrows():
        if s["stint_number"] > 1 and (int(s["driver_number"]), s["start"]) in pit_laps:
            stints.loc[i, "start"] += 1
            prev = (stints["driver_number"] == s["driver_number"]) & (stints["stint_number"] == s["stint_number"] - 1)
            stints.loc[prev, "end"] = stints.loc[prev, "end"].clip(lower=s["start"])  # o stint antigo cobre a volta de entrada
    for _, s in stints.iterrows():
        start = int(s["start"])
        m = (laps["driver_number"] == s["driver_number"]) & laps["lap_number"].between(start, s["end"])
        age0 = 0 if pd.isna(s.get("tyre_age_at_start")) else int(s["tyre_age_at_start"])
        laps.loc[m, "Stint"] = s["stint_number"]
        laps.loc[m, "Compound"] = None if pd.isna(s.get("compound")) else str(s["compound"]).upper()
        laps.loc[m, "TyreLife"] = age0 + laps.loc[m, "lap_number"] - start + 1
        laps.loc[m, "FreshTyre"] = age0 == 0

    # boxes: volta de entrada (pit) e volta de saída (is_pit_out_lap); o valor é o tempo desde o início
    laps["PitInTime_s"] = np.nan
    if not pit.empty:
        pit = pit.assign(t=_ts(pit["date"]))
        for _, p in pit.iterrows():
            m = (laps["driver_number"] == p["driver_number"]) & (laps["lap_number"] == p["lap_number"])
            laps.loc[m, "PitInTime_s"] = (p["t"] - t0).total_seconds()
    out_lap = laps["is_pit_out_lap"].fillna(False).astype(bool) & (laps["lap_number"] > 1)
    laps["PitOutTime_s"] = np.where(out_lap, (laps["start"] - t0).dt.total_seconds(), np.nan)

    # posição ao fim da volta
    pos = pd.DataFrame(raw["position"])
    laps["Position"] = np.nan
    if not pos.empty:
        pos = pos.assign(t=_ts(pos["date"])).sort_values("t")
        for num, g in laps.groupby("driver_number"):
            p = pos[pos["driver_number"] == num]
            if p.empty:
                continue
            idx = np.searchsorted(p["t"].to_numpy(), g["end"].to_numpy(), side="right") - 1
            laps.loc[g.index, "Position"] = np.where(idx >= 0, p["position"].to_numpy()[np.clip(idx, 0, None)], np.nan)

    # status da pista
    intervals = _status_intervals(raw["race_control"], laps)
    codes = []
    for s, e in zip(laps["start"], laps["end"], strict=True):
        if pd.isna(s) or pd.isna(e):
            codes.append(None)
            continue
        seen = sorted({c for a, b, c in intervals if a < e and b > s})
        codes.append("".join(seen) if seen else "1")
    laps["TrackStatus"] = codes

    # voltas anuladas pela direção de prova
    deleted: set[tuple[int, int]] = set()
    for m in sorted(raw["race_control"], key=lambda m: m.get("date") or ""):
        text = (m.get("message") or "").upper()
        car, lap_hits = _CAR.search(text), _LAP.findall(text)
        if not car or not lap_hits or ("DELETED" not in text and "REINSTATED" not in text):
            continue
        key = (int(car.group(1)), int(lap_hits[-1]))  # o número da volta vem por último ("... AT TURN 1 LAP 15")
        if "REINSTATED" in text:
            deleted.discard(key)
        else:
            deleted.add(key)
    laps["Deleted"] = [(int(n), int(lap)) in deleted for n, lap in zip(laps["driver_number"], laps["lap_number"], strict=True)]

    race_id = make_race_id(year, round_)
    df = pd.DataFrame(
        {
            "race_id": race_id,
            "Driver": [drivers.get(n, {}).get("name_acronym") or str(n) for n in laps["driver_number"]],
            "DriverNumber": laps["driver_number"].astype(str),
            "Team": [drivers.get(n, {}).get("team_name") for n in laps["driver_number"]],
            "LapNumber": laps["lap_number"].astype(float),
            "Stint": laps["Stint"].astype(float),
            "Compound": laps["Compound"],
            "TyreLife": laps["TyreLife"].astype(float),
            "FreshTyre": laps["FreshTyre"].astype(bool),
            "LapTime_s": pd.to_numeric(laps["lap_duration"], errors="coerce"),
            "Sector1Time_s": pd.to_numeric(laps["duration_sector_1"], errors="coerce"),
            "Sector2Time_s": pd.to_numeric(laps["duration_sector_2"], errors="coerce"),
            "Sector3Time_s": pd.to_numeric(laps["duration_sector_3"], errors="coerce"),
            "PitInTime_s": laps["PitInTime_s"],
            "PitOutTime_s": laps["PitOutTime_s"],
            "SpeedI1": pd.to_numeric(laps["i1_speed"], errors="coerce").astype(float),
            "SpeedI2": pd.to_numeric(laps["i2_speed"], errors="coerce").astype(float),
            "SpeedFL": np.nan,
            "SpeedST": pd.to_numeric(laps["st_speed"], errors="coerce").astype(float),
            "TrackStatus": laps["TrackStatus"],
            "Position": laps["Position"].astype(float),
            "IsAccurate": laps["lap_duration"].notna(),
            "Deleted": laps["Deleted"].astype(bool),
        }
    )
    valid = df["LapTime_s"].where(~df["Deleted"])
    df["IsPersonalBest"] = valid.notna() & (valid == valid.groupby(df["Driver"]).cummin())
    race = {
        "race_id": race_id,
        "year": year,
        "round": round_,
        "circuit": session.get("circuit_short_name") or session.get("location") or f"round {round_}",
        "n_laps": int(df["LapNumber"].max()),
        "source": "openf1",
    }
    return df[BRONZE_LAP_COLUMNS], {k: race[k] for k in BRONZE_RACE_COLUMNS}


def fetch_race(year: int, round_: int, raw_dir: str | Path = "data/raw/openf1"):  # pragma: no cover - precisa de rede
    sessions = race_sessions(year)
    if not 1 <= round_ <= len(sessions):
        raise ValueError(f"{year} tem {len(sessions)} corridas; rodada {round_} não existe")
    landed = land_session(sessions[round_ - 1], raw_dir)
    return openf1_to_bronze(read_landed(landed), year, round_)


def main(argv=None):  # pragma: no cover - precisa de rede
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--rounds", type=int, nargs="+", required=True)
    p.add_argument("--out", default="data/bronze")
    p.add_argument("--raw", default="data/raw/openf1")
    args = p.parse_args(argv)
    laps, races = [], []
    for rnd in args.rounds:
        lp, race = fetch_race(args.year, rnd, args.raw)
        laps.append(lp)
        races.append(race)
        print(f"rodada {rnd} ({race['circuit']}): {len(lp)} voltas")
    write_bronze(pd.concat(laps, ignore_index=True), pd.DataFrame(races), args.out)
    print(f"bronze gravado em {args.out}")


if __name__ == "__main__":  # pragma: no cover
    main()

"""Dashboard Streamlit: lê o Gold e as tabelas `analytics.*` do DuckDB. Não recalcula nada do pipeline.

    streamlit run dashboard/app.py
Variáveis: F1_DB (padrão data/f1.duckdb) e F1_ARTIFACTS (padrão artifacts/).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard.car import car_html  # noqa: E402
from dashboard.car3d import team_color  # noqa: E402
from dashboard.replay import height as replay_height  # noqa: E402
from dashboard.replay import payload as replay_payload
from dashboard.replay import replay_html
from f1lab import strategy as strat  # noqa: E402
from f1lab.model import LapModel  # noqa: E402
from f1lab.schema import COMPOUNDS  # noqa: E402

DB = Path(os.environ.get("F1_DB", ROOT / "data" / "f1.duckdb"))
ART = Path(os.environ.get("F1_ARTIFACTS", ROOT / "artifacts"))
ASSETS = Path(__file__).resolve().parent / "assets"

# Tema Console. Âmbar marca desvio e seleção, azul marca leitura de instrumento; vermelho, amarelo e branco são pneus.
AMBER, COOL = "#f7b83d", "#6ebcfc"
AMBER_SOFT = "#38280a"
INK, MUTED, RULE_2 = "#eceff2", "#9da2a8", "#484e54"
PANEL = "#15191c"
GRID = "rgba(236,239,242,0.06)"
AXIS = "rgba(236,239,242,0.18)"
BODY_FONT = "Host Grotesk, system-ui, sans-serif"
MEASURED_FONT = "Atkinson Hyperlegible Mono, Consolas, monospace"
COLORS = {"SOFT": "#ff3b30", "MEDIUM": "#f5d000", "HARD": "#e8e8e8"}
PT = {"SOFT": "Macio", "MEDIUM": "Médio", "HARD": "Duro"}
HOVER_TEAM = "%{y}<br>%{x:+.2f} s vs. mediana<br>%{customdata[0]} voltas, %{customdata[1]} pilotos<extra></extra>"

st.set_page_config(page_title="F1 Strategy Lakehouse", page_icon=":material/sports_score:", layout="wide")

# O tema nativo cobre cores e fontes; o CSS cuida do que ele não alcança: painéis, leituras em mono e foco.
st.html(
    f"<style>{(ASSETS / 'tokens.css').read_text(encoding='utf-8')}{(ASSETS / 'console.css').read_text(encoding='utf-8')}</style>"
)


def style(fig: go.Figure, height: int = 380, legend: bool = True) -> go.Figure:
    """Tema único dos gráficos. O título fica no painel, fora do gráfico."""
    fig.update_layout(
        height=height,
        margin=dict(l=4, r=12, t=34 if legend else 8, b=4),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=BODY_FONT, color=MUTED, size=12),
        hoverlabel=dict(bgcolor=PANEL, bordercolor=RULE_2, font=dict(family=MEASURED_FONT, color=INK, size=12)),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0, bgcolor="rgba(0,0,0,0)", title=None),
    )
    tick = dict(family=MEASURED_FONT, size=12)
    fig.update_xaxes(
        showgrid=False,
        zeroline=False,
        linecolor=AXIS,
        ticks="outside",
        tickcolor=AXIS,
        title_font=dict(size=12),
        tickfont=tick,
        automargin=True,
    )
    fig.update_yaxes(gridcolor=GRID, zeroline=False, showline=False, title_font=dict(size=12), tickfont=tick, automargin=True)
    return fig


def chart(fig: go.Figure, alt: str, key: str) -> None:
    st.plotly_chart(fig, theme=None, config={"displayModeBar": False}, alt=alt, key=key)


def panel(name: str):
    """Painel com borda fina, um degrau acima do fundo."""
    return st.container(border=True, height="stretch", key=f"panel_{name}")


def kpis(key: str, items: list[tuple[str, str, bool]], min_width: int = 150) -> None:
    """Indicadores de largura igual. O terceiro campo diz se o valor foi medido (fonte mono) ou é texto."""
    with st.grid(len(items), min_column_width=min_width, gap="small"):
        for i, (label, value, measured) in enumerate(items):
            with st.container(key=f"{'kpi' if measured else 'text'}_{key}_{i}", height="stretch"):
                st.metric(label, value, border=True, height="stretch")


def lap_clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:06.3f}"


def race_clock(seconds: float) -> str:
    h, rest = divmod(float(seconds), 3600)
    return f"{int(h)}:{int(rest // 60):02d}:{rest % 60:04.1f}"


def plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def strategy_label(text: str) -> str:
    for en, pt in PT.items():
        text = text.replace(en, pt)
    return text


@st.cache_data(show_spinner=False)
def query(sql: str, db: str, mtime: float) -> pd.DataFrame:
    con = duckdb.connect(db, read_only=True)
    try:
        return con.execute(sql).df()
    finally:
        con.close()


def q(sql: str) -> pd.DataFrame:
    return query(sql, str(DB), DB.stat().st_mtime)


@st.cache_resource(show_spinner=False)
def load_model(path: str, mtime: float) -> LapModel:
    return LapModel.load(path)


@st.cache_data(show_spinner="Simulando estratégias...", max_entries=64)
def simulate(
    _model: LapModel, mtime: float, n_laps: int, base: float, loss: float, compounds: tuple[str, ...], min_stint: int
) -> pd.DataFrame:
    return strat.enumerate_strategies(_model, n_laps, base, loss, compounds=compounds, min_stint=min_stint, top=10)


def neutralized_laps(laps: pd.DataFrame) -> list[tuple[int, int]]:
    """Trechos de voltas em que a maioria do pelotão correu sob safety car, VSC ou bandeira vermelha."""
    marked = laps.assign(hit=laps["track_status"].astype("string").str.contains("[4567]", regex=True).fillna(False).astype(bool))
    share = marked.groupby("lap_number")["hit"].mean()
    runs: list[tuple[int, int]] = []
    for lap in share[share >= 0.5].index.astype(int):
        if runs and lap == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], lap)
        else:
            runs.append((lap, lap))
    return runs


def render_positions(race_id: str) -> None:
    laps = q(
        f"""select driver, team, lap_number, position, track_status
            from silver.stg_laps where race_id = '{race_id}' order by driver, lap_number"""
    )
    placed = laps.dropna(subset=["position"]).copy()
    if placed.empty:
        return
    placed["position"] = placed["position"].astype(int)
    leaders = placed.loc[placed["position"] == 1, "driver"].value_counts()
    total = int(laps["lap_number"].max())
    colors = {t: team_color(t, i) for i, t in enumerate(sorted(placed["team"].dropna().unique()))}
    with panel("positions"):
        st.subheader(f"{leaders.index[0]} liderou {leaders.iloc[0]} de {total} voltas")
        fig = go.Figure()
        for a, b in neutralized_laps(laps):
            fig.add_vrect(x0=a - 0.5, x1=b + 0.5, fillcolor=AMBER_SOFT, opacity=1, line_width=0, layer="below")
        seen: set[str] = set()
        for driver, d in placed.groupby("driver", sort=True):
            team = str(d["team"].iloc[0])
            second = team in seen  # o segundo carro da equipe fica pontilhado: as duas linhas têm a mesma cor
            seen.add(team)
            fig.add_trace(
                go.Scatter(
                    x=d["lap_number"],
                    y=d["position"],
                    mode="lines",
                    name=str(driver),
                    line=dict(color=colors.get(team, MUTED), width=2, dash="dot" if second else "solid"),
                    hovertemplate=f"{driver}<br>Volta %{{x}}: P%{{y}}<extra></extra>",
                )
            )
            fig.add_annotation(
                x=d["lap_number"].iloc[-1],
                y=d["position"].iloc[-1],
                text=str(driver),
                showarrow=False,
                xanchor="left",
                xshift=6,
                font=dict(family=BODY_FONT, size=11, color=INK),
            )
        n = int(placed["position"].max())
        fig.update_yaxes(range=[n + 0.5, 0.5], dtick=1, title="Posição", showgrid=False)
        fig.update_xaxes(title="Volta", range=[0.5, total + 0.5])
        style(fig, height=max(420, 22 * n + 70), legend=False)
        fig.update_layout(margin_r=44)
        chart(
            fig,
            f"Posição de cada piloto volta a volta; {leaders.index[0]} liderou {leaders.iloc[0]} de {total} voltas",
            "race_positions",
        )
        st.caption(
            "Faixa âmbar: voltas sob safety car, safety car virtual ou bandeira vermelha. "
            "Linha pontilhada: segundo carro da equipe."
        )


def render_race(race_id: str) -> None:
    render_positions(race_id)
    laps = q(f"select * from gold.fct_laps_model where race_id = '{race_id}'")
    stints = q(f"select * from gold.fct_stints where race_id = '{race_id}' order by driver, stint")
    left, right = st.columns([7, 5])
    with left, panel("stints"):
        stops = stints.groupby("driver").size() - 1
        common = int(stops.mode().iloc[0])
        st.subheader(f"{(stops == common).sum()} de {len(stops)} pilotos fizeram {plural(common, 'parada', 'paradas')}")
        fig = go.Figure()
        for c in COMPOUNDS:
            d = stints[stints["compound"] == c]
            fig.add_trace(
                go.Bar(
                    y=d["driver"],
                    x=d["end_lap"] - d["start_lap"] + 1,
                    base=d["start_lap"] - 1,
                    orientation="h",
                    name=PT[c],
                    marker=dict(color=COLORS[c], line=dict(color=PANEL, width=2)),
                    customdata=d[["start_lap", "end_lap"]],
                    hovertemplate="%{y}: voltas %{customdata[0]} a %{customdata[1]}<extra>" + PT[c] + "</extra>",
                )
            )
        fig.update_layout(barmode="overlay", bargap=0.32, yaxis=dict(autorange="reversed"))
        fig.update_xaxes(title="Volta")
        chart(style(fig, height=540), "Stints de cada piloto ao longo da corrida, por composto", "race_stints")
    with right, panel("laps"):
        counts = laps["compound"].value_counts()
        st.subheader(f"Pneu {PT[counts.index[0]].lower()} em {counts.iloc[0] / len(laps):.0%} das voltas limpas")
        fig = go.Figure()
        for c in COMPOUNDS:
            d = laps[laps["compound"] == c]
            fig.add_trace(
                go.Scattergl(
                    x=d["lap_number"],
                    y=d["lap_time_s"],
                    mode="markers",
                    name=PT[c],
                    marker=dict(color=COLORS[c], size=5, opacity=0.7, line=dict(width=0)),
                    customdata=d["driver"],
                    hovertemplate="%{customdata}<br>Volta %{x}<br>%{y:.2f} s<extra>" + PT[c] + "</extra>",
                )
            )
        lo, hi = laps["lap_time_s"].quantile([0.005, 0.995])  # corta extremos para não achatar o gráfico
        fig.update_yaxes(range=[lo - 0.5, hi + 0.5], title="Tempo de volta (s)")
        fig.update_xaxes(title="Volta")
        chart(style(fig, height=540), "Tempo de cada volta limpa, colorido por composto", "race_laps")


def render_teams(race_id: str) -> None:
    """Ritmo por equipe na corrida escolhida e o carro genérico pintado com a cor da equipe."""
    laps = q(f"select driver, lap_delta_s from gold.fct_laps_model where race_id = '{race_id}'")
    teams = q(f"select distinct driver, team from silver.stg_laps where race_id = '{race_id}' and team is not null")
    stints = q(f"select driver, count(*) as n_stints from gold.fct_stints where race_id = '{race_id}' group by driver")
    m = laps.merge(teams, on="driver")
    if m.empty:
        st.info("Sem voltas limpas com equipe nesta corrida.")
        return
    pace = m.groupby("team").agg(delta=("lap_delta_s", "median"), laps=("lap_delta_s", "size"), drivers=("driver", "nunique"))
    pace = pace.sort_values("delta")
    colors = {t: team_color(t, i) for i, t in enumerate(sorted(pace.index))}
    left, right = st.columns([2, 3])
    with left, panel("team"):
        pick = st.selectbox("Equipe", list(pace.index), key="team_pick")
        st.iframe(
            car_html(colors[pick]),
            height=240,
            alt=f"Desenho técnico de um carro genérico em vista superior, na cor da equipe {pick}",
        )
        pits = stints.merge(teams, on="driver").query("team == @pick")
        kpis(
            "team",
            [
                ("Ritmo vs. mediana", f"{pace.loc[pick, 'delta']:+.2f} s", True),
                ("Posição no ritmo", f"{list(pace.index).index(pick) + 1} de {len(pace)}", True),
                ("Paradas por carro", f"{(pits['n_stints'] - 1).mean():.1f}" if len(pits) else "-", True),
            ],
            min_width=160,
        )
        st.caption(
            "Desenho genérico nas medidas do regulamento de 2022 a 2025, pintado só com a cor da equipe. "
            "Sem logos nem modelos oficiais."
        )
    with right, panel("pace"):
        gap = pace["delta"].iloc[-1] - pace["delta"].iloc[0]
        st.subheader(f"{pace.index[0]} teve o melhor ritmo, {gap:.2f} s à frente da última")
        fig = go.Figure(
            go.Bar(
                y=pace.index,
                x=pace["delta"],
                orientation="h",
                marker=dict(color=[colors[t] if t == pick else RULE_2 for t in pace.index]),
                text=[f"{v:+.2f}" for v in pace["delta"]],
                textposition="outside",
                textfont=dict(family=MEASURED_FONT, color=MUTED),
                customdata=pace[["laps", "drivers"]],
                hovertemplate=HOVER_TEAM,
            )
        )
        pad = max(0.2, 0.4 * float(pace["delta"].abs().max()))  # folga para os rótulos de fora das barras
        fig.update_layout(yaxis=dict(autorange="reversed"), bargap=0.3)
        fig.update_xaxes(
            title="Mediana do atraso por volta (s); menor é mais rápido",
            range=[min(0.0, pace["delta"].min()) - pad, max(0.0, pace["delta"].max()) + pad],
        )
        style(fig, height=max(440, 34 * len(pace) + 90), legend=False)
        fig.update_layout(margin_l=135)  # abas ocultas medem o texto errado; a margem fixa evita cortar os nomes
        fig.update_yaxes(automargin=False)
        chart(fig, "Ritmo mediano de cada equipe", "team_pace")


def degradation_title(curves: pd.DataFrame) -> str:
    """Compara os compostos na maior idade que todos têm nos dados."""
    ok = curves[curves["supported"]]
    if ok["compound"].nunique() < len(COMPOUNDS):
        return "Perda por idade do pneu"
    age = int(ok.groupby("compound")["tyre_life"].max().min())
    at_age = ok[ok["tyre_life"] == age].set_index("compound")["effect_s"]
    if len(at_age) < len(COMPOUNDS):
        return "Perda por idade do pneu"
    parts = ", ".join(f"{PT[c].lower()} {at_age[c]:+.2f} s" for c in COMPOUNDS)
    return f"Com {age} voltas de uso: {parts}"


def render_degradation(circuits: dict[str, str]) -> None:
    left, right = st.columns([3, 2])
    with left, panel("curves"):
        curves = q("select * from analytics.tyre_curves order by compound, tyre_life")
        st.subheader(degradation_title(curves))
        fig = go.Figure()
        for c in COMPOUNDS:
            d = curves[curves["compound"] == c]
            ok, out = d[d["supported"]], d[~d["supported"]]
            fig.add_trace(
                go.Scatter(
                    x=ok["tyre_life"],
                    y=ok["effect_s"],
                    mode="lines",
                    name=PT[c],
                    line=dict(color=COLORS[c], width=2.5, shape="spline", smoothing=0.6),
                    hovertemplate="%{x} voltas: %{y:+.2f} s<extra>" + PT[c] + "</extra>",
                )
            )
            if len(out):
                fig.add_trace(
                    go.Scatter(
                        x=out["tyre_life"],
                        y=out["effect_s"],
                        mode="lines",
                        name=f"{PT[c]} (sem dados)",
                        line=dict(color=COLORS[c], dash="dot", width=1.5),
                        opacity=0.55,
                        showlegend=False,
                        hovertemplate="%{x} voltas: sem dados<extra>" + PT[c] + "</extra>",
                    )
                )
        fig.update_xaxes(title="Idade do pneu (voltas)")
        fig.update_yaxes(title="Perda (s) vs. pneu novo")
        chart(style(fig, height=420), "Perda de tempo por idade do pneu, por composto", "deg_curves")
        st.caption("Linha pontilhada: idades sem suporte nos dados. O modelo não extrapola e o simulador as evita.")
    with right, panel("cv"):
        cv = q("select race_id, rmse_baseline, rmse_xgb from analytics.cv_by_race order by race_id")
        wins = int((cv["rmse_xgb"] < cv["rmse_baseline"]).sum())
        st.subheader(f"XGBoost errou menos em {wins} de {len(cv)} corridas")
        names = [circuits.get(r, r) for r in cv["race_id"]]
        fig = go.Figure(
            [
                go.Bar(
                    y=names,
                    x=cv["rmse_baseline"],
                    name="Baseline linear",
                    orientation="h",
                    marker_color=MUTED,
                    hovertemplate="%{y}: %{x:.2f} s<extra>Baseline</extra>",
                ),
                go.Bar(
                    y=names,
                    x=cv["rmse_xgb"],
                    name="XGBoost monotônico",
                    orientation="h",
                    marker_color=COOL,
                    hovertemplate="%{y}: %{x:.2f} s<extra>XGBoost</extra>",
                ),
            ]
        )
        fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.08, yaxis=dict(autorange="reversed"))
        fig.update_xaxes(title="RMSE (s), corrida fora do treino")
        style(fig, height=420)
        fig.update_layout(margin_l=85)
        fig.update_yaxes(automargin=False)
        chart(fig, "Erro do baseline e do XGBoost em cada corrida", "deg_cv")
        st.caption("Cada corrida foi prevista por um modelo treinado sem ela.")


def render_strategy(race: pd.Series) -> None:
    model_file = ART / "model" / "lap_model.json"
    model = load_model(str(ART / "model"), model_file.stat().st_mtime)
    pit = q("select * from analytics.pit_loss").iloc[0]
    with panel("params"):
        st.subheader("Parâmetros")
        c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 2], vertical_alignment="bottom")
        n_laps = c1.number_input("Voltas da corrida", 30, 80, int(race["n_laps"]))
        base = c2.number_input("Ritmo base (s)", 60.0, 130.0, round(float(race["race_median_lap_s"]), 2), step=0.1)
        loss = c3.number_input("Perda por parada (s)", 10.0, 40.0, round(float(pit["median_s"]), 1), step=0.1)
        min_stint = c4.number_input("Stint mínimo", 3, 20, 8)
        comps = c5.pills(
            "Compostos disponíveis",
            list(COMPOUNDS),
            selection_mode="multi",
            default=list(COMPOUNDS),
            format_func=PT.get,
            key="strategy_compounds",
        )
    if len(comps) < 2:
        st.info("Escolha ao menos 2 compostos (regra de pista seca).")
        return
    res = simulate(model, model_file.stat().st_mtime, int(n_laps), float(base), float(loss), tuple(comps), int(min_stint))
    if res.empty:
        st.warning("Nenhuma estratégia válida: o modelo não tem dados de pneu para stints tão longos.")
        return
    res = res.assign(label=res["strategy"].map(strategy_label))
    best = res.iloc[0]
    items = [
        ("Melhor estratégia", " / ".join(PT[c] for c in best["compounds"]), False),
        ("Paradas nas voltas", ", ".join(str(int(v)) for v in best["pit_laps"]), True),
        ("Tempo total", race_clock(best["total_time_s"]), True),
    ]
    if len(res) > 1:
        items.append(("Vantagem sobre a 2ª", f"{res['gap_s'].iloc[1]:.1f} s", True))
    kpis("strategy", items)
    left, right = st.columns([3, 2])
    with left, panel("strategy_bars"):
        st.subheader("As 5 melhores, volta a volta")
        fig = go.Figure()
        for _, r in res.head(5).iterrows():
            bounds = [0, *r["pit_laps"], int(n_laps)]
            for i, c in enumerate(r["compounds"]):
                fig.add_trace(
                    go.Bar(
                        y=[f"#{r['rank']}  +{r['gap_s']:.1f}s"],
                        x=[bounds[i + 1] - bounds[i]],
                        base=bounds[i],
                        orientation="h",
                        marker=dict(color=COLORS[c], line=dict(color=PANEL, width=2)),
                        text=PT[c],
                        textposition="inside",
                        insidetextanchor="middle",
                        textfont=dict(color="#111" if c != "SOFT" else "#fff", size=12),
                        name=PT[c],
                        showlegend=False,
                        hovertemplate=f"{PT[c]}: voltas {bounds[i] + 1} a {bounds[i + 1]}<extra></extra>",
                    )
                )
        fig.update_layout(barmode="overlay", bargap=0.28, yaxis=dict(autorange="reversed"))
        fig.update_xaxes(title="Volta", range=[0, int(n_laps)])
        chart(style(fig, height=300, legend=False), "Stints das cinco melhores estratégias", "strategy_bars")
    with right, panel("strategy_table"):
        st.subheader("Todas as 10 estratégias")
        st.dataframe(
            res[["rank", "label", "stops", "total_time_s", "gap_s"]],
            hide_index=True,
            height=300,
            column_config={
                "rank": st.column_config.NumberColumn("#", width="small"),
                "label": "Estratégia",
                "stops": st.column_config.NumberColumn("Paradas", width="small"),
                "total_time_s": st.column_config.NumberColumn("Tempo total (s)", format="%.2f"),
                "gap_s": st.column_config.NumberColumn("Diferença (s)", format="+%.2f"),
            },
            alt="As 10 melhores estratégias simuladas",
        )
    st.caption("Compara estratégias em pista livre. Não simula tráfego, ultrapassagens, safety car nem clima.")


def render_anomalies(race_id: str) -> None:
    labels = {"robust_z": "Z-score robusto", "iforest": "Isolation Forest"}
    det = st.segmented_control(
        "Detector", list(labels), default="robust_z", required=True, format_func=labels.get, key="detector"
    )
    flags = q(f"select * from analytics.anomaly_flags where race_id = '{race_id}' and detector = '{det}'")
    laps = q(f"select driver, lap_number, speed_st from gold.fct_laps_model where race_id = '{race_id}' and speed_st is not null")
    m = laps.merge(flags[["driver", "lap_number", "is_flagged"]], on=["driver", "lap_number"], how="left")
    m["is_flagged"] = m["is_flagged"].eq(True)
    n = int(m["is_flagged"].sum())
    if n:
        medians = m.groupby("driver")["speed_st"].transform("median")
        hits = m[m["is_flagged"]].assign(drop=lambda d: medians[d.index] - d["speed_st"])
        table = (
            hits.groupby("driver")
            .agg(voltas=("lap_number", "size"), primeira=("lap_number", "min"), queda=("drop", "max"))
            .reset_index()
            .sort_values(["voltas", "queda"], ascending=False, ignore_index=True)
        )
        left, right = st.columns([2, 3])
        with left, panel("anomaly_table"):
            st.subheader(f"{plural(n, 'volta sinalizada', 'voltas sinalizadas')} em {plural(len(table), 'piloto', 'pilotos')}")
            event = st.dataframe(
                table,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key=f"anomaly_table_{race_id}_{det}",
                column_config={
                    "driver": "Piloto",
                    "voltas": st.column_config.NumberColumn("Voltas", width="small"),
                    "primeira": st.column_config.NumberColumn("1ª volta", width="small"),
                    "queda": st.column_config.NumberColumn("Queda máx. (km/h)", format="%.0f"),
                },
                alt="Pilotos com voltas sinalizadas",
            )
            st.caption("Selecione uma linha para ver o piloto no gráfico.")
        rows = event.selection.rows
        pick = table["driver"].iloc[rows[0] if rows else 0]
        d = m[m["driver"] == pick].sort_values("lap_number")
        with right, panel("anomaly_speed"):
            st.subheader(f"{pick}: velocidade de reta volta a volta")
            fig = go.Figure(
                [
                    go.Scatter(
                        x=d["lap_number"],
                        y=d["speed_st"],
                        mode="lines+markers",
                        name="Velocidade na reta",
                        line=dict(color=COOL, width=1.5),
                        marker=dict(color=COOL, size=4),
                        hovertemplate="Volta %{x}: %{y:.0f} km/h<extra></extra>",
                    ),
                    go.Scatter(
                        x=d[d["is_flagged"]]["lap_number"],
                        y=d[d["is_flagged"]]["speed_st"],
                        mode="markers",
                        name="Sinalizada",
                        marker=dict(color=AMBER, size=12, line=dict(color=PANEL, width=2)),
                        hovertemplate="Sinalizada, volta %{x}: %{y:.0f} km/h<extra></extra>",
                    ),
                ]
            )
            fig.update_xaxes(title="Volta")
            fig.update_yaxes(title="km/h")
            chart(style(fig, height=400), f"Velocidade de reta de {pick}, com as voltas sinalizadas", "anomaly_speed")
    else:
        with panel("anomaly_empty"):
            st.subheader("Nenhuma volta sinalizada nesta corrida")
            st.caption("Experimente o outro detector para comparar.")
    metrics_file = ART / "metrics.json"
    if metrics_file.exists():
        with st.expander("Métricas do treino", icon=":material/monitoring:"):
            st.json(json.loads(metrics_file.read_text(encoding="utf-8")))


def main() -> None:
    if not DB.exists() or not (ART / "model" / "lap_model.json").exists():
        st.title("F1 Strategy Lakehouse")
        st.error("Dados ou modelo não encontrados. Rode `python -m f1lab.pipeline all` primeiro.")
        st.stop()

    races = q("select * from gold.dim_races order by race_id")
    indexed = races.set_index("race_id")
    brand, picker = st.columns([3, 1], vertical_alignment="bottom")
    brand.title("F1 Strategy Lakehouse")
    with picker:
        race_id = st.selectbox(
            "Corrida",
            races["race_id"].tolist(),
            format_func=lambda r: f"R{int(indexed.loc[r, 'round']):02d}  {indexed.loc[r, 'circuit']}",
            key="race",
        )
    race = indexed.loc[race_id]
    synthetic = (races["source"] == "synthetic").any()
    if synthetic:
        st.warning("Dados SINTÉTICOS gerados para validar o pipeline. Não representam corridas reais.")

    laps = q(f"select driver, lap_time_s from gold.fct_laps_model where race_id = '{race_id}'")
    best = laps.loc[laps["lap_time_s"].idxmin()]
    stops = q(f"select driver, count(*) - 1 as n from gold.fct_stints where race_id = '{race_id}' group by driver")["n"]
    pit = q("select * from analytics.pit_loss").iloc[0]

    all_laps = q(
        f"""select driver, team, lap_number, lap_time_s, position, pit_in_time_s
            from silver.stg_laps where race_id = '{race_id}'"""
    )
    team_names = sorted(all_laps["team"].dropna().unique())
    colors = {t: team_color(t, i) for i, t in enumerate(team_names)}
    replay = replay_payload(all_laps, float(race["race_median_lap_s"]), colors)

    reading, stage = st.columns([1, 2], vertical_alignment="center")
    with reading:
        st.header(str(race["circuit"]))
        origin = "Dados sintéticos" if synthetic else "Dados reais via FastF1"
        st.caption(f"Rodada {int(race['round'])} de {int(race['year'])}, {int(race['n_laps'])} voltas. {origin}.")
        with st.container(key="reading"):
            st.metric("Ritmo base", lap_clock(float(race["race_median_lap_s"])))
        st.caption("O replay usa os tempos de volta acumulados e a posição oficial. Voltas sem tempo usam a mediana do pelotão.")
    with stage:
        st.iframe(
            replay_html(replay, str(race["circuit"])),
            height=replay_height(replay),
            alt=f"Replay da corrida em {race['circuit']}, com a diferença de cada piloto para o líder",
        )
    kpis(
        "race",
        [
            (f"Melhor volta limpa, {best['driver']}", lap_clock(float(best["lap_time_s"])), True),
            ("Paradas mais comuns", str(int(stops.mode().iloc[0])), True),
            ("Perda no box, temporada", f"{float(pit['median_s']):.1f} s", True),
        ],
    )

    t_race, t_team, t_deg, t_strat, t_anom = st.tabs(["Corrida", "Equipes", "Degradação", "Estratégia", "Anomalias"])
    with t_race:
        render_race(race_id)
    with t_team:
        render_teams(race_id)
    with t_deg:
        render_degradation(indexed["circuit"].to_dict())
    with t_strat:
        render_strategy(race)
    with t_anom:
        render_anomalies(race_id)


main()

"""Dashboard Garmin Connect.

Avvio:  doppio clic su "Avvia Dashboard" (Mac) / "Avvia Dashboard.bat" (Windows)
oppure: .venv/bin/streamlit run dashboard.py
"""
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import analysis as A
import garmin_data as gd
import pages_analysis as PA
import theme
from common import (activities, activities_long, card, chart, client, daily, daily_year, fitness, hms, kpi,
                    pace, pill, year_window)

st.set_page_config(page_title="Garmin Dashboard", page_icon="⌚", layout="wide",
                   initial_sidebar_state="expanded")
theme.apply()


def header(title):
    st.title(title)
    st.caption(f"{start:%d/%m/%Y} → {end:%d/%m/%Y}")


def steps_chart(df, where=st, height=340):
    fig = go.Figure()
    fig.add_bar(x=df.index, y=df["steps"], name="Passi")
    fig.add_scatter(x=df.index, y=df["step_goal"], name="Obiettivo", mode="lines", line=dict(dash="dot"))
    chart(fig, where, height, title="Passi giornalieri")


# ---------- pagine ----------
def page_overview():
    header("Panoramica")
    df = daily(start, end)
    c = st.columns(6)
    kpi(c[0], "Passi (oggi)", df["steps"])
    kpi(c[1], "FC a riposo", df["resting_hr"], invert=True)
    kpi(c[2], "Sonno (h)", df["sleep_h"], "{:.1f}")
    kpi(c[3], "Sleep score", df["sleep_score"])
    kpi(c[4], "HRV notte", df["hrv_night"])
    kpi(c[5], "Stress medio", df["stress_avg"], invert=True)

    # tre "verdetti" dalle pagine di analisi
    year, acts = daily_year(), activities_long()
    c = st.columns(3)
    with c[0]:
        base = A.baselines(year)
        if not base.empty:
            days = A.alert_days(base)
            lvl = days["level"].iloc[-1]
            msgs = A.alert_messages(base, days.index[-1])
            card(f'<div class="g-eyebrow">Salute oggi</div><div class="g-big">{lvl.capitalize()}</div>'
                 f'<div class="g-small">{msgs[0] if msgs else "Parametri notturni nella norma."}</div>',
                 PA.LEVEL_TONE[lvl])
    with c[1]:
        s, e = year_window()
        p = A.pmc(A.daily_load(acts, s, e))
        zone, text = A.form_zone(p["tsb"].iloc[-1])
        card(f'<div class="g-eyebrow">Stato di forma</div><div class="g-big">{zone}</div>'
             f'<div class="g-small">Freschezza {p["tsb"].iloc[-1]:+.0f} · {text}</div>', "neutral")
    with c[2]:
        found = PA._insights(year, acts)
        if found:
            i = found[0]
            card(f'<div class="g-eyebrow">Il tuo schema più forte</div><div class="g-small" style="font-size:.98rem">'
                 f'{i.text}</div>', "good" if i.good else "bad")

    l, r = st.columns([3, 2])
    steps_chart(df, l)
    chart(px.line(df, y="sleep_score", markers=True, title="Sleep score"), r, 340)

    acts = activities(start, end)
    if not acts.empty:
        st.subheader("Ultimi allenamenti")
        last = acts.head(5)[["start", "name", "type", "distance_km", "duration_min", "avg_hr"]]
        st.dataframe(last.rename(columns={"start": "Data", "name": "Nome", "type": "Tipo", "distance_km": "Km",
                                          "duration_min": "Durata (min)", "avg_hr": "FC media"}),
                     width="stretch", hide_index=True)


def page_activity():
    header("Attività quotidiana")
    df = daily(start, end)
    steps_chart(df)
    l, r = st.columns(2)
    chart(px.bar(df, y="active_calories", title="Calorie attive"), l)
    weekly = df["intensity_min"].resample("W-MON", label="left", closed="left").sum()
    fig = px.bar(weekly, title="Minuti di intensità a settimana (obiettivo OMS 150)")
    fig.add_hline(y=150, line_dash="dot")
    chart(fig, r, showlegend=False)


def page_sleep():
    header("Sonno")
    df = daily(start, end)
    stages = df[["deep_h", "light_h", "rem_h", "awake_h"]].rename(
        columns={"deep_h": "Profondo", "light_h": "Leggero", "rem_h": "REM", "awake_h": "Sveglio"})
    chart(px.bar(stages, title="Fasi del sonno (ore)", barmode="stack"), height=380, legend_title=None)
    l, r = st.columns(2)
    chart(px.line(df, y="sleep_score", markers=True, title="Sleep score"), l)
    avg_stages = stages.mean().dropna()
    if not avg_stages.empty:
        chart(px.pie(values=avg_stages.values, names=avg_stages.index, title="Distribuzione media fasi", hole=0.5), r)


def page_heart():
    header("Cuore e recupero")
    df = daily(start, end)
    l, r = st.columns(2)
    chart(px.line(df, y="resting_hr", markers=True, title="Frequenza cardiaca a riposo"), l)
    chart(px.line(df, y=["hrv_night", "hrv_week"], markers=True, title="HRV (ms)"), r, legend_title=None)
    fig = go.Figure()
    fig.add_scatter(x=df.index, y=df["bb_high"], name="Max", mode="lines", line=dict(width=0))
    fig.add_scatter(x=df.index, y=df["bb_low"], name="Min", mode="lines", fill="tonexty", line=dict(width=0),
                    fillcolor="rgba(125,211,252,0.25)")
    chart(fig, l, title="Body Battery (range giornaliero)", yaxis_range=[0, 100])
    chart(px.bar(df, y="stress_avg", title="Stress medio"), r)


def page_fitness():
    header("Forma e gara")
    fit, errors = fitness(start, end)
    if errors:
        with st.expander("⚠️ Alcuni dati non sono disponibili"):
            st.write("\n".join(f"- {e}" for e in errors))

    st.subheader("Previsioni gara")
    now, race = fit["race_now"], fit["race"]
    c = st.columns(4)
    for col, (label, km) in zip(c, gd.RACE_DISTANCES.values()):
        sec = now.get(label)
        delta = None
        if not race.empty and label in race and race[label].dropna().size > 1 and sec:
            diff = sec - race[label].dropna().iloc[0]  # negativo = più veloce
            delta = ("-" if diff < 0 else "+") + hms(abs(diff)) + " nel periodo"
        col.metric(label, hms(sec), delta=delta, delta_color="inverse", help=pace(sec / km) if sec else None)
    if not race.empty:
        paces = pd.DataFrame({l: race[l] / k / 60 for l, k in gd.RACE_DISTANCES.values() if l in race})
        fig = px.line(paces, title="Passo previsto (min/km) — più in alto è meglio")
        fig.update_yaxes(autorange="reversed")
        chart(fig, height=340, legend_title=None)
    elif not any(now.values()):
        st.info("Nessuna previsione gara: servono corse registrate con un dispositivo che la supporta.")

    l, r = st.columns(2)
    vo2 = fit["vo2"]
    if vo2.empty:
        l.info("Nessun dato VO2max nel periodo.")
    else:
        fig = px.line(vo2.rename(columns={"vo2_run": "Corsa", "vo2_bike": "Bici"}), markers=True, title="VO2max")
        chart(fig, l, legend_title=None)

    rd = fit["readiness"]
    if rd.empty:
        r.info("Nessun dato di training readiness nel periodo.")
    else:
        fig = px.bar(rd, y="readiness", color="level", title="Training readiness",
                     color_discrete_map={"PRIME": "#5EEAD4", "HIGH": "#7DD3FC", "MODERATE": "#FCD34D",
                                         "LOW": "#FDBA74", "POOR": "#FCA5A5"})
        chart(fig, r, legend_title=None, yaxis_range=[0, 100])

    st.subheader("Peso")
    wt = fit["weight"]
    if wt.empty:
        st.info("Nessuna pesata nel periodo.")
    else:
        c = st.columns([1, 3])
        first, last = wt["weight_kg"].iloc[0], wt["weight_kg"].iloc[-1]
        c[0].metric("Peso", f"{last:.1f} kg", delta=f"{last - first:+.1f} kg nel periodo", delta_color="off")
        if wt["body_fat"].notna().any():
            c[0].metric("Massa grassa", f"{wt['body_fat'].dropna().iloc[-1]:.1f} %")
        fig = px.line(wt, y="weight_kg", markers=True, title="Peso")
        if len(wt) >= 7:
            fig.add_scatter(x=wt.index, y=wt["weight_kg"].rolling(7, min_periods=3).mean(),
                            name="Media 7 pesate", mode="lines")
        chart(fig, c[1], showlegend=False)


def page_workouts():
    header("Allenamenti")
    acts = activities(start, end)
    if acts.empty:
        st.info("Nessuna attività nel periodo selezionato.")
        return
    types = sorted(acts["type"].unique())
    sel = st.multiselect("Tipo di attività", types, default=types)
    a = acts[acts["type"].isin(sel)]

    c = st.columns(4)
    c[0].metric("Allenamenti", len(a))
    c[1].metric("Distanza totale", f"{a['distance_km'].sum():.1f} km")
    c[2].metric("Tempo totale", f"{a['duration_min'].sum() / 60:.1f} h")
    c[3].metric("Dislivello", f"{a['elev_gain_m'].sum():.0f} m")

    l, r = st.columns(2)
    wk = (a.set_index("start").groupby([pd.Grouper(freq="W-MON", label="left", closed="left"), "type"])
          ["duration_min"].sum().reset_index())
    chart(px.bar(wk, x="start", y="duration_min", color="type", title="Minuti di allenamento a settimana"),
          l, legend_title=None)
    by_type = a.groupby("type")["duration_min"].sum()
    chart(px.pie(values=by_type.values, names=by_type.index, title="Tempo per tipo", hole=0.5), r)

    cols = ["start", "name", "type", "distance_km", "duration_min", "pace_min_km", "avg_hr", "max_hr",
            "calories", "elev_gain_m", "training_load"]
    st.dataframe(
        a[cols].rename(columns={"start": "Data", "name": "Nome", "type": "Tipo", "distance_km": "Km",
                                "duration_min": "Durata (min)", "pace_min_km": "Passo (min/km)",
                                "avg_hr": "FC media", "max_hr": "FC max", "calories": "Kcal",
                                "elev_gain_m": "D+ (m)", "training_load": "Carico"}),
        width="stretch", hide_index=True,
    )


# ---------- login ----------
def login_page(note: str | None = None):
    """Mostrata quando non c'è ancora un account Garmin collegato su questo computer."""
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        st.title("Garmin Dashboard")
        st.caption("Collega il tuo account Garmin Connect. La password serve solo per questo primo accesso e non "
                   "viene salvata: sul computer restano solo i token di accesso, nella tua cartella personale.")
        if note:
            st.warning(note)
        if "mfa_state" not in st.session_state:
            with st.form("login"):
                email = st.text_input("Email Garmin")
                password = st.text_input("Password", type="password")
                ok = st.form_submit_button("Accedi", type="primary", width="stretch")
            if ok:
                if not email or not password:
                    st.error("Inserisci email e password.")
                    return
                with st.spinner("Accesso a Garmin Connect…"):
                    try:
                        status, state = gd.login_with_password(email.strip(), password)
                    except Exception as exc:
                        st.error(_login_error(exc))
                        return
                if status == "needs_mfa":
                    st.session_state["mfa_state"] = state
                    st.rerun()
                _logged_in()
        else:
            st.info("Garmin ti ha mandato un codice di verifica (via email o SMS).")
            with st.form("mfa"):
                code = st.text_input("Codice di verifica")
                ok = st.form_submit_button("Conferma", type="primary", width="stretch")
            if ok:
                try:
                    gd.finish_mfa(st.session_state["mfa_state"], code.strip())
                except Exception as exc:
                    st.error(_login_error(exc))
                    return
                del st.session_state["mfa_state"]
                _logged_in()
            if st.button("Annulla"):
                del st.session_state["mfa_state"]
                st.rerun()


def _login_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if "429" in msg or "too many" in msg:
        return "Garmin ha bloccato temporaneamente i tentativi di accesso. Riprova tra qualche minuto."
    if "401" in msg or "auth" in msg or "credential" in msg or "password" in msg:
        return "Email o password non corrette (oppure codice di verifica sbagliato)."
    return f"Accesso non riuscito: {exc}"


def _logged_in():
    st.cache_resource.clear()
    st.cache_data.clear()
    st.rerun()


if not gd.has_token():
    login_page()
    st.stop()
try:
    client()
except Exception:
    st.cache_resource.clear()
    login_page("La sessione con Garmin è scaduta: accedi di nuovo.")
    st.stop()


# ---------- menu laterale ----------
nav = st.navigation({
    "": [st.Page(page_overview, title="Panoramica", icon=":material/space_dashboard:", default=True)],
    "Analisi": [
        st.Page(PA.page_insights, title="Cosa ti fa stare bene", icon=":material/lightbulb:", url_path="insight"),
        st.Page(PA.page_alerts, title="Allerte salute", icon=":material/monitor_heart:", url_path="allerte"),
        st.Page(PA.page_load, title="Carico e forma", icon=":material/show_chart:", url_path="carico"),
        st.Page(PA.page_efficiency, title="Efficienza aerobica", icon=":material/speed:", url_path="efficienza"),
        st.Page(PA.page_technique, title="Tecnica di corsa", icon=":material/directions_run:", url_path="tecnica"),
        st.Page(PA.page_cross, title="Altri sport", icon=":material/sports_tennis:", url_path="altri-sport"),
        st.Page(PA.page_race, title="Gara obiettivo", icon=":material/flag:", url_path="gara"),
        st.Page(PA.page_calendar, title="Calendario e record", icon=":material/calendar_month:",
                url_path="calendario"),
    ],
    "Salute": [
        st.Page(page_activity, title="Attività quotidiana", icon=":material/directions_walk:", url_path="attivita"),
        st.Page(page_sleep, title="Sonno", icon=":material/bedtime:", url_path="sonno"),
        st.Page(page_heart, title="Cuore e recupero", icon=":material/favorite:", url_path="cuore"),
    ],
    "Sport": [
        st.Page(page_fitness, title="Forma e gara", icon=":material/trending_up:", url_path="forma"),
        st.Page(page_workouts, title="Allenamenti", icon=":material/fitness_center:", url_path="allenamenti"),
    ],
})

with st.sidebar:
    st.divider()
    period = st.selectbox("Periodo", ["7 giorni", "30 giorni", "90 giorni", "180 giorni", "365 giorni"], index=1,
                          help="Vale per le pagine Salute e Sport. Le pagine di Analisi usano sempre l'ultimo anno.")
    if st.button("Aggiorna dati", icon=":material/refresh:", width="stretch"):
        st.cache_data.clear()
    try:
        name = client().get_full_name()
    except Exception:
        name = None
    st.caption(f"Connesso come **{name}**" if name else "Connesso a Garmin")
    if st.button("Esci", icon=":material/logout:", width="stretch",
                 help="Scollega l'account e cancella i dati salvati su questo computer."):
        gd.logout()
        _logged_in()

end = date.today()
start = end - timedelta(days=int(period.split()[0]) - 1)

nav.run()

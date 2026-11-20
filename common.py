"""Caricamento dati (con cache) e piccoli helper grafici condivisi da tutte le pagine."""
import json
from datetime import date, timedelta

import pandas as pd
import streamlit as st

import analysis as A
import garmin_data as gd

ANALYSIS_DAYS = 365  # le pagine di analisi guardano sempre l'ultimo anno


# ---------- dati ----------
@st.cache_resource(show_spinner="Login a Garmin Connect…")
def client():
    return gd.get_client()


@st.cache_data(ttl=3600, show_spinner=False)
def daily(start: date, end: date) -> pd.DataFrame:
    bar = st.progress(0.0, "Scarico dati giornalieri…")
    df = gd.load_daily_df(client(), start, end, progress=bar.progress)
    bar.empty()
    return df


@st.cache_data(ttl=3600, show_spinner="Scarico attività…")
def activities(start: date, end: date) -> pd.DataFrame:
    return gd.load_activities_df(client(), start, end)


@st.cache_data(ttl=3600, show_spinner="Scarico peso, VO2max, readiness e previsioni gara…")
def fitness(start: date, end: date) -> tuple[dict, list[str]]:
    """Ogni sezione è indipendente: se una fallisce, le altre si vedono comunque."""
    loaders = {
        "weight": lambda: gd.load_weight_df(client(), start, end),
        "vo2": lambda: gd.load_vo2max_df(client(), start, end),
        "readiness": lambda: gd.load_readiness_df(client(), start, end),
        "race": lambda: gd.load_race_df(client(), start, end),
        "race_now": lambda: gd.load_latest_race(client()),
    }
    out, errors = {}, []
    for key, fn in loaders.items():
        try:
            out[key] = fn()
        except Exception as exc:
            out[key] = {} if key == "race_now" else pd.DataFrame()
            errors.append(f"{key}: {exc}")
    return out, errors


@st.cache_data(ttl=6 * 3600, show_spinner="Scarico i record personali…")
def records() -> pd.DataFrame:
    try:
        return gd.load_records(client())
    except Exception:
        return pd.DataFrame()


RUNS_DIR = gd.DATA_DIR / "runs"


def run_profiles(ids: tuple) -> dict:
    """Profilo di ogni corsa (tratti stabili, disaccoppiamento, meteo).
    Ogni corsa viene scaricata una volta sola e poi letta da disco."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    out, missing = {}, []
    for i in ids:
        path = RUNS_DIR / f"{i}.json"
        try:
            prof = json.loads(path.read_text())
            if prof.get("v") == A.PROFILE_VERSION:
                out[i] = prof
                continue
        except Exception:
            pass
        missing.append(i)
    if missing:
        bar = st.progress(0.0, f"Analizzo {len(missing)} corse secondo per secondo (solo la prima volta)…")
        for k, i in enumerate(missing):
            try:
                prof = A.run_profile(gd.load_activity_stream(client(), i), gd.load_activity_weather(client(), i))
                (RUNS_DIR / f"{i}.json").write_text(json.dumps(prof))
                out[i] = prof
            except Exception:
                pass  # riproverà la prossima volta
            bar.progress((k + 1) / len(missing), f"Corsa {k + 1} di {len(missing)}")
        bar.empty()
    return out


def year_window() -> tuple[date, date]:
    end = date.today()
    return end - timedelta(days=ANALYSIS_DAYS - 1), end


def daily_year() -> pd.DataFrame:
    """Ultimo anno di dati giornalieri, a partire dal primo giorno in cui hai l'orologio."""
    df = daily(*year_window())
    first = df.dropna(subset=["steps"]).index.min()
    return df[df.index >= first] if pd.notna(first) else df


def activities_long() -> pd.DataFrame:
    """Due anni di attività (servono per il confronto con l'anno precedente)."""
    end = date.today()
    return activities(end - timedelta(days=2 * 365), end)


# ---------- helper grafici e formattazione ----------
def chart(fig, where=st, height=320, **layout):
    where.plotly_chart(fig.update_layout(height=height, **layout), width="stretch", theme=None)


def kpi(col, label, series, fmt="{:.0f}", invert=False):
    s = series.dropna()
    if s.empty:
        col.metric(label, "–")
        return
    last, avg = s.iloc[-1], s.mean()
    col.metric(label, fmt.format(last), delta=fmt.format(last - avg) + " vs media",
               delta_color="inverse" if invert else "normal")


def hms(sec):
    if sec is None or pd.isna(sec) or sec == 0:
        return "–"
    sec = int(round(abs(sec)))
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def pace(sec_per_km) -> str:
    if sec_per_km is None or pd.isna(sec_per_km):
        return "–"
    return f"{int(sec_per_km // 60)}:{int(round(sec_per_km % 60)) % 60:02d}/km"


def card(html: str, tone: str = "neutral"):
    """Riquadro glass con bordo colorato a sinistra. tone: good / bad / warn / neutral."""
    st.markdown(f'<div class="g-card g-{tone}">{html}</div>', unsafe_allow_html=True)


def pill(text: str, tone: str = "neutral") -> str:
    return f'<span class="g-pill g-{tone}">{text}</span>'

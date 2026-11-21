"""Scarica i dati da Garmin Connect e li mette in cache su disco."""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from garminconnect import Garmin

TOKENSTORE = os.path.expanduser(os.getenv("GARMINTOKENS", "~/.garminconnect"))
DATA_DIR = Path(__file__).parent / "data"
CACHE_DIR = DATA_DIR / "daily_v2"
CHUNK_DAYS = 90  # gli endpoint "range" di Garmin accettano al massimo ~90 giorni per chiamata


def get_client() -> Garmin:
    """Login usando i token salvati (dal form di login della dashboard o da login.py)."""
    garmin = Garmin()
    garmin.login(TOKENSTORE)
    return garmin


def has_token() -> bool:
    tok = Path(TOKENSTORE)
    return any(tok.glob("*.json")) if tok.is_dir() else tok.exists()


def login_with_password(email: str, password: str):
    """Primo login. Restituisce ("ok", None) oppure ("needs_mfa", stato) se serve il codice MFA.
    La password non viene salvata: si salvano solo i token, nella cartella personale dell'utente."""
    garmin = Garmin(email=email, password=password, return_on_mfa=True)
    status, state = garmin.login()
    if status == "needs_mfa":
        return "needs_mfa", state
    garmin.client.dump(TOKENSTORE)
    return "ok", None


def finish_mfa(state, code: str) -> None:
    garmin = Garmin()
    garmin.resume_login(state, code)
    garmin.client.dump(TOKENSTORE)


def logout() -> None:
    """Cancella i token e tutti i dati in cache (così i dati di due account non si mescolano)."""
    import shutil
    tok = Path(TOKENSTORE)
    if tok.is_dir():
        for f in tok.glob("*.json"):
            f.unlink()
    elif tok.exists():
        tok.unlink()
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)


def _get(dct, *keys):
    for k in keys:
        if not isinstance(dct, dict):
            return None
        dct = dct.get(k)
    return dct


def _as_list(data, *keys):
    """Gli endpoint a volte rispondono con una lista, a volte con {chiave: lista}."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in keys:
            if isinstance(data.get(k), list):
                return data[k]
    return []


def _chunks(start: date, end: date, size: int = CHUNK_DAYS):
    s = start
    while s <= end:
        e = min(s + timedelta(days=size - 1), end)
        yield s.isoformat(), e.isoformat()
        s = e + timedelta(days=1)


# ---------- dati giornalieri ----------
def _fetch_range(garmin: Garmin, start: date, end: date, progress=None) -> dict[str, dict]:
    """Scarica riepilogo, passi, sonno e HRV per un intervallo, a blocchi di 90 giorni."""
    out: dict[str, dict] = defaultdict(dict)
    sources = [
        ("summary", garmin.get_daily_summaries, ("data",)),
        ("steps", garmin.get_daily_steps, ()),
        ("sleep", garmin.get_sleep_daily, ()),
        ("hrv", garmin.get_hrv_data_range, ("hrvSummaries",)),
    ]
    chunks = list(_chunks(start, end))
    total, done = len(chunks) * len(sources), 0
    for s, e in chunks:
        for key, fn, list_keys in sources:
            try:
                for item in _as_list(fn(s, e), *list_keys):
                    if item.get("calendarDate"):
                        out[item["calendarDate"]][key] = item
            except Exception:
                pass  # un endpoint senza dati (es. HRV prima del primo orologio) non blocca gli altri
            done += 1
            if progress:
                progress(done / total, f"Scarico {s} → {e}")
    return out


def load_raw_days(garmin: Garmin, start: date, end: date, progress=None) -> dict[str, dict]:
    """Dati grezzi per giorno. I giorni chiusi (prima di ieri) vengono letti dalla cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    final_before = date.today() - timedelta(days=1)

    raw, missing = {}, []
    for d in days:
        path = CACHE_DIR / f"{d.isoformat()}.json"
        if d < final_before and path.exists():
            raw[d.isoformat()] = json.loads(path.read_text())
        else:
            missing.append(d)

    if missing:
        fetched = _fetch_range(garmin, min(missing), max(missing), progress)
        for d in missing:
            item = fetched.get(d.isoformat(), {})
            raw[d.isoformat()] = item
            if d < final_before:
                (CACHE_DIR / f"{d.isoformat()}.json").write_text(json.dumps(item))
    return raw


def _bedtime_hours(ms):
    """Ora di addormentamento come ore dopo le 18:00 (es. 23:30 → 5.5, 01:00 → 7)."""
    if not ms:
        return None
    t = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)  # Garmin dà l'ora locale "finta UTC"
    return round(((t.hour + t.minute / 60) - 18) % 24, 2)


def parse_day(d: str, raw: dict) -> dict:
    s = raw.get("summary") or {}
    st = raw.get("steps") or {}
    sl = _get(raw, "sleep", "values") or {}
    hrv = raw.get("hrv") or {}

    def hours(sec):
        return round(sec / 3600, 2) if sec else None

    stress = _get(s, "stress", "avgLevel")
    return {
        "date": pd.Timestamp(d),
        "steps": _get(s, "movement", "steps", "value") or st.get("totalSteps"),
        "step_goal": _get(s, "movement", "steps", "goal") or st.get("stepGoal"),
        "distance_km": round(st["totalDistance"] / 1000, 2) if st.get("totalDistance") else None,
        "calories": _get(s, "calories", "burnedTotal"),
        "active_calories": _get(s, "calories", "burnedActive"),
        "floors": _get(s, "movement", "floorsAscended", "value"),
        "intensity_min": (_get(s, "intensityMinutes", "moderate") or 0)
        + 2 * (_get(s, "intensityMinutes", "vigorous") or 0),
        "resting_hr": _get(s, "heartRate", "restingValue") or sl.get("restingHeartRate"),
        "max_hr": _get(s, "heartRate", "maxValue"),
        "stress_avg": stress if stress is not None and stress >= 0 else None,
        "bb_high": _get(s, "bodyBattery", "maxValue"),
        "bb_low": _get(s, "bodyBattery", "minValue"),
        "bb_charged": _get(s, "bodyBattery", "chargedValue"),
        "respiration_day": _get(s, "respiration", "avgValue"),
        # sonno: il record del giorno D è la notte che finisce la mattina di D
        "sleep_h": hours(sl.get("totalSleepTimeInSeconds")),
        "deep_h": hours(sl.get("deepTime")),
        "light_h": hours(sl.get("lightTime")),
        "rem_h": hours(sl.get("remTime")),
        "awake_h": hours(sl.get("awakeTime")),
        "sleep_score": sl.get("sleepScore"),
        "bedtime_h": _bedtime_hours(sl.get("localSleepStartTimeInMillis")),
        "sleep_hr": sl.get("avgHeartRate"),
        "respiration_sleep": sl.get("respiration"),
        "spo2": sl.get("spO2"),
        "skin_temp": sl.get("skinTempC"),
        "hrv_night": hrv.get("lastNightAvg") or sl.get("avgOvernightHrv"),
        "hrv_week": hrv.get("weeklyAvg") or sl.get("hrv7dAverage"),
        "hrv_status": hrv.get("status"),
    }


def load_daily_df(garmin: Garmin, start: date, end: date, progress=None) -> pd.DataFrame:
    raw = load_raw_days(garmin, start, end, progress)
    rows = [parse_day(d, raw[d]) for d in sorted(raw)]
    return pd.DataFrame(rows).set_index("date")


# ---------- attività ----------
def load_activities_df(garmin: Garmin, start: date, end: date) -> pd.DataFrame:
    acts = garmin.get_activities_by_date(start.isoformat(), end.isoformat())
    rows = []
    for a in acts:
        dist = a.get("distance") or 0
        dur = a.get("duration") or 0
        start_t = pd.to_datetime(a.get("startTimeLocal"))
        gap = a.get("avgGradeAdjustedSpeed")  # m/s corretta per salite/discese
        rows.append({
            "id": a.get("activityId"),
            "start": start_t,
            "end": start_t + pd.Timedelta(seconds=dur) if pd.notna(start_t) else None,
            "name": a.get("activityName"),
            "type": _get(a, "activityType", "typeKey") or "other",
            "distance_km": round(dist / 1000, 2) if dist else None,
            "duration_min": round(dur / 60, 1) if dur else None,
            "pace_min_km": round((dur / 60) / (dist / 1000), 2) if dist > 0 else None,
            "speed_ms": a.get("averageSpeed"),
            "gap_speed_ms": gap if gap and gap > 0 else None,
            "avg_hr": a.get("averageHR"),
            "max_hr": a.get("maxHR"),
            "calories": a.get("calories"),
            "elev_gain_m": a.get("elevationGain"),
            "training_load": a.get("activityTrainingLoad"),
            "aerobic_te": a.get("aerobicTrainingEffect"),
            "anaerobic_te": a.get("anaerobicTrainingEffect"),
            "te_label": a.get("trainingEffectLabel"),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("start", ascending=False)
    return df


# ---------- record personali ----------
# value: secondi per i tempi, metri per le distanze, conteggi per passi/serie
PR_LABELS = {
    "1k.run": ("1 km", "time"), "1mile.run": ("1 miglio", "time"), "5k.run": ("5 km", "time"),
    "10k.run": ("10 km", "time"), "halfmarathon.run": ("Mezza maratona", "time"),
    "half.marathon.run": ("Mezza maratona", "time"), "marathon.run": ("Maratona", "time"),
    "farthest.run": ("Corsa più lunga", "dist"), "farthest.cycle": ("Uscita in bici più lunga", "dist"),
    "40k.cycle": ("40 km bici", "time"), "max.elev": ("Dislivello max in bici", "m"),
    "steps.best.day": ("Passi in un giorno", "count"), "steps.best.week": ("Passi in una settimana", "count"),
    "steps.best.month": ("Passi in un mese", "count"),
    "steps.longest.streak": ("Serie più lunga obiettivo passi", "days"),
    "steps.current.streak": ("Serie attuale obiettivo passi", "days"),
}


def load_records(garmin: Garmin) -> pd.DataFrame:
    types = {t["id"]: t.get("key", "") for t in _as_list(garmin.get_personal_record_types())}
    rows = []
    for p in _as_list(garmin.get_personal_record()):
        key = types.get(p.get("typeId"), "").replace("pr.label.", "")
        rows.append({
            "key": key,
            "label": PR_LABELS.get(key, (key, ""))[0],
            "kind": PR_LABELS.get(key, ("", "count"))[1],
            "value": p.get("value"),
            "date": pd.to_datetime(p.get("activityStartDateTimeLocalFormatted") or p.get("prStartTimeLocalFormatted")),
            "activity": p.get("activityName"),
            "sport": p.get("activityType"),
        })
    return pd.DataFrame(rows)


# ---------- forma: peso, VO2max, training readiness, previsioni gara ----------
RACE_DISTANCES = {"time5K": ("5 km", 5.0), "time10K": ("10 km", 10.0),
                  "timeHalfMarathon": ("Mezza", 21.0975), "timeMarathon": ("Maratona", 42.195)}


def load_weight_df(garmin: Garmin, start: date, end: date) -> pd.DataFrame:
    data = garmin.get_body_composition(start.isoformat(), end.isoformat())
    rows = []
    for w in _as_list(data, "dateWeightList"):
        kg = w.get("weight")
        if not kg:
            continue
        rows.append({
            "date": pd.Timestamp(w.get("calendarDate")),
            "weight_kg": kg / 1000 if kg > 1000 else kg,  # Garmin restituisce grammi
            "body_fat": w.get("bodyFat"),
            "bmi": w.get("bmi"),
        })
    df = pd.DataFrame(rows, columns=["date", "weight_kg", "body_fat", "bmi"])
    return df.groupby("date").last() if not df.empty else df.set_index("date")


def load_vo2max_df(garmin: Garmin, start: date, end: date) -> pd.DataFrame:
    rows = []
    for m in _as_list(garmin.get_max_metrics_range(start.isoformat(), end.isoformat())):
        for sport, col in (("generic", "vo2_run"), ("cycling", "vo2_bike")):
            v = m.get(sport) or {}
            val = v.get("vo2MaxPreciseValue") or v.get("vo2MaxValue")
            if val and v.get("calendarDate"):
                rows.append({"date": pd.Timestamp(v["calendarDate"]), "sport": col, "value": val})
    if not rows:
        return pd.DataFrame(columns=["vo2_run", "vo2_bike"])
    return pd.DataFrame(rows).pivot_table(index="date", columns="sport", values="value", aggfunc="last")


def load_readiness_df(garmin: Garmin, start: date, end: date) -> pd.DataFrame:
    rows = []
    for r in _as_list(garmin.get_training_readiness_range(start.isoformat(), end.isoformat())):
        if r.get("score") is None or not r.get("calendarDate"):
            continue
        rows.append({
            "date": pd.Timestamp(r["calendarDate"]),
            "ts": r.get("timestampLocal") or r.get("timestamp") or "",
            "morning": r.get("inputContext") == "AFTER_WAKEUP_RESET",
            "readiness": r.get("score"),
            "level": r.get("level"),
            "recovery_h": round(r["recoveryTime"] / 60, 1) if r.get("recoveryTime") else None,
            "acute_load": r.get("acuteLoad"),
        })
    if not rows:
        return pd.DataFrame(columns=["readiness", "level", "recovery_h", "acute_load"])
    df = pd.DataFrame(rows)
    # più valori al giorno (mattina + dopo le attività): tengo quello del risveglio, altrimenti l'ultimo
    df = df.sort_values(["date", "morning", "ts"]).groupby("date").last()
    return df.drop(columns=["ts", "morning"])


def load_race_df(garmin: Garmin, start: date, end: date) -> pd.DataFrame:
    start = max(start, end - timedelta(days=365))  # l'endpoint accetta al massimo un anno
    data = garmin.get_race_predictions(start.isoformat(), end.isoformat(), "daily")
    rows = []
    for p in _as_list(data):
        if not p.get("calendarDate"):
            continue
        row = {"date": pd.Timestamp(p["calendarDate"])}
        row.update({label: p.get(key) for key, (label, _) in RACE_DISTANCES.items()})
        rows.append(row)
    if not rows:
        return pd.DataFrame(columns=[label for label, _ in RACE_DISTANCES.values()])
    return pd.DataFrame(rows).groupby("date").last()


def load_latest_race(garmin: Garmin) -> dict:
    p = garmin.get_race_predictions() or {}
    if isinstance(p, list):
        p = p[-1] if p else {}
    return {label: p.get(key) for key, (label, _) in RACE_DISTANCES.items()}


# ---------- impostazioni locali (es. gara obiettivo) ----------
SETTINGS_FILE = DATA_DIR / "settings.json"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except Exception:
        return {}


def save_settings(settings: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2, default=str))


# ---------- dati secondo per secondo di una corsa ----------
_STREAM_KEYS = {"directHeartRate": "hr", "directSpeed": "speed", "directGradeAdjustedSpeed": "gap",
                "sumDuration": "t", "sumMovingDuration": "t_moving", "sumDistance": "dist",
                # dinamiche di corsa (orologio o fascia compatibile)
                "directDoubleCadence": "cad", "directStrideLength": "stride", "directGroundContactTime": "gct",
                "directGroundContactBalanceLeft": "gcb", "directVerticalOscillation": "vo",
                "directVerticalRatio": "vr"}


def load_activity_stream(garmin: Garmin, activity_id) -> pd.DataFrame:
    """FC, velocità e velocità corretta per pendenza, un punto al secondo."""
    d = garmin.get_activity_details(str(activity_id), maxchart=20000)
    idx = {m["key"]: m["metricsIndex"] for m in d.get("metricDescriptors", [])}
    cols = {name: idx[key] for key, name in _STREAM_KEYS.items() if key in idx}
    rows = [{name: (p["metrics"][i] if i < len(p["metrics"]) else None) for name, i in cols.items()}
            for p in d.get("activityDetailMetrics", [])]
    return pd.DataFrame(rows, columns=list(cols)).astype(float)


def load_activity_weather(garmin: Garmin, activity_id) -> dict:
    """Meteo della stazione più vicina all'inizio dell'attività (Garmin la dà in °F)."""
    try:
        w = garmin.get_activity_weather(str(activity_id)) or {}
    except Exception:
        return {}
    temp_f = w.get("temp")
    return {
        "temp_c": round((temp_f - 32) * 5 / 9, 1) if temp_f is not None else None,
        "humidity": w.get("relativeHumidity"),
        "dew_point_c": round((w["dewPoint"] - 32) * 5 / 9, 1) if w.get("dewPoint") is not None else None,
    }

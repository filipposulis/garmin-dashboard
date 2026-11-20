"""Analisi che Garmin Connect non fa. Solo calcoli: niente Streamlit qui dentro."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

RUN_TYPES = {"running", "treadmill_running", "track_running", "street_running", "virtual_run"}


# =====================================================================
# 1. INSIGHT: cosa influenza sonno e recupero
# =====================================================================
@dataclass
class Insight:
    text: str
    detail: str
    effect: float       # differenza tra i due gruppi, nell'unità dell'outcome
    d: float            # Cohen's d (forza dell'effetto)
    p: float            # p-value del test di permutazione
    n_a: int
    n_b: int
    good: bool          # True se l'effetto del gruppo A è positivo per te
    feature: str
    outcome: str
    values_a: list = None
    values_b: list = None
    label_a: str = ""
    label_b: str = ""


def day_features(daily: pd.DataFrame, acts: pd.DataFrame) -> pd.DataFrame:
    """Una riga per giorno D: cosa hai fatto in D e come è andata la notte/mattina dopo (D+1)."""
    f = pd.DataFrame(index=daily.index)
    f["steps"] = daily["steps"]
    f["stress"] = daily["stress_avg"]
    f["sleep_prev"] = daily["sleep_h"]  # notte prima del giorno D

    if not acts.empty:
        a = acts.dropna(subset=["start"]).copy()
        a["day"] = a["start"].dt.normalize()
        a["end_h"] = a["end"].dt.hour + a["end"].dt.minute / 60
        g = a.groupby("day")
        f["workout_min"] = g["duration_min"].sum().reindex(f.index).fillna(0)
        f["load"] = g["training_load"].sum().reindex(f.index).fillna(0)
        f["last_end_h"] = g["end_h"].max().reindex(f.index)
    else:
        f["workout_min"] = 0.0
        f["load"] = 0.0
        f["last_end_h"] = np.nan

    # risultati della notte/mattina successiva
    nxt = daily.shift(-1)
    f["next_sleep_score"] = nxt["sleep_score"]
    f["next_sleep_h"] = nxt["sleep_h"]
    f["next_deep_h"] = nxt["deep_h"]
    f["next_hrv"] = nxt["hrv_night"]
    f["next_rhr"] = nxt["resting_hr"]
    f["next_bb_high"] = nxt["bb_high"]
    f["next_bedtime"] = nxt["bedtime_h"]
    # risultati dello stesso giorno (dopo la notte prima)
    f["stress_today"] = daily["stress_avg"]
    return f


def _perm_test(a: np.ndarray, b: np.ndarray, n: int = 3000, seed: int = 0) -> float:
    """p-value a due code per la differenza delle medie (test di permutazione)."""
    rng = np.random.default_rng(seed)
    obs = abs(a.mean() - b.mean())
    pooled = np.concatenate([a, b])
    hits = 0
    for _ in range(n):
        rng.shuffle(pooled)
        if abs(pooled[: len(a)].mean() - pooled[len(a):].mean()) >= obs:
            hits += 1
    return (hits + 1) / (n + 1)


def _fmt_hm(hours: float) -> str:
    m = int(round(abs(hours) * 60))
    return f"{m // 60} h {m % 60:02d} min" if m >= 60 else f"{m} min"


def _clock(h_after_18: float) -> str:
    t = (h_after_18 + 18) % 24
    return f"{int(t):02d}:{int(round((t % 1) * 60)) % 60:02d}"


# outcome: (etichetta, unità, formato, più alto è meglio?)
# outcome: (frase, etichetta breve, unità, formato, più alto è meglio?)
OUTCOMES = {
    "next_sleep_score": ("il tuo sleep score", "Sleep score", "punti", "{:.0f} punti", True),
    "next_sleep_h": ("il tuo sonno", "Ore di sonno", "h", None, True),
    "next_deep_h": ("il tuo sonno profondo", "Sonno profondo", "h", None, True),
    "next_hrv": ("la tua HRV notturna", "HRV notturna", "ms", "{:.0f} ms", True),
    "next_rhr": ("la tua FC a riposo", "FC a riposo", "bpm", "{:.1f} bpm", False),
    "next_bb_high": ("la tua Body Battery al risveglio", "Body Battery al risveglio", "punti", "{:.0f} punti", True),
    "stress_today": ("il tuo stress medio", "Stress medio", "punti", "{:.0f} punti", False),
}
# quando si misura l'outcome rispetto al giorno della "causa"
_WHEN = {"next_rhr": "il giorno dopo", "next_bb_high": "il giorno dopo", "stress_today": "quel giorno"}


def _hypotheses(f: pd.DataFrame):
    """(feature, descrizione gruppo A, descrizione gruppo B, maschera A, maschera B, outcomes)."""
    nxt = ["next_sleep_score", "next_sleep_h", "next_deep_h", "next_hrv", "next_rhr", "next_bb_high"]
    trained = f["workout_min"] > 0

    late = f["last_end_h"] >= 20
    yield ("late_workout", "ti alleni dopo le 20", "ti alleni prima delle 20",
           trained & late, trained & ~late & f["last_end_h"].notna(), nxt)

    yield ("workout", "ti alleni", "fai riposo", trained, ~trained, nxt)

    if f["steps"].notna().sum() >= 20:
        hi, lo = f["steps"].quantile(0.7), f["steps"].quantile(0.3)
        yield ("steps", f"fai più di {hi:,.0f} passi".replace(",", "."), f"ne fai meno di {lo:,.0f}".replace(",", "."),
               f["steps"] >= hi, f["steps"] <= lo, ["next_sleep_score", "next_sleep_h", "next_deep_h"])

    if f["stress"].notna().sum() >= 20:
        hi, lo = f["stress"].quantile(0.7), f["stress"].quantile(0.3)
        yield ("stress", f"lo stress medio supera {hi:.0f}", f"resta sotto {lo:.0f}",
               f["stress"] >= hi, f["stress"] <= lo, ["next_sleep_score", "next_hrv", "next_rhr", "next_bb_high"])

    loads = f.loc[trained, "load"]
    if (loads > 0).sum() >= 15:
        hi = loads.quantile(0.67)
        yield ("load", f"fai un allenamento duro (carico > {hi:.0f})", "fai un allenamento leggero",
               trained & (f["load"] >= hi), trained & (f["load"] < hi) & (f["load"] > 0),
               ["next_hrv", "next_rhr", "next_sleep_score", "next_bb_high"])

    bt = f["next_bedtime"]
    if bt.notna().sum() >= 20:
        cut = bt.median()
        yield ("bedtime", f"vai a letto dopo le {_clock(cut)}", f"prima delle {_clock(cut)}",
               bt > cut, bt <= cut, ["next_sleep_score", "next_sleep_h", "next_deep_h", "next_hrv", "next_bb_high"])

    sp = f["sleep_prev"]
    if sp.notna().sum() >= 20:
        yield ("short_sleep", "dormi meno di 7 ore", "dormi almeno 7 ore",
               sp < 7, sp >= 7, ["stress_today"])


def find_insights(daily: pd.DataFrame, acts: pd.DataFrame, min_n: int = 6,
                  max_p: float = 0.1, min_d: float = 0.3) -> list[Insight]:
    f = day_features(daily, acts)
    found: list[Insight] = []
    for feat, a_desc, b_desc, mask_a, mask_b, outcomes in _hypotheses(f):
        for out in outcomes:
            a = f.loc[mask_a.fillna(False), out].dropna().to_numpy(float)
            b = f.loc[mask_b.fillna(False), out].dropna().to_numpy(float)
            if len(a) < min_n or len(b) < min_n:
                continue
            diff = a.mean() - b.mean()
            sd = np.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / (len(a) + len(b) - 2))
            if not sd or np.isnan(sd):
                continue
            d = diff / sd
            if abs(d) < min_d:
                continue
            p = _perm_test(a, b)
            if p > max_p:
                continue
            phrase, label, unit, fmt, higher_better = OUTCOMES[out]
            amount = _fmt_hm(diff) if unit == "h" else fmt.format(abs(diff))
            verb = "aumenta" if diff > 0 else "cala"
            # per l'orario di addormentamento la notte "colpita" è la stessa, non quella dopo
            when = _WHEN.get(out, "quella notte" if feat == "bedtime" else "la notte dopo")
            text = f"Quando {a_desc}, {when} {phrase} {verb} in media di {amount}"
            detail = (f"{label}: {a.mean():.1f} vs {b.mean():.1f} {unit} — "
                      f"{len(a)} giorni in cui {a_desc}, {len(b)} in cui {b_desc}.")
            found.append(Insight(text, detail, diff, d, p, len(a), len(b),
                                 good=(diff > 0) == higher_better, feature=feat, outcome=out,
                                 values_a=a.tolist(), values_b=b.tolist(), label_a=a_desc, label_b=b_desc))
    # tengo l'effetto più forte per ogni coppia (feature, tipo di outcome) e ordino per forza
    found.sort(key=lambda i: (-abs(i.d), i.p))
    return found


def strength_label(i: Insight) -> str:
    if abs(i.d) >= 0.8 and i.p < 0.02:
        return "forte"
    if abs(i.d) >= 0.5 and i.p < 0.05:
        return "chiaro"
    return "probabile"


# =====================================================================
# 2. ALLERTE: scostamenti dal tuo normale
# =====================================================================
# metrica: (etichetta, unità, +1 se un aumento è un segnale negativo / -1 se lo è un calo)
ALERT_METRICS = {
    "resting_hr": ("FC a riposo", "bpm", +1),
    "hrv_night": ("HRV notturna", "ms", -1),
    "respiration_sleep": ("Respirazione nel sonno", "resp/min", +1),
    "sleep_hr": ("FC media nel sonno", "bpm", +1),
    "stress_avg": ("Stress medio", "", +1),
    "skin_temp": ("Temperatura cutanea", "°C", +1),
}


def baselines(daily: pd.DataFrame, window: int = 28, gap: int = 3) -> pd.DataFrame:
    """Per ogni metrica: media e deviazione standard dei 28 giorni precedenti,
    escludendo gli ultimi 3 (così una malattia in corso non "sporca" il riferimento)."""
    out = {}
    for m in ALERT_METRICS:
        if m not in daily or daily[m].notna().sum() < 14:
            continue
        s = daily[m].astype(float)
        hist = s.shift(gap).rolling(window, min_periods=14)
        mean, std = hist.mean(), hist.std()
        std = std.clip(lower=std.median() * 0.5 if std.notna().any() else None)  # evita std ~0
        out[(m, "value")] = s
        out[(m, "mean")] = mean
        out[(m, "std")] = std
        out[(m, "z")] = (s - mean) / std * ALERT_METRICS[m][2]  # z > 0 = direzione "brutta"
    return pd.DataFrame(out)


def alert_days(base: pd.DataFrame, z_thr: float = 1.5) -> pd.DataFrame:
    """Per ogni giorno: quante metriche sono fuori norma nella direzione negativa, e quali."""
    if base.empty:
        return pd.DataFrame(columns=["n_flags", "flags", "level"])
    zs = base.xs("z", axis=1, level=1)
    flags = zs.ge(z_thr)
    res = pd.DataFrame(index=base.index)
    res["n_flags"] = flags.sum(axis=1)
    res["flags"] = flags.apply(lambda r: [m for m, v in r.items() if v], axis=1)
    # 2 giorni di fila con almeno 2 segnali = allerta; 2+ segnali in un giorno = attenzione
    two = res["n_flags"] >= 2
    res["level"] = np.select(
        [two & two.shift(1, fill_value=False), two, res["n_flags"] == 1],
        ["allerta", "attenzione", "lieve"], default="ok")
    return res


def alert_messages(base: pd.DataFrame, day: pd.Timestamp, z_thr: float = 1.5) -> list[str]:
    msgs = []
    for m, (label, unit, sign) in ALERT_METRICS.items():
        if (m, "z") not in base or day not in base.index:
            continue
        z = base.at[day, (m, "z")]
        if pd.isna(z) or z < z_thr:
            continue
        v, mu = base.at[day, (m, "value")], base.at[day, (m, "mean")]
        diff = v - mu
        msgs.append(f"{label}: {v:.1f} {unit} ({'+' if diff > 0 else ''}{diff:.1f} rispetto al tuo normale di {mu:.1f})")
    return msgs


# =====================================================================
# 3. FITNESS / FATIGUE / FORM (modello di Banister, come il PMC di TrainingPeaks)
# =====================================================================
CTL_DAYS, ATL_DAYS = 42, 7


def daily_load(acts: pd.DataFrame, start: date, end: date) -> pd.Series:
    idx = pd.date_range(start, end, freq="D")
    if acts.empty:
        return pd.Series(0.0, index=idx)
    a = acts.dropna(subset=["start"]).copy()
    load = a["training_load"].astype(float)
    # se manca il carico Garmin, stima grezza: 1 punto al minuto
    load = load.fillna(a["duration_min"].astype(float))
    return load.groupby(a["start"].dt.normalize()).sum().reindex(idx, fill_value=0.0)


def pmc(load: pd.Series, future_load: pd.Series | None = None) -> pd.DataFrame:
    """CTL = forma fisica (42 g), ATL = fatica (7 g), TSB = freschezza = CTL - ATL di ieri."""
    s = load if future_load is None else pd.concat([load, future_load])
    ctl = s.ewm(alpha=1 / CTL_DAYS, adjust=False).mean()
    atl = s.ewm(alpha=1 / ATL_DAYS, adjust=False).mean()
    df = pd.DataFrame({"load": s, "ctl": ctl, "atl": atl})
    df["tsb"] = (ctl - atl).shift(1)
    df["future"] = False
    if future_load is not None:
        df.loc[future_load.index, "future"] = True
    return df


def form_zone(tsb: float) -> tuple[str, str]:
    if pd.isna(tsb):
        return "–", ""
    if tsb < -30:
        return "Sovraccarico", "Fatica molto alta: rischio infortunio, valuta qualche giorno leggero."
    if tsb < -10:
        return "Costruzione", "Stai accumulando fatica utile: è qui che si migliora."
    if tsb < 5:
        return "Mantenimento", "Carico e recupero sono in equilibrio."
    if tsb < 25:
        return "Fresco", "Sei riposato: il momento giusto per una gara o un test."
    return "Scarico", "Riposo prolungato: la forma inizia a calare."


def ramp_rate(p: pd.DataFrame) -> float:
    """Variazione della forma (CTL) negli ultimi 7 giorni."""
    past = p[~p["future"]]
    if len(past) < 8:
        return float("nan")
    return float(past["ctl"].iloc[-1] - past["ctl"].iloc[-8])


# =====================================================================
# 4. EFFICIENZA AEROBICA (dai dati secondo per secondo)
# =====================================================================
# Perché non la media della corsa: in un allenamento a ripetute la media mescola riscaldamento,
# recuperi e prove; sopra soglia la FC non sale più in proporzione alla velocità; il caldo alza la FC.
# Quindi: (1) solo tratti di 2 minuti a ritmo e FC stabili, (2) solo vicino a una FC di riferimento
# in zona aerobica, (3) correzione per caldo+umidità stimata sui tuoi dati.

WARMUP_S = 480        # salto i primi 8 minuti
WIN_S, STEP_S = 120, 30
HR_LAG_S = 30         # la FC risponde allo sforzo con ~30 s di ritardo
MIN_SPEED = 1.9       # m/s (~8:45/km): sotto è camminata
MAX_CV = 0.06         # variazione max del ritmo nel tratto
MAX_HR_RANGE = 10     # bpm: la FC deve essersi assestata
PROFILE_VERSION = 1


def stream_grid(stream: pd.DataFrame) -> pd.DataFrame:
    """Uno sample al secondo (tempo trascorso), con velocità corretta per pendenza dove c'è."""
    if stream.empty or "t" not in stream or "hr" not in stream:
        return pd.DataFrame(columns=["hr", "sp"])
    s = stream.dropna(subset=["t"]).sort_values("t").copy()
    s["t"] = s["t"].round().astype(int)
    s = s.drop_duplicates("t").set_index("t")
    s = s.reindex(range(int(s.index.min()), int(s.index.max()) + 1))
    gap = s["gap"] if "gap" in s else pd.Series(np.nan, index=s.index)
    spd = s["speed"] if "speed" in s else pd.Series(np.nan, index=s.index)
    sp = gap.where(gap > 0).fillna(spd)
    return pd.DataFrame({"hr": s["hr"].interpolate(limit=5), "sp": sp.interpolate(limit=3)})


def steady_windows(g: pd.DataFrame) -> pd.DataFrame:
    """Tratti di 2 minuti con ritmo costante e FC stabile → (inizio, FC media, velocità media)."""
    if len(g) < WARMUP_S + WIN_S + HR_LAG_S:
        return pd.DataFrame(columns=["t", "hr", "sp"])
    sp10 = g["sp"].rolling(10, center=True, min_periods=6).mean()  # toglie il rumore del GPS
    hr = g["hr"]
    out = []
    for t0 in range(g.index[0] + WARMUP_S, g.index[-1] - WIN_S - HR_LAG_S, STEP_S):
        sp = sp10.loc[t0:t0 + WIN_S - 1]
        h = hr.loc[t0 + HR_LAG_S:t0 + HR_LAG_S + WIN_S - 1]
        if sp.isna().mean() > 0.05 or h.isna().mean() > 0.1:
            continue
        m = sp.mean()
        if m < MIN_SPEED or sp.std() / m > MAX_CV or h.max() - h.min() > MAX_HR_RANGE:
            continue
        out.append((t0, float(h.mean()), float(m)))
    return pd.DataFrame(out, columns=["t", "hr", "sp"])


def decoupling(g: pd.DataFrame, min_minutes: float = 50, max_cv: float = 0.12) -> dict | None:
    """Disaccoppiamento aerobico (Friel): quanto peggiora velocità/FC tra prima e seconda metà.
    Ha senso solo su corse lunghe a ritmo abbastanza costante."""
    if len(g) < min_minutes * 60:
        return None
    body = g.iloc[600:]  # dopo 10 minuti di riscaldamento
    body = body[(body["sp"] >= MIN_SPEED) & body["hr"].notna()]
    if len(body) < 30 * 60:
        return None
    sp10 = body["sp"].rolling(10, min_periods=6).mean()
    cv = float(sp10.std() / sp10.mean())
    half = len(body) // 2
    a, b = body.iloc[:half], body.iloc[half:]
    ef1, ef2 = a["sp"].mean() / a["hr"].mean(), b["sp"].mean() / b["hr"].mean()
    return {"pct": float((ef1 - ef2) / ef1 * 100), "cv": cv, "steady": cv <= max_cv,
            "hr1": float(a["hr"].mean()), "hr2": float(b["hr"].mean()),
            "pace1": float(1000 / a["sp"].mean()), "pace2": float(1000 / b["sp"].mean()),
            "minutes": len(g) / 60}


def decoupling_valid(d: dict | None, min_minutes: float = 60) -> bool:
    """Valido solo su corse di almeno un'ora a ritmo davvero costante: niente progressivi,
    niente lunghi con tratti a ritmo gara (lì la FC sale per il ritmo, non per la deriva)."""
    if not d or d["minutes"] < min_minutes:
        return False
    return d["cv"] <= 0.12 and abs(d["pace2"] - d["pace1"]) / d["pace1"] <= 0.05


def run_profile(stream: pd.DataFrame, weather: dict) -> dict:
    """Riassunto compatto di una corsa (finisce nella cache su disco)."""
    g = stream_grid(stream)
    has_gap = "gap" in stream and stream["gap"].notna().any()
    w = steady_windows(g) if has_gap else pd.DataFrame(columns=["t", "hr", "sp"])
    return {
        "v": PROFILE_VERSION,
        "gps": bool(has_gap),  # senza GPS la velocità è stimata dal polso: inaffidabile
        "windows": w[["hr", "sp"]].round(3).values.tolist(),
        "decoupling": decoupling(g) if has_gap else None,
        **weather,
    }


def heat_index(temp_c, dew_c) -> float:
    """Regola dei runner: temperatura + punto di rugiada in °F. Sotto 100 il caldo non pesa."""
    if temp_c is None or dew_c is None or pd.isna(temp_c) or pd.isna(dew_c):
        return np.nan
    return max(temp_c * 9 / 5 + 32 + dew_c * 9 / 5 + 32 - 100, 0.0)


def efficiency_model(runs: pd.DataFrame, profiles: dict, ref_hr: float, band: float = 8) -> dict:
    """Velocità a ref_hr per ogni corsa, corretta per il caldo.

    runs: tabella attività (solo corse); profiles: {id: run_profile}."""
    rows = []
    for _, r in runs.iterrows():
        p = profiles.get(r["id"])
        if not p or not p.get("gps"):
            continue
        for hr, sp in p["windows"]:
            rows.append((r["id"], r["start"], r["name"], hr, sp, p.get("temp_c"), p.get("dew_point_c")))
    W = pd.DataFrame(rows, columns=["id", "date", "name", "hr", "sp", "temp", "dew"])
    n_no_gps = sum(1 for i in runs["id"] if i in profiles and not profiles[i].get("gps"))
    if W.empty:
        return {"runs": pd.DataFrame(), "n_no_gps": n_no_gps}

    near = W[(W["hr"] - ref_hr).abs() <= band].copy()
    if len(near) < 20:
        return {"runs": pd.DataFrame(), "n_no_gps": n_no_gps, "too_few": True}
    # pendenza velocità/FC vicino alla FC di riferimento, per riportare ogni tratto esattamente a ref_hr
    slope = np.polyfit(near["hr"], near["sp"], 1)[0]
    slope = float(np.clip(slope, 0.005, 0.04))  # m/s per bpm, valori plausibili
    near["sp_ref"] = near["sp"] + slope * (ref_hr - near["hr"])

    per = near.groupby("id").agg(date=("date", "first"), name=("name", "first"), sp=("sp_ref", "median"),
                                 n=("sp_ref", "size"), temp=("temp", "first"), dew=("dew", "first"))
    per = per[per["n"] >= 4].sort_values("date")
    per["heat"] = [heat_index(t, d) for t, d in zip(per["temp"], per["dew"])]
    per["heat"] = per["heat"].fillna(per["heat"].median())

    # quanto ti rallenta il caldo a parità di FC (stimato su di te, con il trend nel tempo come controllo)
    heat_coef = 0.0
    if len(per) >= 12 and per["heat"].std() > 5:
        days = (per["date"] - per["date"].min()).dt.days.to_numpy(float)
        X = np.column_stack([np.ones(len(per)), per["heat"], days])
        beta = np.linalg.lstsq(X, per["sp"].to_numpy(float), rcond=None)[0]
        heat_coef = float(min(beta[1], 0.0))  # il caldo non può farti andare più veloce
    per["sp_adj"] = per["sp"] - heat_coef * per["heat"]
    per["pace_raw"] = 1000 / per["sp"]
    per["pace_adj"] = 1000 / per["sp_adj"]
    return {"runs": per, "slope": slope, "heat_coef": heat_coef, "n_no_gps": n_no_gps}


def heat_cost(heat_coef: float, ref_sp: float, temp_c: float, dew_c: float) -> float:
    """Secondi al km persi a parità di FC in quelle condizioni."""
    h = heat_index(temp_c, dew_c)
    if not heat_coef or pd.isna(h) or not ref_sp:
        return 0.0
    return 1000 / (ref_sp + heat_coef * h) - 1000 / ref_sp


def efficiency_trend(per: pd.DataFrame, windows=(180, 90, 0), span: int = 42) -> list[dict]:
    """Mediana del passo corretto nelle 6 settimane che terminano N giorni fa."""
    if per.empty:
        return []
    last = per["date"].max().normalize()
    out = []
    for back in windows:
        end = last - pd.Timedelta(days=back)
        w = per[(per["date"] > end - pd.Timedelta(days=span)) & (per["date"] <= end + pd.Timedelta(days=1))]
        if len(w) >= 3:
            out.append({"days_ago": back, "pace": float(w["pace_adj"].median()),
                        "pace_raw": float(w["pace_raw"].median()), "n": len(w)})
    return out


# =====================================================================
# 5. GARA OBIETTIVO
# =====================================================================
def parse_time(text: str) -> float | None:
    """'1:45:00' → 6300 s, '45:30' → 2730 s, '1h45' → 6300 s, '3h' → 10800 s."""
    t = (text or "").strip().lower().replace(" ", "")
    try:
        if "h" in t:
            h, _, rest = t.partition("h")
            m, _, sec = rest.replace("m", ":").partition(":")
            return float(h) * 3600 + float(m or 0) * 60 + float(sec.strip("s") or 0)
        nums = [float(x) for x in t.split(":")]
    except ValueError:
        return None
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    return None


def prediction_trend(series: pd.Series, days: int = 60) -> tuple[float, float] | None:
    """Pendenza (secondi al giorno) e valore attuale della retta sugli ultimi N giorni."""
    s = series.dropna()
    s = s[s.index >= s.index.max() - pd.Timedelta(days=days)] if not s.empty else s
    if len(s) < 10:
        return None
    x = (s.index - s.index[0]).days.to_numpy(float)
    slope, intercept = np.polyfit(x, s.to_numpy(float), 1)
    return float(slope), float(intercept + slope * x[-1])


def project_time(current: float, slope_per_day: float, days_left: int) -> float:
    """Proiezione con miglioramento che rallenta (dimezza ogni 8 settimane): più realistico di una retta."""
    if days_left <= 0:
        return current
    half_life = 56
    k = np.log(2) / half_life
    gain = slope_per_day * (1 - np.exp(-k * days_left)) / k
    return current + gain


TAPER_DAYS = {"5 km": 7, "10 km": 10, "Mezza": 12, "Maratona": 18}


def taper_plan(load: pd.Series, race_day: date, distance_label: str, cut: float = 0.5) -> dict:
    """Simula: continui col tuo carico medio delle ultime 4 settimane, poi scarichi al 50% dal giorno X.
    Restituisce il giorno di inizio scarico e la forma prevista il giorno della gara."""
    today = pd.Timestamp(date.today())
    race = pd.Timestamp(race_day)
    days_left = (race - today).days
    if days_left <= 0:
        return {}
    avg = load[load.index > today - pd.Timedelta(days=28)].mean()
    taper = min(TAPER_DAYS.get(distance_label, 10), days_left)
    future_idx = pd.date_range(today + pd.Timedelta(days=1), race, freq="D")
    fut = pd.Series(avg, index=future_idx)
    fut[fut.index > race - pd.Timedelta(days=taper)] = avg * cut
    fut.iloc[-1] = 0.0  # il carico della gara non conta per la freschezza della mattina
    p = pmc(load[load.index <= today], fut)
    return {
        "taper_start": (race - pd.Timedelta(days=taper - 1)).date(),
        "taper_days": taper,
        "avg_load": avg,
        "race_tsb": float(p["tsb"].iloc[-1]),
        "race_ctl": float(p["ctl"].iloc[-1]),
        "pmc": p,
    }


# =====================================================================
# 6. CALENDARIO E SERIE
# =====================================================================
def streaks(active: pd.Series) -> tuple[int, int]:
    """(serie attuale, serie più lunga) di giorni consecutivi True."""
    best = cur = 0
    for v in active.fillna(False).astype(bool):
        cur = cur + 1 if v else 0
        best = max(best, cur)
    # la serie attuale non si interrompe solo perché oggi non hai ancora fatto nulla
    vals = active.fillna(False).astype(bool).tolist()
    if vals and not vals[-1]:
        vals = vals[:-1]
    current = 0
    for v in reversed(vals):
        if not v:
            break
        current += 1
    return current, best


def calendar_grid(values: pd.Series, end: date, weeks: int = 53) -> pd.DataFrame:
    """Griglia stile GitHub: righe = giorni della settimana (lun→dom), colonne = settimane."""
    end_ts = pd.Timestamp(end)
    start = end_ts - pd.Timedelta(days=end_ts.weekday()) - pd.Timedelta(weeks=weeks - 1)
    idx = pd.date_range(start, end_ts, freq="D")
    v = values.reindex(idx)
    df = pd.DataFrame({"value": v.values, "date": idx})
    df["week"] = (df["date"] - pd.to_timedelta(df["date"].dt.weekday, unit="D"))
    df["weekday"] = df["date"].dt.weekday
    return df

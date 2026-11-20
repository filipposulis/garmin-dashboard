"""Le 6 pagine di analisi: quello che Garmin Connect non ti dice."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import analysis as A
import garmin_data as gd
from common import (activities_long, card, chart, daily_year, fitness, hms, pace, pill, records,
                    run_profiles, year_window)

MONTHS = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
_DAYS = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
_MONTHS_LONG = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre",
                "ottobre", "novembre", "dicembre"]


def _it_date(d) -> str:
    return f"{_DAYS[d.weekday()]} {d.day} {_MONTHS_LONG[d.month - 1]}"


TONE_COLOR = {"good": "#5EEAD4", "bad": "#FCA5A5", "warn": "#FCD34D", "neutral": "#7DD3FC"}
LEVEL_TONE = {"ok": "good", "lieve": "neutral", "attenzione": "warn", "allerta": "bad"}


def _period_caption(df):
    if df.empty:
        return
    st.caption(f"Analisi su {len(df)} giorni di dati "
               f"({df.index.min():%d/%m/%Y} → {df.index.max():%d/%m/%Y}).")


# =====================================================================
# 1. INSIGHT
# =====================================================================
@st.cache_data(ttl=3600, show_spinner="Cerco i tuoi schemi personali…")
def _insights(daily, acts):
    return A.find_insights(daily, acts)


def page_insights():
    st.title("Cosa ti fa stare bene")
    daily, acts = daily_year(), activities_long()
    _period_caption(daily)

    found = _insights(daily, acts)
    if not found:
        st.info("Ancora pochi dati per trovare schemi affidabili: servono almeno 3–4 settimane.")
        return

    with st.expander("Come funziona"):
        st.markdown(
            "Confronto i giorni in cui fai una cosa (allenarti tardi, andare a letto tardi, molti passi, "
            "stress alto…) con quelli in cui non la fai, e guardo come cambiano sonno, HRV, FC a riposo e "
            "Body Battery **la notte o il giorno dopo**.\n\n"
            "Mostro solo le differenze **statisticamente solide** (test di permutazione, p < 0.1, effetto "
            "almeno medio). *Forte / chiaro / probabile* indica quanto è affidabile.\n\n"
            "⚠️ È una correlazione, non per forza una causa: ad esempio i giorni di stress alto potrebbero "
            "essere anche quelli in cui dormi meno.")

    good = [i for i in found if i.good]
    bad = [i for i in found if not i.good]
    l, r = st.columns(2)
    for col, items, title, tone in ((l, good, "Ti fa bene", "good"), (r, bad, "Ti penalizza", "bad")):
        with col:
            st.subheader(title)
            if not items:
                st.caption("Nessuno schema trovato.")
            for i in items[:6]:
                card(f'<div class="g-big">{i.text}</div>'
                     f'<div class="g-small">{i.detail}</div>'
                     f'{pill(A.strength_label(i), tone)}', tone)

    st.subheader("Guarda i dati")
    labels = [i.text for i in found]
    pick = st.selectbox("Schema", labels, label_visibility="collapsed")
    i = found[labels.index(pick)]
    unit = A.OUTCOMES[i.outcome][2]
    df = pd.DataFrame({"valore": i.values_a + i.values_b,
                       "gruppo": [f"Quando {i.label_a}"] * len(i.values_a) + [f"Quando {i.label_b}"] * len(i.values_b)})
    fig = px.strip(df, x="gruppo", y="valore", color="gruppo", stripmode="overlay")
    fig.update_traces(marker=dict(size=8, opacity=0.55), jitter=0.35)
    for k, (vals, color) in enumerate(((i.values_a, TONE_COLOR["good" if i.good else "bad"]),
                                       (i.values_b, TONE_COLOR["neutral"]))):
        fig.add_shape(type="line", x0=k - 0.3, x1=k + 0.3, y0=np.mean(vals), y1=np.mean(vals),
                      line=dict(color=color, width=4))
    chart(fig, height=380, showlegend=False, yaxis_title=A.OUTCOMES[i.outcome][1] + (f" ({unit})" if unit else ""),
          title="Ogni punto è un giorno · la linea è la media")


# =====================================================================
# 2. ALLERTE SALUTE
# =====================================================================
def page_alerts():
    st.title("Allerte salute")
    daily = daily_year()
    base = A.baselines(daily)
    if base.empty or len(daily) < 21:
        st.info("Servono almeno 3 settimane di dati per conoscere il tuo \"normale\".")
        return
    days = A.alert_days(base)
    today = days.index[-1]
    level = days.at[today, "level"]
    msgs = A.alert_messages(base, today)

    titles = {
        "ok": "Tutto nella norma",
        "lieve": "Un valore fuori dal solito",
        "attenzione": "Attenzione: più segnali insieme",
        "allerta": "Allerta: segnali di stress fisico da 2 giorni",
    }
    advice = {
        "ok": "I tuoi parametri notturni sono in linea con le ultime 4 settimane.",
        "lieve": "Un solo segnale isolato di solito non significa nulla. Da tenere d'occhio.",
        "attenzione": "Più parametri si sono spostati nella direzione sbagliata. Può essere fatica, "
                      "poco sonno, alcol, o l'inizio di un malanno. Valuta un giorno leggero.",
        "allerta": "Questo schema compare spesso 1–2 giorni prima di un raffreddore o in caso di "
                   "sovraccarico. Meglio riposo o allenamento molto leggero oggi.",
    }
    tone = LEVEL_TONE[level]
    body = "".join(f"<li>{m}</li>" for m in msgs)
    card(f'<div class="g-eyebrow">Oggi · {today:%d/%m}</div><div class="g-hero">{titles[level]}</div>'
         f'<div class="g-small">{advice[level]}</div>' + (f"<ul>{body}</ul>" if body else ""), tone)

    st.caption("Il tuo \"normale\" è la media delle 4 settimane precedenti (esclusi gli ultimi 3 giorni). "
               "Un valore è segnalato se si discosta di oltre 1,5 deviazioni standard nella direzione "
               "sfavorevole. Non è un dispositivo medico.")

    st.subheader("Ultimi 60 giorni rispetto al tuo normale")
    recent = base[base.index > today - pd.Timedelta(days=60)]
    metrics = [m for m in A.ALERT_METRICS if (m, "value") in recent and recent[(m, "value")].notna().any()]
    cols = st.columns(2)
    for k, m in enumerate(metrics):
        label, unit, sign = A.ALERT_METRICS[m]
        v, mu, sd, z = (recent[(m, x)] for x in ("value", "mean", "std", "z"))
        fig = go.Figure()
        fig.add_scatter(x=recent.index, y=mu + 1.5 * sd, mode="lines", line=dict(width=0), showlegend=False,
                        hoverinfo="skip")
        fig.add_scatter(x=recent.index, y=mu - 1.5 * sd, mode="lines", line=dict(width=0), fill="tonexty",
                        fillcolor="rgba(125,211,252,0.12)", name="Il tuo normale", hoverinfo="skip")
        fig.add_scatter(x=recent.index, y=mu, mode="lines", line=dict(color="rgba(125,211,252,0.5)", dash="dot",
                                                                      width=1.5), name="Media")
        fig.add_scatter(x=recent.index, y=v, mode="lines+markers", name=label, line=dict(color="#E6ECFF", width=2),
                        marker=dict(size=5))
        out = z >= 1.5
        fig.add_scatter(x=recent.index[out], y=v[out], mode="markers", name="Fuori norma",
                        marker=dict(size=11, color=TONE_COLOR["bad"], line=dict(width=2, color="#0A1433")))
        chart(fig, cols[k % 2], 260, title=f"{label}" + (f" ({unit})" if unit else ""), showlegend=False)

    past = days[days["level"].isin(["attenzione", "allerta"])].iloc[::-1]
    if not past.empty:
        st.subheader("Storico segnalazioni")
        names = {m: A.ALERT_METRICS[m][0] for m in A.ALERT_METRICS}
        st.dataframe(pd.DataFrame({
            "Giorno": past.index.strftime("%a %d/%m/%Y"),
            "Livello": past["level"].str.capitalize(),
            "Segnali": past["flags"].apply(lambda f: ", ".join(names[m] for m in f)),
        }), hide_index=True, width="stretch")
        st.caption("Ti ricordi come stavi in quei giorni? È il modo migliore per capire quanto ti puoi fidare "
                   "di questi segnali.")


# =====================================================================
# 3. CARICO E FORMA
# =====================================================================
def page_load():
    st.title("Carico e forma")
    start, end = year_window()
    acts = activities_long()
    load = A.daily_load(acts, start, end)
    if load.sum() == 0:
        st.info("Nessun allenamento con carico nel periodo.")
        return
    first = acts["start"].min().normalize() if not acts.empty else load.index[0]
    rest = pd.Series(0.0, index=pd.date_range(end + timedelta(days=1), periods=14, freq="D"))
    p = A.pmc(load, rest)
    p = p[p.index >= first]
    now = p[~p["future"]].iloc[-1]
    zone, zone_text = A.form_zone(now["tsb"])
    ramp = A.ramp_rate(p)

    c = st.columns(4)
    c[0].metric("Forma fisica", f"{now['ctl']:.0f}", delta=f"{ramp:+.1f} in 7 giorni",
                help="CTL: media del carico degli ultimi ~42 giorni. Sale lentamente se ti alleni con costanza.")
    c[1].metric("Fatica", f"{now['atl']:.0f}", help="ATL: media del carico degli ultimi ~7 giorni.")
    c[2].metric("Freschezza", f"{now['tsb']:+.0f}", help="TSB = forma − fatica (di ieri). Positiva = riposato.")
    c[3].metric("Stato", zone)
    tone = {"Sovraccarico": "bad", "Costruzione": "neutral", "Mantenimento": "neutral", "Fresco": "good",
            "Scarico": "warn"}.get(zone, "neutral")
    msg = zone_text
    if ramp > 8:
        msg += " La forma sta salendo molto in fretta (> 8 punti a settimana): attenzione agli infortuni."
        tone = "warn"
    card(f'<div class="g-big">{zone}</div><div class="g-small">{msg}</div>', tone)

    past, fut = p[~p["future"]], p[p["future"]]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.62, 0.38], vertical_spacing=0.06)
    fig.add_scatter(x=past.index, y=past["ctl"], name="Forma (CTL)", line=dict(color="#7DD3FC", width=3), row=1, col=1)
    fig.add_scatter(x=past.index, y=past["atl"], name="Fatica (ATL)", line=dict(color="#F9A8D4", width=1.8), row=1, col=1)
    fig.add_scatter(x=fut.index, y=fut["ctl"], name="Se ti riposi 2 settimane", line=dict(color="#7DD3FC", dash="dot"),
                    row=1, col=1)
    fig.add_scatter(x=fut.index, y=fut["atl"], showlegend=False, line=dict(color="#F9A8D4", dash="dot", width=1.5),
                    row=1, col=1)
    colors = ["#FCA5A5" if v < -30 else "#A78BFA" if v < -10 else "#7DD3FC" if v < 5 else "#5EEAD4" if v < 25
              else "#FCD34D" for v in p["tsb"].fillna(0)]
    fig.add_bar(x=p.index, y=p["tsb"], marker_color=colors, name="Freschezza (TSB)",
                marker_opacity=[0.45 if f else 0.9 for f in p["future"]], row=2, col=1)
    fig.add_vline(x=pd.Timestamp(end), line_dash="dot", line_color="rgba(255,255,255,0.3)")
    fig.update_yaxes(title_text="carico", row=1, col=1)
    fig.update_yaxes(title_text="freschezza", row=2, col=1)
    chart(fig, height=520, title="Forma, fatica e freschezza (tratteggiato: proiezione se ti fermi)")

    with st.expander("Come leggere il grafico"):
        st.markdown(
            "È il modello di **Banister** (usato da TrainingPeaks, il *Performance Management Chart*), "
            "calcolato con il *carico allenamento* che Garmin dà a ogni attività.\n\n"
            "- **Forma (CTL)**: quanto sei allenato. Sale piano piano con la costanza.\n"
            "- **Fatica (ATL)**: quanto sei stanco adesso. Sale e scende in fretta.\n"
            "- **Freschezza (TSB)**: la differenza. Molto negativa = stai costruendo ma sei cotto; "
            "tra +5 e +25 = sei fresco, il momento ideale per gareggiare.\n\n"
            "Le zone sono indicative: sono tarate sul TSS di TrainingPeaks, e il carico Garmin ha una scala "
            "simile ma non identica.")

    st.subheader("Carico settimanale")
    wk = load[load.index >= first].resample("W-MON", label="left", closed="left").sum()
    fig = px.bar(wk, title=None)
    fig.add_scatter(x=wk.index, y=wk.rolling(4, min_periods=1).mean(), mode="lines", name="Media 4 settimane",
                    line=dict(color="#FCD34D", width=2))
    chart(fig, height=280, showlegend=False)


# =====================================================================
# 4. EFFICIENZA AEROBICA
# =====================================================================
def _pace_axis(fig):
    """Asse Y in min:ss/km, con i più veloci in alto."""
    fig.update_yaxes(autorange="reversed", tickformat="%M:%S", title_text="min/km")
    return fig


def _as_time(sec_per_km):
    return pd.to_datetime(np.asarray(sec_per_km, float), unit="s")


def page_efficiency():
    st.title("Efficienza aerobica")
    st.caption("A parità di battiti, quanto vai veloce? Misurato solo sui tratti a ritmo costante, "
               "con la velocità corretta per la pendenza e al netto del caldo.")

    acts = activities_long()
    runs = acts[acts["type"].isin(A.RUN_TYPES)] if not acts.empty else acts
    if runs.empty:
        st.info("Nessuna corsa trovata.")
        return
    profiles = run_profiles(tuple(runs["id"]))

    all_hr = [hr for p in profiles.values() if p.get("gps") for hr, _ in p["windows"]]
    aerobic = [h for h in all_hr if 140 <= h <= 175]
    default = int(5 * round(np.median(aerobic) / 5)) if aerobic else 155
    ref = st.slider("Frequenza cardiaca di riferimento", 130, 185, default, step=1,
                    help="Scegli una FC della tua zona aerobica (corse facili / medie). Sopra la soglia la FC non "
                         "sale più in proporzione alla velocità, e il confronto perde senso.")

    m = A.efficiency_model(runs, profiles, ref)
    per = m["runs"]
    if per.empty or len(per) < 5:
        st.info(f"Troppi pochi tratti stabili intorno a {ref} bpm. Prova una FC di riferimento vicina a quella "
                "delle tue corse facili.")
        return

    # --- confronto nel tempo ---
    trend = A.efficiency_trend(per)
    names = {180: "6 mesi fa", 90: "3 mesi fa", 0: "Ultime 6 settimane"}
    if trend:
        now = trend[-1]
        # due righe: al netto del meteo e dati grezzi, così si vede anche quanto pesa il caldo
        for key, row_title, row_help in (
                ("pace", "Al netto del meteo", "Come se avessi corso sempre in condizioni fresche."),
                ("pace_raw", "Dati grezzi, senza correzione", "Così come sono, con il caldo di quei giorni.")):
            st.markdown(f'<div class="g-eyebrow" style="margin-top:6px">{row_title}</div>', unsafe_allow_html=True)
            c = st.columns(len(trend))
            for col, t in zip(c, trend):
                delta = None
                if t["days_ago"]:
                    diff = now[key] - t[key]
                    delta = f"{'-' if diff < 0 else '+'}{abs(diff):.0f} s/km da allora"
                col.metric(f"{names[t['days_ago']]} · {ref} bpm", pace(t[key]), delta=delta, delta_color="inverse",
                           help=f"Mediana di {t['n']} corse. {row_help}")

        if len(trend) > 1:
            first = trend[0]
            when = names[first["days_ago"]].lower()

            def verdict(diff):
                if abs(diff) < 6:
                    return "alla stessa velocità"
                return f"{abs(diff):.0f} s/km {'più veloce' if diff > 0 else 'più lento'}"

            diff = first["pace"] - now["pace"]           # > 0 = oggi più veloce
            raw_diff = first["pace_raw"] - now["pace_raw"]
            weather = raw_diff - diff                     # quanto della differenza grezza è meteo
            tone = "neutral" if abs(diff) < 6 else ("good" if diff > 0 else "bad")
            head = f"A {ref} bpm oggi vai {verdict(diff)} rispetto a {when}, al netto del meteo"
            sub = (f"Senza correzione: {verdict(raw_diff)}. ")
            if abs(weather) >= 6:
                sub += (f"Quindi circa {abs(weather):.0f} s/km della differenza sono dovuti al meteo "
                        f"({'condizioni più fresche' if weather > 0 else 'condizioni più calde'} oggi rispetto ad "
                        f"allora), il resto è forma vera.")
            else:
                sub += "Il meteo era simile, quindi i due confronti coincidono."
            if abs(diff) >= 6 and diff < 0:
                sub += " Il calo può essere stanchezza accumulata, poco volume facile, o un periodo di stop."
            card(f'<div class="g-big">{head}</div><div class="g-small">{sub}</div>', tone)

    # --- grafico ---
    per = per.copy()
    roll = per.set_index("date")
    per["trend"] = roll["pace_adj"].rolling("42D", min_periods=3).median().values
    per["trend_raw"] = roll["pace_raw"].rolling("42D", min_periods=3).median().values
    custom = np.stack([per["name"], per["n"] * A.STEP_S / 60, per["temp"], per["dew"]], axis=1)
    hover = ("%{customdata[0]}<br>%{y|%M:%S}/km a " + str(ref) + " bpm (LABEL)<br>%{customdata[1]:.0f} min di tratti "
             "stabili<br>%{customdata[2]:.0f}°C, rugiada %{customdata[3]:.0f}°C<extra></extra>")
    fig = go.Figure()
    fig.add_scatter(x=per["date"], y=_as_time(per["pace_raw"]), mode="markers", name="Corsa, grezzo",
                    marker=dict(size=8, color="rgba(255,255,255,0)", line=dict(color="rgba(201,212,245,0.5)", width=1.2)),
                    customdata=custom, hovertemplate=hover.replace("LABEL", "grezzo"))
    fig.add_scatter(x=per["date"], y=_as_time(per["pace_adj"]), mode="markers", name="Corsa, al netto del meteo",
                    marker=dict(size=9, color=per["temp"], colorscale=[[0, "#7DD3FC"], [0.5, "#FCD34D"], [1, "#FCA5A5"]],
                                cmin=10, cmax=32, showscale=True,
                                colorbar=dict(title="°C", thickness=10, len=0.6, outlinewidth=0)),
                    customdata=custom, hovertemplate=hover.replace("LABEL", "al netto del meteo"))
    fig.add_scatter(x=per["date"], y=_as_time(per["trend_raw"]), mode="lines", name="Tendenza grezza",
                    line=dict(color="rgba(201,212,245,0.7)", width=2, dash="dash"))
    fig.add_scatter(x=per["date"], y=_as_time(per["trend"]), mode="lines", name="Tendenza al netto del meteo",
                    line=dict(color="#5EEAD4", width=3))
    chart(_pace_axis(fig), height=440, title=f"Passo a {ref} bpm, corsa per corsa (più in alto = più efficiente)")
    st.caption("Lo spazio tra la linea tratteggiata e quella piena è quanto ti è costato il meteo in quel periodo.")

    if m.get("heat_coef"):
        ref_sp = float(per["sp_adj"].median())
        c1 = A.heat_cost(m["heat_coef"], ref_sp, 24, 18)
        c2 = A.heat_cost(m["heat_coef"], ref_sp, 30, 22)
        card(f'<div class="g-eyebrow">Quanto ti costa il caldo</div>'
             f'<div class="g-big">A parità di FC perdi circa {c1:.0f} s/km a 24°C con afa, {c2:.0f} s/km a 30°C</div>'
             f'<div class="g-small">Stimato sulle tue corse confrontando giornate fresche e calde '
             f'(uso temperatura + punto di rugiada della stazione meteo più vicina, non il sensore al polso).</div>',
             "warn")

    if m.get("n_no_gps"):
        st.caption(f"Escluse {m['n_no_gps']} corse senza GPS (tapis roulant o orologio senza GPS): lì la velocità "
                   "è stimata dal movimento del polso e non è affidabile per questo calcolo.")

    # --- disaccoppiamento ---
    st.subheader("Disaccoppiamento aerobico")
    st.caption("Sulle corse di almeno un'ora a ritmo costante: di quanto peggiora il rapporto velocità/FC tra la prima e la "
               "seconda metà. Sotto il 5% la tua base aerobica regge quella durata.")
    dec = []
    for _, r in runs.iterrows():
        d = (profiles.get(r["id"]) or {}).get("decoupling")
        if A.decoupling_valid(d):
            dec.append({"date": r["start"], "name": r["name"], "km": r["distance_km"], **d})
    if not dec:
        st.info("Nessuna corsa di almeno 60 minuti a ritmo costante.")
    else:
        dd = pd.DataFrame(dec).sort_values("date")
        last = dd.iloc[-1]
        ok = last["pct"] < 5
        card(f'<div class="g-eyebrow">Ultimo lungo · {last["date"]:%d/%m} · {last["km"]:.1f} km · {last["minutes"]:.0f} min</div>'
             f'<div class="g-hero">{last["pct"]:.1f}%</div>'
             f'<div class="g-small">Prima metà {pace(last["pace1"])} a {last["hr1"]:.0f} bpm, seconda metà '
             f'{pace(last["pace2"])} a {last["hr2"]:.0f} bpm. '
             + ("La base aerobica regge bene questa durata." if ok else
                "Il cuore ha dovuto lavorare sempre di più per tenere il ritmo: per questa durata serve "
                "ancora volume facile (o faceva caldo, o sei partito troppo forte).") + "</div>",
             "good" if ok else ("warn" if last["pct"] < 8 else "bad"))
        colors = ["#5EEAD4" if v < 5 else "#FCD34D" if v < 8 else "#FCA5A5" for v in dd["pct"]]
        fig = go.Figure(go.Bar(x=dd["date"], y=dd["pct"], marker_color=colors,
                               customdata=np.stack([dd["name"], dd["km"], dd["minutes"]], axis=1),
                               hovertemplate="%{customdata[0]}<br>%{customdata[1]:.1f} km · %{customdata[2]:.0f} min"
                                             "<br>%{y:.1f}%<extra></extra>"))
        fig.add_hline(y=5, line_dash="dot", line_color="rgba(255,255,255,0.4)", annotation_text="5%",
                      annotation_position="top left")
        chart(fig, height=300, yaxis_title="%")

    with st.expander("Come funziona, nel dettaglio"):
        st.markdown(
            f"1. Per ogni corsa scarico i dati **secondo per secondo** (FC e velocità corretta per la pendenza).\n"
            f"2. Salto i primi 8 minuti e cerco tratti di **2 minuti** in cui il ritmo varia meno del 6% e la FC "
            f"meno di 10 bpm, con la FC sfasata di 30 s (risponde in ritardo allo sforzo). In un 5x1000 restano "
            f"solo le prove; riscaldamento, recuperi e defaticamento vengono scartati.\n"
            f"3. Tengo solo i tratti tra **{ref - 8} e {ref + 8} bpm** e li riporto esattamente a {ref} bpm con la "
            f"tua relazione velocità/FC ({m['slope'] * 3.6:.2f} km/h ogni bpm).\n"
            f"4. Stimo quanto ti rallenta il caldo (temperatura + punto di rugiada) confrontando giornate diverse, "
            f"e lo tolgo.\n"
            f"5. Ogni punto del grafico è la mediana dei tratti di una corsa; la linea è la mediana mobile su "
            f"6 settimane.")


# =====================================================================
# 5. GARA OBIETTIVO
# =====================================================================
DIST_KM = {label: km for label, km in gd.RACE_DISTANCES.values()}


def page_race():
    st.title("Gara obiettivo")
    settings = gd.load_settings()
    race = settings.get("race", {})

    with st.expander("Imposta la gara", expanded=not race):
        with st.form("race"):
            c = st.columns([2, 1, 1, 1])
            name = c[0].text_input("Nome", race.get("name", ""), placeholder="Es. Mezza di Milano")
            dist = c[1].selectbox("Distanza", list(DIST_KM), index=list(DIST_KM).index(race.get("distance", "Mezza")))
            day = c[2].date_input("Data", value=date.fromisoformat(race["date"]) if race.get("date")
                                  else date.today() + timedelta(days=60), min_value=date.today(), format="DD/MM/YYYY")
            goal = c[3].text_input("Tempo obiettivo", race.get("goal", ""), placeholder="Es. 1:45:00")
            if st.form_submit_button("Salva", type="primary"):
                if A.parse_time(goal) is None:
                    st.error("Tempo non valido. Scrivilo come 1:45:00, 45:30 o 1h45.")
                else:
                    settings["race"] = {"name": name or dist, "distance": dist, "date": day.isoformat(), "goal": goal}
                    gd.save_settings(settings)
                    st.rerun()
    if not race:
        st.info("Imposta una gara qui sopra per vedere quanto sei vicino all'obiettivo.")
        return

    dist, km = race["distance"], DIST_KM[race["distance"]]
    race_day = date.fromisoformat(race["date"])
    goal_s = A.parse_time(race["goal"])
    days_left = (race_day - date.today()).days

    fit, _ = fitness(*year_window())
    preds = fit["race"][dist].dropna() if dist in fit["race"] else pd.Series(dtype=float)
    current = fit["race_now"].get(dist) or (preds.iloc[-1] if not preds.empty else None)

    st.subheader(f"{race['name']} · {race_day:%d/%m/%Y}")
    c = st.columns(4)
    c[0].metric("Giorni mancanti", max(days_left, 0), help=f"{days_left // 7} settimane")
    c[1].metric("Obiettivo", hms(goal_s), help=f"Passo {pace(goal_s / km)}")
    c[2].metric("Previsione Garmin oggi", hms(current), help=f"Passo {pace(current / km) if current else '–'}")
    if current:
        gap = current - goal_s
        c[3].metric("Distanza dall'obiettivo", ("+" if gap > 0 else "-") + hms(gap) if abs(gap) >= 1 else "0:00",
                    delta=f"{pace(abs(gap) / km).replace('/km', '')} al km", delta_color="off")

    trend = A.prediction_trend(preds, days=60)
    projected = None
    if current and trend:
        slope, _ = trend
        projected = A.project_time(current, slope, days_left)
        weekly = slope * 7
        needed = (goal_s - current) / max(days_left / 7, 1)
        if projected <= goal_s:
            tone, head = "good", f"Al ritmo attuale arrivi in circa {hms(projected)}: obiettivo alla portata"
        elif current <= goal_s:
            tone, head = "good", "Sei già sotto l'obiettivo secondo Garmin: ora conta arrivarci fresco"
        else:
            tone, head = ("warn" if projected - goal_s < 0.03 * goal_s else "bad",
                          f"Al ritmo attuale arrivi in circa {hms(projected)}: mancano {hms(projected - goal_s)}")
        trend_txt = (f"Negli ultimi 60 giorni la previsione è {'migliorata' if weekly < 0 else 'peggiorata'} di "
                     f"{abs(weekly):.0f} s a settimana.")
        need_txt = (f" Per centrare l'obiettivo serve migliorare di {abs(needed):.0f} s a settimana."
                    if current > goal_s else "")
        card(f'<div class="g-big">{head}</div><div class="g-small">{trend_txt}{need_txt} La proiezione assume '
             f'che il miglioramento rallenti col tempo, come succede quasi sempre.</div>', tone)
    elif not current:
        st.info("Garmin non ha ancora una previsione per questa distanza: servono alcune corse con il cardio.")

    if not preds.empty:
        fig = go.Figure()
        fig.add_scatter(x=preds.index, y=preds / 60, name="Previsione Garmin", line=dict(color="#7DD3FC", width=3))
        if projected and days_left > 0:
            xs = pd.date_range(date.today(), race_day, freq="D")
            ys = [A.project_time(current, trend[0], (x.date() - date.today()).days) / 60 for x in xs]
            fig.add_scatter(x=xs, y=ys, name="Proiezione", line=dict(color="#7DD3FC", dash="dot"))
        fig.add_hline(y=goal_s / 60, line_color="#5EEAD4", line_dash="dash",
                      annotation_text=f"Obiettivo {hms(goal_s)}", annotation_position="top left")
        fig.add_vline(x=pd.Timestamp(race_day), line_color="rgba(255,255,255,0.35)", line_dash="dot")
        fig.update_yaxes(autorange="reversed", title_text="minuti")
        chart(fig, height=380, title=f"Previsione {dist} nel tempo (più in alto = più veloce)")

    if days_left > 0:
        st.subheader("Quando scaricare")
        start, end = year_window()
        load = A.daily_load(activities_long(), start, end)
        plan = A.taper_plan(load, race_day, dist)
        if plan:
            zone, _ = A.form_zone(plan["race_tsb"])
            tone = "good" if 5 <= plan["race_tsb"] <= 25 else "warn"
            card(f'<div class="g-big">Inizia lo scarico {_it_date(plan["taper_start"])}</div>'
                 f'<div class="g-small">Se continui con il tuo carico medio attuale ({plan["avg_load"]:.0f} al giorno) '
                 f'e negli ultimi {plan["taper_days"]} giorni lo dimezzi, arrivi alla gara con freschezza '
                 f'<b>{plan["race_tsb"]:+.0f}</b> ({zone.lower()}) e forma {plan["race_ctl"]:.0f}. '
                 f'L\'ideale per gareggiare è tra +5 e +25.</div>', tone)
            pp = plan["pmc"]
            pp = pp[pp.index >= pd.Timestamp(date.today()) - pd.Timedelta(days=42)]
            fig = go.Figure()
            fig.add_scatter(x=pp.index, y=pp["ctl"], name="Forma", line=dict(color="#7DD3FC", width=3))
            fig.add_scatter(x=pp.index, y=pp["tsb"], name="Freschezza", line=dict(color="#5EEAD4", width=2))
            fig.add_hrect(y0=5, y1=25, fillcolor="rgba(94,234,212,0.08)", line_width=0)
            fig.add_vrect(x0=pd.Timestamp(plan["taper_start"]), x1=pd.Timestamp(race_day),
                          fillcolor="rgba(252,211,77,0.08)", line_width=0, annotation_text="scarico",
                          annotation_position="top left")
            fig.add_vline(x=pd.Timestamp(date.today()), line_dash="dot", line_color="rgba(255,255,255,0.3)")
            chart(fig, height=320, title="Simulazione fino al giorno della gara", legend_title=None)


# =====================================================================
# 6. CALENDARIO E RECORD
# =====================================================================


def _fmt_record(row) -> str:
    v, kind = row["value"], row["kind"]
    if pd.isna(v):
        return "–"
    if kind == "time":
        return hms(v)
    if kind == "dist":
        return f"{v / 1000:.2f} km"
    if kind == "m":
        return f"{v:.0f} m"
    if kind == "days":
        return f"{v:.0f} giorni"
    return f"{v:,.0f}".replace(",", ".")


def page_calendar():
    st.title("Calendario e record")
    daily, acts = daily_year(), activities_long()
    today = date.today()

    # --- heatmap ---
    metric = st.segmented_control("Mostra", ["Allenamento", "Passi", "Sleep score"], default="Allenamento")
    if metric == "Allenamento":
        vals = (acts.groupby(acts["start"].dt.normalize())["duration_min"].sum() if not acts.empty
                else pd.Series(dtype=float))
        unit, scale = "min", [[0, "rgba(125,211,252,0.06)"], [0.01, "#1E3A6B"], [0.5, "#3B82C4"], [1, "#7DD3FC"]]
    elif metric == "Passi":
        vals, unit = daily["steps"], "passi"
        scale = [[0, "rgba(94,234,212,0.06)"], [0.01, "#134E4A"], [0.5, "#2BA597"], [1, "#5EEAD4"]]
    else:
        vals, unit = daily["sleep_score"], "punti"
        scale = [[0, "rgba(167,139,250,0.06)"], [0.01, "#3B2A6B"], [0.5, "#7458C4"], [1, "#C4B5FD"]]
    grid = A.calendar_grid(vals, today)
    z = grid.pivot(index="weekday", columns="week", values="value")
    d = grid.pivot(index="weekday", columns="week", values="date")
    text = d.map(lambda x: x.strftime("%a %d/%m/%Y") if pd.notna(x) else "")
    fig = go.Figure(go.Heatmap(
        z=z.fillna(0 if metric == "Allenamento" else np.nan).values, x=z.columns,
        y=["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"], customdata=text.values,
        colorscale=scale, xgap=3, ygap=3, showscale=False,
        hovertemplate="%{customdata}<br>%{z:.0f} " + unit + "<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(showgrid=False, dtick="M1", tickformat="%b")
    chart(fig, height=230, margin=dict(t=10, b=10, l=10, r=10))

    # --- serie ---
    days_idx = pd.date_range(daily.index.min(), pd.Timestamp(today), freq="D")
    trained = pd.Series(False, index=days_idx)
    if not acts.empty:
        trained |= pd.Series(True, index=acts["start"].dt.normalize().unique()).reindex(days_idx, fill_value=False)
    goal_hit = (daily["steps"] >= daily["step_goal"]).reindex(days_idx)
    week_trained = trained.resample("W-MON", label="left", closed="left").sum() > 0
    cur_t, best_t = A.streaks(trained)
    cur_s, best_s = A.streaks(goal_hit)
    cur_w, best_w = A.streaks(week_trained)
    c = st.columns(3)
    c[0].metric("Settimane di fila con allenamento", cur_w, help=f"Record: {best_w}")
    c[1].metric("Giorni di fila con allenamento", cur_t, help=f"Record: {best_t}")
    c[2].metric("Giorni di fila obiettivo passi", cur_s, help=f"Record: {best_s}")

    # --- confronto mesi / anni ---
    st.subheader("Mese per mese")
    if not acts.empty:
        a = acts.copy()
        a["year"], a["month"] = a["start"].dt.year, a["start"].dt.month
        a["run_km"] = np.where(a["type"].isin(A.RUN_TYPES), a["distance_km"].fillna(0), 0)
        m = a.groupby(["year", "month"]).agg(ore=("duration_min", lambda x: x.sum() / 60), km=("run_km", "sum"),
                                             n=("id", "count")).reset_index()
        m["mese"] = m["month"].map(lambda x: MONTHS[x - 1])
        years = sorted(m["year"].unique())
        what = st.segmented_control("Misura", ["Ore di allenamento", "Km di corsa", "Allenamenti"],
                                    default="Ore di allenamento")
        col = {"Ore di allenamento": "ore", "Km di corsa": "km", "Allenamenti": "n"}[what or "Ore di allenamento"]
        fig = px.bar(m, x="mese", y=col, color=m["year"].astype(str), barmode="group",
                     category_orders={"mese": MONTHS})
        chart(fig, height=320, legend_title=None)

        this = a[(a["year"] == today.year) & (a["month"] == today.month)]
        prev_m = (today.replace(day=1) - timedelta(days=1))
        prev = a[(a["year"] == prev_m.year) & (a["month"] == prev_m.month) & (a["start"].dt.day <= today.day)]
        last_y = a[(a["year"] == today.year - 1) & (a["month"] == today.month) & (a["start"].dt.day <= today.day)]
        c = st.columns(3)
        c[0].metric(f"{MONTHS[today.month - 1]} finora", f"{this['duration_min'].sum() / 60:.1f} h",
                    delta=f"{(this['duration_min'].sum() - prev['duration_min'].sum()) / 60:+.1f} h vs "
                          f"{MONTHS[prev_m.month - 1]} allo stesso giorno")
        c[1].metric("Km di corsa nel mese", f"{this['run_km'].sum():.0f} km",
                    delta=f"{this['run_km'].sum() - prev['run_km'].sum():+.0f} km")
        if len(years) > 1 and not last_y.empty:
            c[2].metric(f"vs {MONTHS[today.month - 1]} {today.year - 1}", f"{len(this)} allenamenti",
                        delta=f"{len(this) - len(last_y):+d}")
        else:
            first = a["start"].min()
            c[2].metric("Confronto con l'anno scorso", "–",
                        help=f"I tuoi dati partono da {MONTHS[first.month - 1]} {first.year}: il confronto "
                             f"anno su anno sarà disponibile da {MONTHS[first.month - 1]} {first.year + 1}.")

    # --- record ---
    st.subheader("Record personali")
    rec = records()
    if rec.empty:
        st.info("Nessun record personale disponibile.")
    else:
        rec = rec[rec["label"] != ""]
        cols = st.columns(4)
        for k, (_, row) in enumerate(rec.iterrows()):
            recent = pd.notna(row["date"]) and row["date"] >= pd.Timestamp(today) - pd.Timedelta(days=30)
            when = f"{row['date']:%d/%m/%Y}" if pd.notna(row["date"]) else ""
            where = f" · {row['activity']}" if row["activity"] else ""
            with cols[k % 4]:
                card(f'<div class="g-eyebrow">{row["label"]}</div><div class="g-hero">{_fmt_record(row)}</div>'
                     f'<div class="g-small">{when}{where}</div>' + (pill("nuovo!", "good") if recent else ""),
                     "good" if recent else "neutral")

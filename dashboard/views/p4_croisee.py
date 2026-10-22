import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import lake
import theme
import ui
from iot import analysis as A  # methodes de la partie 3 (detection des episodes)
from ui import fr, pct

ui.header(
    "Partie 4 – Analyse croisée",
    "Fusion des flux météo (Open-Meteo), pollution (OpenAQ) et mobilité (CityBikes) par ville et par heure",
    [
        "Existe-t-il une relation entre conditions météorologiques et pollution ?",
        "Les conditions météo influencent-elles l'utilisation des vélos urbains ?",
        "Peut-on identifier des conditions météorologiques favorables à la mobilité douce ?",
        "Existe-t-il des périodes où mobilité, pollution et météo interagissent fortement ?",
    ],
)
ui.data_status("Partie 4 – Analyse croisée")

f = lake.fused()
pol_raw = lake.load("pollution_horaire_ville")
if f is None or pol_raw is None:
    st.warning("La fusion nécessite meteo_horaire_ville, pollution_horaire_ville et network_timeseries dans data/.",
               icon=":material/folder_off:")
    st.stop()
h, d = f

TZ = "Europe/Paris"
MIN_BIKE_MIN = 30        # heure velo retenue si observee au moins 30 min (meme regle que la page Velos)
MIN_CLASS_H = 10         # Q3 : une classe meteo n'est interpretee qu'avec au moins 10 heures velo
LABELS = {"pm25": "PM2.5", "pm10": "PM10", "no2": "NO₂", "o3": "O₃", "co": "CO"}
POLS = [p for p in A.POLLUTANTS if p in h.columns]
W_HOURLY = {"temperature": "Température", "humidity": "Humidité", "wind_speed": "Vent", "precipitation": "Pluie",
            "pressure": "Pression", "cloud_cover": "Nébulosité"}
W_DAILY = {"temp_mean": "Température", "humidity_mean": "Humidité", "wind_mean": "Vent",
           "precipitation_sum": "Pluie", "pressure_mean": "Pression", "cloud_mean": "Nébulosité"}
DIVERGING = [[0, theme.SERIES[0]], [0.5, "#f0efec"], [1, "#e34948"]]   # bleu (r < 0) / gris / rouge (r > 0)
cities = [c for c in theme.CITY_COLORS if c in set(h["city"])]
h = h.assign(t=h["timestamp"].dt.tz_convert(TZ).dt.tz_localize(None))


@st.cache_data(show_spinner="Détection des épisodes…")
def episodes(g: pd.DataFrame) -> pd.DataFrame:
    return A.q4_episodes(g)[1]


def corr_heatmap(corr: pd.DataFrame, title: str, height: int = 380):
    text = corr.map(lambda v: "" if pd.isna(v) else fr(v, 2))
    fig = px.imshow(corr, zmin=-1, zmax=1, aspect="auto", color_continuous_scale=DIVERGING, title=title)
    fig.update_traces(text=text.values, texttemplate="%{text}", xgap=2, ygap=2,
                      hovertemplate="%{y} × %{x}<br>r = %{text}<extra></extra>")
    fig.update_layout(height=height, xaxis_title=None, yaxis_title=None,
                      coloraxis_colorbar=dict(title="r", tickvals=[-1, -0.5, 0, 0.5, 1]))
    return fig


def class_lines(df: pd.DataFrame, x: str, y: str, title: str, xtitle: str, ytitle: str):
    g = df.groupby(["city", x], observed=True)[y].agg(["mean", "size"]).reset_index()
    fig = px.line(g, x=x, y="mean", color="city", markers=True, custom_data=["size"],
                  color_discrete_map=theme.CITY_COLORS, category_orders={"city": cities}, title=title)
    fig.update_traces(line_width=2, marker_size=8,
                      hovertemplate="%{x} : %{y:.1f} µg/m³ (%{customdata[0]} h)<extra>%{fullData.name}</extra>")
    fig.update_layout(height=380, xaxis_title=xtitle, yaxis_title=ytitle, legend_title=None,
                      legend=dict(orientation="h", y=1.02, x=0, yanchor="bottom"))
    return fig, g


# --------------------------------------------------------------------- recouvrement des sources
wp = h["has_weather"] & h["has_pollution"]
bk = h[h["has_bikes"] & (h["bike_observed_min"] >= MIN_BIKE_MIN) & h["has_weather"]].copy()
bike_days = bk["date_local"].nunique()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Villes croisées", len(cities))
k2.metric("Heures météo × pollution", fr(wp.sum()))
k3.metric("Heures météo × vélos", fr(len(bk)), help=f"Heures vélo observées au moins {MIN_BIKE_MIN} min.")
k4.metric("Jours avec données vélo", bike_days)


def segments(flag: pd.Series, label: str) -> pd.DataFrame:
    ts = pd.Series(sorted(h.loc[flag, "t"].unique()))
    if ts.empty:
        return pd.DataFrame()
    grp = (ts.diff() != pd.Timedelta(hours=1)).cumsum()
    seg = ts.groupby(grp).agg(["min", "max"])
    return pd.DataFrame({"Source": label, "Début": seg["min"], "Fin": seg["max"] + pd.Timedelta(hours=1)})


cov = pd.concat([segments(h["has_weather"], "Météo (Open-Meteo)"), segments(h["has_pollution"], "Pollution (OpenAQ)"),
                 segments(h["has_bikes"], "Vélos (CityBikes)")])
fig = px.timeline(cov, x_start="Début", x_end="Fin", y="Source", color="Source",
                  color_discrete_sequence=theme.SERIES[:3], title="Périodes couvertes par chaque source")
fig.update_traces(hovertemplate="%{y}<br>%{base|%d/%m %Hh} → %{x|%d/%m %Hh}<extra></extra>")
fig.update_layout(height=230, showlegend=False, xaxis_title=None, yaxis_title=None, margin=dict(t=40, b=10))
fig.update_yaxes(autorange="reversed")
theme.show(fig)

if bike_days < 7:
    st.warning(f"**Données vélo très courtes** : {len(bk)} heures exploitables sur {bike_days} jour(s) "
               f"({', '.join(sorted(bk['date_local'].unique()))}). Les questions 2 et 3 sont traitées de façon "
               "**exploratoire** : les résultats ne permettent pas de conclure. La page se met à jour "
               "automatiquement quand un export vélo plus long est déposé dans `data/`.",
               icon=":material/science:")

q1, q2, q3, q4 = st.tabs(["Q1 · Météo et pollution", "Q2 · Météo et vélos", "Q3 · Conditions favorables",
                          "Q4 · Interactions"])

# --------------------------------------------------------------------- Q1
with q1:
    scale = st.radio("Échelle d'analyse", ["Journalière (écart à la moyenne de chaque ville)", "Horaire (valeurs brutes)"],
                     horizontal=True, key="q1_scale",
                     help="L'échelle journalière en écart à la moyenne de la ville neutralise le cycle jour/nuit "
                          "(qui fait varier ensemble température et ozone) et les différences entre villes.")
    if scale.startswith("Journalière"):
        dd = d[(d["weather_hours"] >= 18) & (d["pollution_hours"] >= 18)].copy()
        cols = list(W_DAILY) + [f"{p}_mean" for p in POLS]
        for c in cols:
            dd[c] = dd[c] - dd.groupby("city")[c].transform("mean")
        corr = dd[cols].corr().loc[list(W_DAILY), [f"{p}_mean" for p in POLS]]
        corr.index, corr.columns = list(W_DAILY.values()), [LABELS[p] for p in POLS]
        n_txt = f"{len(dd)} jours × ville complets (au moins 18 h de météo et de pollution)"
    else:
        x = h[wp]
        corr = x[list(W_HOURLY) + POLS].corr().loc[list(W_HOURLY), POLS]
        corr.index, corr.columns = list(W_HOURLY.values()), [LABELS[p] for p in POLS]
        n_txt = f"{fr(len(x))} heures × ville"
    theme.show(corr_heatmap(corr, f"Corrélation météo × polluants (Pearson, {n_txt})"))

    x = h[wp].copy()
    x["vent"] = pd.cut(x["wind_speed"], [0, 1.5, 3, 5, np.inf], right=False,
                       labels=["< 1,5", "1,5–3", "3–5", "≥ 5"])
    x["temp"] = pd.cut(x["temperature"], [-np.inf, 12, 16, 20, 24, np.inf], right=False,
                       labels=["< 12", "12–16", "16–20", "20–24", "≥ 24"])
    x["pluie"] = np.where(x["precipitation"] > 0, "Heures de pluie", "Heures sèches")
    a, b, c = st.columns(3)
    with a:
        fig, g_no2 = class_lines(x, "vent", "no2", "NO₂ selon la vitesse du vent", "Vent (m/s)", "NO₂ (µg/m³)")
        theme.show(fig)
    with b:
        fig, g_o3 = class_lines(x, "temp", "o3", "O₃ selon la température", "Température (°C)", "O₃ (µg/m³)")
        theme.show(fig)
    with c:
        g_pm = x.groupby(["city", "pluie"])["pm10"].agg(["mean", "size"]).reset_index()
        fig = px.bar(g_pm, x="city", y="mean", color="pluie", barmode="group", text="mean", custom_data=["size"],
                     category_orders={"city": cities, "pluie": ["Heures sèches", "Heures de pluie"]},
                     color_discrete_map={"Heures sèches": theme.SERIES[1], "Heures de pluie": theme.SERIES[0]},
                     title="PM10 par temps sec et sous la pluie")
        fig.update_traces(marker_cornerradius=4, texttemplate="%{y:.0f}", textposition="outside",
                          textfont_color=theme.INK_2, cliponaxis=False,
                          hovertemplate="%{x} : %{y:.1f} µg/m³ (%{customdata[0]} h)<extra>%{fullData.name}</extra>")
        fig.update_layout(height=380, xaxis_title=None, yaxis_title="PM10 (µg/m³)", legend_title=None, bargap=0.25,
                          legend=dict(orientation="h", y=1.02, x=0, yanchor="bottom"))
        theme.show(fig)

    def first_last(g: pd.DataFrame) -> pd.DataFrame:
        g = g[g["size"] >= 10]
        return g.groupby("city")["mean"].agg(first="first", last="last")

    fl_no2, fl_o3 = first_last(g_no2), first_last(g_o3)
    pm = g_pm.pivot(index="city", columns="pluie", values="mean").dropna()
    flat = corr.stack().sort_values(key=abs, ascending=False)
    txt = ("- Relations les plus marquées : " + " ; ".join(
        f"{w} × {p} (r = {fr(r, 2)})" for (w, p), r in flat.head(4).items()) + ".\n")
    dec = fl_no2[fl_no2["first"] > fl_no2["last"]]
    if len(fl_no2):
        txt += (f"- **Vent et NO₂** : dans {len(dec)} ville(s) sur {len(fl_no2)}, le NO₂ est plus faible par vent fort "
                f"que par vent faible (de {fr((dec['first'] / dec['last']).min(), 1)} à "
                f"{fr((dec['first'] / dec['last']).max(), 1)} fois moins) : le vent **disperse** les polluants "
                "émis localement par le trafic.\n")
    inc = fl_o3[fl_o3["last"] > fl_o3["first"]]
    if len(fl_o3):
        txt += (f"- **Température et O₃** : dans {len(inc)} ville(s) sur {len(fl_o3)}, l'ozone augmente avec la "
                f"température (jusqu'à {fr((inc['last'] / inc['first']).max(), 1)} fois plus au-delà de 24 °C) : "
                "l'O₃ se forme sous l'effet du soleil et de la chaleur.\n")
    if len(pm):
        lower = pm[pm["Heures de pluie"] < pm["Heures sèches"]]
        txt += (f"- **Pluie et particules** : les PM10 sont plus faibles sous la pluie dans {len(lower)} ville(s) sur "
                f"{len(pm)} (−{pct((1 - lower['Heures de pluie'] / lower['Heures sèches']).mean())} en moyenne) : "
                "la pluie lessive l'air. La corrélation reste proche de 0 car les heures de pluie sont rares "
                f"({pct((x['precipitation'] > 0).mean())} des heures).\n")
    no2_ok = len(fl_no2) and len(dec) > len(fl_no2) / 2
    o3_ok = len(fl_o3) and len(inc) > len(fl_o3) / 2
    if no2_ok and o3_ok:
        txt += ("- **Réponse** : oui, la météo pèse nettement sur la pollution, dans des sens opposés selon le "
                "polluant : un temps calme favorise l'accumulation du NO₂, un temps chaud et ensoleillé favorise l'ozone.")
    else:
        txt += ("- **Réponse** : les relations ne sont pas homogènes d'une ville à l'autre sur cette période ; "
                "voir les corrélations ci-dessus.")
    ui.reading(txt)

# --------------------------------------------------------------------- Q2
with q2:
    if bk.empty:
        st.info("Aucune heure vélo exploitable dans la période couverte par la météo.")
    else:
        bk["indice"] = bk["bike_movements_per_hour"] / bk.groupby("city")["bike_movements_per_hour"].transform("mean")
        st.markdown(f"Activité vélo (mouvements par heure) exprimée en **indice** : 1 = moyenne de la ville sur les "
                    f"heures observées, pour comparer Paris et Bordeaux sur la même échelle. "
                    f"{len(bk)} heures × ville exploitables.")
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                            subplot_titles=["Activité vélo (indice)", "Température (°C)", "Pluie (mm/h)"])
        for city in [c for c in cities if c in set(bk["city"])]:
            s = bk[bk["city"] == city].sort_values("t")
            for row, col, fmt in [(1, "indice", ".2f"), (2, "temperature", ".1f"), (3, "precipitation", ".1f")]:
                fig.add_scatter(x=s["t"], y=s[col], mode="lines+markers", name=city, legendgroup=city,
                                showlegend=row == 1, row=row, col=1,
                                line=dict(color=theme.city_color(city), width=2), marker_size=7,
                                hovertemplate=f"{city} · %{{x|%d/%m %Hh}} : %{{y:{fmt}}}<extra></extra>")
        fig.update_layout(height=560, hovermode="x unified", title="Activité vélo et météo, heure par heure",
                          legend=dict(orientation="h", y=1.06, x=0, yanchor="bottom"))
        fig.update_xaxes(tickformat="%d/%m %Hh")
        theme.show(fig)

        vars_ = {**W_HOURLY, "hour_local": "Heure de la journée"}
        r = pd.DataFrame({"variable": list(vars_.values()),
                          "r": [bk["indice"].corr(bk[c]) for c in vars_]}).dropna().sort_values("r")
        fig = px.bar(r, x="r", y="variable", orientation="h", text="r",
                     title=f"Corrélation avec l'activité vélo (n = {len(bk)} heures × ville)")
        fig.update_traces(marker_color=[theme.SERIES[0] if v < 0 else "#e34948" for v in r["r"]],
                          marker_cornerradius=4, texttemplate="%{x:+.2f}", textposition="outside",
                          textfont_color=theme.INK_2, cliponaxis=False,
                          hovertemplate="%{y} : r = %{x:+.2f}<extra></extra>")
        fig.update_layout(height=320, xaxis=dict(range=[-1, 1], title="r"), yaxis_title=None, bargap=0.4)
        fig.add_vline(x=0, line_color=theme.AXIS, line_width=1)
        theme.show(fig)

        rr = r.set_index("variable")["r"]
        best_w = rr.drop("Heure de la journée", errors="ignore").abs().idxmax()
        rain_h = int((bk["precipitation"] > 0).sum())
        txt = (f"- Données : {len(bk)} heures × ville sur {bike_days} jour(s), "
               f"{bk['hour_local'].min()}h à {bk['hour_local'].max()}h, {rain_h} heure(s) avec pluie.\n"
               f"- Variable météo la plus liée à l'activité : **{best_w.lower()}** (r = {fr(rr[best_w], 2)}), "
               f"mais l'activité suit aussi l'**heure de la journée** (r = {fr(rr.get('Heure de la journée', np.nan), 2)}).\n")
        with_hour = {W_HOURLY[c]: bk[c].corr(bk["hour_local"]) for c in W_HOURLY}
        moving = {k: v for k, v in with_hour.items() if pd.notna(v) and abs(v) >= 0.3}
        if moving:
            txt += ("- Plusieurs variables météo changent elles aussi au fil des heures observées ("
                    + ", ".join(f"{k.lower()} : r = {fr(v, 2)} avec l'heure" for k, v in moving.items())
                    + ") : on ne peut pas séparer l'effet de la météo de celui de l'heure.\n")
        if bike_days < 7:
            txt += ("- **Réponse provisoire** : les données ne permettent pas de conclure. Il faut plusieurs jours de "
                    "collecte, dont des jours de pluie et de semaine comme de week-end, pour comparer des heures "
                    "identiques sous des météos différentes.")
        else:
            txt += ("- Pour isoler l'effet météo, comparer à heure identique (onglet Q3) : les écarts d'activité entre "
                    "classes de météo y sont mesurés.")
        ui.reading(txt)

# --------------------------------------------------------------------- Q3
with q3:
    st.markdown("**A. Ce que montrent les données vélo** : activité moyenne (indice) selon la météo. "
                f"Une classe n'est interprétée qu'avec au moins {MIN_CLASS_H} heures de données.")
    if not bk.empty:
        bk["indice"] = bk["bike_movements_per_hour"] / bk.groupby("city")["bike_movements_per_hour"].transform("mean")
        classes = {
            "Température": pd.cut(bk["temperature"], [-np.inf, 10, 15, 20, 25, np.inf], right=False,
                                  labels=["< 10 °C", "10–15", "15–20", "20–25", "≥ 25 °C"]),
            "Pluie": pd.Series(np.where(bk["precipitation"] > 0, "Pluie", "Sec"), index=bk.index),
            "Vent": pd.cut(bk["wind_speed"], [0, 2, 4, 6, np.inf], right=False,
                           labels=["< 2 m/s", "2–4", "4–6", "≥ 6 m/s"]),
        }
        cols3 = st.columns(3)
        usable = {}
        for (name, cls), col in zip(classes.items(), cols3):
            g = bk.groupby(cls, observed=True)["indice"].agg(["mean", "size"]).reset_index()
            g.columns = ["classe", "mean", "size"]
            g["fiable"] = g["size"] >= MIN_CLASS_H
            usable[name] = g[g["fiable"]]
            fig = px.bar(g, x="classe", y="mean", text="size", custom_data=["size"], title=f"Selon : {name.lower()}")
            fig.update_traces(marker_color=[theme.SERIES[0] if ok else theme.OTHER for ok in g["fiable"]],
                              marker_cornerradius=4, texttemplate="%{text} h", textposition="outside",
                              textfont_color=theme.INK_2, cliponaxis=False,
                              hovertemplate="%{x} : indice %{y:.2f} (%{customdata[0]} h)<extra></extra>")
            fig.update_layout(height=320, xaxis_title=None, yaxis_title="Indice d'activité", bargap=0.35)
            fig.add_hline(y=1, line_dash="dot", line_color=theme.INK_2, line_width=1)
            with col:
                theme.show(fig)
        st.caption("Barres grises : moins de 10 heures de données, non interprétables. Ligne pointillée : activité moyenne.")

    st.markdown("**B. Fréquence des conditions favorables sur la période météo** : critères **à ajuster**. "
                "Ce sont des hypothèses, à confirmer avec la partie A quand les données vélo seront suffisantes.")
    c1, c2, c3, c4 = st.columns(4)
    t_rng = c1.slider("Température (°C)", -5, 40, (10, 25), key="q3_t")
    p_max = c2.slider("Pluie max (mm/h)", 0.0, 5.0, 0.0, 0.1, key="q3_p")
    w_max = c3.slider("Vent max (m/s)", 0.0, 15.0, 6.0, 0.5, key="q3_w")
    hrs = c4.slider("Heures de la journée", 0, 23, (7, 21), key="q3_h")
    day = h[h["has_weather"] & h["hour_local"].between(*hrs)].copy()
    ok_t = day["temperature"].between(*t_rng)
    ok_p = day["precipitation"] <= p_max
    ok_w = day["wind_speed"] <= w_max
    day["favorable"] = ok_t & ok_p & ok_w
    share = day.groupby(["city", "date_local"])["favorable"].mean().unstack().reindex(cities)
    fig = px.imshow(share, zmin=0, zmax=1, aspect="auto", color_continuous_scale=theme.SEQUENTIAL,
                    title=f"Part des heures favorables entre {hrs[0]}h et {hrs[1]}h, par jour")
    fig.update_traces(xgap=1, ygap=2, hovertemplate="%{y} · %{x} : %{z:.0%} des heures<extra></extra>")
    fig.update_layout(height=320, xaxis_title=None, yaxis_title=None,
                      coloraxis_colorbar=dict(title="Heures", tickformat=".0%"))
    theme.show(fig)

    by_city = day.groupby("city")["favorable"].mean().reindex(cities)
    fails = pd.Series({"température hors plage": (~ok_t).mean(), "pluie": (~ok_p).mean(), "vent": (~ok_w).mean()})
    txt = ""
    if not bk.empty:
        found = []
        for name, g in usable.items():
            if len(g) >= 2:
                best = g.loc[g["mean"].idxmax()]
                found.append(f"{name.lower()} : activité la plus forte pour « {best['classe']} » (indice {fr(best['mean'], 2)})")
        txt += ("- Données vélo : " + ("; ".join(found) + ".\n" if found else
                "aucune variable n'a au moins deux classes suffisamment remplies pour comparer : "
                "pas de conclusion possible avec l'export actuel.\n"))
    txt += (f"- Avec les critères choisis, les heures favorables représentent **{pct(day['favorable'].mean())}** des "
            f"heures de journée ; ville la plus favorable : **{by_city.idxmax()}** ({pct(by_city.max())}), "
            f"la moins favorable : **{by_city.idxmin()}** ({pct(by_city.min())}).\n"
            f"- Critère le plus souvent bloquant : **{fails.idxmax()}** ({pct(fails.max())} des heures).\n"
            "- **Réponse** : on peut repérer et compter les créneaux favorables par ville ; il reste à vérifier, "
            "avec un historique vélo plus long, que l'activité y est effectivement plus forte.")
    ui.reading(txt)

# --------------------------------------------------------------------- Q4
with q4:
    st.markdown("**A. Épisodes de pollution et météo** : épisodes détectés en Partie 3, comparés à la météo "
                "habituelle de la ville pendant la période.")
    eps = episodes(pol_raw)
    rows = []
    for _, e in eps.iterrows():
        m = h[(h["city"] == e["city"]) & h["timestamp"].between(e["start"], e["end"]) & h["has_weather"]]
        if m.empty:
            continue
        rows.append({"city": e["city"], "polluant": LABELS[e["pollutant"]],
                     "debut": e["start"].tz_convert(TZ).tz_localize(None), "heures": e["hours_flagged"],
                     "pic": e["peak_value"], "vent": m["wind_speed"].mean(), "temperature": m["temperature"].mean(),
                     "humidite": m["humidity"].mean(), "pluie": m["precipitation"].sum()})
    ew = pd.DataFrame(rows)
    ref = h[wp].groupby("city")[["wind_speed", "temperature", "humidity"]].median()
    if ew.empty:
        st.info("Aucun épisode de pollution pendant la période couverte par la météo.")
    else:
        ew["vent_habituel"] = ew["city"].map(ref["wind_speed"])
        a, b = st.columns([2, 3])
        with a:
            comp = (ew.groupby("city")["vent"].mean().rename("Pendant les épisodes").to_frame()
                    .join(ref["wind_speed"].rename("Médiane de la période")).reindex(cities).dropna()
                    .reset_index().melt("city", var_name="periode", value_name="vent"))
            fig = px.bar(comp, x="city", y="vent", color="periode", barmode="group", text="vent",
                         color_discrete_map={"Pendant les épisodes": theme.SERIES[1],
                                             "Médiane de la période": theme.SERIES[0]},
                         title="Vitesse du vent pendant les épisodes")
            fig.update_traces(marker_cornerradius=4, texttemplate="%{y:.1f}", textposition="outside",
                              textfont_color=theme.INK_2, cliponaxis=False,
                              hovertemplate="%{x} : %{y:.1f} m/s<extra>%{fullData.name}</extra>")
            fig.update_layout(height=380, xaxis_title=None, yaxis_title="Vent (m/s)", legend_title=None, bargap=0.25,
                              legend=dict(orientation="h", y=1.02, x=0, yanchor="bottom"))
            theme.show(fig)
        with b:
            st.dataframe(ew.sort_values("debut"), hide_index=True, width="stretch", height=380, column_config={
                "city": "Ville", "polluant": "Polluant",
                "debut": st.column_config.DatetimeColumn("Début", format="DD/MM HH:mm"), "heures": "Heures",
                "pic": st.column_config.NumberColumn("Pic (µg/m³)", format="%.0f"),
                "vent": st.column_config.NumberColumn("Vent (m/s)", format="%.1f"),
                "vent_habituel": st.column_config.NumberColumn("Vent médian ville", format="%.1f"),
                "temperature": st.column_config.NumberColumn("Temp. (°C)", format="%.1f"),
                "humidite": st.column_config.NumberColumn("Humidité (%)", format="%.0f"),
                "pluie": st.column_config.NumberColumn("Pluie (mm)", format="%.1f")})

    st.markdown("**B. Fenêtre commune aux trois flux** : vélos, pollution et météo sur les mêmes heures.")
    common = sorted(bk["date_local"].unique()) if not bk.empty else []
    if not common:
        st.info("Aucune heure commune aux trois flux.")
    else:
        b_cities = [c for c in cities if c in set(bk["city"])]
        city = st.selectbox("Ville", b_cities, key="q4_city")
        win = h[(h["city"] == city) & h["date_local"].isin(common)].sort_values("t")
        bw = bk[bk["city"] == city].sort_values("t")
        fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                            subplot_titles=["Vélos (mouvements / h)", "NO₂ et O₃ (µg/m³)", "Température (°C)",
                                            "Vent (m/s)"])
        fig.add_scatter(x=bw["t"], y=bw["bike_movements_per_hour"], mode="lines+markers", name="Vélos",
                        line=dict(color=theme.INK, width=2), marker_size=7, row=1, col=1,
                        hovertemplate="%{y:.0f} mvts/h<extra>Vélos</extra>")
        for p, color in [("no2", theme.SERIES[0]), ("o3", theme.SERIES[1])]:
            fig.add_scatter(x=win["t"], y=win[p], mode="lines", name=LABELS[p], line=dict(color=color, width=2),
                            row=2, col=1, hovertemplate=f"%{{y:.1f}} µg/m³<extra>{LABELS[p]}</extra>")
        fig.add_scatter(x=win["t"], y=win["temperature"], mode="lines", name="Température", showlegend=False,
                        line=dict(color=theme.INK_2, width=2), row=3, col=1,
                        hovertemplate="%{y:.1f} °C<extra>Température</extra>")
        fig.add_scatter(x=win["t"], y=win["wind_speed"], mode="lines", name="Vent", showlegend=False,
                        line=dict(color=theme.INK_2, width=2), row=4, col=1,
                        hovertemplate="%{y:.1f} m/s<extra>Vent</extra>")
        x0, x1 = bw["t"].min(), bw["t"].max() + pd.Timedelta(hours=1)
        fig.add_vrect(x0=x0, x1=x1, fillcolor=theme.SERIES[2], opacity=0.08, line_width=0)
        fig.update_layout(height=640, hovermode="x unified", title=f"{city} · {', '.join(common)} (bande = heures vélo)",
                          legend=dict(orientation="h", y=1.05, x=0, yanchor="bottom"))
        fig.update_xaxes(tickformat="%d/%m %Hh")
        theme.show(fig)

    txt = ""
    if not ew.empty:
        calm = (ew["vent"] < ew["vent_habituel"]).mean()
        eve = ew["debut"].dt.hour.between(17, 23).mean()
        txt += (f"- **{pct(calm)} des épisodes** de pollution ont lieu avec un vent plus faible que d'habitude "
                f"dans la ville ({fr(ew['vent'].mean(), 1)} m/s en moyenne pendant les épisodes, contre "
                f"{fr(ref['wind_speed'].mean(), 1)} m/s en médiane) ; {pct(eve)} commencent en soirée (17h-23h), "
                "quand le vent retombe et que l'air se mélange moins"
                + (". Météo calme + émissions du trafic = accumulation : c'est l'interaction météo-pollution la "
                   "plus nette de la période.\n" if calm > 0.5 else ".\n"))
        e_days = set(ew["debut"].dt.strftime("%Y-%m-%d"))
        overlap = e_days & set(common)
        txt += ("- Aucun épisode de pollution ne tombe sur les heures où les données vélo existent : on ne peut pas "
                "observer l'effet d'un épisode sur la mobilité.\n" if not overlap else
                f"- Des épisodes tombent pendant la collecte vélo ({', '.join(sorted(overlap))}) : à examiner ci-dessus.\n")
    if common and len(bw) >= 2:
        wb = win[win["t"].between(x0, x1)]

        def trend(col, s):
            s = s.dropna(subset=[col])
            if len(s) < 2:
                return "non mesuré"
            return "hausse" if s[col].iloc[-1] > s[col].iloc[0] else "baisse"

        txt += (f"- Sur la fenêtre commune à {city} : vélos en {trend('bike_movements_per_hour', bw)}, "
                f"température en {trend('temperature', wb)}, vent en {trend('wind_speed', wb)}, "
                f"NO₂ en {trend('no2', wb)}, O₃ en {trend('o3', wb)}. "
                "Une seule fenêtre de quelques heures ne permet pas de distinguer une interaction d'une simple "
                "coïncidence horaire.\n")
    if not ew.empty and calm > 0.5:
        txt += ("- **Réponse** : oui pour météo × pollution (les épisodes surviennent par temps calme, surtout le soir) ; "
                "pour la mobilité, l'interaction reste à mesurer sur un historique vélo couvrant plusieurs jours et "
                "des épisodes.")
    else:
        txt += ("- **Réponse** : pas d'interaction nette mise en évidence sur la période ; à mesurer sur un historique "
                "vélo plus long.")
    ui.reading(txt)

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import lake
import theme
import ui
from ui import fr, pct

from iot import analysis as A  # methodes de la partie 3 (src/ ajoute au chemin par lake), reutilisees telles quelles

ui.header(
    "Partie 3 – Flux IoT : pollution urbaine",
    "Source : API OpenAQ · capteurs des principales villes de France · PM2.5, PM10, NO₂, O₃, CO",
    [
        "Quelles zones présentent les niveaux de pollution les plus élevés ?",
        "Existe-t-il une variation journalière de la pollution ?",
        "Quels polluants sont les plus dominants dans la ville étudiée ?",
        "Peut-on identifier des épisodes de pollution anormale ?",
    ],
)
ui.data_status("Partie 3 – Pollution")

t = lake.require("pollution_horaire_ville", "pollution_sensors", "q1_ranking_stations")
if len(t) < 3:
    st.stop()

TZ = "Europe/Paris"
LABELS = {"pm25": "PM2.5", "pm10": "PM10", "no2": "NO₂", "o3": "O₃", "co": "CO"}
MAP_STYLE = "carto-positron"


def au(p: str) -> str:
    """Article contracte : « au NO₂ » mais « à l'O₃ »."""
    return f"à l'{LABELS[p]}" if p == "o3" else f"au {LABELS[p]}"


def le(p: str) -> str:
    return f"l'{LABELS[p]}" if p == "o3" else f"le {LABELS[p]}"


@st.cache_data(show_spinner="Calcul des indicateurs…")
def who_table(g: pd.DataFrame) -> pd.DataFrame:
    return A.q3_who(g)


@st.cache_data(show_spinner="Détection des épisodes…")
def episodes(g: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    return A.q4_episodes(g)


g = t["pollution_horaire_ville"]
sensors = t["pollution_sensors"]
rank = t["q1_ranking_stations"]
pols = [p for p in A.POLLUTANTS if p in set(g["pollutant"])]
cities = [c for c in theme.CITY_COLORS if c in set(g["city"])]
start, end = g["timestamp"].min().tz_convert(TZ), g["timestamp"].max().tz_convert(TZ)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Période", f"{start:%d/%m/%Y} → {end:%d/%m/%Y}")
k2.metric("Villes", len(cities))
k3.metric("Capteurs", fr(sensors["sensor_id"].nunique()))
k4.metric("Stations de mesure", fr(sensors["location_name"].nunique()))
missing_co = [c for c in cities if not ((g["city"] == c) & (g["pollutant"] == "co")).any()]
st.caption("Concentrations en µg/m³ (ppb/ppm convertis à 25 °C). Heures en heure de Paris."
           + (f" Le CO n'est mesuré que par 1 à 4 capteurs et pas du tout à {' ni à '.join(missing_co)}."
              if missing_co else ""))

q1, q2, q3, q4 = st.tabs(["Q1 · Zones les plus polluées", "Q2 · Variation journalière",
                          "Q3 · Polluants dominants", "Q4 · Épisodes anormaux"])

# --------------------------------------------------------------------- Q1
with q1:
    c1, c2 = st.columns([2, 1])
    pol = c1.radio("Polluant", pols, format_func=LABELS.get, horizontal=True, key="q1_pol")
    min_h = c2.slider("Heures de mesure minimales par station", 0, int(rank["n_hours"].max()), 0, 24,
                      help="Les stations n'ont pas toutes mesuré pendant toute la période : une station "
                           "mesurée 10 jours n'est pas comparable à une station mesurée 30 jours.")
    st.caption("Classement par station : résultat de la partie 3 (`outputs/partie3/tables/q1_ranking_stations.csv`, "
               "moyenne et 95e centile des concentrations horaires). Les mesures par capteur n'ont pas été exportées.")
    r = rank[(rank["pollutant"] == pol) & (rank["n_hours"] >= min_h)]
    loc = sensors.drop_duplicates("location_name")[["location_name", "distance_km"]]
    r = r.merge(loc, on="location_name", how="left")

    a, b = st.columns([2, 3])
    with a:
        top = r.nlargest(12, "mean").sort_values("mean")
        top = top.assign(label=top["location_name"].str.slice(0, 30) + " · " + top["city"])
        fig = px.bar(top, x="mean", y="label", orientation="h", custom_data=["p95", "n_hours"],
                     title=f"Stations les plus exposées · {LABELS[pol]}")
        fig.update_traces(marker_color=theme.SERIES[0], marker_cornerradius=4, texttemplate="%{x:.1f}",
                          textposition="outside", textfont_color=theme.INK_2, cliponaxis=False,
                          hovertemplate="<b>%{y}</b><br>Moyenne %{x:.1f} µg/m³<br>95e centile %{customdata[0]:.1f}"
                                        "<br>%{customdata[1]} heures de mesure<extra></extra>")
        fig.update_layout(height=max(320, 30 * len(top) + 90), bargap=0.35, yaxis_title=None,
                          xaxis_title="Concentration moyenne (µg/m³)")
        theme.show(fig)
    with b:
        city = st.selectbox("Ville (carte)", cities, key="q1_city")
        rc = r[r["city"] == city]
        if rc.empty:
            st.info(f"Aucune station ne mesure {le(pol)} à {city}.")
        else:
            fig = px.scatter_map(rc, lat="latitude", lon="longitude", color="mean", size="p95", size_max=22,
                                 color_continuous_scale=theme.SEQUENTIAL_MAP, hover_name="location_name",
                                 custom_data=["mean", "p95", "n_hours"], map_style=MAP_STYLE, zoom=10,
                                 center={"lat": rc["latitude"].mean(), "lon": rc["longitude"].mean()},
                                 height=480, title=f"{city} · {LABELS[pol]} moyen par station (taille = 95e centile)")
            fig.update_traces(hovertemplate="<b>%{hovertext}</b><br>Moyenne %{customdata[0]:.1f} µg/m³<br>"
                                            "95e centile %{customdata[1]:.1f}<br>%{customdata[2]} h<extra></extra>")
            fig.update_layout(margin=dict(l=0, r=0, t=40, b=0),
                              coloraxis_colorbar=dict(title="µg/m³"))
            theme.show(fig)

    city_mean = (g[g["pollutant"] == pol].groupby("city")["value"].mean().reindex(cities).dropna()
                 .sort_values(ascending=False))
    txt = ""
    if len(top):
        s = top.iloc[-1]
        txt += (f"- Station la plus exposée {au(pol)} : **{s['location_name']}** ({s['city']}), "
                f"{fr(s['mean'], 1)} µg/m³ en moyenne (95e centile {fr(s['p95'], 1)}).\n")
        names = top.sort_values("mean", ascending=False).head(5)["location_name"]
        road = names[names.str.contains(r"Auto|Périph|périph|RN\d|Bld|Boulevard|Avenue|AVENUES|Rue", regex=True)]
        if len(road) >= 2:
            txt += (f"- Parmi les 5 premières, {len(road)} portent le nom d'un axe routier ("
                    + ", ".join(road) + ") : ce sont des stations de **proximité trafic**.\n")
        if s["n_hours"] < 0.5 * rank["n_hours"].max():
            txt += (f"- Attention : cette station n'a mesuré que {s['n_hours']} heures sur la période ; "
                    "le curseur permet de ne garder que les stations mesurées plus longtemps.\n")
    if len(city_mean):
        txt += (f"- Ville la plus exposée {au(pol)} (moyenne de ses capteurs) : **{city_mean.index[0]}** "
                f"({fr(city_mean.iloc[0], 1)} µg/m³), la moins exposée : {city_mean.index[-1]} "
                f"({fr(city_mean.iloc[-1], 1)} µg/m³).")
    ui.reading(txt)

# --------------------------------------------------------------------- Q2
with q2:
    st.markdown("Concentration moyenne pour chaque heure de la journée (heure de Paris), sur toute la période.")
    prof = A.q2_daily_profile(g)
    prof["polluant"] = prof["pollutant"].map(LABELS)
    fig = px.line(prof, x="local_hour", y="mean", color="city", facet_col="polluant", facet_col_wrap=3,
                  color_discrete_map=theme.CITY_COLORS, markers=True,
                  category_orders={"polluant": [LABELS[p] for p in pols], "city": cities},
                  facet_row_spacing=0.14, facet_col_spacing=0.06,
                  title="Profil journalier moyen par polluant (échelles indépendantes)")
    fig.update_traces(line_width=2, marker_size=5, hovertemplate="%{x}h : %{y:.1f} µg/m³")
    fig.update_yaxes(matches=None, showticklabels=True, title=None, rangemode="tozero")
    fig.update_xaxes(title=None, dtick=3, ticksuffix="h")
    fig.for_each_annotation(lambda a: a.update(text=f"<b>{a.text.split('=')[-1]}</b>"))
    fig.update_layout(height=620, legend_title=None, hovermode="x unified",
                      legend=dict(orientation="h", y=1.04, x=0, yanchor="bottom"))
    theme.show(fig)

    peaks = prof.loc[prof.groupby(["pollutant", "city"])["mean"].idxmax()]
    lows = prof.loc[prof.groupby(["pollutant", "city"])["mean"].idxmin()]
    amp = (peaks.set_index(["pollutant", "city"])["mean"] / lows.set_index(["pollutant", "city"])["mean"])
    txt = ""
    for p in pols:
        ph = peaks[peaks["pollutant"] == p]
        hours = ph["local_hour"].value_counts()
        h_typ = int(ph["local_hour"].median())
        line = (f"- **{LABELS[p]}** : pic vers **{h_typ}h** (médiane des villes ; "
                + ", ".join(f"{r.city} {r.local_hour}h" for r in ph.itertuples()) + ")")
        a_ = amp.loc[p]
        line += f", le maximum vaut {fr(a_.min(), 1)} à {fr(a_.max(), 1)} fois le minimum de la journée"
        if p == "no2":
            d = prof[prof["pollutant"] == "no2"]
            morning = d[d["local_hour"].between(5, 13)].loc[lambda x: x.groupby("city")["mean"].idxmax()]
            evening = d[d["local_hour"].between(17, 23)].loc[lambda x: x.groupby("city")["mean"].idxmax()]
            line = (f"- **NO₂** : **deux pics**, le matin vers **{int(morning['local_hour'].median())}h** et le soir "
                    f"vers **{int(evening['local_hour'].median())}h** (médianes des villes), le maximum vaut "
                    f"{fr(a_.min(), 1)} à {fr(a_.max(), 1)} fois le minimum : rythme du trafic routier, renforcé le "
                    "soir et la nuit par une couche d'air plus basse qui disperse moins les polluants")
        if p == "o3" and 12 <= h_typ <= 19:
            line += " : l'ozone se forme sous l'effet du soleil, d'où un pic l'après-midi"
        txt += line + ".\n"
    txt += "- Oui, la pollution varie nettement au cours de la journée, avec des rythmes différents selon le polluant."
    ui.reading(txt)

# --------------------------------------------------------------------- Q3
with q3:
    st.markdown("Les concentrations en µg/m³ ne sont pas comparables d'un polluant à l'autre (le CO est toujours "
                "le plus élevé en masse mais rarement nocif à ces niveaux). On compare donc chaque polluant à sa "
                "**valeur guide OMS 2021 sur 24 h** : "
                + " · ".join(f"{LABELS[p]} {fr(A.WHO[p])} µg/m³" for p in pols)
                + " (O₃ : maximum journalier de la moyenne sur 8 h). Un polluant est **dominant** quand son "
                  "rapport à la valeur guide est le plus élevé de la ville.")
    w = who_table(g)
    w["polluant"] = w["pollutant"].map(LABELS)
    cols = [LABELS[p] for p in pols]
    ratio = w.pivot(index="city", columns="polluant", values="ratio_to_who").reindex(index=cities, columns=cols)
    days = w.pivot(index="city", columns="polluant", values="pct_days_above_who").reindex(index=cities, columns=cols)

    a, b = st.columns(2)
    for col, mat, title, fmt, zmax in [
        (a, ratio, "Niveau moyen ÷ valeur guide OMS (> 1 = au-dessus)", lambda v: fr(v, 2), max(1.0, ratio.max().max())),
        (b, days / 100, "Part des jours au-dessus de la valeur guide", lambda v: pct(v), 1.0)]:
        text = mat.map(lambda v: "" if pd.isna(v) else fmt(v))
        fig = px.imshow(mat, aspect="auto", zmin=0, zmax=zmax, color_continuous_scale=theme.SEQUENTIAL, title=title)
        fig.update_traces(text=text.values, texttemplate="%{text}", xgap=2, ygap=2,
                          hovertemplate="<b>%{y}</b> · %{x}<br>%{text}<extra></extra>")
        fig.update_layout(height=380, xaxis_title=None, yaxis_title=None, coloraxis_showscale=False)
        with col:
            theme.show(fig)

    dom = w[w["dominant_in_city"]].set_index("city").reindex(cities).dropna(subset=["pollutant"])
    with st.expander("Tableau détaillé"):
        st.dataframe(w[["city", "polluant", "valid_days", "mean_daily_metric", "who_guideline", "ratio_to_who",
                        "days_above_who", "dominant_in_city"]], hide_index=True, width="stretch", column_config={
            "city": "Ville", "polluant": "Polluant", "valid_days": "Jours valides",
            "mean_daily_metric": st.column_config.NumberColumn("Moyenne journalière (µg/m³)", format="%.1f"),
            "who_guideline": "Valeur guide OMS", "ratio_to_who": st.column_config.NumberColumn("Rapport", format="%.2f"),
            "days_above_who": "Jours au-dessus", "dominant_in_city": "Dominant"})

    by_pol = dom["polluant"].value_counts()
    txt = "- Polluant dominant par ville : " + " ; ".join(
        f"**{c}** : {r['polluant']} ({fr(r['ratio_to_who'], 2)} × la valeur guide, {pct(r['pct_days_above_who'] / 100)} "
        "des jours au-dessus)" for c, r in dom.iterrows()) + ".\n"
    why = {"NO₂": "le NO₂ est surtout émis par le trafic routier",
           "O₃": "l'O₃ est un polluant secondaire, formé sous l'effet du soleil et souvent plus élevé hors des centres"}
    txt += ("- " + " ; ".join(f"**{p}** dominant dans {n} ville(s)" for p, n in by_pol.items())
            + "".join(f". Rappel : {why[p]}" for p in by_pol.index if p in why) + ".\n")
    above = w[w["ratio_to_who"] >= 1]
    if len(above):
        txt += ("- Niveau moyen au-dessus de la valeur guide : " + ", ".join(
            f"{r['polluant']} à {r['city']} ({fr(r['ratio_to_who'], 2)})" for _, r in above.iterrows()) + ".\n")
    pm = w[w["pollutant"].isin(["pm25", "pm10"])]
    txt += (f"- Les particules (PM2.5, PM10) restent en dessous des valeurs guides en moyenne "
            f"(rapport max {fr(pm['ratio_to_who'].max(), 2)}) sur la période." if pm["ratio_to_who"].max() < 1 else "")
    ui.reading(txt)

# --------------------------------------------------------------------- Q4
with q4:
    st.markdown(f"Une heure est **anormale** quand la concentration (médiane des capteurs de la ville) dépasse "
                f"nettement le niveau habituel de cette heure de la journée (z-score robuste > {A.Z_THRESHOLD}). "
                f"Un **épisode** regroupe au moins {A.MIN_EPISODE_H} heures anormales espacées de moins de "
                f"{A.MAX_GAP_H} h. Seules les heures mesurées par au moins {A.MIN_SENSORS} capteurs sont analysées.")
    series, eps = episodes(g)
    if eps.empty:
        st.info("Aucun épisode anormal détecté sur la période.")
        st.stop()
    eps = eps.assign(polluant=eps["pollutant"].map(LABELS),
                     debut=eps["start"].dt.tz_convert(TZ), fin=eps["end"].dt.tz_convert(TZ))

    a, b = st.columns([2, 3])
    with a:
        cnt = eps.groupby(["city", "polluant"]).size().unstack().reindex(index=cities, columns=cols)
        fig = px.imshow(cnt, aspect="auto", zmin=0, color_continuous_scale=theme.SEQUENTIAL,
                        title="Nombre d'épisodes par ville et polluant")
        fig.update_traces(text=cnt.map(lambda v: "" if pd.isna(v) else f"{v:.0f}").values, texttemplate="%{text}",
                          xgap=2, ygap=2, hovertemplate="<b>%{y}</b> · %{x}<br>%{text} épisode(s)<extra></extra>")
        fig.update_layout(height=380, xaxis_title=None, yaxis_title=None, coloraxis_showscale=False)
        theme.show(fig)
    with b:
        st.markdown("**Épisodes détectés** (triés par intensité)")
        st.dataframe(eps[["city", "polluant", "debut", "fin", "hours_flagged", "peak_value", "baseline_median",
                          "peak_z"]], hide_index=True, width="stretch", height=330, column_config={
            "city": "Ville", "polluant": "Polluant",
            "debut": st.column_config.DatetimeColumn("Début", format="DD/MM HH:mm"),
            "fin": st.column_config.DatetimeColumn("Fin", format="DD/MM HH:mm"),
            "hours_flagged": "Heures anormales",
            "peak_value": st.column_config.NumberColumn("Pic (µg/m³)", format="%.1f"),
            "baseline_median": st.column_config.NumberColumn("Niveau habituel", format="%.1f"),
            "peak_z": st.column_config.NumberColumn("Intensité (z)", format="%.1f")})

    combos = eps.groupby(["city", "pollutant"])["hours_flagged"].sum().sort_values(ascending=False)
    options = [f"{c} · {LABELS[p]}" for c, p in combos.index]
    choice = st.selectbox("Série à afficher", options, key="q4_series")
    c_city, c_pol = combos.index[options.index(choice)]
    d = series[(series["city"] == c_city) & (series["pollutant"] == c_pol)].copy()
    d["t"] = d["timestamp"].dt.tz_convert(TZ)
    fig = go.Figure()
    for _, e in eps[(eps["city"] == c_city) & (eps["pollutant"] == c_pol)].iterrows():
        fig.add_vrect(x0=e["debut"], x1=e["fin"] + pd.Timedelta(hours=1), fillcolor=theme.STATUS["critical"],
                      opacity=0.12, line_width=0)
    fig.add_scatter(x=d["t"], y=d["baseline"], mode="lines", name="Niveau habituel (profil horaire médian)",
                    line=dict(color=theme.OTHER, width=2), hovertemplate="%{y:.1f} µg/m³")
    fig.add_scatter(x=d["t"], y=d["value"], mode="lines", name="Concentration horaire",
                    line=dict(color=theme.SERIES[0], width=2), hovertemplate="%{y:.1f} µg/m³")
    an = d[d["anomaly"]]
    fig.add_scatter(x=an["t"], y=an["value"], mode="markers", name="Heure anormale",
                    marker=dict(color=theme.STATUS["critical"], size=8, line=dict(color=theme.SURFACE, width=1)),
                    hovertemplate="%{y:.1f} µg/m³")
    fig.add_hline(y=A.WHO[c_pol], line_dash="dot", line_color=theme.INK_2, line_width=1,
                  annotation_text=f"Valeur guide OMS 24 h ({fr(A.WHO[c_pol])} µg/m³)",
                  annotation_font_color=theme.INK_2, annotation_position="top left")
    fig.update_layout(title=f"{c_city} · {LABELS[c_pol]} (bandes = épisodes anormaux)", height=440,
                      yaxis_title="µg/m³", xaxis_title=None, hovermode="x unified",
                      legend=dict(orientation="h", y=1.02, x=0, yanchor="bottom"))
    theme.show(fig)

    top_e = eps.iloc[0]
    evening = eps["debut"].dt.hour.between(17, 23).mean()
    by_city = eps["city"].value_counts()
    by_p = eps["polluant"].value_counts()
    txt = (f"- **{len(eps)} épisodes** détectés sur la période ; ville la plus touchée : **{by_city.index[0]}** "
           f"({by_city.iloc[0]} épisodes) ; polluant le plus concerné : **{by_p.index[0]}** ({by_p.iloc[0]}).\n"
           f"- Épisode le plus intense : {top_e['polluant']} à {top_e['city']} le {top_e['debut']:%d/%m} de "
           f"{top_e['debut']:%Hh} à {top_e['fin']:%Hh}, pic à {fr(top_e['peak_value'], 1)} µg/m³ pour un niveau "
           f"habituel de {fr(top_e['baseline_median'], 1)} µg/m³.\n"
           f"- {pct(evening)} des épisodes commencent en soirée (17h-23h).\n"
           "- Un épisode est un écart au niveau habituel de la ville, pas forcément un dépassement de la valeur "
           "guide : il signale un événement local (trafic, conditions météo défavorables à la dispersion…) "
           "à croiser avec la météo (Partie 4).")
    ui.reading(txt)

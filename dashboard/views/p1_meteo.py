import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import lake
import theme
import ui
from ui import fr, pct

ui.header(
    "Partie 1 – Flux batch : météo urbaine",
    "Source : NOAA Global Hourly · stations françaises · 2021 → août 2025",
    [
        "Peut-on identifier des périodes météorologiques anormales ?",
        "Existe-t-il une corrélation entre conditions météorologiques et visibilité ?",
        "Quelle est l'évolution saisonnière de la température en France ; dans les principales villes ?",
        "Quels sont les jours présentant des conditions météorologiques extrêmes ?",
    ],
)
ui.data_status("Partie 1 – Météo")

t = lake.require("meteo_journalier", "meteo_temperature_mensuelle", "meteo_anomalies_france",
                 "meteo_jours_extremes_villes")
if len(t) < 4:
    st.stop()

MIN_MESURES = 12        # jour fiable : au moins 12 mesures horaires (meme regle que le notebook de la partie 1)
MOIS = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]
MOIS_LONG = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
             "novembre", "décembre"]
CHAUD, FROID = "#e34948", theme.SERIES[0]      # poles chaud / froid (rouge / bleu)
# Seuils des jours extremes (notebook de la partie 1)
TYPES = {
    "grand_froid": ("Grand froid", "Tmin ≤ −5 °C", "temp_min", True),
    "forte_chaleur": ("Forte chaleur", "Tmax ≥ 35 °C", "temp_max", False),
    "vent_violent": ("Vent violent", "rafale max ≥ 17 m/s (61 km/h)", "vent_max", False),
    "fortes_pluies": ("Fortes pluies", "≥ 40 mm dans la journée", "pluie_mm", False),
}
TYPE_COLORS = dict(zip([v[0] for v in TYPES.values()], theme.SERIES[:4]))   # ordre valide (paires adjacentes)

j = t["meteo_journalier"]
fiables = j[j["nb_mesures"] >= MIN_MESURES]
an = t["meteo_anomalies_france"].sort_values("date")
tm = t["meteo_temperature_mensuelle"]
ex = t["meteo_jours_extremes_villes"]
cities = [c for c in theme.CITY_COLORS if c in set(tm["city"])]

k1, k2, k3, k4 = st.columns(4)
k1.metric("Période", f"{j['date'].min():%d/%m/%Y} → {j['date'].max():%d/%m/%Y}")
k2.metric("Stations", fr(j["station_id"].nunique()))
k3.metric("Jours × stations", fr(len(j)))
k4.metric("Jours fiables", pct(len(fiables) / len(j)),
          help=f"Au moins {MIN_MESURES} mesures dans la journée ; les autres jours sont écartés des analyses.")
st.caption(f"Les données NOAA publiées s'arrêtent au {j['date'].max():%d/%m/%Y}. Les analyses utilisent les "
           f"jours avec au moins {MIN_MESURES} mesures horaires (sinon une journée peut être résumée par "
           "2 ou 3 relevés, ce qui produit des valeurs aberrantes).")

# --------------------------------------------------------------------- carte des stations
MAP_VARS = {"temp_moy": ("Température moyenne", "°C"), "vent_moy": ("Vent moyen", "m/s"),
            "visibilite_moy": ("Visibilité moyenne", "m"), "pluie_mm": ("Pluie moyenne", "mm/jour")}
var = st.segmented_control("Carte des stations NOAA", list(MAP_VARS), default="temp_moy",
                           format_func=lambda v: MAP_VARS[v][0], key="p1_map_var") or "temp_moy"
stations = (fiables.groupby("station_id")
            .agg(station_name=("station_name", "first"), city=("city", "first"), latitude=("latitude", "mean"),
                 longitude=("longitude", "mean"), value=(var, "mean"), jours=("date", "nunique"))
            .dropna(subset=["latitude", "longitude", "value"]).reset_index())
stations["city"] = stations["city"].fillna("hors des 5 villes")
label, unit = MAP_VARS[var]
scale = ([[0, theme.SERIES[0]], [0.5, "#f0efec"], [1, CHAUD]] if var == "temp_moy" else theme.SEQUENTIAL_MAP)
fig = px.scatter_map(stations, lat="latitude", lon="longitude", color="value", size="jours", size_max=14,
                     color_continuous_scale=scale, map_style="carto-positron", zoom=4.6,
                     center={"lat": 46.6, "lon": 2.4}, height=560, custom_data=["station_name", "city", "jours"],
                     title=f"{fr(len(stations))} stations françaises · {label.lower()} 2021-2025 (taille = jours fiables)")
fig.update_traces(hovertemplate="<b>%{customdata[0]}</b> (%{customdata[1]})<br>"
                                f"{label} : %{{marker.color:.1f}} {unit}<br>%{{customdata[2]}} jours<extra></extra>")
fig.update_layout(margin=dict(l=0, r=0, t=40, b=0), coloraxis_colorbar=dict(title=unit))
theme.show(fig)

q1, q2, q3, q4 = st.tabs(["Q1 · Périodes anormales", "Q2 · Météo et visibilité", "Q3 · Saisons",
                          "Q4 · Jours extrêmes"])

# --------------------------------------------------------------------- Q1
with q1:
    st.markdown("Pour chaque jour, on compare la température moyenne en France à la **normale du mois** "
                "(moyenne 2021-2025). Un jour est **anormal** si l'écart dépasse 2 écarts-types. "
                "Une **période anormale** est une suite de jours anormaux consécutifs du même type.")
    min_days = st.slider("Durée minimale d'une période (jours)", 1, 7, 3, key="q1_min")

    an["groupe"] = (an["anomalie"] != an["anomalie"].shift()).cumsum()
    periods = (an[an["anomalie"] != "normal"].groupby("groupe")
               .agg(type=("anomalie", "first"), debut=("date", "min"), fin=("date", "max"),
                    jours=("date", "count"), ecart_max=("ecart", lambda s: s.abs().max()))
               .query("jours >= @min_days").sort_values("debut").reset_index(drop=True))

    fig = go.Figure()
    for _, p in periods.iterrows():
        fig.add_vrect(x0=p["debut"] - pd.Timedelta(hours=12), x1=p["fin"] + pd.Timedelta(hours=12),
                      fillcolor=CHAUD if p["type"] == "chaud" else FROID, opacity=0.15, line_width=0)
    fig.add_scatter(x=an["date"], y=an["ecart"], mode="lines", name="Écart à la normale",
                    line=dict(color=theme.AXIS, width=1), hovertemplate="%{x|%d/%m/%Y} : %{y:+.1f} °C<extra></extra>")
    for typ, color, label in [("chaud", CHAUD, "Jour anormalement chaud"), ("froid", FROID, "Jour anormalement froid")]:
        d = an[an["anomalie"] == typ]
        fig.add_scatter(x=d["date"], y=d["ecart"], mode="markers", name=label,
                        marker=dict(color=color, size=8, line=dict(color=theme.SURFACE, width=1)),
                        hovertemplate="%{x|%d/%m/%Y} : %{y:+.1f} °C<extra>" + label + "</extra>")
    fig.add_hline(y=0, line_color=theme.AXIS, line_width=1)
    fig.update_layout(title="Écart quotidien à la normale du mois, France (bandes = périodes anormales)",
                      yaxis_title="Écart (°C)", height=440, hovermode="closest",
                      legend=dict(orientation="h", y=1.02, x=0, yanchor="bottom"))
    theme.show(fig)

    a, b = st.columns([3, 2])
    with a:
        st.markdown(f"**Périodes anormales d'au moins {min_days} jour(s)**")
        st.dataframe(periods.assign(type=periods["type"].map({"chaud": "Chaud", "froid": "Froid"})),
                     hide_index=True, width="stretch", column_config={
                         "type": "Type", "debut": st.column_config.DateColumn("Début", format="DD/MM/YYYY"),
                         "fin": st.column_config.DateColumn("Fin", format="DD/MM/YYYY"), "jours": "Jours",
                         "ecart_max": st.column_config.NumberColumn("Écart max", format="%.1f °C")})
    with b:
        per_year = (an[an["anomalie"] != "normal"].assign(annee=an["date"].dt.year)
                    .groupby(["annee", "anomalie"]).size().rename("n").reset_index())
        per_year["anomalie"] = per_year["anomalie"].map({"chaud": "Chauds", "froid": "Froids"})
        fig = px.bar(per_year, x="annee", y="n", color="anomalie", barmode="group", text="n",
                     color_discrete_map={"Chauds": CHAUD, "Froids": FROID}, title="Jours anormaux par année")
        fig.update_traces(marker_cornerradius=4, textposition="outside", textfont_color=theme.INK_2,
                          cliponaxis=False, hovertemplate="%{x} : %{y} jours<extra></extra>")
        fig.update_layout(height=340, xaxis_title=None, yaxis_title="Jours", legend_title=None, bargap=0.3,
                          xaxis_dtick=1, legend=dict(orientation="h", y=1.02, x=0, yanchor="bottom"))
        theme.show(fig)

    n_hot, n_cold = int((an["anomalie"] == "chaud").sum()), int((an["anomalie"] == "froid").sum())
    txt = (f"- Sur {fr(len(an))} jours, **{n_hot} jours anormalement chauds** et **{n_cold} anormalement froids** "
           f"({pct((n_hot + n_cold) / len(an), 1)} des jours).\n")
    if len(periods):
        txt += f"- {len(periods)} période(s) anormale(s) d'au moins {min_days} jour(s) : " + " ; ".join(
            f"{'vague de chaleur' if p['type'] == 'chaud' else 'vague de froid'} du {p['debut']:%d/%m/%Y} au "
            f"{p['fin']:%d/%m/%Y} ({p['jours']} j, jusqu'à {fr(p['ecart_max'], 1)} °C d'écart)"
            for _, p in periods.iterrows()) + ".\n"
    yr = per_year.pivot(index="annee", columns="anomalie", values="n").fillna(0)
    if "Chauds" in yr:
        txt += (f"- L'année avec le plus de jours anormalement chauds est **{yr['Chauds'].idxmax()}** "
                f"({int(yr['Chauds'].max())} jours)")
        if "Froids" in yr:
            txt += f", celle avec le plus de jours froids **{yr['Froids'].idxmax()}** ({int(yr['Froids'].max())} jours)"
        txt += ".\n"
    txt += ("- Limite : la normale est calculée sur 2021-2025 seulement (et non sur la référence climatique "
            "1991-2020) ; une année chaude dans l'ensemble « relève » la normale.")
    ui.reading(txt)

# --------------------------------------------------------------------- Q2
with q2:
    st.markdown("Corrélations calculées sur les **moyennes journalières par station** (jours fiables). "
                "Les mesures horaires NOAA n'ont pas été exportées : le résultat peut différer légèrement "
                "d'un calcul heure par heure.")
    v = fiables.dropna(subset=["visibilite_moy"]).assign(vis=lambda d: d["visibilite_moy"] / 1000)
    variables = {"temp_moy": "Température", "pluie_mm": "Pluie", "pression_moy": "Pression", "vent_moy": "Vent moyen"}
    corr = pd.DataFrame({"variable": list(variables.values()),
                         "r": [v["visibilite_moy"].corr(v[c]) for c in variables],
                         "n": [int(v[c].notna().sum()) for c in variables]}).sort_values("r")
    corr["signe"] = corr["r"].map(lambda r: "Positive" if r >= 0 else "Négative")

    a, b = st.columns(2)
    with a:
        fig = px.bar(corr, x="r", y="variable", orientation="h", color="signe", text="r",
                     color_discrete_map={"Positive": theme.SERIES[0], "Négative": CHAUD}, custom_data=["n"],
                     title="Corrélation avec la visibilité (coefficient de Pearson)")
        fig.update_traces(marker_cornerradius=4, texttemplate="%{x:+.2f}", textposition="outside",
                          textfont_color=theme.INK_2, cliponaxis=False,
                          hovertemplate="<b>%{y}</b><br>r = %{x:+.3f}<br>%{customdata[0]:,} jours<extra></extra>")
        fig.update_layout(height=340, xaxis=dict(range=[-1, 1], dtick=0.25, title="r"), yaxis_title=None,
                          legend_title=None, bargap=0.4, showlegend=False)
        fig.add_vline(x=0, line_color=theme.AXIS, line_width=1)
        theme.show(fig)
    with b:
        month = v.groupby("mois")["vis"].mean().reindex(range(1, 13)).reset_index()
        fig = px.line(month, x="mois", y="vis", markers=True, title="Visibilité moyenne selon le mois")
        fig.update_traces(line=dict(color=theme.SERIES[0], width=2), marker_size=8,
                          hovertemplate="%{customdata} : %{y:.1f} km<extra></extra>", customdata=MOIS)
        fig.update_layout(height=340, yaxis_title="km", xaxis=dict(title=None, tickvals=list(range(1, 13)),
                                                                   ticktext=MOIS))
        theme.show(fig)

    rain = v.dropna(subset=["pluie_mm"]).assign(classe=lambda d: pd.cut(
        d["pluie_mm"], [-0.01, 0, 1, 10, float("inf")],
        labels=["Sec (0 mm)", "Faible (< 1 mm)", "Modérée (1-10 mm)", "Forte (≥ 10 mm)"]))
    wind = v.dropna(subset=["vent_moy"]).assign(classe=lambda d: pd.cut(
        d["vent_moy"], [0, 2, 5, 10, float("inf")], right=False,
        labels=["Calme (< 2 m/s)", "Faible (2-5)", "Modéré (5-10)", "Fort (≥ 10)"]))
    a, b = st.columns(2)
    for col, df, title in [(a, rain, "Visibilité selon la pluie du jour"), (b, wind, "Visibilité selon le vent moyen")]:
        g = df.groupby("classe", observed=True)["vis"].agg(["mean", "count"]).reset_index()
        fig = px.bar(g, x="classe", y="mean", text="mean", custom_data=["count"], title=title)
        fig.update_traces(marker_color=theme.SERIES[0], marker_cornerradius=4, texttemplate="%{y:.1f} km",
                          textposition="outside", textfont_color=theme.INK_2, cliponaxis=False,
                          hovertemplate="%{x}<br>%{y:.1f} km<br>%{customdata[0]:,} jours<extra></extra>")
        fig.update_layout(height=340, xaxis_title=None, yaxis_title="Visibilité moyenne (km)", bargap=0.4)
        with col:
            theme.show(fig)

    strongest = corr.loc[corr["r"].abs().idxmax()]
    rg = rain.groupby("classe", observed=True)["vis"].mean()
    wg = wind.groupby("classe", observed=True)["vis"].mean()
    txt = (f"- Les corrélations linéaires sont **faibles** : la plus forte est avec la **{strongest['variable'].lower()}** "
           f"(r = {fr(strongest['r'], 2)}). Aucune variable ne suffit seule à expliquer la visibilité.\n"
           f"- Visibilité moyenne : {fr(rg.iloc[0], 1)} km les jours secs contre {fr(rg.iloc[-1], 1)} km les jours "
           f"de forte pluie{' : la pluie réduit la visibilité' if rg.iloc[-1] < rg.iloc[0] else ''}.\n")
    middle = wg.iloc[1:-1].max()
    if wg.iloc[0] < middle and wg.iloc[-1] < middle:
        txt += (f"- La relation avec le vent n'est pas linéaire : la visibilité est plus faible par temps **calme** "
                f"({fr(wg.iloc[0], 1)} km, situations propices au brouillard) et par **vent fort** "
                f"({fr(wg.iloc[-1], 1)} km, souvent associé aux perturbations), et meilleure entre les deux "
                f"({fr(middle, 1)} km). C'est pourquoi le coefficient de corrélation avec le vent est proche de 0.\n")
    m_min, m_max = (MOIS_LONG[int(month.loc[month["vis"].idxmin(), "mois"]) - 1],
                    MOIS_LONG[int(month.loc[month["vis"].idxmax(), "mois"]) - 1])
    txt += (f"- Effet saisonnier : visibilité minimale en **{m_min}** ({fr(month['vis'].min(), 1)} km) et maximale "
            f"en **{m_max}** ({fr(month['vis'].max(), 1)} km)"
            + (", ce qui explique la corrélation positive avec la température.\n"
               if corr.set_index("variable").loc["Température", "r"] > 0 else ".\n")
            + "- Limite : l'humidité, principal facteur du brouillard, ne fait pas partie des variables NOAA extraites.")
    ui.reading(txt)

# --------------------------------------------------------------------- Q3
with q3:
    shown = st.multiselect("Villes", cities, default=cities, key="q3_cities")
    keep = shown + ["France"]
    prof = tm[tm["city"].isin(keep)].groupby(["city", "mois"])["temp_moy"].mean().reset_index()
    serie = tm[tm["city"].isin(keep)].assign(
        periode=lambda d: pd.to_datetime(dict(year=d["annee"], month=d["mois"], day=1))).sort_values("periode")
    colors = {**theme.CITY_COLORS, "France": theme.FRANCE}
    order = {"city": shown + ["France"]}

    def style(fig):
        fig.update_traces(line_width=2, marker_size=7)
        fig.for_each_trace(lambda tr: tr.update(line_dash="dash", line_width=3) if tr.name == "France" else None)
        fig.update_layout(legend_title=None, yaxis_title="Température moyenne (°C)", xaxis_title=None,
                          hovermode="x unified", legend=dict(orientation="h", y=1.02, x=0, yanchor="bottom"))
        return fig

    fig = px.line(prof, x="mois", y="temp_moy", color="city", markers=True, color_discrete_map=colors,
                  category_orders=order, title="Profil saisonnier moyen (2021-2025)")
    fig.update_traces(hovertemplate="%{y:.1f} °C")
    fig.update_layout(height=420, xaxis=dict(tickvals=list(range(1, 13)), ticktext=MOIS))
    theme.show(style(fig))

    fig = px.line(serie, x="periode", y="temp_moy", color="city", color_discrete_map=colors,
                  category_orders=order, title="Température moyenne mois par mois")
    fig.update_traces(hovertemplate="%{y:.1f} °C")
    fig.update_layout(height=400, xaxis_tickformat="%m/%Y")
    theme.show(style(fig))

    piv = tm.groupby(["city", "mois"])["temp_moy"].mean().unstack("mois")
    with st.expander("Tableau : température moyenne par mois (°C)"):
        st.dataframe(piv.rename(columns=dict(enumerate(MOIS, 1))).loc[[c for c in cities + ["France"] if c in piv.index]]
                     .round(1), width="stretch")

    fr_ = piv.loc["France"] if "France" in piv.index else None
    cp = piv.loc[[c for c in cities if c in piv.index]]
    amp = cp.max(axis=1) - cp.min(axis=1)
    summer = cp[[7, 8]].mean(axis=1)
    txt = ""
    if fr_ is not None:
        txt += (f"- En France, la température moyenne passe de **{fr(fr_.min(), 1)} °C** en {MOIS_LONG[fr_.idxmin() - 1]} "
                f"à **{fr(fr_.max(), 1)} °C** en {MOIS_LONG[fr_.idxmax() - 1]} (amplitude {fr(fr_.max() - fr_.min(), 1)} °C).\n")
    txt += (f"- Ville la plus chaude en moyenne annuelle : **{cp.mean(axis=1).idxmax()}** "
            f"({fr(cp.mean(axis=1).max(), 1)} °C) ; la plus fraîche : **{cp.mean(axis=1).idxmin()}** "
            f"({fr(cp.mean(axis=1).min(), 1)} °C).\n"
            f"- Climat le plus contrasté : **{amp.idxmax()}** ({fr(amp.max(), 1)} °C entre le mois le plus froid et le "
            f"plus chaud) ; le moins contrasté : **{amp.idxmin()}** ({fr(amp.min(), 1)} °C).\n"
            f"- Été (juillet-août) le plus frais : **{summer.idxmin()}** ({fr(summer.min(), 1)} °C) ; le plus chaud : "
            f"**{summer.idxmax()}** ({fr(summer.max(), 1)} °C).\n"
            "- Toutes les villes suivent le même cycle annuel ; les écarts reflètent leur climat : océanique "
            "(Bordeaux), océanique dégradé (Paris), semi-continental (Lyon), méditerranéen (Marseille), "
            "océanique à influence méditerranéenne (Toulouse).")
    ui.reading(txt)

# --------------------------------------------------------------------- Q4
with q4:
    st.markdown("Un jour est **extrême** pour une ville si l'une de ses stations dépasse un seuil : "
                + " · ".join(f"**{v[0].lower()}** : {v[1]}" for v in TYPES.values()) + ".")
    counts = (ex.groupby("city")[list(TYPES)].sum().reindex([c for c in cities if c in set(ex["city"])])
              .rename(columns={k: v[0] for k, v in TYPES.items()}).reset_index()
              .melt("city", var_name="type", value_name="jours"))
    fig = px.bar(counts, x="city", y="jours", color="type", barmode="group", text="jours",
                 color_discrete_map=TYPE_COLORS, category_orders={"type": list(TYPE_COLORS)},
                 title=f"Nombre de jours extrêmes par ville ({ex['date'].min():%Y} - {ex['date'].max():%m/%Y})")
    fig.update_traces(marker_cornerradius=4, texttemplate="%{y:.0f}", textposition="outside",
                      textfont_color=theme.INK_2, cliponaxis=False,
                      hovertemplate="<b>%{x}</b><br>%{y:.0f} jours<extra>%{fullData.name}</extra>")
    fig.update_layout(height=420, xaxis_title=None, yaxis_title="Jours", legend_title=None, bargap=0.2,
                      bargroupgap=0.08, legend=dict(orientation="h", y=1.02, x=0, yanchor="bottom"))
    theme.show(fig)

    tl = (ex.melt(["city", "date"], list(TYPES), var_name="k", value_name="flag").query("flag == 1")
          .assign(type=lambda d: d["k"].map({k: v[0] for k, v in TYPES.items()})))
    fig = px.scatter(tl, x="date", y="city", color="type", facet_row="type", color_discrete_map=TYPE_COLORS,
                     category_orders={"type": list(TYPE_COLORS), "city": cities[::-1]},
                     title="Calendrier des jours extrêmes")
    fig.update_traces(marker=dict(size=9, symbol="line-ns", line=dict(width=2)),
                      hovertemplate="%{y} · %{x|%d/%m/%Y}<extra>%{fullData.name}</extra>")
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1], textangle=0, xanchor="left", x=1.005))
    fig.update_layout(height=620, showlegend=False, margin=dict(r=110))
    fig.update_yaxes(title=None)
    fig.update_xaxes(title=None)
    theme.show(fig)

    st.markdown("**Records en France (toutes stations, jours fiables)**")
    choice = st.radio("Type", [v[0] for v in TYPES.values()], horizontal=True, key="q4_type",
                      label_visibility="collapsed")
    key = next(k for k, v in TYPES.items() if v[0] == choice)
    _, _, col, asc = TYPES[key]
    rec = fiables.dropna(subset=[col]).sort_values(col, ascending=asc).head(10)
    unit = "mm" if col == "pluie_mm" else ("m/s" if col == "vent_max" else "°C")
    st.dataframe(rec[["date", "station_name", "city", col]], hide_index=True, width="stretch", column_config={
        "date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"), "station_name": "Station",
        "city": "Ville étudiée", col: st.column_config.NumberColumn(choice, format=f"%.1f {unit}")})

    tot = counts.groupby("type")["jours"].sum()
    lead = counts.loc[counts.groupby("type")["jours"].idxmax()].set_index("type")
    txt = "".join(f"- **{typ}** : {int(tot[typ])} jours au total, surtout à **{lead.loc[typ, 'city']}** "
                  f"({int(lead.loc[typ, 'jours'])} jours).\n" for typ in TYPE_COLORS if typ in tot and tot[typ] > 0)
    hot = fiables.loc[fiables["temp_max"].idxmax()]
    cold = fiables.loc[fiables["temp_min"].idxmin()]
    txt += (f"- Records nationaux : {fr(hot['temp_max'], 1)} °C le {hot['date']:%d/%m/%Y} ({hot['station_name'].removesuffix(', FR').title()}), "
            f"{fr(cold['temp_min'], 1)} °C le {cold['date']:%d/%m/%Y} ({cold['station_name'].removesuffix(', FR').title()}).\n")
    heat_years = ex[ex["forte_chaleur"] == 1]["date"].dt.year.value_counts()
    if len(heat_years):
        top_y = heat_years.head(3)
        txt += ("- Années avec le plus de jours de forte chaleur (toutes villes) : "
                + ", ".join(f"**{y}** ({n} j)" for y, n in top_y.items()) + ".\n")
    if "Vent violent" in lead.index and lead.loc["Vent violent", "city"] == "Marseille":
        share = lead.loc["Vent violent", "jours"] / max(tot["Vent violent"], 1)
        txt += f"- Le vent violent est une particularité marseillaise ({pct(share)} des jours, effet du mistral)."
    ui.reading(txt)

ui.gallery("Figures du notebook Spark (partie1_meteo/meteo_silver_gold.ipynb)",
           ui.notebook_pngs(lake.ROOT / "partie1_meteo" / "meteo_silver_gold.ipynb"))

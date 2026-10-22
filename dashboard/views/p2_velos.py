import pandas as pd
import plotly.express as px
import streamlit as st

import lake
import theme
import ui
from ui import fr, pct

ui.header(
    "Partie 2 – Flux streaming : mobilité urbaine",
    "Source : API CityBikes · 10 réseaux de vélos en libre-service · relevé toutes les 2 min 30",
    [
        "Quelles stations présentent le plus fort taux d'utilisation ?",
        "Peut-on identifier des zones où l'offre de vélos est insuffisante ?",
        "Quels sont les pics d'utilisation journaliers du réseau de vélos ?",
        "Existe-t-il des déséquilibres géographiques dans la disponibilité des vélos ?",
        "Peut-on détecter des stations critiques nécessitant un rééquilibrage des vélos ?",
    ],
)
ui.data_status("Partie 2 – Vélos")

t = lake.require("station_usage", "zone_supply", "network_timeseries", "geo_balance", "critical_stations")
if len(t) < 5:
    st.stop()

MAX_GAP_MIN = 10        # deux releves plus espaces ne sont pas consecutifs (meme regle que silver_to_gold)
MIN_HOUR_MIN = 30       # Q3 : une heure n'est retenue que si elle est observee au moins 30 min
MAP_STYLE = "carto-positron"
VIDE, PLEINE = "Vide chronique : réapprovisionner", "Pleine chronique : délester"
PONCTUEL = "Vide ou pleine au dernier relevé"
STATUS_COLORS = {VIDE: theme.SERIES[1], PLEINE: theme.SERIES[0], PONCTUEL: theme.OTHER}

# --------------------------------------------------------------------- qualite et filtres
su_all = t["station_usage"]
per_city = su_all.groupby("city").agg(mv=("movements", "sum"), empty=("pct_time_empty", "mean"),
                                      n=("station_id", "count"))
# Reseau inexploitable : aucun mouvement et toutes les stations vides pendant toute la periode
invalid = sorted(per_city[(per_city["mv"] == 0) & (per_city["empty"] >= 0.99)].index)

c1, c2 = st.columns([1, 2], vertical_alignment="bottom")
exclude = False
if invalid:
    with c2:
        exclude = st.toggle(f"Exclure les réseaux sans activité mesurable ({', '.join(invalid)})", value=True)


def keep(df: pd.DataFrame) -> pd.DataFrame:
    return df[~df["city"].isin(invalid)] if exclude else df


su, zs, ts, gb, cs = (keep(t[n]) for n in
                      ["station_usage", "zone_supply", "network_timeseries", "geo_balance", "critical_stations"])
cities = su.groupby("city").size().sort_values(ascending=False).index.tolist()
with c1:
    city = st.selectbox("Ville (cartes et détail)", cities,
                        index=cities.index("Paris") if "Paris" in cities else 0)

start, end = ts["collected_at"].min(), ts["collected_at"].max()
k1, k2, k3, k4 = st.columns(4)
k1.metric("Période observée", f"{start:%d/%m %Hh%M} → {end:%d/%m %Hh%M}")
k2.metric("Durée d'observation (médiane par station)", f"{fr(su['observed_hours'].median(), 1)} h")
k3.metric("Stations", fr(len(su)))
k4.metric("Villes", len(cities))

for c in invalid:
    st.warning(f"**{c}** : les {per_city.loc[c, 'n']} stations affichent 0 vélo à chaque relevé, sans aucun "
               "mouvement. Le flux CityBikes de ce réseau ne permet pas de mesurer l'activité (à vérifier "
               "à la source).", icon=":material/report:")
st.caption("L'API ne donne que le nombre de vélos par station à chaque relevé, pas les trajets : l'activité est "
           "estimée par les variations entre deux relevés consécutifs (baisse = départs, hausse = arrivées). "
           "C'est une **borne basse** : un départ et une arrivée dans le même intervalle s'annulent.")


def city_map(df: pd.DataFrame, **kwargs):
    fig = px.scatter_map(df, lat="latitude", lon="longitude", map_style=MAP_STYLE, zoom=11.5,
                         center={"lat": df["latitude"].mean(), "lon": df["longitude"].mean()},
                         height=520, **kwargs)
    fig.update_layout(margin=dict(l=0, r=0, t=40, b=0), legend=dict(orientation="h", y=1.02, x=0))
    return fig


def hbar(df: pd.DataFrame, x: str, y: str, title: str, fmt: str, hover: str, custom=None):
    fig = px.bar(df, x=x, y=y, orientation="h", title=title, custom_data=custom)
    fig.update_traces(marker_color=theme.SERIES[0], marker_cornerradius=4, texttemplate=f"%{{x:{fmt}}}",
                      textposition="outside", textfont_color=theme.INK_2, hovertemplate=hover + "<extra></extra>",
                      cliponaxis=False)
    fig.update_layout(height=max(300, 32 * len(df) + 90), bargap=0.35, yaxis_title=None)
    return fig


q1, q2, q3, q4, q5 = st.tabs(["Q1 · Utilisation", "Q2 · Offre insuffisante", "Q3 · Pics journaliers",
                              "Q4 · Déséquilibres géographiques", "Q5 · Stations critiques"])

# --------------------------------------------------------------------- Q1
with q1:
    st.markdown("**Taux d'utilisation** = mouvements estimés par jour ÷ nombre de points d'attache "
                "(nombre de rotations quotidiennes par place).")
    net = su.groupby("city").agg(mvt=("movements_per_day", "sum"), cap=("capacity", "sum"),
                                 n=("station_id", "count")).reset_index()
    net["rot"] = net["mvt"] / net["cap"]
    net = net.sort_values("rot")

    a, b = st.columns(2)
    with a:
        theme.show(hbar(net, "rot", "city", "Taux d'utilisation par réseau", ".1f",
                        "<b>%{y}</b><br>%{x:.1f} rotations / place / jour<br>%{customdata[0]} stations",
                        custom=["n"]).update_layout(xaxis_title="Rotations par place et par jour"))
    with b:
        f1, f2 = st.columns(2)
        scope = f1.radio("Stations", [city, "Toutes les villes"], horizontal=True, key="q1_scope")
        hmax = float(su["observed_hours"].max())
        min_h = f2.slider("Observation minimale (h)", 0.0, round(hmax, 1), min(1.0, hmax), 0.5,
                          help="Écarte les stations vues sur trop peu de relevés : un seul mouvement "
                               "extrapolé sur une journée donne un taux artificiellement élevé.")
        pool = su if scope == "Toutes les villes" else su[su["city"] == city]
        dropped = int((pool["observed_hours"] < min_h).sum())
        top = pool[pool["observed_hours"] >= min_h].nlargest(15, "usage_rate").sort_values("usage_rate")
        top = top.assign(label=top["station_name"].str.slice(0, 32)
                         + (" · " + top["city"] if scope == "Toutes les villes" else ""))
        theme.show(hbar(top, "usage_rate", "label", f"Top 15 des stations · {scope}", ".1f",
                        "<b>%{y}</b><br>%{x:.1f} rotations / place / jour<br>%{customdata[0]:.0f} mouvements / jour"
                        "<br>%{customdata[1]} places",
                        custom=["movements_per_day", "capacity"])
                   .update_layout(xaxis_title="Rotations par place et par jour"))

    best, worst = net.iloc[-1], net.iloc[0]
    s = top.iloc[-1] if len(top) else None
    txt = (f"- Réseau le plus sollicité : **{best['city']}** ({fr(best['rot'], 1)} rotations par place et par jour), "
           f"contre **{fr(worst['rot'], 1)}** à {worst['city']}.\n")
    if s is not None:
        txt += (f"- Station la plus utilisée ({scope.lower() if scope != city else city}) : **{s['station_name']}**"
                f"{' (' + s['city'] + ')' if scope != city else ''} avec {fr(s['usage_rate'], 1)} rotations par "
                f"place et par jour ({fr(s['movements_per_day'])} mouvements estimés par jour pour "
                f"{s['capacity']} places).\n")
    txt += (f"- {dropped} station(s) observée(s) moins de {fr(min_h, 1)} h sont écartées du classement. "
            "Les taux sont extrapolés à la journée à partir de la période observée : ils comparent les "
            "stations entre elles, ce ne sont pas des volumes journaliers réels.")
    ui.reading(txt)

# --------------------------------------------------------------------- Q2
with q2:
    st.markdown("Le territoire est découpé en mailles d'environ 1 km². Une maille est **en offre insuffisante** "
                "si ses stations cumulent moins de 10 % de vélos plus de 25 % du temps, ou si leur "
                "remplissage moyen est inférieur à 15 %.")
    z = zs.assign(etat=zs["supply_insufficient"].map({True: "Offre insuffisante", False: "Offre suffisante"}))
    zc = z[z["city"] == city]

    a, b = st.columns([3, 2])
    with a:
        fig = city_map(zc, color="etat", size="departures_per_day", size_max=28,
                       color_discrete_map={"Offre insuffisante": theme.STATUS["critical"],
                                           "Offre suffisante": theme.SERIES[0]},
                       category_orders={"etat": ["Offre insuffisante", "Offre suffisante"]},
                       custom_data=["n_stations", "avg_fill_rate", "pct_time_short", "departures_per_day"],
                       title=f"{city} · mailles de 1 km² (taille = départs par jour)")
        fig.update_traces(hovertemplate="<b>%{fullData.name}</b><br>%{customdata[0]} stations<br>"
                                        "Remplissage moyen %{customdata[1]:.0%}<br>"
                                        "Moins de 10 % de vélos %{customdata[2]:.0%} du temps<br>"
                                        "%{customdata[3]:.0f} départs / jour<extra></extra>")
        theme.show(fig)
    with b:
        share = z.groupby("city").agg(n=("zone_id", "count"), ins=("supply_insufficient", "sum")).reset_index()
        share["pct"] = share["ins"] / share["n"]
        theme.show(hbar(share.sort_values("pct"), "pct", "city", "Part des mailles en offre insuffisante", ".0%",
                        "<b>%{y}</b><br>%{x:.0%} des mailles<br>%{customdata[0]} sur %{customdata[1]}",
                        custom=["ins", "n"]).update_layout(xaxis_tickformat=".0%", xaxis_title=None))

    worst_z = (zc[zc["supply_insufficient"]].nlargest(10, "departures_per_day")
               .assign(position=lambda d: d["latitude"].round(4).astype(str) + ", " + d["longitude"].round(4).astype(str)))
    st.markdown(f"**Mailles en offre insuffisante les plus demandées · {city}**")
    st.dataframe(
        worst_z[["position", "dist_center_km", "n_stations", "avg_bikes", "avg_fill_rate", "pct_time_short",
                 "departures_per_day"]],
        hide_index=True, width="stretch",
        column_config={
            "position": "Position (lat, lon)",
            "dist_center_km": st.column_config.NumberColumn("Distance au centre", format="%.1f km"),
            "n_stations": "Stations",
            "avg_bikes": st.column_config.NumberColumn("Vélos en moyenne", format="%.0f"),
            "avg_fill_rate": st.column_config.NumberColumn("Remplissage", format="percent"),
            "pct_time_short": st.column_config.NumberColumn("Temps < 10 % de vélos", format="percent"),
            "departures_per_day": st.column_config.NumberColumn("Départs / jour", format="%.0f"),
        })

    ins_c = zc[zc["supply_insufficient"]]
    top_city = share.sort_values("pct").iloc[-1]
    txt = (f"- **{city}** : {len(ins_c)} mailles sur {len(zc)} ({pct(len(ins_c) / max(len(zc), 1))}) sont en "
           f"offre insuffisante.\n"
           f"- Réseau le plus touché : **{top_city['city']}** ({pct(top_city['pct'])} des mailles).\n")
    if len(ins_c) and len(zc) > len(ins_c):
        d_in, d_ok = ins_c["dist_center_km"].median(), zc[~zc["supply_insufficient"]]["dist_center_km"].median()
        txt += (f"- À {city}, les mailles en déficit sont à {fr(d_in, 1)} km du centre en médiane, contre "
                f"{fr(d_ok, 1)} km pour les autres.\n")
    if len(worst_z) and worst_z.iloc[0]["departures_per_day"] >= 1:
        w = worst_z.iloc[0]
        txt += (f"- La maille en déficit la plus demandée ({w['position']}) enregistre {fr(w['departures_per_day'])} "
                f"départs estimés par jour pour {fr(w['avg_bikes'])} vélo(s) disponible(s) en moyenne : c'est là qu'un "
                "renfort d'offre a le plus d'effet.")
    ui.reading(txt)

# --------------------------------------------------------------------- Q3
with q3:
    ok = ts[ts["interval_min"] <= MAX_GAP_MIN]
    prof = ok.groupby(["city", "hour"]).agg(mvt=("movements", "sum"), minutes=("interval_min", "sum")).reset_index()
    prof["rate"] = prof["mvt"] / prof["minutes"] * 60
    excluded_hours = sorted(prof.loc[prof["minutes"] < MIN_HOUR_MIN, "hour"].unique())
    prof = prof[prof["minutes"] >= MIN_HOUR_MIN]
    order = prof.groupby("city")["rate"].sum().sort_values(ascending=False).index.tolist()

    snaps = pd.Series(sorted(ts["collected_at"].unique()))
    gaps = [(a, b) for a, b in zip(snaps[:-1], snaps[1:])
            if (b - a).total_seconds() / 60 > MAX_GAP_MIN and a.date() == b.date()]
    kept = ok[ok["hour"].isin(prof["hour"])]
    covered = sorted(kept["date"].dt.strftime("%d/%m").unique())
    weekdays_only = not kept["is_weekend"].astype(bool).any()
    st.markdown(f"Mouvements par heure (somme des mouvements ÷ durée observée dans l'heure). Seules les heures "
                f"observées au moins {MIN_HOUR_MIN} min sont affichées"
                + (f" (écartées : {', '.join(f'{h}h' for h in excluded_hours)})." if excluded_hours else ".")
                + ("  \nInterruptions de la collecte : "
                   + ", ".join(f"{a:%d/%m %Hh%M} → {b:%Hh%M}" for a, b in gaps) + "." if gaps else ""))
    fig = px.line(prof, x="hour", y="rate", facet_col="city", facet_col_wrap=5, markers=True,
                  category_orders={"city": order}, facet_row_spacing=0.18, facet_col_spacing=0.05,
                  title="Profil horaire par réseau (échelles indépendantes)")
    fig.update_traces(line=dict(color=theme.SERIES[0], width=2), marker=dict(size=8),
                      hovertemplate="%{x}h : %{y:.0f} mouvements / h<extra></extra>")
    fig.update_yaxes(matches=None, showticklabels=True, title=None, rangemode="tozero")
    fig.update_xaxes(title=None, dtick=1, ticksuffix="h")
    fig.for_each_annotation(lambda a: a.update(text=f"<b>{a.text.split('=')[-1]}</b>"))
    fig.update_layout(height=520)
    theme.show(fig)

    main_day = ts["date"].value_counts().idxmax()
    fl = ts[(ts["city"] == city) & (ts["date"] == main_day)].set_index("collected_at")
    fl = fl[["share_fleet_in_use", "share_stations_empty"]].resample("15min").mean().reset_index()
    fl = fl.melt("collected_at", var_name="m", value_name="v").replace(
        {"m": {"share_fleet_in_use": "Part de la flotte en circulation", "share_stations_empty": "Part des stations vides"}})
    fig = px.line(fl, x="collected_at", y="v", color="m", markers=True,
                  title=f"{city} · état du réseau le {main_day:%d/%m} (moyenne par quart d'heure)",
                  color_discrete_sequence=theme.SERIES)
    fig.update_traces(line_width=2, marker_size=8, hovertemplate="%{x|%Hh%M} : %{y:.1%}")
    fig.update_layout(yaxis_tickformat=".0%", yaxis_title=None, xaxis_title=None, legend_title=None,
                      hovermode="x unified", legend=dict(orientation="h", y=1.02, x=0, yanchor="bottom"))
    theme.show(fig)

    peaks = prof.loc[prof.groupby("city")["rate"].idxmax()].set_index("city").loc[order]
    peaks["hour"] = peaks["hour"].astype(int)
    hours = sorted(prof["hour"].unique())
    last_h = hours[-1] if hours else None
    n_last = int((peaks["hour"] == last_h).sum())
    pc = peaks.loc[city] if city in peaks.index else None
    txt = ""
    if pc is not None:
        txt += f"- **{city}** : pic observé à **{int(pc['hour'])}h** avec {fr(pc['rate'])} mouvements par heure.\n"
    txt += (f"- Dans {n_last} réseau(x) sur {len(peaks)}, le pic tombe sur la dernière heure observée ({last_h}h) : "
            "l'activité augmente au fil de l'après-midi, ce qui est cohérent avec le début de la pointe du soir.\n"
            f"- Limite : les heures exploitables ({', '.join(f'{h}h' for h in hours)}) couvrent seulement "
            f"**{len(covered)} jour(s){' de semaine' if weekdays_only else ''}** ({', '.join(covered)}). On ne peut pas conclure sur la pointe du matin, "
            "la soirée ni le week-end : il faut prolonger la collecte.")
    ui.reading(txt)

# --------------------------------------------------------------------- Q4
with q4:
    bands = ["0-2 km", "2-4 km", "4-6 km", "6-10 km", "> 10 km"]
    hm = su.groupby(["city", "dist_band"]).agg(fill=("avg_fill_rate", "mean"), n=("station_id", "count")).reset_index()
    grid = hm.pivot(index="city", columns="dist_band", values="fill").reindex(columns=bands).loc[cities]
    count = hm.pivot(index="city", columns="dist_band", values="n").reindex(columns=bands).loc[cities]

    fig = px.imshow(grid, text_auto=".0%", aspect="auto", zmin=0, zmax=1,
                    color_continuous_scale=theme.SEQUENTIAL,
                    title="Remplissage moyen des stations selon la distance au centre-ville")
    fig.update_traces(customdata=count.values,
                      hovertemplate="<b>%{y}</b> · %{x}<br>Remplissage %{z:.0%}<br>%{customdata} stations<extra></extra>",
                      xgap=2, ygap=2)
    fig.update_layout(height=420, xaxis_title="Distance au centre", yaxis_title=None,
                      coloraxis_colorbar=dict(title="Remplissage", tickformat=".0%"))
    theme.show(fig)

    a, b = st.columns([3, 2])
    with a:
        sc = su[su["city"] == city]
        fig = city_map(sc, color="avg_fill_rate", color_continuous_scale=theme.SEQUENTIAL_MAP,
                       range_color=(0, 1), hover_name="station_name",
                       custom_data=["avg_fill_rate", "pct_time_empty", "pct_time_full", "capacity"],
                       title=f"{city} · remplissage moyen par station")
        fig.update_traces(marker_size=8,
                          hovertemplate="<b>%{hovertext}</b><br>Remplissage %{customdata[0]:.0%}<br>"
                                        "Vide %{customdata[1]:.0%} du temps · pleine %{customdata[2]:.0%}<br>"
                                        "%{customdata[3]} places<extra></extra>")
        fig.update_layout(coloraxis_colorbar=dict(title="Remplissage", tickformat=".0%"))
        theme.show(fig)
    with b:
        g = gb[gb["city"] == city]
        fig = px.bar(g, x="dist_band", y="avg_fill_rate", color="period", barmode="group",
                     category_orders={"dist_band": bands}, custom_data=["n_stations"],
                     color_discrete_sequence=theme.SERIES, title=f"{city} · remplissage selon le moment")
        fig.update_traces(marker_cornerradius=4,
                          hovertemplate="%{x} · %{y:.0%}<br>%{customdata[0]} stations<extra></extra>")
        fig.update_layout(height=520, yaxis_tickformat=".0%", yaxis_title=None, xaxis_title=None,
                          legend_title=None, bargap=0.3, bargroupgap=0.1,
                          legend=dict(orientation="h", y=1.02, x=0, yanchor="bottom"))
        theme.show(fig)

    row = grid.loc[city].dropna()
    txt = ""
    if len(row) >= 2:
        txt += (f"- **{city}** : remplissage le plus élevé dans la tranche **{row.idxmax()}** ({pct(row.max())}), "
                f"le plus faible dans la tranche **{row.idxmin()}** ({pct(row.min())}), soit un écart de "
                f"{fr((row.max() - row.min()) * 100)} points.\n")
    centre = grid["0-2 km"]
    rest = su[su["dist_band"] != "0-2 km"].groupby("city")["avg_fill_rate"].mean().reindex(grid.index)
    diff = (centre - rest).dropna()
    up, down = diff[diff > 0.05].index.tolist(), diff[diff < -0.05].index.tolist()
    if up:
        txt += f"- Centre mieux pourvu que la périphérie (plus de 5 points d'écart) : {', '.join(up)}.\n"
    if down:
        txt += f"- Centre moins bien pourvu que la périphérie : {', '.join(down)}.\n"
    n_empty, n_full = int((su["pct_time_empty"] > 0.5).sum()), int((su["pct_time_full"] > 0.5).sum())
    txt += (f"- {n_empty} stations sont vides plus de la moitié du temps et {n_full} sont pleines plus de la "
            "moitié du temps : la disponibilité n'est pas homogène sur le territoire.")
    ui.reading(txt)

# --------------------------------------------------------------------- Q5
with q5:
    st.markdown("Une station est **critique** si elle est vide (ou pleine) plus de 25 % du temps observé. "
                "Le besoin est le nombre de vélos à apporter (+) ou retirer (−) pour revenir à 50 % de "
                "remplissage d'après le dernier relevé. Le score de priorité combine la durée de rupture et "
                "l'activité de la station.")
    c = cs.assign(etat=cs["status"].fillna(PONCTUEL))
    chronic = c[c["etat"] != PONCTUEL]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Stations vides chroniques", fr((c["etat"] == VIDE).sum()))
    m2.metric("Stations pleines chroniques", fr((c["etat"] == PLEINE).sum()))
    m3.metric("Vélos à apporter", fr(chronic.loc[chronic["rebalance_bikes"] > 0, "rebalance_bikes"].sum()))
    m4.metric("Vélos à retirer", fr(-chronic.loc[chronic["rebalance_bikes"] < 0, "rebalance_bikes"].sum()))

    a, b = st.columns([3, 2])
    cc = c[c["city"] == city]
    with a:
        fig = city_map(cc, color="etat", size="priority_score", size_max=18, hover_name="station_name",
                       color_discrete_map=STATUS_COLORS, category_orders={"etat": [VIDE, PLEINE, PONCTUEL]},
                       custom_data=["bikes_now", "capacity", "rebalance_bikes", "priority_score"],
                       title=f"{city} · stations critiques (taille = priorité)")
        fig.update_traces(hovertemplate="<b>%{hovertext}</b><br>%{fullData.name}<br>%{customdata[0]} vélos / "
                                        "%{customdata[1]} places<br>Action : %{customdata[2]:+d} vélos<br>"
                                        "Priorité %{customdata[3]}<extra></extra>")
        theme.show(fig)
    with b:
        bars = (chronic.groupby(["city", "etat"]).size().rename("n").reset_index())
        tot = bars.groupby("city")["n"].sum().sort_values().index.tolist()
        fig = px.bar(bars, x="n", y="city", color="etat", orientation="h", barmode="group",
                     category_orders={"city": tot[::-1], "etat": [VIDE, PLEINE]},
                     color_discrete_map=STATUS_COLORS, title="Stations critiques par réseau")
        fig.update_traces(marker_cornerradius=4, hovertemplate="<b>%{y}</b><br>%{x} stations<extra></extra>")
        fig.update_layout(height=520, xaxis_title="Stations", yaxis_title=None, legend_title=None,
                          bargap=0.25, legend=dict(orientation="h", y=1.02, x=0, yanchor="bottom"))
        theme.show(fig)

    st.markdown(f"**Liste de rééquilibrage · {city}** (par priorité décroissante)")
    table = cc.sort_values("priority_score", ascending=False)[
        ["station_name", "etat", "bikes_now", "capacity", "pct_time_empty", "pct_time_full", "rebalance_bikes",
         "priority_score"]]
    st.dataframe(table, hide_index=True, width="stretch", height=320, column_config={
        "station_name": "Station", "etat": "Diagnostic", "bikes_now": "Vélos (dernier relevé)", "capacity": "Places",
        "pct_time_empty": st.column_config.NumberColumn("Temps vide", format="percent"),
        "pct_time_full": st.column_config.NumberColumn("Temps pleine", format="percent"),
        "rebalance_bikes": st.column_config.NumberColumn("Action (vélos)", format="%+d"),
        "priority_score": st.column_config.ProgressColumn("Priorité", min_value=0,
                                                          max_value=float(c["priority_score"].max()), format="%.0f"),
    })
    st.download_button("Télécharger la liste complète (CSV)", c.drop(columns="etat").to_csv(index=False).encode("utf-8"),
                       "stations_critiques.csv", "text/csv", icon=":material/download:")

    ccc = chronic[chronic["city"] == city]
    top3 = cc.nlargest(3, "priority_score")
    txt = (f"- **{city}** : {(ccc['etat'] == VIDE).sum()} stations à réapprovisionner et "
           f"{(ccc['etat'] == PLEINE).sum()} à délester, soit environ "
           f"{fr(ccc.loc[ccc['rebalance_bikes'] > 0, 'rebalance_bikes'].sum())} vélos à déposer et "
           f"{fr(-ccc.loc[ccc['rebalance_bikes'] < 0, 'rebalance_bikes'].sum())} à retirer.\n")
    if len(top3):
        txt += "- Priorités : " + " ; ".join(
            f"**{r['station_name']}** ({r['etat'].split(' :')[0].lower()}, {r['rebalance_bikes']:+d} vélos)"
            for _, r in top3.iterrows()) + ".\n"
    vide_share = (chronic["etat"] == VIDE).mean() if len(chronic) else 0
    txt += (f"- Sur l'ensemble des réseaux, {pct(vide_share)} des stations critiques sont des stations **vides** : "
            "le besoin principal est d'apporter des vélos plutôt que d'en retirer.")
    ui.reading(txt)

ui.gallery("Figures du rapport (outputs/figures, générées par viz.figures)", ui.png_files(lake.ROOT / "outputs" / "figures"))

"""Gold -> figures matplotlib + rapport d'interprétation (questions métier 1 à 5).

Lit les tables gold avec Spark, les convertit en pandas (petits volumes agrégés),
produit les PNG dans outputs/figures/, un rapport Markdown et un CSV des stations
critiques, puis publie le tout dans MinIO (reports/partie2/).
"""
import os
from pathlib import Path

import boto3
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402

from common import config  # noqa: E402
from spark_jobs.session import get_spark  # noqa: E402

FOCUS = os.getenv("FOCUS_NETWORK", "velib")   # réseau étudié en détail (cartes)
OUT = Path(os.getenv("OUTPUT_DIR", "/app/outputs"))
FIG = OUT / "figures"

# Palette de référence (catégorielle dans l'ordre fixe, encre, statuts)
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
CRITICAL, SURFACE = "#d03b3b", "#fcfcfb"
SEQ = LinearSegmentedColormap.from_list("seq_blue", ["#cde2fb", "#6da7ec", "#2a78d6", "#184f95", "#0d366b"])
SEQ_ORANGE = LinearSegmentedColormap.from_list("seq_orange", ["#fde3d6", "#f5a27f", "#eb6834", "#b8461b", "#7d2c0e"])
DIVERGING = LinearSegmentedColormap.from_list("div", ["#d03b3b", "#ec9a95", "#f0efec", "#86b6ef", "#1c5cab"])

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "DejaVu Sans", "font.size": 10,
    "text.color": INK, "axes.labelcolor": INK2, "axes.titlecolor": INK,
    "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.edgecolor": AXIS,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False, "lines.linewidth": 2,
})


def pct(x: float) -> str:
    return f"{100 * x:.0f} %"


def save(fig, name: str, saved: list) -> None:
    path = FIG / name
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    saved.append(path)
    print(f"[viz] {path}")


def map_axes(ax, title: str) -> None:
    ax.set_title(title)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect(1.45)   # ≈ 1 / cos(46°) : évite d'écraser la carte
    ax.grid(False)


def load_gold(spark) -> dict:
    names = ["station_usage", "zone_supply", "network_timeseries", "hourly_profile",
             "geo_balance", "critical_stations"]
    return {n: spark.read.parquet(config.s3a(f"{config.GOLD_PREFIX}/{n}")).toPandas() for n in names}


# ---------------------------------------------------------------- Q1 utilisation
def q1(g: dict, saved: list, notes: list) -> None:
    usage = g["station_usage"]
    # On écarte les stations trop peu observées (apparues en cours de collecte, pannes)
    usage = usage[usage["observed_hours"] >= 0.5 * usage["observed_hours"].max()]
    focus = usage[usage["network_id"] == FOCUS].nlargest(15, "usage_rate").iloc[::-1]
    city = focus["city"].iloc[0] if len(focus) else FOCUS

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(focus["station_name"].str.slice(0, 40), focus["usage_rate"], color=BLUE, height=0.7)
    for y, (v, m) in enumerate(zip(focus["usage_rate"], focus["movements_per_day"])):
        ax.text(v, y, f"  {v:.1f}  ({m:.0f} mvts/j)", va="center", color=INK2, fontsize=8)
    ax.set_title(f"Q1 – Stations au plus fort taux d'utilisation ({city})")
    ax.set_xlabel("Rotations par point d'attache et par jour (mouvements / capacité)")
    ax.grid(axis="y", visible=False)
    ax.margins(x=0.25)
    save(fig, "q1_top_stations_utilisation.png", saved)

    by_city = (usage.groupby("city")
               .apply(lambda d: d["movements_per_day"].sum() / d["capacity"].sum(), include_groups=False)
               .sort_values())
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(by_city.index, by_city.values, color=BLUE, height=0.65)
    for y, v in enumerate(by_city.values):
        ax.text(v, y, f"  {v:.2f}", va="center", color=INK2, fontsize=9)
    ax.set_title("Q1 – Taux d'utilisation moyen par réseau")
    ax.set_xlabel("Rotations par point d'attache et par jour")
    ax.grid(axis="y", visible=False)
    ax.margins(x=0.12)
    save(fig, "q1_utilisation_par_ville.png", saved)

    top = focus.iloc[::-1].head(5)
    notes.append("## Q1 – Stations au plus fort taux d'utilisation\n")
    notes.append(f"Taux d'utilisation = mouvements estimés par jour / nombre de points d'attache. "
                 f"Top 5 à {city} :\n")
    notes += [f"- **{r.station_name}** : {r.usage_rate:.1f} rotations/jour "
              f"({r.movements_per_day:.0f} mouvements/jour, {r.capacity:.0f} places)" for r in top.itertuples()]
    notes.append(f"\nRéseau le plus sollicité : **{by_city.index[-1]}** ({by_city.iloc[-1]:.2f} rotations/place/jour) ; "
                 f"le moins sollicité : **{by_city.index[0]}** ({by_city.iloc[0]:.2f}).\n")


# ---------------------------------------------------------------- Q2 offre insuffisante
def q2(g: dict, saved: list, notes: list) -> None:
    zones = g["zone_supply"]
    zf = zones[zones["network_id"] == FOCUS]
    city = zf["city"].iloc[0] if len(zf) else FOCUS

    fig, ax = plt.subplots(figsize=(9, 7.5))
    sc = ax.scatter(zf["longitude"], zf["latitude"], c=zf["pct_time_short"], cmap=SEQ_ORANGE, vmin=0, vmax=1,
                    s=30 + 25 * zf["n_stations"], edgecolors=SURFACE, linewidths=1)
    bad = zf[zf["supply_insufficient"]]
    ax.scatter(bad["longitude"], bad["latitude"], s=30 + 25 * bad["n_stations"], facecolors="none",
               edgecolors=CRITICAL, linewidths=1.6, label="Offre insuffisante")
    cb = fig.colorbar(sc, ax=ax, shrink=0.7)
    cb.set_label("Part du temps où la maille a < 10 % de vélos", color=INK2)
    cb.outline.set_visible(False)
    map_axes(ax, f"Q2 – Zones où l'offre de vélos est insuffisante ({city}, mailles ≈ 1 km²)")
    ax.legend(loc="upper left")
    save(fig, "q2_carte_zones_offre.png", saved)

    share = (zones.groupby("city")["supply_insufficient"].mean().sort_values())
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(share.index, share.values, color=ORANGE, height=0.65)
    for y, v in enumerate(share.values):
        ax.text(v, y, f"  {pct(v)}", va="center", color=INK2, fontsize=9)
    ax.set_title("Q2 – Part des zones en offre insuffisante par réseau")
    ax.set_xlabel("Part des mailles de 1 km² en déficit")
    ax.xaxis.set_major_formatter(lambda v, _: pct(v))
    ax.grid(axis="y", visible=False)
    ax.margins(x=0.12)
    save(fig, "q2_zones_insuffisantes_par_ville.png", saved)

    worst = zf.sort_values(["pct_time_short", "tension"], ascending=False).head(5)
    notes.append("## Q2 – Zones où l'offre est insuffisante\n")
    notes.append(f"Maillage ≈ 1 km × 1 km. Une zone est en déficit si ses stations cumulent moins de 10 % "
                 f"de vélos plus de 25 % du temps, ou un remplissage moyen < 15 %. "
                 f"À {city} : **{int(zf['supply_insufficient'].sum())} zones sur {len(zf)}** en déficit.\n")
    notes += [f"- Zone ({r.latitude:.4f}, {r.longitude:.4f}), {r.dist_center_km:.1f} km du centre, "
              f"{r.n_stations} stations : sous-dotée {pct(r.pct_time_short)} du temps, "
              f"{r.avg_bikes:.0f} vélos en moyenne pour {r.departures_per_day:.0f} départs/jour"
              for r in worst.itertuples()]
    notes.append("")


# ---------------------------------------------------------------- Q3 pics journaliers
def q3(g: dict, saved: list, notes: list) -> None:
    hp = g["hourly_profile"].dropna(subset=["movements_per_hour"])
    cities = (hp.groupby("city")["movements_per_hour"].mean().sort_values(ascending=False).index.tolist())
    ncols = 5
    nrows = -(-len(cities) // ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(16, 3.3 * nrows), squeeze=False)
    notes.append("## Q3 – Pics d'utilisation journaliers\n")
    for ax, c in zip(axes.flat, cities):
        d = hp[hp["city"] == c]
        for day_type, color in (("Semaine", BLUE), ("Week-end", ORANGE)):
            s = d[d["day_type"] == day_type].sort_values("hour")
            if len(s):
                ax.plot(s["hour"], s["movements_per_hour"], color=color, label=day_type,
                        marker="o", markersize=3)
        ax.set_title(c, fontsize=10)
        ax.set_xlim(0, 23)
        ax.set_xticks([0, 6, 12, 18, 23])
        wk = d[d["day_type"] == "Semaine"]
        src = wk if len(wk) else d
        peak = src.loc[src["movements_per_hour"].idxmax()]
        notes.append(f"- **{c}** : pic à **{int(peak['hour'])}h** ({peak['movements_per_hour']:.0f} mouvements/h, "
                     f"{peak['day_type'].lower()})")
    for ax in list(axes.flat)[len(cities):]:
        ax.set_visible(False)
    axes[0][0].legend(loc="upper left", fontsize=8)
    fig.supxlabel("Heure (Europe/Paris)", color=INK2)
    fig.supylabel("Mouvements estimés par heure", color=INK2)
    fig.suptitle("Q3 – Profil horaire de l'activité des réseaux", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    save(fig, "q3_profil_horaire_villes.png", saved)

    ts = g["network_timeseries"]
    tf = ts[ts["network_id"] == FOCUS].sort_values("collected_at")
    city = tf["city"].iloc[0] if len(tf) else FOCUS
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(tf["collected_at"], tf["share_fleet_in_use"], color=BLUE)
    ax.fill_between(tf["collected_at"], tf["share_fleet_in_use"], color=BLUE, alpha=0.12, linewidth=0)
    ax.set_title(f"Q3 – Part de la flotte en circulation au fil du temps ({city})")
    ax.set_ylabel("Vélos hors station (proxy)")
    ax.yaxis.set_major_formatter(lambda v, _: pct(v))
    ax.set_ylim(bottom=0)
    fig.autofmt_xdate()
    save(fig, "q3_serie_flotte_en_circulation.png", saved)
    notes.append(f"\nSérie temporelle ({city}) : jusqu'à **{pct(tf['share_fleet_in_use'].max())}** de la flotte "
                 f"hors station au maximum observé.\n")


# ---------------------------------------------------------------- Q4 déséquilibres géographiques
def q4(g: dict, saved: list, notes: list) -> None:
    usage = g["station_usage"]
    uf = usage[usage["network_id"] == FOCUS]
    city = uf["city"].iloc[0] if len(uf) else FOCUS

    fig, ax = plt.subplots(figsize=(9, 7.5))
    sc = ax.scatter(uf["longitude"], uf["latitude"], c=uf["avg_fill_rate"], cmap=DIVERGING,
                    norm=TwoSlopeNorm(vmin=0, vcenter=0.5, vmax=1), s=14, edgecolors="none")
    cb = fig.colorbar(sc, ax=ax, shrink=0.7)
    cb.set_label("Taux de remplissage moyen (rouge = vide, bleu = pleine)", color=INK2)
    cb.outline.set_visible(False)
    map_axes(ax, f"Q4 – Disponibilité moyenne des vélos par station ({city})")
    save(fig, "q4_carte_remplissage.png", saved)

    gb = g["geo_balance"]
    order = ["0-2 km", "2-4 km", "4-6 km", "6-10 km", "> 10 km"]
    periods = [("Pointe matin (7h-10h)", BLUE), ("Journée (10h-16h)", AQUA),
               ("Pointe soir (16h-20h)", ORANGE), ("Soir/nuit (20h-7h)", YELLOW)]
    gf = gb[gb["network_id"] == FOCUS]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    for period, color in periods:
        s = gf[gf["period"] == period].set_index("dist_band").reindex(order).dropna(subset=["avg_fill_rate"])
        if len(s):
            ax.plot(s.index, s["avg_fill_rate"], color=color, marker="o", markersize=6, label=period)
    ax.axhline(0.5, color=AXIS, linewidth=1)
    ax.set_title(f"Q4 – Remplissage selon la distance au centre ({city})")
    ax.set_xlabel("Distance de la station au centre-ville")
    ax.set_ylabel("Taux de remplissage moyen")
    ax.yaxis.set_major_formatter(lambda v, _: pct(v))
    ax.legend(loc="best", fontsize=8)
    save(fig, "q4_remplissage_distance_centre.png", saved)

    pivot = (usage.groupby(["city", "dist_band"])
             .apply(lambda d: d["avg_bikes"].sum() / d["capacity"].sum(), include_groups=False)
             .unstack().reindex(columns=order))
    fig, ax = plt.subplots(figsize=(8, 0.45 * len(pivot) + 1.5))
    im = ax.imshow(pivot.values, cmap=DIVERGING, norm=TwoSlopeNorm(vmin=0, vcenter=0.5, vmax=1), aspect="auto")
    ax.set_xticks(range(len(order)), order)
    ax.set_yticks(range(len(pivot)), pivot.index)
    ax.grid(False)
    for (i, j), v in pd.DataFrame(pivot.values).stack().items():
        ax.text(j, i, pct(v), ha="center", va="center", fontsize=8, color=INK)
    ax.set_title("Q4 – Remplissage moyen par ville et distance au centre")
    cb = fig.colorbar(im, ax=ax, shrink=0.8)
    cb.outline.set_visible(False)
    save(fig, "q4_heatmap_villes_distance.png", saved)

    centre = uf[uf["dist_center_km"] < 2]["avg_fill_rate"].mean()
    periph = uf[uf["dist_center_km"] >= 6]["avg_fill_rate"].mean()
    morning = gf[gf["period"] == "Pointe matin (7h-10h)"].set_index("dist_band")["avg_fill_rate"]
    notes.append("## Q4 – Déséquilibres géographiques\n")
    notes.append(f"À {city}, remplissage moyen **{pct(centre)}** à moins de 2 km du centre contre "
                 f"**{pct(periph)}** au-delà de 6 km (écart de {abs(centre - periph) * 100:.0f} points).")
    if len(morning):
        notes.append(f"En pointe du matin : {', '.join(f'{b} = {pct(v)}' for b, v in morning.reindex(order).dropna().items())}.")
    notes.append(f"Stations vides plus de la moitié du temps : **{int((uf['pct_time_empty'] > 0.5).sum())}** ; "
                 f"pleines plus de la moitié du temps : **{int((uf['pct_time_full'] > 0.5).sum())}**.\n")


# ---------------------------------------------------------------- Q5 stations critiques
def q5(g: dict, saved: list, notes: list) -> None:
    crit = g["critical_stations"]
    usage = g["station_usage"]
    cf = crit[(crit["network_id"] == FOCUS) & crit["status"].notna()]
    uf = usage[usage["network_id"] == FOCUS]
    city = uf["city"].iloc[0] if len(uf) else FOCUS
    empty = cf[cf["status"].str.startswith("Vide")]
    full = cf[cf["status"].str.startswith("Pleine")]

    fig, ax = plt.subplots(figsize=(9, 7.5))
    ax.scatter(uf["longitude"], uf["latitude"], s=6, color=AXIS, label="Autres stations")
    ax.scatter(empty["longitude"], empty["latitude"], s=28, color=CRITICAL, edgecolors=SURFACE, linewidths=0.8,
               label=f"Vide chronique – à réapprovisionner ({len(empty)})")
    ax.scatter(full["longitude"], full["latitude"], s=28, color="#1c5cab", edgecolors=SURFACE, linewidths=0.8,
               marker="s", label=f"Pleine chronique – à délester ({len(full)})")
    map_axes(ax, f"Q5 – Stations critiques nécessitant un rééquilibrage ({city})")
    ax.legend(loc="upper left", fontsize=8)
    save(fig, "q5_carte_stations_critiques.png", saved)

    top = cf.nlargest(15, "priority_score").iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 6))
    colors = [CRITICAL if s.startswith("Vide") else "#1c5cab" for s in top["status"]]
    ax.barh(top["station_name"].str.slice(0, 40), top["priority_score"], color=colors, height=0.7)
    for y, (v, r) in enumerate(zip(top["priority_score"], top["rebalance_bikes"])):
        ax.text(v, y, f"  {v:.0f}   ({r:+d} vélos)", va="center", color=INK2, fontsize=8)
    ax.set_title(f"Q5 – Priorités de rééquilibrage ({city})")
    ax.set_xlabel("Score de priorité (temps en rupture × activité)  –  rouge : vide, bleu : pleine")
    ax.grid(axis="y", visible=False)
    ax.margins(x=0.25)
    save(fig, "q5_priorites_reequilibrage.png", saved)

    crit.to_csv(OUT / "stations_critiques.csv", index=False, encoding="utf-8-sig")
    notes.append("## Q5 – Stations critiques\n")
    notes.append(f"Critère : station vide (ou pleine) plus de 25 % du temps observé. "
                 f"À {city} : **{len(empty)} stations à réapprovisionner**, **{len(full)} à délester**. "
                 f"Besoin estimé pour revenir à 50 % de remplissage : "
                 f"+{int(empty['rebalance_bikes'].clip(lower=0).sum())} vélos à déposer, "
                 f"{int(full['rebalance_bikes'].clip(upper=0).sum())} à retirer.\n")
    notes += [f"- **{r.station_name}** – {r.status} (vide {pct(r.pct_time_empty)}, pleine {pct(r.pct_time_full)}"
              f" du temps ; action : {r.rebalance_bikes:+d} vélos)" for r in top.iloc[::-1].head(5).itertuples()]
    notes.append("\nListe complète (tous réseaux) : `outputs/stations_critiques.csv`.\n")


def upload(paths: list) -> None:
    s3 = boto3.client("s3", endpoint_url=config.MINIO_ENDPOINT, aws_access_key_id=config.MINIO_ACCESS_KEY,
                      aws_secret_access_key=config.MINIO_SECRET_KEY, region_name="us-east-1")
    for p in paths:
        s3.upload_file(str(p), config.BUCKET, f"{config.REPORTS_PREFIX}/{p.relative_to(OUT).as_posix()}")
    print(f"[viz] {len(paths)} fichiers publiés dans s3://{config.BUCKET}/{config.REPORTS_PREFIX}/")


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    spark = get_spark("urbanhub-figures")
    g = load_gold(spark)
    spark.stop()

    # Réseaux sans activité mesurable (aucun mouvement, stations vides à chaque relevé, ex. le-velo
    # à Marseille) : exclus des analyses, comme dans le dashboard et la Partie 4
    per_net = g["network_timeseries"].groupby("network_id").agg(
        mv=("movements", "sum"), empty=("share_stations_empty", "mean"))
    inactive = per_net[(per_net["mv"] == 0) & (per_net["empty"] >= 0.99)].index.tolist()
    g = {n: df[~df["network_id"].isin(inactive)] for n, df in g.items()}

    ts = g["network_timeseries"]
    saved, notes = [], [
        "# UrbanHub – Partie 2 : mobilité vélo en libre-service (CityBikes)\n",
        f"Période observée : **{ts['collected_at'].min():%d/%m/%Y %H:%M}** → **{ts['collected_at'].max():%d/%m/%Y %H:%M}** "
        f"({ts['collected_at'].nunique()} snapshots, {g['station_usage']['station_id'].nunique()} stations, "
        f"{g['station_usage']['city'].nunique()} villes). Réseau détaillé : `{FOCUS}`.\n",
        "> Indicateurs calculés à partir des variations du nombre de vélos entre snapshots consécutifs "
        "(≈ toutes les 2 min 30) : ce sont des estimations basses de l'activité réelle.\n",
    ]
    if inactive:
        notes.append(f"> Réseaux exclus (0 vélo et aucun mouvement à chaque relevé, flux CityBikes inexploitable) : "
                     f"{', '.join(f'`{n}`' for n in inactive)}.\n")
    for question in (q1, q2, q3, q4, q5):
        question(g, saved, notes)

    report = OUT / "rapport_partie2.md"
    report.write_text("\n".join(notes) + "\n", encoding="utf-8")
    print(f"[viz] {report}")
    upload(saved + [report, OUT / "stations_critiques.csv"])


if __name__ == "__main__":
    main()

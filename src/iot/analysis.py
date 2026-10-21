"""Analyses de la Partie 3 (flux IoT) : 4 questions metier + table curated.

Usage (depuis la racine) :
    python -m src.iot.analysis

Produit :
  - curated/iot (Data Lake) : pollution horaire par ville  [city, pollutant, timestamp, value, n_sensors]
  - reports/iot/tables/*.csv
  - reports/iot/figures/*.png
"""
import logging

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import config
from .storage import Store

log = logging.getLogger("iot.analysis")

POLLUTANTS = ["pm25", "pm10", "no2", "o3", "co"]
LABELS = {"pm25": "PM2.5", "pm10": "PM10", "no2": "NO2", "o3": "O3", "co": "CO"}

# Valeurs guides OMS 2021 sur 24 h, en ug/m3 (O3 : maximum journalier de la moyenne sur 8 h ;
# CO : 4 mg/m3 = 4000 ug/m3). A verifier/citer dans le rapport.
WHO = {"pm25": 15, "pm10": 45, "no2": 25, "o3": 100, "co": 4000}

MIN_HOURS_PER_DAY = 18      # un jour n'est retenu que s'il a assez d'heures de mesure
Z_THRESHOLD = 3.5           # seuil du z-score robuste pour les anomalies
MAX_GAP_H = 3               # ecart max (heures) entre deux heures anormales d'un meme episode
MIN_EPISODE_H = 3           # duree minimale d'un episode
MIN_SENSORS = 3             # nb minimal de capteurs par heure pour detecter une anomalie


# ------------------------------------------------------------------ preparation
def hourly_by_sensor(clean: pd.DataFrame) -> pd.DataFrame:
    """Moyenne horaire par capteur (neutralise les frequences d'emission differentes)."""
    df = clean.copy()
    df["hour"] = df["timestamp"].dt.floor("h")
    keys = ["sensor_id", "pollutant", "city", "location_name", "latitude", "longitude", "hour"]
    return df.groupby(keys, as_index=False, observed=True)["value"].mean()


def hourly_by_city(hs: pd.DataFrame) -> pd.DataFrame:
    """Table 'curated' : une ligne par (ville, polluant, heure UTC)."""
    g = hs.groupby(["city", "pollutant", "hour"], observed=True)
    out = g.agg(value=("value", "mean"), value_median=("value", "median"),
                n_sensors=("sensor_id", "nunique")).reset_index()
    return out.rename(columns={"hour": "timestamp"})

# ------------------------------------------------------------------ Q1 : zones les plus polluees
def q1_ranking(hs: pd.DataFrame) -> pd.DataFrame:
    g = hs.groupby(["pollutant", "city", "location_name", "latitude", "longitude"], observed=True)
    out = g.agg(mean=("value", "mean"), p95=("value", lambda s: s.quantile(0.95)),
                n_hours=("value", "size")).reset_index()
    return out.sort_values(["pollutant", "mean"], ascending=[True, False])


def fig_ranking(rank: pd.DataFrame, path) -> None:
    pols = [p for p in POLLUTANTS if p in set(rank["pollutant"])]
    fig, axes = plt.subplots(2, 3, figsize=(17, 9))
    for ax, p in zip(axes.ravel(), pols):
        top = rank[rank["pollutant"] == p].head(10).iloc[::-1]
        ax.barh(top["location_name"].str.slice(0, 28) + " (" + top["city"] + ")", top["mean"])
        ax.axvline(WHO[p], color="red", ls="--", lw=1, label="valeur guide OMS")
        ax.set_title(f"{LABELS[p]} : 10 stations les plus elevees (µg/m³)")
        ax.legend(fontsize=8)
        ax.tick_params(axis="y", labelsize=7)
    for ax in axes.ravel()[len(pols):]:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fig_maps(rank: pd.DataFrame, pollutant: str, path) -> None:
    cities = sorted(rank["city"].unique())
    sub = rank[rank["pollutant"] == pollutant]
    if sub.empty:
        return
    fig, axes = plt.subplots(1, len(cities), figsize=(4.2 * len(cities), 4.2))
    vmin, vmax = sub["mean"].min(), sub["mean"].max()
    sc = None
    for ax, c in zip(np.atleast_1d(axes), cities):
        d = sub[sub["city"] == c]
        if not d.empty:
            sc = ax.scatter(d["longitude"], d["latitude"], c=d["mean"], s=90, cmap="YlOrRd",
                            vmin=vmin, vmax=vmax, edgecolor="k")
        ax.set_title(c)
        ax.set_xlabel("longitude")
        ax.set_aspect(1 / np.cos(np.radians(d["latitude"].mean() if len(d) else 45)))
    if sc is not None:
        fig.colorbar(sc, ax=axes, label=f"{LABELS[pollutant]} moyen (µg/m³)", shrink=0.8)
    fig.suptitle(f"Niveaux moyens de {LABELS[pollutant]} par station")
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


# ------------------------------------------------------------------ Q2 : variation journaliere
def q2_daily_profile(ch: pd.DataFrame) -> pd.DataFrame:
    df = ch.copy()
    df["local_hour"] = df["timestamp"].dt.tz_convert(config.TIMEZONE).dt.hour
    return (df.groupby(["pollutant", "city", "local_hour"], observed=True)["value"]
              .agg(["mean", "median"]).reset_index())


def fig_profile(prof: pd.DataFrame, path) -> None:
    pols = [p for p in POLLUTANTS if p in set(prof["pollutant"])]
    fig, axes = plt.subplots(2, 3, figsize=(17, 8), sharex=True)
    for ax, p in zip(axes.ravel(), pols):
        for city, d in prof[prof["pollutant"] == p].groupby("city"):
            ax.plot(d["local_hour"], d["mean"], marker="o", ms=3, label=city)
        ax.set_title(f"{LABELS[p]} : profil moyen par heure")
        ax.set_xlabel(f"heure locale ({config.TIMEZONE})")
        ax.set_ylabel("µg/m³")
        ax.set_xticks(range(0, 24, 3))
        ax.legend(fontsize=7)
    for ax in axes.ravel()[len(pols):]:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


# ------------------------------------------------------------------ Q3 : polluants dominants
def _daily_metric(s: pd.Series, pollutant: str) -> pd.Series:
    """Metrique journaliere comparee a la valeur guide (jours locaux, couverture minimale)."""
    s = s.asfreq("h").tz_convert(config.TIMEZONE)
    count = s.resample("D").count()
    if pollutant == "o3":
        daily = s.rolling(8, min_periods=6).mean().resample("D").max()
    else:
        daily = s.resample("D").mean()
    return daily[count >= MIN_HOURS_PER_DAY].dropna()


def q3_who(ch: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (city, p), d in ch.groupby(["city", "pollutant"], observed=True):
        daily = _daily_metric(d.set_index("timestamp")["value"], p)
        if len(daily) < 5:
            continue
        rows.append({
            "city": city, "pollutant": p, "valid_days": len(daily),
            "mean_daily_metric": daily.mean(), "who_guideline": WHO[p],
            "ratio_to_who": daily.mean() / WHO[p],
            "days_above_who": int((daily > WHO[p]).sum()),
            "pct_days_above_who": 100 * (daily > WHO[p]).mean(),
        })
    out = pd.DataFrame(rows)
    out["dominant_in_city"] = out["ratio_to_who"] == out.groupby("city")["ratio_to_who"].transform("max")
    return out.sort_values(["city", "ratio_to_who"], ascending=[True, False])


def fig_who(who: pd.DataFrame, path) -> None:
    piv = who.pivot(index="city", columns="pollutant", values="pct_days_above_who")
    piv = piv[[p for p in POLLUTANTS if p in piv.columns]]
    ratio = who.pivot(index="city", columns="pollutant", values="ratio_to_who")[piv.columns]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    piv.rename(columns=LABELS).plot.bar(ax=axes[0], rot=0)
    axes[0].set_ylabel("% de jours au-dessus de la valeur guide OMS")
    axes[0].set_title("Jours de depassement OMS")
    ratio.rename(columns=LABELS).plot.bar(ax=axes[1], rot=0)
    axes[1].axhline(1, color="red", ls="--", lw=1)
    axes[1].set_ylabel("niveau moyen / valeur guide OMS")
    axes[1].set_title("Poids relatif de chaque polluant (>1 = au-dessus de la valeur guide)")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


# ------------------------------------------------------------------ Q4 : episodes anormaux
def q4_episodes(ch: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """z-score robuste par rapport au profil horaire median ; regroupement en episodes."""
    flagged_frames, episodes = [], []
    for (city, p), d in ch.groupby(["city", "pollutant"], observed=True):
        d = d[d["n_sensors"] >= MIN_SENSORS].sort_values("timestamp").copy()
        d["value"] = d["value_median"]  # mediane inter-capteurs : robuste a un capteur aberrant
        if len(d) < 24 * 7:
            continue
        d["local_hour"] = d["timestamp"].dt.tz_convert(config.TIMEZONE).dt.hour
        base = d.groupby("local_hour")["value"].transform("median")
        resid = d["value"] - base
        mad = (resid - resid.median()).abs().median()
        if mad == 0 or np.isnan(mad):
            continue
        d["z"] = (resid - resid.median()) / (1.4826 * mad)
        d["baseline"] = base
        d["anomaly"] = d["z"] > Z_THRESHOLD
        d["city"], d["pollutant"] = city, p
        flagged_frames.append(d)

        hrs = d.loc[d["anomaly"], "timestamp"]
        if hrs.empty:
            continue
        new_ep = hrs.diff() > pd.Timedelta(hours=MAX_GAP_H)
        ep_id = new_ep.cumsum()
        for _, idx in hrs.groupby(ep_id).groups.items():
            e = d.loc[idx]
            if len(e) < MIN_EPISODE_H:
                continue
            episodes.append({
                "city": city, "pollutant": p, "start": e["timestamp"].min(), "end": e["timestamp"].max(),
                "hours_flagged": len(e), "peak_value": e["value"].max(),
                "mean_value": e["value"].mean(), "baseline_median": e["baseline"].mean(),
                "peak_z": e["z"].max(),
            })
    series = pd.concat(flagged_frames, ignore_index=True) if flagged_frames else pd.DataFrame()
    eps = pd.DataFrame(episodes)
    if not eps.empty:
        eps = eps.sort_values("peak_z", ascending=False).reset_index(drop=True)
    return series, eps


def fig_episodes(series: pd.DataFrame, eps: pd.DataFrame, path) -> None:
    if eps.empty:
        return
    top = eps.groupby(["city", "pollutant"])["hours_flagged"].sum().idxmax()
    city, p = top
    d = series[(series["city"] == city) & (series["pollutant"] == p)]
    fig, ax = plt.subplots(figsize=(14, 4.5))
    ax.plot(d["timestamp"], d["value"], lw=0.8, label="moyenne horaire")
    ax.plot(d["timestamp"], d["baseline"], lw=0.8, color="gray", label="profil horaire median")
    ax.scatter(d.loc[d["anomaly"], "timestamp"], d.loc[d["anomaly"], "value"],
               color="red", s=14, label=f"heures anormales (z > {Z_THRESHOLD})")
    for _, e in eps[(eps["city"] == city) & (eps["pollutant"] == p)].iterrows():
        ax.axvspan(e["start"], e["end"], color="red", alpha=0.15)
    ax.axhline(WHO[p], color="orange", ls="--", lw=1, label="valeur guide OMS (24 h)")
    ax.set_title(f"Episodes anormaux : {LABELS[p]} a {city}")
    ax.set_ylabel("µg/m³")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


# ------------------------------------------------------------------ orchestration
def run() -> None:
    store = Store()
    clean = store.read("clean")
    if clean.empty:
        raise SystemExit("Aucune donnee 'clean' : lance d'abord le backfill.")
    log.info("%d mesures nettoyees, du %s au %s", len(clean), clean["timestamp"].min(), clean["timestamp"].max())

    hs = hourly_by_sensor(clean)
    ch = hourly_by_city(hs)

    # table curated pour l'integration (Partie 4) : on repart d'une couche vide
    if store.fs.exists(f"{store.root}/curated/iot"):
        store.fs.rm(f"{store.root}/curated/iot", recursive=True)
    store.write(ch, "curated")
    log.info("curated/iot : %d lignes (ville x polluant x heure)", len(ch))

    tables = config.REPORTS_DIR / "tables"
    figs = config.REPORTS_DIR / "figures"
    tables.mkdir(parents=True, exist_ok=True)
    figs.mkdir(parents=True, exist_ok=True)

    rank = q1_ranking(hs)
    rank.to_csv(tables / "q1_ranking_stations.csv", index=False)
    fig_ranking(rank, figs / "q1_top_stations.png")
    for p in ("no2", "pm25"):
        fig_maps(rank, p, figs / f"q1_carte_{p}.png")

    prof = q2_daily_profile(ch)
    prof.to_csv(tables / "q2_profil_horaire.csv", index=False)
    fig_profile(prof, figs / "q2_profil_journalier.png")

    who = q3_who(ch)
    who.to_csv(tables / "q3_polluants_vs_oms.csv", index=False)
    fig_who(who, figs / "q3_oms.png")

    series, eps = q4_episodes(ch)
    eps.to_csv(tables / "q4_episodes.csv", index=False)
    fig_episodes(series, eps, figs / "q4_episodes.png")

    pd.set_option("display.width", 200, "display.max_columns", 20)
    print("\n=== Q1 : station la plus elevee par polluant ===")
    print(rank.groupby("pollutant").head(1)[["pollutant", "city", "location_name", "mean"]].to_string(index=False))
    print("\n=== Q2 : heure locale du pic moyen, par ville et polluant ===")
    peak = prof.loc[prof.groupby(["pollutant", "city"])["mean"].idxmax()]
    print(peak.pivot(index="city", columns="pollutant", values="local_hour").to_string())
    print("\n=== Q3 : niveau moyen / valeur guide OMS (polluant dominant = max par ville) ===")
    print(who.pivot(index="city", columns="pollutant", values="ratio_to_who").round(2).to_string())
    print("\n=== Q4 : episodes anormaux ===")
    print(f"{len(eps)} episodes" + (f", les 10 plus intenses :\n{eps.head(10).to_string(index=False)}" if len(eps) else ""))
    print(f"\nTableaux : {tables}\nFigures  : {figs}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
"""Partie 4 : fusion des flux meteo, pollution et velos en tables gold croisees.

Usage (racine du repo) :  PYTHONPATH=src python -m croise.fusion
                          IOT_STORE=s3 PYTHONPATH=src python -m croise.fusion   (ecriture dans MinIO)

Lit (data/, voir common.local_lake) :
    meteo_horaire_ville      Open-Meteo, ville x heure (Partie 1, Ali)
    pollution_horaire_ville  OpenAQ, ville x polluant x heure (Partie 3, Yassine)
    network_timeseries       CityBikes, reseau x releve (Partie 2, Antoine)
Ecrit (gold/, meme Store que la Partie 3) :
    croise_horaire_ville     une ligne par ville x heure UTC : meteo + polluants + activite velo
    croise_journalier_ville  une ligne par ville x jour (heure de Paris)

Cle de jointure : city + timestamp (debut de l'heure, UTC).
"""
import logging

import pandas as pd

from common import local_lake
from iot.storage import Store

log = logging.getLogger("croise.fusion")

TZ = "Europe/Paris"
WEATHER = ["temperature", "humidity", "precipitation", "wind_speed", "wind_direction", "pressure",
           "visibility", "cloud_cover"]
POLLUTANTS = ["pm25", "pm10", "no2", "o3", "co"]
MAX_GAP_MIN = 10        # deux releves velo plus espaces ne sont pas consecutifs (regle de la Partie 2)

GOLD_HOURLY = "gold/croise_horaire_ville"
GOLD_DAILY = "gold/croise_journalier_ville"


def _require(name: str) -> pd.DataFrame:
    df = local_lake.load(name)
    if df is None:
        raise FileNotFoundError(f"Table {name} introuvable dans {local_lake.DATA_DIR}")
    return df


# ------------------------------------------------------------------ preparation de chaque flux
def weather_hourly(meteo: pd.DataFrame) -> pd.DataFrame:
    """Meteo ville x heure : on ne garde que les heures ou au moins une variable est renseignee."""
    df = meteo.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.dropna(subset=WEATHER, how="all")
    return df[["city", "timestamp"] + WEATHER]


def pollution_hourly(pol: pd.DataFrame) -> pd.DataFrame:
    """Polluants en colonnes (moyenne entre capteurs de la ville, en ug/m3)."""
    df = pol.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    wide = df.pivot_table(index=["city", "timestamp"], columns="pollutant", values="value", aggfunc="mean")
    return wide.reindex(columns=POLLUTANTS).reset_index().rename_axis(columns=None)


def inactive_networks(ts: pd.DataFrame) -> list[str]:
    """Reseaux sans activite mesurable : aucun mouvement et stations vides a chaque releve (cf. Partie 2)."""
    per_city = ts.groupby("city").agg(mv=("movements", "sum"), empty=("share_stations_empty", "mean"))
    return sorted(per_city[(per_city["mv"] == 0) & (per_city["empty"] >= 0.99)].index)


def bikes_hourly(ts: pd.DataFrame) -> pd.DataFrame:
    """Activite velo ville x heure UTC, a partir des releves consecutifs (heures CityBikes en heure de Paris)."""
    df = ts[~ts["city"].isin(inactive_networks(ts))].copy()
    local = pd.to_datetime(df["collected_at"]).dt.tz_localize(TZ, ambiguous="NaT", nonexistent="shift_forward")
    df["timestamp"] = local.dt.tz_convert("UTC").dt.floor("h")
    ok = df[df["interval_min"] <= MAX_GAP_MIN]
    g = ok.groupby(["city", "timestamp"]).agg(
        movements=("movements", "sum"), bike_observed_min=("interval_min", "sum"),
        bike_share_in_use=("share_fleet_in_use", "mean"),
        bike_share_stations_empty=("share_stations_empty", "mean"),
        bike_share_stations_full=("share_stations_full", "mean")).reset_index()
    g["bike_movements_per_hour"] = g["movements"] / g["bike_observed_min"] * 60
    return g.drop(columns="movements")


# ------------------------------------------------------------------ fusion
def build_hourly(weather: pd.DataFrame, pollution: pd.DataFrame, bikes: pd.DataFrame) -> pd.DataFrame:
    """Table de faits horaire : toutes les heures ou la meteo ou la pollution existent, + velos si disponibles."""
    out = weather.merge(pollution, on=["city", "timestamp"], how="outer")
    out = out.merge(bikes, on=["city", "timestamp"], how="left")
    local = out["timestamp"].dt.tz_convert(TZ)
    out["date_local"] = local.dt.strftime("%Y-%m-%d")
    out["hour_local"] = local.dt.hour
    out["weekday"] = local.dt.weekday                      # 0 = lundi
    out["is_weekend"] = out["weekday"] >= 5
    out["has_weather"] = out[WEATHER].notna().any(axis=1)
    out["has_pollution"] = out[POLLUTANTS].notna().any(axis=1)
    out["has_bikes"] = out["bike_movements_per_hour"].notna()
    first = ["city", "timestamp", "date_local", "hour_local", "weekday", "is_weekend"]
    flags = ["has_weather", "has_pollution", "has_bikes"]
    rest = [c for c in out.columns if c not in first + flags]
    return out[first + rest + flags].sort_values(["city", "timestamp"]).reset_index(drop=True)


def build_daily(hourly: pd.DataFrame) -> pd.DataFrame:
    """Agregat ville x jour (heure de Paris)."""
    h = hourly.assign(_mv=hourly["bike_movements_per_hour"] * hourly["bike_observed_min"] / 60)
    g = h.groupby(["city", "date_local"])
    out = g.agg(
        weather_hours=("has_weather", "sum"), pollution_hours=("has_pollution", "sum"),
        temp_mean=("temperature", "mean"), temp_min=("temperature", "min"), temp_max=("temperature", "max"),
        humidity_mean=("humidity", "mean"), precipitation_sum=("precipitation", "sum"),
        wind_mean=("wind_speed", "mean"), wind_max=("wind_speed", "max"), pressure_mean=("pressure", "mean"),
        visibility_mean=("visibility", "mean"), cloud_mean=("cloud_cover", "mean"),
        **{f"{p}_mean": (p, "mean") for p in POLLUTANTS},
        no2_max=("no2", "max"), o3_max=("o3", "max"),
        bike_observed_min=("bike_observed_min", "sum"), _mv=("_mv", "sum"),
    ).reset_index()
    out["bike_movements_per_hour"] = (out["_mv"] / out["bike_observed_min"] * 60).where(out["bike_observed_min"] > 0)
    out["weekday"] = pd.to_datetime(out["date_local"]).dt.weekday
    out["is_weekend"] = out["weekday"] >= 5
    # Somme de pluie : NaN (et non 0) si aucune heure de meteo ce jour-la
    out.loc[out["weather_hours"] == 0, "precipitation_sum"] = float("nan")
    return out.drop(columns="_mv")


def run() -> tuple[pd.DataFrame, pd.DataFrame]:
    meteo, pol, ts = (_require(n) for n in ["meteo_horaire_ville", "pollution_horaire_ville", "network_timeseries"])
    weather, pollution, bikes = weather_hourly(meteo), pollution_hourly(pol), bikes_hourly(ts)
    dropped = sorted(set(bikes["city"]) - set(weather["city"]) - set(pollution["city"]))
    if dropped:
        log.info("Reseaux velo sans meteo ni pollution (hors fusion) : %s", ", ".join(dropped))
    if inactive_networks(ts):
        log.info("Reseaux velo inactifs exclus : %s", ", ".join(inactive_networks(ts)))

    hourly = build_hourly(weather, pollution, bikes)
    daily = build_daily(hourly)

    store = Store()
    store.delete_prefix(GOLD_HOURLY)
    store.write_parquet(hourly, GOLD_HOURLY)
    store.delete_prefix(GOLD_DAILY)
    store.write_table(daily, f"{GOLD_DAILY}/part-0.parquet")

    log.info("%s : %d lignes (%s -> %s)", GOLD_HOURLY, len(hourly), hourly["timestamp"].min(), hourly["timestamp"].max())
    log.info("%s : %d lignes", GOLD_DAILY, len(daily))
    both = hourly["has_weather"] & hourly["has_pollution"]
    log.info("Heures meteo x pollution : %d | meteo x velos : %d | les trois : %d",
             both.sum(), (hourly["has_weather"] & hourly["has_bikes"]).sum(), (both & hourly["has_bikes"]).sum())
    return hourly, daily


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s")
    run()

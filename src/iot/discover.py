"""Decouverte des capteurs OpenAQ autour des villes cibles.

Usage (depuis la racine du repo) :
    python -m src.iot.discover --active-days 7        (local : IOT_STORE=local)
Dans Docker : python -m iot.discover
"""
import argparse
import logging
import math
from datetime import datetime, timedelta, timezone

import pandas as pd

from . import config
from .openaq_client import OpenAQClient
from .storage import Store

log = logging.getLogger("iot.discover")


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _utc(value) -> str | None:
    """datetimeFirst/datetimeLast : dict {'utc':..., 'local':...} ou chaine."""
    if isinstance(value, dict):
        return value.get("utc")
    return value


def discover(active_days: int | None = None) -> pd.DataFrame:
    config.check_api_key()
    client = OpenAQClient()
    rows = []

    for city in config.CITIES:
        coords = f"{city['lat']},{city['lon']}"
        n_loc = 0
        for loc in client.paginate(
            "/locations", {"coordinates": coords, "radius": config.RADIUS_M}
        ):
            n_loc += 1
            c = loc.get("coordinates") or {}
            lat, lon = c.get("latitude"), c.get("longitude")
            if lat is None or lon is None:
                continue
            for s in loc.get("sensors", []):
                p = s.get("parameter") or {}
                name = (p.get("name") or "").lower()
                if name not in config.POLLUTANTS:
                    continue
                rows.append({
                    "sensor_id": s["id"],
                    "location_id": loc["id"],
                    "location_name": loc.get("name"),
                    "pollutant": name,
                    "unit": p.get("units"),
                    "parameter_id": p.get("id"),
                    "latitude": lat,
                    "longitude": lon,
                    "city": city["name"],
                    "distance_km": haversine_km(city["lat"], city["lon"], lat, lon),
                    "datetime_first": _utc(loc.get("datetimeFirst")),
                    "datetime_last": _utc(loc.get("datetimeLast")),
                })
        log.info("%s : %d stations dans %d km", city["name"], n_loc, config.RADIUS_M // 1000)

    df = pd.DataFrame(rows)
    if df.empty:
        log.warning("Aucun capteur trouve.")
        return df

    # Un capteur proche de deux villes est rattache a la plus proche
    df = (df.sort_values("distance_km")
            .drop_duplicates("sensor_id")
            .reset_index(drop=True))

    for col in ("datetime_first", "datetime_last"):
        df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")

    if active_days is not None:
        limit = datetime.now(timezone.utc) - timedelta(days=active_days)
        df = df[df["datetime_last"] >= limit].reset_index(drop=True)

    return df


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--active-days", type=int, default=None,
                    help="ne garder que les capteurs ayant mesure dans les N derniers jours")
    args = ap.parse_args()

    df = discover(args.active_days)
    if df.empty:
        return

    Store().write_table(df, config.SENSORS_KEY)
    log.info("%d capteurs ecrits dans %s", len(df), config.SENSORS_KEY)

    print("\nCapteurs par ville et polluant :")
    print(df.pivot_table(index="city", columns="pollutant",
                         values="sensor_id", aggfunc="count", fill_value=0))
    print("\nUnites rencontrees :")
    print(df.groupby(["pollutant", "unit"]).size())


if __name__ == "__main__":
    main()
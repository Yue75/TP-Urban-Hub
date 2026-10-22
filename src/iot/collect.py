"""Collecte des mesures OpenAQ : backfill historique et ingestion reguliere (flux IoT).

Usage (depuis la racine) :
    python -m src.iot.collect backfill --days 30 --workers 4
    python -m src.iot.collect live --interval 15
    python -m src.iot.collect live --once
Dans Docker : python -m iot.collect ...   |   Prerequis : discover
"""
import argparse
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pandas as pd

from . import config
from .clean import clean
from .openaq_client import OpenAQClient
from .storage import Store

log = logging.getLogger("iot.collect")


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _period_end(r: dict) -> str | None:
    """Horodatage = fin de la periode de mesure (meme convention que 'latest')."""
    p = r.get("period") or {}
    dt = p.get("datetimeTo") or p.get("datetimeFrom") or {}
    return dt.get("utc")


def load_sensors(store: Store) -> pd.DataFrame:
    if not store.exists(config.SENSORS_KEY):
        raise SystemExit("Table des capteurs absente : lance d'abord discover.")
    return store.read_table(config.SENSORS_KEY)


def _keys(df: pd.DataFrame) -> pd.MultiIndex:
    """Cles (capteur, instant) comparables meme si les unites de temps different."""
    ts = pd.to_datetime(df["timestamp"], utc=True).dt.as_unit("ns")
    return pd.MultiIndex.from_arrays([df["sensor_id"].astype("int64"), ts])


# --------------------------------------------------------------------------- backfill
def fetch_sensor(client, sensor_id: int, dt_from: datetime, dt_to: datetime) -> list[dict]:
    rows = []
    params = {"datetime_from": _iso(dt_from), "datetime_to": _iso(dt_to)}
    for r in client.paginate(f"/sensors/{sensor_id}/measurements", params):
        rows.append({"sensor_id": sensor_id, "timestamp": _period_end(r), "value": r.get("value")})
    return rows


def backfill(days: int, workers: int = 4, chunk: int = 40, client=None, store=None) -> None:
    config.check_api_key()
    client = client or OpenAQClient()
    store = store or Store()
    sensors = load_sensors(store)
    ids = sensors["sensor_id"].tolist()
    dt_to = datetime.now(timezone.utc)
    dt_from = dt_to - timedelta(days=days)
    log.info("Backfill de %d capteurs sur %d jours", len(ids), days)

    # Idempotence : on ne reecrit pas les mesures deja presentes (relance apres interruption)
    existing = store.read_parquet(config.SILVER_PREFIX)
    existing_idx = _keys(existing) if not existing.empty else None

    for i in range(0, len(ids), chunk):
        batch_ids = ids[i:i + chunk]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = pool.map(lambda sid: fetch_sensor(client, sid, dt_from, dt_to), batch_ids)
            rows = [r for res in results for r in res]
        raw = pd.DataFrame(rows, columns=["sensor_id", "timestamp", "value"])
        raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True, errors="coerce")
        raw = raw.dropna(subset=["timestamp"]).drop_duplicates(["sensor_id", "timestamp"])
        if existing_idx is not None and not raw.empty:
            raw = raw[~_keys(raw).isin(existing_idx)]
        raw["ingested_at"] = pd.Timestamp.now(tz="UTC")
        store.write_parquet(raw, config.BRONZE_PREFIX)
        n_clean = store.write_parquet(clean(raw, sensors), config.SILVER_PREFIX)
        log.info("Capteurs %d-%d / %d : %d nouvelles mesures brutes, %d propres",
                 i + 1, i + len(batch_ids), len(ids), len(raw), n_clean)


# --------------------------------------------------------------------------- live
def init_last_seen(store: Store) -> dict[int, pd.Timestamp]:
    df = store.read_parquet(config.SILVER_PREFIX)
    if df.empty:
        return {}
    return df.groupby("sensor_id")["timestamp"].max().to_dict()


def poll_once(client, sensors: pd.DataFrame, last_seen: dict) -> pd.DataFrame:
    wanted = set(sensors["sensor_id"])
    rows = []
    for loc_id in sensors["location_id"].unique():
        data = client.get(f"/locations/{loc_id}/latest", {"limit": 1000})
        for r in data.get("results", []):
            sid = r.get("sensorsId")
            ts = pd.to_datetime((r.get("datetime") or {}).get("utc"), utc=True, errors="coerce")
            if sid not in wanted or pd.isna(ts):
                continue
            if sid in last_seen and ts <= last_seen[sid]:
                continue  # deja ingere
            last_seen[sid] = ts
            rows.append({"sensor_id": sid, "timestamp": ts, "value": r.get("value")})
    raw = pd.DataFrame(rows, columns=["sensor_id", "timestamp", "value"])
    raw["ingested_at"] = pd.Timestamp.now(tz="UTC")
    return raw


def live(interval_min: int, once: bool = False, client=None, store=None) -> None:
    config.check_api_key()
    client = client or OpenAQClient()
    store = store or Store()
    sensors = load_sensors(store)
    last_seen = init_last_seen(store)
    log.info("Ingestion IoT : %d capteurs, toutes les %d min", len(sensors), interval_min)

    while True:
        started = time.time()
        try:
            raw = poll_once(client, sensors, last_seen)
            store.write_parquet(raw, config.BRONZE_PREFIX)
            n = store.write_parquet(clean(raw, sensors), config.SILVER_PREFIX)
            log.info("Cycle : %d nouvelles mesures brutes, %d propres", len(raw), n)
        except Exception:
            log.exception("Cycle en echec, on reessaie au prochain passage")
        if once:
            return
        time.sleep(max(0, interval_min * 60 - (time.time() - started)))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    b = sub.add_parser("backfill")
    b.add_argument("--days", type=int, default=14)
    b.add_argument("--workers", type=int, default=4)
    lv = sub.add_parser("live")
    lv.add_argument("--interval", type=int, default=15, help="minutes entre deux cycles")
    lv.add_argument("--once", action="store_true")
    args = ap.parse_args()

    if args.mode == "backfill":
        backfill(args.days, args.workers)
    else:
        live(args.interval, args.once)


if __name__ == "__main__":
    main()

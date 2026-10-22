"""Collecte temps réel CityBikes -> MinIO (zone bronze).

Toutes les COLLECT_INTERVAL_SECONDS (150 s par défaut), interroge en parallèle les
réseaux de vélos des principales villes de France et dépose, pour chaque réseau,
un fichier JSON Lines gzip (une ligne = une station brute + métadonnées de collecte) :

    s3://urbanhub/bronze/citybikes/date=YYYY-MM-DD/network=<id>/<id>_<YYYYMMDDTHHMMSSZ>.jsonl.gz

Usage :
    python -m collector.collect_citybikes          # boucle infinie
    python -m collector.collect_citybikes --once   # un seul passage (test)
"""
import argparse
import gzip
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import boto3
import requests
from botocore.exceptions import ClientError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from common import config

API_URL = "https://api.citybik.es/v2/networks/{network}"
FIELDS = "id,name,location,stations"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("collector")


def make_http() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = "UrbanHub-TP/1.0 (projet etudiant)"
    return session


def make_s3():
    return boto3.client(
        "s3",
        endpoint_url=config.MINIO_ENDPOINT,
        aws_access_key_id=config.MINIO_ACCESS_KEY,
        aws_secret_access_key=config.MINIO_SECRET_KEY,
        region_name="us-east-1",
    )


def ensure_bucket(s3) -> None:
    try:
        s3.head_bucket(Bucket=config.BUCKET)
    except ClientError:
        s3.create_bucket(Bucket=config.BUCKET)
        log.info("Bucket %s créé", config.BUCKET)


def fetch_network(http: requests.Session, network: str) -> dict:
    resp = http.get(API_URL.format(network=network), params={"fields": FIELDS}, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return json.loads(resp.text)["network"]


def to_jsonl_gz(network: dict, collected_at: datetime) -> bytes:
    meta = {
        "network_id": network["id"],
        "city": network.get("location", {}).get("city"),
        "collected_at": collected_at.isoformat(),
    }
    lines = (json.dumps({**station, **meta}, ensure_ascii=False) for station in network["stations"])
    return gzip.compress("\n".join(lines).encode("utf-8"))


def collect_network(http, s3, network_id: str, collected_at: datetime) -> int:
    network = fetch_network(http, network_id)
    stamp = collected_at.strftime("%Y%m%dT%H%M%SZ")
    key = (f"{config.BRONZE_PREFIX}/date={collected_at:%Y-%m-%d}/network={network_id}/"
           f"{network_id}_{stamp}.jsonl.gz")
    s3.put_object(Bucket=config.BUCKET, Key=key, Body=to_jsonl_gz(network, collected_at),
                  ContentType="application/x-ndjson", ContentEncoding="gzip")
    return len(network["stations"])


def collect_once(http, s3) -> None:
    # Un horodatage commun à tous les réseaux = un "snapshot" cohérent du parc
    collected_at = datetime.now(timezone.utc).replace(microsecond=0)
    with ThreadPoolExecutor(max_workers=len(config.NETWORKS)) as pool:
        futures = {n: pool.submit(collect_network, http, s3, n, collected_at) for n in config.NETWORKS}
    ok, total = 0, 0
    for network_id, future in futures.items():
        try:
            total += future.result()
            ok += 1
        except Exception as exc:  # un réseau en panne ne doit pas bloquer les autres
            log.warning("Échec %s : %s", network_id, exc)
    log.info("Snapshot %s : %d/%d réseaux, %d stations", collected_at.isoformat(), ok,
             len(config.NETWORKS), total)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="un seul passage puis arrêt")
    args = parser.parse_args()

    http, s3 = make_http(), make_s3()
    ensure_bucket(s3)
    log.info("Collecte de %d réseaux toutes les %d s", len(config.NETWORKS),
             config.COLLECT_INTERVAL_SECONDS)
    while True:
        started = time.monotonic()
        collect_once(http, s3)
        if args.once:
            break
        time.sleep(max(0.0, config.COLLECT_INTERVAL_SECONDS - (time.monotonic() - started)))


if __name__ == "__main__":
    main()

"""Configuration du flux IoT : cle API, villes, polluants, chemins."""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

API_BASE = "https://api.openaq.org/v3"
API_KEY = os.getenv("OPENAQ_API_KEY", "")

# Polluants demandes par l'enonce (noms OpenAQ v3, en minuscules)
POLLUTANTS = {"pm25", "pm10", "no2", "o3", "co"}

# Rayon de recherche autour de chaque ville (maximum impose par l'API : 25 000 m)
RADIUS_M = 25_000

DATA_DIR = ROOT / "data"
SENSORS_FILE = DATA_DIR / "reference" / "iot_sensors.parquet"


def load_cities(path: Path = ROOT / "config" / "cities.yaml") -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["cities"]


def check_api_key() -> None:
    if not API_KEY:
        raise RuntimeError(
            "OPENAQ_API_KEY manquante : cree un fichier .env a la racine "
            "(voir .env.example)."
        )


# --- Stockage (fsspec) ------------------------------------------------------
# Local par defaut (./data). Pour MinIO : IOT_STORE_URI=s3://urbanhub
# Les noms de variables MinIO sont a aligner avec ceux du docker-compose de l'equipe.
STORE_URI = os.getenv("IOT_STORE_URI", str(DATA_DIR))
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9100")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "")


def storage_options() -> dict:
    if STORE_URI.startswith("s3://"):
        return {
            "key": MINIO_ACCESS_KEY,
            "secret": MINIO_SECRET_KEY,
            "client_kwargs": {"endpoint_url": MINIO_ENDPOINT},
        }
    return {}


# --- Rapports d'analyse -----------------------------------------------------
REPORTS_DIR = ROOT / "reports" / "iot"
TIMEZONE = "Europe/Paris"  # fuseau d'affichage (les donnees restent stockees en UTC)
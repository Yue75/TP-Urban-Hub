"""Configuration du flux IoT (OpenAQ).

Les variables MinIO ont les memes noms et valeurs par defaut que src/common/config.py
(partie streaming), pour partager le meme MinIO et le meme bucket.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

try:  # .env optionnel : utile en local, inutile dans Docker (variables du compose)
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

# --- OpenAQ -----------------------------------------------------------------
API_BASE = "https://api.openaq.org/v3"
API_KEY = os.getenv("OPENAQ_API_KEY", "")

# Villes communes a l'equipe (memes noms que les autres parties)
CITIES = [
    {"name": "Paris",     "lat": 48.8566, "lon": 2.3522},
    {"name": "Lyon",      "lat": 45.7640, "lon": 4.8357},
    {"name": "Marseille", "lat": 43.2965, "lon": 5.3698},
    {"name": "Toulouse",  "lat": 43.6047, "lon": 1.4442},
    {"name": "Bordeaux",  "lat": 44.8378, "lon": -0.5792},
]

# Polluants demandes par l'enonce (noms OpenAQ v3, en minuscules)
POLLUTANTS = {"pm25", "pm10", "no2", "o3", "co"}

# Rayon de recherche autour de chaque ville (maximum impose par l'API : 25 000 m)
RADIUS_M = 25_000

TIMEZONE = "Europe/Paris"  # fuseau des colonnes date_local / hour_local (stockage en UTC)

# --- Stockage ---------------------------------------------------------------
# IOT_STORE=local : dossier ./data (tests sans Docker)
# IOT_STORE=s3    : MinIO de l'equipe (bucket MINIO_BUCKET)
STORE_MODE = os.getenv("IOT_STORE", "local")
DATA_DIR = Path(os.getenv("IOT_DATA_DIR", ROOT / "data"))

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9100")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "urbanhub")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "urbanhub123")
BUCKET = os.getenv("MINIO_BUCKET", "urbanhub")

# Architecture medaillon (meme logique que bronze/citybikes, silver/stations, gold/...)
BRONZE_PREFIX = "bronze/openaq"                 # mesures brutes (Parquet, partition date=)
SILVER_PREFIX = "silver/pollution"              # mesures nettoyees, en ug/m3
SENSORS_KEY = "silver/pollution_sensors/sensors.parquet"   # table de reference des capteurs
GOLD_PREFIX = "gold/pollution_horaire_ville"    # une ligne par ville x polluant x heure
REPORTS_PREFIX = "reports/partie3"              # figures PNG et tableaux CSV

# Rapports produits en local (le dossier outputs/ est monte dans Docker)
REPORTS_DIR = Path(os.getenv("IOT_REPORTS_DIR", ROOT / "outputs" / "partie3"))

# Parametres du service Docker (iot.run)
BACKFILL_DAYS = int(os.getenv("IOT_BACKFILL_DAYS", "30"))
INTERVAL_MIN = int(os.getenv("IOT_INTERVAL_MIN", "15"))
MAX_AGE_HOURS = int(os.getenv("IOT_MAX_AGE_HOURS", "48"))   # ignore les valeurs plus anciennes (capteurs muets)


def check_api_key() -> None:
    if not API_KEY:
        raise RuntimeError(
            "OPENAQ_API_KEY manquante : renseigne-la dans le fichier .env a la racine "
            "du repo (voir .env.example)."
        )

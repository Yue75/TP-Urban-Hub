"""Configuration partagée (lue depuis les variables d'environnement du docker-compose)."""
import os

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9100")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "urbanhub")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "urbanhub123")
BUCKET = os.getenv("MINIO_BUCKET", "urbanhub")

NETWORKS = [n.strip() for n in os.getenv(
    "CITYBIKES_NETWORKS",
    "velib,velov,le-velo,velo,bicloo,velhop,velomagg,v3-bordeaux,vlille,le-velo-star",
).split(",") if n.strip()]
COLLECT_INTERVAL_SECONDS = int(os.getenv("COLLECT_INTERVAL_SECONDS", "150"))

# Zones du Data Lake (architecture médaillon)
BRONZE_PREFIX = "bronze/citybikes"   # JSON brut horodaté, tel que renvoyé par l'API
SILVER_PREFIX = "silver/stations"    # snapshots nettoyés, Parquet
GOLD_PREFIX = "gold"                 # indicateurs métier, Parquet
REPORTS_PREFIX = "reports/partie2"   # figures PNG + rapport


def s3a(path: str) -> str:
    return f"s3a://{BUCKET}/{path}"

"""Gold -> CSV : export des indicateurs métier pour Excel / Power BI / rendu.

    docker compose run --rm spark python -m spark_jobs.export_csv            # tables gold
    docker compose run --rm spark python -m spark_jobs.export_csv --silver   # + snapshots silver

Les tables gold (petits volumes agrégés) sont écrites en un CSV par table dans outputs/csv/
(UTF-8 avec BOM pour qu'Excel lise les accents) puis publiées dans MinIO (reports/partie2/csv/).
Avec --silver, l'historique complet des snapshots nettoyés est aussi exporté par Spark en CSV
gzip dans s3a://urbanhub/exports/silver_stations/ (trop volumineux pour passer par pandas).
"""
import os
import sys
from pathlib import Path

import boto3

from common import config
from spark_jobs.session import get_spark

OUT = Path(os.getenv("OUTPUT_DIR", "/app/outputs"))
CSV_DIR = OUT / "csv"
GOLD_TABLES = ["station_usage", "zone_supply", "network_timeseries", "hourly_profile",
               "geo_balance", "critical_stations"]
SILVER_EXPORT = "exports/silver_stations"


def export_gold(spark) -> list:
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    saved = []
    for name in GOLD_TABLES:
        df = spark.read.parquet(config.s3a(f"{config.GOLD_PREFIX}/{name}")).toPandas()
        path = CSV_DIR / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d %H:%M:%S")
        saved.append(path)
        print(f"[csv] {name:<20} {len(df):>8,} lignes -> {path}")
    return saved


def export_silver(spark) -> None:
    path = config.s3a(SILVER_EXPORT)
    (spark.read.parquet(config.s3a(config.SILVER_PREFIX))
     .write.mode("overwrite")
     .option("header", True).option("compression", "gzip")
     .option("timestampFormat", "yyyy-MM-dd HH:mm:ss")
     .csv(path))
    print(f"[csv] silver_stations -> {path}")


def upload(paths: list) -> None:
    s3 = boto3.client("s3", endpoint_url=config.MINIO_ENDPOINT, aws_access_key_id=config.MINIO_ACCESS_KEY,
                      aws_secret_access_key=config.MINIO_SECRET_KEY, region_name="us-east-1")
    for p in paths:
        s3.upload_file(str(p), config.BUCKET, f"{config.REPORTS_PREFIX}/{p.relative_to(OUT).as_posix()}")
    print(f"[csv] {len(paths)} fichiers publiés dans s3://{config.BUCKET}/{config.REPORTS_PREFIX}/csv/")


def main(with_silver: bool = False) -> None:
    spark = get_spark("urbanhub-export-csv")
    saved = export_gold(spark)
    if with_silver:
        export_silver(spark)
    spark.stop()
    upload(saved)


if __name__ == "__main__":
    main(with_silver="--silver" in sys.argv[1:])

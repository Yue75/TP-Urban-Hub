"""Synchronisation entre le Data Lake MinIO (bucket urbanhub) et le dossier local data/.

MinIO est la source de vérité : chaque partie y écrit ses tables gold. Le dashboard et la fusion
de la Partie 4 lisent des fichiers locaux (common.local_lake) : `pull` les télécharge dans data/.

    python -m common.lake_sync pull    # MinIO -> data/<table>.csv   (avant le dashboard / la fusion)
    python -m common.lake_sync push    # data/<table>.csv -> MinIO   (tables reçues de l'équipe)
    python -m common.lake_sync status  # tables présentes dans MinIO et dans data/

`push` ne remplace jamais une table déjà présente dans MinIO (sauf --force) : il sert à déposer
les exports d'un coéquipier dont la collecte a tourné sur une autre machine.

Horodatages : les tables écrites par Spark (Parties 1 et 2) stockent des instants UTC sans fuseau ;
ils sont convertis en heure de Paris, comme le fait Spark (session.timeZone = Europe/Paris).
Les tables écrites par pandas (Parties 1 récente, 3 et 4) gardent leur fuseau (UTC).
"""
import argparse
import io

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
from pyarrow import fs

from common import config, local_lake

TZ = "Europe/Paris"

# Nom de la table (= nom attendu par le dashboard) -> préfixe ou fichier dans le bucket
TABLES = {
    # Partie 1 – météo (notebook Spark NOAA + meteo_recente.py)
    "meteo_journalier": "gold/meteo/journalier",
    "meteo_temperature_mensuelle": "gold/meteo/temperature_mensuelle",
    "meteo_anomalies_france": "gold/meteo/anomalies_france",
    "meteo_jours_extremes_villes": "gold/meteo/jours_extremes_villes",
    "meteo_horaire_ville": "gold/meteo_horaire_ville/meteo_horaire_ville.parquet",
    "meteo_journaliere_ville": "gold/meteo_journaliere_ville/meteo_journaliere_ville.parquet",
    # Partie 2 – vélos (spark_jobs.silver_to_gold)
    "station_usage": "gold/station_usage",
    "zone_supply": "gold/zone_supply",
    "network_timeseries": "gold/network_timeseries",
    "hourly_profile": "gold/hourly_profile",
    "geo_balance": "gold/geo_balance",
    "critical_stations": "gold/critical_stations",
    # Partie 3 – pollution (iot.discover + iot.analysis)
    "pollution_sensors": "silver/pollution_sensors/sensors.parquet",
    "pollution_horaire_ville": "gold/pollution_horaire_ville",
    # Partie 4 – croisement (croise.fusion)
    "croise_horaire_ville": "gold/croise_horaire_ville",
    "croise_journalier_ville": "gold/croise_journalier_ville",
}


def s3fs() -> fs.S3FileSystem:
    scheme, host = config.MINIO_ENDPOINT.split("://")
    return fs.S3FileSystem(endpoint_override=host, scheme=scheme, access_key=config.MINIO_ACCESS_KEY,
                           secret_key=config.MINIO_SECRET_KEY, region="us-east-1")


def exists(s3, key: str) -> bool:
    path = f"{config.BUCKET}/{key}"
    if key.endswith(".parquet"):
        return s3.get_file_info(path).type == fs.FileType.File
    infos = s3.get_file_info(fs.FileSelector(path, recursive=True, allow_not_found=True))
    return any(i.path.endswith(".parquet") for i in infos)


def read_minio(s3, key: str) -> pd.DataFrame:
    path = f"{config.BUCKET}/{key}"
    table = (pq.read_table(path, filesystem=s3) if key.endswith(".parquet")
             else ds.dataset(path, filesystem=s3, format="parquet", partitioning="hive").to_table())
    df = table.to_pandas()
    for col in df.columns:
        if pd.api.types.is_datetime64_dtype(df[col]):          # sans fuseau = instant UTC écrit par Spark
            df[col] = df[col].dt.tz_localize("UTC").dt.tz_convert(TZ).dt.tz_localize(None)
    return df


def pull(names: list) -> None:
    s3 = s3fs()
    local_lake.DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in names:
        key = TABLES[name]
        if not exists(s3, key):
            print(f"[pull] {name:<28} absente de MinIO ({key})")
            continue
        df = read_minio(s3, key)
        path = local_lake.DATA_DIR / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"[pull] {name:<28} {len(df):>9,} lignes -> {local_lake.display_path(path)}")


def push(names: list, force: bool) -> None:
    s3 = s3fs()
    for name in names:
        key = TABLES[name]
        src = local_lake.find(name)
        if src is None:
            print(f"[push] {name:<28} absente de data/")
            continue
        if exists(s3, key) and not force:
            print(f"[push] {name:<28} déjà dans MinIO ({key}), ignorée (--force pour remplacer)")
            continue
        df = local_lake.read(src)
        for col in df.columns:
            if not pd.api.types.is_datetime64_dtype(df[col]):
                continue
            if (df[col].dropna() == df[col].dropna().dt.normalize()).all():   # jour sans heure : reste une date
                df[col] = df[col].dt.date
            else:                                               # heure de Paris sans fuseau -> UTC
                df[col] = df[col].dt.tz_localize(TZ, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
        target = key if key.endswith(".parquet") else f"{key}/part-0.parquet"
        if force and not key.endswith(".parquet"):
            s3.delete_dir_contents(f"{config.BUCKET}/{key}", missing_dir_ok=True)
        buf = io.BytesIO()
        pq.write_table(pa.Table.from_pandas(df, preserve_index=False), buf,
                       coerce_timestamps="us", allow_truncated_timestamps=True)
        with s3.open_output_stream(f"{config.BUCKET}/{target}") as out:
            out.write(buf.getvalue())
        print(f"[push] {name:<28} {len(df):>9,} lignes -> s3://{config.BUCKET}/{target}")


def status(names: list) -> None:
    s3 = s3fs()
    print(f"{'table':<28} {'MinIO':<6} data/")
    for name in names:
        local = local_lake.find(name)
        print(f"{name:<28} {'oui' if exists(s3, TABLES[name]) else '-':<6} "
              f"{local_lake.display_path(local) if local else '-'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["pull", "push", "status"])
    parser.add_argument("tables", nargs="*", help="tables à traiter (défaut : toutes)")
    parser.add_argument("--force", action="store_true", help="push : remplace la table dans MinIO")
    args = parser.parse_args()
    unknown = set(args.tables) - set(TABLES)
    if unknown:
        parser.error(f"tables inconnues : {', '.join(sorted(unknown))}")
    names = args.tables or list(TABLES)
    if args.action == "pull":
        pull(names)
    elif args.action == "push":
        push(names, args.force)
    else:
        status(names)


if __name__ == "__main__":
    main()

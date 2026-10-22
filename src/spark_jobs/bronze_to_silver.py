"""Bronze -> Silver : extraction des variables demandées + nettoyage.

Entrée  : s3a://urbanhub/bronze/citybikes/**/*.jsonl.gz   (stations brutes CityBikes)
Sortie  : s3a://urbanhub/silver/stations/                 (Parquet partitionné network_id/date)

Variables extraites : station_id, station_name, latitude, longitude, timestamp,
bikes_available, free_slots (+ colonnes utiles à l'analyse : capacity, ebikes, city...).
"""
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql import types as T

from common import config
from spark_jobs.session import get_spark

# Schéma explicite : les champs "extra" varient d'un opérateur à l'autre, on les lit
# en chaîne puis on les caste, pour qu'un type inattendu donne null au lieu de casser la lecture.
RAW_SCHEMA = T.StructType([
    T.StructField("id", T.StringType()),
    T.StructField("name", T.StringType()),
    T.StructField("latitude", T.DoubleType()),
    T.StructField("longitude", T.DoubleType()),
    T.StructField("timestamp", T.StringType()),
    T.StructField("free_bikes", T.LongType()),
    T.StructField("empty_slots", T.LongType()),
    T.StructField("extra", T.StructType([
        T.StructField("uid", T.StringType()),
        T.StructField("slots", T.StringType()),
        T.StructField("ebikes", T.StringType()),
        T.StructField("normal_bikes", T.StringType()),
        T.StructField("renting", T.StringType()),
        T.StructField("returning", T.StringType()),
        T.StructField("virtual", T.StringType()),
    ])),
    T.StructField("network_id", T.StringType()),
    T.StructField("city", T.StringType()),
    T.StructField("collected_at", T.StringType()),
])


def parse_iso(col: F.Column) -> F.Column:
    # L'API renvoie des horodatages du type "2026-10-21T10:14:14.741144+00:00Z" (offset ET "Z") :
    # on normalise en "+00:00" avant le cast.
    return F.regexp_replace(col, r"(\+00:00)?Z$", "+00:00").cast("timestamp")


def transform(raw: DataFrame) -> DataFrame:
    df = raw.select(
        F.col("network_id"),
        F.col("city"),
        F.col("id").alias("station_id"),
        F.trim("name").alias("station_name"),
        F.col("latitude"),
        F.col("longitude"),
        F.col("free_bikes").alias("bikes_available"),
        F.col("empty_slots").alias("free_slots"),
        parse_iso(F.col("timestamp")).alias("timestamp"),
        parse_iso(F.col("collected_at")).alias("collected_at"),
        F.col("extra.slots").cast("int").alias("slots"),
        F.col("extra.ebikes").cast("int").alias("ebikes"),
        F.col("extra.normal_bikes").cast("int").alias("normal_bikes"),
        F.col("extra.renting").alias("renting"),
        F.col("extra.virtual").alias("virtual"),
    )

    df = (
        df
        # Valeurs manquantes / aberrantes
        .filter(F.col("station_id").isNotNull() & F.col("collected_at").isNotNull())
        .filter(F.col("latitude").between(41.0, 51.5) & F.col("longitude").between(-5.5, 10.0))
        .filter(F.col("bikes_available").isNotNull() & (F.col("bikes_available") >= 0))
        .withColumn("free_slots", F.when(F.col("free_slots") >= 0, F.col("free_slots")))
        .withColumn("timestamp", F.coalesce("timestamp", "collected_at"))
        # Stations virtuelles (sans bornes) exclues : pas de notion de places libres
        .filter(~F.lower(F.coalesce("virtual", F.lit("false"))).isin("true", "1"))
        # Stations fermées à la location (renting = 0) exclues des analyses de disponibilité
        .filter(~F.coalesce("renting", F.lit("1")).isin("0", "false", "False"))
        .withColumn("station_name", F.coalesce("station_name", F.col("station_id")))
        .withColumn("capacity", F.coalesce(
            F.when(F.col("slots") > 0, F.col("slots")),
            F.col("bikes_available") + F.coalesce("free_slots", F.lit(0)),
        ))
        .filter(F.col("capacity") > 0)
        .withColumn("fill_rate", F.least(F.lit(1.0), F.col("bikes_available") / F.col("capacity")))
        # Dimensions temporelles en heure de Paris (session.timeZone = Europe/Paris)
        .withColumn("date", F.to_date("collected_at"))
        .withColumn("hour", F.hour("collected_at"))
        .withColumn("day_of_week", F.dayofweek("collected_at"))            # 1 = dimanche
        .withColumn("is_weekend", F.col("day_of_week").isin(1, 7))
        .dropDuplicates(["network_id", "station_id", "collected_at"])
        .drop("slots", "renting", "virtual")
    )
    return df


def main() -> None:
    spark = get_spark("urbanhub-bronze-to-silver")
    raw = (spark.read.schema(RAW_SCHEMA)
           .option("recursiveFileLookup", "true")
           .json(config.s3a(config.BRONZE_PREFIX)))
    silver = transform(raw)
    (silver.repartition("network_id", "date")
     .write.mode("overwrite")
     .partitionBy("network_id", "date")
     .parquet(config.s3a(config.SILVER_PREFIX)))

    out = spark.read.parquet(config.s3a(config.SILVER_PREFIX))
    print(f"[silver] {out.count():,} lignes, "
          f"{out.select('collected_at').distinct().count()} snapshots, "
          f"{out.select('network_id', 'station_id').distinct().count()} stations")
    out.groupBy("network_id", "city").agg(
        F.countDistinct("station_id").alias("stations"),
        F.min("collected_at").alias("debut"), F.max("collected_at").alias("fin"),
    ).orderBy("network_id").show(truncate=False)
    spark.stop()


if __name__ == "__main__":
    main()

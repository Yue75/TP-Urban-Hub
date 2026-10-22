"""Silver -> Gold : indicateurs métier de la mobilité vélo (questions 1 à 5).

CityBikes ne publie que des *états* de stations (vélos présents à l'instant t), pas des trajets.
On reconstitue l'activité à partir des variations entre deux snapshots consécutifs :
    départs  = baisse du nombre de vélos   | arrivées = hausse du nombre de vélos
    mouvements = |Δ vélos|   (borne basse : un départ et une arrivée simultanés s'annulent)

Tables produites dans s3a://urbanhub/gold/ :
    station_usage      Q1/Q5  activité, taux d'utilisation et remplissage par station
    zone_supply        Q2     offre de vélos par maille d'environ 1 km x 1 km
    network_timeseries Q3     activité du réseau à chaque snapshot
    hourly_profile     Q3     profil horaire moyen (semaine / week-end)
    geo_balance        Q4     remplissage selon la distance au centre et le moment de la journée
    critical_stations  Q5     stations à rééquilibrer + besoin estimé en vélos
"""
from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

from common import config
from spark_jobs.session import get_spark

MAX_GAP_MIN = 10          # au-delà, deux snapshots ne sont pas considérés comme consécutifs
EMPTY_LOW_BIKES = 2       # "quasi vide" : 2 vélos ou moins
CRITICAL_SHARE = 0.25     # station critique si vide (ou pleine) plus de 25 % du temps observé
TARGET_FILL = 0.5         # objectif de rééquilibrage : station remplie à moitié
CELL_LAT, CELL_LON = 0.009, 0.013   # maille ≈ 1 km x 1 km en France métropolitaine

# Centre de référence de chaque ville (hôtel de ville / place centrale)
CITY_CENTERS = {
    "velib": (48.8566, 2.3522),          # Paris, Hôtel de Ville
    "velov": (45.7578, 4.8320),          # Lyon, Bellecour
    "le-velo": (43.2951, 5.3740),        # Marseille, Vieux-Port
    "velo": (43.6045, 1.4440),           # Toulouse, Capitole
    "bicloo": (47.2184, -1.5536),        # Nantes
    "velhop": (48.5839, 7.7455),         # Strasbourg
    "velomagg": (43.6085, 3.8797),       # Montpellier, Comédie
    "v3-bordeaux": (44.8378, -0.5792),   # Bordeaux
    "vlille": (50.6366, 3.0635),         # Lille, Grand'Place
    "le-velo-star": (48.1113, -1.6800),  # Rennes
}
DIST_BANDS = [(0, 2, "0-2 km"), (2, 4, "2-4 km"), (4, 6, "4-6 km"), (6, 10, "6-10 km"), (10, 999, "> 10 km")]


def haversine_km(lat1: str, lon1: str, lat2: str, lon2: str) -> F.Column:
    lat1, lon1, lat2, lon2 = (F.col(c) for c in (lat1, lon1, lat2, lon2))
    dlat, dlon = F.radians(lat2 - lat1), F.radians(lon2 - lon1)
    a = F.sin(dlat / 2) ** 2 + F.cos(F.radians(lat1)) * F.cos(F.radians(lat2)) * F.sin(dlon / 2) ** 2
    return 2 * 6371.0 * F.asin(F.sqrt(a))


def day_period(hour: F.Column) -> F.Column:
    return (F.when(hour.between(7, 9), "Pointe matin (7h-10h)")
            .when(hour.between(10, 15), "Journée (10h-16h)")
            .when(hour.between(16, 19), "Pointe soir (16h-20h)")
            .otherwise("Soir/nuit (20h-7h)"))


def add_movements(silver: DataFrame) -> DataFrame:
    w = Window.partitionBy("network_id", "station_id").orderBy("collected_at")
    gap = (F.unix_timestamp("collected_at") - F.unix_timestamp(F.lag("collected_at").over(w))) / 60
    delta = F.col("bikes_available") - F.lag("bikes_available").over(w)
    consecutive = F.col("gap_min") <= MAX_GAP_MIN
    return (silver
            .withColumn("gap_min", gap)
            .withColumn("delta", F.when(consecutive, delta))
            .withColumn("observed_min", F.when(consecutive, F.col("gap_min")).otherwise(0.0))
            .withColumn("departures", F.when(F.col("delta") < 0, -F.col("delta")).otherwise(0))
            .withColumn("arrivals", F.when(F.col("delta") > 0, F.col("delta")).otherwise(0))
            .withColumn("movements", F.col("departures") + F.col("arrivals"))
            .withColumn("is_empty", (F.col("bikes_available") == 0).cast("int"))
            .withColumn("is_low", (F.col("bikes_available") <= EMPTY_LOW_BIKES).cast("int"))
            .withColumn("is_full", (F.coalesce("free_slots", F.lit(1)) == 0).cast("int")))


def with_city_geo(df: DataFrame, spark) -> DataFrame:
    centers = spark.createDataFrame([(k, la, lo) for k, (la, lo) in CITY_CENTERS.items()],
                                    ["network_id", "center_lat", "center_lon"])
    band = F.lit(None).cast("string")
    for lo, hi, label in reversed(DIST_BANDS):
        band = F.when((F.col("dist_center_km") >= lo) & (F.col("dist_center_km") < hi), label).otherwise(band)
    return (df.join(F.broadcast(centers), "network_id", "left")
            .withColumn("dist_center_km", haversine_km("center_lat", "center_lon", "latitude", "longitude"))
            .withColumn("dist_band", band)
            .drop("center_lat", "center_lon"))


def station_usage(mov: DataFrame, spark) -> DataFrame:
    w_last = Window.partitionBy("network_id", "station_id").orderBy(F.desc("collected_at"))
    latest = (mov.withColumn("rn", F.row_number().over(w_last)).filter("rn = 1")
              .select("network_id", "station_id",
                      F.col("station_name"),
                      F.col("bikes_available").alias("bikes_now"),
                      F.col("free_slots").alias("free_slots_now"),
                      F.col("collected_at").alias("last_seen")))
    agg = (mov.groupBy("network_id", "city", "station_id").agg(
        F.avg("latitude").alias("latitude"),
        F.avg("longitude").alias("longitude"),
        F.expr("percentile_approx(capacity, 0.5)").alias("capacity"),
        F.count("*").alias("snapshots"),
        (F.sum("observed_min") / 60).alias("observed_hours"),
        F.sum("movements").alias("movements"),
        F.sum("departures").alias("departures"),
        F.sum("arrivals").alias("arrivals"),
        F.avg("bikes_available").alias("avg_bikes"),
        F.avg("fill_rate").alias("avg_fill_rate"),
        F.avg("is_empty").alias("pct_time_empty"),
        F.avg("is_low").alias("pct_time_low"),
        F.avg("is_full").alias("pct_time_full"),
    ))
    days = F.greatest(F.col("observed_hours"), F.lit(1 / 60)) / 24
    return (with_city_geo(agg.join(latest, ["network_id", "station_id"]), spark)
            .withColumn("movements_per_day", F.col("movements") / days)
            .withColumn("departures_per_day", F.col("departures") / days)
            # Taux d'utilisation = rotations quotidiennes par point d'attache
            .withColumn("usage_rate", F.col("movements_per_day") / F.col("capacity")))


def zone_supply(mov: DataFrame, usage: DataFrame) -> DataFrame:
    cell = lambda df: (df.withColumn("cell_y", F.floor(F.col("latitude") / CELL_LAT))
                       .withColumn("cell_x", F.floor(F.col("longitude") / CELL_LON)))
    per_snapshot = (cell(mov).groupBy("network_id", "city", "cell_y", "cell_x", "collected_at")
                    .agg(F.sum("bikes_available").alias("bikes"), F.sum("capacity").alias("capacity")))
    supply = (per_snapshot.groupBy("network_id", "city", "cell_y", "cell_x").agg(
        F.avg("bikes").alias("avg_bikes"),
        F.avg("capacity").alias("capacity"),
        F.avg(F.col("bikes") / F.col("capacity")).alias("avg_fill_rate"),
        F.avg((F.col("bikes") / F.col("capacity") < 0.10).cast("int")).alias("pct_time_short"),
    ))
    demand = (cell(usage).groupBy("network_id", "cell_y", "cell_x").agg(
        F.count("*").alias("n_stations"),
        F.avg("latitude").alias("latitude"),
        F.avg("longitude").alias("longitude"),
        F.sum("departures_per_day").alias("departures_per_day"),
        F.avg("pct_time_empty").alias("avg_pct_time_empty"),
        F.first("dist_center_km").alias("dist_center_km"),
    ))
    return (supply.join(demand, ["network_id", "cell_y", "cell_x"])
            # Tension = départs quotidiens rapportés aux vélos disponibles en moyenne
            .withColumn("tension", F.col("departures_per_day") / F.greatest("avg_bikes", F.lit(1.0)))
            .withColumn("supply_insufficient",
                        (F.col("pct_time_short") >= CRITICAL_SHARE) | (F.col("avg_fill_rate") < 0.15))
            .withColumn("zone_id", F.concat_ws("_", "network_id", "cell_y", "cell_x")))


def network_timeseries(mov: DataFrame) -> DataFrame:
    ts = (mov.groupBy("network_id", "city", "collected_at", "date", "hour", "is_weekend").agg(
        F.sum("movements").alias("movements"),
        F.sum("departures").alias("departures"),
        F.sum("bikes_available").alias("bikes_docked"),
        F.sum("capacity").alias("capacity"),
        F.avg("is_empty").alias("share_stations_empty"),
        F.avg("is_full").alias("share_stations_full"),
        F.expr("percentile_approx(gap_min, 0.5)").alias("interval_min"),
    ))
    # Vélos en circulation (proxy) = pic de vélos garés sur la période - vélos garés à l'instant t
    w_net = Window.partitionBy("network_id")
    return (ts
            .withColumn("movements_per_hour",
                        F.when(F.col("interval_min") <= MAX_GAP_MIN,
                               F.col("movements") / F.col("interval_min") * 60))
            .withColumn("bikes_in_use_proxy", F.max("bikes_docked").over(w_net) - F.col("bikes_docked"))
            .withColumn("share_fleet_in_use", F.col("bikes_in_use_proxy") / F.max("bikes_docked").over(w_net)))


def hourly_profile(ts: DataFrame) -> DataFrame:
    return (ts.withColumn("day_type", F.when(F.col("is_weekend"), "Week-end").otherwise("Semaine"))
            .groupBy("network_id", "city", "day_type", "hour").agg(
                F.avg("movements_per_hour").alias("movements_per_hour"),
                F.avg("share_fleet_in_use").alias("share_fleet_in_use"),
                F.avg("share_stations_empty").alias("share_stations_empty"),
                F.countDistinct("date").alias("n_days")))


def geo_balance(mov: DataFrame, spark) -> DataFrame:
    return (with_city_geo(mov, spark)
            .withColumn("period", day_period(F.col("hour")))
            .groupBy("network_id", "city", "dist_band", "period").agg(
                F.countDistinct("station_id").alias("n_stations"),
                F.avg("fill_rate").alias("avg_fill_rate"),
                F.avg("is_empty").alias("pct_time_empty"),
                F.avg("is_full").alias("pct_time_full")))


def critical_stations(usage: DataFrame) -> DataFrame:
    status = (F.when(F.col("pct_time_empty") >= CRITICAL_SHARE, "Vide chronique : réapprovisionner")
              .when(F.col("pct_time_full") >= CRITICAL_SHARE, "Pleine chronique : délester"))
    return (usage
            .withColumn("status", status)
            .withColumn("alert_now", F.when(F.col("bikes_now") == 0, "vide").when(F.col("free_slots_now") == 0, "pleine"))
            .filter(F.col("status").isNotNull() | F.col("alert_now").isNotNull())
            # Vélos à apporter (+) ou retirer (-) pour revenir à TARGET_FILL
            .withColumn("rebalance_bikes", F.round(F.col("capacity") * TARGET_FILL - F.col("bikes_now")).cast("int"))
            # Priorité : part du temps en rupture, pondérée par l'activité de la station
            .withColumn("priority_score", F.round(
                100 * F.greatest("pct_time_empty", "pct_time_full") * (1 + F.least(F.col("usage_rate"), F.lit(5.0)) / 5), 1))
            .select("network_id", "city", "station_id", "station_name", "latitude", "longitude",
                    "capacity", "bikes_now", "free_slots_now", "pct_time_empty", "pct_time_full",
                    "usage_rate", "status", "alert_now", "rebalance_bikes", "priority_score", "last_seen")
            .orderBy(F.desc("priority_score")))


def main() -> None:
    spark = get_spark("urbanhub-silver-to-gold")
    silver = spark.read.parquet(config.s3a(config.SILVER_PREFIX))
    mov = add_movements(silver).cache()

    usage = station_usage(mov, spark).cache()
    ts = network_timeseries(mov).cache()
    tables = {
        "station_usage": usage,
        "zone_supply": zone_supply(mov, usage),
        "network_timeseries": ts,
        "hourly_profile": hourly_profile(ts),
        "geo_balance": geo_balance(mov, spark),
        "critical_stations": critical_stations(usage),
    }
    for name, df in tables.items():
        path = config.s3a(f"{config.GOLD_PREFIX}/{name}")
        df.coalesce(1).write.mode("overwrite").parquet(path)
        print(f"[gold] {name:<20} {spark.read.parquet(path).count():>8,} lignes -> {path}")
    spark.stop()


if __name__ == "__main__":
    main()

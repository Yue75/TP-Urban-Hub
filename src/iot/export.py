"""Export de la Partie 3 pour partager les donnees sans MinIO (CSV + copie du Data Lake).

Usage : python -m iot.export        (Docker : docker compose run --rm iot_analysis python -m iot.export)
Ecrit dans outputs/partie3/export/ :
  - pollution_horaire_ville.csv      (table gold, pour la Partie 4)
  - pollution_sensors.csv            (capteurs : id, station, ville, coordonnees)
  - lake/gold/pollution_horaire_ville/date=*/part-*.parquet   (meme arborescence que MinIO)
  - lake/silver/pollution_sensors/sensors.parquet
  - LISEZMOI.txt
"""
import logging

from . import config
from .storage import Store

log = logging.getLogger("iot.export")

README = """UrbanHub - Partie 3 (pollution, OpenAQ) - export
===================================================
Periode      : {tmin} -> {tmax} (UTC)
Lignes gold  : {n_gold}   | capteurs : {n_sensors}
Villes       : {cities}

pollution_horaire_ville.csv  (une ligne par ville x polluant x heure)
  city          Paris | Lyon | Marseille | Toulouse | Bordeaux
  pollutant     pm25 | pm10 | no2 | o3 | co        (valeurs en ug/m3)
  timestamp     debut de l'heure, en UTC
  value         moyenne entre capteurs de la ville
  value_median  mediane entre capteurs (robuste a un capteur aberrant)
  n_sensors     nombre de capteurs ayant mesure cette heure-la
  date_local    date en heure de Paris   |  hour_local : heure (0-23) en heure de Paris

Pour joindre avec la meteo / les velos : city + timestamp (UTC), ou city + date_local + hour_local.
Le CO n'est couvert que par 1 a 4 capteurs (absent a Toulouse et Bordeaux).

Dossier lake/ : memes chemins que dans MinIO (bucket urbanhub), a copier tel quel si besoin :
  gold/pollution_horaire_ville/   et   silver/pollution_sensors/
"""


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    store = Store()
    gold = store.read_parquet(config.GOLD_PREFIX)
    if gold.empty:
        raise SystemExit("Table gold vide : lance d'abord les analyses (python -m iot.analysis).")
    sensors = store.read_table(config.SENSORS_KEY)

    out = config.REPORTS_DIR / "export"
    out.mkdir(parents=True, exist_ok=True)
    gold = gold.sort_values(["city", "pollutant", "timestamp"])
    gold.to_csv(out / "pollution_horaire_ville.csv", index=False)
    sensors.to_csv(out / "pollution_sensors.csv", index=False)

    for key in store.list(config.GOLD_PREFIX) + [config.SENSORS_KEY]:
        dest = out / "lake" / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(store.get(key))

    (out / "LISEZMOI.txt").write_text(README.format(
        tmin=gold["timestamp"].min(), tmax=gold["timestamp"].max(), n_gold=len(gold),
        n_sensors=len(sensors), cities=", ".join(sorted(gold["city"].unique()))), encoding="utf-8")
    log.info("Export ecrit dans %s (%d lignes gold)", out, len(gold))


if __name__ == "__main__":
    main()
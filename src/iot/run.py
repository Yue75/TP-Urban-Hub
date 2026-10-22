"""Point d'entree du service Docker iot_collector.

1. decouvre les capteurs OpenAQ s'ils ne sont pas deja dans le Data Lake
2. fait un backfill de IOT_BACKFILL_DAYS jours si le silver est vide
3. lance l'ingestion reguliere (toutes les IOT_INTERVAL_MIN minutes)

Usage : python -m iot.run
"""
import logging

from . import config
from .collect import backfill, live
from .discover import discover
from .storage import Store

log = logging.getLogger("iot.run")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config.check_api_key()
    store = Store()

    if not store.exists(config.SENSORS_KEY):
        log.info("Premiere execution : decouverte des capteurs")
        sensors = discover(active_days=7)
        if sensors.empty:
            raise SystemExit("Aucun capteur trouve, arret.")
        store.write_table(sensors, config.SENSORS_KEY)

    if not store.list(config.SILVER_PREFIX):
        log.info("Silver vide : backfill de %d jours", config.BACKFILL_DAYS)
        backfill(config.BACKFILL_DAYS, store=store)

    live(config.INTERVAL_MIN, store=store)


if __name__ == "__main__":
    main()

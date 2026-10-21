"""Client minimal OpenAQ v3 : en-tete X-API-Key, retries, rate limit, pagination."""
import logging
import time

import requests

from . import config

log = logging.getLogger(__name__)


class OpenAQClient:
    def __init__(self, api_key: str = config.API_KEY, max_retries: int = 5):
        self.session = requests.Session()
        self.session.headers.update({"X-API-Key": api_key})
        self.max_retries = max_retries

    def get(self, path: str, params: dict | None = None) -> dict:
        url = f"{config.API_BASE}{path}"
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=30)
            except requests.RequestException as exc:
                wait = 2 ** attempt
                log.warning("Erreur reseau (%s), nouvel essai dans %ss", exc, wait)
                time.sleep(wait)
                continue

            if resp.status_code == 200:
                # Si le quota est presque epuise, on attend la remise a zero
                remaining = resp.headers.get("x-ratelimit-remaining")
                reset = resp.headers.get("x-ratelimit-reset")
                if remaining is not None and reset is not None and int(remaining) <= 1:
                    time.sleep(int(reset) + 1)
                return resp.json()

            if resp.status_code == 429:
                wait = int(resp.headers.get("x-ratelimit-reset")
                           or resp.headers.get("retry-after") or 2 ** attempt)
                log.warning("429 rate limit, pause de %ss", wait)
                time.sleep(wait + 1)
                continue

            if resp.status_code >= 500:
                wait = 2 ** attempt
                log.warning("Erreur %s, nouvel essai dans %ss", resp.status_code, wait)
                time.sleep(wait)
                continue

            # 4xx (401, 403, 404, 422...) : inutile de reessayer
            resp.raise_for_status()

        raise RuntimeError(f"Echec apres {self.max_retries} essais : {url} {params}")

    def paginate(self, path: str, params: dict | None = None, limit: int = 1000):
        """Parcourt toutes les pages et renvoie les resultats un par un."""
        params = dict(params or {}, limit=limit)
        page = 1
        while True:
            params["page"] = page
            data = self.get(path, params)
            results = data.get("results", [])
            yield from results
            if len(results) < limit:
                break
            page += 1

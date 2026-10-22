"""Lecture des tables du Data Lake pour le dashboard (cache Streamlit autour de common.local_lake).

La recherche des tables par nom (data/ puis outputs/, CSV ou Parquet) est dans src/common/local_lake.py,
partagee avec le pipeline de la Partie 4.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from common import local_lake  # noqa: E402
from common.local_lake import DATA_DIR, ROOT, display_path, find  # noqa: E402,F401


@dataclass(frozen=True)
class Table:
    name: str
    description: str
    optional: bool = False


# Tables attendues par partie (noms des tables gold/silver de chaque pipeline)
TABLES: dict[str, list[Table]] = {
    "Partie 1 – Météo": [
        Table("meteo_journalier", "NOAA : météo journalière par station"),
        Table("meteo_temperature_mensuelle", "NOAA : température moyenne mensuelle (5 villes + France)"),
        Table("meteo_anomalies_france", "NOAA : écart quotidien à la normale du mois"),
        Table("meteo_jours_extremes_villes", "NOAA : jours de chaleur, froid, vent ou pluie extrêmes"),
    ],
    "Partie 2 – Vélos": [
        Table("station_usage", "Indicateurs par station"),
        Table("zone_supply", "Offre de vélos par maille de 1 km²"),
        Table("hourly_profile", "Profil horaire du réseau"),
        Table("network_timeseries", "Série temporelle par réseau"),
        Table("geo_balance", "Remplissage par distance au centre et moment de la journée"),
        Table("critical_stations", "Stations critiques à rééquilibrer"),
    ],
    "Partie 3 – Pollution": [
        Table("pollution_horaire_ville", "Concentration horaire par ville et polluant"),
        Table("pollution_sensors", "Référentiel des capteurs (position, polluant)"),
        Table("q1_ranking_stations", "Classement des stations (résultat de la partie 3, outputs/)"),
    ],
    "Partie 4 – Analyse croisée": [
        Table("meteo_horaire_ville", "Open-Meteo : météo récente par ville et par heure (Partie 1)"),
        Table("pollution_horaire_ville", "OpenAQ : concentration horaire par ville et polluant (Partie 3)"),
        Table("network_timeseries", "CityBikes : activité des réseaux à chaque relevé (Partie 2)"),
        Table("croise_horaire_ville", "Sortie du pipeline python -m croise.fusion (la page recalcule la fusion)",
              optional=True),
    ],
}


@st.cache_data(show_spinner="Chargement des données…")
def _read(path: str, mtime: float) -> pd.DataFrame:     # mtime : relit si le fichier change
    return local_lake.read(Path(path))


def load(name: str) -> pd.DataFrame | None:
    p = find(name)
    return None if p is None else _read(str(p), local_lake.mtime(p))


@st.cache_data(show_spinner=False)
def _count_rows(path: str, mtime: float) -> int:
    p = Path(path)
    if p.suffix.lower() == ".csv":
        with p.open("rb") as f:
            return max(sum(1 for _ in f) - 1, 0)
    return ds.dataset(p, format="parquet", partitioning="hive").count_rows()


def status(partie: str) -> pd.DataFrame:
    """Etat des tables attendues pour une partie (affiche sur l'accueil et chaque page)."""
    rows = []
    for t in TABLES[partie]:
        p = find(t.name)
        if p is None:
            etat = "— Optionnelle, absente" if t.optional else "✗ Manquante"
            rows.append({"Table": t.name, "Contenu": t.description, "État": etat,
                         "Lignes": None, "Fichier": ""})
        else:
            rows.append({"Table": t.name, "Contenu": t.description, "État": "✓ Disponible",
                         "Lignes": _count_rows(str(p), local_lake.mtime(p)),
                         "Fichier": display_path(p)})
    out = pd.DataFrame(rows)
    out["Lignes"] = out["Lignes"].astype("Int64")
    return out


def require(*names: str) -> dict[str, pd.DataFrame]:
    """Charge les tables demandees ; signale celles qui manquent au lieu de planter."""
    found, missing = {}, []
    for n in names:
        df = load(n)
        if df is None:
            missing.append(n)
        else:
            found[n] = df
    if missing:
        st.warning(f"Données manquantes dans `{DATA_DIR.name}/` : "
                   + ", ".join(f"`{m}`" for m in missing), icon=":material/folder_off:")
    return found


FUSION_INPUTS = ["meteo_horaire_ville", "pollution_horaire_ville", "network_timeseries"]


@st.cache_data(show_spinner="Fusion des données…")
def _fused(paths: tuple[str, ...], mtimes: tuple[float, ...]) -> tuple[pd.DataFrame, pd.DataFrame]:
    from croise import fusion
    meteo, pol, ts = (local_lake.read(Path(p)) for p in paths)
    hourly = fusion.build_hourly(fusion.weather_hourly(meteo), fusion.pollution_hourly(pol), fusion.bikes_hourly(ts))
    return hourly, fusion.build_daily(hourly)


def fused() -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """Tables croisees (horaire, journaliere) recalculees avec le pipeline de la Partie 4 des que
    une source change : il suffit de deposer un nouvel export dans data/."""
    paths = [find(n) for n in FUSION_INPUTS]
    if any(p is None for p in paths):
        return None
    return _fused(tuple(map(str, paths)), tuple(local_lake.mtime(p) for p in paths))

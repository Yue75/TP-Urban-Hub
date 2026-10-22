"""Lecture des tables du Data Lake pour le dashboard.

Chaque table est cherchee par son nom dans data/ (ou URBANHUB_DATA_DIR), quel que soit
le format envoye par l'equipe :
    data/station_usage.csv                        export CSV (comme la partie 2)
    data/partie2/station_usage.csv                meme chose dans un sous-dossier
    data/gold/station_usage/                      dossier Parquet ecrit par Spark (partitions cle=valeur)
    data/silver/pollution_sensors/sensors.parquet fichier Parquet seul
Un nom peut etre qualifie ("silver/meteo") pour lever une ambiguite.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("URBANHUB_DATA_DIR", ROOT / "data"))

_PARTITION = re.compile(r"^[^=]+=[^=]*$")          # dossier de partition Spark : annee=2021
_DATE_COLS = {"date", "timestamp", "collected_at", "last_seen", "debut", "fin"}


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
        Table("silver/pollution", "Mesures nettoyées par capteur (classement des zones)"),
    ],
}


# ------------------------------------------------------------------ recherche
def _is_table_dir(d: Path) -> bool:
    """Dossier Parquet ecrit par Spark : que des partitions cle=valeur et au moins un .parquet."""
    for sub in d.rglob("*"):
        if sub.is_dir() and not _PARTITION.match(sub.name):
            return False
    return any(d.rglob("*.parquet"))


def _candidates() -> list[Path]:
    if not DATA_DIR.exists():
        return []
    out = []
    for p in DATA_DIR.rglob("*"):
        if p.name.startswith((".", "_")):
            continue
        if p.is_file() and p.suffix.lower() in (".csv", ".parquet"):
            out.append(p)
        elif p.is_dir() and not _PARTITION.match(p.name) and _is_table_dir(p):
            out.append(p)
    return out


def find(name: str) -> Path | None:
    """Chemin de la table `name` (le plus court si plusieurs correspondent)."""
    name = name.strip("/")
    matches = []
    for p in _candidates():
        rel = p.relative_to(DATA_DIR).with_suffix("").as_posix() if p.is_file() \
            else p.relative_to(DATA_DIR).as_posix()
        if rel == name or rel.endswith("/" + name):
            matches.append(p)
    if not matches:
        return None
    return min(matches, key=lambda p: (len(p.relative_to(DATA_DIR).parts), str(p)))


def _mtime(p: Path) -> float:
    if p.is_file():
        return p.stat().st_mtime
    return max((f.stat().st_mtime for f in p.rglob("*") if f.is_file()), default=0.0)


# ------------------------------------------------------------------ lecture
def _parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if (col in _DATE_COLS or col.endswith("_at")) and pd.api.types.is_string_dtype(df[col]):
            parsed = pd.to_datetime(df[col], errors="coerce")
            if parsed.notna().sum() >= 0.9 * df[col].notna().sum():
                df[col] = parsed
    return df


@st.cache_data(show_spinner="Chargement des données…")
def _read(path: str, mtime: float) -> pd.DataFrame:     # mtime : relit si le fichier change
    p = Path(path)
    if p.suffix.lower() == ".csv":
        df = pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
        if df.shape[1] == 1 and ";" in df.columns[0]:     # export Excel francais
            df = pd.read_csv(p, encoding="utf-8-sig", sep=";", decimal=",", low_memory=False)
    else:
        df = pd.read_parquet(p)
    return _parse_dates(df)


def load(name: str) -> pd.DataFrame | None:
    p = find(name)
    return None if p is None else _read(str(p), _mtime(p))


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
                         "Lignes": _count_rows(str(p), _mtime(p)),
                         "Fichier": p.relative_to(DATA_DIR).as_posix()})
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

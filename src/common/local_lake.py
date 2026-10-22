"""Recherche et lecture des tables exportees par l'equipe dans data/ (dashboard et Partie 4).

Chaque table est cherchee par son nom, quel que soit le format envoye :
    data/station_usage.csv                        export CSV (comme la partie 2)
    data/partie2/station_usage.csv                meme chose dans un sous-dossier
    data/gold/station_usage/                      dossier Parquet ecrit par Spark (partitions cle=valeur)
    data/silver/pollution_sensors/sensors.parquet fichier Parquet seul
Un nom peut etre qualifie ("silver/meteo") pour lever une ambiguite.
Si la table n'est pas dans data/, elle est cherchee dans outputs/ (resultats commites par l'equipe).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("URBANHUB_DATA_DIR", ROOT / "data"))
SEARCH_DIRS = [DATA_DIR, ROOT / "outputs"]           # par ordre de priorite

_PARTITION = re.compile(r"^[^=]+=[^=]*$")          # dossier de partition Spark : annee=2021
_DATE_COLS = {"date", "timestamp", "collected_at", "last_seen", "debut", "fin"}


def _is_table_dir(d: Path) -> bool:
    """Dossier Parquet ecrit par Spark : que des partitions cle=valeur et au moins un .parquet."""
    for sub in d.rglob("*"):
        if sub.is_dir() and not _PARTITION.match(sub.name):
            return False
    return any(d.rglob("*.parquet"))


def _candidates(base: Path) -> list[Path]:
    if not base.exists():
        return []
    out = []
    for p in base.rglob("*"):
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
    for base in SEARCH_DIRS:
        matches = []
        for p in _candidates(base):
            rel = p.relative_to(base).with_suffix("").as_posix() if p.is_file() \
                else p.relative_to(base).as_posix()
            if rel == name or rel.endswith("/" + name):
                matches.append(p)
        if matches:
            return min(matches, key=lambda p: (len(p.relative_to(base).parts), str(p)))
    return None


def display_path(p: Path) -> str:
    return p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else str(p)


def mtime(p: Path) -> float:
    if p.is_file():
        return p.stat().st_mtime
    return max((f.stat().st_mtime for f in p.rglob("*") if f.is_file()), default=0.0)


def _parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if (col in _DATE_COLS or col.endswith("_at") or col.startswith("datetime")) \
                and pd.api.types.is_string_dtype(df[col]):
            parsed = pd.to_datetime(df[col], errors="coerce")
            if parsed.notna().sum() >= 0.9 * df[col].notna().sum():
                df[col] = parsed
    return df


def read(p: Path) -> pd.DataFrame:
    if p.suffix.lower() == ".csv":
        df = pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
        if df.shape[1] == 1 and ";" in df.columns[0]:     # export Excel francais
            df = pd.read_csv(p, encoding="utf-8-sig", sep=";", decimal=",", low_memory=False)
    else:
        df = pd.read_parquet(p)
    return _parse_dates(df)


def load(name: str) -> pd.DataFrame | None:
    p = find(name)
    return None if p is None else read(p)

"""Nettoyage : jointure metadonnees capteur, unites -> ug/m3, valeurs aberrantes, doublons.

Conversion ppb/ppm -> ug/m3 a 25 degC et 1 atm (facteur = masse molaire / 24.45).
"""
import pandas as pd

UG = "µg/m³"

# ug/m3 par ppb
_PER_PPB = {"no2": 46.0055 / 24.45, "o3": 48.0 / 24.45, "co": 28.01 / 24.45}
FACTORS = {}
for _p, _f in _PER_PPB.items():
    FACTORS[(_p, "ppb")] = _f
    FACTORS[(_p, "ppm")] = _f * 1000

# Bornes de plausibilite (ug/m3) : au-dela, on considere la mesure comme une erreur capteur
MAX_PLAUSIBLE = {"pm25": 1000, "pm10": 2000, "no2": 2000, "o3": 1000, "co": 100_000}

META_COLS = ["sensor_id", "pollutant", "unit", "latitude", "longitude", "city", "location_name"]


def clean(raw: pd.DataFrame, sensors: pd.DataFrame) -> pd.DataFrame:
    """raw : sensor_id, timestamp, value.  sensors : table de reference de discover.py."""
    if raw.empty:
        return raw
    df = raw.merge(sensors[META_COLS], on="sensor_id", how="inner")

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["timestamp", "value"])

    # Unites -> ug/m3
    df["unit"] = df["unit"].str.lower().str.replace("µg/m³", "ug/m3", regex=False)
    keys = list(zip(df["pollutant"], df["unit"]))
    factor = pd.Series([FACTORS.get(k, 1.0) for k in keys], index=df.index)
    known = [(u == "ug/m3") or (k in FACTORS) for k, u in zip(keys, df["unit"])]
    df = df[known].copy()
    df["value"] = df["value"] * factor[df.index]
    df["unit"] = UG

    # Valeurs negatives ou aberrantes
    df = df[df["value"] >= 0]
    df = df[df["value"] <= df["pollutant"].map(MAX_PLAUSIBLE)]

    df = df.drop_duplicates(subset=["sensor_id", "timestamp"], keep="last")
    cols = ["sensor_id", "pollutant", "value", "unit", "timestamp",
            "latitude", "longitude", "city", "location_name"]
    return df[cols].sort_values(["sensor_id", "timestamp"]).reset_index(drop=True)

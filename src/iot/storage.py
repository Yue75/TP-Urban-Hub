"""Ecriture/lecture Parquet par couche du Data Lake (raw / clean / curated).

Meme code en local (./data) ou sur MinIO (IOT_STORE_URI=s3://bucket), grace a fsspec.
Arborescence : <racine>/<couche>/iot/date=YYYY-MM-DD/part-<batch>.parquet
"""
import uuid
from datetime import datetime, timezone

import fsspec
import pandas as pd

from . import config


class Store:
    def __init__(self, uri: str | None = None):
        uri = uri or config.STORE_URI
        self.fs, self.root = fsspec.core.url_to_fs(uri, **config.storage_options())

    def write(self, df: pd.DataFrame, layer: str, ts_col: str = "timestamp") -> int:
        """Ecrit df partitionne par date du timestamp. Renvoie le nombre de lignes."""
        if df.empty:
            return 0
        df = df.copy()
        df["_date"] = df[ts_col].dt.strftime("%Y-%m-%d")
        batch = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + uuid.uuid4().hex[:6]
        for date, part in df.groupby("_date"):
            folder = f"{self.root}/{layer}/iot/date={date}"
            self.fs.makedirs(folder, exist_ok=True)
            with self.fs.open(f"{folder}/part-{batch}.parquet", "wb") as f:
                part.drop(columns="_date").to_parquet(f, index=False)
        return len(df)

    def read(self, layer: str) -> pd.DataFrame:
        files = sorted(self.fs.glob(f"{self.root}/{layer}/iot/date=*/*.parquet"))
        frames = []
        for path in files:
            with self.fs.open(path, "rb") as f:
                frames.append(pd.read_parquet(f))
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

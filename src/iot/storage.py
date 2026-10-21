"""Acces au Data Lake : MinIO (boto3) ou dossier local, avec le meme code.

Les cles ressemblent a celles de l'equipe :
    silver/pollution/date=2026-10-21/part-<batch>.parquet
Les Parquet sont lisibles par Spark (s3a://urbanhub/silver/pollution/).
"""
import io
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from . import config

log = logging.getLogger(__name__)


def _to_parquet_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    table = pa.Table.from_pandas(df, preserve_index=False)
    # microsecondes : lisible par Spark 3.5 sans ambiguite
    pq.write_table(table, buf, coerce_timestamps="us", allow_truncated_timestamps=True)
    return buf.getvalue()


def _from_parquet_bytes(data: bytes) -> pd.DataFrame:
    return pq.read_table(io.BytesIO(data)).to_pandas()


class Store:
    def __init__(self, mode: str | None = None):
        self.mode = mode or config.STORE_MODE
        if self.mode == "s3":
            import boto3
            from botocore.exceptions import ClientError
            self._s3 = boto3.client(
                "s3",
                endpoint_url=config.MINIO_ENDPOINT,
                aws_access_key_id=config.MINIO_ACCESS_KEY,
                aws_secret_access_key=config.MINIO_SECRET_KEY,
                region_name="us-east-1",
            )
            try:
                self._s3.head_bucket(Bucket=config.BUCKET)
            except ClientError:
                self._s3.create_bucket(Bucket=config.BUCKET)
                log.info("Bucket %s cree", config.BUCKET)
        else:
            self.root = Path(config.DATA_DIR)

    # ---------------------------------------------------------------- bas niveau
    def put(self, key: str, data: bytes) -> None:
        if self.mode == "s3":
            self._s3.put_object(Bucket=config.BUCKET, Key=key, Body=data)
        else:
            path = self.root / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def get(self, key: str) -> bytes:
        if self.mode == "s3":
            return self._s3.get_object(Bucket=config.BUCKET, Key=key)["Body"].read()
        return (self.root / key).read_bytes()

    def list(self, prefix: str) -> list[str]:
        prefix = prefix.rstrip("/") + "/"
        if self.mode == "s3":
            keys = []
            pager = self._s3.get_paginator("list_objects_v2")
            for page in pager.paginate(Bucket=config.BUCKET, Prefix=prefix):
                keys += [o["Key"] for o in page.get("Contents", [])]
            return sorted(keys)
        base = self.root / prefix
        if not base.exists():
            return []
        return sorted(str(p.relative_to(self.root)).replace("\\", "/")
                      for p in base.rglob("*") if p.is_file())

    def exists(self, key: str) -> bool:
        if self.mode == "s3":
            from botocore.exceptions import ClientError
            try:
                self._s3.head_object(Bucket=config.BUCKET, Key=key)
                return True
            except ClientError:
                return False
        return (self.root / key).exists()

    def delete_prefix(self, prefix: str) -> None:
        for key in self.list(prefix):
            if self.mode == "s3":
                self._s3.delete_object(Bucket=config.BUCKET, Key=key)
            else:
                (self.root / key).unlink()

    def put_file(self, key: str, path: Path) -> None:
        self.put(key, Path(path).read_bytes())

    # ---------------------------------------------------------------- Parquet
    def write_parquet(self, df: pd.DataFrame, prefix: str, ts_col: str = "timestamp") -> int:
        """Ecrit df partitionne par date UTC du timestamp : <prefix>/date=YYYY-MM-DD/part-*.parquet.

        La colonne de partition n'est PAS ecrite dans les fichiers (comme le fait Spark),
        pour eviter tout conflit quand Spark relit le dossier.
        """
        if df.empty:
            return 0
        part_date = df[ts_col].dt.strftime("%Y-%m-%d")
        batch = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + uuid.uuid4().hex[:6]
        for date, part in df.groupby(part_date):
            self.put(f"{prefix}/date={date}/part-{batch}.parquet", _to_parquet_bytes(part))
        return len(df)

    def read_parquet(self, prefix: str) -> pd.DataFrame:
        frames = [_from_parquet_bytes(self.get(k)) for k in self.list(prefix) if k.endswith(".parquet")]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def write_table(self, df: pd.DataFrame, key: str) -> None:
        self.put(key, _to_parquet_bytes(df))

    def read_table(self, key: str) -> pd.DataFrame:
        return _from_parquet_bytes(self.get(key))

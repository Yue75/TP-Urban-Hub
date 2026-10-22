"""
UrbanHub - Migration UNE SEULE FOIS vers le bucket commun de l'equipe.

Ancienne organisation (Ali) : 3 buckets  bronze / silver / gold
Nouvelle organisation (equipe) : 1 bucket "urbanhub" avec les prefixes bronze/ silver/ gold/

Copie les fichiers NOAA deja telecharges (bronze/meteo/...) vers urbanhub/bronze/meteo/...
sans les retelecharger. Silver et Gold seront recrees en relancant le notebook.
"""
import os
try:
    from minio import Minio
except ImportError:                      # conteneur recree : on reinstalle la librairie
    import subprocess, sys
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "minio"], check=True)
    from minio import Minio
from minio.commonconfig import CopySource

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
BUCKET = os.getenv("MINIO_BUCKET", "urbanhub")
client = Minio(MINIO_ENDPOINT.split("://")[1],
               access_key=os.getenv("MINIO_ACCESS_KEY", "urbanhub"),
               secret_key=os.getenv("MINIO_SECRET_KEY", "urbanhub123"),
               secure=MINIO_ENDPOINT.startswith("https"))

if not client.bucket_exists(BUCKET):
    client.make_bucket(BUCKET)
    print(f"Bucket cree : {BUCKET}")

copies = 0
for obj in client.list_objects("bronze", prefix="meteo/", recursive=True):
    client.copy_object(BUCKET, f"bronze/{obj.object_name}", CopySource("bronze", obj.object_name))
    copies += 1
    if copies % 200 == 0:
        print(f"  {copies} fichiers copies...")
print(f"Termine : {copies} fichiers NOAA copies vers {BUCKET}/bronze/meteo/")

"""Data Lake : exploration des couches bronze / silver / gold du bucket MinIO urbanhub."""
import gzip
import io
import json

import boto3
import pandas as pd
import plotly.express as px
import pyarrow.parquet as pq
import streamlit as st
from botocore.exceptions import BotoCoreError, ClientError

import theme
from common import config
from ui import fr

LAYERS = {
    "bronze": ("Bronze", "Données brutes, telles que renvoyées par les sources (JSON, CSV, Parquet), horodatées"),
    "silver": ("Silver", "Données nettoyées et typées : variables de l'énoncé, unités converties, doublons retirés"),
    "gold": ("Gold", "Indicateurs métier prêts pour l'analyse et le dashboard"),
    "reports": ("Reports", "Figures et rapports produits par les pipelines"),
}
# Partie d'origine selon le nom du jeu de données (2e niveau du chemin)
PARTS = {
    "Partie 1 – Météo": ("meteo",),
    "Partie 2 – Vélos": ("citybikes", "stations", "station_usage", "zone_supply", "network_timeseries",
                         "hourly_profile", "geo_balance", "critical_stations", "partie2"),
    "Partie 3 – Pollution": ("openaq", "pollution", "partie3"),
    "Partie 4 – Croisée": ("croise",),
}
PREVIEW_ROWS = 200

st.title("Data Lake – couches bronze, silver, gold")
st.caption(f"Bucket MinIO `{config.BUCKET}` · {config.MINIO_ENDPOINT} · console web : http://localhost:9101 "
           f"(identifiants {config.MINIO_ACCESS_KEY} / {config.MINIO_SECRET_KEY})")


@st.cache_resource
def s3():
    return boto3.client("s3", endpoint_url=config.MINIO_ENDPOINT, aws_access_key_id=config.MINIO_ACCESS_KEY,
                        aws_secret_access_key=config.MINIO_SECRET_KEY, region_name="us-east-1")


def dataset_of(key: str) -> str:
    """Jeu de données = chemin jusqu'au premier dossier de partition (cle=valeur) ou jusqu'au fichier."""
    parts = key.split("/")[:-1]
    out = []
    for p in parts:
        if "=" in p:
            break
        out.append(p)
    return "/".join(out[:3]) or key


def part_of(dataset: str) -> str:
    name = dataset.split("/")[1] if "/" in dataset else dataset
    for part, tokens in PARTS.items():
        if name.startswith(tokens):
            return part
    return "Autre"


@st.cache_data(ttl=60, show_spinner="Lecture du bucket MinIO…")
def inventory() -> pd.DataFrame:
    rows = []
    for page in s3().get_paginator("list_objects_v2").paginate(Bucket=config.BUCKET):
        rows += [{"key": o["Key"], "size": o["Size"], "modified": o["LastModified"]} for o in page.get("Contents", [])]
    df = pd.DataFrame(rows, columns=["key", "size", "modified"])
    df["layer"] = df["key"].str.split("/").str[0]
    df["dataset"] = df["key"].map(dataset_of)
    df["partition"] = df["key"].str.split("/").map(lambda p: "/".join(x for x in p[:-1] if "=" in x))
    df["part"] = df["dataset"].map(part_of)
    return df


try:
    inv = inventory()
except (BotoCoreError, ClientError) as e:
    st.error(f"MinIO injoignable ({e.__class__.__name__}). Démarrer le Data Lake : `docker compose up -d minio`.",
             icon=":material/cloud_off:")
    st.stop()

if inv.empty:
    st.warning("Le bucket est vide : lancer les collectes (voir README).", icon=":material/folder_off:")
    st.stop()

# --------------------------------------------------------------------- vue d'ensemble
cols = st.columns(len(LAYERS))
for col, (layer, (name, desc)) in zip(cols, LAYERS.items()):
    sub = inv[inv["layer"] == layer]
    col.metric(name, f"{fr(sub['size'].sum() / 1e6, 1)} Mo",
               f"{fr(len(sub))} fichiers · {sub['dataset'].nunique()} jeux", delta_color="off", help=desc)

st.code("Sources ──► BRONZE (brut) ──► SILVER (nettoyé, typé) ──► GOLD (indicateurs) ──► dashboard / rapports",
        language=None)

# --------------------------------------------------------------------- lignage par partie
st.subheader("Lignage par partie")
datasets = (inv.groupby(["part", "layer", "dataset"])
            .agg(fichiers=("key", "size"), taille=("size", "sum"), partitions=("partition", "nunique"),
                 maj=("modified", "max")).reset_index())
lineage = (datasets[datasets["layer"].isin(["bronze", "silver", "gold"])]
           .groupby(["part", "layer"])["dataset"].apply(lambda s: "\n".join(f"{d.split('/', 1)[1]}" for d in s))
           .unstack().reindex(index=list(PARTS), columns=["bronze", "silver", "gold"]).fillna("—"))
lineage.columns = ["Bronze", "Silver", "Gold"]
st.dataframe(lineage, width="stretch", row_height=70)
st.caption("« — » : couche absente de ce MinIO (collecte faite sur une autre machine, seules les tables gold "
           "ont été versées avec `python -m common.lake_sync push`).")

sizes = datasets[datasets["layer"].isin(LAYERS)].assign(
    Couche=lambda d: d["layer"].map(lambda l: LAYERS[l][0]), Mo=lambda d: d["taille"] / 1e6)
fig = px.bar(sizes, x="Mo", y="part", color="Couche", orientation="h", custom_data=["dataset", "fichiers"],
             color_discrete_sequence=theme.SERIES, category_orders={"Couche": [v[0] for v in LAYERS.values()],
                                                                    "part": list(PARTS) + ["Autre"]},
             title="Volume stocké par partie et par couche")
fig.update_traces(hovertemplate="%{customdata[0]}<br>%{x:.2f} Mo · %{customdata[1]} fichiers<extra></extra>")
fig.update_layout(height=300, yaxis_title=None, xaxis_title="Mo", legend_title=None, bargap=0.35,
                  legend=dict(orientation="h", y=1.02, x=0, yanchor="bottom"))
theme.show(fig)

# --------------------------------------------------------------------- explorateur
st.subheader("Explorer une couche")
tabs = st.tabs([LAYERS[l][0] for l in LAYERS])
for tab, layer in zip(tabs, LAYERS):
    with tab:
        st.caption(LAYERS[layer][1])
        ds = datasets[datasets["layer"] == layer].sort_values(["part", "dataset"])
        if ds.empty:
            st.info("Aucun fichier dans cette couche.")
            continue
        view = ds.assign(Mo=(ds["taille"] / 1e6).round(2), maj=ds["maj"].dt.tz_convert("Europe/Paris")
                         .dt.strftime("%d/%m/%Y %H:%M"))
        st.dataframe(view[["part", "dataset", "fichiers", "partitions", "Mo", "maj"]]
                     .rename(columns={"part": "Partie", "dataset": "Jeu de données", "fichiers": "Fichiers",
                                      "partitions": "Partitions", "maj": "Dernière écriture"}),
                     hide_index=True, width="stretch")
        name = st.selectbox("Aperçu du jeu de données", ds["dataset"].tolist(), key=f"sel_{layer}")
        files = inv[inv["dataset"] == name].sort_values("modified", ascending=False)
        data_files = files[files["key"].str.endswith((".parquet", ".jsonl.gz", ".json", ".csv", ".gz"))]
        if data_files.empty:
            images = files[files["key"].str.endswith(".png")]
            if len(images):
                key = st.selectbox("Figure", images["key"].tolist(), key=f"img_{layer}")
                st.image(s3().get_object(Bucket=config.BUCKET, Key=key)["Body"].read(), caption=key)
            else:
                st.dataframe(files[["key", "size", "modified"]], hide_index=True, width="stretch")
            continue
        key = st.selectbox("Fichier (le plus récent en premier)", data_files["key"].tolist(), key=f"file_{layer}")

        @st.cache_data(ttl=300, show_spinner="Lecture du fichier…")
        def preview(k: str) -> pd.DataFrame:
            body = s3().get_object(Bucket=config.BUCKET, Key=k)["Body"].read()
            if k.endswith(".parquet"):
                return pq.read_table(io.BytesIO(body)).slice(0, PREVIEW_ROWS).to_pandas()
            if k.endswith(".csv"):
                return pd.read_csv(io.BytesIO(body), nrows=PREVIEW_ROWS)
            text = gzip.decompress(body).decode("utf-8") if k.endswith(".gz") else body.decode("utf-8")
            lines = text.splitlines()
            if len(lines) == 1:                                  # JSON unique (ex. réponse Open-Meteo)
                obj = json.loads(lines[0])
                return pd.json_normalize(obj if isinstance(obj, list) else [obj]).head(PREVIEW_ROWS)
            return pd.json_normalize([json.loads(x) for x in lines[:PREVIEW_ROWS]])

        try:
            df = preview(key)
        except Exception as e:  # format inattendu : on montre l'erreur sans casser la page
            st.warning(f"Aperçu impossible : {e}")
            continue
        size = files.loc[files["key"] == key, "size"].iloc[0]
        st.caption(f"`{key}` · {fr(size / 1e3, 1)} Ko · aperçu des {fr(len(df))} premières lignes, "
                   f"{len(df.columns)} colonnes")
        c_data, c_schema = st.columns([3, 1])
        c_data.dataframe(df, width="stretch", height=360)
        c_schema.dataframe(pd.DataFrame({"colonne": df.columns, "type": df.dtypes.astype(str).values}),
                           hide_index=True, width="stretch", height=360)

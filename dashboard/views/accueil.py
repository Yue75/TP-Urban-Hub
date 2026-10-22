import streamlit as st

import lake

st.title("UrbanHub")
st.markdown(
    "Jumeau numérique urbain : collecte, stockage et analyse des données d'une Smart City "
    "pour produire des indicateurs utiles aux décideurs publics."
)

st.subheader("Architecture")
st.code(
    "Sources            NOAA (batch)  ·  CityBikes (streaming)  ·  OpenAQ (IoT)\n"
    "   │\n"
    "Ingestion          téléchargement parallèle · appel API toutes les 2 min 30 · collecte régulière\n"
    "   │\n"
    "Data Lake MinIO    bucket urbanhub : bronze (brut) → silver (nettoyé) → gold (indicateurs)\n"
    "   │\n"
    "Traitement         Spark / pandas\n"
    "   │\n"
    "Analyse            pages Partie 1 à 4 de ce dashboard",
    language=None,
)

st.subheader("État des données")
st.caption(f"Tables lues dans `{lake.DATA_DIR}`")
for partie in lake.TABLES:
    df = lake.status(partie)
    ok = df["État"].str.startswith("✓").sum()
    st.markdown(f"**{partie}** · {ok}/{len(df)} tables disponibles")
    st.dataframe(df, hide_index=True, width="stretch")

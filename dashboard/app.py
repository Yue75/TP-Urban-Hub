"""UrbanHub - dashboard Streamlit (une page par partie du TP).

Lancement depuis la racine du repo :  streamlit run dashboard/app.py
"""
import streamlit as st

import theme  # noqa: F401  (enregistre le theme Plotly "urbanhub")

st.set_page_config(page_title="UrbanHub", page_icon=":material/location_city:", layout="wide")

pages = st.navigation([
    st.Page("views/accueil.py", title="Accueil", icon=":material/home:", default=True),
    st.Page("views/p1_meteo.py", title="Partie 1 – Météo", icon=":material/partly_cloudy_day:"),
    st.Page("views/p2_velos.py", title="Partie 2 – Vélos", icon=":material/pedal_bike:"),
    st.Page("views/p3_pollution.py", title="Partie 3 – Pollution", icon=":material/air:"),
    st.Page("views/p4_croisee.py", title="Partie 4 – Analyse croisée", icon=":material/hub:"),
])
pages.run()

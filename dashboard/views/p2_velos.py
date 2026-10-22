import streamlit as st

import ui

ui.header(
    "Partie 2 – Flux streaming : mobilité urbaine",
    "Source : API CityBikes · 10 réseaux de vélos en libre-service · relevé toutes les 2 min 30",
    [
        "Quelles stations présentent le plus fort taux d'utilisation ?",
        "Peut-on identifier des zones où l'offre de vélos est insuffisante ?",
        "Quels sont les pics d'utilisation journaliers du réseau de vélos ?",
        "Existe-t-il des déséquilibres géographiques dans la disponibilité des vélos ?",
        "Peut-on détecter des stations critiques nécessitant un rééquilibrage des vélos ?",
    ],
)
ui.data_status("Partie 2 – Vélos")
st.info("Page en construction.", icon=":material/construction:")

import streamlit as st

import ui

ui.header(
    "Partie 1 – Flux batch : météo urbaine",
    "Source : NOAA Global Hourly · stations françaises · 2021 → août 2025",
    [
        "Peut-on identifier des périodes météorologiques anormales ?",
        "Existe-t-il une corrélation entre conditions météorologiques et visibilité ?",
        "Quelle est l'évolution saisonnière de la température en France ; dans les principales villes ?",
        "Quels sont les jours présentant des conditions météorologiques extrêmes ?",
    ],
)
ui.data_status("Partie 1 – Météo")
st.info("Page en construction.", icon=":material/construction:")

import streamlit as st

import ui

ui.header(
    "Partie 3 – Flux IoT : pollution urbaine",
    "Source : API OpenAQ · capteurs des principales villes de France · PM2.5, PM10, NO₂, O₃, CO",
    [
        "Quelles zones présentent les niveaux de pollution les plus élevés ?",
        "Existe-t-il une variation journalière de la pollution ?",
        "Quels polluants sont les plus dominants dans la ville étudiée ?",
        "Peut-on identifier des épisodes de pollution anormale ?",
    ],
)
ui.data_status("Partie 3 – Pollution")
st.info("Page en construction.", icon=":material/construction:")

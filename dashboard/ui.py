"""Elements d'interface communs aux pages."""
import streamlit as st

import lake


def header(title: str, source: str, questions: list[str]) -> None:
    st.title(title)
    st.caption(source)
    with st.container(border=True):
        st.markdown("**Questions métier**")
        st.markdown("\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1)))


def data_status(partie: str) -> None:
    df = lake.status(partie)
    ok = df["État"].str.startswith("✓").sum()
    with st.expander(f"Données utilisées : {ok}/{len(df)} tables disponibles"):
        st.dataframe(df, hide_index=True, width="stretch")


def reading(markdown: str) -> None:
    """Encadre d'interpretation sous les graphiques d'une question."""
    with st.container(border=True):
        st.markdown("**Lecture**\n\n" + markdown)


def fr(x: float, decimals: int = 0) -> str:
    """Nombre au format francais : 12 345,6"""
    return f"{x:,.{decimals}f}".replace(",", " ").replace(".", ",")


def pct(x: float, decimals: int = 0) -> str:
    """Part (0-1) en pourcentage au format francais : 42 %"""
    return f"{x * 100:.{decimals}f} %".replace(".", ",")

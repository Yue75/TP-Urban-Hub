"""Elements d'interface communs aux pages."""
import base64
import json
from pathlib import Path

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


def gallery(title: str, images: list[tuple[str, bytes | Path]], ncols: int = 2) -> None:
    """Figures statiques du rapport (PNG des pipelines), en grille dans un volet repliable."""
    if not images:
        return
    with st.expander(f"{title} ({len(images)})", icon=":material/image:"):
        cols = st.columns(ncols)
        for i, (caption, img) in enumerate(images):
            cols[i % ncols].image(str(img) if isinstance(img, Path) else img, caption=caption, width="stretch")


def png_files(folder: Path) -> list[tuple[str, Path]]:
    """PNG d'un dossier de sorties, legende = nom du fichier."""
    return [(p.stem.replace("_", " "), p) for p in sorted(folder.glob("*.png"))] if folder.exists() else []


@st.cache_data(show_spinner=False)
def _notebook_pngs(path: str, mtime: float) -> list[tuple[str, bytes]]:
    nb = json.loads(Path(path).read_text(encoding="utf-8"))
    out, section = [], ""
    for cell in nb["cells"]:
        src = "".join(cell["source"])
        if cell["cell_type"] == "markdown" and src.lstrip().startswith("#"):
            section = src.lstrip("# ").splitlines()[0]
        for o in cell.get("outputs", []):
            png = o.get("data", {}).get("image/png")
            if png:
                out.append((section, base64.b64decode("".join(png) if isinstance(png, list) else png)))
    return out


def notebook_pngs(path: Path) -> list[tuple[str, bytes]]:
    """Graphiques enregistres dans les sorties d'un notebook (legende = titre de section)."""
    return _notebook_pngs(str(path), path.stat().st_mtime) if path.exists() else []

"""Theme graphique commun a toutes les pages (Plotly).

Palette categorielle validee daltonisme (ordre fixe, jamais recycle) et couleurs fixes
par ville : une ville garde la meme couleur sur toutes les pages.
"""
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# Encre et surfaces
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'

# Palette categorielle (ordre = mecanisme de securite daltonisme, ne pas reordonner)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
          "#e87ba4", "#008300", "#6250d6", "#e34948"]

# Villes communes aux 3 flux (config/cities.yaml) : couleur fixe.
# Les autres villes du reseau velo (Lille, Nantes...) sont en gris "Autres villes".
CITY_COLORS = {
    "Paris": SERIES[0], "Lyon": SERIES[1], "Marseille": SERIES[2],
    "Toulouse": SERIES[3], "Bordeaux": SERIES[4],
}
OTHER = "#b5b3ab"
FRANCE = INK                                   # agregat national : encre, trait pointille

# Rampe sequentielle (une teinte, clair -> fonce)
SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

# Statuts (reserves : jamais utilises comme couleur de serie, toujours avec un libelle)
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}


def city_color(city: str) -> str:
    return CITY_COLORS.get(city, OTHER)


def _axis() -> dict:
    return dict(gridcolor=GRID, linecolor=AXIS, zerolinecolor=AXIS, tickcolor=AXIS,
                tickfont=dict(color=MUTED), title=dict(font=dict(color=INK_2)),
                showline=True, ticks="outside", ticklen=4)


pio.templates["urbanhub"] = go.layout.Template(layout=dict(
    font=dict(family=FONT, color=INK, size=13),
    paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
    colorway=SERIES,
    title=dict(font=dict(size=16, color=INK), x=0, xanchor="left"),
    xaxis=_axis(), yaxis=_axis(),
    legend=dict(font=dict(color=INK_2), bgcolor="rgba(0,0,0,0)"),
    hoverlabel=dict(bgcolor="white", bordercolor=AXIS, font=dict(family=FONT, color=INK)),
    hovermode="closest",
    margin=dict(l=10, r=10, t=50, b=10),
    colorscale=dict(sequential=SEQUENTIAL),
))
pio.templates.default = "urbanhub"


def show(fig: go.Figure, **kwargs) -> None:
    """Affiche une figure avec le theme UrbanHub (et non celui de Streamlit)."""
    st.plotly_chart(fig, theme=None, width="stretch", **kwargs)

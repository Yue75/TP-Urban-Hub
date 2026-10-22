# UrbanHub – Dashboard

Dashboard Streamlit : une page par partie du TP (météo, vélos, pollution) et une page d'analyse croisée.

## Lancement

Depuis la racine du repo :

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r dashboard/requirements.txt
.venv/bin/streamlit run dashboard/app.py        # http://localhost:8501
```

## Partie 4 : fusion des données

La page Analyse croisée lit les tables produites par le pipeline de fusion ([src/croise/fusion.py](../src/croise/fusion.py)) :

```bash
PYTHONPATH=src .venv/bin/python -m croise.fusion                  # écrit dans data/gold/
IOT_STORE=s3 PYTHONPATH=src .venv/bin/python -m croise.fusion     # écrit dans MinIO (bucket urbanhub)
```

| Table | Grain | Contenu |
|---|---|---|
| `gold/croise_horaire_ville` | ville × heure UTC | météo Open-Meteo, PM2.5, PM10, NO₂, O₃, CO, activité vélo + indicateurs `has_weather/has_pollution/has_bikes` |
| `gold/croise_journalier_ville` | ville × jour (Paris) | agrégats journaliers des mêmes variables |

Clé de jointure : `city` + `timestamp` (début de l'heure, UTC). Les heures CityBikes (heure de Paris) sont converties en UTC ;
les réseaux vélo sans activité mesurable (Marseille) et les villes sans météo ni pollution sont exclus.
À relancer après chaque nouvel export de données.

## Données

Le dashboard lit les tables dans `data/` (ou le dossier indiqué par `URBANHUB_DATA_DIR`).
Chaque table est cherchée **par son nom**, quel que soit le format reçu :

| Format | Exemple |
|---|---|
| CSV (`,` ou `;`) | `data/station_usage.csv`, `data/partie2/station_usage.csv` |
| Dossier Parquet Spark (partitions `cle=valeur`) | `data/gold/meteo/journalier/annee=2021/part-….parquet` |
| Fichier Parquet | `data/silver/pollution_sensors/sensors.parquet` |

La liste des tables attendues par partie est dans [lake.py](lake.py) (`TABLES`) ; l'accueil du dashboard
indique celles qui sont présentes. Une page dont les données manquent l'affiche au lieu de planter.

Une table absente de `data/` est ensuite cherchée dans `outputs/` (résultats commités par l'équipe) : c'est
le cas du classement des stations de pollution (`outputs/partie3/tables/q1_ranking_stations.csv`).

La page Pollution réutilise directement les méthodes de la partie 3 (`src/iot/analysis.py` : profil journalier,
comparaison aux valeurs guides OMS, détection des épisodes) pour que les résultats soient identiques.

## Organisation

| Fichier | Rôle |
|---|---|
| `app.py` | Point d'entrée, navigation entre les pages |
| `lake.py` | Lecture des tables avec cache Streamlit (recherche dans `src/common/local_lake.py`) |
| `theme.py` | Thème Plotly commun, couleur fixe par ville |
| `ui.py` | En-tête de page (questions métier) et état des données |
| `views/` | Une page par partie |

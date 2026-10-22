# UrbanHub – Partie 1 : Flux Batch (météo)

Collecte, nettoyage et analyse de la météo horaire des stations françaises, organisées en architecture médaillon (Bronze / Silver / Gold) dans le data lake MinIO commun de l'équipe.

Deux sources :

| Source | Période | Rôle |
|---|---|---|
| **NOAA Global Hourly** (source de l'énoncé) | 2021 → 24 août 2025, 211 stations françaises | Questions métier de la Partie 1 |
| **Open-Meteo** (API gratuite, sans clé) | 92 derniers jours, heure par heure, 5 villes | **Partie 4** : jours communs avec les vélos et la pollution |

> Les données NOAA s'arrêtent au 24 août 2025 : sans Open-Meteo, la météo n'aurait aucun jour en commun avec les vélos et la pollution (2026).

## Conventions de l'équipe

- Un seul bucket **`urbanhub`**, préfixes `bronze/<source>`, `silver/<source>`, `gold/<table>`
- Colonne ville : **`city`** (Paris, Lyon, Marseille, Toulouse, Bordeaux)
- `timestamp` en **UTC** + **`date_local`** / **`hour_local`** en heure de Paris (Europe/Paris) pour les jointures
- Fichiers **Parquet**
- Identifiants MinIO lus dans les variables `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET` (défaut : `urbanhub` / `urbanhub123`)

## Architecture

```
NOAA Global Hourly (S3 public : noaa-global-hourly-pds)        Open-Meteo (API)
      │  meteo_batch.py : 16 téléchargements en parallèle            │  meteo_recente.py
      ▼                                                              ▼
🥉 urbanhub/bronze/meteo/annee=AAAA/                     urbanhub/bronze/meteo_recente/
      │  Spark (meteo_silver_gold.ipynb)                             │  pandas
      ▼                                                              ▼
🥈 urbanhub/silver/meteo/annee=AAAA/                     urbanhub/silver/meteo_recente/
      │  Spark                                                       │
      ▼                                                              ▼
🥇 urbanhub/gold/meteo/...  (Partie 1)                   urbanhub/gold/meteo_horaire_ville/   ← Partie 4
                                                         urbanhub/gold/meteo_journaliere_ville/
```

## Fichiers

| Fichier | Rôle |
|---|---|
| `docker-compose.yml` | MinIO + JupyterLab/PySpark (identifiants de l'équipe) |
| `meteo_batch.py` | Collecte NOAA en parallèle → Bronze |
| `meteo_silver_gold.ipynb` | Nettoyage (Silver), indicateurs (Gold), analyses et graphiques |
| `meteo_recente.py` | Météo récente Open-Meteo → Bronze, Silver et Gold (Partie 4) |
| `export_gold_meteo.py` | Export des tables Gold en CSV + LISEZMOI (zip pour l'équipe) |
| `migration_urbanhub.py` | Une seule fois : copie l'ancien bucket `bronze` vers `urbanhub/bronze` |

## Lancer le projet

1. Démarrer l'environnement :
```bash
docker compose up -d
```
   - Console MinIO : http://localhost:9001 (urbanhub / urbanhub123)
   - JupyterLab : http://localhost:8888
2. Copier les `.py` dans `scripts/` et le notebook dans `notebooks/` (les scripts installent `minio` tout seuls si besoin).
3. Collecter NOAA (Bronze) :
```bash
docker exec urbanhub-jupyter python -u /home/jovyan/work/scripts/meteo_batch.py test   # 3 stations
docker exec urbanhub-jupyter python -u /home/jovyan/work/scripts/meteo_batch.py        # toutes (≈ 20 min)
```
4. Ouvrir `meteo_silver_gold.ipynb` et exécuter toutes les cellules (≈ 10 min).
5. Météo récente pour la Partie 4 (à relancer avant la démo pour avoir les derniers jours) :
```bash
docker exec urbanhub-jupyter python /home/jovyan/work/scripts/meteo_recente.py
```
6. Export CSV pour l'équipe : `docker exec urbanhub-jupyter python /home/jovyan/work/scripts/export_gold_meteo.py` → `data/export_gold_meteo.zip`

## Données produites

| Couche | Chemin (bucket `urbanhub`) | Contenu | Volume |
|---|---|---|---|
| Bronze | `bronze/meteo/` | NOAA, 211 stations, 10 colonnes brutes | 1 027 fichiers, 14 028 602 lignes |
| Silver | `silver/meteo/` | NOAA décodé et nettoyé, + `city`, `date_local`, `hour_local` | 11 076 139 lignes |
| Gold | `gold/meteo/journalier/` | NOAA, une ligne par station et par jour | 304 269 lignes |
| Gold | `gold/meteo/temperature_mensuelle/` | Température moyenne par mois, 5 villes + France | 336 lignes |
| Gold | `gold/meteo/anomalies_france/` | Écart quotidien à la normale du mois | 1 692 lignes |
| Gold | `gold/meteo/jours_extremes_villes/` | Jours de chaleur, froid, vent ou pluie extrêmes | 379 lignes |
| Bronze | `bronze/meteo_recente/` | Open-Meteo, réponses brutes (JSON) | |
| Silver | `silver/meteo_recente/` | Open-Meteo, une ligne par `city` et par heure | ≈ 11 000 lignes |
| **Gold** | **`gold/meteo_horaire_ville/`** | **Table de jointure Partie 4** : `city`, `timestamp`, `date_local`, `hour_local`, temperature, humidity, precipitation, wind_speed, wind_direction, pressure, visibility, cloud_cover | ≈ 11 000 lignes |
| Gold | `gold/meteo_journaliere_ville/` | Open-Meteo, une ligne par `city` et par jour | ≈ 465 lignes |

Unités : température °C, vent m/s, direction °, pression hPa, pluie mm, visibilité m, humidité et nuages %.

**Pour la Partie 4 :** joindre `gold/meteo_horaire_ville` avec les tables vélos / pollution sur `city` + `timestamp` (UTC, à l'heure pleine) ou sur `city` + `date_local` + `hour_local`.

## Nettoyage appliqué

NOAA :
- Décodage des colonnes NOAA (ex. `TMP = +0119,1` → 11,9 °C) et conversion des unités
- Codes de valeur manquante (`9999`, `99999`, `999999`) remplacés par des valeurs vides
- Mesures marquées douteuses par la NOAA (codes qualité 2, 3, 6, 7) écartées
- Valeurs physiquement impossibles écartées (ex. température hors de -50 / +50 °C)
- Doublons fusionnés : une ligne par station et par heure (≈ 21 % des lignes brutes)
- Types de colonnes harmonisés (93 fichiers avaient des colonnes vides)
- Ajout de `city` : stations à moins de 30 km du centre (formule de Haversine)

Open-Meteo :
- Une ligne par ville et par heure (en cas de plusieurs extractions, la plus récente est gardée)
- Prévisions écartées (uniquement le passé), mêmes limites physiques que NOAA

## Villes étudiées

Paris (8 stations NOAA), Toulouse (4), Marseille (3), Lyon (2), Bordeaux (1). Open-Meteo : centre de chaque ville (mêmes coordonnées que `config/cities.yaml`).

## Résultats principaux

1. **Périodes anormales** : 28 jours anormalement chauds et 24 froids. 4 épisodes de 3 jours ou plus, dont la vague de froid de février 2021 et la canicule de fin juin 2025.
2. **Météo et visibilité** : corrélations faibles (|r| ≤ 0,13). La pluie et le temps calme (brouillard) réduisent la visibilité, plus faible en hiver.
3. **Saisons** : en France, 5,6 °C en janvier et 21,5 °C en août. Marseille est la plus chaude, Lyon la plus contrastée, Paris a l'été le plus frais.
4. **Jours extrêmes** : Toulouse est la plus exposée à la chaleur (72 jours ≥ 35 °C), Marseille au vent (74 jours, mistral). Les records correspondent à des événements connus (canicule de juin 2022, tempête Ciarán de novembre 2023).

## Limites

- NOAA s'arrête au **24 août 2025** : Open-Meteo complète la période récente (données de modèle, pas de stations).
- La « normale » est calculée sur 2021-2025, et non sur la référence 1991-2020.
- Pas d'humidité dans NOAA (elle est présente dans Open-Meteo).

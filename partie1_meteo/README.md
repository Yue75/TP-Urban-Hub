# UrbanHub – Partie 1 : Flux Batch (météo)

Collecte, nettoyage et analyse de 5 ans de données météo horaires des stations françaises (NOAA Global Hourly), organisées en architecture médaillon (Bronze / Silver / Gold) dans un data lake MinIO.

## Architecture

```
NOAA Global Hourly (bucket S3 public : noaa-global-hourly-pds)
      │  Python + requests + ThreadPoolExecutor (16 téléchargements en parallèle)
      ▼
🥉 urbanhub/bronze/meteo/annee=AAAA/   données brutes, colonnes utiles, Parquet
      │  Spark (JupyterLab)
      ▼
🥈 urbanhub/silver/meteo/annee=AAAA/   décodées, nettoyées, sans doublons, colonne ville
      │  Spark
      ▼
🥇 urbanhub/gold/meteo/             indicateurs : journalier, mensuel, anomalies, extrêmes
      │  pandas + matplotlib
      ▼
📊 Analyses et graphiques (4 questions métier)
```

## Technologies

Docker Compose · MinIO (data lake compatible S3) · Python (requests, pandas, ThreadPoolExecutor) · Apache Spark 3.5 (PySpark) · JupyterLab · Parquet · matplotlib

## Lancer le projet

La partie 1 utilise le MinIO commun de l'équipe (`docker-compose.yml` à la racine du repo, bucket `urbanhub`).

1. Démarrer l'environnement (depuis la racine du repo) :
```bash
   docker compose --profile meteo up -d minio jupyter
```
   - Console MinIO : http://localhost:9101 (urbanhub / urbanhub123)
   - JupyterLab : http://localhost:8888 (le dossier `partie1_meteo/` est monté dans `work/partie1_meteo/`)
2. Collecter les données (couche Bronze) :
```bash
   docker exec urbanhub_jupyter python -u /home/jovyan/work/partie1_meteo/meteo_batch.py test   # 3 stations
   docker exec urbanhub_jupyter python -u /home/jovyan/work/partie1_meteo/meteo_batch.py        # toutes (≈ 20 min)
```
3. Ouvrir `partie1_meteo/meteo_silver_gold.ipynb` dans JupyterLab et exécuter les cellules dans l'ordre.

## Données produites

| Couche | Chemin MinIO (bucket `urbanhub`) | Contenu | Volume |
|---|---|---|---|
| Bronze | `bronze/meteo/` | 211 stations, 2021 → août 2025, 10 colonnes brutes | 1 027 fichiers, 14 028 602 lignes |
| Silver | `silver/meteo/` | Mesures horaires décodées et nettoyées | 11 076 139 lignes |
| Gold | `gold/meteo/journalier/` | Une ligne par station et par jour | 304 269 lignes |
| Gold | `gold/meteo/temperature_mensuelle/` | Température moyenne par mois, 5 villes + France | |
| Gold | `gold/meteo/anomalies_france/` | Écart quotidien à la normale du mois | |
| Gold | `gold/meteo/jours_extremes_villes/` | Jours de chaleur, froid, vent ou pluie extrêmes | |

**Variables (Silver) :** `station_id`, `timestamp` (UTC), `temperature` (°C), `wind_speed` (m/s), `wind_direction` (°), `pressure` (hPa), `precipitation` (mm), `visibility` (m), `latitude`, `longitude`, `ville`.

**Pour la Partie 4 :** joindre sur `gold/meteo/journalier` avec les colonnes `date` et `ville`.

## Nettoyage appliqué

- Décodage des colonnes NOAA (ex. `TMP = +0119,1` → 11,9 °C) et conversion des unités
- Codes de valeur manquante (`9999`, `99999`, `999999`) remplacés par des valeurs vides
- Mesures marquées douteuses par la NOAA (codes qualité 2, 3, 6, 7) écartées
- Valeurs physiquement impossibles écartées (ex. température hors de -50 / +50 °C)
- Doublons fusionnés : une ligne par station et par heure (≈ 21 % des lignes brutes)
- Types de colonnes harmonisés (93 fichiers avaient des colonnes vides)
- Ajout de la `ville` : stations à moins de 30 km du centre (formule de Haversine)

## Villes étudiées

Paris (8 stations), Toulouse (4), Marseille (3), Lyon (2), Bordeaux (1).

## Résultats principaux

1. **Périodes anormales** : 28 jours anormalement chauds et 24 froids. 4 épisodes de 3 jours ou plus, dont la vague de froid de février 2021 et la canicule de fin juin 2025.
2. **Météo et visibilité** : corrélations faibles (|r| ≤ 0,13). La pluie et le temps calme (brouillard) réduisent la visibilité, plus faible en hiver.
3. **Saisons** : en France, 5,6 °C en janvier et 21,5 °C en août. Marseille est la plus chaude, Lyon la plus contrastée, Paris a l'été le plus frais.
4. **Jours extrêmes** : Toulouse est la plus exposée à la chaleur (72 jours ≥ 35 °C), Marseille au vent (74 jours, mistral). Les records correspondent à des événements connus (canicule de juin 2022, tempête Ciarán de novembre 2023).

## Limites

- Les données NOAA s'arrêtent au **24 août 2025** (pas de publication plus récente).
- La « normale » est calculée sur 2021-2025, et non sur la référence 1991-2020.
- L'humidité, facteur principal du brouillard, ne fait pas partie des variables extraites.
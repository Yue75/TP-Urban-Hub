# UrbanHub – Synthèse des résultats

UrbanHub est un jumeau numérique urbain : il collecte trois flux de données d'une Smart City (météo, mobilité
vélo, pollution), les stocke dans un data lake, les traite et les croise pour produire des indicateurs utiles
aux décideurs publics.

Ce document répond aux questions métier des quatre parties du sujet. Chaque réponse renvoie à l'onglet du
dashboard où la retrouver avec ses graphiques. Les chiffres sont ceux du dashboard au 22/10/2026.

| Statut | Signification |
|---|---|
| **Définitif** | Données complètes sur la période : la réponse ne changera pas. |
| **Provisoire** | Dépend des données vélo, qui ne couvrent pour l'instant qu'un après-midi : à mettre à jour avec l'export long (voir § 8). |

---

## 1. Architecture

```
Sources            NOAA Global Hourly (batch) · CityBikes (streaming) · OpenAQ (IoT) · Open-Meteo (météo récente)
   │
Ingestion          téléchargement parallèle (16 threads) · appel API toutes les 2 min 30 · collecte régulière
   │
Data Lake MinIO    bucket urbanhub : bronze (brut) → silver (nettoyé) → gold (indicateurs)
   │
Traitement         Spark (parties 1 et 2) · pandas (parties 3 et 4)
   │
Analyse            dashboard Streamlit : une page par partie + analyse croisée
```

| Flux | Source | Collecte | Période analysée | Volume |
|---|---|---|---|---|
| Batch (Partie 1) | NOAA Global Hourly, stations françaises | [partie1_meteo/meteo_batch.py](partie1_meteo/meteo_batch.py) | 01/01/2021 → 24/08/2025 | 211 stations, 304 269 jours × station |
| Streaming (Partie 2) | API CityBikes, 10 réseaux | [src/collector/collect_citybikes.py](src/collector/collect_citybikes.py) | 21/10/2026 12h22 → 22/10/2026 10h03 | 3 292 stations |
| IoT (Partie 3) | API OpenAQ, 5 villes | [src/iot/](src/iot/) | 22/09/2026 → 22/10/2026 | 191 capteurs, 85 stations |
| Croisement (Partie 4) | Fusion des trois flux + Open-Meteo | [src/croise/fusion.py](src/croise/fusion.py) | 10/09/2026 → 22/10/2026 | 5 085 heures × ville |

Les cinq villes communes aux trois flux sont Paris, Lyon, Marseille, Toulouse et Bordeaux
([config/cities.yaml](config/cities.yaml)). Le flux vélo couvre en plus Lille, Nantes, Rennes, Strasbourg et
Montpellier.

---

## 2. Partie 1 – Flux batch : météo urbaine · Définitif

Page **Partie 1 – Météo** du dashboard.

**Q1. Peut-on identifier des périodes météorologiques anormales ?** *(onglet Q1)*
Oui. En comparant chaque jour à la normale du mois (écart > 2 écarts-types), on compte **28 jours anormalement
chauds et 24 anormalement froids** sur 1 692 jours (3,1 %). Quatre périodes d'au moins 3 jours se détachent :

- vague de froid du 11 au 13/02/2021 (jusqu'à −9,2 °C par rapport à la normale) ;
- vague de froid du 01 au 04/04/2022 (−7,8 °C) ;
- vague de chaleur du 17 au 19/05/2022 (+6,0 °C) ;
- vague de chaleur du 28/06 au 01/07/2025 (+8,0 °C).

2025 est l'année avec le plus de jours anormalement chauds (12), 2021 celle avec le plus de jours froids (11).

**Q2. Existe-t-il une corrélation entre conditions météorologiques et visibilité ?** *(onglet Q2)*
Les corrélations linéaires sont **faibles** (la plus forte : température, r = 0,21), mais des effets nets
apparaissent par classes :

- la pluie réduit la visibilité : 18,9 km les jours secs contre 14,6 km les jours de forte pluie ;
- la relation avec le vent n'est pas linéaire : la visibilité est plus faible par temps calme (14,7 km,
  brouillard) et par vent fort (14,3 km, perturbations) qu'entre les deux (16,9 km) ;
- la visibilité est minimale en janvier (14,5 km) et maximale en septembre (18,5 km).

**Q3. Quelle est l'évolution saisonnière de la température ?** *(onglet Q3)*
En France, la température moyenne passe de **5,6 °C en janvier à 21,5 °C en août**. Marseille est la ville la
plus chaude (16,6 °C en moyenne annuelle, 26,1 °C en été), Paris la plus fraîche (12,7 °C, été à 20,4 °C).
Lyon a le climat le plus contrasté (19,1 °C d'écart entre le mois le plus froid et le plus chaud), Paris le
moins contrasté (15,9 °C).

**Q4. Quels sont les jours présentant des conditions extrêmes ?** *(onglet Q4)*

| Type | Seuil | Jours (5 villes) | Ville la plus touchée |
|---|---|---|---|
| Forte chaleur | Tmax ≥ 35 °C | 243 | Toulouse (72) |
| Vent violent | rafale ≥ 17 m/s | 84 | Marseille (74, mistral) |
| Grand froid | Tmin ≤ −5 °C | 43 | Lyon (18) |
| Fortes pluies | ≥ 40 mm/jour | 9 | Lyon (6) |

Les étés 2022 (82 jours de forte chaleur), 2025 (79) et 2023 (46) concentrent la chaleur extrême. Records
nationaux : 43,0 °C le 18/07/2022 (Biscarosse Parentis) et −16,0 °C le 14/02/2021 (Bâle-Mulhouse).

---

## 3. Partie 2 – Flux streaming : mobilité urbaine · Provisoire

Page **Partie 2 – Vélos** du dashboard. L'activité est estimée à partir des variations du nombre de vélos entre
deux relevés (baisse = départs, hausse = arrivées) : c'est une borne basse de l'activité réelle. Le réseau de
Marseille est exclu (voir § 7).

**Q1. Quelles stations présentent le plus fort taux d'utilisation ?** *(onglet Q1)*
Taux d'utilisation = rotations quotidiennes par point d'attache. Toulouse est le réseau le plus sollicité
(**9,0 rotations par place et par jour**), Strasbourg le moins (0,4). Station la plus utilisée : **Cartoucherie
Tramway** à Toulouse (38,0 rotations par place et par jour) ; à Paris, **Chabrol – d'Hauteville** (18,8).

**Q2. Peut-on identifier des zones où l'offre est insuffisante ?** *(onglet Q2)*
Oui. Sur un maillage d'environ 1 km², **74 mailles sur 349 à Paris (21 %)** sont en offre insuffisante ; Lyon est
le réseau le plus touché (25 % de ses mailles). La maille en déficit la plus demandée, à Paris, enregistre environ
1 051 départs par jour pour 47 vélos disponibles en moyenne : c'est là qu'un renfort d'offre aurait le plus d'effet.

**Q3. Quels sont les pics d'utilisation journaliers ?** *(onglet Q3)*
Sur l'après-midi observé (12h-17h), l'activité augmente jusqu'à la fin de journée : dans **6 réseaux sur 9, le
pic est à 17h**, début de la pointe du soir (Paris : environ 10 000 mouvements par heure). Les données ne couvrent
ni le matin, ni la soirée, ni le week-end.

**Q4. Existe-t-il des déséquilibres géographiques ?** *(onglet Q4)*
Oui. À Paris, les stations à moins de 2 km du centre sont remplies à **68 %**, contre **30 %** entre 4 et 6 km.
Le centre est mieux pourvu que la périphérie à Paris, Nantes et Rennes ; c'est l'inverse à Montpellier et
Strasbourg. 138 stations sont vides plus de la moitié du temps et 33 pleines plus de la moitié du temps.

**Q5. Peut-on détecter des stations critiques ?** *(onglet Q5)*
Oui. **343 stations sont vides chroniques** et **143 pleines chroniques** (vides ou pleines plus de 25 % du
temps). Pour les ramener à 50 % de remplissage, il faudrait apporter environ **3 008 vélos** et en retirer
1 236 (Paris : 121 stations à réapprovisionner, 87 à délester). 71 % des stations critiques sont vides : le
besoin principal est d'apporter des vélos. La liste priorisée est téléchargeable depuis le dashboard.

---

## 4. Partie 3 – Flux IoT : pollution urbaine · Définitif

Page **Partie 3 – Pollution** du dashboard. Les profils, les comparaisons aux valeurs guides OMS et la
détection d'épisodes utilisent directement les fonctions de la partie 3 ([src/iot/analysis.py](src/iot/analysis.py)).

**Q1. Quelles zones présentent les niveaux de pollution les plus élevés ?** *(onglet Q1)*
Les stations de **proximité trafic** : l'autoroute A1 à Saint-Denis arrive en tête pour le NO₂ (49,7 µg/m³ en
moyenne), les PM10 (37,1) et les PM2.5 (12,7). Parmi les 5 stations les plus exposées au NO₂, 4 sont le long
d'axes routiers (A1, périphérique de Lyon, boulevard périphérique Est, RN20). Pour l'ozone, la station la plus
exposée est hors du centre : Sausset-les-Pins, à 21 km de Marseille (76,0 µg/m³). Par ville, Paris est la plus exposée
au NO₂ (25,1 µg/m³) et aux PM10 (18,2), Marseille aux PM2.5 (8,3) et à l'O₃ (64,7).

**Q2. Existe-t-il une variation journalière de la pollution ?** *(onglet Q2)*
Oui, avec un rythme propre à chaque polluant :

- **NO₂ : deux pics**, vers 10h et vers 22h (le maximum vaut 1,9 à 3,2 fois le minimum de la journée) :
  rythme du trafic, renforcé le soir par une couche d'air plus basse qui disperse moins ;
- **O₃ : pic vers 17h** (2,0 à 3,2 fois le minimum) : l'ozone se forme sous l'effet du soleil ;
- **PM2.5 et PM10 : pics en fin de matinée** (vers 10h et 12h).

**Q3. Quels polluants sont les plus dominants ?** *(onglet Q3)*
Les concentrations n'étant pas comparables entre polluants, chacun est rapporté à sa valeur guide OMS 2021 sur
24 h. Le **NO₂ domine à Paris, Lyon et Marseille** ; à Paris il dépasse la valeur guide en moyenne (1,01 fois)
et 50 % des jours. L'**O₃ domine à Toulouse et Bordeaux**. Les particules restent sous les valeurs guides
(rapport maximal 0,56).

**Q4. Peut-on identifier des épisodes de pollution anormale ?** *(onglet Q4)*
Oui : **23 épisodes** (au moins 3 heures nettement au-dessus du niveau habituel de la ville à cette heure).
Ils concernent surtout le NO₂ (14 épisodes) et Bordeaux (10). Le plus intense : NO₂ à Toulouse le 23/09 de 22h
à 2h, avec un pic à 99,9 µg/m³ pour un niveau habituel de 12,2. 61 % des épisodes commencent en soirée.

---

## 5. Partie 4 – Analyse croisée

Page **Partie 4 – Analyse croisée** du dashboard. Les trois flux sont fusionnés par ville et par heure UTC
([src/croise/fusion.py](src/croise/fusion.py)) avec la météo récente Open-Meteo, car la NOAA s'arrête en août
2025. Le croisement météo × pollution repose sur **3 559 heures** ; le croisement avec les vélos sur seulement
**20 heures** (4 villes, un après-midi).

**Q1. Existe-t-il une relation entre météo et pollution ?** *(onglet Q1)* · Définitif
**Oui, nettement**, et dans des sens opposés selon le polluant :

- **le vent disperse le NO₂** : dans les 5 villes, le NO₂ est 1,8 à 3,1 fois plus faible par vent fort que par
  vent faible (corrélation journalière r = −0,62) ;
- **la chaleur favorise l'ozone** : dans les 5 villes, l'O₃ augmente avec la température, jusqu'à 3,7 fois plus
  au-delà de 24 °C ;
- **la pluie lessive les particules** : les PM10 sont plus faibles de 28 % en moyenne sous la pluie (4 villes
  sur 5).

**Q2. La météo influence-t-elle l'utilisation des vélos ?** *(onglet Q2)* · Provisoire
**Pas de conclusion possible avec les données actuelles.** Sur les 20 heures disponibles, l'activité suit surtout
l'heure de la journée (r = 0,77), et la météo varie elle-même au fil de l'après-midi (nébulosité, humidité,
température) : on ne peut pas séparer les deux effets. Il faut plusieurs jours de collecte, avec de la pluie et
des week-ends, pour comparer des heures identiques sous des météos différentes.

**Q3. Peut-on identifier des conditions favorables à la mobilité douce ?** *(onglet Q3)* · Provisoire
Les données vélo ne permettent pas encore de mesurer l'activité par classe de météo (moins de 10 heures par
classe). Le dashboard compte en revanche les créneaux favorables selon des critères réglables, validés par
l'équipe : **température de 10 à 25 °C, pas de pluie, vent ≤ 6 m/s, entre 7h et 21h**. Sur la période, 71 % des
heures de journée sont favorables. Paris est la ville la plus favorable (83 %), Marseille la moins (58 % : température hors plage
28 % des heures, vent trop fort 11 %). La température hors plage est le critère le plus souvent bloquant (21 % des heures).

**Q4. Existe-t-il des périodes où mobilité, pollution et météo interagissent fortement ?** *(onglet Q4)* · Provisoire
L'interaction **météo × pollution** est forte : **91 % des épisodes de pollution** surviennent avec un vent plus
faible que d'habitude (1,2 m/s en moyenne contre 2,1 m/s), et 61 % commencent le soir, quand l'air se mélange
moins. Aucun épisode ne tombe pendant la collecte vélo : l'effet d'un épisode sur la mobilité reste à mesurer.

---

## 6. Ce qu'il faut retenir

1. **Le trafic routier est au cœur de la pollution urbaine** : stations de proximité trafic en tête, NO₂ dominant
   dans les trois plus grandes villes, pics aux heures de déplacement.
2. **La météo module fortement la pollution** : un temps calme piège le NO₂, surtout le soir ; un temps chaud
   et ensoleillé produit de l'ozone, y compris en périphérie.
3. **Les réseaux vélo sont déséquilibrés** : centres mieux pourvus à Paris, nombreuses stations vides
   chroniques, besoin d'environ 3 000 vélos à redistribuer.
4. **Le lien entre météo et mobilité douce reste à établir** : il faut un historique vélo de plusieurs jours.

---

## 7. Choix de méthode et limites

| Sujet | Choix | Raison |
|---|---|---|
| Jours météo fiables | Jours avec au moins 12 mesures horaires (91 % des jours) | Sans ce filtre, une station affiche 48,6 °C de moyenne journalière calculée sur 2 mesures |
| Normale de température | Moyenne 2021-2025 | Seules données disponibles ; une année chaude « relève » la normale (référence officielle : 1991-2020) |
| Visibilité (P1 Q2) | Corrélations sur moyennes journalières | Les mesures horaires NOAA n'ont pas été exportées ; le calcul horaire de la partie 1 donne des r encore plus faibles (≤ 0,13) |
| Données NOAA | S'arrêtent au 24/08/2025 | Pas de publication plus récente ; la Partie 4 utilise Open-Meteo |
| Réseau de Marseille | Exclu par défaut (interrupteur dans le dashboard) | Ses 122 stations affichent 0 vélo à chaque relevé, sans mouvement : activité non mesurable |
| Classement des stations vélo | Stations observées moins de 1 h écartées (réglable) | Un mouvement extrapolé sur une journée donne un taux artificiel |
| Profil horaire vélo | Heures observées moins de 30 min écartées | Coupures de collecte (12h55 → 13h52 et 16h46 → 16h58 le 21/10) |
| Classement des stations de pollution | Tableau produit par la partie 3 ([outputs/partie3/tables/q1_ranking_stations.csv](outputs/partie3/tables/q1_ranking_stations.csv)) | Les mesures par capteur n'ont pas été exportées ; les stations n'ont pas toutes mesuré pendant toute la période (227 à 720 h) |
| CO | Peu représentatif | 1 à 4 capteurs, absent à Toulouse et Bordeaux |
| Polluant dominant | Rapport à la valeur guide OMS 2021 sur 24 h | Les concentrations en µg/m³ ne sont pas comparables d'un polluant à l'autre |
| Corrélations météo × pollution | Journalières, en écart à la moyenne de chaque ville (vue horaire disponible) | Neutralise le cycle jour/nuit et les différences entre villes |
| Conditions favorables (P4 Q3) | 10-25 °C, pas de pluie, vent ≤ 6 m/s, 7h-21h | Hypothèses validées par l'équipe, à confirmer avec un historique vélo |
| Données vélo | Un après-midi de semaine | Collecte récente ; voir § 8 |

---

## 8. Reproduire et mettre à jour

```bash
# Collecte et data lake (MinIO commun, bucket urbanhub)
docker compose up -d --build                                   # MinIO + collecteur vélos (toutes les 2 min 30)
docker compose run --rm spark python -m spark_jobs.pipeline    # Partie 2 : bronze -> silver -> gold
docker compose --profile meteo up -d jupyter                   # Partie 1 : meteo_batch.py + notebook

# Partie 4 : tables gold croisées
PYTHONPATH=src .venv/bin/python -m croise.fusion

# Dashboard
.venv/bin/pip install -r dashboard/requirements.txt
.venv/bin/streamlit run dashboard/app.py
```

Le dashboard lit les exports déposés dans `data/` (CSV ou Parquet, voir [dashboard/README.md](dashboard/README.md)).

**Après réception de l'export vélo long** :

1. Remplacer les CSV de la partie 2 dans `data/`. Les pages Vélos et Analyse croisée se recalculent seules,
   textes de lecture compris.
2. Relancer `PYTHONPATH=src .venv/bin/python -m croise.fusion` pour mettre à jour les tables gold du data lake.
3. Reporter dans ce document les nouveaux chiffres des sections marquées **Provisoire** (§ 3 et § 5, Q2 à Q4).

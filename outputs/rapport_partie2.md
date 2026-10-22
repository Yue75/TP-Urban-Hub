# UrbanHub – Partie 2 : mobilité vélo en libre-service (CityBikes)

Période observée : **21/10/2026 12:22** → **21/10/2026 12:35** (6 snapshots, 3228 stations, 10 villes). Réseau détaillé : `velib`.

> Indicateurs calculés à partir des variations du nombre de vélos entre snapshots consécutifs (≈ toutes les 2 min 30) : ce sont des estimations basses de l'activité réelle.

## Q1 – Stations au plus fort taux d'utilisation

Taux d'utilisation = mouvements estimés par jour / nombre de points d'attache. Top 5 à Paris :

- **Montmartre - Etienne Marcel** : 36.0 rotations/jour (576 mouvements/jour, 16 places)
- **Bruant - Vincent Auriol** : 32.3 rotations/jour (806 mouvements/jour, 25 places)
- **Departement - Pajol** : 30.3 rotations/jour (576 mouvements/jour, 19 places)
- **Rapp - Place du Général Gouraud** : 29.7 rotations/jour (922 mouvements/jour, 31 places)
- **Dora Maar - Nadia Guendouz** : 26.9 rotations/jour (806 mouvements/jour, 30 places)

Réseau le plus sollicité : **Lyon** (7.76 rotations/place/jour) ; le moins sollicité : **Marseille** (0.00).

## Q2 – Zones où l'offre est insuffisante

Maillage ≈ 1 km × 1 km. Une zone est en déficit si ses stations cumulent moins de 10 % de vélos plus de 25 % du temps, ou un remplissage moyen < 15 %. À Paris : **71 zones sur 349** en déficit.

- Zone (48.8733, 2.4254), 5.9 km du centre, 3 stations : sous-dotée 100 % du temps, 1 vélos en moyenne pour 115 départs/jour
- Zone (48.7945, 2.2944), 8.0 km du centre, 2 stations : sous-dotée 100 % du temps, 3 vélos en moyenne pour 230 départs/jour
- Zone (48.8659, 2.3861), 2.5 km du centre, 10 stations : sous-dotée 100 % du temps, 16 vélos en moyenne pour 922 départs/jour
- Zone (48.8303, 2.3336), 3.6 km du centre, 8 stations : sous-dotée 100 % du temps, 6 vélos en moyenne pour 230 départs/jour
- Zone (48.8390, 2.3207), 3.3 km du centre, 11 stations : sous-dotée 100 % du temps, 35 vélos en moyenne pour 1152 départs/jour

## Q3 – Pics d'utilisation journaliers

- **Paris** : pic à **12h** (6696 mouvements/h, semaine)
- **Lyon** : pic à **12h** (3072 mouvements/h, semaine)
- **Toulouse** : pic à **12h** (2510 mouvements/h, semaine)
- **Lille** : pic à **12h** (1080 mouvements/h, semaine)
- **Bordeaux** : pic à **12h** (389 mouvements/h, semaine)
- **Nantes** : pic à **12h** (278 mouvements/h, semaine)
- **Rennes** : pic à **12h** (259 mouvements/h, semaine)
- **Montpellier** : pic à **12h** (5 mouvements/h, semaine)
- **Marseille** : pic à **12h** (0 mouvements/h, semaine)
- **Strasbourg** : pic à **12h** (0 mouvements/h, semaine)

Série temporelle (Paris) : jusqu'à **0 %** de la flotte hors station au maximum observé.

## Q4 – Déséquilibres géographiques

À Paris, remplissage moyen **64 %** à moins de 2 km du centre contre **43 %** au-delà de 6 km (écart de 21 points).
Stations vides plus de la moitié du temps : **107** ; pleines plus de la moitié du temps : **40**.

## Q5 – Stations critiques

Critère : station vide (ou pleine) plus de 25 % du temps observé. À Paris : **143 stations à réapprovisionner**, **62 à délester**. Besoin estimé pour revenir à 50 % de remplissage : +2086 vélos à déposer, -982 à retirer.

- **Batignolles - Rome** – Vide chronique : réapprovisionner (vide 67 %, pleine 0 % du temps ; action : +7 vélos)
- **Neuilly - Petit** – Pleine chronique : délester (vide 0 %, pleine 67 % du temps ; action : -6 vélos)
- **Paradis - Hauteville** – Pleine chronique : délester (vide 0 %, pleine 67 % du temps ; action : -14 vélos)
- **Nationale - Marcel Duchamp** – Vide chronique : réapprovisionner (vide 67 %, pleine 0 % du temps ; action : +11 vélos)
- **Mairie du 18ème** – Vide chronique : réapprovisionner (vide 67 %, pleine 0 % du temps ; action : +18 vélos)

Liste complète (tous réseaux) : `outputs/stations_critiques.csv`.


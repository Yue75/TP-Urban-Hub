# UrbanHub – Partie 2 : mobilité vélo en libre-service (CityBikes)

Période observée : **21/10/2026 12:22** → **22/10/2026 10:03** (97 snapshots, 3170 stations, 9 villes). Réseau détaillé : `velib`.

> Indicateurs calculés à partir des variations du nombre de vélos entre snapshots consécutifs (≈ toutes les 2 min 30) : ce sont des estimations basses de l'activité réelle.

> Réseaux exclus (0 vélo et aucun mouvement à chaque relevé, flux CityBikes inexploitable) : `le-velo`.

## Q1 – Stations au plus fort taux d'utilisation

Taux d'utilisation = mouvements estimés par jour / nombre de points d'attache. Top 5 à Paris :

- **Chabrol - d'Hauteville** : 18.8 rotations/jour (207 mouvements/jour, 11 places)
- **Place de l'Hôtel de Ville** : 15.6 rotations/jour (219 mouvements/jour, 14 places)
- **Montgallet - Reuilly** : 14.6 rotations/jour (219 mouvements/jour, 15 places)
- **Place de la République - Temple** : 14.4 rotations/jour (260 mouvements/jour, 18 places)
- **Jemmapes - Ecluses Saint-Martin** : 14.2 rotations/jour (213 mouvements/jour, 15 places)

Réseau le plus sollicité : **Toulouse** (9.10 rotations/place/jour) ; le moins sollicité : **Strasbourg** (0.44).

## Q2 – Zones où l'offre est insuffisante

Maillage ≈ 1 km × 1 km. Une zone est en déficit si ses stations cumulent moins de 10 % de vélos plus de 25 % du temps, ou un remplissage moyen < 15 %. À Paris : **74 zones sur 349** en déficit.

- Zone (48.8659, 2.3987), 3.9 km du centre, 8 stations : sous-dotée 100 % du temps, 10 vélos en moyenne pour 408 départs/jour
- Zone (48.8738, 2.3848), 3.4 km du centre, 13 stations : sous-dotée 100 % du temps, 17 vélos en moyenne pour 573 départs/jour
- Zone (48.8659, 2.3861), 2.5 km du centre, 10 stations : sous-dotée 100 % du temps, 23 vélos en moyenne pour 703 départs/jour
- Zone (48.8922, 2.3461), 4.3 km du centre, 14 stations : sous-dotée 100 % du temps, 30 vélos en moyenne pour 809 départs/jour
- Zone (48.8738, 2.3988), 3.7 km du centre, 11 stations : sous-dotée 100 % du temps, 12 vélos en moyenne pour 325 départs/jour

## Q3 – Pics d'utilisation journaliers

- **Paris** : pic à **17h** (10039 mouvements/h, semaine)
- **Lyon** : pic à **17h** (4680 mouvements/h, semaine)
- **Toulouse** : pic à **17h** (4190 mouvements/h, semaine)
- **Lille** : pic à **17h** (1281 mouvements/h, semaine)
- **Bordeaux** : pic à **17h** (1125 mouvements/h, semaine)
- **Nantes** : pic à **17h** (423 mouvements/h, semaine)
- **Rennes** : pic à **13h** (235 mouvements/h, semaine)
- **Montpellier** : pic à **10h** (24 mouvements/h, semaine)
- **Strasbourg** : pic à **16h** (16 mouvements/h, semaine)

Série temporelle (Paris) : jusqu'à **8 %** de la flotte hors station au maximum observé.

## Q4 – Déséquilibres géographiques

À Paris, remplissage moyen **68 %** à moins de 2 km du centre contre **42 %** au-delà de 6 km (écart de 25 points).
Stations vides plus de la moitié du temps : **43** ; pleines plus de la moitié du temps : **19**.

## Q5 – Stations critiques

Critère : station vide (ou pleine) plus de 25 % du temps observé. À Paris : **121 stations à réapprovisionner**, **87 à délester**. Besoin estimé pour revenir à 50 % de remplissage : +1443 vélos à déposer, -863 à retirer.

- **Coquillière - Louvre** – Pleine chronique : délester (vide 0 %, pleine 71 % du temps ; action : -2 vélos)
- **Estrapade - Ulm** – Pleine chronique : délester (vide 0 %, pleine 65 % du temps ; action : -2 vélos)
- **Place Saint-André des Arts** – Pleine chronique : délester (vide 0 %, pleine 59 % du temps ; action : -6 vélos)
- **Jean-Jacques Rousseau - Deux Ecus** – Pleine chronique : délester (vide 0 %, pleine 65 % du temps ; action : -1 vélos)
- **Gare du Nord - La Chapelle** – Vide chronique : réapprovisionner (vide 70 %, pleine 0 % du temps ; action : +8 vélos)

Liste complète (tous réseaux) : `outputs/stations_critiques.csv`.


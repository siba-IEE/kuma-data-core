# ADR-0010 : lignes servies et zone couverte

Date : 2026-11-11. Statut : accepté. Complète ADR-0009 et amende ADR-0004.

## Contexte

Deux questions restaient sans réponse unique dans le moteur.

**Quelles lignes sert-on ?** Les valeurs sont versionnées (`valide_au` nul
pour la version en vigueur) et portent un statut éditorial. Chaque lecteur
écrivait sa propre condition : les lectures journalières et mensuelles de
l'API servaient toute version en vigueur, dépréciée comprise ; l'atlas lisait
`grandeurs_metier` sans filtre de statut ni de version de formule ; la capsule
ne servait, en horaire, que le statut `valide_auto`, et aurait écarté une
ligne validée par un éditeur. La base ne contient aujourd'hui ni ligne
dépréciée ni version fermée : ces écarts ne se voyaient dans aucune réponse.
Ils se seraient vus à la première dépréciation.

**Jusqu'où transporte-t-on une climatologie ?** La résolution d'un point
(ADR-0004) rendait le point d'ingestion de sa cellule de grille et, à défaut,
le plus proche, sans limite : le point (0, 0), en plein océan, était résolu vers
un point d'ingestion situé à 1 283 km. La règle était écrite deux fois, dans
la route de résolution et dans la capsule.

## Décision

1. **Deux règles de sélection, définies une fois** dans
   `editorial/selection.py`. Chaque lecteur nomme celle qu'il applique.

   | Règle | Condition | Tables |
   |---|---|---|
   | en vigueur | `valide_au IS NULL` et statut autre que `deprecie` | mesures journalières et mensuelles ; valeurs de grandeurs, par la vue `v_grandeurs_metier_courantes`, qui ajoute « version de formule actuelle » |
   | en vigueur et validée | `valide_au IS NULL` et statut parmi `STATUTS_VALIDES` | mesures horaires |

   La différence tient au contrôle qualité automatique. Les mesures horaires
   y passent : `brut` y signifie « n'a pas passé le contrôle », et la ligne
   n'est pas servie. Les mesures journalières et mensuelles n'ont pas de
   contrôle automatique : `brut` est leur état normal, et les écarter
   viderait l'API.

   Deux tests d'architecture tiennent la règle : `valide_au IS NULL` ne
   s'écrit nulle part ailleurs, hors exceptions motivées ; et toute fonction
   servie qui lit une table versionnée cite l'une des deux règles ou la vue.
   La route horaire sert le statut de chaque ligne, et non plus `valide_auto`
   pour toutes.

2. **Un point est résolu dans sa cellule, sinon dans une cellule voisine,
   sinon il ne l'est pas.** S'il existe des points d'ingestion dans la cellule
   du point, le plus proche d'entre eux est retenu. Sinon, le plus proche
   parmi ceux des huit cellules voisines, avec `meme_cellule = false`. Sinon
   la route répond 404 et nomme le point d'ingestion le plus proche et sa
   distance.

   La limite est en cellules, pas en kilomètres : la valeur servie est celle
   d'une cellule, et l'erreur vient du nombre de cellules franchies, pas de la
   position du point d'ingestion dans la sienne. Mesure sur les 22 cellules
   occupées du référentiel (GHI mensuel 1991-2020, moyenne annuelle) :

   | Écart de cellules | Paires | Écart médian | 9ᵉ décile | Maximum |
   |---|---|---|---|---|
   | 1 (voisines) | 54 | 2,7 % | 5,6 % | 9,6 % |
   | 2 | 60 | 5,6 % | 10,6 % | 11,3 % |
   | 3 | 53 | 7,5 % | 15,5 % | 16,5 % |

   Repère : au même point, l'écart de GHI annuel que le moteur enregistre
   entre NASA POWER et PVGIS-SARAH3 est de 6,5 % en médiane et de 9,7 % au
   9ᵉ décile (102 années-localités, 2021-2023). Transporter une climatologie
   à la cellule voisine coûte donc moins que de changer de source ; à deux
   cellules, cela coûte autant.

3. **Une seule implémentation de la résolution**, fonction pure de
   `services/resolution.py`, appelée par la route `/v1/localites/resolution`
   et par la capsule. Les candidates sont lues par une seule requête de
   `lecture`.

4. **`services` peut importer `lecture`.** Un cas d'usage lit par la couche
   de lecture au lieu de porter sa propre requête. La table d'ADR-0009 gagne
   cette flèche ; `lecture` n'importe toujours que `editorial`.

## Conséquences

- Aucune réponse ne change sur le territoire guinéen : sur une grille de
  8 052 points, tous sont résolus (85,6 % dans leur cellule, 14,4 % dans une
  cellule voisine, à 118 km au plus) et aucun ne change de point d'ingestion.
- Hors du pays, un point qui reste résolu l'est vers le point d'ingestion le
  plus proche des cellules voisines, qui n'est pas toujours le plus proche de
  tous : 75 points sur une grille de 16 600 couvrant les six pays voisins
  changent ainsi de point d'ingestion.
- La limite n'est pas une frontière : un point d'un pays voisin qui partage
  une cellule, ou une cellule voisine, avec un point d'ingestion est résolu.
  C'est exact pour la grille, et la base ne porte pas de contour de pays.
- La zone couverte d'un pays est celle de ses points d'ingestion. Un pays
  ouvert avec peu de points d'ingestion ne sera servi que près d'eux : il
  faut au moins un point d'ingestion par cellule, ou par cellule voisine, du
  territoire.
- Une valeur dépréciée cesse d'être servie partout à la fois. Changer une
  règle de sélection se fait à un endroit.

## Hors périmètre

- **Les calculs de grandeurs stockées** (`services/grandeurs/`) appliquent
  déjà la règle « en vigueur », écrite sur place. Ils sont rejoués par des
  migrations antérieures à la révision 122 et ne changent pas.
- **Le contrôle qualité horaire** lit toutes les lignes en vigueur, quel que
  soit leur statut : c'est lui qui décide du statut.
- **Les candidates de la résolution** sont les localités qui portent une
  série mensuelle couvrant exactement 1991-2020. Une série prolongée au-delà
  de 2020 ne serait plus candidate.

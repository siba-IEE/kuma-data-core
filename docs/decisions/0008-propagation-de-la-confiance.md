# ADR-0008 : propagation de la confiance aux grandeurs calculées

Date : 2026-10-28. Statut : accepté.

## Contexte

La définition de la confiance A admet une donnée « calculée par une méthode
reconnue à partir de mesures elles-mêmes A ». Les règles R1 à R4 ne regardent
pourtant que la méthode de collecte de la série et la fiabilité de sa source.
Une grandeur calculée (méthode `calcul_derive`, source `kuma_calculs` de
fiabilité haute) tombait en R4 et recevait B quelles que soient ses entrées,
et les calculs à la volée de `/v1/grandeurs` posaient B en dur. Une grandeur
tirée d'une valeur C, ou d'une valeur qu'un override éditorial a descendue en
C, sortait donc en B, plus sûre que ce dont elle est faite ; une somme exacte
de mesures au sol A (Kankan, ESMAP/WAPP) aurait reçu B.

## Décision

1. **Règle P**, évaluée après R3 et avant R4 : une valeur calculée prend le
   niveau effectif (override sinon dérivé) le plus bas de ses entrées, sans
   dépasser le **plafond** de sa méthode.
2. **Le plafond est B par défaut.** Il monte à A seulement pour un calcul
   exact, sans modèle ni hypothèse de l'utilisateur : agrégation (HEP),
   ratio (fraction diffuse), formule fermée (humidex), statistique
   (variabilité journalière, P50/P90 de `ghi_exceedance`). Il reste B pour
   les grandeurs paramétrables (POA, bifacial, productibles, énergie ECS,
   degrés-jours), qui reposent sur un modèle et sur des paramètres déclarés
   que le producteur ne vérifie pas (`grandeurs-F2-phase-1.md`, L-TR-2), pour
   le productible spécifique théorique (PR conventionnel), pour les proxys
   (salissure HSU, PR réaliste) et pour l'indicateur qualité. Le B uniforme
   des grandeurs paramétrables devient ainsi un plafond : il descend en C
   avec leurs entrées. La note de calage dit de même qu'une station au sol
   fait passer en A les mesures d'irradiance et de météo, pas les grandeurs
   tirées d'un modèle de module.
3. **Comme R3 pour une mesure, A exige une source de calcul de fiabilité
   haute** : celle de la série d'une grandeur stockée, le moteur lui-même
   pour un calcul à la volée. Ailleurs, le plafond est ramené à B.
4. **Chaque valeur ne voit que les entrées de sa période** : un jour, un
   mois, ou une plage d'années éventuellement restreinte à un mois calendaire
   (climatologies). `NiveauxEntrees` range les niveaux par jour et par mois.
   La salissure HSU, modèle cumulatif, prend le niveau des entrées de tous les
   jours retenus, et le PR réaliste aussi quand il en tient compte ; sans
   salissure, le PR réaliste se calcule jour par jour.
5. **Application** : les grandeurs stockées calculées par le moteur (HEP,
   humidex, fraction diffuse, variabilité journalière, productible spécifique
   théorique, indicateur qualité) et les calculs à la volée de
   `/v1/grandeurs` (grandeurs paramétrables, `ghi_exceedance`,
   `taux_salissure_proxy`, `pr_realiste`). Le calcul pur pose un niveau
   provisoire, que la route remplace.

## Hors périmètre

Les indicateurs entre sources (`ecart_relatif_referentiel`,
`ecart_relatif_dni_cams`, `rang_referentiel_*`, `degenerescence_pixel`) gardent
le B que leurs migrations écrivent : ils ne sont pas recalculés, et leurs
entrées actuelles, satellitaires ou de réanalyse, sont toutes B.
`incertitude_inter_source` continue d'exiger B et répond 500 plutôt que
d'afficher un autre niveau. Un recalcul futur de ces indicateurs devra passer
par la règle P, avec le plafond B : leurs services écrivent encore B en dur.

## Conséquences

- Les séries satellitaires et de réanalyse donnent toujours B : rien ne change
  pour elles, ni dans la base, ni dans les réponses de l'API. Le rejeu des
  migrations produit les mêmes niveaux.
- Une entrée C fait descendre en C les seules valeurs calculées de sa
  période. Une climatologie de trente ans passe en C pour un seul jour C, ce
  que les éditeurs doivent savoir avant de poser un override.
- Un niveau stocké se fixe au calcul : un override posé ensuite sur une
  entrée appelle le recalcul de la grandeur.
- `calculer_niveau_confiance_derive` prend `niveaux_entrees` et `plafond`,
  facultatifs : sans eux, R1 à R4 s'appliquent comme avant.
- Une instance qui calcule ses grandeurs en SQL applique la même règle : les
  niveaux étant ordonnés comme leurs lettres, le plus bas des entrées est
  `max(coalesce(niveau_confiance_override, niveau_confiance_derive))`, à
  borner par le plafond de la grandeur.

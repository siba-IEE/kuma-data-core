# ADR-0007 : Assistant Kuma, couverture régionale des 13 pays et IA outillée

Date : 2026-10-18. Statut : proposé.

## Contexte

L'approche pays par pays est lente. Chaque pays demande son dépôt
(rds-guinee, kuma-data-core-bfa, kuma-data-core-civ, un RNDE) et une
adoption institutionnelle à obtenir. Or les institutions ont déjà leurs
outils : elles n'adoptent pas un référentiel de plus. Le modèle « aller
vers les gens » ne passe pas à l'échelle de l'Afrique de l'Ouest.

L'écosystème a pourtant déjà presque toutes les briques à l'échelle
régionale :

- **le Core** : schéma sans pays câblé ([généricité
  pays](../contribution/genericite-pays.md)), résolution d'un point vers sa
  cellule de 1° (ADR-0004), capsule de ressource au point
  (`GET /v1/etudes/capsule`), fiches d'études à contrat fermé (ADR-0006) ;
- **kuma-calage** : ses ancres sont les 31 stations sol de la campagne
  ESMAP / WAPP, réparties dans 13 pays : Bénin, Burkina Faso, Côte d'Ivoire,
  Gambie, Ghana, Guinée, Guinée-Bissau, Libéria, Mali, Niger, Nigéria,
  Sierra Leone, Togo. Il rend, par point, un verdict de couverture et un
  résidu de calage chiffré ;
- **les moteurs de dimensionnement** (`@kuma/moteur-pv`,
  `@kuma/moteur-minireseau`, dépôt kuma-bridges) : TypeScript purs, sans
  dépendance, validés contre pvlib.

Il manque deux choses. La donnée du Core s'arrête à la Guinée. Et la porte
d'entrée demande un logiciel (SolClim-3), une clé d'API ou une expertise :
rien qu'un porteur de projet, un élu local ou un installateur ne puisse
utiliser en deux minutes.

Les sources amont (NASA POWER, PVGIS / SARAH-3, CAMS, ERA5-Land) sont
ouvertes et couvrent toute la région. La couverture brute des 13 pays ne
dépend donc d'aucun partenaire national.

## Décision

1. **La région remplace le pays comme unité de couverture.** Le Core ingère
   une grille de 1° couvrant les 13 pays. 1°, c'est la résolution native du
   rayonnement NASA POWER, la convention de cellule de l'ADR-0004 et la maille
   de kuma-calage : un point tombe dans une seule cellule pour les trois, sans
   hypothèse de transport. Chaque maille terrestre entre comme une localité
   de type `site` rattachée à son pays, code `<pays>_m<lat>n_<lon>[ew]`
   (coin bas-gauche, par exemple `gin_m10n_010w`). Si la matrice du trigger de
   hiérarchie (migration 084) n'admet pas `site` sous `pays`, le lot
   d'ingestion l'étend. Une `region_supranationale` regroupe les 13 pays pour
   les statistiques régionales. Une maille à cheval sur une frontière va au
   pays qui contient son centre (centre en mer : au pays le plus proche).

2. **La grille entre par pipeline, pas par migration.** Plusieurs centaines
   de mailles en seeds committés feraient exploser le dépôt. Le chantier du
   jalon 4, « découpler l'ingestion de masse des migrations », devient le
   prérequis du lot R1 : pipeline reproductible, script versionné, édition
   publiée (ADR-0003). Ordre des volumes : d'abord la climatologie mensuelle
   1991-2020 (de quoi répondre aux questions et dimensionner du PV autonome),
   ensuite une séquence horaire type par maille (8 760 pas, pour le
   mini-réseau), jamais les 25 ans d'horaire par maille dans l'édition.

3. **L'Assistant est un service distinct, consommateur de l'API.** Il ne vit
   pas dans le Core : un appel à un modèle de langage est une dépendance
   sortante, que l'ADR-0003 (D6) exclut de l'édition publique. Comme Solar
   Bridge et kuma-calage, il consomme le Core par son API. Il embarque les
   moteurs comme paquets ; TypeScript purs, ils tournent tels quels côté
   serveur, sans réécriture.

4. **Le modèle de langage ne produit aucun chiffre.** Chaque valeur d'une
   réponse vient d'un outil : le Core, kuma-calage ou un moteur. Le modèle
   comprend la demande (lieu, consommation, contraintes), choisit les outils,
   remplit leurs entrées, puis explique le résultat et la méthode. Pour chaque
   valeur, la réponse porte sa source, son niveau de confiance (A/B/C), son
   incertitude (résidu de calage quand il existe), la version du moteur et
   l'édition du Core. Une garde vérifie avant envoi que tout nombre du texte
   figure dans une sortie d'outil : un chiffre orphelin bloque la réponse.
   Hors domaine (lieu non couvert, grandeur absente), l'Assistant refuse
   honnêtement, comme Solar Bridge.

5. **L'Assistant reformule avant de calculer.** Une consommation mal lue (W
   pour Wh, par jour pour par mois) fausse tout le dimensionnement. Avant
   chaque calcul, l'Assistant affiche les entrées qu'il a comprises et le
   rapport les reprend.

6. **Outils, contrat v1** :

   | Outil | Rend | Appuyé sur |
   |---|---|---|
   | `resoudre_lieu` | maille, pays, coordonnées, depuis un nom ou un point | `/v1/localites`, `/v1/localites/resolution` ; un nom inconnu passe par un géocodeur ouvert et une confirmation |
   | `ressource_au_point` | climatologie mensuelle (GHI, HSE, température), source, confiance | `/v1/series` |
   | `couverture_calage` | couvert ou non, résidu GHI et DNI (médiane, p80) | kuma-calage `/couverture` |
   | `statistiques_pays` | min, médiane, max d'une grandeur sur les mailles d'un pays | endpoint d'agrégats à créer (jalon 4, « statistiques agrégées par série ») |
   | `dimensionner_pv_autonome` | champ, batterie, onduleur, productible, coûts | `@kuma/moteur-pv` |
   | `dimensionner_minireseau` | champ, stockage, LPSP, groupe, LCOE | `@kuma/moteur-minireseau`, une fois la séquence horaire type servie |

7. **« S'améliorer sur les données » veut dire boucle de données, pas
   réentraînement.** Le modèle n'est pas affiné : le savoir vit dans le Core,
   versionné et audité, et chaque correction profite à toutes les réponses
   suivantes. L'amélioration vient de quatre sources :
   - les fiches des dimensionnements faits par l'Assistant, avec le
     consentement de l'utilisateur, au format fermé de l'ADR-0006
     (`pv-autonome@1`) : profils de consommation et prix observés par région ;
   - les nouvelles stations sol, qui étendent le calage ;
   - un jeu d'évaluation versionné (questions de référence, réponses chiffrées
     attendues), rejoué à chaque changement de consigne, d'outil ou d'édition ;
   - le journal des questions restées sans réponse (lieu introuvable, hors
     domaine), qui priorise la feuille de route.

8. **Séquence.**

   | Lot | Objet | Dépend de |
   |---|---|---|
   | R1 | Grille 1° des 13 pays, climatologie mensuelle NASA POWER 1991-2020, édition publiée | ingestion découplée (décision 2) |
   | R2 | kuma-calage étend sa grille aux 13 pays (les ancres y sont déjà) | - |
   | A1 | Assistant, « une question sur un lieu » : `resoudre_lieu`, `ressource_au_point`, `couverture_calage` ; jeu d'évaluation initial | R1 |
   | A2 | « Ma consommation, mon système » : PV autonome, rapport exportable avec méthode et hypothèses | A1 |
   | R3 + A3 | Séquence horaire type par maille, mini-réseau | R1 |
   | A4 | Canaux : page web Kuma Science, puis messagerie | A1 |

## Conséquences

- La couverture ne passe plus par un dépôt ni par une adoption par pays. Les
  RDS nationaux et le pont du jalon 2 restent utiles, comme renforts (données
  nationales, stations), plus comme voie de couverture.
- La lecture de la confiance ne change pas : satellite brut en B, calage
  signalé avec son résidu, A réservé au sol. L'Assistant hérite de la doctrine
  au lieu d'en inventer une.
- Chaque conversation coûte des appels au modèle : clé et quota (ADR-0003, D3)
  s'appliquent à l'Assistant comme à l'API.
- Le brut reste ouvert (AGPL pour le moteur, CC-BY pour les données). Le
  calage reste la couche propriétaire de kuma-calage : l'Assistant en sert le
  verdict et le résidu, jamais la loi.

## Hors périmètre

Affinage d'un modèle sur les données, pays hors des 13, domaines autres que
le solaire, choix du fournisseur de modèle et de l'hébergement de
l'Assistant (tranchés à son propre dépôt).

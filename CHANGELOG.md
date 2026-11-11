# Changelog

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et
le projet suit le versionnement sémantique.

## Non publié

### Sécurité

- Plafond de débit par adresse avant l'authentification
  (`429 DEBIT_DEPASSE`, `DEBIT_IP_PAR_MINUTE`), corps de requête limité à
  1 Mo par le reverse proxy. En IPv6, débit et limite d'émission de clés se
  comptent par réseau /64.
- Une clé `Bearer` non ASCII reçoit `401` et non plus `500`.
- Les erreurs `422` ne renvoient plus la valeur fautive, seulement son
  emplacement, son type et le message.
- Les fiches de contribution refusent `NaN` et les infinis.
- En production, `API_CLE_ADMIN` doit faire au moins 32 caractères et ne
  pas être une valeur d'exemple : le démarrage échoue sinon.
- Le mot de passe PostgreSQL n'apparaît plus dans la représentation de la
  configuration ; ses caractères réservés sont encodés dans la chaîne de
  connexion.
- Dépendances mises à jour (starlette, fastapi, anyio, certifi, idna,
  urllib3, pydantic-settings) ; audit des vulnérabilités à chaque
  intégration. Actions GitHub et `uv` épinglés.

### Corrigé

- Une valeur dépréciée (statut `deprecie`) n'est plus servie par les lectures
  journalières et mensuelles (`/v1/series/{code_serie}`, grandeurs calculées
  qui lisent ces mesures, recherche des localités de même série mensuelle) ni
  par l'atlas d'incertitude inter-source, qui écarte aussi une valeur calculée
  par une version de formule remplacée. La base ne porte aujourd'hui aucune
  valeur dépréciée : aucune réponse ne change.
- La capsule sert l'horaire validé par un éditeur (`valide_humain`, `publie`),
  et plus seulement celui que le contrôle qualité automatique a validé.
- `/v1/horaire` ne tient plus pour stockée une série dont aucune ligne n'est
  validée : la demande suit le repli ordinaire (relais à la source amont,
  refus sur une édition figée) au lieu de recevoir une réponse vide.
- `/v1/horaire` rend chaque point stocké avec le statut de sa ligne
  (`statut_editorial` : `valide_auto`, `valide_humain` ou `publie`), et non
  plus `valide_auto` pour tous. Les lignes servies aujourd'hui sont toutes
  `valide_auto` : aucune réponse ne change.
- `/v1/grandeurs/ghi_exceedance` : la mise en garde de cellule partagée du
  champ `limite` ne connaissait que Kindia et Mamou. Les localités de même
  cellule sont reconnues à l'identité de leur série GHI mensuelle : la mise
  en garde vaut pour les 20 localités concernées et nomme toutes leurs
  jumelles (Dalaba s'ajoute à Kindia et Mamou).

- `/v1/series/{code_serie}` répondait `500` pour une série mensuelle remontant
  avant 1991 : le schéma de réponse exigeait `annee >= 1991` alors que la base
  admet les mois depuis 1981.

- Une requête incohérente sur `/v1/grandeurs` ou l'horaire (période
  inversée, paramètre requis par un autre) reçoit `422` et non plus `500`.
- Le choix d'une série parmi plusieurs candidates est ordonné : deux
  requêtes identiques lisent la même série.
- Le fuseau des sessions PostgreSQL est fixé à UTC : les regroupements par
  jour ne dépendent plus du réglage du serveur.

### Modifié

- Les lecteurs de mesures et de valeurs de grandeur partagent deux règles de
  sélection, définies une seule fois (`editorial/selection.py`) : version en
  vigueur et non dépréciée pour le journalier, le mensuel et les valeurs de
  grandeur ; version en vigueur et validée pour l'horaire, seul soumis au
  contrôle qualité automatique. Les lectures de l'API, la capsule et les
  scripts d'export les appliquent ; un test refuse qu'une règle soit récrite
  ailleurs, hors exceptions motivées.
- Le pays est une donnée lue dans la base, et non plus une constante du
  moteur ; un test de bout en bout sur un pays fictif le vérifie
  (`tests/integration/api/test_pays_fictif.py`). Pour la Guinée, les points
  ci-dessous ne changent aucune réponse.
  - `/v1/horaire/{localite}/{grandeur}` : le préfixe qui complète un code
    court de localité est cherché parmi les codes des pays du référentiel, et
    non plus fixé à `gin_`. Un code court porté par des localités de
    plusieurs pays reçoit `404 RESSOURCE_LOCALITE_INCONNUE`, avec la liste des
    codes complets.
  - Les grandeurs calculées par intégration horaire comptent en heure
    locale : fenêtre demandée, regroupement par jour et propagation de la
    confiance suivent le fuseau de la localité (`fuseau_horaire`, UTC à
    défaut). La capsule exprime les mois et les heures de sa séquence horaire
    dans ce fuseau. `/v1/horaire` reste en UTC.
  - Les descriptions servies ne citent plus d'exemple pris en Guinée : elles
    renvoient à la route qui liste les valeurs (`/v1/localites`,
    `/v1/series`). Un test refuse ces exemples dans le document OpenAPI.
  - Nouvelle dépendance `tzdata` : la base des fuseaux est fournie avec le
    moteur, quelle que soit l'image qui l'exécute.
- Couches du moteur et sens des dépendances (ADR-0009), sans changement des
  réponses de l'API : les calculs n'importent plus les schémas de l'API, le
  SQL de lecture quitte les routes pour le paquet `lecture`, `/v1/grandeurs`
  est découpé en un module par famille de routes, et chaque règle de
  sélection des lignes a une seule définition nommée. Un test vérifie ces
  règles, ainsi que l'absence d'import du moteur dans les nouvelles
  migrations.
- Textes servis par l'API réécrits pour un lecteur extérieur : descriptions
  de routes et de champs, messages d'erreur et mises en garde du champ
  `limite` ne portent plus de code interne et disent le fait à la place
  (cellule partagée par deux localités, biais de moyennage du calcul
  journalier, absence de calage sur des mesures au sol). Un test balaie le
  document OpenAPI et ces textes.
- Le message 404 de `/v1/grandeurs/ghi_exceedance` ne parle plus de « 6
  villes pilotes » : la série existe pour toutes les localités d'ingestion.
- Descriptions corrigées d'après le code : `/v1/horaire` sert d'abord la
  série stockée avant de relayer la source amont ; `ghi_exceedance` répond
  `RESSOURCE_LOCALITE_INCONNUE`.
- Commentaires du schéma (tables, colonnes, vues, fonction de validation de
  la hiérarchie des localités) réécrits d'après le schéma et les données :
  ils ne renvoient plus à l'histoire du projet, citent les documents du
  dépôt par leur URL et corrigent des faits périmés (identité d'une série,
  valeurs de `periode_type`, exemples de codes, décompte des unités).
- Libellés de 62 séries d'écart 2021-2023 : la mention entre parenthèses qui
  suivait la période est retirée, le libellé suit le modèle des autres
  séries de la même grandeur.
- `series_metadonnees.methode_collecte_doc` et `url_documentation` : pour
  170 séries calculées, le chemin de la fiche méthodologique relatif au
  dépôt devient son URL publique. Les 28 séries de
  `rang_referentiel_temporel` qui citaient une fiche inexistante ne citent
  plus rien, comme les autres séries de cette grandeur.
- Textes enregistrés en base et publiés avec les données, réécrits en clair
  et avec leurs accents, sans renvoi à l'organisation du projet : fiches des
  sources (`sources.notes`, quelques valeurs de `sources.metadonnees`),
  notes des localités, descriptions de 15 grandeurs, provenance des
  référentiels de calage (la note de méthode et le script y sont cités par
  leur URL). Seul le texte change ; les corrections sont journalisées.
- Note publique des séries `rang_referentiel_spatial` : elle nomme les six
  villes classées, donne le sens du rang et précise que les autres localités
  n'entrent pas dans ce classement.
- Commentaire des lignes `degenerescence_pixel`, servi par
  `/v1/grandeurs/incertitude_inter_source` (champ `degenerescence.note`) :
  réécrit en clair (cellule partagée, source interpolée ou point seul dans
  sa cellule). Valeurs, versions et dates de validité sont inchangées.
- Un test balaie toutes les colonnes de texte des tables publiées et les
  commentaires du schéma, et refuse le vocabulaire interne.

- Les origines CORS se règlent par déploiement (`CORS_ORIGINES`, liste
  JSON) ; la valeur par défaut est inchangée, `*` est refusé en production.

### Ajouté

- Confiance : règle de propagation P (ADR-0008). Une valeur calculée prend le
  niveau effectif le plus bas des valeurs dont elle est tirée, sur sa seule
  période, sans dépasser le plafond de sa méthode : B par défaut, A pour un
  calcul exact sans modèle ni hypothèse (HEP, fraction diffuse, humidex,
  variabilité journalière, P50/P90) dont la source de calcul est de
  fiabilité haute. `calculer_niveau_confiance_derive` prend
  `niveaux_entrees` et `plafond`, `NiveauxEntrees` range les niveaux par
  jour et par mois, chaque module de calcul déclare `PLAFOND_CONFIANCE`.
  Appliquée aux grandeurs stockées (HEP, humidex, fraction diffuse,
  variabilité journalière, productible spécifique théorique, indicateur
  qualité) et aux calculs à la volée de `/v1/grandeurs`.
- Contributions : format `pv-champ@1` (ADR-0006), conception de champ PV.
  Module et onduleur par leurs caractéristiques (sans marque ni référence),
  pertes, câblage, et résultats : strings, vérifications électriques,
  productible, sections de câbles, protections.
- Contributions : format `minireseau@1` (ADR-0006). Postes de charge avec
  leur profil sur 24 heures, groupe et prix du carburant, configuration
  retenue et LCOE ; le module choisit le format, une fiche d'un module sous
  l'autre est refusée.
- Contributions d'études SolClim-3 (ADR-0006) : table `contributions_etudes`
  dans la base de service ; `POST /v1/contributions/{etude_uid}` dépose ou
  remplace la fiche d'une étude (clé porteuse d'une licence), `POST
  /v1/contributions/{etude_uid}/retrait` la retire. Contrat fermé : point
  arrondi à 0,1°, nom d'appareil coupé à 40 caractères, tout champ non prévu
  refusé. Outil `python -m kuma_data_core.services.contributions` (bilan,
  exporter sans les clés).
- Licences SolClim-3 (ADR-0005) : table `licences_solclim` dans la base de
  service, à côté de `cles_api` ; une clé d'API publique seule n'ouvre plus
  le logiciel.
- `POST /v1/licence/bail` : bail Ed25519 de 30 jours, plafonné par le terme
  de la licence, vérifiable hors ligne avec la clé publique.
- Outil d'administration `python -m kuma_data_core.services.licences`
  (accorder, lister, prolonger, retirer) et script de génération de la
  paire de signature.

### Modifié

- `/v1/grandeurs` : le `niveau_confiance` des résultats suit la règle P. Les
  grandeurs paramétrables, `taux_salissure_proxy` et `pr_realiste` restent
  au plus B et passent en C pour les périodes dont une entrée est C ;
  `ghi_exceedance` prend le niveau des mesures mensuelles lues, avec le
  plafond A d'un calcul exact. Les séries satellitaires et de réanalyse
  donnent toujours B. La constante
  `ghi_exceedance.NIVEAU_CONFIANCE_DERIVE` est retirée.

## 1.0.0

Première version publique de Kuma Data Core.

- Schéma générique : localités, sources, unités, grandeurs, mesures, audit,
  versionnement temporel non destructif.
- Niveaux de confiance A/B/C dérivés de règles explicites, portés par
  chaque série.
- Audit applicatif par triggers PostgreSQL.
- API FastAPI (auth Bearer) : catalogue de séries, lecture, localités,
  grandeurs métier calculées, séries horaires validées par contrôle
  qualité.
- Domaine pilote : ressource solaire en Guinée, à partir de sources
  ouvertes (NASA POWER, PVGIS/SARAH-3, Copernicus CAMS et ERA5-Land,
  stations sol ESMAP/WAPP).

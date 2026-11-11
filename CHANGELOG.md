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

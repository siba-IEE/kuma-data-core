# Changelog

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et
le projet suit le versionnement sémantique.

## Non publié

### Ajouté

- Séries CAMS EAC4 journalières du 1er février 2004 au 31 décembre 2025 aux
  34 points (6 villes pilotes et 28 communes chef-lieu), 8 005 jours par
  série, confiance B : épaisseur optique des aérosols à 550 nm, totale
  (`aod_550`) et due aux poussières (`aod_poussiere_550`), 68 séries
  (migration 123) ; ozone de surface en ppb, moyenne journalière
  (`ozone_surface`) et diurne des pas de 09, 12 et 15 h UTC
  (`ozone_surface_diurne`), 68 séries (migration 124). 1 088 680 mesures au
  total, ingérées hors ligne depuis les compagnons
  `cams_eac4_aod_ozone_journalier_seed_data_*` ; source `cams_eac4`
  réutilisée. Valeur au point de grille le plus proche (0,75°, environ
  80 km). La note publique de l'ozone signale les pics de fin de saison
  sèche (février à mai, 2006 à 2019 ; environ 300 ppb en moyenne diurne,
  jusqu'à 340 ppb, contre une médiane de 27 ppb), artefacts probables du
  modèle liés aux feux de végétation, conservés tels que fournis.
- Référentiel : unité `partie_par_milliard` (ppb, fraction molaire) et
  quatre grandeurs brutes de la réanalyse CAMS EAC4 : `aod_550`,
  `aod_poussiere_550` (épaisseurs optiques à 550 nm, sans dimension),
  `ozone_surface` et `ozone_surface_diurne` (ozone au niveau modèle le plus
  bas, en ppb, moyenne journalière ou des pas de 09, 12 et 15 h UTC).
  Déclarations (migration 122) ; les séries, capturées hors ligne par
  `scripts/preparer_seed_cams_eac4_aod_ozone.py`, suivent en migrations
  123 et 124.
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

### Corrigé

- Commentaires des tables `unites` et `grandeurs_referentiel`, publiés dans
  l'édition : les décomptes figés devenus faux et le vocabulaire de chantier
  sont remplacés par une description sans décompte. La phrase qui
  rattachait le lieu de stockage à `methode_collecte` est retirée : il
  dépend de la source et de la granularité de la série (migration 125).
- Source `cams_eac4` : la notice ne décrivait que les PM2.5 et PM10 ; elle
  couvre désormais l'épaisseur optique des aérosols à 550 nm et l'ozone de
  surface, sans vocabulaire de chantier, la période étant portée par chaque
  série. Les métadonnées listent les variables, conversions et périodes
  par famille de variables (migration 125).

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

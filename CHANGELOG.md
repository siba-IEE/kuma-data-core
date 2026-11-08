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

- `rang_referentiel_spatial` classe désormais chaque mois toutes les
  localités couvertes : rang de 1 à 34 par moyenne mensuelle croissante du
  GHI NASA POWER journalier, 2021-2025, au lieu de 1 à 6 parmi Kaloum,
  Kankan, Kindia, Labé, Mamou et Nzérékoré. Le sens d'une valeur change (un
  rang 6 n'est plus le maximum) : nouvelle version de formule 2,
  `version_formule` vaut 2 dans `/v1/series`. Les 360 valeurs de la
  version 1 sont closes et restent en base pour l'historique ; 2 040 valeurs
  version 2, confiance B, dont 28 nouvelles séries
  `<localité>_rang_referentiel_spatial_kuma_calculs_2021_2025`. Huit groupes
  de localités (20 au total, par exemple Kindia, Mamou et Dalaba) lisent la
  même cellule de la grille NASA POWER et ont des valeurs identiques : leurs
  rangs sont consécutifs et leur ordre relatif arbitraire (ordre des codes de
  localité). La description de la grandeur le dit et la note publique de
  chacune des 20 séries concernées nomme ses jumelles ; les libellés des six
  séries existantes emploient le nom de la localité (Kaloum, Labé,
  Nzérékoré). Fonction
  `calculer_et_inserer_rang_spatial` (migration 133).
- `/v1/grandeurs` : le `niveau_confiance` des résultats suit la règle P. Les
  grandeurs paramétrables, `taux_salissure_proxy` et `pr_realiste` restent
  au plus B et passent en C pour les périodes dont une entrée est C ;
  `ghi_exceedance` prend le niveau des mesures mensuelles lues, avec le
  plafond A d'un calcul exact. Les séries satellitaires et de réanalyse
  donnent toujours B. La constante
  `ghi_exceedance.NIVEAU_CONFIANCE_DERIVE` est retirée.

### Corrigé

- `GET /v1/grandeurs/incertitude_inter_source` (collection) : le périmètre
  des points ne retient plus que les écarts de la fenêtre 2021-2023, comme la
  fiche par localité ; un écart postérieur à 2023 aurait listé un point sans
  fiche lisible et renvoyé une erreur 500.
- Authentification : une panne de la base de service pendant la recherche
  d'une clé self-service est journalisée (`meta_db_injoignable_cle_refusee`,
  avertissement avec la trace) ; la clé reste refusée (401).
- Document OpenAPI : les descriptions de la fiche et de la collection
  d'incertitude inter-source et du champ `note` de la dégénérescence de
  pixel n'emploient plus de vocabulaire de chantier (« Temps 1 », « Temps 2 »,
  « B-3 »).
- Tests : la comparaison DHI ≤ GHI des cinq villes rapproche GHI et DHI d'une
  même source et d'une même série (elle croisait les sources et comptait des
  doublons) ; les tests d'aller-retour Alembic qui redescendent sous la
  migration 046, non réversible, sont ignorés avec ce motif, et celui des
  grandeurs métier compare les décomptes avant et après.
- Constantes inutilisées retirées (`METHODE_COLLECTE_INDICATEUR`,
  `SOURCE_CODE_INDICATEUR`, `IRRADIANCE_STC_W_PAR_M2`, `UNITE_SORTIE`,
  `FAMILLES_AUTORISEES`, `STRATEGIES_CALCUL_AUTORISEES`,
  `TABLES_HORS_ORM_PUBLIEES`).
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
- Référentiel des grandeurs : `degenerescence_pixel`, `ecart_relatif_dni_cams`,
  `ecart_relatif_referentiel`, `rang_referentiel_spatial` et
  `rang_referentiel_temporel` étaient déclarées `calculee_volee` alors que
  leurs valeurs sont calculées par Kuma puis stockées dans `grandeurs_metier`
  et servies telles quelles ; elles passent en `stockee`. Leurs descriptions
  publiques sont réécrites d'après le calcul réel, sans vocabulaire de
  chantier ni couverture figée : `ecart_relatif_referentiel` est l'écart
  mensuel du GHI entre NASA POWER et PVGIS-SARAH-3, et non un écart à la
  moyenne des sites Kuma (migration 126). Référence de l'API (§4.2, §4.3,
  §5.6) et notes méthodologiques alignées.
- Textes publiés dans l'édition : vocabulaire de chantier interne retiré
  (renvois de PR, de specs, d'étapes, de vagues, de lots, de dettes et de
  caveats internes, codes d'étape, ADR, renvois vers des documents du dépôt)
  des descriptions de dix grandeurs (`albedo_surface`, `ghi`, `pm10`,
  `pm2_5`, `pr_realiste`, `precipitation`, `rang_referentiel`,
  `taux_salissure_proxy`, `vent_10m`, `vent_2m`) et des commentaires du
  catalogue (six tables, dix colonnes, deux vues, la fonction
  `valider_hierarchie_localites`) ; un identifiant de caveat est remplacé
  par son contenu. Erreurs de fond corrigées au passage : `vent_2m`
  n'alimente pas la correction thermique (modèle NOCT, sans vent) ;
  `albedo_surface` n'alimente que le POA bifacial ; `periode_type` admet
  aussi `statique` ; les tables mensuelle et horaire ne portent pas que les
  sources qu'elles nommaient ; le commentaire de `sources.fiabilite`
  renvoyait à un document inexistant. Les décomptes figés sont remplacés par
  le nom de la contrainte CHECK qui fait foi (migration 127).
- Données publiées dans l'édition : vocabulaire de chantier interne retiré
  des textes des tables publiées telles quelles. Note de dégénérescence de
  pixel (`grandeurs_metier.commentaire_editorial`, servie par l'API) : la
  mention « (D-29 generalise) » est retirée de 140 lignes, la règle restant
  dite en clair. Notes de 67 localités (densification préfectorale, renvois
  de spec, phases, étiquettes de suivi), notes de 14 sources et deux valeurs
  de `sources.metadonnees` (vagues, lots, dettes, phases, codes d'étape,
  renvoi de PR), provenance du calage GHI de Kankan (renvoi vers une note et
  un script du dépôt) : les codes sont retirés ou remplacés par leur contenu.
  Erreurs de fond corrigées au passage : `ecmwf_era5` ne porte aucune série
  Kuma (ERA5-Land est la source distincte `ecmwf_era5_land`) ;
  `ecmwf_era5_land` couvre 34 localités et non les 6 villes pilotes ;
  `esmap_wapp` alimente une série DNI en plus du GHI ; `cams_radiation`
  porte GHI, DNI et DHI ; la communauté NASA POWER utilisée (RE) est fixée.
  Correction en place, sans nouvelle version ni changement de valeur, de
  période, de statut ou de confiance (migration 128).
- Données publiées dans l'édition : vocabulaire des fiches de compilation
  retiré. Notes de 76 localités (renvois au cahier des charges remplacés par
  la règle qu'ils désignent, code de décision « (D7) », « verifiee par
  superviseur », « migration 011 », étiquettes « post-audit »), notes de 9
  sources (codes de décisions techniques et de garde-fous « DT-n » et
  « GF-n », statut « β2 » du vecteur hydro, passes de compilation) et trois
  valeurs de `sources.metadonnees` (« en passe 2 ») : les codes sont retirés
  ou remplacés par leur contenu. `series_metadonnees.methode_collecte_doc`
  et `url_documentation` (198 séries calculées) portaient un chemin du dépôt
  (`docs/methodologie/grandeurs/*.md`) : ils portent désormais le lien du
  document dans le dépôt public ; le chemin donné pour
  `rang_referentiel_temporel` ne désignait aucun fichier et vise la note des
  référentiels comparatifs qui documente sa méthode. Correction en place,
  sans nouvelle version (migration 129).
- Données publiées dans l'édition : les libellés des 62 séries d'écart
  inter-source 2021-2023 (`ecart_relatif_referentiel` aux 28 communes,
  `ecart_relatif_dni_cams` aux 34 points) ne portent plus le marqueur
  d'étape interne « (atlas Temps 1) » ; les libellés restent uniques.
  Correction en place, sans nouvelle version (migration 130).
- Données publiées dans l'édition : 314 libellés de séries calculées par Kuma
  désignaient leur localité par son code (`ecart_relatif_dni_cams mensuel
  gin_fria 2021-2023`) ; ils la nomment désormais par son nom, comme le reste
  de la base (`ecart_relatif_dni_cams mensuel Fria 2021-2023`). Sont concernés
  les écarts inter-source 2021-2023 (`ecart_relatif_dni_cams` aux 34 points,
  `ecart_relatif_referentiel` aux 28 communes) et les neuf séries « (calcul
  Kuma) » des 28 communes (fraction diffuse, HEP, productible spécifique
  théorique, humidex, variabilité journalière, rang référentiel temporel).
  Les libellés restent uniques. Correction en place, sans nouvelle version
  (migration 131).
- Données publiées dans l'édition : 141 libellés de séries écrivaient leur
  localité autrement que son nom au référentiel : « Conakry-Kaloum » pour
  Kaloum (commune de Conakry nommée, comme Dixinn, Matam, Matoto et Ratoma,
  par son seul nom), « Labe » pour Labé, « Nzerekore » pour Nzérékoré, 47
  séries par localité ; ils emploient désormais le nom exact. Les libellés
  restent uniques. Correction en place, sans nouvelle version
  (migration 132).
- Données publiées et API : toutes les localités sont couvertes ; les textes
  qui en présentaient une partie comme « pilotes » décrivent la couverture
  réelle. Les notes publiques des 36 séries horaires NASA POWER de Kaloum,
  Kankan, Kindia, Labé, Mamou et Nzérékoré disent que le contrôle qualité
  s'applique aux séries horaires de toutes les localités couvertes ; la
  description de `ghi_exceedance` et celle de son schéma de réponse dans le
  document OpenAPI indiquent que les 34 localités couvertes disposent de la
  série GHI mensuelle 1991-2020 qui la fonde ; celle de `rang_referentiel`
  (désactivée) ne parle plus de « villes pilotes » ; la note de la source
  `esmap_wapp` situe la station de Kankan à environ 2 km du point de la
  localité (2,14 km, et non « moins de 2 km »). Correction en place, sans
  nouvelle version (migration 132). Les textes de `rang_referentiel_spatial`
  sont repris avec sa nouvelle version (migration 133).
- API : codes internes (dettes « D-n », caveats « L-XXX-n », ADR, codes
  d'étape, convention de nommage « D-32 ») retirés du document OpenAPI
  (descriptions de routes, de schémas et de champs) et des avertissements
  `limite` de la salissure, du PR réaliste, de l'exceedance GHI et de
  l'incertitude inter-source, leur contenu restant dit en clair. Le message
  404 de `ghi_exceedance` annonçait une disponibilité limitée aux « 6 villes
  pilotes » : il nomme la condition réelle (une série GHI mensuelle NASA
  POWER 1991-2020, portée par 34 localités).
- Code : les textes historiques des migrations immuables 085, 090 et 101 sont
  isolés et figés par test ; `calculer_et_inserer_degenerescence_pixel`
  écrit le commentaire courant sans code interne,
  `calculer_et_inserer_degenerescence` reste la variante historique importée
  par la migration 090.

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

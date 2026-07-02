# Feuille de route

Kuma Data Core est le moteur ; les données nationales vivent dans des dépôts
RDS par pays ([rds-guinee](https://github.com/siba-IEE/rds-guinee), puis
d'autres). La contribution s'organise autour de trois profils :

- `pour:dev` : le moteur (API, schéma, ingestion, connecteurs).
- `pour:chercheur` : la méthode (contrôle qualité, incertitude, grille de
  confiance, calage terrain).
- `pour:institution` : la donnée et le terrain (RDS national, validation au sol).

Cette feuille de route décrit la direction. Seule la tranche actionnable à
court terme est ouverte en issues, classées par jalon. Le reste est listé ici
pour rester visible sans encombrer le suivi ; un item passe en issue quand il
devient réellement actionnable.

## Jalon 1 : portes ouvertes

Les portes d'entrée elles-mêmes : un guide de contribution de données (source,
grandeur, série, confiance, statut, seed), la documentation du modèle de
confiance A/B/C, et un guide pour un contributeur pays ou terrain.

## Jalon 2 : multi-pays

Le schéma n'a aucune notion de pays en dur : le pays est un axe de
classification. L'objectif est de le rendre explicite et de construire le
**pont** qui verse un RDS national dans le Core, sans qu'un contributeur ait à
écrire une migration.

- Rendre explicite la généricité pays (note d'architecture) et la prouver par
  un test de bout en bout sur un pays fictif.
- Pont RDS national vers Core : un loader qui réutilise la couche d'ingestion
  existante (fonctions `session`-based), hors migrations.
- Template de RDS national réutilisable, sur le modèle de rds-guinee.
- Exposer `family_metier` (famille éditoriale) dans le contrat de série ; axe
  qui prépare aussi l'ouverture à d'autres domaines que le solaire.

## Jalon 3 : méthode ouverte

Le pilier chercheur. Une surface où les méthodes appliquées peuvent être lues,
contestées, corrigées, validées.

- Surface de revue de la doctrine méthodologique (procédure et modèle d'issue).
- Reproductibilité des calages terrain (publication des méthodes et notebooks
  de calage) ; ouvert en issue une fois les artefacts prêts à être versés.
- Vérifier empiriquement l'homogénéisation quantile-mapping de NASA POWER sur
  le GHI (validation publique connue sur le longwave seulement).
- Correction d'altitude pour les massifs : le lissage MERRA-2 sous-estime le
  gradient thermique au Fouta-Djalon.
- Co-localisation de localités dans un même pixel satellite (résolution CERES
  d'environ 110 km) : détecter, documenter, piste haute-résolution.
- Documenter l'asymétrie de disponibilité des paramètres CERES (produits
  dérivés publiés en retard).
- Généraliser l'indicateur qualité 5 axes à toutes les séries et l'exposer.

## Jalon 4 : robustesse moteur

Le pilier dev.

- Compléter le contrat OpenAPI : typer les endpoints restants, exposer les
  codes d'erreur en schéma typé.
- Exposer un niveau de confiance A/B/C agrégé par série (aujourd'hui dérivé
  côté client).
- Découpler l'ingestion de masse des migrations Alembic (seed offline ou
  pipeline reproductible) ; c'est le chantier de fond qui simplifie aussi le
  pont du jalon 2.
- Endpoints F2 : renvoyer 422 (pas 500) sur paramètre invalide. Le validateur
  fautif est sur la classe de base commune, donc le correctif est transversal
  aux endpoints F2 (handler dédié ou validation en handler).
- Piloter le statut éditorial au niveau série (aujourd'hui au niveau mesure).
- Tracer le modèle appliqué et les séries compagnes dans la réponse F2.
- Distinguer les causes d'une valeur nulle en horaire (nocturne, indisponible).
- Rotation versionnée des mesures ré-ingérées (temps réel vers qualité climat)
  en ingestion continue.
- Connecteur réutilisable pour une nouvelle source ouverte (contrat commun) ;
  ingérer la climatologie OMM 1991-2020 comme grandeur dédiée.
- Servir des statistiques agrégées par série côté Core.
- Isoler les tests d'API par rollback transactionnel (chantier de harnais,
  demande une vue d'ensemble).

## Jalon 5 : terrain (confiance A)

La confiance A est réservée aux mesures validées au sol.

- Protocole de soumission d'une validation terrain par une station ou une
  institution.
- Doctrine de confiance graduée « B calibré » (satellite corrigé par station) :
  spécification et câblage.
- Exposer un résiduel de calage (incertitude de la correction transférée).
- Tester et documenter la stationnarité temporelle du biais satellite.
- Caractériser le sur-biais du DNI CAMS vs sol sur le réseau (ne pas
  généraliser depuis un seul site).
- Calibrer le modèle thermique Faiman pour le climat tropical (coefficients
  locaux).
- Établir le terme d'incertitude absolu du solaire (biais satellite vs sol).
- Construire ou intégrer une année météo typique (TMY) Guinée.

## Backlog

Sans jalon pour l'instant, à instruire au besoin :

- Unifier le modèle multi-granularité des mesures (journalier, mensuel, autres).
- Politique de clôture des versions de formule lors d'un upgrade.
- Borner le plancher du roundtrip Alembic (migration corrective irréversible).
- Revue périodique des dépendances scientifiques.

## Candidats (à confirmer selon le besoin)

- Endpoint `/v1/sources` exposant des libellés officiels : les libellés sont
  déjà dénormalisés dans `/v1/series` ; à créer seulement si un besoin distinct
  émerge.
- Ré-ingestion SARAH-3 ICDR 2024-2025 : en attente tant que le JRC plafonne la
  publication à 2023.

"""retirer_jargon_interne_textes_publies

Revision ID: 127
Revises: 126
Create Date: 2026-11-07 15:00:00.000000+00:00

Migration de coherence editoriale, sans DDL de structure ni donnee mesuree.

Les textes publies dans l'edition publique portaient du vocabulaire de
chantier interne (references de PR, de specs, d'etapes, de vagues, de lots,
de dettes « D-n », de caveats « L-XXX-n », d'ADR, codes de phase « 1-2b »,
renvois vers des documents du depot prive). Sont publies : les lignes de
``grandeurs_referentiel`` (table publiee telle quelle, manifeste de
publication) et les commentaires du catalogue, que ``pg_dump`` emporte avec
le schema (l'export ne passe pas ``--no-comments``).

1. ``grandeurs_referentiel.description`` de 10 grandeurs : le jargon est
   retire ; un identifiant qui portait un contenu est remplace par ce
   contenu en clair (L-SOIL-3 : demarrage propre du modele HSU ; L-SOIL-4 :
   grille EAC4 grossiere ; D-39 : decomposition de ``rang_referentiel``).
   Corrections de fond au passage : ``vent_2m`` n'alimente pas
   ``productible_correction_thermique`` (modele NOCT simple, sans vent ;
   Faiman retire de l'API) ; ``albedo_surface`` n'alimente que
   ``poa_bifacial`` (``poa_parametrable`` prend l'albedo en parametre) ;
   ``ghi`` ne vit pas qu'en ``mesures_ressource`` et ses sources ne sont pas
   toutes satellitaires.
2. Commentaires de tables, colonnes, vues et de la fonction
   ``valider_hierarchie_localites`` : jargon retire, renvois vers des
   documents internes retires (dont ``docs/architecture/04-api.md``, lien
   mort), decomptes figes remplaces par le nom de la contrainte CHECK qui
   fait foi. Corrections de fond : ``periode_type`` admet aussi
   ``statique`` ; les tables mensuelle et horaire portent d'autres sources
   que celles qu'elles nommaient (CAMS, ERA5-Land, ESMAP). Les modeles ORM
   portent les memes textes (``alembic check``) ; les vues et la fonction
   sont hors ORM (``COMMENT ON``, precedent migrations 018, 024, 084).

Gardes : chaque UPDATE de description exige le texte de depart exact
(exactement 1 ligne) ; chaque commentaire est verifie egal a son texte de
depart exact avant d'etre remplace. Le downgrade restaure les textes
d'origine a l'identique, garde de la meme facon. Trigger d'audit :
``kuma_log_audit()`` journalise les UPDATE ; ``modifie_le`` non touche
(precedent migrations 100, 125 et 126). Aucun reseau.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "127"
down_revision: str | Sequence[str] | None = "126"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === 1. Descriptions de grandeurs_referentiel ==============================

_SALISSURE_ANCIEN = (
    "Entree particules du modele de salissure HSU (pvlib.soiling.hsu) pour la "
    "grandeur proxy taux_salissure_proxy (Vague 5 soiling Lot C)."
)
_SALISSURE_NOUVEAU = (
    "Entree particules du modele de salissure HSU (pvlib.soiling.hsu) pour la "
    "grandeur proxy taux_salissure_proxy."
)

# code -> (description de depart exacte, nouvelle description)
DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "albedo_surface": (
        (
            "Albédo de surface (réflectivité du sol, sans dimension, plage théorique "
            "[0, 1]). Donnée brute ingérée depuis NASA POWER paramètre ALLSKY_SRF_ALB. "
            "Entrée de la composante réfléchie pour les modèles POA et préparation du "
            "bifacial (Phase 2 vague 5)."
        ),
        (
            "Albédo de surface (réflectivité du sol, sans dimension, plage théorique "
            "[0, 1]). Donnée brute ingérée depuis NASA POWER paramètre ALLSKY_SRF_ALB. "
            "Entrée du rayonnement réfléchi par le sol dans le POA bifacial "
            "(poa_bifacial), qui retient l'albédo fourni en paramètre pour les jours "
            "sans valeur ; le POA paramétrable (poa_parametrable) utilise uniquement "
            "l'albédo fourni en paramètre."
        ),
    ),
    "ghi": (
        (
            "Irradiation globale horizontale (Global Horizontal Irradiance) "
            "journalière. Donnée brute ingérée depuis NASA POWER paramètre "
            "ALLSKY_SFC_SW_DWN (méthode satellitaire CERES SYN1deg + FLASHFlux) ou "
            "autre source de méthode équivalente. Lieu de stockage physique : "
            "mesures_ressource (convention cadrage Q7 v1.3 pour "
            "methode_collecte=modele_satellitaire)."
        ),
        (
            "Irradiation globale horizontale (Global Horizontal Irradiance) "
            "journalière. Donnée brute ingérée depuis NASA POWER paramètre "
            "ALLSKY_SFC_SW_DWN (méthode satellitaire CERES SYN1deg + FLASHFlux) ou "
            "depuis d'autres sources (estimations satellitaires, réanalyses, mesures "
            "au sol) ; la source et la méthode de collecte de chaque série sont "
            "indiquées sur la série."
        ),
    ),
    "pm10": (
        (
            "Concentration massique journaliere de particules de diametre <= 10 um "
            "(ug/m3). Donnee brute EAC4 (ADS Copernicus), moyenne journaliere du pas "
            f"3-horaire. {_SALISSURE_ANCIEN} Inclut les PM2.5 (PM10 >= PM2.5). "
            "Confiance B."
        ),
        (
            "Concentration massique journaliere de particules de diametre <= 10 um "
            "(ug/m3). Donnee brute EAC4 (ADS Copernicus), moyenne journaliere du pas "
            f"3-horaire. {_SALISSURE_NOUVEAU} Inclut les PM2.5 (PM10 >= PM2.5). "
            "Confiance B."
        ),
    ),
    "pm2_5": (
        (
            "Concentration massique journaliere de particules fines de diametre "
            "<= 2,5 um (ug/m3). Donnee brute EAC4 (ADS Copernicus), moyenne "
            f"journaliere du pas 3-horaire. {_SALISSURE_ANCIEN} Confiance B (modele "
            "satellitaire)."
        ),
        (
            "Concentration massique journaliere de particules fines de diametre "
            "<= 2,5 um (ug/m3). Donnee brute EAC4 (ADS Copernicus), moyenne "
            f"journaliere du pas 3-horaire. {_SALISSURE_NOUVEAU} Confiance B (modele "
            "satellitaire)."
        ),
    ),
    "pr_realiste": (
        (
            "PR effectif site-specifique = PR_fourni x ratio_T x (1 - salissure), "
            "ratio sans dimension. Modes de correction aucune / temperature / "
            "salissure / temperature_salissure. Compose le facteur thermique NOCT "
            "(Ross 1980, productible_correction_thermique) et le proxy de salissure "
            "HSU (taux_salissure_proxy, Lot C). La courbe mensuelle est la 'PR "
            "saisonniere' (creux Harmattan). F1 calculee_volee, confiance B. "
            "Doctrine PR-reference (anti double-comptage) : le PR_fourni est suppose "
            "hors salissure ET hors temperature ; corrections multiplicatives "
            "separables. Ne traite pas la correction meteo/climat."
        ),
        (
            "PR effectif site-specifique = PR_fourni x ratio_T x (1 - salissure), "
            "ratio sans dimension. Modes de correction aucune / temperature / "
            "salissure / temperature_salissure. Compose le facteur thermique NOCT "
            "(Ross 1980, productible_correction_thermique) et le proxy de salissure "
            "HSU (taux_salissure_proxy). La courbe mensuelle est la 'PR "
            "saisonniere' (creux Harmattan). F1 calculee_volee, confiance B. "
            "Doctrine PR-reference (anti double-comptage) : le PR_fourni est suppose "
            "hors salissure ET hors temperature ; corrections multiplicatives "
            "separables. Ne traite pas la correction meteo/climat."
        ),
    ),
    "precipitation": (
        (
            "Hauteur de precipitation journaliere (mm/jour). Donnee brute ingeree "
            "depuis NASA POWER parametre PRECTOTCORR (Precipitation Corrected, source "
            "amont MERRA-2 GMAO / IMERG). Entree pluie du modele de salissure HSU "
            "(pvlib.soiling.hsu) pour la grandeur proxy taux_salissure_proxy (Vague "
            "5 soiling Lot C). Confiance B (modele satellitaire)."
        ),
        (
            "Hauteur de precipitation journaliere (mm/jour). Donnee brute ingeree "
            "depuis NASA POWER parametre PRECTOTCORR (Precipitation Corrected, source "
            "amont MERRA-2 GMAO / IMERG). Entree pluie du modele de salissure HSU "
            "(pvlib.soiling.hsu) pour la grandeur proxy taux_salissure_proxy. "
            "Confiance B (modele satellitaire)."
        ),
    ),
    "rang_referentiel": (
        (
            "Rang dans le référentiel Kuma. Position ordinale d'une série dans le "
            "classement des sites du référentiel pour une grandeur donnée. Calculé à "
            "la volée, dépendant du périmètre courant. [D-39 : desactivee en "
            "migration 042, decomposee en rang_referentiel_temporel + "
            "rang_referentiel_spatial cf. spec 1-7 PR #54.]"
        ),
        (
            "Rang dans le référentiel Kuma. Position ordinale d'une série dans le "
            "classement des sites du référentiel pour une grandeur donnée. Calculé à "
            "la volée, dépendant du périmètre courant. [Grandeur désactivée, "
            "remplacée par rang_referentiel_temporel (position d'un mois dans la "
            "climatologie de sa localité) et rang_referentiel_spatial (rang d'une "
            "ville parmi les villes pilotes pour un même mois).]"
        ),
    ),
    "taux_salissure_proxy": (
        (
            "Proxy de salissure des modules PV : perte de transmission par "
            "salissure, en % = (1 - ratio HSU) x 100. Modele HSU (pvlib.soiling.hsu, "
            "Coello & Boyle 2019) a partir des PM2.5/PM10 EAC4 (convertis ug/m3 -> "
            "g/m3, unite attendue par pvlib) et de la pluie NASA POWER (mm). F1 "
            "calculee_volee, confiance B derivee. Tilt et seuil de nettoyage par "
            "defaut documentes (10 deg, 1 mm). Caveats L-SOIL : proxy modele (pas "
            "une mesure de salissure, terrain) ; spin-up (HSU demarre propre, "
            "premiers jours sous-estimes, L-SOIL-3) ; grille EAC4 grossiere 0,75 "
            "deg (L-SOIL-4). "
        ),
        (
            "Proxy de salissure des modules PV : perte de transmission par "
            "salissure, en % = (1 - ratio HSU) x 100. Modele HSU (pvlib.soiling.hsu, "
            "Coello & Boyle 2019) a partir des PM2.5/PM10 EAC4 (convertis ug/m3 -> "
            "g/m3, unite attendue par pvlib) et de la pluie NASA POWER (mm). F1 "
            "calculee_volee, confiance B derivee. Tilt et seuil de nettoyage par "
            "defaut documentes (10 deg, 1 mm). Limites : proxy modele (pas une "
            "mesure de salissure sur le terrain) ; spin-up (HSU demarre propre, "
            "premiers jours sous-estimes) ; grille EAC4 grossiere 0,75 deg (des "
            "localites proches peuvent partager la meme cellule)."
        ),
    ),
    "vent_10m": (
        (
            "Vitesse moyenne journalière du vent à 10 mètres au-dessus de la "
            "surface. Donnée brute ingérée depuis NASA POWER paramètre WS10M (source "
            "MERRA-2 GMAO). Cohorte vent complémentaire pour usages potentiels "
            "éoliens ; hors périmètre Phase 2 (solaire uniquement)."
        ),
        (
            "Vitesse moyenne journalière du vent à 10 mètres au-dessus de la "
            "surface. Donnée brute ingérée depuis NASA POWER paramètre WS10M (source "
            "MERRA-2 GMAO). Complément du vent à 2 m pour d'éventuels usages "
            "éoliens ; n'entre dans aucun calcul solaire de Kuma."
        ),
    ),
    "vent_2m": (
        (
            "Vitesse moyenne journalière du vent à 2 mètres au-dessus de la surface. "
            "Donnée brute ingérée depuis NASA POWER paramètre WS2M (source MERRA-2 "
            "GMAO). Entrée du modèle Faiman 2008 pour la température cellule de la "
            "grandeur F2 productible_correction_thermique (résorbe la dette D-43)."
        ),
        (
            "Vitesse moyenne journalière du vent à 2 mètres au-dessus de la surface. "
            "Donnée brute ingérée depuis NASA POWER paramètre WS2M (source MERRA-2 "
            "GMAO). N'entre pas dans le calcul de la grandeur F2 "
            "productible_correction_thermique : son modèle de température de "
            "cellule (NOCT simple, Ross 1980) ne tient pas compte du vent."
        ),
    ),
}


# === 2. Commentaires de tables =============================================

_SUFFIXE_MESURES = (
    "Statut editorial et niveau de confiance derive/override par couche service editoriale."
)

# table -> (commentaire de depart exact, nouveau commentaire)
COMMENTAIRES_TABLES: dict[str, tuple[str, str]] = {
    "grandeurs_metier": (
        (
            "Grandeurs metier calculees par Kuma a partir des mesures brutes. "
            "Premiere table de fabrication editoriale phase 1 (etape 1-5). "
            "F1 stockee, agregations annuelles et mensuelles. Versioning "
            "temporel par (valide_du, valide_au) + EXCLUDE BTree-GiST sur "
            "identite metier etendue avec version_formule. " + _SUFFIXE_MESURES
        ),
        (
            "Grandeurs metier calculees par Kuma a partir des mesures brutes : "
            "grandeurs F1 de strategie stockee, agregees par annee, par mois ou sur "
            "une plage statique (cf. periode_type). Versioning temporel par "
            "(valide_du, valide_au) + EXCLUDE BTree-GiST sur identite metier "
            "etendue avec version_formule. " + _SUFFIXE_MESURES
        ),
    ),
    "mesures_ressource": (
        (
            "Mesures journalieres ingerees depuis sources externes. Premiere table "
            "metier operationnelle phase 1. Versioning temporel par (valide_du, "
            "valide_au) + EXCLUDE BTree-GiST sur identite metier (serie_id, "
            "instant_mesure). " + _SUFFIXE_MESURES
        ),
        (
            "Mesures journalieres ingerees depuis sources externes. Versioning "
            "temporel par (valide_du, valide_au) + EXCLUDE BTree-GiST sur identite "
            "metier (serie_id, instant_mesure). " + _SUFFIXE_MESURES
        ),
    ),
    "mesures_ressource_mensuelles": (
        (
            "Mesures mensuelles ingerees depuis sources externes (SARAH-3 ICDR + "
            "NASA POWER 1991-2020, etape 1-7a). Pendant mensuel de "
            "mesures_ressource (journalier strict, cadrage Q2 phase 1). Versioning "
            "temporel par (valide_du, valide_au) + EXCLUDE BTree-GiST sur identite "
            "metier (serie_id, annee, mois). " + _SUFFIXE_MESURES
        ),
        (
            "Mesures mensuelles ingerees depuis sources externes (la source de "
            "chaque serie est portee par series_metadonnees). Pendant mensuel de "
            "mesures_ressource (journalier) et mesures_ressource_horaires (horaire). "
            "Versioning temporel par (valide_du, valide_au) + EXCLUDE BTree-GiST "
            "sur identite metier (serie_id, annee, mois). " + _SUFFIXE_MESURES
        ),
    ),
    "mesures_ressource_horaires": (
        (
            "Mesures horaires ingerees depuis sources externes (NASA POWER, Vague "
            "3). Pendant horaire de mesures_ressource (journalier) et "
            "mesures_ressource_mensuelles (mensuel). instant_mesure en TIMESTAMPTZ "
            "(UTC) pour le controle qualite horaire (position solaire sans "
            "ambiguite de fuseau). Versioning temporel par (valide_du, valide_au) + "
            "EXCLUDE BTree-GiST sur identite metier (serie_id, instant_mesure). " + _SUFFIXE_MESURES
        ),
        (
            "Mesures horaires ingerees depuis sources externes (la source de chaque "
            "serie est portee par series_metadonnees). Pendant horaire de "
            "mesures_ressource (journalier) et mesures_ressource_mensuelles "
            "(mensuel). instant_mesure en TIMESTAMPTZ (UTC) pour le controle "
            "qualite horaire (position solaire sans ambiguite de fuseau). "
            "Versioning temporel par (valide_du, valide_au) + EXCLUDE BTree-GiST "
            "sur identite metier (serie_id, instant_mesure). " + _SUFFIXE_MESURES
        ),
    ),
    "calage_couverture": (
        (
            "Domaine de couverture des referentiels de calage : localites "
            "qualifiees pour le transport, avec justification. Pilote la couverture "
            "geographique des consommateurs (ADR-0004, couverture progressive)."
        ),
        (
            "Domaine de couverture des referentiels de calage : localites "
            "qualifiees pour le transport, avec justification. Pilote la couverture "
            "geographique des consommateurs, limitee aux localites ou le transport "
            "du calage est defendable et etendue progressivement."
        ),
    ),
    "referentiels_calage": (
        (
            "Referentiel de calage satellite/sol : biais saisonniers mesures aux "
            "stations de reference, publies avec provenance et portee de transport "
            "(ADR-0004)."
        ),
        (
            "Referentiel de calage satellite/sol : biais saisonniers mesures aux "
            "stations de reference, publies avec provenance et portee de transport."
        ),
    ),
}


# === 3. Commentaires de colonnes ===========================================

_NIVEAU_DERIVE_ANCIEN = (
    "Niveau de confiance derive automatiquement par la couche service a partir "
    "des regles R1-R4 (cf. spec mecaniques-transverses-phase-1 sec. 6.4). A = "
    "haute, B = moyenne, C = basse. Recalcule a chaque modification de "
    "methode_collecte ou source_id de la serie."
)
_NIVEAU_DERIVE_NOUVEAU = (
    "Niveau de confiance derive automatiquement par la couche service a partir "
    "des regles R1-R4. A = haute, B = moyenne, C = basse. Recalcule a chaque "
    "modification de methode_collecte ou source_id de la serie."
)

# (table, colonne) -> (commentaire de depart exact, nouveau commentaire)
COMMENTAIRES_COLONNES: dict[tuple[str, str], tuple[str, str]] = {
    ("grandeurs_metier", "version_formule"): (
        (
            "Version de la formule de calcul en vigueur au moment de l'insertion. "
            "Lien implicite avec grandeurs_referentiel.version_formule_actuelle pour "
            "la grandeur concernee. Incremente lors de toute revision "
            "methodologique. Inclus dans l'EXCLUDE pour permettre la coexistence "
            "v1/v2 apres upgrade (spec 1-5 sec. 3.2, cadrage Q7)."
        ),
        (
            "Version de la formule de calcul en vigueur au moment de l'insertion. "
            "Lien implicite avec grandeurs_referentiel.version_formule_actuelle pour "
            "la grandeur concernee. Incremente lors de toute revision "
            "methodologique. Inclus dans l'EXCLUDE pour permettre la coexistence "
            "v1/v2 apres upgrade."
        ),
    ),
    ("grandeurs_metier", "periode_type"): (
        (
            "Granularite temporelle de l'agregation : annuel (1 ligne par "
            "(localite, grandeur, annee, version_formule), mois NULL) ou mensuel "
            "(12 lignes par annee, mois 1-12). Cf. cadrage phase 1 Q2 et Q6."
        ),
        (
            "Granularite temporelle de l'agregation : annuel (une valeur par annee, "
            "mois NULL), mensuel (une valeur par annee et par mois, mois de 1 a 12) "
            "ou statique (une valeur pour toute la plage annee_debut a annee_fin, "
            "mois NULL). Valeurs autorisees : contrainte CHECK "
            "ck_grandeurs_metier_periode_type_valide."
        ),
    ),
    ("grandeurs_metier", "niveau_confiance_derive"): (
        _NIVEAU_DERIVE_ANCIEN,
        _NIVEAU_DERIVE_NOUVEAU,
    ),
    ("mesures_ressource", "niveau_confiance_derive"): (
        _NIVEAU_DERIVE_ANCIEN,
        _NIVEAU_DERIVE_NOUVEAU,
    ),
    ("series_metadonnees", "granularite"): (
        (
            "Discriminant de granularite temporelle pour le routage table-cible "
            "(journalier/mensuel/horaire). NULL pour les series kuma_calculs "
            "(routees par source vers grandeurs_metier ; temporalite portee par "
            "grandeurs_metier.periode_type). Resout D-36 (Vague 3 lot 1)."
        ),
        (
            "Discriminant de granularite temporelle pour le routage table-cible "
            "(journalier/mensuel/horaire). NULL pour les series kuma_calculs "
            "(routees par source vers grandeurs_metier ; temporalite portee par "
            "grandeurs_metier.periode_type)."
        ),
    ),
    ("series_metadonnees", "methode_collecte"): (
        (
            "Methode dominante de collecte de la serie. Liste indicative des 6 "
            "valeurs en spec mecaniques-transverses sec. 6.4. CHECK formel pose en "
            "1-2b."
        ),
        (
            "Methode dominante de collecte de la serie : mesure_directe, "
            "modele_satellitaire, interpolation_geographique, "
            "extrapolation_temporelle, calcul_derive ou expertise_humaine. Valeurs "
            "autorisees : contrainte CHECK "
            "ck_series_metadonnees_methode_collecte_valide (NULL admis)."
        ),
    ),
    ("sources", "type_source"): (
        (
            "11 valeurs autorisees : rapport, article_scientifique, texte_legal, "
            "communique, page_web, base_donnees, livre, chapitre_livre, these, "
            "norme_technique (10 valeurs documentaires externes initiales, "
            "migration 004) + auteur_kuma (couche editoriale interne Kuma, "
            "introduite en 1-5D-i pour la source synthetique kuma_calculs)."
        ),
        (
            "Type de la source : rapport, article_scientifique, texte_legal, "
            "communique, page_web, base_donnees, livre, chapitre_livre, these, "
            "norme_technique (sources documentaires externes) ou auteur_kuma "
            "(couche editoriale interne Kuma, source synthetique kuma_calculs). "
            "Valeurs autorisees : contrainte CHECK ck_sources_type_source_valide."
        ),
    ),
    ("sources", "fiabilite"): (
        (
            "Qualification editoriale Kuma (3 niveaux). Voir "
            "docs/architecture/04-api.md pour le mapping editorial complet."
        ),
        (
            "Qualification editoriale Kuma de la fiabilite de la source : haute, "
            "moyenne ou faible, NULL si non qualifiee (contrainte CHECK "
            "ck_sources_fiabilite_valide). Entre dans la derivation du niveau de "
            "confiance des mesures (regles R1 et R3)."
        ),
    ),
    ("localites", "type_localite"): (
        (
            "7 valeurs : continent, region_supranationale, pays, "
            "region_administrative, prefecture, commune, site. prefecture ajoutee "
            "en densification prefectorale Etape 1 (niveau pays > region > "
            "prefecture > commune)."
        ),
        (
            "Type de localite : continent, region_supranationale, pays, "
            "region_administrative, prefecture, commune ou site (contrainte CHECK "
            "ck_localites_type_valide). Niveaux administratifs : pays > region > "
            "prefecture > commune."
        ),
    ),
    ("grandeurs_referentiel", "code"): (
        (
            "Cle naturelle metier (ASCII pur, snake_case, citee par les FK aval). "
            "Cf. 01-naming.md section Codes metier des referentiels."
        ),
        "Cle naturelle metier (ASCII pur, snake_case, citee par les FK aval).",
    ),
}


# === 4. Commentaires hors ORM (vues, fonction) =============================

# objet SQL (``COMMENT ON <objet> IS``) -> (commentaire de depart exact, nouveau)
COMMENTAIRES_HORS_ORM: dict[str, tuple[str, str]] = {
    "VIEW v_grandeurs_metier_courantes": (
        (
            "Vue projetant les lignes courantes de grandeurs_metier (valide_au IS "
            "NULL) en version de formule actuelle (version_formule = "
            "grandeurs_referentiel.version_formule_actuelle) et hors statut "
            "deprecie. Ajoute la colonne calculee niveau_effectif = "
            "COALESCE(niveau_confiance_override, niveau_confiance_derive). "
            "Equivalent SQL de l'hybrid_property GrandeurMetier.niveau_effectif. "
            "Cf. spec 1-5 sec. 4."
        ),
        (
            "Vue projetant les lignes courantes de grandeurs_metier (valide_au IS "
            "NULL) en version de formule actuelle (version_formule = "
            "grandeurs_referentiel.version_formule_actuelle) et hors statut "
            "deprecie. Ajoute la colonne calculee niveau_effectif = "
            "COALESCE(niveau_confiance_override, niveau_confiance_derive). "
            "Equivalent SQL de l'hybrid_property GrandeurMetier.niveau_effectif."
        ),
    ),
    "VIEW v_mesures_avec_niveau_effectif": (
        (
            "Vue projetant mesures_ressource + colonne calculee niveau_effectif = "
            "COALESCE(niveau_confiance_override, niveau_confiance_derive). "
            "Equivalent SQL de l'hybrid_property MesureRessource.niveau_effectif. "
            "Permet d'eviter le scan applicatif Python pour les requetes lecture "
            "massives. Cf. spec 1-2b sec. 3.4."
        ),
        (
            "Vue projetant mesures_ressource + colonne calculee niveau_effectif = "
            "COALESCE(niveau_confiance_override, niveau_confiance_derive). "
            "Equivalent SQL de l'hybrid_property MesureRessource.niveau_effectif. "
            "Permet d'eviter le scan applicatif Python pour les requetes lecture "
            "massives."
        ),
    ),
    "FUNCTION valider_hierarchie_localites()": (
        (
            "Valide la matrice parent-enfant de localites (BEFORE INSERT OR "
            "UPDATE). Cloture datee de la dette du trigger 007 (annonce des "
            "migration 003, jamais bati). Portee minimale : matrice + "
            "continent-racine ; pas de detection de cycles."
        ),
        (
            "Valide la matrice parent-enfant de localites (BEFORE INSERT OR "
            "UPDATE). Portee minimale : matrice + continent-racine ; pas de "
            "detection de cycles."
        ),
    ),
}

# Lecture du commentaire courant d'un objet ``COMMENT ON`` hors ORM.
_LECTURE_HORS_ORM: dict[str, str] = {
    "VIEW v_grandeurs_metier_courantes": (
        "SELECT obj_description('v_grandeurs_metier_courantes'::regclass, 'pg_class')"
    ),
    "VIEW v_mesures_avec_niveau_effectif": (
        "SELECT obj_description('v_mesures_avec_niveau_effectif'::regclass, 'pg_class')"
    ),
    "FUNCTION valider_hierarchie_localites()": (
        "SELECT obj_description('valider_hierarchie_localites()'::regprocedure, 'pg_proc')"
    ),
}


# === Helpers ===============================================================


def _litteral(texte: str) -> str:
    """Litteral SQL d'un texte constant (``COMMENT ON`` n'accepte pas de parametre)."""
    return "'" + texte.replace("'", "''") + "'"


def _exiger_commentaire(objet: str, actuel: str | None, attendu: str) -> None:
    if actuel != attendu:
        raise RuntimeError(
            f"Migration 127 : commentaire de {objet} attendu dans son etat de depart "
            f"exact, trouve {actuel!r}. Abandon sans ecriture partielle."
        )


def _commentaire_table(table: str) -> str | None:
    return (
        op.get_bind()
        .execute(sa.text("SELECT obj_description(CAST(:t AS regclass), 'pg_class')"), {"t": table})
        .scalar()
    )


def _commentaire_colonne(table: str, colonne: str) -> str | None:
    return (
        op.get_bind()
        .execute(
            sa.text(
                """
            SELECT col_description(a.attrelid, a.attnum)
            FROM pg_attribute a
            WHERE a.attrelid = CAST(:t AS regclass) AND a.attname = :c
            """
            ),
            {"t": table, "c": colonne},
        )
        .scalar()
    )


def _update_description(*, code: str, attendue: str, nouvelle: str) -> None:
    """UPDATE garde de la description d'une grandeur : texte de depart exact, 1 ligne."""
    resultat = op.get_bind().execute(
        sa.text(
            """
            UPDATE grandeurs_referentiel
            SET description = :nouvelle
            WHERE code = :code AND description = :attendue
            """
        ),
        {"code": code, "nouvelle": nouvelle, "attendue": attendue},
    )
    if resultat.rowcount != 1:
        raise RuntimeError(
            f"Migration 127 : description de {code!r} attendue dans son etat de depart "
            f"exact, {resultat.rowcount} ligne(s) mise(s) a jour au lieu de 1. Abandon "
            "sans ecriture partielle."
        )


def _appliquer(*, sens: int) -> None:
    """``sens`` = 1 : (ancien -> nouveau) ; ``sens`` = 0 : (nouveau -> ancien)."""
    depart, arrivee = (0, 1) if sens == 1 else (1, 0)

    for code in sorted(DESCRIPTIONS):
        textes = DESCRIPTIONS[code]
        _update_description(code=code, attendue=textes[depart], nouvelle=textes[arrivee])

    for table in sorted(COMMENTAIRES_TABLES):
        textes = COMMENTAIRES_TABLES[table]
        _exiger_commentaire(f"table {table}", _commentaire_table(table), textes[depart])
        op.create_table_comment(table, textes[arrivee], existing_comment=textes[depart])

    for table, colonne in sorted(COMMENTAIRES_COLONNES):
        textes = COMMENTAIRES_COLONNES[(table, colonne)]
        _exiger_commentaire(
            f"colonne {table}.{colonne}", _commentaire_colonne(table, colonne), textes[depart]
        )
        op.alter_column(table, colonne, comment=textes[arrivee], existing_comment=textes[depart])

    for objet in sorted(COMMENTAIRES_HORS_ORM):
        textes = COMMENTAIRES_HORS_ORM[objet]
        actuel = op.get_bind().execute(sa.text(_LECTURE_HORS_ORM[objet])).scalar()
        _exiger_commentaire(objet, actuel, textes[depart])
        op.execute(f"COMMENT ON {objet} IS {_litteral(textes[arrivee])}")


def upgrade() -> None:
    _appliquer(sens=1)


def downgrade() -> None:
    _appliquer(sens=0)

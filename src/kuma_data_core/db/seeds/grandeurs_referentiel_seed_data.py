"""Données de seed des grandeurs ``grandeurs_referentiel`` (migrations 010 et 015).

Le fichier expose **deux variables séparées** par discipline d'immuabilité
des migrations mergées (cf. ``docs/conventions/02-migrations.md``) :

- ``GRANDEURS_REFERENTIEL_SEED`` (15 entrées) : grandeurs traduites Kuma.
  Seedées par la migration 010. Immutable post-merge.

- ``GRANDEURS_REFERENTIEL_SEED_BRUTES_1_2B`` (5 entrées) : grandeurs
  brutes ingérées (``ghi``, ``dni``, ``dhi``, ``t2m``, ``rh2m``)
  ajoutées par la migration 015.

Le référentiel devient hétérogène : grandeurs traduites Kuma
+ grandeurs brutes ingérées, distinguées par leur description. Le lieu
de stockage physique d'une F1 stockée est déterminé par
``series_metadonnees.methode_collecte`` de la série :

- F1 stockée + ``methode_collecte ∈ {modele_satellitaire, mesure_directe}``
  → physiquement dans ``mesures_ressource``
- F1 stockée + ``methode_collecte ∈ {calcul_derive, expertise_humaine}``
  → physiquement dans ``grandeurs_metier``

Décomptes :

- ``GRANDEURS_REFERENTIEL_SEED`` : 8 F1 stockee + 2 F1 calculee_volee
  + 5 F2 calculee_volee = 15 grandeurs traduites.
- ``GRANDEURS_REFERENTIEL_SEED_BRUTES_1_2B`` : 5 F1 stockee (brutes
  ingestion satellitaire).
- Total : 20 grandeurs.

Pattern reproduit de ``unites_seed_data.py`` : dicts prêts
pour ``op.bulk_insert``, ``cree_par`` et ``modifie_par`` laissés à
NULL, ``actif``/``cree_le``/``modifie_le``/``version_formule_actuelle``
laissés aux ``server_default``.

Chaque entrée porte une clé ``unite_code`` (string) au lieu de
``unite_id`` (int). La résolution ``unite_code -> unite_id`` est
effectuée dynamiquement par les migrations (010 et 015) - les IDs
``IDENTITY`` ne sont pas garantis stables entre environnements.

``methode_calcul_doc`` reste NULL pour les 20 grandeurs - fiches
méthodologiques détaillées différées à une étape éditoriale
ultérieure.
"""

from __future__ import annotations

from typing import Any

GRANDEURS_REFERENTIEL_SEED: list[dict[str, Any]] = [
    {
        "code": "hep",
        "libelle": "Heures équivalentes pleines",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "unite_code": "heure_equivalente_pleine",
        "description": (
            "Heures équivalentes pleines (HEP). Quotient de l'énergie "
            "produite par la puissance crête nominale d'un système "
            "photovoltaïque, exprimé en heures équivalentes. Cadence "
            "annuelle ou mensuelle selon la série."
        ),
    },
    {
        "code": "kt",
        "libelle": "Indice de clarté",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "unite_code": "sans_unite",
        "description": (
            "Indice de clarté Kt. Rapport entre l'irradiation globale "
            "horizontale au sol et l'irradiation extraterrestre. Ingéré "
            "directement depuis NASA POWER (paramètre `ALLSKY_KT`)."
        ),
    },
    {
        "code": "fraction_diffuse",
        "libelle": "Fraction diffuse",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "unite_code": "sans_unite",
        "description": (
            "Fraction diffuse de l'irradiation. Rapport entre "
            "l'irradiation horizontale diffuse (DHI) et l'irradiation "
            "horizontale globale (GHI). DHI source CERES SYN1deg."
        ),
    },
    {
        "code": "productible_specifique_theorique",
        "libelle": "Productible spécifique théorique",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "unite_code": "kwh_par_kwc_jour",
        "description": (
            "Productible spécifique théorique journalier. Énergie "
            "attendue d'un système photovoltaïque par kilowatt-crête "
            "installé, calculée par un modèle de performance simplifié "
            "à partir des seules données d'irradiation, sans correction "
            "thermique ni autre paramètre. Valeur de référence éditoriale."
        ),
    },
    {
        "code": "variabilite_journaliere",
        "libelle": "Indice de variabilité journalière",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "unite_code": "sans_unite",
        "description": (
            "Indice de variabilité journalière. Coefficient de variation "
            "de l'irradiation journalière sur la période, sans dimension. "
            "Utilisé pour le dimensionnement des systèmes avec stockage."
        ),
    },
    {
        "code": "productible_mensuel",
        "libelle": "Productible mensuel",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "unite_code": "kwh_par_kwc_mois",
        "description": (
            "Productible mensuel. Énergie produite par kilowatt-crête "
            "sur un mois calendaire, calculée pour chacun des 12 mois "
            "de l'année. Caractérise la saisonnalité énergétique d'un site."
        ),
    },
    {
        "code": "ecart_relatif_referentiel",
        "libelle": "Écart relatif au référentiel Kuma",
        "famille": "F1",
        "strategie_calcul": "calculee_volee",
        "unite_code": "pourcent",
        "description": (
            "Écart relatif au référentiel Kuma. Différence entre la "
            "valeur d'une série et la moyenne de cette grandeur calculée "
            "sur l'ensemble des sites du référentiel Kuma, exprimée en "
            "pourcent. Calculée à la volée, dépendante du périmètre courant."
        ),
    },
    {
        "code": "rang_referentiel",
        "libelle": "Rang dans le référentiel Kuma",
        "famille": "F1",
        "strategie_calcul": "calculee_volee",
        "unite_code": "sans_unite",
        "description": (
            "Rang dans le référentiel Kuma. Position ordinale d'une "
            "série dans le classement des sites du référentiel pour une "
            "grandeur donnée. Calculé à la volée, dépendant du périmètre "
            "courant."
        ),
    },
    {
        "code": "indicateur_qualite_donnees",
        "libelle": "Indicateur qualité du jeu de données",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "unite_code": "sans_unite",
        "description": (
            "Indicateur qualité du jeu de données. Score éditorial Kuma "
            "de 1 (faible) à 5 (excellent) caractérisant la fiabilité "
            "d'une série mesurée. Métrique de transparence éditoriale."
        ),
    },
    {
        "code": "poa_parametrable",
        "libelle": "POA paramétrable",
        "famille": "F2",
        "strategie_calcul": "calculee_volee",
        "unite_code": "kwh_par_m2_jour",
        "description": (
            "Plane of Array (POA) paramétrable. Irradiation incidente "
            "sur une surface inclinée selon les paramètres utilisateur "
            "(inclinaison, azimut, albédo). Calculée à la volée à partir "
            "de GHI, DNI et DHI selon le modèle de transposition retenu."
        ),
    },
    {
        "code": "productible_correction_thermique",
        "libelle": "Productible avec correction thermique",
        "famille": "F2",
        "strategie_calcul": "calculee_volee",
        "unite_code": "kwh_par_kwc_jour",
        "description": (
            "Productible spécifique journalier avec correction thermique. "
            "Énergie produite par kilowatt-crête, ajustée selon le "
            "coefficient de température et la NOCT du module fournis par "
            "l'utilisateur. Calculée à la volée."
        ),
    },
    {
        "code": "productible_pr_fourni",
        "libelle": "Productible avec PR fourni",
        "famille": "F2",
        "strategie_calcul": "calculee_volee",
        "unite_code": "kwh_par_kwc_jour",
        "description": (
            "Productible spécifique journalier avec PR fourni. Énergie "
            "produite par kilowatt-crête, ajustée selon le Performance "
            "Ratio fourni par l'utilisateur. Calculée à la volée."
        ),
    },
    {
        "code": "energie_utile_ecs",
        "libelle": "Énergie utile ECS",
        "famille": "F2",
        "strategie_calcul": "calculee_volee",
        "unite_code": "kwh_par_m2_jour",
        "description": (
            "Énergie utile pour eau chaude sanitaire (ECS). Énergie "
            "thermique délivrée par mètre carré de collecteur solaire, "
            "ajustée selon le rendement optique et les pertes thermiques "
            "fournis par l'utilisateur. Calculée à la volée."
        ),
    },
    {
        "code": "degre_jour_climatisation",
        "libelle": "Degrés-jours de climatisation",
        "famille": "F2",
        "strategie_calcul": "calculee_volee",
        "unite_code": "degre_jour",
        "description": (
            "Degrés-jours de climatisation. Cumul des écarts positifs "
            "entre la température journalière moyenne et la température "
            "de référence de climatisation (base) précisée par "
            "l'utilisateur. Calculé à la volée selon la convention "
            "ISO 15927-6 (Part 6, Accumulated temperature differences)."
        ),
    },
    {
        "code": "humidex",
        "libelle": "Indice de confort thermique (Humidex)",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "unite_code": "degree_celsius",
        "description": (
            "Indice de confort thermique Humidex. Indice combinant "
            "température et humidité, exprimé en degrés Celsius "
            "apparents. Formule Masterton & Richardson (1979), Service "
            "de l'environnement atmosphérique (AES) d'Environnement "
            "Canada."
        ),
    },
]

# Variable séparée pour préserver l'immuabilité de la migration 010 (qui
# consomme `GRANDEURS_REFERENTIEL_SEED` à 15 entrées). Les 5 grandeurs brutes
# ingérées sont consommées par la migration 015 via
# `GRANDEURS_REFERENTIEL_SEED_BRUTES_1_2B`.
#
# Lieu de stockage physique = mesures_ressource quand la
# série a methode_collecte ∈ {modele_satellitaire, mesure_directe}.
GRANDEURS_REFERENTIEL_SEED_BRUTES_1_2B: list[dict[str, Any]] = [
    {
        "code": "ghi",
        "libelle": "Irradiation globale horizontale",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "unite_code": "kwh_par_m2_jour",
        "description": (
            "Irradiation globale horizontale (Global Horizontal Irradiance) "
            "journalière. Donnée brute ingérée depuis NASA POWER paramètre "
            "ALLSKY_SFC_SW_DWN (méthode satellitaire CERES SYN1deg + "
            "FLASHFlux) ou autre source de méthode équivalente. Lieu de "
            "stockage physique : mesures_ressource (convention cadrage Q7 "
            "v1.3 pour methode_collecte=modele_satellitaire)."
        ),
    },
    {
        "code": "dni",
        "libelle": "Irradiation normale directe",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "unite_code": "kwh_par_m2_jour",
        "description": (
            "Irradiation normale directe (Direct Normal Irradiance) "
            "journalière. Donnée brute ingérée depuis NASA POWER paramètre "
            "ALLSKY_SFC_SW_DNI ou autre source de méthode équivalente. "
            "Entrée du calcul Plane of Array (POA) paramétrable F2."
        ),
    },
    {
        "code": "dhi",
        "libelle": "Irradiation diffuse horizontale",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "unite_code": "kwh_par_m2_jour",
        "description": (
            "Irradiation diffuse horizontale (Diffuse Horizontal Irradiance) "
            "journalière. Donnée brute ingérée depuis NASA POWER paramètre "
            "ALLSKY_SFC_SW_DIFF (composant diffus CERES SYN1deg) ou autre "
            "source de méthode équivalente. Entrée du calcul fraction "
            "diffuse F1 stockée et du POA paramétrable F2."
        ),
    },
    {
        "code": "t2m",
        "libelle": "Température à 2 mètres",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "unite_code": "degree_celsius",
        "description": (
            "Température moyenne journalière à 2 mètres au-dessus de la "
            "surface. Donnée brute ingérée depuis NASA POWER paramètre "
            "T2M (source MERRA-2 GMAO) ou autre source équivalente. "
            "Entrée du calcul humidex F1 stockée et du productible avec "
            "correction thermique F2."
        ),
    },
    {
        "code": "rh2m",
        "libelle": "Humidité relative à 2 mètres",
        "famille": "F1",
        "strategie_calcul": "stockee",
        "unite_code": "pourcent",
        "description": (
            "Humidité relative moyenne journalière à 2 mètres au-dessus "
            "de la surface. Donnée brute ingérée depuis NASA POWER "
            "paramètre RH2M (source MERRA-2 GMAO) ou autre source "
            "équivalente. Entrée du calcul humidex F1 stockée (formule "
            "Masterton & Richardson 1979)."
        ),
    },
]


# Vérifications de décompte sur GRANDEURS_REFERENTIEL_SEED (inchangé, 15 entrées).
assert len(GRANDEURS_REFERENTIEL_SEED) == 15, (
    f"Expected 15 grandeurs traduites, got {len(GRANDEURS_REFERENTIEL_SEED)}"
)

_codes_seen: set[str] = set()
for _entry in GRANDEURS_REFERENTIEL_SEED:
    _code = _entry["code"]
    assert _code not in _codes_seen, f"Code dupliqué dans GRANDEURS_REFERENTIEL_SEED : {_code!r}"
    _codes_seen.add(_code)
del _codes_seen, _entry, _code

_familles = [e["famille"] for e in GRANDEURS_REFERENTIEL_SEED]
_strategies = [e["strategie_calcul"] for e in GRANDEURS_REFERENTIEL_SEED]
assert _familles.count("F1") == 10, f"Expected 10 F1, got {_familles.count('F1')}"
assert _familles.count("F2") == 5, f"Expected 5 F2, got {_familles.count('F2')}"
assert _strategies.count("stockee") == 8, f"Expected 8 stockee, got {_strategies.count('stockee')}"
assert _strategies.count("calculee_volee") == 7, (
    f"Expected 7 calculee_volee, got {_strategies.count('calculee_volee')}"
)
del _familles, _strategies

# Vérifications de décompte sur GRANDEURS_REFERENTIEL_SEED_BRUTES_1_2B
# (5 entrées toutes F1 stockee, ingérées depuis sources externes).
assert len(GRANDEURS_REFERENTIEL_SEED_BRUTES_1_2B) == 5, (
    f"Expected 5 brutes ingérées 1-2b, got {len(GRANDEURS_REFERENTIEL_SEED_BRUTES_1_2B)}"
)

_codes_brutes_seen: set[str] = set()
_codes_existants: set[str] = {e["code"] for e in GRANDEURS_REFERENTIEL_SEED}
for _entry in GRANDEURS_REFERENTIEL_SEED_BRUTES_1_2B:
    _code = _entry["code"]
    assert _code not in _codes_brutes_seen, (
        f"Code dupliqué dans GRANDEURS_REFERENTIEL_SEED_BRUTES_1_2B : {_code!r}"
    )
    _codes_brutes_seen.add(_code)
    assert _code not in _codes_existants, (
        f"Code {_code!r} déjà présent dans GRANDEURS_REFERENTIEL_SEED - collision référentiel."
    )
del _codes_brutes_seen, _codes_existants, _entry, _code

# Tuple expose les 5 codes pour les tests d'intégration + assertions aval
CODES_BRUTES_INGESTION_1_2B: tuple[str, ...] = tuple(
    e["code"] for e in GRANDEURS_REFERENTIEL_SEED_BRUTES_1_2B
)

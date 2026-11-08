"""Grandeurs référentielles stockées dans ``grandeurs_metier``.

- ``ecart_relatif_referentiel`` : ``(kuma - sarah3) / sarah3 * 100``, NASA
  POWER journalier agrégé au mois contre PVGIS-SARAH3 ICDR, sur 2021-2023.
- ``rang_referentiel_temporel`` : percentile de la valeur 2021-2025 dans la
  climatologie NASA POWER 1991-2020 du même mois calendaire (n = 30).
- ``rang_referentiel_spatial`` : rang 1-N parmi les N localités classées, même
  mois. Version 1 : Kaloum, Kankan, Kindia, Labé, Mamou et Nzérékoré (orchestrateur combiné) ;
  version 2 : toutes les localités couvertes (:func:`calculer_et_inserer_rang_spatial`).

Confiance propagée depuis les entrées du mois (règle P), plafonnée à ``B`` :
l'écart combine deux sources, le quantile mapping NASA POWER n'est validé
publiquement que pour le rayonnement de grande longueur d'onde, et le rang
spatial classe des données de modèle dont la grille donne des valeurs
identiques à des localités voisines.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TypedDict

from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.editorial.niveaux_confiance import (
    NiveauConfiance,
    NiveauxEntrees,
    calculer_niveau_confiance_derive,
)
from kuma_data_core.editorial.statuts import filtre_mesure_utilisable
from kuma_data_core.services.grandeurs._commun import (
    CibleConfiance,
    inserer_lignes_grandeurs_metier,
    lire_cible,
    verifier_version_formule,
)

# === Constantes module =====================================================

GRANDEUR_ECART: str = "ecart_relatif_referentiel"
GRANDEUR_RANG_TEMPOREL: str = "rang_referentiel_temporel"
GRANDEUR_RANG_SPATIAL: str = "rang_referentiel_spatial"

PLAFOND_CONFIANCE: NiveauConfiance = "B"
VERSION_FORMULE_1_7B: int = 1

ANNEE_KUMA_DEBUT: int = 2021
ANNEE_KUMA_FIN: int = 2025
ANNEE_SARAH3_FIN: int = 2023
ANNEE_CLIMATO_DEBUT: int = 1991
ANNEE_CLIMATO_FIN: int = 2020

N_VILLES_KUMA: int = 6
"""Taille du pool du rang spatial version 1, figée par :func:`calculer_et_inserer_referentiels`."""

SEUIL_SARAH3_MIN_DEFAUT: float = 0.5
"""SARAH-3 mensuel minimal (kWh/m²/jour) pour calculer un écart relatif.

En dessous, l'écart diverge (``s -> 0``) et la valeur est stockée NULL. En
Afrique de l'Ouest tropicale, même un mois très couvert dépasse 2 kWh/m²/jour :
une valeur < 0.5 trahit un défaut amont (sentinelle, unité).
"""


# === Types ================================================================


class ContexteVille(TypedDict):
    """Contexte d'ingestion par localité pour l'orchestrateur référentiels."""

    localite_id: int
    code_serie_kuma_daily: str
    code_serie_sarah3: str
    code_serie_power_1991_2020: str


class CalculReferentielsResultat(TypedDict):
    """Résultat d'un appel à :func:`calculer_et_inserer_referentiels`."""

    nb_ecart_insere: int
    nb_rang_temporel_insere: int
    nb_rang_spatial_insere: int
    nb_total: int


# === Fonctions pures ======================================================


def _niveau_derive(cible: CibleConfiance, niveaux_entrees: set[str]) -> str:
    """Niveau d'une valeur calculée depuis les niveaux de ses entrées."""
    return calculer_niveau_confiance_derive(
        cible.methode_collecte,
        cible.fiabilite_source,
        niveaux_entrees=niveaux_entrees,
        plafond=PLAFOND_CONFIANCE,
    )


def _agreger_mensuel(valeurs_journalieres: Sequence[float]) -> float:
    """Moyenne arithmétique ; ``ValueError`` si vide."""
    if not valeurs_journalieres:
        raise ValueError("Aucune valeur journaliere a agreger")
    return sum(valeurs_journalieres) / len(valeurs_journalieres)


def _calcul_ecart_relatif(valeur_kuma: float, valeur_sarah3: float) -> float:
    """``(kuma - sarah3) / sarah3 * 100`` ; ``ValueError`` si SARAH-3 nul."""
    if valeur_sarah3 == 0.0:
        raise ValueError("Ecart relatif indefini : valeur SARAH-3 nulle")
    return (valeur_kuma - valeur_sarah3) / valeur_sarah3 * 100.0


def _calcul_rang_temporel(valeur_kuma: float, distribution: Sequence[float]) -> float:
    """Percentile type 7 (numpy/R) : ``(rang - 1) / (n - 1) * 100``, borné à [0, 100].

    Les ex-aequo prennent le demi-rang ; ``ValueError`` si n < 2.
    """
    if len(distribution) < 2:
        raise ValueError(f"Distribution insuffisante : n={len(distribution)} (>= 2 requis)")

    n = len(distribution)
    nb_strict_inf = sum(1 for v in distribution if v < valeur_kuma)
    nb_egaux = sum(1 for v in distribution if v == valeur_kuma)
    rang = nb_strict_inf + (nb_egaux + 1) / 2.0
    percentile = (rang - 1) / (n - 1) * 100.0
    return max(0.0, min(100.0, percentile))


def _calcul_rang_spatial(valeurs_par_localite: dict[int, float]) -> dict[int, int]:
    """Rang 1-N par valeur croissante ; ex-aequo départagés par l'ordre d'entrée."""
    if not valeurs_par_localite:
        raise ValueError("Aucune valeur a classer")
    items_tries = sorted(valeurs_par_localite.items(), key=lambda kv: kv[1])
    return {loc_id: idx + 1 for idx, (loc_id, _) in enumerate(items_tries)}


# === Helpers I/O ==========================================================


def _lire_kuma_mensuel(
    session: Session, code_serie: str, niveaux: NiveauxEntrees | None = None
) -> dict[tuple[int, int], float]:
    """Agrège en moyenne mensuelle les mesures Kuma NASA POWER 2021-2025.

    Range sous chaque mois les niveaux effectifs de ses jours dans ``niveaux``.
    """
    rows = session.execute(
        text(
            f"""
            SELECT
                EXTRACT(YEAR FROM mr.instant_mesure)::int AS annee,
                EXTRACT(MONTH FROM mr.instant_mesure)::int AS mois,
                AVG(mr.valeur) AS moyenne,
                array_agg(DISTINCT coalesce(mr.niveau_confiance_override,
                                            mr.niveau_confiance_derive)) AS niveaux
            FROM mesures_ressource mr
            JOIN series_metadonnees sm ON sm.id = mr.serie_id
            WHERE sm.code = :code
              AND {filtre_mesure_utilisable("mr")}
            GROUP BY annee, mois
            ORDER BY annee, mois
            """
        ),
        {"code": code_serie},
    ).all()
    if niveaux is not None:
        for r in rows:
            for niveau in r.niveaux:
                niveaux.ajouter((int(r.annee), int(r.mois)), niveau)
    return {(int(r.annee), int(r.mois)): float(r.moyenne) for r in rows}


def _lire_mensuel(
    session: Session, code_serie: str, niveaux: NiveauxEntrees | None = None
) -> dict[tuple[int, int], float]:
    """Lit les valeurs mensuelles d'une série, et leurs niveaux effectifs dans ``niveaux``."""
    rows = session.execute(
        text(
            f"""
            SELECT m.annee, m.mois, m.valeur,
                   coalesce(m.niveau_confiance_override, m.niveau_confiance_derive) AS niveau
            FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code = :code
              AND {filtre_mesure_utilisable("m")}
            ORDER BY m.annee, m.mois
            """
        ),
        {"code": code_serie},
    ).all()
    if niveaux is not None:
        for r in rows:
            niveaux.ajouter((int(r.annee), int(r.mois)), r.niveau)
    return {(int(r.annee), int(r.mois)): float(r.valeur) for r in rows}


# === Orchestrateur I/O ====================================================


def calculer_et_inserer_referentiels(
    *,
    session: Session,
    contextes_villes: Sequence[ContexteVille],
    serie_id_par_grandeur_localite: dict[tuple[str, int], int],
) -> CalculReferentielsResultat:
    """Calcule et insère les 936 lignes des trois grandeurs (add et flush, sans commit).

    ``serie_id_par_grandeur_localite`` : ``{(grandeur_code, localite_id): serie_id}``
    des 18 séries calculées, créées au préalable.
    """
    nb_ecart = 0
    nb_rang_temporel = 0
    nb_rang_spatial = 0

    # Pré-charge des mesures Kuma mensuelles (utilisées par les 3 étapes)
    kuma_par_localite: dict[int, dict[tuple[int, int], float]] = {}
    niveaux_kuma: dict[int, NiveauxEntrees] = {}
    for ctx in contextes_villes:
        loc_id = ctx["localite_id"]
        niveaux_kuma[loc_id] = NiveauxEntrees()
        kuma_par_localite[loc_id] = _lire_kuma_mensuel(
            session, ctx["code_serie_kuma_daily"], niveaux_kuma[loc_id]
        )

    # === ecart_relatif_referentiel (216 lignes attendues) ====================
    for ctx in contextes_villes:
        loc_id = ctx["localite_id"]
        niveaux_sarah3 = NiveauxEntrees()
        sarah3 = _lire_mensuel(session, ctx["code_serie_sarah3"], niveaux_sarah3)
        serie_id = serie_id_par_grandeur_localite[(GRANDEUR_ECART, loc_id)]
        cible = lire_cible(session, serie_id)

        lignes: list[dict[str, object]] = []
        for annee in range(ANNEE_KUMA_DEBUT, ANNEE_SARAH3_FIN + 1):
            for mois in range(1, 13):
                kuma_v = kuma_par_localite[loc_id].get((annee, mois))
                sarah3_v = sarah3.get((annee, mois))
                if kuma_v is None or sarah3_v is None:
                    continue
                ecart_pct = _calcul_ecart_relatif(kuma_v, sarah3_v)
                lignes.append(
                    {
                        "grandeur_code": GRANDEUR_ECART,
                        "localite_id": loc_id,
                        "series_metadonnees_id": serie_id,
                        "periode_type": "mensuel",
                        "annee_debut": annee,
                        "annee_fin": annee,
                        "mois": mois,
                        "version_formule": VERSION_FORMULE_1_7B,
                        "valeur": ecart_pct,
                        "niveau_confiance_derive": _niveau_derive(
                            cible,
                            niveaux_kuma[loc_id].du_mois(annee, mois)
                            | niveaux_sarah3.du_mois(annee, mois),
                        ),
                    }
                )
        inserer_lignes_grandeurs_metier(session, lignes)
        nb_ecart += len(lignes)

    # === rang_referentiel_temporel (360 lignes attendues) ====================
    for ctx in contextes_villes:
        loc_id = ctx["localite_id"]
        niveaux_climato = NiveauxEntrees()
        climato = _lire_mensuel(session, ctx["code_serie_power_1991_2020"], niveaux_climato)

        # Distribution stratifiée par mois calendrier
        distribution_par_mois: dict[int, list[float]] = {m: [] for m in range(1, 13)}
        for (annee_clim, mois_clim), valeur in climato.items():
            if ANNEE_CLIMATO_DEBUT <= annee_clim <= ANNEE_CLIMATO_FIN:
                distribution_par_mois[mois_clim].append(valeur)

        serie_id = serie_id_par_grandeur_localite[(GRANDEUR_RANG_TEMPOREL, loc_id)]
        cible = lire_cible(session, serie_id)

        lignes = []
        for annee in range(ANNEE_KUMA_DEBUT, ANNEE_KUMA_FIN + 1):
            for mois in range(1, 13):
                kuma_v = kuma_par_localite[loc_id].get((annee, mois))
                distribution = distribution_par_mois.get(mois, [])
                if kuma_v is None or len(distribution) < 2:
                    continue
                percentile = _calcul_rang_temporel(kuma_v, distribution)
                lignes.append(
                    {
                        "grandeur_code": GRANDEUR_RANG_TEMPOREL,
                        "localite_id": loc_id,
                        "series_metadonnees_id": serie_id,
                        "periode_type": "mensuel",
                        "annee_debut": annee,
                        "annee_fin": annee,
                        "mois": mois,
                        "version_formule": VERSION_FORMULE_1_7B,
                        "valeur": percentile,
                        "niveau_confiance_derive": _niveau_derive(
                            cible,
                            niveaux_kuma[loc_id].du_mois(annee, mois)
                            | niveaux_climato.de_periode(
                                ANNEE_CLIMATO_DEBUT, ANNEE_CLIMATO_FIN, mois
                            ),
                        ),
                    }
                )
        inserer_lignes_grandeurs_metier(session, lignes)
        nb_rang_temporel += len(lignes)

    # === rang_referentiel_spatial (360 lignes attendues) =====================
    lignes_spatial: list[dict[str, object]] = []
    cibles_spatial: dict[int, CibleConfiance] = {}
    for annee in range(ANNEE_KUMA_DEBUT, ANNEE_KUMA_FIN + 1):
        for mois in range(1, 13):
            valeurs_par_loc: dict[int, float] = {}
            for loc_id, kuma_mens in kuma_par_localite.items():
                valeur_loc = kuma_mens.get((annee, mois))
                if valeur_loc is not None:
                    valeurs_par_loc[loc_id] = valeur_loc
            if len(valeurs_par_loc) != N_VILLES_KUMA:
                continue
            rangs = _calcul_rang_spatial(valeurs_par_loc)
            # Un rang dépend des valeurs de tout le pool ce mois-là.
            niveaux_pool = set().union(
                *(niveaux_kuma[loc].du_mois(annee, mois) for loc in valeurs_par_loc)
            )
            for loc_id, rang in rangs.items():
                serie_id = serie_id_par_grandeur_localite[(GRANDEUR_RANG_SPATIAL, loc_id)]
                if serie_id not in cibles_spatial:
                    cibles_spatial[serie_id] = lire_cible(session, serie_id)
                lignes_spatial.append(
                    {
                        "grandeur_code": GRANDEUR_RANG_SPATIAL,
                        "localite_id": loc_id,
                        "series_metadonnees_id": serie_id,
                        "periode_type": "mensuel",
                        "annee_debut": annee,
                        "annee_fin": annee,
                        "mois": mois,
                        "version_formule": VERSION_FORMULE_1_7B,
                        "valeur": float(rang),
                        "niveau_confiance_derive": _niveau_derive(
                            cibles_spatial[serie_id], niveaux_pool
                        ),
                    }
                )

    inserer_lignes_grandeurs_metier(session, lignes_spatial)
    nb_rang_spatial += len(lignes_spatial)

    session.flush()

    return {
        "nb_ecart_insere": nb_ecart,
        "nb_rang_temporel_insere": nb_rang_temporel,
        "nb_rang_spatial_insere": nb_rang_spatial,
        "nb_total": nb_ecart + nb_rang_temporel + nb_rang_spatial,
    }


# === Recalcul de ecart_relatif avec seuil =================================


def _calcul_ecart_relatif_avec_seuil(
    valeur_kuma: float,
    valeur_sarah3: float,
    seuil_sarah3_min: float,
) -> float | None:
    """Écart relatif signé, ou ``None`` si SARAH-3 < seuil (kWh/m²/jour).

    Distinct de :func:`_calcul_ecart_relatif` pour ne pas changer le calcul
    historique de :func:`calculer_et_inserer_referentiels`.
    """
    if valeur_sarah3 < seuil_sarah3_min:
        return None
    return (valeur_kuma - valeur_sarah3) / valeur_sarah3 * 100.0


def _decouvrir_contextes_villes_depuis_db(session: Session) -> list[ContexteVille]:
    """Contextes, lus dans ``series_metadonnees``, des localités GHI NASA POWER + SARAH-3.

    ``RuntimeError`` s'il n'y en a pas exactement ``N_VILLES_KUMA``.
    """
    rows = session.execute(
        text(
            """
            SELECT
                sm.localite_id,
                MAX(CASE WHEN s.code = 'nasa_power'
                         AND sm.grandeur_code = 'ghi'
                         AND sm.periode_debut = '2021-01-01'
                         AND sm.periode_fin = '2025-12-31'
                    THEN sm.code END) AS code_kuma_daily,
                MAX(CASE WHEN s.code = 'sarah3_monthly'
                         AND sm.grandeur_code = 'ghi'
                    THEN sm.code END) AS code_sarah3,
                MAX(CASE WHEN s.code = 'nasa_power'
                         AND sm.grandeur_code = 'ghi'
                         AND sm.periode_debut = '1991-01-01'
                         AND sm.periode_fin = '2020-12-31'
                    THEN sm.code END) AS code_power_climato
            FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            WHERE sm.grandeur_code = 'ghi'
              AND s.code IN ('nasa_power', 'sarah3_monthly')
            GROUP BY sm.localite_id
            HAVING MAX(CASE WHEN s.code = 'sarah3_monthly' THEN 1 ELSE 0 END) = 1
            ORDER BY sm.localite_id
            """
        )
    ).all()
    contextes: list[ContexteVille] = []
    for r in rows:
        if r.code_kuma_daily is None or r.code_sarah3 is None:
            continue
        contextes.append(
            {
                "localite_id": int(r.localite_id),
                "code_serie_kuma_daily": r.code_kuma_daily,
                "code_serie_sarah3": r.code_sarah3,
                "code_serie_power_1991_2020": r.code_power_climato or "",
            }
        )
    if len(contextes) != N_VILLES_KUMA:
        raise RuntimeError(
            f"Recalcul ecart_relatif : {len(contextes)} contextes villes "
            f"trouvés (attendu {N_VILLES_KUMA}). Vérifier le seed des séries "
            f"NASA POWER + SARAH-3."
        )
    return contextes


def _resoudre_serie_id_ecart_par_localite(session: Session) -> dict[int, int]:
    """``{localite_id: serie_id}`` des séries ``ecart_relatif_referentiel`` calculées."""
    rows = session.execute(
        text(
            """
            SELECT sm.localite_id, sm.id AS serie_id
            FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            WHERE sm.grandeur_code = :grandeur
              AND s.code = 'kuma_calculs'
            """
        ),
        {"grandeur": GRANDEUR_ECART},
    ).all()
    return {int(r.localite_id): int(r.serie_id) for r in rows}


def recalculer_ecart_relatif_referentiel(
    *,
    session: Session,
    seuil_sarah3_min: float = SEUIL_SARAH3_MIN_DEFAUT,
) -> tuple[int, int]:
    """Recalcule les 216 lignes d'écart relatif (6 villes x 36 mois) depuis la donnée brute.

    Un mois où SARAH-3 < ``seuil_sarah3_min`` est inséré avec ``valeur = NULL``
    plutôt qu'amplifié par une division quasi nulle. Renvoie
    ``(nb_lignes_inserees, nb_lignes_null)`` ; l'appelant commit.
    """
    contextes = _decouvrir_contextes_villes_depuis_db(session)
    serie_id_par_loc = _resoudre_serie_id_ecart_par_localite(session)

    nb_total = 0
    nb_null = 0

    for ctx in contextes:
        loc_id = ctx["localite_id"]
        niveaux = NiveauxEntrees()
        kuma_mens = _lire_kuma_mensuel(session, ctx["code_serie_kuma_daily"], niveaux)
        sarah3_mens = _lire_mensuel(session, ctx["code_serie_sarah3"], niveaux)
        serie_id = serie_id_par_loc.get(loc_id)
        if serie_id is None:
            # Garde défensive : chaque localité doit avoir sa série d'écart.
            continue
        cible = lire_cible(session, serie_id)

        lignes: list[dict[str, object]] = []
        for annee in range(ANNEE_KUMA_DEBUT, ANNEE_SARAH3_FIN + 1):
            for mois in range(1, 13):
                kuma_v = kuma_mens.get((annee, mois))
                sarah3_v = sarah3_mens.get((annee, mois))
                if kuma_v is None or sarah3_v is None:
                    continue
                ecart_pct = _calcul_ecart_relatif_avec_seuil(kuma_v, sarah3_v, seuil_sarah3_min)
                if ecart_pct is None:
                    nb_null += 1
                lignes.append(
                    {
                        "grandeur_code": GRANDEUR_ECART,
                        "localite_id": loc_id,
                        "series_metadonnees_id": serie_id,
                        "periode_type": "mensuel",
                        "annee_debut": annee,
                        "annee_fin": annee,
                        "mois": mois,
                        "version_formule": VERSION_FORMULE_1_7B,
                        "valeur": ecart_pct,
                        "niveau_confiance_derive": _niveau_derive(
                            cible, niveaux.du_mois(annee, mois)
                        ),
                    }
                )
        inserer_lignes_grandeurs_metier(session, lignes)
        nb_total += len(lignes)

    session.flush()
    return nb_total, nb_null


# === Atlas : écart inter-source ===========================================


class ContexteEcartInterSource(TypedDict):
    """Séries d'une localité pour l'écart inter-source (SARAH-3 pour le GHI, CAMS pour le DNI)."""

    localite_id: int
    code_serie_nasa_daily: str
    code_serie_reference: str
    series_metadonnees_id: int


def calculer_et_inserer_ecart_inter_source(
    *,
    session: Session,
    contextes: Sequence[ContexteEcartInterSource],
    grandeur_code: str,
    annee_debut: int,
    annee_fin: int,
    seuil_reference_min: float = SEUIL_SARAH3_MIN_DEFAUT,
) -> tuple[int, int]:
    """Écart mensuel signé ``(nasa - ref) / ref * 100``, NASA journalier agrégé au mois.

    GHI contre SARAH-3 (``ecart_relatif_referentiel``), DNI contre CAMS
    (``ecart_relatif_dni_cams``), mêmes helpers que l'orchestrateur. Référence
    < seuil -> NULL. Renvoie ``(nb_lignes_inserees, nb_lignes_null)``.
    """
    nb_total = 0
    nb_null = 0
    for ctx in contextes:
        niveaux = NiveauxEntrees()
        nasa = _lire_kuma_mensuel(session, ctx["code_serie_nasa_daily"], niveaux)
        reference = _lire_mensuel(session, ctx["code_serie_reference"], niveaux)
        cible = lire_cible(session, ctx["series_metadonnees_id"])

        lignes: list[dict[str, object]] = []
        for annee in range(annee_debut, annee_fin + 1):
            for mois in range(1, 13):
                valeur_nasa = nasa.get((annee, mois))
                valeur_ref = reference.get((annee, mois))
                if valeur_nasa is None or valeur_ref is None:
                    continue
                ecart = _calcul_ecart_relatif_avec_seuil(
                    valeur_nasa, valeur_ref, seuil_reference_min
                )
                if ecart is None:
                    nb_null += 1
                lignes.append(
                    {
                        "grandeur_code": grandeur_code,
                        "localite_id": ctx["localite_id"],
                        "series_metadonnees_id": ctx["series_metadonnees_id"],
                        "periode_type": "mensuel",
                        "annee_debut": annee,
                        "annee_fin": annee,
                        "mois": mois,
                        "version_formule": VERSION_FORMULE_1_7B,
                        "valeur": ecart,
                        "niveau_confiance_derive": _niveau_derive(
                            cible, niveaux.du_mois(annee, mois)
                        ),
                    }
                )
        inserer_lignes_grandeurs_metier(session, lignes)
        nb_total += len(lignes)

    session.flush()
    return nb_total, nb_null


# === Rang temporel seul ===================================================


class ContexteRangTemporel(TypedDict):
    """Séries d'une localité pour le rang temporel (climatologie NASA POWER 1991-2020 par mois)."""

    localite_id: int
    code_serie_kuma_daily: str
    code_serie_power_1991_2020: str
    series_metadonnees_id: int


def calculer_et_inserer_rang_temporel(
    *,
    session: Session,
    contextes: Sequence[ContexteRangTemporel],
    grandeur_code: str = GRANDEUR_RANG_TEMPOREL,
    annee_debut: int = ANNEE_KUMA_DEBUT,
    annee_fin: int = ANNEE_KUMA_FIN,
) -> int:
    """Rang temporel seul, sans écart ni rang spatial ; renvoie le nombre de lignes.

    Passer par :func:`calculer_et_inserer_referentiels` réinsérerait aussi un rang
    spatial (version 1, pool de six localités). Même formule que l'orchestrateur.
    """
    nb_total = 0
    for ctx in contextes:
        niveaux_climato = NiveauxEntrees()
        climato = _lire_mensuel(session, ctx["code_serie_power_1991_2020"], niveaux_climato)
        distribution_par_mois: dict[int, list[float]] = {m: [] for m in range(1, 13)}
        for (annee_clim, mois_clim), valeur in climato.items():
            if ANNEE_CLIMATO_DEBUT <= annee_clim <= ANNEE_CLIMATO_FIN:
                distribution_par_mois[mois_clim].append(valeur)
        niveaux_kuma = NiveauxEntrees()
        kuma = _lire_kuma_mensuel(session, ctx["code_serie_kuma_daily"], niveaux_kuma)
        cible = lire_cible(session, ctx["series_metadonnees_id"])

        lignes: list[dict[str, object]] = []
        for annee in range(annee_debut, annee_fin + 1):
            for mois in range(1, 13):
                kuma_v = kuma.get((annee, mois))
                distribution = distribution_par_mois.get(mois, [])
                if kuma_v is None or len(distribution) < 2:
                    continue
                percentile = _calcul_rang_temporel(kuma_v, distribution)
                lignes.append(
                    {
                        "grandeur_code": grandeur_code,
                        "localite_id": ctx["localite_id"],
                        "series_metadonnees_id": ctx["series_metadonnees_id"],
                        "periode_type": "mensuel",
                        "annee_debut": annee,
                        "annee_fin": annee,
                        "mois": mois,
                        "version_formule": VERSION_FORMULE_1_7B,
                        "valeur": percentile,
                        "niveau_confiance_derive": _niveau_derive(
                            cible,
                            niveaux_kuma.du_mois(annee, mois)
                            | niveaux_climato.de_periode(
                                ANNEE_CLIMATO_DEBUT, ANNEE_CLIMATO_FIN, mois
                            ),
                        ),
                    }
                )
        inserer_lignes_grandeurs_metier(session, lignes)
        nb_total += len(lignes)

    session.flush()
    return nb_total


# === Rang spatial seul ====================================================


class ContexteRangSpatial(TypedDict):
    """Série GHI journalière d'une localité du pool et sa série de rang spatial."""

    localite_id: int
    code_serie_kuma_daily: str
    series_metadonnees_id: int


def _lignes_rang_spatial(
    *,
    kuma_par_localite: dict[int, dict[tuple[int, int], float]],
    serie_id_par_localite: dict[int, int],
    annee_debut: int,
    annee_fin: int,
    version_formule: int,
    niveaux_pool: NiveauxEntrees,
    cible_par_localite: dict[int, CibleConfiance],
) -> tuple[list[dict[str, object]], list[tuple[int, int]]]:
    """Lignes de rang 1-N par mois, et mois non classés faute d'une valeur pour chaque localité.

    Ex-aequo départagés par l'ordre d'insertion de ``kuma_par_localite``
    (:func:`_calcul_rang_spatial`). Un rang dépend des valeurs de tout le pool :
    il prend le niveau des entrées du pool pour son mois (``niveaux_pool``).
    """
    lignes: list[dict[str, object]] = []
    mois_non_classes: list[tuple[int, int]] = []
    for annee in range(annee_debut, annee_fin + 1):
        for mois in range(1, 13):
            valeurs = {
                loc_id: kuma_mens[(annee, mois)]
                for loc_id, kuma_mens in kuma_par_localite.items()
                if (annee, mois) in kuma_mens
            }
            if len(valeurs) != len(kuma_par_localite):
                mois_non_classes.append((annee, mois))
                continue
            niveaux_mois = niveaux_pool.du_mois(annee, mois)
            for loc_id, rang in _calcul_rang_spatial(valeurs).items():
                lignes.append(
                    {
                        "grandeur_code": GRANDEUR_RANG_SPATIAL,
                        "localite_id": loc_id,
                        "series_metadonnees_id": serie_id_par_localite[loc_id],
                        "periode_type": "mensuel",
                        "annee_debut": annee,
                        "annee_fin": annee,
                        "mois": mois,
                        "version_formule": version_formule,
                        "valeur": float(rang),
                        "niveau_confiance_derive": _niveau_derive(
                            cible_par_localite[loc_id], niveaux_mois
                        ),
                    }
                )
    return lignes, mois_non_classes


def calculer_et_inserer_rang_spatial(
    *,
    session: Session,
    contextes: Sequence[ContexteRangSpatial],
    version_formule: int,
    annee_debut: int = ANNEE_KUMA_DEBUT,
    annee_fin: int = ANNEE_KUMA_FIN,
    valide_du: datetime | None = None,
) -> tuple[int, list[tuple[int, int]]]:
    """Rang spatial sur le pool ``contextes`` (flush, sans commit).

    Un mois n'est classé que si chaque localité du pool a une valeur. Les
    ex-aequo sont départagés par l'ordre de ``contextes``. ``valide_du`` (défaut
    ``now()``) date aussi ``cree_le`` et ``modifie_le``, pour enchaîner sur la
    clôture d'une version antérieure au même instant. Renvoie
    ``(nb_lignes_inserees, mois_non_classes)`` ; ``RuntimeError`` si
    ``version_formule`` diffère du référentiel ou si une localité est en double.
    """
    verifier_version_formule(session, GRANDEUR_RANG_SPATIAL, version_formule)
    if len({ctx["localite_id"] for ctx in contextes}) != len(contextes):
        raise RuntimeError("Rang spatial : localite en double dans le pool.")

    niveaux_pool = NiveauxEntrees()
    kuma_par_localite = {
        ctx["localite_id"]: _lire_kuma_mensuel(session, ctx["code_serie_kuma_daily"], niveaux_pool)
        for ctx in contextes
    }
    lignes, mois_non_classes = _lignes_rang_spatial(
        kuma_par_localite=kuma_par_localite,
        serie_id_par_localite={
            ctx["localite_id"]: ctx["series_metadonnees_id"] for ctx in contextes
        },
        annee_debut=annee_debut,
        annee_fin=annee_fin,
        version_formule=version_formule,
        niveaux_pool=niveaux_pool,
        cible_par_localite={
            ctx["localite_id"]: lire_cible(session, ctx["series_metadonnees_id"])
            for ctx in contextes
        },
    )
    if lignes:
        session.execute(
            text(
                """
                INSERT INTO grandeurs_metier
                    (grandeur_code, localite_id, series_metadonnees_id,
                     periode_type, annee_debut, annee_fin, mois,
                     version_formule, valeur, niveau_confiance_derive,
                     valide_du, cree_le, modifie_le)
                VALUES
                    (:grandeur_code, :localite_id, :series_metadonnees_id,
                     :periode_type, :annee_debut, :annee_fin, :mois,
                     :version_formule, :valeur, :niveau_confiance_derive,
                     COALESCE(CAST(:valide_du AS timestamptz), now()),
                     COALESCE(CAST(:valide_du AS timestamptz), now()),
                     COALESCE(CAST(:valide_du AS timestamptz), now()))
                """
            ),
            [{**ligne, "valide_du": valide_du} for ligne in lignes],
        )
    session.flush()
    return len(lignes), mois_non_classes

"""Grandeurs F1 de comparaison à des référentiels (écart inter-source, rangs).

- ``ecart_relatif_referentiel`` : écart entre NASA POWER (journalier, moyenné
  par mois depuis ``mesures_ressource``) et PVGIS-SARAH3 ICDR (lu dans
  ``mesures_ressource_mensuelles``), sur le chevauchement 2021-2023.
- ``rang_referentiel_temporel`` : percentile de la valeur 2021-2025 dans la
  climatologie NASA POWER 1991-2020 du même mois calendaire (n = 30).
- ``rang_referentiel_spatial`` : rang ordinal de la valeur parmi les 6 villes
  de référence pour le même mois.

Niveau de confiance uniforme B : l'écart combine deux sources (signal
indirect) ; pour le rang temporel, la validation publique du quantile mapping
NASA POWER est limitée au longwave ; le rang spatial ne porte que sur 6 villes.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypedDict

from sqlalchemy import text
from sqlalchemy.orm import Session

GRANDEUR_ECART: str = "ecart_relatif_referentiel"
GRANDEUR_RANG_TEMPOREL: str = "rang_referentiel_temporel"
GRANDEUR_RANG_SPATIAL: str = "rang_referentiel_spatial"

NIVEAU_CONFIANCE_DERIVE_1_7B: str = "B"
VERSION_FORMULE_1_7B: int = 1

ANNEE_KUMA_DEBUT: int = 2021
ANNEE_KUMA_FIN: int = 2025
ANNEE_SARAH3_FIN: int = 2023
ANNEE_CLIMATO_DEBUT: int = 1991
ANNEE_CLIMATO_FIN: int = 2020

N_VILLES_KUMA: int = 6

SEUIL_SARAH3_MIN_DEFAUT: float = 0.5
"""Seuil (kWh/m²/jour) sous lequel la valeur mensuelle de référence est jugée
anormale : l'écart relatif n'est pas calculé et la valeur stockée est NULL.

La formule ``(k - s) / s * 100`` diverge quand ``s -> 0``, et un GHI mensuel
inférieur à 0,5 kWh/m²/jour n'est pas physique en Afrique de l'Ouest tropicale
(un ciel couvert en permanence donnerait encore 2 à 3) : il signale un défaut
amont (sentinelle non nettoyée, erreur d'unité à l'ingestion).
"""


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


def _agreger_mensuel(valeurs_journalieres: Sequence[float]) -> float:
    """Moyenne arithmétique ; lève ``ValueError`` si la séquence est vide."""
    if not valeurs_journalieres:
        raise ValueError("Aucune valeur journaliere a agreger")
    return sum(valeurs_journalieres) / len(valeurs_journalieres)


def _calcul_ecart_relatif(valeur_kuma: float, valeur_sarah3: float) -> float:
    """Écart relatif signé en pourcent : ``(kuma - sarah3) / sarah3 * 100``.

    Lève ``ValueError`` si ``valeur_sarah3`` est nulle.
    """
    if valeur_sarah3 == 0.0:
        raise ValueError("Ecart relatif indefini : valeur SARAH-3 nulle")
    return (valeur_kuma - valeur_sarah3) / valeur_sarah3 * 100.0


def _calcul_rang_temporel(valeur_kuma: float, distribution: Sequence[float]) -> float:
    """Percentile de ``valeur_kuma`` dans la distribution, borné à [0, 100].

    ``p = (rang - 1) / (n - 1) * 100`` avec
    ``rang = nb_inférieurs + (nb_égaux + 1) / 2``. Lève ``ValueError`` si n < 2.
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
    """Rang ordinal 1 à N de chaque localité, par valeur croissante.

    Les ex aequo sont départagés par l'ordre d'insertion du dictionnaire (tri
    stable). Lève ``ValueError`` si le dictionnaire est vide.
    """
    if not valeurs_par_localite:
        raise ValueError("Aucune valeur a classer")
    items_tries = sorted(valeurs_par_localite.items(), key=lambda kv: kv[1])
    return {loc_id: idx + 1 for idx, (loc_id, _) in enumerate(items_tries)}


def _lire_kuma_mensuel(session: Session, code_serie: str) -> dict[tuple[int, int], float]:
    """Moyenne mensuelle des mesures journalières courantes d'une série."""
    rows = session.execute(
        text(
            """
            SELECT
                EXTRACT(YEAR FROM mr.instant_mesure)::int AS annee,
                EXTRACT(MONTH FROM mr.instant_mesure)::int AS mois,
                AVG(mr.valeur) AS moyenne
            FROM mesures_ressource mr
            JOIN series_metadonnees sm ON sm.id = mr.serie_id
            WHERE sm.code = :code
              AND mr.valide_au IS NULL
              AND mr.statut <> 'deprecie'
            GROUP BY annee, mois
            ORDER BY annee, mois
            """
        ),
        {"code": code_serie},
    ).all()
    return {(int(r.annee), int(r.mois)): float(r.moyenne) for r in rows}


def _lire_mensuel(session: Session, code_serie: str) -> dict[tuple[int, int], float]:
    """Lit les valeurs mensuelles d'une série depuis ``mesures_ressource_mensuelles``."""
    rows = session.execute(
        text(
            """
            SELECT m.annee, m.mois, m.valeur
            FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code = :code
              AND m.valide_au IS NULL
              AND m.statut <> 'deprecie'
            ORDER BY m.annee, m.mois
            """
        ),
        {"code": code_serie},
    ).all()
    return {(int(r.annee), int(r.mois)): float(r.valeur) for r in rows}


def _bulk_insert_grandeurs_metier(session: Session, lignes: list[dict[str, object]]) -> None:
    """Insère les lignes dans ``grandeurs_metier`` ; sans effet si la liste est vide."""
    if not lignes:
        return
    session.execute(
        text(
            """
            INSERT INTO grandeurs_metier
                (grandeur_code, localite_id, series_metadonnees_id,
                 periode_type, annee_debut, annee_fin, mois,
                 version_formule, valeur, niveau_confiance_derive)
            VALUES
                (:grandeur_code, :localite_id, :series_metadonnees_id,
                 :periode_type, :annee_debut, :annee_fin, :mois,
                 :version_formule, :valeur, :niveau_confiance_derive)
            """
        ),
        lignes,
    )


def calculer_et_inserer_referentiels(
    *,
    session: Session,
    contextes_villes: Sequence[ContexteVille],
    serie_id_par_grandeur_localite: dict[tuple[str, int], int],
) -> CalculReferentielsResultat:
    """Calcule et insère les trois grandeurs pour les villes fournies.

    ``serie_id_par_grandeur_localite`` associe ``(grandeur_code, localite_id)``
    à la série calculée cible, qui doit déjà exister. Le rang spatial n'est
    calculé que pour les mois où 6 villes ont une valeur. Fait un ``flush``
    sans ``commit``.
    """
    nb_ecart = 0
    nb_rang_temporel = 0
    nb_rang_spatial = 0

    kuma_par_localite: dict[int, dict[tuple[int, int], float]] = {}
    for ctx in contextes_villes:
        loc_id = ctx["localite_id"]
        kuma_par_localite[loc_id] = _lire_kuma_mensuel(session, ctx["code_serie_kuma_daily"])

    # Écart relatif : 2021-2023, années communes avec SARAH-3.
    for ctx in contextes_villes:
        loc_id = ctx["localite_id"]
        sarah3 = _lire_mensuel(session, ctx["code_serie_sarah3"])
        serie_id = serie_id_par_grandeur_localite[(GRANDEUR_ECART, loc_id)]

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
                        "niveau_confiance_derive": NIVEAU_CONFIANCE_DERIVE_1_7B,
                    }
                )
        _bulk_insert_grandeurs_metier(session, lignes)
        nb_ecart += len(lignes)

    # Rang temporel : distribution 1991-2020 du même mois calendaire.
    for ctx in contextes_villes:
        loc_id = ctx["localite_id"]
        climato = _lire_mensuel(session, ctx["code_serie_power_1991_2020"])

        distribution_par_mois: dict[int, list[float]] = {m: [] for m in range(1, 13)}
        for (annee_clim, mois_clim), valeur in climato.items():
            if ANNEE_CLIMATO_DEBUT <= annee_clim <= ANNEE_CLIMATO_FIN:
                distribution_par_mois[mois_clim].append(valeur)

        serie_id = serie_id_par_grandeur_localite[(GRANDEUR_RANG_TEMPOREL, loc_id)]

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
                        "niveau_confiance_derive": NIVEAU_CONFIANCE_DERIVE_1_7B,
                    }
                )
        _bulk_insert_grandeurs_metier(session, lignes)
        nb_rang_temporel += len(lignes)

    # Rang spatial : seulement les mois où les 6 villes ont une valeur.
    lignes_spatial: list[dict[str, object]] = []
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
            for loc_id, rang in rangs.items():
                serie_id = serie_id_par_grandeur_localite[(GRANDEUR_RANG_SPATIAL, loc_id)]
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
                        "niveau_confiance_derive": NIVEAU_CONFIANCE_DERIVE_1_7B,
                    }
                )

    _bulk_insert_grandeurs_metier(session, lignes_spatial)
    nb_rang_spatial += len(lignes_spatial)

    session.flush()

    return {
        "nb_ecart_insere": nb_ecart,
        "nb_rang_temporel_insere": nb_rang_temporel,
        "nb_rang_spatial_insere": nb_rang_spatial,
        "nb_total": nb_ecart + nb_rang_temporel + nb_rang_spatial,
    }


def _calcul_ecart_relatif_avec_seuil(
    valeur_kuma: float,
    valeur_sarah3: float,
    seuil_sarah3_min: float,
) -> float | None:
    """Écart relatif signé en pourcent, ou ``None`` si la référence est sous le seuil.

    Même formule que :func:`_calcul_ecart_relatif`, valeurs et seuil en
    kWh/m²/jour. Fonction distincte pour laisser inchangé le calcul de
    :func:`calculer_et_inserer_referentiels`.
    """
    if valeur_sarah3 < seuil_sarah3_min:
        return None
    return (valeur_kuma - valeur_sarah3) / valeur_sarah3 * 100.0


def _decouvrir_contextes_villes_depuis_db(session: Session) -> list[ContexteVille]:
    """Reconstruit depuis ``series_metadonnees`` les contextes des 6 villes.

    Retient les localités ayant une série GHI ``sarah3_monthly`` et une série
    GHI ``nasa_power`` 2021-2025. Lève ``RuntimeError`` si l'on n'en trouve pas
    exactement 6.
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
    """Renvoie ``{localite_id: series_metadonnees.id}`` des séries
    ``ecart_relatif_referentiel`` de la source ``kuma_calculs``.
    """
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
    """Recalcule ``ecart_relatif_referentiel`` depuis les mesures sources.

    Relit ``mesures_ressource`` (NASA POWER, moyenné par mois) et
    ``mesures_ressource_mensuelles`` (SARAH-3) pour 2021-2023. Quand SARAH-3
    est sous ``seuil_sarah3_min`` (kWh/m²/jour), la ligne est insérée avec
    ``valeur = NULL`` : ``grandeurs_metier.valeur`` doit donc être nullable.
    N'efface pas les lignes existantes.

    Renvoie ``(nb_lignes_inserees, nb_lignes_null)`` ; ``flush`` sans ``commit``.
    """
    contextes = _decouvrir_contextes_villes_depuis_db(session)
    serie_id_par_loc = _resoudre_serie_id_ecart_par_localite(session)

    nb_total = 0
    nb_null = 0

    for ctx in contextes:
        loc_id = ctx["localite_id"]
        kuma_mens = _lire_kuma_mensuel(session, ctx["code_serie_kuma_daily"])
        sarah3_mens = _lire_mensuel(session, ctx["code_serie_sarah3"])
        serie_id = serie_id_par_loc.get(loc_id)
        if serie_id is None:
            # Localité sans série ecart_relatif_referentiel : ignorée.
            continue

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
                        "niveau_confiance_derive": NIVEAU_CONFIANCE_DERIVE_1_7B,
                    }
                )
        _bulk_insert_grandeurs_metier(session, lignes)
        nb_total += len(lignes)

    session.flush()
    return nb_total, nb_null


class ContexteEcartInterSource(TypedDict):
    """Contexte par localité pour l'écart inter-source de l'atlas.

    NASA daily (agrégé mensuel à la volée) vs une référence mensuelle (SARAH-3
    pour le GHI, CAMS pour le DNI), sur la fenêtre commune.
    """

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
    niveau_confiance: str = NIVEAU_CONFIANCE_DERIVE_1_7B,
) -> tuple[int, int]:
    """Calcule et insère l'écart entre NASA journalier moyenné et une référence mensuelle.

    GHI : NASA contre SARAH-3 (``ecart_relatif_referentiel``) ; DNI : NASA
    contre CAMS (``ecart_relatif_dni_cams``). La valeur stockée est signée,
    ``(nasa - ref) / ref * 100`` ; elle mesure un désaccord entre sources, pas
    une correction de biais. Sous ``seuil_reference_min``, la valeur est NULL.

    Renvoie ``(nb_lignes_inserees, nb_lignes_null)`` ; ``flush`` sans ``commit``.
    """
    nb_total = 0
    nb_null = 0
    for ctx in contextes:
        nasa = _lire_kuma_mensuel(session, ctx["code_serie_nasa_daily"])
        reference = _lire_mensuel(session, ctx["code_serie_reference"])

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
                        "niveau_confiance_derive": niveau_confiance,
                    }
                )
        _bulk_insert_grandeurs_metier(session, lignes)
        nb_total += len(lignes)

    session.flush()
    return nb_total, nb_null


class ContexteRangTemporel(TypedDict):
    """Contexte par localité pour le rang temporel focalisé.

    Percentile de la valeur Kuma (NASA daily agrégé mensuel à la volée) dans la
    climatologie NASA POWER 1991-2020 stratifiée par mois calendrier.
    """

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
    niveau_confiance: str = NIVEAU_CONFIANCE_DERIVE_1_7B,
) -> int:
    """Calcule et insère le seul ``rang_referentiel_temporel``.

    Permet d'étendre le rang temporel à d'autres localités sans passer par
    :func:`calculer_et_inserer_referentiels`, qui calcule aussi l'écart et le
    rang spatial, défini sur un ensemble fixe de 6 villes. Même formule
    (``_calcul_rang_temporel``). Renvoie le nombre de lignes insérées ;
    ``flush`` sans ``commit``.
    """
    nb_total = 0
    for ctx in contextes:
        climato = _lire_mensuel(session, ctx["code_serie_power_1991_2020"])
        distribution_par_mois: dict[int, list[float]] = {m: [] for m in range(1, 13)}
        for (annee_clim, mois_clim), valeur in climato.items():
            if ANNEE_CLIMATO_DEBUT <= annee_clim <= ANNEE_CLIMATO_FIN:
                distribution_par_mois[mois_clim].append(valeur)
        kuma = _lire_kuma_mensuel(session, ctx["code_serie_kuma_daily"])

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
                        "niveau_confiance_derive": niveau_confiance,
                    }
                )
        _bulk_insert_grandeurs_metier(session, lignes)
        nb_total += len(lignes)

    session.flush()
    return nb_total

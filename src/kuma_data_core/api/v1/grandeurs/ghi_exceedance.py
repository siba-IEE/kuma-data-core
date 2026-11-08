"""Exceedance inter-annuelle P50 / P90 de l'irradiation annuelle (``ghi_exceedance``)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.schemas.grandeurs import ReponseGhiExceedance
from kuma_data_core.db.session import obtenir_session
from kuma_data_core.editorial.niveaux_confiance import (
    NiveauxEntrees,
    propager_niveau_confiance,
)
from kuma_data_core.editorial.statuts import filtre_mesure_utilisable
from kuma_data_core.services.grandeurs.ghi_exceedance import (
    ANNEE_DEBUT_CLIMATOLOGIE,
    ANNEE_FIN_CLIMATOLOGIE,
    METHODE_PERCENTILE,
    NOMBRE_ANNEES_BASE,
    PAIRES_COLOCALISEES_D29,
    UNITE_GHI_EXCEEDANCE,
    calculer_ghi_exceedance,
    calculer_totaux_annuels,
)
from kuma_data_core.services.grandeurs.ghi_exceedance import (
    PLAFOND_CONFIANCE as PLAFOND_GHI_EXCEEDANCE,
)

routeur = APIRouter()


def _resoudre_serie_ghi_mensuelle_1991_2020(
    session: Session, code_localite: str
) -> tuple[int, str]:
    """Résout (serie_id, code_serie) de la série GHI mensuelle 1991-2020 d'une ville.

    Cherche dans ``series_metadonnees`` la série active de la localité
    ciblée avec ``grandeur_code = 'ghi'``, ``source.code = 'nasa_power'``
    et ``periode_debut`` dans la fenêtre climatologique. Cette série est
    seedée en migration 041 (NASA POWER 1991-2020).

    Raises:
        ExceptionKuma : HTTP 404 ``RESSOURCE_INCONNUE`` si la localité
            n'est pas trouvée ou si aucune série GHI mensuelle 1991-2020
            n'est rattachée (code de localité inconnu ou hors couverture).
    """
    row = session.execute(
        text(
            """
            SELECT sm.id AS serie_id, sm.code AS code_serie
            FROM series_metadonnees sm
            JOIN localites l ON l.id = sm.localite_id
            JOIN sources s ON s.id = sm.source_id
            WHERE l.code = :code_localite
              AND sm.grandeur_code = 'ghi'
              AND s.code = 'nasa_power'
              AND EXTRACT(YEAR FROM sm.periode_debut) = :annee_debut
              AND sm.actif = TRUE
            LIMIT 1
            """
        ),
        {"code_localite": code_localite, "annee_debut": ANNEE_DEBUT_CLIMATOLOGIE},
    ).first()
    if row is None:
        raise ExceptionKuma(
            code=CodeErreur.RESSOURCE_LOCALITE_INCONNUE,
            message=(
                f"Aucune serie GHI mensuelle {ANNEE_DEBUT_CLIMATOLOGIE}-"
                f"{ANNEE_FIN_CLIMATOLOGIE} trouvee pour la localite "
                f"{code_localite!r}. La grandeur ghi_exceedance n'est "
                f"disponible que pour les localites dotees d'une serie GHI "
                f"mensuelle NASA POWER {ANNEE_DEBUT_CLIMATOLOGIE}-"
                f"{ANNEE_FIN_CLIMATOLOGIE}."
            ),
            statut_http=status.HTTP_404_NOT_FOUND,
        )
    return int(row.serie_id), str(row.code_serie)


def _lire_mensuelles_brutes(
    session: Session, serie_id: int, *, niveaux: NiveauxEntrees
) -> list[tuple[int, int, float]]:
    """Lit les 360 mesures mensuelles courantes d'une série sous forme de tuples.

    Renvoie une liste de tuples ``(annee, mois, valeur)`` ordonnés
    chronologiquement. Mesures utilisables seulement (courantes, non
    dépréciées). Pas de pagination : on charge tout (360 lignes attendues
    pour une série 1991-2020 complète). Range le niveau effectif de chaque
    valeur lue dans ``niveaux``.
    """
    rows = session.execute(
        text(
            f"""
            SELECT annee, mois, valeur,
                   coalesce(niveau_confiance_override, niveau_confiance_derive) AS niveau
            FROM mesures_ressource_mensuelles
            WHERE serie_id = :serie_id AND {filtre_mesure_utilisable()}
            ORDER BY annee, mois
            """
        ),
        {"serie_id": serie_id},
    ).all()
    for r in rows:
        niveaux.ajouter((int(r.annee), int(r.mois)), r.niveau)
    return [(int(r.annee), int(r.mois), float(r.valeur)) for r in rows]


def _construire_limite_ghi_exceedance(code_localite: str) -> str:
    """Compose le champ ``limite`` de la réponse, enrichi le cas échéant.

    Le texte de base avertit que la valeur est inter-annuelle uniquement
    (et non un P90 bancable complet). Pour les villes co-localisées dans
    le même pixel CERES SYN1deg (Kindia / Mamou), une mention
    explicite de l'identité avec la ville jumelle est ajoutée.
    """
    base = (
        "Exceedance inter-annuelle uniquement (variabilite annee a annee sur "
        f"{NOMBRE_ANNEES_BASE} ans). Ne propage pas l'incertitude de modele "
        "satellitaire NASA POWER : ce n'est pas un P90 bancable complet "
        "(qui necessiterait un modele d'erreur explicite, type PRUVE, et "
        "idealement une calibration sol)."
    )
    jumelle = PAIRES_COLOCALISEES_D29.get(code_localite)
    if jumelle is not None:
        base += (
            f" Co-localisation : cette localite et {jumelle!r} tombent dans le meme "
            f"pixel CERES SYN1deg NASA POWER (110 km a 10 deg N) ; leurs "
            f"series GHI mensuelles 1991-2020 sont strictement identiques "
            f"et leurs P50 / P90 le sont donc aussi."
        )
    return base


@routeur.get(
    "/ghi_exceedance/{code_localite}",
    response_model=ReponseGhiExceedance,
    status_code=status.HTTP_200_OK,
    summary="Exceedance inter-annuelle P50 / P90 de l'irradiation annuelle (GHI)",
    tags=["grandeurs-F1"],
)
def grandeur_ghi_exceedance(
    code_localite: str,
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> ReponseGhiExceedance:
    """Calcule à la volée P50 et P90 de l'irradiation annuelle d'une ville.

    Pipeline :

    1. Résolution de la série GHI mensuelle 1991-2020 de la localité
       (404 ``RESSOURCE_INCONNUE`` si la ville n'est pas couverte).
    2. Lecture des 360 mesures mensuelles courantes (kWh/m²/jour).
    3. Calcul des totaux annuels (kWh/m²/an) par pondération
       journalière ``calendar.monthrange`` (années bissextiles incluses).
    4. Percentiles P50 (médiane) et P90 (= percentile 10, scénario
       conservateur). P90 < P50 par construction.
    5. Construction de la réponse avec champ ``limite`` enrichi pour
       les villes co-localisées Kindia / Mamou.
    """
    niveaux = NiveauxEntrees()
    serie_id, code_serie = _resoudre_serie_ghi_mensuelle_1991_2020(session, code_localite)
    mensuelles = _lire_mensuelles_brutes(session, serie_id, niveaux=niveaux)
    totaux_par_annee = calculer_totaux_annuels(mensuelles)
    resultat = calculer_ghi_exceedance(list(totaux_par_annee.values()))
    return ReponseGhiExceedance(
        code_localite=code_localite,
        code_serie_source=code_serie,
        periode=f"{ANNEE_DEBUT_CLIMATOLOGIE}-{ANNEE_FIN_CLIMATOLOGIE}",
        base_annees=len(totaux_par_annee),
        p50=resultat.p50,
        p90=resultat.p90,
        unite=UNITE_GHI_EXCEEDANCE,
        methode_percentile=METHODE_PERCENTILE,
        niveau_confiance=propager_niveau_confiance(niveaux.tous(), plafond=PLAFOND_GHI_EXCEEDANCE),
        limite=_construire_limite_ghi_exceedance(code_localite),
    )

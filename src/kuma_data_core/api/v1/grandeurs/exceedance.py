"""P50 et P90 de l'irradiation annuelle (GHI) d'une localité."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.schemas.grandeurs import ReponseGhiExceedance
from kuma_data_core.db.session import obtenir_session
from kuma_data_core.editorial.niveaux_confiance import NiveauxEntrees, propager_niveau_confiance
from kuma_data_core.lecture.mesures import lire_serie_mensuelle_entiere
from kuma_data_core.lecture.series import SerieIdentifiee, chercher_serie_ghi_nasa_power
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
) -> SerieIdentifiee:
    """``(serie_id, code_serie)`` de la série GHI NASA POWER de la localité débutant en 1991.

    Lève 404 ``RESSOURCE_LOCALITE_INCONNUE`` si aucune n'est rattachée à la
    localité (ou si la localité n'existe pas).
    """
    serie = chercher_serie_ghi_nasa_power(session, code_localite, ANNEE_DEBUT_CLIMATOLOGIE)
    if serie is None:
        raise ExceptionKuma(
            code=CodeErreur.RESSOURCE_LOCALITE_INCONNUE,
            message=(
                f"Aucune série GHI mensuelle {ANNEE_DEBUT_CLIMATOLOGIE}-"
                f"{ANNEE_FIN_CLIMATOLOGIE} n'est rattachée à la localité "
                f"{code_localite!r}."
            ),
            statut_http=status.HTTP_404_NOT_FOUND,
        )
    return serie


def _construire_limite_ghi_exceedance(code_localite: str) -> str:
    """Champ ``limite`` de la réponse.

    Nomme la localité jumelle quand deux localités tombent dans la même cellule
    CERES SYN1deg et ont donc les mêmes P50 et P90.
    """
    base = (
        "Exceedance inter-annuelle uniquement (variabilité d'une année à l'autre sur "
        f"{NOMBRE_ANNEES_BASE} ans). Ne propage pas l'incertitude du modèle "
        "satellitaire NASA POWER : ce n'est pas un P90 bancable complet "
        "(qui nécessiterait un modèle d'erreur explicite, de type PRUVE, et "
        "idéalement un calage sur des mesures au sol)."
    )
    jumelle = PAIRES_COLOCALISEES_D29.get(code_localite)
    if jumelle is not None:
        base += (
            f" Cette localité et {jumelle!r} tombent dans la même cellule de la "
            f"grille CERES SYN1deg de NASA POWER (environ 110 km de côté) : leurs "
            f"séries GHI mensuelles 1991-2020 sont strictement identiques, "
            f"et leurs P50 et P90 aussi."
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
    """P50 et P90 de l'irradiation annuelle (GHI) d'une localité, calculés à chaque appel.

    La route lit la série GHI mensuelle 1991-2020 NASA POWER de la localité, en
    tire les totaux annuels (kWh/m²/an, années bissextiles comprises), puis
    leurs percentiles : P50 est la médiane, P90 la valeur dépassée neuf années
    sur dix (10e percentile), donc inférieure à P50. 404
    ``RESSOURCE_LOCALITE_INCONNUE`` si aucune série de ce type n'est rattachée à
    la localité.

    Le champ ``limite`` rappelle que seule la variabilité d'une année à l'autre
    est prise en compte ; il signale aussi le cas de deux localités situées dans
    la même cellule de la source, dont les valeurs sont identiques.
    """
    niveaux = NiveauxEntrees()
    serie_id, code_serie = _resoudre_serie_ghi_mensuelle_1991_2020(session, code_localite)
    mensuelles = lire_serie_mensuelle_entiere(session, serie_id, niveaux=niveaux)
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

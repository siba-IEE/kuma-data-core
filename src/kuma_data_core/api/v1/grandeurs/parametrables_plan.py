"""Grandeurs paramétrables du plan des modules : POA mono-plan et POA bifacial."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee, parametres_requete
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.grandeurs._commun import (
    _construire_reponse,
    _exiger_grandeur,
    _resoudre_coordonnees,
    _resoudre_serie_source,
)
from kuma_data_core.api.v1.schemas.grandeurs import ParametresBifacial, ParametresPOA
from kuma_data_core.db.session import obtenir_session
from kuma_data_core.editorial.niveaux_confiance import NiveauxEntrees
from kuma_data_core.lecture.mesures import lire_valeurs_horaires, lire_valeurs_journalieres
from kuma_data_core.lecture.series import chercher_serie_albedo_journalier, chercher_serie_compagne
from kuma_data_core.services.grandeurs.poa_bifacial import (
    PLAFOND_CONFIANCE as PLAFOND_POA_BIFACIAL,
)
from kuma_data_core.services.grandeurs.poa_bifacial import (
    MesureHeureBifacial,
    MesureJourBifacial,
    albedo_du_jour,
    calculer_poa_bifacial,
    calculer_poa_bifacial_horaire,
)
from kuma_data_core.services.grandeurs.poa_parametrable import (
    PLAFOND_CONFIANCE as PLAFOND_POA,
)
from kuma_data_core.services.grandeurs.poa_parametrable import (
    MesureHeurePOA,
    MesureJourPOA,
    calculer_poa_parametrable,
    calculer_poa_parametrable_horaire,
)

routeur = APIRouter()


@routeur.get(
    "/poa_parametrable",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="POA paramétrable (modèle Perez 1990 + Liu-Jordan fallback)",
)
def grandeur_poa_parametrable(
    params: Annotated[ParametresPOA, Depends(parametres_requete(ParametresPOA))],
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> Response:
    """Irradiation journalière dans le plan des modules (POA), à partir d'une série GHI.

    La série source doit être une série GHI, sinon la route répond 400
    ``INCOMPATIBILITE_SOURCE_GRANDEUR``. Les séries DNI et DHI de la même
    localité et de la même source sont utilisées quand elles existent : le
    calcul suit alors le modèle de Perez (1990). Sinon, en méthode journalière,
    le DNI et le DHI sont estimés à partir du GHI (corrélation d'Erbs 1982) et
    la transposition est isotrope (Liu-Jordan 1963), ce qui est moins précis
    sous ciel partiellement couvert. La réponse n'indique pas lequel des deux
    modèles a été appliqué.

    Avec ``methode=integration_horaire``, la série source doit être horaire et
    les séries DNI et DHI horaires sont obligatoires (400
    ``VALIDATION_VALEUR_INVALIDE`` sinon).
    """
    niveaux = NiveauxEntrees()
    serie = _resoudre_serie_source(session, params.code_serie_source)
    _exiger_grandeur(serie.grandeur_code, "ghi", params.code_serie_source, "poa_parametrable")

    latitude, longitude = _resoudre_coordonnees(session, serie.localite_id)

    dni_serie_id = chercher_serie_compagne(
        session, serie.localite_id, serie.source_id, "dni", serie.periode_debut, serie.granularite
    )
    dhi_serie_id = chercher_serie_compagne(
        session, serie.localite_id, serie.source_id, "dhi", serie.periode_debut, serie.granularite
    )

    if params.methode == "integration_horaire":
        # Pas de repli Liu-Jordan en horaire : les séries DNI et DHI sont exigées.
        if serie.granularite != "horaire":
            raise ExceptionKuma(
                code=CodeErreur.VALIDATION_VALEUR_INVALIDE,
                message=(
                    "methode='integration_horaire' exige une serie source horaire "
                    f"(granularite='horaire'), mais {params.code_serie_source!r} est de "
                    f"granularite {serie.granularite!r}."
                ),
                statut_http=status.HTTP_400_BAD_REQUEST,
            )
        if dni_serie_id is None or dhi_serie_id is None:
            raise ExceptionKuma(
                code=CodeErreur.VALIDATION_VALEUR_INVALIDE,
                message=(
                    "Le POA horaire (Perez) exige des series compagnes DNI et DHI "
                    f"horaires pour la localite de {params.code_serie_source!r} ; absentes."
                ),
                statut_http=status.HTTP_400_BAD_REQUEST,
            )
        ghi_h = lire_valeurs_horaires(
            session,
            serie.serie_id,
            params.periode_debut,
            params.periode_fin,
            fuseau=serie.fuseau_horaire,
            niveaux=niveaux,
        )
        dni_h = lire_valeurs_horaires(
            session,
            dni_serie_id,
            params.periode_debut,
            params.periode_fin,
            fuseau=serie.fuseau_horaire,
            niveaux=niveaux,
        )
        dhi_h = lire_valeurs_horaires(
            session,
            dhi_serie_id,
            params.periode_debut,
            params.periode_fin,
            fuseau=serie.fuseau_horaire,
            niveaux=niveaux,
        )
        mesures_horaires: list[MesureHeurePOA] = [
            {"instant_mesure": instant, "ghi": ghi, "dni": dni_h[instant], "dhi": dhi_h[instant]}
            for instant, ghi in ghi_h.items()
            if instant in dni_h and instant in dhi_h
        ]
        resultats = calculer_poa_parametrable_horaire(
            mesures=mesures_horaires,
            latitude_deg=latitude,
            longitude_deg=longitude,
            parametres=params,
        )
    else:
        ghi_par_jour = lire_valeurs_journalieres(
            session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        # Sans DNI ou DHI, la fonction de calcul applique le repli Liu-Jordan.
        dni_par_jour: dict[date, float] = (
            lire_valeurs_journalieres(
                session, dni_serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
            )
            if dni_serie_id is not None
            else {}
        )
        dhi_par_jour: dict[date, float] = (
            lire_valeurs_journalieres(
                session, dhi_serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
            )
            if dhi_serie_id is not None
            else {}
        )
        mesures: list[MesureJourPOA] = [
            {
                "instant_mesure": jour,
                "ghi": ghi,
                "dni": dni_par_jour.get(jour),
                "dhi": dhi_par_jour.get(jour),
            }
            for jour, ghi in ghi_par_jour.items()
        ]
        resultats = calculer_poa_parametrable(
            mesures=mesures,
            latitude_deg=latitude,
            longitude_deg=longitude,
            parametres=params,
        )

    return _construire_reponse(
        code_grandeur="poa_parametrable",
        code_serie_source=params.code_serie_source,
        parametres_appliques={
            "inclinaison_deg": params.inclinaison_deg,
            "orientation_deg": params.orientation_deg,
            "albedo_sol": params.albedo_sol,
            "methode": params.methode,
        },
        resultats=resultats,
        format_sortie=params.format_sortie,
        niveaux=niveaux,
        plafond=PLAFOND_POA,
    )


@routeur.get(
    "/poa_bifacial",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="POA bifacial (modèle infinite-sheds row-aware)",
)
def grandeur_poa_bifacial(
    params: Annotated[ParametresBifacial, Depends(parametres_requete(ParametresBifacial))],
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> Response:
    """Irradiation journalière dans le plan des modules d'un champ de rangées bifacial.

    Modèle infinite-sheds : à la différence de ``poa_parametrable`` (plan seul),
    il tient compte des rangées (gcr, hauteur, pas entre rangées) et de la face
    arrière. La série source doit être une série GHI ; les séries DNI et DHI de
    la même localité et de la même source sont obligatoires (400
    ``INCOMPATIBILITE_SOURCE_GRANDEUR`` si l'une manque). L'albédo vient de la
    série journalière ``albedo_surface`` de la même localité et de la même
    source ; les jours où elle n'a pas de valeur, ``albedo_sol`` est utilisé.

    Avec ``methode=integration_horaire``, la série source doit être horaire (400
    ``VALIDATION_VALEUR_INVALIDE`` sinon) et l'albédo du jour vaut pour chacune
    de ses heures.
    """
    niveaux = NiveauxEntrees()
    serie = _resoudre_serie_source(session, params.code_serie_source)
    _exiger_grandeur(serie.grandeur_code, "ghi", params.code_serie_source, "poa_bifacial")
    latitude, longitude = _resoudre_coordonnees(session, serie.localite_id)

    dni_serie_id = chercher_serie_compagne(
        session, serie.localite_id, serie.source_id, "dni", serie.periode_debut, serie.granularite
    )
    dhi_serie_id = chercher_serie_compagne(
        session, serie.localite_id, serie.source_id, "dhi", serie.periode_debut, serie.granularite
    )
    if dni_serie_id is None or dhi_serie_id is None:
        raise ExceptionKuma(
            code=CodeErreur.INCOMPATIBILITE_SOURCE_GRANDEUR,
            message=(
                "Le POA bifacial (infinite-sheds) exige des series compagnes DNI et DHI "
                f"pour la localite de {params.code_serie_source!r} (pas de fallback) ; absentes."
            ),
            statut_http=status.HTTP_400_BAD_REQUEST,
        )

    albedo_serie_id = chercher_serie_albedo_journalier(session, serie.localite_id, serie.source_id)
    albedo_jour: dict[date, float] = (
        lire_valeurs_journalieres(
            session, albedo_serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        if albedo_serie_id is not None
        else {}
    )

    if params.methode == "integration_horaire":
        if serie.granularite != "horaire":
            raise ExceptionKuma(
                code=CodeErreur.VALIDATION_VALEUR_INVALIDE,
                message=(
                    "methode='integration_horaire' exige une serie source horaire "
                    f"(granularite='horaire'), mais {params.code_serie_source!r} est de "
                    f"granularite {serie.granularite!r}."
                ),
                statut_http=status.HTTP_400_BAD_REQUEST,
            )
        ghi_h = lire_valeurs_horaires(
            session,
            serie.serie_id,
            params.periode_debut,
            params.periode_fin,
            fuseau=serie.fuseau_horaire,
            niveaux=niveaux,
        )
        dni_h = lire_valeurs_horaires(
            session,
            dni_serie_id,
            params.periode_debut,
            params.periode_fin,
            fuseau=serie.fuseau_horaire,
            niveaux=niveaux,
        )
        dhi_h = lire_valeurs_horaires(
            session,
            dhi_serie_id,
            params.periode_debut,
            params.periode_fin,
            fuseau=serie.fuseau_horaire,
            niveaux=niveaux,
        )
        mesures_horaires: list[MesureHeureBifacial] = [
            {
                "instant_mesure": instant,
                "ghi": ghi,
                "dni": dni_h[instant],
                "dhi": dhi_h[instant],
                "albedo": albedo_du_jour(albedo_jour, instant.date(), params.albedo_sol),
            }
            for instant, ghi in ghi_h.items()
            if instant in dni_h and instant in dhi_h
        ]
        resultats = calculer_poa_bifacial_horaire(
            mesures=mesures_horaires,
            latitude_deg=latitude,
            longitude_deg=longitude,
            parametres=params,
        )
    else:
        ghi_j = lire_valeurs_journalieres(
            session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        dni_j = lire_valeurs_journalieres(
            session, dni_serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        dhi_j = lire_valeurs_journalieres(
            session, dhi_serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        mesures: list[MesureJourBifacial] = [
            {
                "instant_mesure": jour,
                "ghi": ghi,
                "dni": dni_j[jour],
                "dhi": dhi_j[jour],
                "albedo": albedo_du_jour(albedo_jour, jour, params.albedo_sol),
            }
            for jour, ghi in ghi_j.items()
            if jour in dni_j and jour in dhi_j
        ]
        resultats = calculer_poa_bifacial(
            mesures=mesures,
            latitude_deg=latitude,
            longitude_deg=longitude,
            parametres=params,
        )

    return _construire_reponse(
        code_grandeur="poa_bifacial",
        code_serie_source=params.code_serie_source,
        parametres_appliques={
            "inclinaison_deg": params.inclinaison_deg,
            "orientation_deg": params.orientation_deg,
            "gcr": params.gcr,
            "hauteur_m": params.hauteur_m,
            "pitch_m": params.pitch_m,
            "bifacialite": params.bifacialite,
            "albedo_sol": params.albedo_sol,
            "methode": params.methode,
        },
        resultats=resultats,
        format_sortie=params.format_sortie,
        niveaux=niveaux,
        plafond=PLAFOND_POA_BIFACIAL,
    )

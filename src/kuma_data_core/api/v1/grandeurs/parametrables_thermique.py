"""Grandeurs paramétrables thermiques : énergie utile ECS et degrés-jours de climatisation."""

from __future__ import annotations

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
    _lire_t2m_compagne,
    _resoudre_serie_source,
)
from kuma_data_core.api.v1.schemas.grandeurs import (
    ParametresDegreJourClimatisation,
    ParametresEnergieUtileECS,
)
from kuma_data_core.db.session import obtenir_session
from kuma_data_core.editorial.niveaux_confiance import NiveauxEntrees
from kuma_data_core.lecture.mesures import lire_valeurs_horaires, lire_valeurs_journalieres
from kuma_data_core.lecture.series import chercher_serie_compagne
from kuma_data_core.services.grandeurs.degre_jour_climatisation import (
    PLAFOND_CONFIANCE as PLAFOND_DJC,
)
from kuma_data_core.services.grandeurs.degre_jour_climatisation import (
    MesureHeureTemperature,
    MesureJourTemperature,
    calculer_degre_jour_climatisation,
    calculer_degre_jour_climatisation_horaire,
)
from kuma_data_core.services.grandeurs.energie_utile_ecs import (
    PLAFOND_CONFIANCE as PLAFOND_ECS,
)
from kuma_data_core.services.grandeurs.energie_utile_ecs import (
    MesureHeureECS,
    MesureJourECS,
    calculer_energie_utile_ecs,
    calculer_energie_utile_ecs_horaire,
)

routeur = APIRouter()


@routeur.get(
    "/energie_utile_ecs",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="Énergie utile ECS bord-capteur (Hottel-Whillier-Bliss)",
)
def grandeur_energie_utile_ecs(
    params: Annotated[
        ParametresEnergieUtileECS, Depends(parametres_requete(ParametresEnergieUtileECS))
    ],
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> Response:
    """Énergie utile d'un capteur solaire thermique pour l'eau chaude sanitaire.

    Énergie en sortie de capteur, par l'équation de Hottel-Whillier-Bliss :
    ``eta = eta0 - a1 x dT / G - a2 x dT² / G``, puis ``Q_utile = eta x G``. La
    série source doit être une série GHI. La série T2M de la même localité et de
    la même source est obligatoire, le rendement dépendant de l'écart entre la
    température du fluide et la température ambiante (400
    ``INCOMPATIBILITE_SOURCE_GRANDEUR`` si elle manque).

    Avec ``methode=integration_horaire``, la série source et la série T2M
    doivent être horaires.
    """
    niveaux = NiveauxEntrees()
    serie = _resoudre_serie_source(session, params.code_serie_source)
    _exiger_grandeur(serie.grandeur_code, "ghi", params.code_serie_source, "energie_utile_ecs")

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
        t2m_serie_id = chercher_serie_compagne(
            session,
            serie.localite_id,
            serie.source_id,
            "t2m",
            serie.periode_debut,
            serie.granularite,
        )
        if t2m_serie_id is None:
            raise ExceptionKuma(
                code=CodeErreur.INCOMPATIBILITE_SOURCE_GRANDEUR,
                message=(
                    "Endpoint 'energie_utile_ecs' horaire requiert une serie T2M horaire "
                    f"compagne de {params.code_serie_source!r}. Aucune trouvee."
                ),
                statut_http=status.HTTP_400_BAD_REQUEST,
            )
        ghi_h = lire_valeurs_horaires(
            session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        t2m_h = lire_valeurs_horaires(
            session, t2m_serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        mesures_horaires: list[MesureHeureECS] = [
            {"instant_mesure": instant, "t_amb_degc": t2m_h[instant], "irradiance_w_par_m2": ghi}
            for instant, ghi in ghi_h.items()
            if instant in t2m_h
        ]
        resultats = calculer_energie_utile_ecs_horaire(mesures=mesures_horaires, parametres=params)
        return _construire_reponse(
            code_grandeur="energie_utile_ecs",
            code_serie_source=params.code_serie_source,
            parametres_appliques={
                "rendement_optique_eta0": params.rendement_optique_eta0,
                "pertes_lineaires_a1": params.pertes_lineaires_a1,
                "pertes_quadratiques_a2": params.pertes_quadratiques_a2,
                "temperature_fluide_entree_degc": params.temperature_fluide_entree_degc,
                "methode": params.methode,
            },
            resultats=resultats,
            format_sortie=params.format_sortie,
            niveaux=niveaux,
            plafond=PLAFOND_ECS,
        )

    ghi_par_jour = lire_valeurs_journalieres(
        session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
    )
    t2m_par_jour = _lire_t2m_compagne(
        session,
        serie.localite_id,
        serie.source_id,
        params.code_serie_source,
        "energie_utile_ecs",
        params.periode_debut,
        params.periode_fin,
        serie.periode_debut,
        serie.granularite,
        niveaux=niveaux,
    )

    mesures: list[MesureJourECS] = [
        {
            "instant_mesure": jour,
            "t_amb_degc": t2m_par_jour[jour],
            "irradiance_kwh_par_m2_jour": ghi,
        }
        for jour, ghi in ghi_par_jour.items()
        if jour in t2m_par_jour
    ]
    resultats = calculer_energie_utile_ecs(mesures=mesures, parametres=params)
    return _construire_reponse(
        code_grandeur="energie_utile_ecs",
        code_serie_source=params.code_serie_source,
        parametres_appliques={
            "rendement_optique_eta0": params.rendement_optique_eta0,
            "pertes_lineaires_a1": params.pertes_lineaires_a1,
            "pertes_quadratiques_a2": params.pertes_quadratiques_a2,
            "temperature_fluide_entree_degc": params.temperature_fluide_entree_degc,
            "methode": params.methode,
        },
        resultats=resultats,
        format_sortie=params.format_sortie,
        niveaux=niveaux,
        plafond=PLAFOND_ECS,
    )


@routeur.get(
    "/degre_jour_climatisation",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="Degrés-jours de climatisation (moyenne journalière ou intégration horaire)",
)
def grandeur_degre_jour_climatisation(
    params: Annotated[
        ParametresDegreJourClimatisation,
        Depends(parametres_requete(ParametresDegreJourClimatisation)),
    ],
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> Response:
    """Degrés-jours de climatisation par mois, pour une température de base ``T_b``.

    La série source doit être une série T2M, sinon la route répond 400
    ``INCOMPATIBILITE_SOURCE_GRANDEUR`` ; aucune autre série n'est lue. Les
    résultats sont mensuels (``instant`` au format ``YYYY-MM``) : somme sur le
    mois des écarts positifs à ``T_b``, calculés sur la température moyenne du
    jour (``methode=moyenne_journaliere``) ou heure par heure
    (``methode=integration_horaire``, Erbs 1983, série source horaire exigée).
    """
    niveaux = NiveauxEntrees()
    serie = _resoudre_serie_source(session, params.code_serie_source)
    _exiger_grandeur(
        serie.grandeur_code, "t2m", params.code_serie_source, "degre_jour_climatisation"
    )

    if params.methode == "integration_horaire":
        if serie.granularite != "horaire":
            raise ExceptionKuma(
                code=CodeErreur.VALIDATION_VALEUR_INVALIDE,
                message=(
                    "methode='integration_horaire' exige une serie source horaire "
                    f"(granularite='horaire'), mais {params.code_serie_source!r} est de "
                    f"granularite {serie.granularite!r}. Fournir une serie T2M horaire "
                    "ou utiliser methode='moyenne_journaliere'."
                ),
                statut_http=status.HTTP_400_BAD_REQUEST,
            )
        t2m_par_heure = lire_valeurs_horaires(
            session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        mesures_horaires: list[MesureHeureTemperature] = [
            {"instant_mesure": instant, "t_degc": valeur}
            for instant, valeur in t2m_par_heure.items()
        ]
        resultats = calculer_degre_jour_climatisation_horaire(
            mesures=mesures_horaires, parametres=params
        )
    else:
        t2m_par_jour = lire_valeurs_journalieres(
            session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        mesures: list[MesureJourTemperature] = [
            {"instant_mesure": jour, "t_moy_degc": valeur} for jour, valeur in t2m_par_jour.items()
        ]
        resultats = calculer_degre_jour_climatisation(mesures=mesures, parametres=params)

    return _construire_reponse(
        code_grandeur="degre_jour_climatisation",
        code_serie_source=params.code_serie_source,
        parametres_appliques={
            "base_temperature_degc": params.base_temperature_degc,
            "methode": params.methode,
        },
        resultats=resultats,
        format_sortie=params.format_sortie,
        niveaux=niveaux,
        plafond=PLAFOND_DJC,
    )

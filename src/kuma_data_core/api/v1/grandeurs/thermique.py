"""Grandeurs thermiques : ``energie_utile_ecs`` et ``degre_jour_climatisation``."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from kuma_data_core.api.dependencies import CleApiValidee
from kuma_data_core.api.v1.grandeurs._commun import (
    SerieSourceResolue,
    _construire_reponse,
    _exiger_serie_horaire,
    _lire_ghi_t2m_horaires,
    _lire_ghi_t2m_journaliers,
    _lire_mesures_horaires_par_serie_id,
    _lire_mesures_par_serie_id,
    _resoudre_serie_exigee,
)
from kuma_data_core.api.v1.schemas.grandeurs import (
    ParametresDegreJourClimatisation,
    ParametresEnergieUtileECS,
    ResultatJournalier,
    ResultatMensuel,
)
from kuma_data_core.db.session import obtenir_session
from kuma_data_core.editorial.niveaux_confiance import NiveauxEntrees
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


# === Endpoint énergie utile ECS ===========================================


def _calculer_ecs_horaire(
    session: Session,
    serie: SerieSourceResolue,
    params: ParametresEnergieUtileECS,
    *,
    niveaux: NiveauxEntrees,
) -> list[ResultatJournalier]:
    """Rendement HWB appliqué par heure (G horaire réel).

    Lève le biais de Jensen (rendement non-linéaire en G). Exige GHI horaire +
    T2M horaire.
    """
    _exiger_serie_horaire(serie, params.code_serie_source)
    alignees = _lire_ghi_t2m_horaires(
        session, serie, params, "'energie_utile_ecs' horaire", niveaux=niveaux
    )
    mesures: list[MesureHeureECS] = [
        {"instant_mesure": instant, "t_amb_degc": t2m, "irradiance_w_par_m2": ghi}
        for instant, (ghi, t2m) in alignees
    ]
    return calculer_energie_utile_ecs_horaire(mesures=mesures, parametres=params)


def _calculer_ecs_journalier(
    session: Session,
    serie: SerieSourceResolue,
    params: ParametresEnergieUtileECS,
    *,
    niveaux: NiveauxEntrees,
) -> list[ResultatJournalier]:
    """Rendement HWB appliqué aux moyennes journalières GHI / T2M."""
    mesures: list[MesureJourECS] = [
        {"instant_mesure": jour, "t_amb_degc": t2m, "irradiance_kwh_par_m2_jour": ghi}
        for jour, ghi, t2m in _lire_ghi_t2m_journaliers(
            session, serie, params, "energie_utile_ecs", niveaux=niveaux
        )
    ]
    return calculer_energie_utile_ecs(mesures=mesures, parametres=params)


@routeur.get(
    "/energie_utile_ecs",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="Énergie utile ECS bord-capteur (Hottel-Whillier-Bliss)",
)
def grandeur_energie_utile_ecs(
    params: Annotated[ParametresEnergieUtileECS, Depends()],
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> Response:
    """Calcule l'énergie utile ECS bord-capteur (Hottel-Whillier-Bliss).

    Pattern multi-séries automatique :

    - **Série principale attendue** : ``grandeur_code = 'ghi'``.
    - **Série compagne cherchée** : T2M (même localité + même source).
    - **Comportement si T2M présente** : équation HWB appliquée
      (eta = eta0 - a1 * dT/G - a2 * dT²/G, puis Q_utile = eta * G).
    - **Comportement si T2M absente** : 400
      ``INCOMPATIBILITE_SOURCE_GRANDEUR`` (le rendement HWB dépend de
      la différence T_fluide - T_amb).
    """
    niveaux = NiveauxEntrees()
    serie = _resoudre_serie_exigee(session, params.code_serie_source, "ghi", "energie_utile_ecs")
    calculer = (
        _calculer_ecs_horaire
        if params.methode == "integration_horaire"
        else _calculer_ecs_journalier
    )
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
        resultats=calculer(session, serie, params, niveaux=niveaux),
        format_sortie=params.format_sortie,
        niveaux=niveaux,
        plafond=PLAFOND_ECS,
    )


# === Endpoint degré-jour climatisation ====================================


def _calculer_djc(
    session: Session,
    serie: SerieSourceResolue,
    params: ParametresDegreJourClimatisation,
    *,
    niveaux: NiveauxEntrees,
) -> list[ResultatMensuel]:
    """DJC par moyenne journalière ou par intégration horaire.

    L'intégration horaire lève le biais de moyennage journalier (-5 à -15 %
    tropical) ; elle exige une série source horaire (T2M stocké et validé).
    """
    if params.methode == "integration_horaire":
        _exiger_serie_horaire(
            serie,
            params.code_serie_source,
            " Fournir une serie T2M horaire ou utiliser methode='moyenne_journaliere'.",
        )
        t2m_par_heure = _lire_mesures_horaires_par_serie_id(
            session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
        )
        mesures_horaires: list[MesureHeureTemperature] = [
            {"instant_mesure": instant, "t_degc": valeur}
            for instant, valeur in t2m_par_heure.items()
        ]
        return calculer_degre_jour_climatisation_horaire(
            mesures=mesures_horaires, parametres=params
        )
    t2m_par_jour = _lire_mesures_par_serie_id(
        session, serie.serie_id, params.periode_debut, params.periode_fin, niveaux=niveaux
    )
    mesures: list[MesureJourTemperature] = [
        {"instant_mesure": jour, "t_moy_degc": valeur} for jour, valeur in t2m_par_jour.items()
    ]
    return calculer_degre_jour_climatisation(mesures=mesures, parametres=params)


@routeur.get(
    "/degre_jour_climatisation",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="Degrés-jours de climatisation (moyenne journalière ou intégration horaire)",
)
def grandeur_degre_jour_climatisation(
    params: Annotated[ParametresDegreJourClimatisation, Depends()],
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> Response:
    """Calcule les degrés-jours de climatisation mensuels (Erbs 1983).

    Pattern série unique (pas de multi-séries) :

    - **Série principale attendue** : ``grandeur_code = 't2m'``. Une série
      pointant une autre grandeur lève une 400
      ``INCOMPATIBILITE_SOURCE_GRANDEUR``.
    - **Aucune série compagne cherchée** : DJC dépend uniquement de la
      température ambiante journalière et de la base T_b utilisateur.
    - **Sortie agrégée mensuel** : la grandeur produit des
      :class:`ResultatMensuel` au format ``instant="YYYY-MM"`` par
      sommation des écarts journaliers positifs sur le mois.
    """
    niveaux = NiveauxEntrees()
    serie = _resoudre_serie_exigee(
        session, params.code_serie_source, "t2m", "degre_jour_climatisation"
    )
    return _construire_reponse(
        code_grandeur="degre_jour_climatisation",
        code_serie_source=params.code_serie_source,
        parametres_appliques={
            "base_temperature_degc": params.base_temperature_degc,
            "methode": params.methode,
        },
        resultats=_calculer_djc(session, serie, params, niveaux=niveaux),
        format_sortie=params.format_sortie,
        niveaux=niveaux,
        plafond=PLAFOND_DJC,
    )

"""Proxy de salissure des modules (modèle HSU)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.grandeurs._commun import (
    _FENETRE_LARGE_DEBUT,
    _FENETRE_LARGE_FIN,
    _exiger_grandeur,
    _resoudre_serie_source,
    _verifier_contiguite_journaliere,
)
from kuma_data_core.api.v1.schemas.grandeurs import ReponseTauxSalissureProxy
from kuma_data_core.db.session import obtenir_session
from kuma_data_core.editorial.niveaux_confiance import NiveauxEntrees, propager_niveau_confiance
from kuma_data_core.lecture.mesures import lire_valeurs_journalieres
from kuma_data_core.lecture.series import (
    chercher_serie_compagne,
    chercher_serie_precipitation_nasa_power,
)
from kuma_data_core.services.grandeurs.soiling_hsu import (
    CLEANING_THRESHOLD_DEFAUT_MM,
    SURFACE_TILT_DEFAUT,
    MesureEntreeSoiling,
    calculer_taux_salissure_proxy,
)
from kuma_data_core.services.grandeurs.soiling_hsu import (
    PLAFOND_CONFIANCE as PLAFOND_SALISSURE,
)

routeur = APIRouter()


@routeur.get(
    "/taux_salissure_proxy/{code_serie_source}",
    response_model=ReponseTauxSalissureProxy,
    status_code=status.HTTP_200_OK,
    summary="Proxy de salissure (perte de transmission %, modele HSU)",
    tags=["grandeurs-F1"],
)
def grandeur_taux_salissure_proxy(
    code_serie_source: str,
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> ReponseTauxSalissureProxy:
    """Perte de transmission par salissure des modules (% = (1 - ratio HSU) x 100).

    Calculée à chaque appel. ``code_serie_source`` désigne la série PM2.5 (EAC4)
    de la localité ; une série d'une autre grandeur donne 400
    ``INCOMPATIBILITE_SOURCE_GRANDEUR``. La route lit aussi la série PM10 de la
    même source et la série de précipitation journalière NASA POWER de la
    localité (400 si l'une manque). Le calcul porte sur les jours où les trois
    séries ont une valeur ; ces jours doivent se suivre sans trou (422
    ``PLAGE_TEMPORELLE_NON_DISPONIBLE`` sinon), le modèle HSU cumulant la
    salissure jour après jour.

    Le modèle part de modules propres au premier jour : les premiers jours de la
    fenêtre sont sous-estimés. L'inclinaison et le seuil de pluie nettoyante
    sont fixes ; la réponse les rappelle.
    """
    niveaux = NiveauxEntrees()
    serie = _resoudre_serie_source(session, code_serie_source)
    _exiger_grandeur(serie.grandeur_code, "pm2_5", code_serie_source, "taux_salissure_proxy")

    pm10_serie_id = chercher_serie_compagne(
        session, serie.localite_id, serie.source_id, "pm10", serie.periode_debut, serie.granularite
    )
    pluie_serie_id = chercher_serie_precipitation_nasa_power(
        session, serie.localite_id, serie.periode_debut, serie.periode_fin
    )
    if pm10_serie_id is None or pluie_serie_id is None:
        raise ExceptionKuma(
            code=CodeErreur.INCOMPATIBILITE_SOURCE_GRANDEUR,
            message=(
                "Le proxy de salissure (HSU) exige la compagne PM10 (meme source EAC4) "
                "et la serie de precipitation journaliere (source nasa_power) pour la "
                f"localite de {code_serie_source!r} ; au moins une est absente."
            ),
            statut_http=status.HTTP_400_BAD_REQUEST,
        )

    pm2_5 = lire_valeurs_journalieres(
        session, serie.serie_id, _FENETRE_LARGE_DEBUT, _FENETRE_LARGE_FIN, niveaux=niveaux
    )
    pm10 = lire_valeurs_journalieres(
        session, pm10_serie_id, _FENETRE_LARGE_DEBUT, _FENETRE_LARGE_FIN, niveaux=niveaux
    )
    pluie = lire_valeurs_journalieres(
        session, pluie_serie_id, _FENETRE_LARGE_DEBUT, _FENETRE_LARGE_FIN, niveaux=niveaux
    )

    dates = sorted(pm2_5.keys() & pm10.keys() & pluie.keys())
    _verifier_contiguite_journaliere(dates, code_serie_source)

    entrees: list[MesureEntreeSoiling] = [
        {
            "instant_mesure": jour,
            "rainfall_mm": pluie[jour],
            "pm2_5": pm2_5[jour],
            "pm10": pm10[jour],
        }
        for jour in dates
    ]
    resultat = calculer_taux_salissure_proxy(entrees)
    # Modèle cumulatif : un jour dépend des jours précédents depuis le dernier
    # nettoyage, chaque jour prend le niveau des entrées des jours retenus (règle P).
    niveau = (
        propager_niveau_confiance(
            {n for jour in dates for n in niveaux.du_jour(jour)}, plafond=PLAFOND_SALISSURE
        )
        if dates
        else "B"
    )
    periode = f"{dates[0].isoformat()}/{dates[-1].isoformat()}" if dates else "aucune"

    return ReponseTauxSalissureProxy(
        code_serie_source=code_serie_source,
        code_localite=serie.localite_code,
        periode=periode,
        surface_tilt_deg=SURFACE_TILT_DEFAUT,
        cleaning_threshold_mm=CLEANING_THRESHOLD_DEFAUT_MM,
        mesures=[m.model_copy(update={"niveau_confiance": niveau}) for m in resultat.mesures],
        limite=resultat.limite,
    )

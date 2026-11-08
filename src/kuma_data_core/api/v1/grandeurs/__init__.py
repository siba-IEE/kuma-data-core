"""Endpoints ``/v1/grandeurs/<code>`` : grandeurs calculées à la volée.

Un module par famille, chacun avec son routeur sans préfixe ; ce paquet les
monte sous ``/grandeurs`` dans l'ordre du document OpenAPI :

- ``poa`` : POA paramétrable et bifacial ;
- ``productible`` : productible avec correction thermique et avec PR fourni ;
- ``thermique`` : énergie utile ECS et degrés-jours de climatisation ;
- ``ghi_exceedance`` : P50 / P90 inter-annuels de l'irradiation ;
- ``salissure`` : proxy de salissure et PR réaliste ;
- ``incertitude`` : atlas d'incertitude inter-source (fiche et collection).

Les étapes communes (résolution de la série source et des compagnes, lecture
des mesures utilisables, propagation de la confiance, sérialisation) sont dans
``_commun``. Authentification Bearer (``CleApiValidee``) ; erreurs dans
l'enveloppe ``{"erreur": {"code": ..., "message": ..., "details": ...}}``.
"""

from __future__ import annotations

from fastapi import APIRouter

from kuma_data_core.api.v1.grandeurs import (
    ghi_exceedance,
    incertitude,
    poa,
    productible,
    salissure,
    thermique,
)
from kuma_data_core.api.v1.grandeurs._commun import _propager
from kuma_data_core.api.v1.grandeurs.ghi_exceedance import _construire_limite_ghi_exceedance
from kuma_data_core.api.v1.grandeurs.incertitude import (
    _construire_limite_incertitude_inter_source,
    _lire_degenerescence_localite,
)
from kuma_data_core.api.v1.grandeurs.salissure import (
    _chercher_serie_pluie_nasa,
    _chercher_serie_pm_cams,
)

__all__ = [
    "_chercher_serie_pluie_nasa",
    "_chercher_serie_pm_cams",
    "_construire_limite_ghi_exceedance",
    "_construire_limite_incertitude_inter_source",
    "_lire_degenerescence_localite",
    "_propager",
    "routeur",
]

routeur = APIRouter(prefix="/grandeurs", tags=["grandeurs-F2"])
routeur.include_router(poa.routeur)
routeur.include_router(productible.routeur)
routeur.include_router(thermique.routeur)
routeur.include_router(ghi_exceedance.routeur)
routeur.include_router(salissure.routeur)
routeur.include_router(incertitude.routeur)

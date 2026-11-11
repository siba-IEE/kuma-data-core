"""Routes ``/v1/grandeurs/<code>``.

Six grandeurs paramétrables (POA mono-plan et bifacial, productible avec
correction thermique ou avec PR fourni, énergie utile ECS, degrés-jours de
climatisation) et cinq routes calculées ou assemblées à la volée (P50/P90 du
GHI, proxy de salissure, PR réaliste, fiche d'incertitude inter-source par
localité et en collection).

Une route paramétrable résout la série source et sa localité, lit ses mesures
et celles des séries compagnes nécessaires (même localité, même source, même
début de période et même granularité), appelle la fonction de calcul de
``services.grandeurs`` puis rend du JSON ou du CSV (paramètre ``format``). Le
niveau de confiance de chaque résultat suit la règle de propagation P
(ADR-0008).

Un module par famille de routes ; ``routeur`` les monte dans l'ordre du
document OpenAPI.
"""

from __future__ import annotations

from fastapi import APIRouter

from kuma_data_core.api.v1.grandeurs import (
    exceedance,
    incertitude,
    parametrables_plan,
    parametrables_productible,
    parametrables_thermique,
    pr_realiste,
    salissure,
)

routeur = APIRouter(prefix="/grandeurs", tags=["grandeurs-F2"])
routeur.include_router(parametrables_plan.routeur)
routeur.include_router(parametrables_productible.routeur)
routeur.include_router(parametrables_thermique.routeur)
routeur.include_router(exceedance.routeur)
routeur.include_router(salissure.routeur)
routeur.include_router(pr_realiste.routeur)
routeur.include_router(incertitude.routeur)

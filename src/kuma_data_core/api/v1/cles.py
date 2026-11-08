"""Endpoints ``/v1/cles`` : émission self-service et révocation (ADR-0003).

L'émission, non authentifiée, est la seule écriture publique du serveur,
d'où la limite par IP ; la révocation est réservée à l'administrateur. Sans
base de service (local), l'émission renvoie 404 ``CLES_EMISSION_NON_ACTIVEE``.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, status
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleAdminValidee
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.schemas.cles import (
    DemandeCle,
    ReponseCleCreee,
    ReponseRevocation,
)
from kuma_data_core.core.config import get_settings
from kuma_data_core.services.cles import (
    LIMITE_EMISSIONS_PAR_IP_24H,
    creer_cle,
    nombre_emissions_recentes,
    revoquer_par_prefixe,
)

routeur = APIRouter(prefix="/cles", tags=["cles"])


def _session_meta() -> Session:
    """Session sur la base de service, ou 404 si elle n'existe pas ici."""
    from kuma_data_core.db.session import get_engine_meta

    if get_settings().meta_db is None:
        raise ExceptionKuma(
            code=CodeErreur.CLES_EMISSION_NON_ACTIVEE,
            message="L'emission self-service de cles n'est pas activee sur ce deploiement.",
            statut_http=status.HTTP_404_NOT_FOUND,
        )
    return Session(get_engine_meta())


def _adresse_ip(request: Request) -> str:
    """IP cliente pour la limite d'émission.

    Derrière le proxy de confiance, on prend la **dernière** entrée de
    ``X-Forwarded-For``, celle ajoutée par le proxy : un client peut préfixer
    de fausses IP, jamais en ajouter après lui. Sans proxy déclaré, l'en-tête
    est ignoré.
    """
    if get_settings().derriere_proxy_confiance:
        transmis = request.headers.get("x-forwarded-for")
        if transmis:
            maillons = [m.strip() for m in transmis.split(",") if m.strip()]
            if maillons:
                return maillons[-1]
    return request.client.host if request.client is not None else "inconnue"


@routeur.post(
    "",
    response_model=ReponseCleCreee,
    status_code=status.HTTP_201_CREATED,
    summary="Émettre une clé API (self-service)",
    description=(
        "Inscription légère : une adresse de contact suffit, la clé est "
        "émise immédiatement. Elle n'est montrée qu'une seule fois - le "
        "serveur n'en conserve que l'empreinte. Émission bornée par "
        "adresse IP."
    ),
)
def emettre_cle(demande: DemandeCle, request: Request) -> ReponseCleCreee:
    """Émet une clé self-service (ADR-0003, D3)."""
    adresse_ip = _adresse_ip(request)
    with _session_meta() as session:
        if nombre_emissions_recentes(session, adresse_ip) >= LIMITE_EMISSIONS_PAR_IP_24H:
            raise ExceptionKuma(
                code=CodeErreur.CLES_LIMITE_EMISSION_ATTEINTE,
                message=(
                    "Limite d'emission de cles atteinte pour cette adresse (24 h glissantes)."
                ),
                statut_http=status.HTTP_429_TOO_MANY_REQUESTS,
                details={"limite_24h": LIMITE_EMISSIONS_PAR_IP_24H},
            )
        cle, enregistrement = creer_cle(
            session,
            email=demande.email,
            usage_prevu=demande.usage_prevu,
            adresse_ip=adresse_ip,
        )
        return ReponseCleCreee(
            cle=cle,
            prefixe=enregistrement.prefixe,
            quota_journalier=enregistrement.quota_journalier,
        )


@routeur.delete(
    "/{prefixe}",
    response_model=ReponseRevocation,
    status_code=status.HTTP_200_OK,
    summary="Révoquer une clé par son préfixe (administrateur)",
)
def revoquer_cle(prefixe: str, _admin: CleAdminValidee) -> ReponseRevocation:
    """Révoque toutes les clés actives portant ce préfixe (soft delete)."""
    with _session_meta() as session:
        revoquees = revoquer_par_prefixe(session, prefixe)
    if revoquees == 0:
        raise ExceptionKuma(
            code=CodeErreur.RESSOURCE_INTROUVABLE,
            message="Aucune cle active ne porte ce prefixe.",
            statut_http=status.HTTP_404_NOT_FOUND,
        )
    return ReponseRevocation(prefixe=prefixe, cles_revoquees=revoquees)

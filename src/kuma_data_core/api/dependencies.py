"""Dépendances FastAPI partagées : authentification par clé API (Bearer)."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, status

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.core.config import get_settings


def _cles_valides() -> set[str]:
    """Clés d'environnement valides, relues à chaque requête (coût négligeable)."""
    settings = get_settings()
    cles: set[str] = set()
    # Sans ce filtre, un Bearer vide égalerait une variable vide (compare_digest("", "")).
    for secret in (settings.api_cle_solar_bridge, settings.api_cle_admin):
        if secret is not None and secret.get_secret_value():
            cles.add(secret.get_secret_value())
    return cles


def verifier_cle_api(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Renvoie la clé si valide, sinon 401 (``AUTH_HEADER_MANQUANT``, ``AUTH_*_INVALIDE``).

    ``compare_digest`` évite tout canal temporel sur les clés d'environnement.
    """
    if authorization is None:
        raise ExceptionKuma(
            code=CodeErreur.AUTH_HEADER_MANQUANT,
            message="Header Authorization manquant.",
            statut_http=status.HTTP_401_UNAUTHORIZED,
        )

    if not authorization.startswith("Bearer "):
        raise ExceptionKuma(
            code=CodeErreur.AUTH_FORMAT_INVALIDE,
            message="Format attendu : 'Authorization: Bearer <cle>'.",
            statut_http=status.HTTP_401_UNAUTHORIZED,
        )

    cle_fournie = authorization.removeprefix("Bearer ").strip()

    # Redondant avec _cles_valides, par défense en profondeur.
    if not cle_fournie:
        raise ExceptionKuma(
            code=CodeErreur.AUTH_CLE_INVALIDE,
            message="Clé API invalide ou révoquée.",
            statut_http=status.HTTP_401_UNAUTHORIZED,
        )

    if any(secrets.compare_digest(cle_fournie, cle) for cle in _cles_valides()):
        return cle_fournie

    # Clés self-service : recherche par empreinte SHA-256 ; la valeur comparée
    # n'est pas le secret, donc pas de canal temporel exploitable.
    settings = get_settings()
    if settings.meta_db is not None:
        quota = _quota_cle_self_service(cle_fournie)
        if quota is not None:
            # Fenêtre fixe UTC, fail-open si Redis est injoignable.
            if settings.rate_limiting_actif:
                from kuma_data_core.services.cles import hacher_cle
                from kuma_data_core.services.quotas import consommer_quota

                if not consommer_quota(hacher_cle(cle_fournie), quota):
                    raise ExceptionKuma(
                        code=CodeErreur.CLES_QUOTA_JOURNALIER_DEPASSE,
                        message="Quota journalier de la clé dépassé.",
                        statut_http=status.HTTP_429_TOO_MANY_REQUESTS,
                        details={"quota_journalier": quota},
                    )
            return cle_fournie

    raise ExceptionKuma(
        code=CodeErreur.AUTH_CLE_INVALIDE,
        message="Clé API invalide ou révoquée.",
        statut_http=status.HTTP_401_UNAUTHORIZED,
    )


def _quota_cle_self_service(cle: str) -> int | None:
    """Quota de la clé self-service active, ``None`` si inconnue ou révoquée.

    Une panne de la base de service vaut 401, pas 500 : l'authentification ne
    doit pas devenir un oracle.
    """
    from sqlalchemy.orm import Session

    from kuma_data_core.core.logging import obtenir_logger
    from kuma_data_core.db.session import get_engine_meta
    from kuma_data_core.services.cles import quota_si_active

    try:
        with Session(get_engine_meta()) as session:
            return quota_si_active(session, cle)
    except Exception:
        obtenir_logger("kuma.api.auth").warning("meta_db_injoignable_cle_refusee", exc_info=True)
        return None


def verifier_cle_admin(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Exige la clé administrateur ; une autre clé valide reçoit le même 401 qu'une clé inconnue."""
    cle = verifier_cle_api(authorization)
    settings = get_settings()
    if settings.api_cle_admin is not None and secrets.compare_digest(
        cle, settings.api_cle_admin.get_secret_value()
    ):
        return cle
    raise ExceptionKuma(
        code=CodeErreur.AUTH_CLE_INVALIDE,
        message="Clé API invalide ou révoquée.",
        statut_http=status.HTTP_401_UNAUTHORIZED,
    )


CleApiValidee = Annotated[str, Depends(verifier_cle_api)]
"""À mettre dans la signature d'un endpoint authentifié (``_cle: CleApiValidee``)."""

CleAdminValidee = Annotated[str, Depends(verifier_cle_admin)]
"""Type-alias pour les endpoints réservés à la clé administrateur."""

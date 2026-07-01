"""Dépendances FastAPI partagées.

Contient l'authentification par clé API (``verifier_cle_api``) et
l'alias ``CleApiValidee`` à utiliser dans les signatures des endpoints
authentifiés.

Les clés valides sont lues depuis la configuration
(``Settings.api_cle_solar_bridge``, ``Settings.api_cle_admin``). Une
migration ultérieure est prévue vers une table ``cles_api`` avec
révocation et rotation.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, status

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.core.config import get_settings


def _cles_valides() -> set[str]:
    """Retourne l'ensemble des clés API valides depuis la configuration.

    Appelée à chaque requête authentifiée. Avec 1-2 clés en mémoire,
    le coût est négligeable. À optimiser via cache TTL le jour où la
    lecture se fera depuis une table.
    """
    settings = get_settings()
    cles: set[str] = set()
    if settings.api_cle_solar_bridge is not None:
        cles.add(settings.api_cle_solar_bridge.get_secret_value())
    if settings.api_cle_admin is not None:
        cles.add(settings.api_cle_admin.get_secret_value())
    return cles


def verifier_cle_api(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Valide la clé API présente dans le header ``Authorization``.

    Retourne la clé brute si valide. Lève une ``ExceptionKuma`` sinon,
    avec un code parmi ``AUTH_HEADER_MANQUANT``, ``AUTH_FORMAT_INVALIDE``
    ou ``AUTH_CLE_INVALIDE`` (toujours statut HTTP 401).

    La comparaison utilise ``secrets.compare_digest`` (constant-time) sur
    chaque clé valide, pour ne pas exposer de canal temporel même si les
    clés (256 bits d'entropie via ``secrets.token_urlsafe(32)``) rendent
    le risque théorique.
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

    if not any(secrets.compare_digest(cle_fournie, cle) for cle in _cles_valides()):
        raise ExceptionKuma(
            code=CodeErreur.AUTH_CLE_INVALIDE,
            message="Clé API invalide ou révoquée.",
            statut_http=status.HTTP_401_UNAUTHORIZED,
        )

    return cle_fournie


CleApiValidee = Annotated[str, Depends(verifier_cle_api)]
"""Type-alias à utiliser dans les signatures des endpoints authentifiés.

Exemple :

.. code-block:: python

    @routeur.get("/secret")
    def endpoint_protege(_cle: CleApiValidee) -> dict[str, str]:
        return {"ok": "ok"}
"""

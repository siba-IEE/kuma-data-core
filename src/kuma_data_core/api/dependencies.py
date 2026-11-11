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

import inspect
import ipaddress
import secrets
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Header, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.core.config import get_settings
from kuma_data_core.core.logging import obtenir_logger

_journal = obtenir_logger("kuma.api.auth")


def _cles_egales(fournie: str, attendue: str) -> bool:
    # En octets : compare_digest lève TypeError sur une str non ASCII.
    return secrets.compare_digest(fournie.encode(), attendue.encode())


def _cles_valides() -> set[str]:
    """Retourne l'ensemble des clés API valides depuis la configuration.

    Appelée à chaque requête authentifiée. Avec 1-2 clés en mémoire,
    le coût est négligeable. À optimiser via cache TTL le jour où la
    lecture se fera depuis une table.
    """
    settings = get_settings()
    cles: set[str] = set()
    # Une clé vide (variable d'environnement présente mais vide) n'est
    # jamais une clé valide : sans ce filtre, un Bearer vide matcherait
    # via compare_digest("", "") et authentifierait un anonyme.
    for secret in (settings.api_cle_solar_bridge, settings.api_cle_admin):
        if secret is not None and secret.get_secret_value():
            cles.add(secret.get_secret_value())
    return cles


def adresse_ip_cliente(request: Request) -> str:
    """Adresse du client, fiable derrière un proxy de confiance déclaré.

    Derrière le reverse proxy, ``request.client.host`` est l'adresse du
    proxy ; la vraie vit dans ``X-Forwarded-For``. On lit la **dernière**
    entrée, celle ajoutée par notre proxy : un client peut préfixer des
    adresses fictives, jamais en ajouter après. Sans proxy de confiance
    déclaré, l'en-tête est ignoré (un client le forgerait).
    """
    if get_settings().derriere_proxy_confiance:
        transmis = request.headers.get("x-forwarded-for")
        if transmis:
            maillons = [m.strip() for m in transmis.split(",") if m.strip()]
            if maillons:
                return maillons[-1]
    return request.client.host if request.client is not None else "inconnue"


def identite_reseau(adresse_ip: str) -> str:
    """Unité de comptage d'un client : l'adresse en IPv4, le /64 en IPv6.

    Un abonné IPv6 dispose d'un /64 entier : compter par adresse lui
    laisserait autant de compteurs que d'adresses.
    """
    try:
        adresse = ipaddress.ip_address(adresse_ip)
    except ValueError:
        return adresse_ip
    if isinstance(adresse, ipaddress.IPv6Address):
        if adresse.ipv4_mapped is not None:
            return str(adresse.ipv4_mapped)
        return str(ipaddress.ip_network((adresse, 64), strict=False))
    return str(adresse)


def limiter_debit_par_ip(request: Request) -> None:
    """Plafonne le débit par adresse avant toute authentification.

    Protège la base d'un flot de requêtes anonymes ou à Bearer aléatoire.
    Inactif hors profil serveur public (``rate_limiting_actif``).
    """
    settings = get_settings()
    if not settings.rate_limiting_actif:
        return
    # Lu sur la requête, pas via ``Header()`` : la dépendance couvre aussi les
    # routes publiques, dont le contrat OpenAPI ne doit pas gagner ce paramètre.
    authorization = request.headers.get("authorization")
    if authorization is not None and authorization.startswith("Bearer "):
        cle = authorization.removeprefix("Bearer ").strip()
        if cle and any(_cles_egales(cle, valide) for valide in _cles_valides()):
            return

    from kuma_data_core.services.quotas import consommer_debit_ip

    identite = identite_reseau(adresse_ip_cliente(request))
    if not consommer_debit_ip(identite, settings.debit_ip_par_minute):
        raise ExceptionKuma(
            code=CodeErreur.DEBIT_DEPASSE,
            message="Trop de requêtes depuis cette adresse. Réessayez dans une minute.",
            statut_http=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"plafond_par_minute": settings.debit_ip_par_minute},
        )


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

    # Une clé vide ne peut jamais être valide : refus avant toute
    # comparaison (défense redondante avec le filtrage de _cles_valides).
    if not cle_fournie:
        raise ExceptionKuma(
            code=CodeErreur.AUTH_CLE_INVALIDE,
            message="Clé API invalide ou révoquée.",
            statut_http=status.HTTP_401_UNAUTHORIZED,
        )

    if any(_cles_egales(cle_fournie, cle) for cle in _cles_valides()):
        return cle_fournie

    # Clés self-service (WP6) : sur un déploiement avec base de service,
    # l'empreinte de la clé est cherchée dans ``cles_api``. La comparaison
    # se fait sur le hash SHA-256 (index unique) : pas de canal temporel
    # exploitable, la valeur comparée n'est pas le secret.
    settings = get_settings()
    if settings.meta_db is not None:
        quota = _quota_cle_self_service(cle_fournie)
        if quota is not None:
            # Quota journalier (WP7) : appliqué aux seules clés
            # self-service, en fenêtre fixe UTC, fail-open si Redis
            # est injoignable (cf. services/quotas.py).
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
    """Quota de la clé self-service active, ``None`` si inconnue/révoquée.

    Ouverture paresseuse d'une session sur la base de service : ce
    chemin n'est atteint que si les clés d'environnement n'ont pas
    reconnu le Bearer, et seulement quand ``META_DB`` est configurée.
    Toute erreur d'infrastructure vaut refus (401), pas 500 : une base
    de service injoignable ne doit pas transformer l'auth en oracle.
    """
    from sqlalchemy.orm import Session

    from kuma_data_core.db.session import get_engine_meta
    from kuma_data_core.services.cles import quota_si_active

    try:
        with Session(get_engine_meta()) as session:
            return quota_si_active(session, cle)
    except Exception:
        _journal.warning("base_de_service_injoignable", exc_info=True)
        return None


def verifier_cle_admin(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Valide que le Bearer est **la clé administrateur** (et elle seule).

    Réservé aux opérations d'administration (révocation de clés, WP6).
    Une clé valide mais non-admin reçoit le même 401
    ``AUTH_CLE_INVALIDE`` qu'une clé inconnue : pas d'oracle sur le
    statut d'une clé.
    """
    cle = verifier_cle_api(authorization)
    settings = get_settings()
    if settings.api_cle_admin is not None and _cles_egales(
        cle, settings.api_cle_admin.get_secret_value()
    ):
        return cle
    raise ExceptionKuma(
        code=CodeErreur.AUTH_CLE_INVALIDE,
        message="Clé API invalide ou révoquée.",
        statut_http=status.HTTP_401_UNAUTHORIZED,
    )


CleApiValidee = Annotated[str, Depends(verifier_cle_api)]
"""Type-alias à utiliser dans les signatures des endpoints authentifiés.

Exemple :

.. code-block:: python

    @routeur.get("/secret")
    def endpoint_protege(_cle: CleApiValidee) -> dict[str, str]:
        return {"ok": "ok"}
"""

CleAdminValidee = Annotated[str, Depends(verifier_cle_admin)]
"""Type-alias pour les endpoints réservés à la clé administrateur."""


def parametres_requete[M: BaseModel](modele: type[M]) -> Callable[..., M]:
    """Dépendance qui construit ``modele`` à partir des paramètres de la requête.

    Avec ``Depends()`` nu, une erreur levée par un ``model_validator``
    (période inversée, paramètre requis par un autre) sort en 500. Elle
    devient ici une ``RequestValidationError``, rendue en 422 comme les
    autres erreurs d'entrée. La signature du modèle est reprise telle
    quelle : les paramètres exposés ne changent pas.
    """

    def construire(**valeurs: Any) -> M:
        try:
            return modele(**valeurs)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc

    construire.__signature__ = inspect.signature(modele)  # type: ignore[attr-defined]
    return construire

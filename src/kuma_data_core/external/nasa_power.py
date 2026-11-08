"""Client HTTP synchrone de l'API NASA POWER (daily, hourly, monthly).

La documentation NASA POWER limite une requête à 20 paramètres en daily et 15
en hourly ; aucun garde-fou applicatif. Valeur manquante : ``-999.0``
(``fill_value``). Erreurs : sous-types de ``NasaPowerError``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from kuma_data_core.exceptions import (
    NasaPowerHttpError,
    NasaPowerPayloadError,
    NasaPowerRateLimitError,
    NasaPowerTimeoutError,
)
from kuma_data_core.external._http_retry import (
    RETRY_BACKOFF_SECONDES,
    HttpRetryHttpError,
    HttpRetryRateLimitError,
    HttpRetryTimeoutError,
    executer_get_avec_retry,
)

# === Constantes ============================================================

BASE_URL: str = "https://power.larc.nasa.gov/api/temporal"
"""URL racine ; daily/hourly/monthly en sont des sous-chemins."""

DEFAULT_COMMUNITY: str = "RE"
"""Communauté Renewable Energy, adaptée au solaire."""

DEFAULT_TIMEOUT: float = 30.0
"""Timeout HTTP par défaut (latence P95 < 30 s)."""

SENTINELLE_VALEUR_MANQUANTE: float = -999.0
"""Valeur manquante NASA POWER (``fill_value`` de l'en-tête)."""

# === Schémas pydantic ======================================================


class _ConfigPermissive:
    """Configuration pydantic permissive : ignore les champs inattendus du payload."""

    model_config = ConfigDict(extra="ignore")


class NasaPowerGeometry(_ConfigPermissive, BaseModel):
    type: Literal["Point"]
    coordinates: tuple[float, float, float]


class NasaPowerApiInfo(_ConfigPermissive, BaseModel):
    version: str
    name: str


class NasaPowerHeader(_ConfigPermissive, BaseModel):
    """En-tête de la réponse ; ``sources`` varie selon l'endpoint."""

    title: str
    api: NasaPowerApiInfo
    fill_value: float
    time_standard: str | None = None
    start: str
    end: str
    sources: list[str | dict[str, str]] | None = None


class NasaPowerParameterMeta(_ConfigPermissive, BaseModel):
    units: str
    longname: str


class NasaPowerProperties(_ConfigPermissive, BaseModel):
    """``{parametre: {cle_date: valeur}}``, clé ``YYYYMMDD`` (daily) ou ``YYYYMMDDHH`` (hourly)."""

    parameter: dict[str, dict[str, float]]


class NasaPowerResponse(_ConfigPermissive, BaseModel):
    """Réponse complète NASA POWER (GeoJSON Feature enrichi)."""

    type: Literal["Feature"]
    geometry: NasaPowerGeometry
    properties: NasaPowerProperties
    header: NasaPowerHeader
    parameters: dict[str, NasaPowerParameterMeta]
    messages: list[str] = Field(default_factory=list)


# === Utilitaires ==========================================================


def calculer_indice_ciel_clair(
    allsky: float,
    clrsky: float,
    *,
    sentinelle: float = SENTINELLE_VALEUR_MANQUANTE,
) -> float | None:
    """Indice de ciel clair ``K = ALLSKY / CLRSKY`` (1 = ciel clair, 0 = masquage total).

    ``None`` sur sentinelle ou ``clrsky`` nul. ``K > 1`` signale un effet
    d'enhancement nuageux ou une anomalie. À ne pas confondre avec l'indice de
    clarté ``Kt = GHI / I0`` (paramètre ``ALLSKY_KT``).
    """
    if allsky == sentinelle or clrsky == sentinelle:
        return None
    if clrsky == 0.0:
        return None
    return allsky / clrsky


# === Fonctions de fetch ====================================================


def _format_date_yyyymmdd(d: date) -> str:
    """Formate une date au format ``YYYYMMDD`` (paramètres ``start``/``end``)."""
    return d.strftime("%Y%m%d")


def _construire_url_et_params(
    *,
    endpoint: str,
    latitude: float,
    longitude: float,
    parameters: Sequence[str],
    start_str: str,
    end_str: str,
    community: str,
    time_standard: str | None = None,
) -> tuple[str, dict[str, str]]:
    """Construit l'URL complète et les query params pour un appel NASA POWER."""
    url = f"{BASE_URL}/{endpoint}/point"
    query_params: dict[str, str] = {
        "parameters": ",".join(parameters),
        "community": community,
        "latitude": str(latitude),
        "longitude": str(longitude),
        "start": start_str,
        "end": end_str,
        "format": "JSON",
    }
    if time_standard is not None:
        query_params["time-standard"] = time_standard
    return url, query_params


def _executer_get_avec_retry(
    *,
    client: httpx.Client,
    url: str,
    query_params: dict[str, str],
    timeout: float,
    retry_backoff_seconds: tuple[float, ...] = RETRY_BACKOFF_SECONDES,
) -> httpx.Response:
    """Branche le retry partagé et convertit ses erreurs en erreurs NASA POWER.

    Gardé ici car les tests de retry importent ce symbole depuis ce module.
    """
    try:
        return executer_get_avec_retry(
            client=client,
            url=url,
            query_params=query_params,
            timeout=timeout,
            retry_backoff_seconds=retry_backoff_seconds,
        )
    except HttpRetryRateLimitError as exc:
        raise NasaPowerRateLimitError(
            status_code=exc.status_code,
            url=exc.url,
            body=exc.body,
        ) from exc
    except HttpRetryHttpError as exc:
        raise NasaPowerHttpError(
            status_code=exc.status_code,
            url=exc.url,
            body=exc.body,
        ) from exc
    except HttpRetryTimeoutError as exc:
        raise NasaPowerTimeoutError(
            url=exc.url,
            timeout_seconds=exc.timeout_seconds,
        ) from exc


def _fetch_payload_brut(
    *,
    url: str,
    query_params: dict[str, str],
    timeout: float,
    httpx_client: httpx.Client | None,
) -> dict[str, Any]:
    """Appel HTTP avec retry, renvoie le payload JSON brut (avant validation Pydantic)."""
    client_fourni = httpx_client is not None
    client = httpx_client if httpx_client is not None else httpx.Client(timeout=timeout)
    try:
        response = _executer_get_avec_retry(
            client=client,
            url=url,
            query_params=query_params,
            timeout=timeout,
        )

        url_complete = str(response.request.url)

        if response.status_code >= 400:
            raise NasaPowerHttpError(
                status_code=response.status_code, url=url_complete, body=response.text
            )

        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise NasaPowerPayloadError(
                message="Réponse non parsable en JSON",
                url=url_complete,
                body=response.text,
            ) from exc

        return payload
    finally:
        if not client_fourni:
            client.close()


def parser_reponse_nasa(payload: dict[str, Any], *, url: str = "") -> NasaPowerResponse:
    """Valide un payload en ``NasaPowerResponse``, que le payload vienne du réseau ou d'un seed."""
    try:
        return NasaPowerResponse.model_validate(payload)
    except ValidationError as exc:
        raise NasaPowerPayloadError(
            message=f"Payload ne respecte pas le schéma NasaPowerResponse : {exc}",
            url=url,
            body=str(payload)[:500],
        ) from exc


def _executer_requete(
    *,
    url: str,
    query_params: dict[str, str],
    timeout: float,
    httpx_client: httpx.Client | None,
) -> NasaPowerResponse:
    """Fetch puis parse ; un client temporaire est créé si ``httpx_client`` est absent."""
    payload = _fetch_payload_brut(
        url=url, query_params=query_params, timeout=timeout, httpx_client=httpx_client
    )
    return parser_reponse_nasa(payload, url=url)


def fetch_daily(
    *,
    latitude: float,
    longitude: float,
    parameters: Sequence[str],
    start: date,
    end: date,
    community: str = DEFAULT_COMMUNITY,
    timeout: float = DEFAULT_TIMEOUT,
    httpx_client: httpx.Client | None = None,
) -> NasaPowerResponse:
    """Séries journalières pour un point (bornes incluses, WGS84 en degrés décimaux)."""
    url, query_params = _construire_url_et_params(
        endpoint="daily",
        latitude=latitude,
        longitude=longitude,
        parameters=parameters,
        start_str=_format_date_yyyymmdd(start),
        end_str=_format_date_yyyymmdd(end),
        community=community,
    )
    return _executer_requete(
        url=url, query_params=query_params, timeout=timeout, httpx_client=httpx_client
    )


def fetch_daily_raw(
    *,
    latitude: float,
    longitude: float,
    parameters: Sequence[str],
    start: date,
    end: date,
    community: str = DEFAULT_COMMUNITY,
    timeout: float = DEFAULT_TIMEOUT,
    httpx_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Comme :func:`fetch_daily`, mais renvoie le payload brut destiné aux seeds."""
    url, query_params = _construire_url_et_params(
        endpoint="daily",
        latitude=latitude,
        longitude=longitude,
        parameters=parameters,
        start_str=_format_date_yyyymmdd(start),
        end_str=_format_date_yyyymmdd(end),
        community=community,
    )
    return _fetch_payload_brut(
        url=url, query_params=query_params, timeout=timeout, httpx_client=httpx_client
    )


def _format_annee_yyyy(annee: int) -> str:
    """Formate une année au format ``YYYY`` (paramètres ``start``/``end`` monthly)."""
    return f"{annee:04d}"


def fetch_monthly(
    *,
    latitude: float,
    longitude: float,
    parameters: Sequence[str],
    annee_debut: int,
    annee_fin: int,
    community: str = DEFAULT_COMMUNITY,
    timeout: float = DEFAULT_TIMEOUT,
    httpx_client: httpx.Client | None = None,
) -> NasaPowerResponse:
    """Séries mensuelles pour un point, bornes en années incluses.

    Clés ``YYYYMM`` ; certaines réponses ajoutent ``YYYY13`` (moyenne annuelle),
    à filtrer par l'appelant.
    """
    url, query_params = _construire_url_et_params(
        endpoint="monthly",
        latitude=latitude,
        longitude=longitude,
        parameters=parameters,
        start_str=_format_annee_yyyy(annee_debut),
        end_str=_format_annee_yyyy(annee_fin),
        community=community,
    )
    return _executer_requete(
        url=url, query_params=query_params, timeout=timeout, httpx_client=httpx_client
    )


def fetch_monthly_raw(
    *,
    latitude: float,
    longitude: float,
    parameters: Sequence[str],
    annee_debut: int,
    annee_fin: int,
    community: str = DEFAULT_COMMUNITY,
    timeout: float = DEFAULT_TIMEOUT,
    httpx_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Comme :func:`fetch_monthly`, mais renvoie le payload brut destiné aux seeds."""
    url, query_params = _construire_url_et_params(
        endpoint="monthly",
        latitude=latitude,
        longitude=longitude,
        parameters=parameters,
        start_str=_format_annee_yyyy(annee_debut),
        end_str=_format_annee_yyyy(annee_fin),
        community=community,
    )
    return _fetch_payload_brut(
        url=url, query_params=query_params, timeout=timeout, httpx_client=httpx_client
    )


def fetch_hourly(
    *,
    latitude: float,
    longitude: float,
    parameters: Sequence[str],
    start: date,
    end: date,
    community: str = DEFAULT_COMMUNITY,
    timeout: float = DEFAULT_TIMEOUT,
    time_standard: str = "UTC",
    httpx_client: httpx.Client | None = None,
) -> NasaPowerResponse:
    """Séries horaires pour un point, de ``start 00:00`` à ``end 23:00``.

    Les bornes sont des dates ``YYYYMMDD`` : l'endpoint rejette ``YYYYMMDDHH``
    (HTTP 422). ``time_standard`` vaut ``"UTC"`` ou ``"LST"`` (temps solaire local).
    """
    url, query_params = _construire_url_et_params(
        endpoint="hourly",
        latitude=latitude,
        longitude=longitude,
        parameters=parameters,
        start_str=_format_date_yyyymmdd(start),
        end_str=_format_date_yyyymmdd(end),
        community=community,
        time_standard=time_standard,
    )
    return _executer_requete(
        url=url, query_params=query_params, timeout=timeout, httpx_client=httpx_client
    )

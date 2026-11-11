"""Client HTTP synchrone de l'API NASA POWER.

Endpoints ``daily``, ``monthly`` et ``hourly`` en mode ``point``. NASA POWER
limite une requête à 20 paramètres (15 en horaire) ; le client ne le vérifie pas.

Une donnée manquante vaut ``-999.0`` (champ ``fill_value`` de l'en-tête,
constante ``SENTINELLE_VALEUR_MANQUANTE``).

Les GET sont retentés sur HTTP 429, 503, timeout et déconnexion du serveur
(``external/_http_retry.py``). Une fois les tentatives épuisées, ou sur toute
autre erreur, l'échec est levé comme sous-type de ``NasaPowerError`` :
``NasaPowerHttpError`` (``NasaPowerRateLimitError`` pour 429),
``NasaPowerTimeoutError``, ``NasaPowerPayloadError`` (JSON invalide ou non
conforme au schéma).
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

BASE_URL: str = "https://power.larc.nasa.gov/api/temporal"
"""URL racine de l'API ; chaque endpoint en est un sous-chemin."""

DEFAULT_COMMUNITY: str = "RE"
"""Communauté NASA POWER par défaut : Renewable Energy."""

DEFAULT_TIMEOUT: float = 30.0
"""Timeout HTTP par défaut (latence P95 < 30 s)."""

SENTINELLE_VALEUR_MANQUANTE: float = -999.0
"""Valeur que NASA POWER substitue aux données manquantes."""


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
    """En-tête de la réponse NASA POWER.

    ``sources`` peut être absent ou de structure variable selon
    l'endpoint ; typage souple en ``list[str | dict[str, str]] | None``.
    """

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
    """Conteneur des valeurs temporelles par paramètre.

    Structure : ``{nom_parametre: {clé_date: valeur}}``.

    - Clé date pour daily : ``"YYYYMMDD"``.
    - Clé date pour hourly : ``"YYYYMMDDHH"``.
    - Valeurs : ``float``. La sentinelle ``-999.0`` indique une donnée
      manquante (cf. ``SENTINELLE_VALEUR_MANQUANTE``).
    """

    parameter: dict[str, dict[str, float]]


class NasaPowerResponse(_ConfigPermissive, BaseModel):
    """Réponse complète NASA POWER (GeoJSON Feature enrichi)."""

    type: Literal["Feature"]
    geometry: NasaPowerGeometry
    properties: NasaPowerProperties
    header: NasaPowerHeader
    parameters: dict[str, NasaPowerParameterMeta]
    messages: list[str] = Field(default_factory=list)


def calculer_indice_ciel_clair(
    allsky: float,
    clrsky: float,
    *,
    sentinelle: float = SENTINELLE_VALEUR_MANQUANTE,
) -> float | None:
    """Indice de ciel clair ``K = ALLSKY / CLRSKY``.

    ``K = 1`` : ciel parfaitement clair ; ``K = 0`` : masquage total ; ``K > 1``
    n'est physiquement attendu que lors d'un renforcement nuageux ponctuel.
    Rend ``None`` si l'une des valeurs est la sentinelle ou si ``clrsky`` est nul.

    À ne pas confondre avec l'indice de clarté ``Kt = GHI / I_0`` (rayonnement
    extraterrestre), que NASA POWER fournit sous le paramètre ``ALLSKY_KT``.
    """
    if allsky == sentinelle or clrsky == sentinelle:
        return None
    if clrsky == 0.0:
        return None
    return allsky / clrsky


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
    """Applique le retry partagé et traduit ses ``HttpRetry*Error`` en erreurs NASA POWER."""
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
    """Exécute le GET (avec retry) et rend le payload JSON brut, avant validation.

    Un statut >= 400 non retenté lève ``NasaPowerHttpError`` ; un corps non JSON,
    ``NasaPowerPayloadError``. Sans ``httpx_client``, un client temporaire est
    créé puis fermé ; un client fourni est laissé ouvert.
    """
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
    """Valide un payload JSON NASA POWER contre le schéma ``NasaPowerResponse``.

    Lève ``NasaPowerPayloadError`` s'il n'est pas conforme ; ``url`` ne sert qu'au
    message d'erreur.
    """
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
    """Récupère le payload (``_fetch_payload_brut``) puis le valide (``parser_reponse_nasa``)."""
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
    """Récupère des séries journalières NASA POWER pour un point.

    Coordonnées WGS84 en degrés décimaux (positif au nord et à l'est) ; ``start``
    et ``end`` sont inclus. Lève un sous-type de ``NasaPowerError``.
    """
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
    """Comme ``fetch_daily``, mais rend le payload JSON brut, non validé."""
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
    """Récupère des séries mensuelles NASA POWER pour un point.

    ``annee_debut`` et ``annee_fin`` sont incluses. Les clés de
    ``properties.parameter[<nom>]`` sont au format ``YYYYMM`` ; certaines réponses
    ajoutent une clé ``YYYY13`` (moyenne annuelle) que l'appelant doit écarter
    s'il n'attend que des mois. Lève un sous-type de ``NasaPowerError``.
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
    """Comme ``fetch_monthly``, mais rend le payload JSON brut, non validé."""
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
    """Récupère des séries horaires NASA POWER pour un point.

    ``start`` et ``end`` sont des dates au format ``YYYYMMDD`` (l'endpoint
    rejette ``YYYYMMDDHH`` par un HTTP 422) : la réponse couvre toutes les heures
    de ``start`` 00:00 à ``end`` 23:00, en ``"UTC"`` ou en ``"LST"`` (heure
    solaire locale) selon ``time_standard``. Les clés de
    ``properties.parameter[<nom>]`` sont au format ``YYYYMMDDHH``. Lève un
    sous-type de ``NasaPowerError``.
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

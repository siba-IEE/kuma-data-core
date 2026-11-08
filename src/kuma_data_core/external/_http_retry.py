"""GET httpx avec retry exponentiel, partagé par les clients externes.

Rejoue sur HTTP 429 et 503, ``TimeoutException`` et ``RemoteProtocolError``
(déconnexions PVGIS intermittentes depuis les runners CI). Pas plus large :
``ConnectError`` ou une erreur DNS/TLS n'est pas transitoire et coûterait
21 s de retry inutile. Les erreurs génériques levées ici sont traduites en
erreurs de domaine par chaque client.
"""

from __future__ import annotations

import time

import httpx

# === Exceptions génériques exposées par le helper =========================


class HttpRetryError(Exception):
    """Base des erreurs levées à l'épuisement du retry."""


class HttpRetryTimeoutError(HttpRetryError):
    """Timeout ou déconnexion serveur persistant après retry."""

    def __init__(self, *, url: str, timeout_seconds: float) -> None:
        super().__init__(
            f"Echec reseau persistant apres epuisement retry "
            f"(url={url}, timeout={timeout_seconds}s)"
        )
        self.url = url
        self.timeout_seconds = timeout_seconds


class HttpRetryHttpError(HttpRetryError):
    """Statut HTTP retryable (typiquement 503) persistant après retry."""

    def __init__(self, *, status_code: int, url: str, body: str) -> None:
        super().__init__(f"HTTP {status_code} persistant apres epuisement retry (url={url})")
        self.status_code = status_code
        self.url = url
        self.body = body


class HttpRetryRateLimitError(HttpRetryHttpError):
    """HTTP 429 (rate limit) persistant après épuisement du retry."""


# === Constantes module ====================================================

RETRY_BACKOFF_SECONDES: tuple[float, ...] = (1.0, 4.0, 16.0)
"""Attentes entre tentatives : 4 tentatives au plus."""

RETRY_STATUTS_HTTP: tuple[int, ...] = (429, 503)
"""Statuts rejoués ; les autres statuts >= 400 sont rendus tels quels à l'appelant."""


# === Helper public-module =================================================


def executer_get_avec_retry(
    *,
    client: httpx.Client,
    url: str,
    query_params: dict[str, str],
    timeout: float,
    retry_backoff_seconds: tuple[float, ...] = RETRY_BACKOFF_SECONDES,
    retry_statuts_http: tuple[int, ...] = RETRY_STATUTS_HTTP,
) -> httpx.Response:
    """GET avec retry ; ``retry_backoff_seconds`` permet aux tests d'éviter les attentes."""
    nb_retries = len(retry_backoff_seconds)
    for tentative, backoff in enumerate([0.0, *retry_backoff_seconds]):
        if backoff > 0:
            time.sleep(backoff)
        try:
            response = client.get(url, params=query_params)
        except (httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
            if tentative == nb_retries:
                # httpx lève RuntimeError sur .request absent (RemoteProtocolError).
                try:
                    url_effectif = str(exc.request.url)
                except RuntimeError:
                    url_effectif = url
                raise HttpRetryTimeoutError(
                    url=url_effectif,
                    timeout_seconds=timeout,
                ) from exc
            continue

        if response.status_code not in retry_statuts_http:
            return response

        if tentative == nb_retries:
            url_complete = str(response.request.url)
            if response.status_code == 429:
                raise HttpRetryRateLimitError(
                    status_code=response.status_code,
                    url=url_complete,
                    body=response.text,
                )
            raise HttpRetryHttpError(
                status_code=response.status_code,
                url=url_complete,
                body=response.text,
            )

    # Garde-fou type : la boucle termine toujours par return ou raise.
    raise RuntimeError("Boucle retry epuisee sans retour ni raise (incoherence interne)")

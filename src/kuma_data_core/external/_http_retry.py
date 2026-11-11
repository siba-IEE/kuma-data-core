"""GET httpx avec retry et backoff exponentiel, partagé par les clients externes.

Sont retentés les statuts HTTP 429 et 503, ``httpx.TimeoutException`` et
``httpx.RemoteProtocolError`` (déconnexion intermittente du serveur PVGIS
observée depuis les runners GitHub Actions). Le périmètre n'est pas élargi à
``httpx.NetworkError`` ou ``ConnectError`` : cela masquerait des erreurs non
transitoires (DNS, TLS) derrière 21 s d'attente inutile.

À l'épuisement des tentatives, le helper lève des ``HttpRetry*Error`` génériques
que chaque client traduit dans ses propres exceptions par ``raise ... from``.
"""

from __future__ import annotations

import time

import httpx


class HttpRetryError(Exception):
    """Base des erreurs levées à l'épuisement des tentatives."""


class HttpRetryTimeoutError(HttpRetryError):
    """Timeout ou déconnexion du serveur persistant après toutes les tentatives."""

    def __init__(self, *, url: str, timeout_seconds: float) -> None:
        super().__init__(
            f"Echec reseau persistant apres epuisement retry "
            f"(url={url}, timeout={timeout_seconds}s)"
        )
        self.url = url
        self.timeout_seconds = timeout_seconds


class HttpRetryHttpError(HttpRetryError):
    """Statut HTTP retenté (503) persistant après toutes les tentatives."""

    def __init__(self, *, status_code: int, url: str, body: str) -> None:
        super().__init__(f"HTTP {status_code} persistant apres epuisement retry (url={url})")
        self.status_code = status_code
        self.url = url
        self.body = body


class HttpRetryRateLimitError(HttpRetryHttpError):
    """HTTP 429 persistant après toutes les tentatives."""


RETRY_BACKOFF_SECONDES: tuple[float, ...] = (1.0, 4.0, 16.0)
"""Attentes avant chaque nouvelle tentative : 4 tentatives au plus, 21 s d'attente cumulée."""

RETRY_STATUTS_HTTP: tuple[int, ...] = (429, 503)
"""Statuts retentés : 429 (limite de débit) et 503 (service indisponible)."""


def executer_get_avec_retry(
    *,
    client: httpx.Client,
    url: str,
    query_params: dict[str, str],
    timeout: float,
    retry_backoff_seconds: tuple[float, ...] = RETRY_BACKOFF_SECONDES,
    retry_statuts_http: tuple[int, ...] = RETRY_STATUTS_HTTP,
) -> httpx.Response:
    """GET avec retry sur erreurs transitoires (voir la docstring du module).

    Une réponse dont le statut n'est pas dans ``retry_statuts_http`` est rendue
    telle quelle, même >= 400 : à l'appelant de la traiter.
    """
    nb_retries = len(retry_backoff_seconds)
    for tentative, backoff in enumerate([0.0, *retry_backoff_seconds]):
        if backoff > 0:
            time.sleep(backoff)
        try:
            response = client.get(url, params=query_params)
        except (httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
            if tentative == nb_retries:
                # httpx lève RuntimeError à l'accès à ``exc.request`` quand la
                # requête n'est pas attachée à l'exception (RemoteProtocolError).
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

    # Inatteignable : la boucle se termine toujours par return ou raise.
    raise RuntimeError("Boucle retry epuisee sans retour ni raise (incoherence interne)")

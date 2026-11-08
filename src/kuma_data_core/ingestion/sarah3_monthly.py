"""Ingestion PVGIS-SARAH3 ICDR mensuelle vers ``mesures_ressource_mensuelles``.

API PVGIS MRcalc v5.3 (JRC), sans authentification (30 req/s par IP).
``H(h)_m`` est un cumul mensuel en kWh/m²/mois, divisé par le nombre exact
de jours du mois pour obtenir des kWh/m²/jour comparables à NASA POWER.

``KUMA_SKIP_SARAH3_INGESTION`` (truthy) court-circuite le réseau. Sous
``KUMA_INGESTION_MODE=offline`` (interdit en prod), le payload vient du seed
committé ; parsing et insertion inchangés.
"""

from __future__ import annotations

import calendar
import os
from typing import Any, cast

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.editorial.niveaux_confiance import (
    calculer_niveau_confiance_derive,
)
from kuma_data_core.exceptions import (
    PvgisHttpError,
    PvgisRateLimitError,
    PvgisTimeoutError,
)
from kuma_data_core.external._http_retry import (
    HttpRetryHttpError,
    HttpRetryRateLimitError,
    HttpRetryTimeoutError,
    executer_get_avec_retry,
)
from kuma_data_core.ingestion._mode import est_mode_offline

PVGIS_MRCALC_URL: str = "https://re.jrc.ec.europa.eu/api/v5_3/MRcalc"
"""Endpoint MRcalc v5.3 ; l'URL sans version est dépréciée depuis le 25 septembre 2024."""

PVGIS_RADDATABASE_SARAH3: str = "PVGIS-SARAH3"
"""Base SARAH-3 côté PVGIS (CM SAF / EUMETSAT ; Europe, Afrique, Asie)."""

DEFAULT_TIMEOUT: float = 30.0

_VARIABLE_ENV_SKIP_INGESTION: str = "KUMA_SKIP_SARAH3_INGESTION"
"""Truthy : '1', 'true', 'yes'. Distincte de la variable NASA pour couper une seule source."""


def _ingestion_doit_etre_skip() -> bool:
    """Vrai si ``KUMA_SKIP_SARAH3_INGESTION`` est truthy."""
    valeur = os.environ.get(_VARIABLE_ENV_SKIP_INGESTION, "").strip().lower()
    return valeur in ("1", "true", "yes")


# === Chemin offline-seed ==================================================


def _cle_payload_offline(
    latitude: float, longitude: float, annee_debut: int, annee_fin: int
) -> str:
    """Clé du seed : coordonnées arrondies à 4 décimales et fenêtre."""
    return f"{round(float(latitude), 4)}_{round(float(longitude), 4)}_{annee_debut}_{annee_fin}"


def _charger_payload_offline(
    *, latitude: float, longitude: float, annee_debut: int, annee_fin: int
) -> dict[str, Any]:
    """Payload PVGIS du seed.

    Import différé : le script qui prépare le seed tourne en live avant que le
    seed n'existe.
    """
    from kuma_data_core.db.seeds.sarah3_monthly_seed_data import SARAH3_PAYLOADS

    cle = _cle_payload_offline(latitude, longitude, annee_debut, annee_fin)
    payload = SARAH3_PAYLOADS.get(cle)
    if payload is None:
        raise RuntimeError(
            f"Mode offline SARAH-3 : aucun payload committé pour la clé {cle!r}. "
            f"Lancer scripts/preparer_seed_sarah3.py. Clés disponibles : "
            f"{sorted(SARAH3_PAYLOADS)}."
        )
    return cast("dict[str, Any]", payload)


def ecart_relatif_max_sarah3(payload_a: dict[str, Any], payload_b: dict[str, Any]) -> float:
    """Max de ``|a - b| / max(|b|, eps)`` sur les ``H(h)_m``, ``inf`` si un mois manque.

    SARAH-3 ICDR est figé : tout écart signale un retraitement JRC, donc un
    seed à refaire.
    """

    def _index(payload: dict[str, Any]) -> dict[tuple[int, int], float]:
        return {
            (int(e["year"]), int(e["month"])): float(e["H(h)_m"])
            for e in payload["outputs"]["monthly"]
        }

    val_a, val_b = _index(payload_a), _index(payload_b)
    ecart_max = 0.0
    for cle in set(val_a) | set(val_b):
        a, b = val_a.get(cle), val_b.get(cle)
        if a is None or b is None:
            return float("inf")
        ecart_max = max(ecart_max, abs(a - b) / max(abs(b), 1e-9))
    return ecart_max


def _fetch_sarah3_monthly_raw(
    *,
    latitude: float,
    longitude: float,
    annee_debut: int,
    annee_fin: int,
    timeout: float,
    httpx_client: httpx.Client | None,
) -> dict[str, Any]:
    """Payload brut de PVGIS MRcalc ou du seed ; ``RuntimeError`` sur erreur HTTP ou JSON."""
    # est_mode_offline lève en prod.
    if est_mode_offline():
        return _charger_payload_offline(
            latitude=latitude,
            longitude=longitude,
            annee_debut=annee_debut,
            annee_fin=annee_fin,
        )

    query_params: dict[str, str] = {
        "lat": str(latitude),
        "lon": str(longitude),
        "raddatabase": PVGIS_RADDATABASE_SARAH3,
        "startyear": str(annee_debut),
        "endyear": str(annee_fin),
        "horirrad": "1",
        "outputformat": "json",
    }

    client_fourni = httpx_client is not None
    client = httpx_client if httpx_client is not None else httpx.Client(timeout=timeout)
    try:
        try:
            response = executer_get_avec_retry(
                client=client,
                url=PVGIS_MRCALC_URL,
                query_params=query_params,
                timeout=timeout,
            )
        except HttpRetryRateLimitError as exc:
            raise PvgisRateLimitError(
                status_code=exc.status_code,
                url=exc.url,
                body=exc.body,
            ) from exc
        except HttpRetryHttpError as exc:
            raise PvgisHttpError(
                status_code=exc.status_code,
                url=exc.url,
                body=exc.body,
            ) from exc
        except HttpRetryTimeoutError as exc:
            raise PvgisTimeoutError(
                url=exc.url,
                timeout_seconds=exc.timeout_seconds,
            ) from exc

        if response.status_code >= 400:
            raise PvgisHttpError(
                status_code=response.status_code,
                url=str(response.request.url),
                body=response.text,
            )
        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"PVGIS MRcalc reponse non parsable en JSON sur "
                f"lat={latitude}, lon={longitude}. Body: {response.text[:500]}"
            ) from exc
    finally:
        if not client_fourni:
            client.close()

    return payload


def _extraire_valeurs_mensuelles(
    payload: dict[str, Any],
) -> list[tuple[int, int, float]]:
    """``(annee, mois, kWh/m²/jour)`` depuis ``outputs.monthly``.

    ``H(h)_m`` (cumul mensuel) est divisé par le nombre de jours du mois,
    bissextiles comprises. ``RuntimeError`` si la structure manque.
    """
    try:
        monthly = payload["outputs"]["monthly"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(
            f"PVGIS MRcalc payload ne contient pas outputs.monthly. "
            f"Cles racines : {list(payload.keys()) if isinstance(payload, dict) else type(payload)}"
        ) from exc

    if not isinstance(monthly, list):
        raise RuntimeError(f"PVGIS MRcalc outputs.monthly n'est pas une liste : {type(monthly)}")

    valeurs: list[tuple[int, int, float]] = []
    for entry in monthly:
        if not isinstance(entry, dict):
            continue
        annee = entry.get("year")
        mois = entry.get("month")
        cumul_mensuel = entry.get("H(h)_m")
        if annee is None or mois is None or cumul_mensuel is None:
            continue
        nombre_jours = calendar.monthrange(int(annee), int(mois))[1]
        valeur_quotidienne = float(cumul_mensuel) / nombre_jours
        valeurs.append((int(annee), int(mois), valeur_quotidienne))

    return valeurs


def ingerer_serie_sarah3_monthly(
    *,
    session: Session,
    code_serie: str,
    latitude: float,
    longitude: float,
    annee_debut: int,
    annee_fin: int,
    timeout: float = DEFAULT_TIMEOUT,
    httpx_client: httpx.Client | None = None,
) -> int:
    """Ingère une série SARAH-3 mensuelle ; renvoie le nombre de lignes insérées.

    0 si l'ingestion est court-circuitée ; ``RuntimeError`` si la série est
    inconnue ou la réponse mal formée.
    """
    if _ingestion_doit_etre_skip():
        return 0

    row = session.execute(
        text(
            """
            SELECT
                sm.id AS serie_id,
                sm.methode_collecte,
                s.fiabilite AS fiabilite_source
            FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            WHERE sm.code = :code
            """
        ),
        {"code": code_serie},
    ).first()
    if row is None:
        raise RuntimeError(
            f"Serie {code_serie!r} introuvable dans series_metadonnees. "
            f"Verifier que la migration de seed 1-7a a bien ete appliquee."
        )

    serie_id: int = int(row.serie_id)
    methode_collecte: str | None = row.methode_collecte
    fiabilite_source: str | None = row.fiabilite_source

    niveau_derive = calculer_niveau_confiance_derive(
        methode_collecte=methode_collecte,
        fiabilite_source=fiabilite_source,
    )

    payload = _fetch_sarah3_monthly_raw(
        latitude=latitude,
        longitude=longitude,
        annee_debut=annee_debut,
        annee_fin=annee_fin,
        timeout=timeout,
        httpx_client=httpx_client,
    )
    valeurs_mensuelles = _extraire_valeurs_mensuelles(payload)

    if not valeurs_mensuelles:
        return 0

    lignes_a_inserer: list[dict[str, object]] = [
        {
            "serie_id": serie_id,
            "annee": annee,
            "mois": mois,
            "valeur": valeur,
            "niveau_confiance_derive": niveau_derive,
        }
        for annee, mois, valeur in valeurs_mensuelles
    ]

    session.execute(
        text(
            """
            INSERT INTO mesures_ressource_mensuelles
                (serie_id, annee, mois, valeur, niveau_confiance_derive)
            VALUES
                (:serie_id, :annee, :mois, :valeur, :niveau_confiance_derive)
            """
        ),
        lignes_a_inserer,
    )
    session.flush()
    return len(lignes_a_inserer)

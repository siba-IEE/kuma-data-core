"""Ingestion mensuelle NASA POWER vers ``mesures_ressource_mensuelles``.

Les clés de la réponse sont au format ``YYYYMM``. La clé ``YYYY13`` (moyenne
annuelle, parfois présente) et les valeurs manquantes (``-999.0``) sont écartées.

``KUMA_SKIP_NASA_POWER_INGESTION`` et ``KUMA_INGESTION_MODE=offline`` agissent
comme pour l'ingestion journalière (voir ``nasa_power_daily.py``) ; le seed est
``db/seeds/nasa_power_monthly_seed_data``.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.editorial.niveaux_confiance import (
    calculer_niveau_confiance_derive,
)
from kuma_data_core.external.nasa_power import (
    SENTINELLE_VALEUR_MANQUANTE,
    fetch_monthly_raw,
    parser_reponse_nasa,
)
from kuma_data_core.ingestion._mode import est_mode_offline

_VARIABLE_ENV_SKIP_INGESTION: str = "KUMA_SKIP_NASA_POWER_INGESTION"
"""Même variable que l'ingestion journalière : un seul interrupteur pour NASA POWER."""


def _ingestion_doit_etre_skip() -> bool:
    """Vrai si la variable de court-circuit est activée."""
    valeur = os.environ.get(_VARIABLE_ENV_SKIP_INGESTION, "").strip().lower()
    return valeur in ("1", "true", "yes")


def _parse_cle_yyyymm(cle: str) -> tuple[int, int] | None:
    """Rend ``(annee, mois)`` pour une clé ``YYYYMM`` valide, ``None`` sinon (dont ``YYYY13``)."""
    if len(cle) != 6 or not cle.isdigit():
        return None
    annee = int(cle[:4])
    mois = int(cle[4:])
    if mois < 1 or mois > 12:
        return None
    return annee, mois


def _cle_ville_offline(latitude: float, longitude: float) -> str:
    """Clé du seed hors ligne : coordonnées arrondies à 4 décimales."""
    return f"{round(float(latitude), 4)}_{round(float(longitude), 4)}"


def _trancher_payload_offline(
    payload_ville: dict[str, Any],
    *,
    parameters: Sequence[str],
    annee_debut: int,
    annee_fin: int,
) -> dict[str, Any]:
    """Restreint le payload d'une ville aux paramètres et aux années demandés.

    L'année est lue sur les 4 premiers caractères de la clé (``YYYYMM`` ou
    ``YYYY13``). Les ``-999`` sont conservés (écartés en aval). Lève
    ``RuntimeError`` si un paramètre manque au seed.
    """
    param_source = payload_ville["properties"]["parameter"]
    param_restreint: dict[str, dict[str, float]] = {}
    for nom in parameters:
        if nom not in param_source:
            raise RuntimeError(
                f"Mode offline NASA monthly : parametre {nom!r} absent du seed ville. "
                f"Relancer scripts/preparer_seed_nasa_monthly.py. Presents : "
                f"{sorted(param_source)}."
            )
        param_restreint[nom] = {
            cle: valeur
            for cle, valeur in param_source[nom].items()
            if annee_debut <= int(cle[:4]) <= annee_fin
        }
    payload_restreint = dict(payload_ville)
    payload_restreint["properties"] = {"parameter": param_restreint}
    return payload_restreint


def _charger_payload_offline(
    *,
    latitude: float,
    longitude: float,
    parameters: Sequence[str],
    annee_debut: int,
    annee_fin: int,
) -> dict[str, Any]:
    """Rend le payload versionné de la ville, restreint à la requête (import du seed différé)."""
    from kuma_data_core.db.seeds.nasa_power_monthly_seed_data import NASA_MONTHLY_PAYLOADS

    cle = _cle_ville_offline(latitude, longitude)
    payload_ville = NASA_MONTHLY_PAYLOADS.get(cle)
    if payload_ville is None:
        raise RuntimeError(
            f"Mode offline NASA monthly : aucun payload committe pour la ville {cle!r}. "
            f"Lancer scripts/preparer_seed_nasa_monthly.py. Cles disponibles : "
            f"{sorted(NASA_MONTHLY_PAYLOADS)}."
        )
    return _trancher_payload_offline(
        payload_ville, parameters=parameters, annee_debut=annee_debut, annee_fin=annee_fin
    )


def _fetch_nasa_monthly_raw(
    *,
    latitude: float,
    longitude: float,
    parameters: Sequence[str],
    annee_debut: int,
    annee_fin: int,
    httpx_client: httpx.Client | None,
) -> dict[str, Any]:
    """Rend le payload mensuel brut : seed versionné en mode hors ligne, appel réseau sinon."""
    if est_mode_offline():
        return _charger_payload_offline(
            latitude=latitude,
            longitude=longitude,
            parameters=parameters,
            annee_debut=annee_debut,
            annee_fin=annee_fin,
        )
    return fetch_monthly_raw(
        latitude=latitude,
        longitude=longitude,
        parameters=parameters,
        annee_debut=annee_debut,
        annee_fin=annee_fin,
        httpx_client=httpx_client,
    )


def ecart_relatif_max_nasa_monthly(
    payload_live: dict[str, Any],
    payload_seed: dict[str, Any],
) -> float:
    """Écart relatif maximal entre un payload réseau et le seed, sur toutes les clés communes.

    Contrairement aux valeurs journalières récentes, la climatologie de long
    terme n'est pas révisée au fil de l'eau : un écart non nul signale un
    retraitement ou un changement de version de NASA POWER. Les valeurs
    manquantes (``-999``) sont ignorées. Rend le maximum de
    ``|live - seed| / max(|seed|, 1e-9)``, ``0.0`` si rien n'est comparable.
    """
    seed_params = payload_seed["properties"]["parameter"]
    live_params = payload_live["properties"]["parameter"]
    ecart_max = 0.0
    for nom, seed_vals in seed_params.items():
        live_vals = live_params.get(nom, {})
        for cle, v_seed in seed_vals.items():
            v_live = live_vals.get(cle)
            if v_live is None:
                continue
            if v_seed == SENTINELLE_VALEUR_MANQUANTE or v_live == SENTINELLE_VALEUR_MANQUANTE:
                continue
            ecart_max = max(ecart_max, abs(v_live - v_seed) / max(abs(v_seed), 1e-9))
    return ecart_max


def ingerer_serie_monthly(
    *,
    session: Session,
    code_serie: str,
    parametre_nasa: str,
    latitude: float,
    longitude: float,
    annee_debut: int,
    annee_fin: int,
    httpx_client: httpx.Client | None = None,
) -> int:
    """Ingère les mesures mensuelles d'une série NASA POWER dans ``mesures_ressource_mensuelles``.

    ``annee_debut`` et ``annee_fin`` sont incluses. Rend le nombre de lignes
    insérées (mois reçus moins les valeurs manquantes et les clés ``YYYY13``),
    0 si l'ingestion est court-circuitée ; insère puis ``flush`` sans ``commit``.
    Lève ``RuntimeError`` si ``code_serie`` est absent de ``series_metadonnees``
    ou si ``parametre_nasa`` manque à la réponse ; les erreurs du client
    (``NasaPowerError``) sont propagées.
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
            f"Verifier que la migration de seed correspondante a bien ete appliquee."
        )

    serie_id: int = int(row.serie_id)
    methode_collecte: str | None = row.methode_collecte
    fiabilite_source: str | None = row.fiabilite_source

    niveau_derive = calculer_niveau_confiance_derive(
        methode_collecte=methode_collecte,
        fiabilite_source=fiabilite_source,
    )

    payload = _fetch_nasa_monthly_raw(
        latitude=latitude,
        longitude=longitude,
        parameters=[parametre_nasa],
        annee_debut=annee_debut,
        annee_fin=annee_fin,
        httpx_client=httpx_client,
    )
    response = parser_reponse_nasa(payload)

    if parametre_nasa not in response.properties.parameter:
        raise RuntimeError(
            f"Parametre {parametre_nasa!r} absent du payload NASA POWER monthly. "
            f"Parametres disponibles : {list(response.properties.parameter)}"
        )
    valeurs_par_cle: dict[str, float] = response.properties.parameter[parametre_nasa]

    lignes_a_inserer: list[dict[str, object]] = []
    for cle, valeur in valeurs_par_cle.items():
        annee_mois = _parse_cle_yyyymm(cle)
        if annee_mois is None:
            # Clé non mensuelle (``YYYY13``, moyenne annuelle).
            continue
        if valeur == SENTINELLE_VALEUR_MANQUANTE:
            continue
        annee, mois = annee_mois
        lignes_a_inserer.append(
            {
                "serie_id": serie_id,
                "annee": annee,
                "mois": mois,
                "valeur": float(valeur),
                "niveau_confiance_derive": niveau_derive,
            }
        )

    if not lignes_a_inserer:
        return 0

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

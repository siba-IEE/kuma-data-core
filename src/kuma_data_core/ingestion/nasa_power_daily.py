"""Ingestion NASA POWER journalière vers ``mesures_ressource``.

``KUMA_SKIP_NASA_POWER_INGESTION`` (truthy) court-circuite le réseau et
n'insère rien. Sous ``KUMA_INGESTION_MODE=offline`` (interdit en prod), le
payload vient du seed committé, restreint à la requête ; le parsing et
l'insertion restent ceux du mode live, avec des décomptes déterministes.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.editorial.niveaux_confiance import (
    calculer_niveau_confiance_derive,
)
from kuma_data_core.external.nasa_power import (
    SENTINELLE_VALEUR_MANQUANTE,
    fetch_daily_raw,
    parser_reponse_nasa,
)
from kuma_data_core.ingestion._mode import est_mode_offline

_VARIABLE_ENV_SKIP_INGESTION: str = "KUMA_SKIP_NASA_POWER_INGESTION"
"""Valeurs truthy : '1', 'true', 'yes' (casse ignorée)."""


def _ingestion_doit_etre_skip() -> bool:
    """Vrai si ``KUMA_SKIP_NASA_POWER_INGESTION`` est truthy."""
    valeur = os.environ.get(_VARIABLE_ENV_SKIP_INGESTION, "").strip().lower()
    return valeur in ("1", "true", "yes")


def _parse_cle_date_nasa(cle: str) -> date:
    """Parse une clé date NASA POWER au format ``YYYYMMDD`` en ``date``."""
    return datetime.strptime(cle, "%Y%m%d").replace(tzinfo=None).date()


# === Chemin offline-seed (NASA daily) =====================================


def _cle_ville_offline(latitude: float, longitude: float) -> str:
    """Clé du seed : coordonnées arrondies à 4 décimales (un payload complet par ville)."""
    return f"{round(float(latitude), 4)}_{round(float(longitude), 4)}"


def _trancher_payload_offline(
    payload_ville: dict[str, Any],
    *,
    parameters: Sequence[str],
    periode_debut: date,
    periode_fin: date,
) -> dict[str, Any]:
    """Restreint le payload d'une ville à ce qu'un appel live aurait renvoyé.

    Garde les paramètres et dates demandés, sentinelles ``-999`` comprises
    (filtrées en aval comme en live), et les autres champs pour la validation.
    """
    debut = periode_debut.strftime("%Y%m%d")
    fin = periode_fin.strftime("%Y%m%d")
    param_source = payload_ville["properties"]["parameter"]
    param_restreint: dict[str, dict[str, float]] = {}
    for nom in parameters:
        if nom not in param_source:
            raise RuntimeError(
                f"Mode offline NASA daily : paramètre {nom!r} absent du seed ville. "
                f"Relancer scripts/preparer_seed_nasa_daily.py. Présents : "
                f"{sorted(param_source)}."
            )
        param_restreint[nom] = {
            cle: valeur for cle, valeur in param_source[nom].items() if debut <= cle <= fin
        }
    payload_restreint = dict(payload_ville)
    payload_restreint["properties"] = {"parameter": param_restreint}
    return payload_restreint


def _charger_payload_offline(
    *,
    latitude: float,
    longitude: float,
    parameters: Sequence[str],
    periode_debut: date,
    periode_fin: date,
) -> dict[str, Any]:
    """Payload du seed restreint à la requête.

    Import différé : le script qui prépare le seed tourne en live avant que le
    seed n'existe.
    """
    from kuma_data_core.db.seeds.nasa_power_daily_seed_data import NASA_DAILY_PAYLOADS

    cle = _cle_ville_offline(latitude, longitude)
    payload_ville = NASA_DAILY_PAYLOADS.get(cle)
    if payload_ville is None:
        raise RuntimeError(
            f"Mode offline NASA daily : aucun payload committé pour la ville {cle!r}. "
            f"Lancer scripts/preparer_seed_nasa_daily.py. Clés disponibles : "
            f"{sorted(NASA_DAILY_PAYLOADS)}."
        )
    return _trancher_payload_offline(
        payload_ville,
        parameters=parameters,
        periode_debut=periode_debut,
        periode_fin=periode_fin,
    )


def _fetch_nasa_daily_raw(
    *,
    latitude: float,
    longitude: float,
    parameters: Sequence[str],
    periode_debut: date,
    periode_fin: date,
    httpx_client: httpx.Client | None,
) -> dict[str, Any]:
    """Payload brut : seed en mode offline, sinon appel live."""
    if est_mode_offline():
        return _charger_payload_offline(
            latitude=latitude,
            longitude=longitude,
            parameters=parameters,
            periode_debut=periode_debut,
            periode_fin=periode_fin,
        )
    return fetch_daily_raw(
        latitude=latitude,
        longitude=longitude,
        parameters=parameters,
        start=periode_debut,
        end=periode_fin,
        httpx_client=httpx_client,
    )


def ecart_relatif_max_nasa_daily(
    payload_live: dict[str, Any],
    payload_seed: dict[str, Any],
    *,
    derniere_date_stable: date,
) -> float:
    """Max de ``|live - seed| / max(|seed|, eps)`` sur la fenêtre stable (0.0 si vide).

    Les données NRT de NASA POWER mûrissent : seules les dates
    ``<= derniere_date_stable`` sont comparées. Paires sentinelles ignorées.
    """
    fin = derniere_date_stable.strftime("%Y%m%d")
    seed_params = payload_seed["properties"]["parameter"]
    live_params = payload_live["properties"]["parameter"]
    ecart_max = 0.0
    for nom, seed_vals in seed_params.items():
        live_vals = live_params.get(nom, {})
        for cle, v_seed in seed_vals.items():
            if cle > fin:
                continue
            v_live = live_vals.get(cle)
            if v_live is None:
                continue
            if v_seed == SENTINELLE_VALEUR_MANQUANTE or v_live == SENTINELLE_VALEUR_MANQUANTE:
                continue
            ecart_max = max(ecart_max, abs(v_live - v_seed) / max(abs(v_seed), 1e-9))
    return ecart_max


def ingerer_serie_daily(
    *,
    session: Session,
    code_serie: str,
    parametre_nasa: str,
    latitude: float,
    longitude: float,
    periode_debut: date,
    periode_fin: date,
    httpx_client: httpx.Client | None = None,
) -> int:
    """Ingère une série (un paramètre NASA POWER) ; renvoie le nombre de lignes insérées.

    Bornes incluses, sentinelles ``-999.0`` écartées, flush sans commit.
    ``RuntimeError`` si ``code_serie`` est inconnu ; 0 si l'ingestion est
    court-circuitée.
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
            f"Série {code_serie!r} introuvable dans series_metadonnees. "
            f"Vérifier que la migration 016 a bien ete appliquee."
        )

    serie_id: int = int(row.serie_id)
    methode_collecte: str | None = row.methode_collecte
    fiabilite_source: str | None = row.fiabilite_source

    # Même méthode et même source pour toute la série : un seul niveau dérivé.
    niveau_derive = calculer_niveau_confiance_derive(
        methode_collecte=methode_collecte,
        fiabilite_source=fiabilite_source,
    )

    payload = _fetch_nasa_daily_raw(
        latitude=latitude,
        longitude=longitude,
        parameters=[parametre_nasa],
        periode_debut=periode_debut,
        periode_fin=periode_fin,
        httpx_client=httpx_client,
    )
    response = parser_reponse_nasa(payload)

    if parametre_nasa not in response.properties.parameter:
        raise RuntimeError(
            f"Paramètre {parametre_nasa!r} absent du payload NASA POWER. "
            f"Paramètres disponibles : {list(response.properties.parameter)}"
        )
    valeurs_par_cle: dict[str, float] = response.properties.parameter[parametre_nasa]

    lignes_a_inserer: list[dict[str, object]] = []
    for cle_date, valeur in valeurs_par_cle.items():
        if valeur == SENTINELLE_VALEUR_MANQUANTE:
            continue
        lignes_a_inserer.append(
            {
                "serie_id": serie_id,
                "instant_mesure": _parse_cle_date_nasa(cle_date),
                "valeur": float(valeur),
                "niveau_confiance_derive": niveau_derive,
                # statut, validité et audit : server_defaults.
            }
        )

    if not lignes_a_inserer:
        return 0

    # Bulk INSERT en SQL brut pour exploiter les server_defaults
    session.execute(
        text(
            """
            INSERT INTO mesures_ressource
                (serie_id, instant_mesure, valeur, niveau_confiance_derive)
            VALUES
                (:serie_id, :instant_mesure, :valeur, :niveau_confiance_derive)
            """
        ),
        lignes_a_inserer,
    )
    session.flush()
    return len(lignes_a_inserer)


def ingerer_series_daily_groupe(
    *,
    session: Session,
    codes_series: Sequence[str],
    mapping_grandeur_parametre_nasa: dict[str, str],
    latitude: float,
    longitude: float,
    periode_debut: date,
    periode_fin: date,
    httpx_client: httpx.Client | None = None,
) -> dict[str, int]:
    """Ingère N séries d'une localité en un seul appel multi-paramètres.

    Un appel garantit la même version d'API et la même release CERES/MERRA-2
    pour toutes les grandeurs. Renvoie ``{code_serie: nb_lignes}`` (``{}`` si
    court-circuité). ``RuntimeError`` si une série est inconnue, une grandeur
    absente de ``mapping_grandeur_parametre_nasa`` ou un paramètre absent de la
    réponse.
    """
    if _ingestion_doit_etre_skip():
        return {}

    if not codes_series:
        return {}

    rows = session.execute(
        text(
            """
            SELECT
                sm.id AS serie_id,
                sm.code AS code_serie,
                sm.grandeur_code,
                sm.methode_collecte,
                s.fiabilite AS fiabilite_source
            FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            WHERE sm.code = ANY(:codes)
            """
        ),
        {"codes": list(codes_series)},
    ).all()

    if len(rows) != len(codes_series):
        codes_trouves = {r.code_serie for r in rows}
        codes_manquants = set(codes_series) - codes_trouves
        raise RuntimeError(
            f"Séries introuvables dans series_metadonnees : "
            f"{sorted(codes_manquants)}. Vérifier le seed (migration 019)."
        )

    grandeurs_manquantes = {r.grandeur_code for r in rows} - set(mapping_grandeur_parametre_nasa)
    if grandeurs_manquantes:
        raise RuntimeError(
            f"Grandeurs sans paramètre NASA POWER mappé : "
            f"{sorted(grandeurs_manquantes)}. Vérifier "
            f"mapping_grandeur_parametre_nasa."
        )

    # Niveau calculé par série, sans supposer qu'elles partagent méthode et source.
    contexte_par_grandeur: dict[str, dict[str, object]] = {}
    for row in rows:
        niveau_derive = calculer_niveau_confiance_derive(
            methode_collecte=row.methode_collecte,
            fiabilite_source=row.fiabilite_source,
        )
        contexte_par_grandeur[row.grandeur_code] = {
            "serie_id": int(row.serie_id),
            "code_serie": str(row.code_serie),
            "niveau_derive": niveau_derive,
        }

    parametres_demandes = sorted(
        {mapping_grandeur_parametre_nasa[g] for g in contexte_par_grandeur}
    )
    payload = _fetch_nasa_daily_raw(
        latitude=latitude,
        longitude=longitude,
        parameters=parametres_demandes,
        periode_debut=periode_debut,
        periode_fin=periode_fin,
        httpx_client=httpx_client,
    )
    response = parser_reponse_nasa(payload)

    lignes_a_inserer: list[dict[str, object]] = []
    decompte_par_serie: dict[str, int] = {
        ctx["code_serie"]: 0  # type: ignore[misc]
        for ctx in contexte_par_grandeur.values()
    }
    for grandeur_code, ctx in contexte_par_grandeur.items():
        parametre_nasa = mapping_grandeur_parametre_nasa[grandeur_code]
        if parametre_nasa not in response.properties.parameter:
            raise RuntimeError(
                f"Paramètre {parametre_nasa!r} (grandeur {grandeur_code!r}) "
                f"absent du payload NASA POWER. Paramètres disponibles : "
                f"{list(response.properties.parameter)}"
            )
        valeurs_par_cle: dict[str, float] = response.properties.parameter[parametre_nasa]
        code_serie = ctx["code_serie"]
        for cle_date, valeur in valeurs_par_cle.items():
            if valeur == SENTINELLE_VALEUR_MANQUANTE:
                continue
            lignes_a_inserer.append(
                {
                    "serie_id": ctx["serie_id"],
                    "instant_mesure": _parse_cle_date_nasa(cle_date),
                    "valeur": float(valeur),
                    "niveau_confiance_derive": ctx["niveau_derive"],
                }
            )
            decompte_par_serie[code_serie] += 1  # type: ignore[index]

    if not lignes_a_inserer:
        return decompte_par_serie

    session.execute(
        text(
            """
            INSERT INTO mesures_ressource
                (serie_id, instant_mesure, valeur, niveau_confiance_derive)
            VALUES
                (:serie_id, :instant_mesure, :valeur, :niveau_confiance_derive)
            """
        ),
        lignes_a_inserer,
    )
    session.flush()
    return decompte_par_serie

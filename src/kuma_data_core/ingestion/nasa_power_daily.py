"""Ingestion journalière NASA POWER vers ``mesures_ressource``.

``ingerer_serie_daily`` ingère une série (un paramètre) par appel ;
``ingerer_series_daily_groupe`` ingère plusieurs séries d'une même localité en
un seul appel multi-paramètres : toutes les grandeurs viennent alors de la même
réponse, donc de la même version amont (CERES SYN1deg + MERRA-2).

Les deux écartent les valeurs manquantes (``-999.0``), insèrent, puis font un
``flush`` sans ``commit``.

Deux variables d'environnement évitent le réseau.
``KUMA_SKIP_NASA_POWER_INGESTION`` (``1``, ``true`` ou ``yes``) court-circuite
l'ingestion : aucun appel, aucune insertion. ``KUMA_INGESTION_MODE=offline``
remplace l'appel par le payload versionné dans
``db/seeds/nasa_power_daily_seed_data``, restreint aux paramètres et à la
fenêtre demandés, puis validé et inséré par le même code qu'une réponse réseau.
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
"""Court-circuite l'ingestion quand elle vaut ``1``, ``true`` ou ``yes`` (casse indifférente)."""


def _ingestion_doit_etre_skip() -> bool:
    """Vrai si la variable de court-circuit est activée."""
    valeur = os.environ.get(_VARIABLE_ENV_SKIP_INGESTION, "").strip().lower()
    return valeur in ("1", "true", "yes")


def _parse_cle_date_nasa(cle: str) -> date:
    """Parse une clé date NASA POWER au format ``YYYYMMDD`` en ``date``."""
    return datetime.strptime(cle, "%Y%m%d").replace(tzinfo=None).date()


def _cle_ville_offline(latitude: float, longitude: float) -> str:
    """Clé du seed hors ligne : coordonnées arrondies à 4 décimales.

    Le seed porte un seul payload par ville ; ``_trancher_payload_offline`` en
    extrait la requête demandée.
    """
    return f"{round(float(latitude), 4)}_{round(float(longitude), 4)}"


def _trancher_payload_offline(
    payload_ville: dict[str, Any],
    *,
    parameters: Sequence[str],
    periode_debut: date,
    periode_fin: date,
) -> dict[str, Any]:
    """Restreint le payload d'une ville aux paramètres et à la fenêtre demandés.

    Le résultat a la forme d'une réponse réseau : les ``-999`` sont conservés
    (écartés en aval), ainsi que les champs hors ``properties``, dont
    ``parser_reponse_nasa`` a besoin. Lève ``RuntimeError`` si un paramètre
    manque au seed.
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
    """Rend le payload versionné de la ville, restreint à la requête.

    L'import du seed est différé : le script qui prépare le seed doit pouvoir
    charger ce module avant que le seed existe.
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
    """Rend le payload journalier brut : seed versionné en mode hors ligne, appel réseau sinon."""
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
    """Écart relatif maximal entre un payload réseau et le seed, sur les dates stables.

    Les valeurs récentes de NASA POWER sont provisoires et révisées par la suite :
    seules les dates ``<= derniere_date_stable`` sont comparées. Les valeurs
    manquantes (``-999``) sont ignorées. Rend le maximum de
    ``|live - seed| / max(|seed|, 1e-9)``, ``0.0`` si rien n'est comparable.
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
    """Ingère les mesures journalières d'une série NASA POWER dans ``mesures_ressource``.

    ``periode_debut`` et ``periode_fin`` sont incluses. Rend le nombre de lignes
    insérées (jours reçus moins les valeurs manquantes), 0 si l'ingestion est
    court-circuitée. Lève ``RuntimeError`` si ``code_serie`` est absent de
    ``series_metadonnees`` ou si ``parametre_nasa`` manque à la réponse ; les
    erreurs du client (``NasaPowerError``) sont propagées.
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

    # Toutes les mesures de la série partagent la même methode_collecte
    # et la même fiabilite_source : niveau dérivé identique pour toutes.
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
            }
        )

    if not lignes_a_inserer:
        return 0

    # SQL brut : les colonnes omises (statut, valide_du, valide_au, cree_le,
    # modifie_le) prennent leur valeur par défaut côté serveur.
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
    """Ingère plusieurs séries d'une même localité en un seul appel multi-paramètres.

    ``mapping_grandeur_parametre_nasa`` associe à chaque ``grandeur_code`` des
    séries son paramètre NASA POWER (par exemple ``{"dni": "ALLSKY_SFC_SW_DNI"}``).
    Les coordonnées sont celles passées en argument, pas celles des séries.

    Rend le nombre de lignes insérées par code de série, ``{}`` si l'ingestion
    est court-circuitée ou si ``codes_series`` est vide. Lève ``RuntimeError`` si
    une série est introuvable, si une grandeur n'a pas de paramètre associé ou si
    un paramètre manque à la réponse ; les erreurs du client (``NasaPowerError``)
    sont propagées.
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

    # Le niveau est calculé série par série plutôt que supposé commun.
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

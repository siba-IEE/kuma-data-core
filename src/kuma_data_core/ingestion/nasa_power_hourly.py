"""Ingestion NASA POWER horaire vers ``mesures_ressource_horaires`` (instants UTC).

Un appel par année civile (l'API accepte au plus 366 jours). Les lignes
arrivent en statut ``brut`` ; le contrôle qualité les passe en
``valide_auto``. ``KUMA_SKIP_NASA_POWER_INGESTION`` (truthy) court-circuite
le réseau.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import UTC, date, datetime

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.editorial.niveaux_confiance import (
    calculer_niveau_confiance_derive,
)
from kuma_data_core.external.nasa_power import (
    SENTINELLE_VALEUR_MANQUANTE,
    fetch_hourly,
)

_VARIABLE_ENV_SKIP_INGESTION: str = "KUMA_SKIP_NASA_POWER_INGESTION"
"""Truthy : '1', 'true', 'yes'. Même variable que journalier et mensuel."""


def _ingestion_doit_etre_skip() -> bool:
    """Vrai si ``KUMA_SKIP_NASA_POWER_INGESTION`` est truthy."""
    valeur = os.environ.get(_VARIABLE_ENV_SKIP_INGESTION, "").strip().lower()
    return valeur in ("1", "true", "yes")


def _parse_cle_yyyymmddhh(cle: str) -> datetime | None:
    """``YYYYMMDDHH`` -> ``datetime`` UTC tz-aware, ``None`` si la clé est non conforme."""
    if len(cle) != 10 or not cle.isdigit():
        return None
    annee = int(cle[0:4])
    mois = int(cle[4:6])
    jour = int(cle[6:8])
    heure = int(cle[8:10])
    if not (1 <= mois <= 12 and 1 <= jour <= 31 and 0 <= heure <= 23):
        return None
    return datetime(annee, mois, jour, heure, tzinfo=UTC)


def ingerer_serie_horaire(
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
    """Ingère une série horaire ; renvoie le nombre de lignes insérées.

    Sentinelles ``-999.0`` et clés non conformes écartées, flush sans commit.
    0 si court-circuité ; ``RuntimeError`` si la série est inconnue ou le
    paramètre absent d'un payload.
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
    niveau_derive = calculer_niveau_confiance_derive(
        methode_collecte=row.methode_collecte,
        fiabilite_source=row.fiabilite_source,
    )

    lignes_a_inserer: list[dict[str, object]] = []
    for annee in range(annee_debut, annee_fin + 1):
        response = fetch_hourly(
            latitude=latitude,
            longitude=longitude,
            parameters=[parametre_nasa],
            start=date(annee, 1, 1),
            end=date(annee, 12, 31),
            time_standard="UTC",
            httpx_client=httpx_client,
        )
        if parametre_nasa not in response.properties.parameter:
            raise RuntimeError(
                f"Parametre {parametre_nasa!r} absent du payload NASA POWER hourly "
                f"(annee {annee}). Parametres disponibles : "
                f"{list(response.properties.parameter)}"
            )
        for cle, valeur in response.properties.parameter[parametre_nasa].items():
            instant = _parse_cle_yyyymmddhh(cle)
            if instant is None:
                continue
            if valeur == SENTINELLE_VALEUR_MANQUANTE:
                continue
            lignes_a_inserer.append(
                {
                    "serie_id": serie_id,
                    "instant_mesure": instant,
                    "valeur": float(valeur),
                    "niveau_confiance_derive": niveau_derive,
                }
            )

    if not lignes_a_inserer:
        return 0

    session.execute(
        text(
            """
            INSERT INTO mesures_ressource_horaires
                (serie_id, instant_mesure, valeur, niveau_confiance_derive)
            VALUES
                (:serie_id, :instant_mesure, :valeur, :niveau_confiance_derive)
            """
        ),
        lignes_a_inserer,
    )
    session.flush()
    return len(lignes_a_inserer)


_TAILLE_LOT_INSERT: int = 20_000
"""Une année x 9 grandeurs approche 79 000 lignes : les lots bornent mémoire et requêtes."""


def ingerer_series_horaires_groupe(
    *,
    session: Session,
    codes_series: Sequence[str],
    mapping_grandeur_parametre_nasa: dict[str, str],
    latitude: float,
    longitude: float,
    annee_debut: int,
    annee_fin: int,
    httpx_client: httpx.Client | None = None,
) -> dict[str, int]:
    """Ingère N séries d'une localité, un appel multi-paramètres par année.

    Même release CERES/MERRA-2 pour toutes les grandeurs d'une année. Les
    grandeurs diurnes (kt) n'ont pas de ligne nocturne (sentinelles). Renvoie
    ``{code_serie: nb_lignes}`` (``{}`` si court-circuité) ; ``RuntimeError``
    comme :func:`ingerer_series_daily_groupe`.
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
            f"Séries introuvables dans series_metadonnees : {sorted(codes_manquants)}. "
            f"Vérifier le seed de la migration appelante."
        )
    grandeurs_manquantes = {r.grandeur_code for r in rows} - set(mapping_grandeur_parametre_nasa)
    if grandeurs_manquantes:
        raise RuntimeError(
            f"Grandeurs sans paramètre NASA POWER mappé : {sorted(grandeurs_manquantes)}. "
            f"Vérifier mapping_grandeur_parametre_nasa."
        )

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
    decompte_par_serie: dict[str, int] = {
        str(ctx["code_serie"]): 0 for ctx in contexte_par_grandeur.values()
    }
    tampon: list[dict[str, object]] = []

    def _vider_tampon() -> None:
        if not tampon:
            return
        session.execute(
            text(
                """
                INSERT INTO mesures_ressource_horaires
                    (serie_id, instant_mesure, valeur, niveau_confiance_derive)
                VALUES
                    (:serie_id, :instant_mesure, :valeur, :niveau_confiance_derive)
                """
            ),
            tampon,
        )
        tampon.clear()

    for annee in range(annee_debut, annee_fin + 1):
        response = fetch_hourly(
            latitude=latitude,
            longitude=longitude,
            parameters=parametres_demandes,
            start=date(annee, 1, 1),
            end=date(annee, 12, 31),
            time_standard="UTC",
            httpx_client=httpx_client,
        )
        for grandeur_code, ctx in contexte_par_grandeur.items():
            parametre_nasa = mapping_grandeur_parametre_nasa[grandeur_code]
            if parametre_nasa not in response.properties.parameter:
                raise RuntimeError(
                    f"Parametre {parametre_nasa!r} (grandeur {grandeur_code!r}) absent du "
                    f"payload NASA POWER hourly (annee {annee}). Parametres disponibles : "
                    f"{list(response.properties.parameter)}"
                )
            code_serie = str(ctx["code_serie"])
            for cle, valeur in response.properties.parameter[parametre_nasa].items():
                instant = _parse_cle_yyyymmddhh(cle)
                if instant is None:
                    continue
                if valeur == SENTINELLE_VALEUR_MANQUANTE:
                    continue
                tampon.append(
                    {
                        "serie_id": ctx["serie_id"],
                        "instant_mesure": instant,
                        "valeur": float(valeur),
                        "niveau_confiance_derive": ctx["niveau_derive"],
                    }
                )
                decompte_par_serie[code_serie] += 1
                if len(tampon) >= _TAILLE_LOT_INSERT:
                    _vider_tampon()

    _vider_tampon()
    session.flush()
    return decompte_par_serie

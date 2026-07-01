"""Ingestion horaire NASA POWER -> ``mesures_ressource_horaires``.

Pendant horaire de ``nasa_power_monthly.py`` et
``nasa_power_daily.py``. Consomme le client
``kuma_data_core.external.nasa_power.fetch_hourly``, transforme la
réponse en lignes ``mesures_ressource_horaires`` (instant ``TIMESTAMPTZ``
UTC), et fait l'INSERT bulk via SQLAlchemy.

Les données ingérées sont en statut **``brut``** (défaut SQL) : le
contrôle qualité algorithmique fera passer les lignes valides en
``valide_auto``.

La fonction principale ``ingerer_serie_horaire`` boucle **par année**
(un appel ``fetch_hourly`` par année civile, borne <= 366 jours validée
empiriquement) et parse les clés de la réponse au format ``YYYYMMDDHH``
en ``datetime`` UTC tz-aware.

Variable d'environnement ``KUMA_SKIP_NASA_POWER_INGESTION`` (truthy)
court-circuite l'appel réseau et retourne 0 lignes insérées, comme les
fonctions journalière et mensuelle. Utile pour CI sans accès réseau.
"""

from __future__ import annotations

import os
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
"""Variable d'environnement court-circuitant l'ingestion réseau.

Truthy values : '1', 'true', 'yes' (case-insensitive). Partage la même
variable que les modules daily / monthly : un seul switch désactive
toutes les ingestions NASA POWER (cohérence opérationnelle CI).
"""


def _ingestion_doit_etre_skip() -> bool:
    """Lit la variable d'environnement et retourne True si elle est truthy."""
    valeur = os.environ.get(_VARIABLE_ENV_SKIP_INGESTION, "").strip().lower()
    return valeur in ("1", "true", "yes")


def _parse_cle_yyyymmddhh(cle: str) -> datetime | None:
    """Parse une clé horaire NASA POWER ``YYYYMMDDHH`` en ``datetime`` UTC.

    Retourne un ``datetime`` tz-aware (fuseau UTC, cohérent avec
    ``time_standard='UTC'`` passé à ``fetch_hourly``) si la clé est
    valide, ``None`` sinon (clé non conforme).

    Args:
        cle : chaîne de 10 caractères (ex. ``"2021060112"`` =
            2021-06-01 12:00 UTC).
    """
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
    """Ingère les mesures horaires d'une série NASA POWER dans ``mesures_ressource_horaires``.

    Boucle par année civile (un appel ``fetch_hourly`` par année, borne
    <= 366 jours), filtre les sentinelles ``-999.0``, et insère les
    lignes en statut ``brut`` (défaut SQL).

    Args:
        session : session SQLAlchemy active. La fonction add+flush mais
            ne commit pas (responsabilité du caller).
        code_serie : code naturel de la série dans ``series_metadonnees``
            (ex. ``gin_conakry_ghi_nasa_power_2021_2023``). Doit exister
            sinon ``RuntimeError``.
        parametre_nasa : code NASA POWER à ingérer (ex.
            ``ALLSKY_SFC_SW_DWN`` pour GHI).
        latitude, longitude : coordonnées WGS84 du point de mesure.
        annee_debut, annee_fin : bornes inclusives (années civiles).
        httpx_client : client httpx injectable pour tests via
            ``httpx.MockTransport``. Si None, un client temporaire est
            créé par ``fetch_hourly``.

    Returns:
        Nombre de lignes effectivement insérées dans
        ``mesures_ressource_horaires`` (heures retournées par NASA POWER
        moins les sentinelles ``-999.0`` filtrées et les clés non
        conformes). Retourne ``0`` si ``KUMA_SKIP_NASA_POWER_INGESTION``
        est truthy (court-circuit sans appel réseau ni INSERT).

    Raises:
        RuntimeError : si ``code_serie`` n'existe pas dans
            ``series_metadonnees`` ou si le ``parametre_nasa`` est absent
            d'un payload.
        kuma_data_core.exceptions.NasaPowerError : remontée du client si
            un appel API échoue.
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

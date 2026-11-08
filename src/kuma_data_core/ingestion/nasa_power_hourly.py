"""Ingestion NASA POWER horaire vers ``mesures_ressource_horaires`` (instants UTC).

Un appel par année civile (l'API accepte au plus 366 jours). Les lignes
arrivent en statut ``brut`` ; le contrôle qualité les passe en
``valide_auto``. ``KUMA_SKIP_NASA_POWER_INGESTION`` (truthy) court-circuite
le réseau.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime

import httpx
from sqlalchemy.orm import Session

from kuma_data_core.external.nasa_power import (
    SENTINELLE_VALEUR_MANQUANTE,
    fetch_hourly,
)
from kuma_data_core.ingestion._commun import (
    contexte_serie,
    contexte_series_groupe,
    doit_etre_skip,
    inserer_mesures,
)

_VARIABLE_ENV_SKIP_INGESTION: str = "KUMA_SKIP_NASA_POWER_INGESTION"
"""Truthy : '1', 'true', 'yes'. Même variable que journalier et mensuel."""


def _ingestion_doit_etre_skip() -> bool:
    """Vrai si ``KUMA_SKIP_NASA_POWER_INGESTION`` est truthy."""
    return doit_etre_skip(_VARIABLE_ENV_SKIP_INGESTION)


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


def _lignes_mesures(
    valeurs_par_cle: dict[str, float], serie_id: int, niveau_derive: str
) -> Iterator[dict[str, object]]:
    """Lignes d'une série pour une année ; clés non conformes et sentinelles écartées."""
    for cle, valeur in valeurs_par_cle.items():
        instant = _parse_cle_yyyymmddhh(cle)
        if instant is None:
            continue
        if valeur == SENTINELLE_VALEUR_MANQUANTE:
            continue
        yield {
            "serie_id": serie_id,
            "instant_mesure": instant,
            "valeur": float(valeur),
            "niveau_confiance_derive": niveau_derive,
        }


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

    contexte = contexte_serie(session, code_serie)
    if contexte is None:
        raise RuntimeError(
            f"Serie {code_serie!r} introuvable dans series_metadonnees. "
            f"Verifier que la migration de seed correspondante a bien ete appliquee."
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
        lignes_a_inserer.extend(
            _lignes_mesures(
                response.properties.parameter[parametre_nasa],
                contexte.serie_id,
                contexte.niveau_derive,
            )
        )

    if not lignes_a_inserer:
        return 0

    inserer_mesures(session, "mesures_ressource_horaires", lignes_a_inserer)
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

    contexte_par_grandeur = contexte_series_groupe(
        session,
        codes_series,
        mapping_grandeur_parametre_nasa,
        verification_seed="Vérifier le seed de la migration appelante.",
    )

    parametres_demandes = sorted(
        {mapping_grandeur_parametre_nasa[g] for g in contexte_par_grandeur}
    )
    decompte_par_serie: dict[str, int] = {
        ctx.code_serie: 0 for ctx in contexte_par_grandeur.values()
    }
    tampon: list[dict[str, object]] = []

    def _vider_tampon() -> None:
        if not tampon:
            return
        inserer_mesures(session, "mesures_ressource_horaires", tampon)
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
            for ligne in _lignes_mesures(
                response.properties.parameter[parametre_nasa], ctx.serie_id, ctx.niveau_derive
            ):
                tampon.append(ligne)
                decompte_par_serie[ctx.code_serie] += 1
                if len(tampon) >= _TAILLE_LOT_INSERT:
                    _vider_tampon()

    _vider_tampon()
    session.flush()
    return decompte_par_serie

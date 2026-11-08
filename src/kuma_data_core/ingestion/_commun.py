"""Briques partagées des modules d'ingestion.

Interrupteur d'ingestion par variable d'environnement, contexte des séries
cibles (identifiant et niveau de confiance dérivé), insertion des mesures et
écart relatif entre un payload live et le seed committé.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.editorial.niveaux_confiance import calculer_niveau_confiance_derive
from kuma_data_core.external.nasa_power import SENTINELLE_VALEUR_MANQUANTE

_SQL_CONTEXTE_SERIES: str = """
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

_SQL_INSERT_MESURES: dict[str, str] = {
    "mesures_ressource": """
        INSERT INTO mesures_ressource
            (serie_id, instant_mesure, valeur, niveau_confiance_derive)
        VALUES
            (:serie_id, :instant_mesure, :valeur, :niveau_confiance_derive)
    """,
    "mesures_ressource_horaires": """
        INSERT INTO mesures_ressource_horaires
            (serie_id, instant_mesure, valeur, niveau_confiance_derive)
        VALUES
            (:serie_id, :instant_mesure, :valeur, :niveau_confiance_derive)
    """,
    "mesures_ressource_mensuelles": """
        INSERT INTO mesures_ressource_mensuelles
            (serie_id, annee, mois, valeur, niveau_confiance_derive)
        VALUES
            (:serie_id, :annee, :mois, :valeur, :niveau_confiance_derive)
    """,
}

_EPSILON_REFERENCE: float = 1e-9
"""Plancher du dénominateur : une référence nulle ne divise pas par zéro."""


def doit_etre_skip(nom_variable: str) -> bool:
    """Vrai si la variable d'environnement vaut '1', 'true' ou 'yes' (casse ignorée)."""
    valeur = os.environ.get(nom_variable, "").strip().lower()
    return valeur in ("1", "true", "yes")


class ContexteSerie(NamedTuple):
    """Série cible d'une ingestion et niveau de confiance de ses lignes."""

    serie_id: int
    code_serie: str
    grandeur_code: str
    niveau_derive: str


def contexte_series(session: Session, codes: Sequence[str]) -> list[ContexteSerie]:
    """Séries ``codes`` présentes en base, dans l'ordre renvoyé par la requête.

    Le niveau dérivé est calculé par série (méthode de collecte et fiabilité
    de la source), sans supposer qu'elles les partagent.
    """
    rows = session.execute(text(_SQL_CONTEXTE_SERIES), {"codes": list(codes)}).all()
    return [
        ContexteSerie(
            serie_id=int(row.serie_id),
            code_serie=str(row.code_serie),
            grandeur_code=row.grandeur_code,
            niveau_derive=calculer_niveau_confiance_derive(
                methode_collecte=row.methode_collecte,
                fiabilite_source=row.fiabilite_source,
            ),
        )
        for row in rows
    ]


def contexte_serie(session: Session, code: str) -> ContexteSerie | None:
    """Série ``code`` (``None`` si absente ; le code est unique en base)."""
    contextes = contexte_series(session, [code])
    return contextes[0] if contextes else None


def contexte_series_groupe(
    session: Session,
    codes_series: Sequence[str],
    mapping_grandeur_parametre_nasa: Mapping[str, str],
    *,
    verification_seed: str,
) -> dict[str, ContexteSerie]:
    """Contexte des séries d'un appel multi-paramètres, indexé par grandeur.

    ``RuntimeError`` si une série manque (message terminé par
    ``verification_seed``) ou si une grandeur n'a pas de paramètre NASA mappé.
    """
    contextes = contexte_series(session, codes_series)
    if len(contextes) != len(codes_series):
        codes_trouves = {c.code_serie for c in contextes}
        codes_manquants = set(codes_series) - codes_trouves
        raise RuntimeError(
            f"Séries introuvables dans series_metadonnees : {sorted(codes_manquants)}. "
            f"{verification_seed}"
        )
    grandeurs_manquantes = {c.grandeur_code for c in contextes} - set(
        mapping_grandeur_parametre_nasa
    )
    if grandeurs_manquantes:
        raise RuntimeError(
            f"Grandeurs sans paramètre NASA POWER mappé : {sorted(grandeurs_manquantes)}. "
            f"Vérifier mapping_grandeur_parametre_nasa."
        )
    return {c.grandeur_code: c for c in contextes}


def inserer_mesures(session: Session, table: str, lignes: Sequence[Mapping[str, object]]) -> None:
    """INSERT en lot dans ``table`` ; statut, validité et audit restent aux server_defaults."""
    session.execute(text(_SQL_INSERT_MESURES[table]), lignes)


def ecart_relatif(valeur: float, reference: float) -> float:
    """``|valeur - reference| / max(|reference|, eps)``."""
    return abs(valeur - reference) / max(abs(reference), _EPSILON_REFERENCE)


def ecart_relatif_max_parametres(
    payload_live: Mapping[str, Any],
    payload_seed: Mapping[str, Any],
    *,
    cle_max: str | None = None,
) -> float:
    """Max de l'écart relatif live/seed sur ``properties.parameter`` (0.0 si vide).

    Parcourt les clés du seed ; ignore celles au-delà de ``cle_max``, celles
    absentes du live et les paires où l'un des deux vaut la sentinelle NASA.
    """
    seed_params = payload_seed["properties"]["parameter"]
    live_params = payload_live["properties"]["parameter"]
    ecart_max = 0.0
    for nom, seed_vals in seed_params.items():
        live_vals = live_params.get(nom, {})
        for cle, v_seed in seed_vals.items():
            if cle_max is not None and cle > cle_max:
                continue
            v_live = live_vals.get(cle)
            if v_live is None:
                continue
            if v_seed == SENTINELLE_VALEUR_MANQUANTE or v_live == SENTINELLE_VALEUR_MANQUANTE:
                continue
            ecart_max = max(ecart_max, ecart_relatif(v_live, v_seed))
    return ecart_max

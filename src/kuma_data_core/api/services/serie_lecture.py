"""Résolution, sans I/O, de la table de mesures d'une série."""

from __future__ import annotations

from enum import StrEnum


class TableMesures(StrEnum):
    """Tables-cibles des mesures pour les endpoints `/api/v1/series`."""

    JOURNALIER = "mesures_ressource"
    MENSUEL_RESSOURCE = "mesures_ressource_mensuelles"
    HORAIRE = "mesures_ressource_horaires"
    GRANDEURS_METIER = "grandeurs_metier"


def resolve_table_from_series_metadata(
    source_code: str,
    granularite: str | None,
) -> TableMesures:
    """Route d'abord par source (``kuma_calculs`` -> ``grandeurs_metier``), puis par granularité.

    Lève ``ValueError`` sur toute autre série sans granularité reconnue : une
    métadonnée incohérente doit échouer bruyamment.
    """
    if source_code == "kuma_calculs":
        return TableMesures.GRANDEURS_METIER
    if granularite == "horaire":
        return TableMesures.HORAIRE
    if granularite == "mensuel":
        return TableMesures.MENSUEL_RESSOURCE
    if granularite == "journalier":
        return TableMesures.JOURNALIER
    raise ValueError(
        f"Routage non resolu pour resolve_table_from_series_metadata : "
        f"source={source_code!r}, granularite={granularite!r}. Une serie "
        f"non-kuma_calculs doit porter une granularite "
        f"'journalier'/'mensuel'/'horaire' (cf. migration 052, dette D-36)."
    )

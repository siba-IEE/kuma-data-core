"""Table de mesures où lire une série, d'après ses métadonnées.

Les séries ``kuma_calculs`` sont dans ``grandeurs_metier`` (leur granularité
est NULL) ; les autres sont routées par ``series_metadonnees.granularite``.
"""

from __future__ import annotations

from enum import StrEnum


class TableMesures(StrEnum):
    """Tables de mesures lues par les endpoints ``/v1/series``."""

    JOURNALIER = "mesures_ressource"
    MENSUEL_RESSOURCE = "mesures_ressource_mensuelles"
    HORAIRE = "mesures_ressource_horaires"
    GRANDEURS_METIER = "grandeurs_metier"


def resolve_table_from_series_metadata(
    source_code: str,
    granularite: str | None,
) -> TableMesures:
    """Table de mesures d'une série : par source d'abord, par granularité ensuite.

    ``source_code`` est ``sources.code``, ``granularite`` est
    ``series_metadonnees.granularite``. Lève ``ValueError`` si une série hors
    ``kuma_calculs`` n'a pas une granularité ``journalier``, ``mensuel`` ou
    ``horaire`` : une métadonnée incohérente ne doit pas passer en silence.
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

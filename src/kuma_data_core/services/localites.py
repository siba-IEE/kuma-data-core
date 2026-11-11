"""Coordonnées des localités, lues une fois dans la table ``localites``.

Le cache n'est jamais invalidé : après une modification de la table, appeler
``_charger_coordonnees.cache_clear()``.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import text

from kuma_data_core.db.session import get_session_factory


@lru_cache(maxsize=1)
def _charger_coordonnees() -> dict[str, tuple[float, float]]:
    """``{code: (latitude, longitude)}`` des localités actives qui ont des coordonnées."""
    factory = get_session_factory()
    with factory() as session:
        rows = session.execute(
            text(
                "SELECT code, latitude, longitude FROM localites "
                "WHERE actif = TRUE "
                "AND latitude IS NOT NULL AND longitude IS NOT NULL"
            )
        ).all()
    return {row.code: (float(row.latitude), float(row.longitude)) for row in rows}


def coordonnees_localite(code: str) -> tuple[float, float]:
    """``(latitude, longitude)`` en degrés décimaux WGS84 d'une localité.

    ``code`` est le code naturel (``"gin_kindia"``). Lève ``KeyError`` si la
    localité est inconnue, inactive ou sans coordonnées.
    """
    return _charger_coordonnees()[code]

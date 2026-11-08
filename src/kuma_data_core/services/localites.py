"""Coordonnées des localités, lues une fois dans ``localites`` puis gardées en mémoire.

Pas d'invalidation automatique : ``_charger_coordonnees.cache_clear()``
force un rechargement.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import text

from kuma_data_core.db.session import get_session_factory


@lru_cache(maxsize=1)
def _charger_coordonnees() -> dict[str, tuple[float, float]]:
    """``{code: (latitude, longitude)}`` des localités actives ayant des coordonnées."""
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
    """``(latitude, longitude)`` WGS84 ; ``KeyError`` si localité absente ou sans coordonnées."""
    return _charger_coordonnees()[code]

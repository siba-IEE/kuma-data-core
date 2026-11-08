"""``Base`` déclarative et convention de nommage (``pk_``, ``fk_``, ``uq_``, ``ck_``, ``idx_``).

Des noms reproductibles entre ``create_all()`` et les migrations Alembic
(``docs/conventions/01-naming.md``).
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION: dict[str, str] = {
    "ix": "idx_%(table_name)s_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s__%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Classe de base pour tous les modèles SQLAlchemy du projet."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

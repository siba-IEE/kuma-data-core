"""Fixtures pour les tests d'intégration de modèles SQLAlchemy.

Premier conftest de tests d'intégration de table dans le projet.
Fournit ``db_session`` : une session
SQLAlchemy isolée par test via une transaction extérieure systématiquement
rollback à la fin (pattern « connection-as-transaction »).

Toutes les écritures faites pendant un test (y compris celles produites
par les triggers d'audit) sont annulées au rollback. Les triggers
``AFTER ROW`` se déclenchent quand même au ``flush()``, et leurs effets
sont visibles dans la même transaction (lecture sur la même connexion).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from kuma_data_core.db.session import get_engine
from tests._migrations import BaseEphemere, base_alembic_ephemere


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Session SQLAlchemy isolée par test, rollback en sortie.

    Utilise ``join_transaction_mode="create_savepoint"`` (SQLAlchemy 2.x)
    pour que les ``session.commit()`` / ``session.begin_nested()`` du
    code testé manipulent des SAVEPOINTs internes à la transaction
    extérieure, qui est rollback à la fin du test.
    """
    engine = get_engine()
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def base_ephemere() -> Iterator[BaseEphemere]:
    """Base PostgreSQL vide propre au test, supprimée en sortie même en échec.

    Pour les aller-retours Alembic : la base partagée, à head, ne peut pas
    redescendre sous la migration 046 (downgrade non réversible).
    """
    with base_alembic_ephemere() as base:
        yield base

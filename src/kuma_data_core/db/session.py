"""Moteur et fabrique de sessions SQLAlchemy pour Kuma Data Core.

Le moteur est créé paresseusement (``lru_cache``) afin qu'une simple
importation du module n'ouvre pas de connexion réseau. La fabrique de
sessions est elle aussi memoizée, et reste utilisable comme point
d'entrée unique tant que la couche FastAPI n'introduit pas son propre
gestionnaire de contexte.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from kuma_data_core.core.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Retourne le moteur SQLAlchemy unique du processus.

    ``pool_pre_ping=True`` valide chaque connexion avant usage : utile
    en développement où PostgreSQL peut redémarrer indépendamment de
    l'application.
    """
    settings = get_settings()
    return create_engine(
        settings.database_url,
        echo=False,
        future=True,
        pool_pre_ping=True,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Retourne la fabrique de sessions associée au moteur unique."""
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )


def obtenir_session() -> Iterator[Session]:
    """Dépendance FastAPI : ouvre une session, la cède, la ferme.

    Utilisée via ``Depends(obtenir_session)`` dans les routeurs. Le
    contextmanager garantit la fermeture (rollback implicite si
    l'endpoint a levé une exception, commit explicite à la charge du
    code applicatif).

    Implémentation **synchrone** alignée sur l'engine sync du projet.
    FastAPI exécute les handlers ``def`` (non ``async def``) dans un
    threadpool, ce qui rend l'usage de psycopg3 sync sans risque pour
    la boucle d'événements en phase 0.
    """
    factory = get_session_factory()
    with factory() as session:
        yield session

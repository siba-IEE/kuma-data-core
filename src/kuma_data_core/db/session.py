"""Moteurs et fabrique de sessions, créés paresseusement : importer n'ouvre aucune connexion."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from kuma_data_core.core.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Moteur unique ; ``pool_pre_ping`` survit aux redémarrages de PostgreSQL."""
    settings = get_settings()
    return create_engine(
        settings.database_url,
        echo=False,
        future=True,
        pool_pre_ping=True,
    )


@lru_cache(maxsize=4)
def _engine_pour_url(url: str) -> Engine:
    """Moteur memoizé par DSN (base de service, tests)."""
    return create_engine(url, echo=False, future=True, pool_pre_ping=True)


def get_engine_meta() -> Engine:
    """Moteur de la base de service ; lève si ``META_DB`` n'est pas configurée."""
    url = get_settings().database_url_meta
    if url is None:
        raise RuntimeError("META_DB non configurée : pas de base de service sur ce déploiement.")
    return _engine_pour_url(url)


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
    """Dépendance FastAPI : session fermée en fin de requête, commit à la charge de l'endpoint.

    Synchrone : FastAPI exécute les handlers ``def`` dans un threadpool.
    """
    factory = get_session_factory()
    with factory() as session:
        yield session

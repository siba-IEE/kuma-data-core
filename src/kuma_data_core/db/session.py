"""Moteur et fabrique de sessions SQLAlchemy.

Le moteur et la fabrique sont créés à la première demande (``lru_cache``) :
importer ce module n'ouvre aucune connexion.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from kuma_data_core.core.config import get_settings

# Fuseau de session fixé : les regroupements par jour (``instant.date()``)
# ne doivent pas dépendre du réglage du serveur PostgreSQL.
_ARGUMENTS_CONNEXION = {"options": "-c timezone=UTC"}


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Moteur SQLAlchemy unique du processus.

    ``pool_pre_ping=True`` valide chaque connexion avant usage : PostgreSQL
    peut redémarrer indépendamment de l'application.
    """
    settings = get_settings()
    return create_engine(
        settings.database_url,
        echo=False,
        future=True,
        pool_pre_ping=True,
        connect_args=_ARGUMENTS_CONNEXION,
    )


@lru_cache(maxsize=4)
def _engine_pour_url(url: str) -> Engine:
    """Moteur memoizé par DSN (base de service, tests)."""
    return create_engine(
        url, echo=False, future=True, pool_pre_ping=True, connect_args=_ARGUMENTS_CONNEXION
    )


def get_engine_meta() -> Engine:
    """Moteur de la base de service ``kuma_api_meta`` (ADR-0003).

    Lève ``RuntimeError`` si ``META_DB`` n'est pas configurée.
    """
    url = get_settings().database_url_meta
    if url is None:
        raise RuntimeError("META_DB non configurée : pas de base de service sur ce déploiement.")
    return _engine_pour_url(url)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Fabrique de sessions liée au moteur unique."""
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )


def obtenir_session() -> Iterator[Session]:
    """Dépendance FastAPI : ouvre une session, la cède, puis la ferme.

    Aucun commit n'est fait ici : il reste à la charge du code appelant.
    Synchrone, comme le moteur : FastAPI exécute les handlers ``def`` dans un
    pool de threads, hors de la boucle d'événements.
    """
    factory = get_session_factory()
    with factory() as session:
        yield session

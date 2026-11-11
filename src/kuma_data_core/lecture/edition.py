"""Édition publiée servie par le déploiement, et sonde de connectivité de la base.

La table ``edition_metadonnees`` n'existe que dans une édition publiée : son
absence est un état normal, rendu par ``None``.
"""

from __future__ import annotations

from datetime import date
from typing import NamedTuple

from sqlalchemy import Connection, text
from sqlalchemy.orm import Session


class EditionPubliee(NamedTuple):
    """Ligne unique d'``edition_metadonnees``."""

    edition_id: str
    date_publication: date
    revision_source: str


def _table_edition_presente(connexion: Session | Connection) -> bool:
    """Vrai si ``edition_metadonnees`` existe.

    ``to_regclass`` évite de dépendre d'une exception pour le cas « table absente ».
    """
    presente = connexion.execute(text("SELECT to_regclass('public.edition_metadonnees')")).scalar()
    return presente is not None


def lire_edition(session: Session) -> EditionPubliee | None:
    """Édition servie, ou ``None`` si ce déploiement n'en sert pas (table absente ou vide)."""
    if not _table_edition_presente(session):
        return None
    row = session.execute(
        text(
            """
            SELECT edition_id, date_publication, revision_source
            FROM edition_metadonnees
            LIMIT 1
            """
        )
    ).first()
    if row is None:
        return None
    return EditionPubliee(
        edition_id=str(row.edition_id),
        date_publication=row.date_publication,
        revision_source=str(row.revision_source),
    )


def lire_identifiant_edition(connexion: Connection) -> str | None:
    """Identifiant de l'édition servie, ou ``None`` si ce déploiement n'en sert pas."""
    if not _table_edition_presente(connexion):
        return None
    edition_id = connexion.execute(
        text("SELECT edition_id FROM edition_metadonnees LIMIT 1")
    ).scalar()
    return str(edition_id) if edition_id is not None else None


def sonder_base(session: Session) -> None:
    """Exécute ``SELECT 1`` : une exception signale une base injoignable."""
    session.execute(text("SELECT 1"))

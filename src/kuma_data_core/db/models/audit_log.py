"""Modèle SQLAlchemy de la table ``audit_log``, en lecture seule côté application.

Les écritures viennent exclusivement de la fonction PL/pgSQL
``kuma_log_audit()``, déclenchée par les triggers ``trg_audit_*`` des tables
auditées (voir ``docs/architecture/03-audit.md``) : aucun code Python ne doit
insérer, modifier ni supprimer de ligne ici. Le modèle existe pour
qu'``alembic check`` compare cette définition à la base.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    Identity,
    Index,
    Text,
    desc,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from kuma_data_core.db.base import Base


class AuditLog(Base):
    """Journal d'audit centralisé de Kuma Data Core (lecture seule)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(start=1, increment=1), primary_key=True)

    table_auditee: Mapped[str] = mapped_column(Text, nullable=False)
    schema_audite: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'public'")
    )
    type_operation: Mapped[str] = mapped_column(CHAR(length=1), nullable=False)
    id_ligne_auditee: Mapped[str] = mapped_column(Text, nullable=False)

    champs_modifies: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    valeurs_avant: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    valeurs_apres: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    utilisateur_pg: Mapped[str] = mapped_column(Text, nullable=False)
    auteur_applicatif: Mapped[str | None] = mapped_column(Text, nullable=True)
    adresse_client: Mapped[str | None] = mapped_column(INET, nullable=True)

    # clock_timestamp() (instant réel) et non now() (début de transaction).
    horodatage: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )

    # Les index trient ``horodatage`` par ordre décroissant : les requêtes lisent
    # d'abord les événements les plus récents.
    __table_args__ = (
        CheckConstraint(
            "type_operation IN ('I', 'U', 'D')",
            name="ck_audit_log_type_operation",
        ),
        Index(
            "idx_audit_log_table_horodatage",
            "schema_audite",
            "table_auditee",
            desc("horodatage"),
        ),
        Index("idx_audit_log_horodatage", desc("horodatage")),
        Index(
            "idx_audit_log_utilisateur_pg",
            "utilisateur_pg",
            desc("horodatage"),
        ),
        Index(
            "idx_audit_log_auteur_applicatif",
            "auteur_applicatif",
            desc("horodatage"),
            postgresql_where=text("auteur_applicatif IS NOT NULL"),
        ),
        Index(
            "idx_audit_log_ligne",
            "schema_audite",
            "table_auditee",
            "id_ligne_auditee",
            desc("horodatage"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog(id={self.id}, table={self.table_auditee!r}, "
            f"op={self.type_operation!r}, ligne={self.id_ligne_auditee!r})>"
        )

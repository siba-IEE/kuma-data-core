"""Modèle SQLAlchemy de la table ``contributeurs``.

Les colonnes d'audit ``cree_par`` et ``modifie_par`` des autres tables pointent
ici. La table est auto-référente : son premier contributeur a ``cree_par`` et
``modifie_par`` à NULL, faute d'antécédent.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from kuma_data_core.db.base import Base


class Contributeur(Base):
    """Auteur ou source humaine derrière toute donnée du noyau."""

    __tablename__ = "contributeurs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(start=1, increment=1), primary_key=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    nom_complet: Mapped[str] = mapped_column(Text, nullable=False)
    nom_court: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_principal: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    type_contributeur: Mapped[str] = mapped_column(String(50), nullable=False)
    statut: Mapped[str] = mapped_column(String(50), nullable=False)

    biographie: Mapped[str | None] = mapped_column(Text, nullable=True)
    affiliation_principale: Mapped[str | None] = mapped_column(Text, nullable=True)
    pays_iso3: Mapped[str | None] = mapped_column(String(3), nullable=True)
    url_publique: Mapped[str | None] = mapped_column(Text, nullable=True)
    orcid: Mapped[str | None] = mapped_column(String(19), nullable=True)
    domaines_expertise: Mapped[list[str] | None] = mapped_column(ARRAY(Text()), nullable=True)

    date_premier_engagement: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_dernier_engagement: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes_internes: Mapped[str | None] = mapped_column(Text, nullable=True)

    actif: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    desactive_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cree_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    cree_par: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("contributeurs.id", name="fk_contributeurs_cree_par__contributeurs"),
        nullable=True,
    )
    modifie_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    modifie_par: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("contributeurs.id", name="fk_contributeurs_modifie_par__contributeurs"),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "type_contributeur IN ("
            "'editeur_principal', 'contributeur_regulier', 'contributeur_invite', "
            "'expert_externe', 'institution', 'agent_automatique')",
            name="ck_contributeurs_type_valide",
        ),
        CheckConstraint(
            "statut IN ('actif', 'inactif', 'archive', 'suspendu')",
            name="ck_contributeurs_statut_valide",
        ),
        CheckConstraint(
            "(actif = TRUE AND desactive_le IS NULL) "
            "OR (actif = FALSE AND desactive_le IS NOT NULL)",
            name="ck_contributeurs_actif_desactive_coherent",
        ),
        CheckConstraint(
            "pays_iso3 IS NULL OR pays_iso3 ~ '^[A-Z]{3}$'",
            name="ck_contributeurs_pays_iso3_format",
        ),
        CheckConstraint(
            "orcid IS NULL OR orcid ~ '^[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9X]{4}$'",
            name="ck_contributeurs_orcid_format",
        ),
        Index("idx_contributeurs_actif", "actif"),
        Index("idx_contributeurs_type_contributeur", "type_contributeur"),
        Index("idx_contributeurs_statut", "statut"),
        Index("idx_contributeurs_pays_iso3", "pays_iso3"),
    )

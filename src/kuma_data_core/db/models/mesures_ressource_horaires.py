"""Modèle SQLAlchemy de la table ``mesures_ressource_horaires`` : mesures horaires ingérées.

Identité métier : ``(serie_id, instant_mesure)``. ``instant_mesure`` est un
``TIMESTAMPTZ`` en UTC : le contrôle qualité horaire calcule la position du
soleil (angle zénithal) et ne doit dépendre d'aucun fuseau. Même versionnement
que ``mesures_ressource``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kuma_data_core.db.base import Base
from kuma_data_core.db.models.series_metadonnees import SerieMetadonnees


class MesureRessourceHoraire(Base):
    """Mesure horaire d'une grandeur brute ingérée depuis une source externe."""

    __tablename__ = "mesures_ressource_horaires"

    id: Mapped[int] = mapped_column(BigInteger, Identity(start=1, increment=1), primary_key=True)

    serie_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "series_metadonnees.id",
            name="fk_mesures_ressource_horaires_serie_id__series_metadonnees",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    instant_mesure: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    valeur: Mapped[float] = mapped_column(Float(precision=53), nullable=False)

    valide_du: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    valide_au: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    statut: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'brut'"),
    )

    niveau_confiance_derive: Mapped[str] = mapped_column(String(1), nullable=False)
    niveau_confiance_override: Mapped[str | None] = mapped_column(String(1), nullable=True)

    commentaire_editorial: Mapped[str | None] = mapped_column(Text, nullable=True)

    cree_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    cree_par: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "contributeurs.id",
            name="fk_mesures_ressource_horaires_cree_par__contributeurs",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    modifie_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    modifie_par: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "contributeurs.id",
            name="fk_mesures_ressource_horaires_modifie_par__contributeurs",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    serie: Mapped[SerieMetadonnees] = relationship(
        SerieMetadonnees,
        lazy="select",
        foreign_keys=[serie_id],
    )

    @hybrid_property
    def niveau_effectif(self) -> str:
        """Niveau de confiance à utiliser : l'override s'il existe, sinon le niveau dérivé."""
        return (
            self.niveau_confiance_override
            if self.niveau_confiance_override is not None
            else self.niveau_confiance_derive
        )

    # La contrainte EXCLUDE et le trigger d'audit sont posés en migration :
    # Alembic ne compare pas les EXCLUDE.
    __table_args__ = (
        CheckConstraint(
            "statut IN ('brut', 'valide_auto', 'valide_humain', 'publie', 'deprecie')",
            name="ck_mesures_ressource_horaires_statut_valide",
        ),
        CheckConstraint(
            "niveau_confiance_derive IN ('A', 'B', 'C')",
            name="ck_mesures_ressource_horaires_niveau_confiance_derive_valide",
        ),
        CheckConstraint(
            "niveau_confiance_override IS NULL OR niveau_confiance_override IN ('A', 'B', 'C')",
            name="ck_mesures_ressource_horaires_niveau_confiance_override_valide",
        ),
        CheckConstraint(
            "valide_au IS NULL OR valide_au > valide_du",
            name="ck_mesures_ressource_horaires_periode_coherente",
        ),
        # Index partiel sur les lignes courantes, les plus lues.
        Index(
            "idx_mesures_ressource_horaires_courantes",
            "serie_id",
            "instant_mesure",
            postgresql_where=text("valide_au IS NULL"),
        ),
        {
            "comment": (
                "Mesures horaires ingerees depuis sources externes (NASA POWER, "
                "Vague 3). Pendant horaire de mesures_ressource (journalier) et "
                "mesures_ressource_mensuelles (mensuel). instant_mesure en "
                "TIMESTAMPTZ (UTC) pour le controle qualite horaire (position "
                "solaire sans ambiguite de fuseau). Versioning temporel par "
                "(valide_du, valide_au) + EXCLUDE BTree-GiST sur identite metier "
                "(serie_id, instant_mesure). Statut editorial et niveau de "
                "confiance derive/override par couche service editoriale."
            ),
        },
    )

    def __repr__(self) -> str:
        return (
            f"<MesureRessourceHoraire(id={self.id}, serie_id={self.serie_id}, "
            f"instant_mesure={self.instant_mesure!r}, valeur={self.valeur})>"
        )

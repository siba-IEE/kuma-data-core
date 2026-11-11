"""Modèle SQLAlchemy de la table ``mesures_ressource`` : mesures journalières ingérées.

Identité métier : ``(serie_id, instant_mesure)``, ``instant_mesure`` étant une
date ; la localité, la grandeur et la source sont portées par
``series_metadonnees``.

Les versions successives d'une mesure sont bornées par ``valide_du`` /
``valide_au``. La contrainte EXCLUDE qui interdit leur chevauchement est posée
en migration et n'apparaît pas dans ce modèle.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
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


class MesureRessource(Base):
    """Mesure journalière d'une grandeur brute ingérée depuis une source externe."""

    __tablename__ = "mesures_ressource"

    id: Mapped[int] = mapped_column(BigInteger, Identity(start=1, increment=1), primary_key=True)

    serie_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "series_metadonnees.id",
            name="fk_mesures_ressource_serie_id__series_metadonnees",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    instant_mesure: Mapped[date] = mapped_column(Date, nullable=False)

    valeur: Mapped[float] = mapped_column(Float(precision=53), nullable=False)

    valide_du: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    valide_au: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    statut: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'brut'"),
        comment=(
            "Statut editorial Kuma : brut (importe non valide), valide_auto "
            "(controle qualite automatique passe), valide_humain (validation "
            "editoriale humaine), publie (publie publiquement), deprecie "
            "(retire du circuit editorial). Transitions encadrees par la "
            "couche service Python (cf. kuma_data_core.editorial.statuts)."
        ),
    )

    niveau_confiance_derive: Mapped[str] = mapped_column(
        String(1),
        nullable=False,
        comment=(
            "Niveau de confiance dérivé par la couche de service selon la méthode de collecte "
            "de la série et la fiabilité de sa source. A = haute, B = moyenne, C = basse. "
            "Règles de dérivation : voir "
            "https://github.com/siba-IEE/kuma-data-core/blob/main/docs/contribution/confiance-et-statuts.md"
        ),
    )
    niveau_confiance_override: Mapped[str | None] = mapped_column(
        String(1),
        nullable=True,
        comment=(
            "Override editorial du niveau derive. NULL = pas override (valeur "
            "effective = derive). Sinon valeur effective = override. Pose par "
            "la fonction service overrider_niveau_confiance avec justification "
            "obligatoire dans commentaire_editorial."
        ),
    )

    commentaire_editorial: Mapped[str | None] = mapped_column(Text, nullable=True)

    cree_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    cree_par: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "contributeurs.id",
            name="fk_mesures_ressource_cree_par__contributeurs",
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
            name="fk_mesures_ressource_modifie_par__contributeurs",
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
        """Niveau de confiance à utiliser : l'override s'il existe, sinon le niveau dérivé.

        Même règle que la vue SQL ``v_mesures_avec_niveau_effectif``.
        """
        return (
            self.niveau_confiance_override
            if self.niveau_confiance_override is not None
            else self.niveau_confiance_derive
        )

    __table_args__ = (
        CheckConstraint(
            "statut IN ('brut', 'valide_auto', 'valide_humain', 'publie', 'deprecie')",
            name="ck_mesures_ressource_statut_valide",
        ),
        CheckConstraint(
            "niveau_confiance_derive IN ('A', 'B', 'C')",
            name="ck_mesures_ressource_niveau_confiance_derive_valide",
        ),
        CheckConstraint(
            "niveau_confiance_override IS NULL OR niveau_confiance_override IN ('A', 'B', 'C')",
            name="ck_mesures_ressource_niveau_confiance_override_valide",
        ),
        CheckConstraint(
            "valide_au IS NULL OR valide_au > valide_du",
            name="ck_mesures_ressource_periode_coherente",
        ),
        # Index partiel sur les lignes courantes, les plus lues.
        Index(
            "idx_mesures_ressource_courantes",
            "serie_id",
            "instant_mesure",
            postgresql_where=text("valide_au IS NULL"),
        ),
        # ``alembic check`` compare ce commentaire de table à la base.
        {
            "comment": (
                "Mesures journalières ingérées depuis les sources externes. Versionnement "
                "temporel par (valide_du, valide_au) et contrainte EXCLUDE BTree-GiST sur "
                "l'identité métier (serie_id, instant_mesure). Statut éditorial et niveau de "
                "confiance dérivé ou forcé par la couche de service éditoriale."
            ),
        },
    )

    def __repr__(self) -> str:
        return (
            f"<MesureRessource(id={self.id}, serie_id={self.serie_id}, "
            f"instant_mesure={self.instant_mesure!r}, valeur={self.valeur})>"
        )

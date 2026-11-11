"""Modèle SQLAlchemy de la table ``grandeurs_metier`` : grandeurs calculées et stockées.

Identité métier : ``(grandeur_code, localite_id, periode_type, annee_debut,
annee_fin, COALESCE(mois, 0), version_formule)``. ``version_formule`` en fait
partie pour que les lignes de deux versions d'une même formule coexistent.

Les versions successives d'une ligne sont bornées par ``valide_du`` /
``valide_au``. La contrainte EXCLUDE qui interdit leur chevauchement est posée
en migration et n'apparaît pas dans ce modèle.
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
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kuma_data_core.db.base import Base
from kuma_data_core.db.models.series_metadonnees import SerieMetadonnees


class GrandeurMetier(Base):
    """Grandeur Kuma F1 stockée calculée à partir de mesures brutes."""

    __tablename__ = "grandeurs_metier"

    id: Mapped[int] = mapped_column(BigInteger, Identity(start=1, increment=1), primary_key=True)

    grandeur_code: Mapped[str] = mapped_column(
        String(80),
        ForeignKey(
            "grandeurs_referentiel.code",
            name="fk_grandeurs_metier_grandeur_code__grandeurs_referentiel",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    localite_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "localites.id",
            name="fk_grandeurs_metier_localite_id__localites",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    series_metadonnees_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "series_metadonnees.id",
            name="fk_grandeurs_metier_series_metadonnees_id__series_metadonnees",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    periode_type: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        comment=(
            "Granularité temporelle de la valeur : annuel (une valeur par année, mois NULL), "
            "mensuel (une valeur par mois, mois de 1 à 12) ou statique (une valeur pour toute "
            "la période annee_debut à annee_fin, mois NULL)."
        ),
    )
    annee_debut: Mapped[int] = mapped_column(Integer, nullable=False)
    annee_fin: Mapped[int] = mapped_column(Integer, nullable=False)
    mois: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version_formule: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment=(
            "Version de la formule de calcul en vigueur à l'insertion, liée à "
            "grandeurs_referentiel.version_formule_actuelle de la grandeur et incrémentée à "
            "chaque révision méthodologique. Incluse dans la contrainte EXCLUDE pour que deux "
            "versions coexistent après une révision."
        ),
    )

    # Nullable : un écart relatif n'est pas calculable quand la valeur SARAH-3
    # mensuelle est sous ``SEUIL_SARAH3_MIN_DEFAUT``
    # (``services/grandeurs/referentiels.py``).
    valeur: Mapped[float | None] = mapped_column(Float(precision=53), nullable=True)

    valide_du: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    valide_au: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    statut: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'brut'"),
        comment=(
            "Statut editorial Kuma : brut (calcule non valide), valide_auto "
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
            "de la série, la fiabilité de sa source et, pour une valeur calculée, le niveau de "
            "ses entrées. A = haute, B = moyenne, C = basse. Règles de dérivation : voir "
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
            name="fk_grandeurs_metier_cree_par__contributeurs",
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
            name="fk_grandeurs_metier_modifie_par__contributeurs",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    serie: Mapped[SerieMetadonnees] = relationship(
        SerieMetadonnees,
        lazy="select",
        foreign_keys=[series_metadonnees_id],
    )

    @hybrid_property
    def niveau_effectif(self) -> str:
        """Niveau de confiance à utiliser : l'override s'il existe, sinon le niveau dérivé.

        Même règle que la vue SQL ``v_grandeurs_metier_courantes``.
        """
        return (
            self.niveau_confiance_override
            if self.niveau_confiance_override is not None
            else self.niveau_confiance_derive
        )

    __table_args__ = (
        CheckConstraint(
            "periode_type IN ('mensuel', 'annuel', 'statique')",
            name="ck_grandeurs_metier_periode_type_valide",
        ),
        CheckConstraint(
            "(periode_type = 'annuel' AND mois IS NULL) "
            "OR (periode_type = 'mensuel' AND mois IS NOT NULL AND mois BETWEEN 1 AND 12) "
            "OR (periode_type = 'statique' AND mois IS NULL)",
            name="ck_grandeurs_metier_periode_coherente",
        ),
        CheckConstraint(
            "annee_fin >= annee_debut",
            name="ck_grandeurs_metier_annees_coherentes",
        ),
        CheckConstraint(
            "version_formule >= 1",
            name="ck_grandeurs_metier_version_formule_positive",
        ),
        CheckConstraint(
            "statut IN ('brut', 'valide_auto', 'valide_humain', 'publie', 'deprecie')",
            name="ck_grandeurs_metier_statut_valide",
        ),
        CheckConstraint(
            "niveau_confiance_derive IN ('A', 'B', 'C')",
            name="ck_grandeurs_metier_niveau_confiance_derive_valide",
        ),
        CheckConstraint(
            "niveau_confiance_override IS NULL OR niveau_confiance_override IN ('A', 'B', 'C')",
            name="ck_grandeurs_metier_niveau_confiance_override_valide",
        ),
        CheckConstraint(
            "valide_au IS NULL OR valide_au > valide_du",
            name="ck_grandeurs_metier_periode_validite_coherente",
        ),
        # Index partiel sur les lignes courantes, les plus lues.
        Index(
            "idx_grandeurs_metier_courantes",
            "grandeur_code",
            "localite_id",
            "periode_type",
            "annee_debut",
            "annee_fin",
            "mois",
            "version_formule",
            postgresql_where=text("valide_au IS NULL"),
        ),
        # ``alembic check`` compare ce commentaire de table à la base.
        {
            "comment": (
                "Grandeurs métier calculées par Kuma à partir des mesures : valeurs annuelles, "
                "mensuelles ou statiques (periode_type). Versionnement temporel par (valide_du,"
                " valide_au) et contrainte EXCLUDE BTree-GiST sur l'identité métier étendue à "
                "version_formule. Statut éditorial et niveau de confiance dérivé ou forcé par "
                "la couche de service éditoriale."
            ),
        },
    )

    def __repr__(self) -> str:
        return (
            f"<GrandeurMetier(id={self.id}, grandeur_code={self.grandeur_code!r}, "
            f"localite_id={self.localite_id}, periode_type={self.periode_type!r}, "
            f"annee_debut={self.annee_debut}, mois={self.mois}, "
            f"version_formule={self.version_formule}, valeur={self.valeur})>"
        )

"""Base de service ``kuma_api_meta`` : modèle et provisioning (ADR-0003, WP6).

La table ``cles_api`` est un **état du serveur**, pas une donnée
éditoriale : elle vit dans la base de service ``kuma_api_meta``,
persistante à travers les bascules d'édition (D1), et **hors lignée
Alembic** (D3) - ``alembic check`` garantit l'alignement modèles <-> base
de référence, une table absente de la référence casserait cet invariant.
D'où la ``BaseMeta`` déclarative distincte : ``Base.metadata`` de
référence ne voit jamais ``cles_api``, et le manifeste de publication
n'a rien à en dire (elle n'existe pas côté édition).

Les clés ne sont **jamais stockées en clair** : seule l'empreinte
SHA-256 est persistée, plus un préfixe non secret (``kuma_xxxxxxxx``)
qui sert d'identifiant public pour la révocation.

La table ``licences_solclim`` vit à côté : une clé API, qu'elle vienne du
self-service ou non, n'ouvre pas SolClim-3 à elle seule. Il faut qu'une
licence lui soit accordée par l'administrateur ; c'est elle qui donne
droit au bail signé de ``POST /v1/licence/bail``. Retirer la licence ôte
SolClim-3 sans toucher à la clé ; révoquer la clé coupe tout.

Provisioning : ``python -m kuma_data_core.db.meta`` crée les tables
(idempotent, ``create_all`` : une table déjà présente n'est pas touchée,
une table nouvelle est créée) dans la base désignée par ``META_DB``. À
exécuter avec le rôle administrateur après ``provisionner-serveur.sh``
(qui crée la base et les rôles, et pose les default privileges pour
``kuma_api_service``).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class BaseMeta(DeclarativeBase):
    """Base déclarative de la base de service (distincte de la référence)."""


class CleApi(BaseMeta):
    """Clé API self-service : empreinte, titulaire, cycle de vie."""

    __tablename__ = "cles_api"

    # === Identifiants ===
    id: Mapped[int] = mapped_column(BigInteger, Identity(start=1, increment=1), primary_key=True)
    # Empreinte SHA-256 (hex, 64 caractères) de la clé complète.
    cle_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # Préfixe non secret de la clé (``kuma_`` + 8 premiers caractères) :
    # identifiant public pour la révocation et le support. Non unique en
    # théorie (collision possible), la révocation opère par préfixe.
    prefixe: Mapped[str] = mapped_column(String(16), nullable=False)

    # === Titulaire ===
    email: Mapped[str] = mapped_column(Text, nullable=False)
    usage_prevu: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Adresse IP au moment de l'émission : support de la limite
    # d'émission par IP (seule surface d'écriture publique, D2).
    adresse_ip_creation: Mapped[str] = mapped_column(String(64), nullable=False)

    # === Quotas (consommés par le rate limiting, WP7) ===
    quota_journalier: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("5000")
    )

    # === Soft delete (révocation) ===
    actif: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    desactive_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # === Traçabilité (pas d'audit par triggers ici : base de service) ===
    cree_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "(actif = TRUE AND desactive_le IS NULL) "
            "OR (actif = FALSE AND desactive_le IS NOT NULL)",
            name="ck_cles_api_desactivation_coherente",
        ),
        CheckConstraint("quota_journalier > 0", name="ck_cles_api_quota_positif"),
        Index("idx_cles_api_prefixe", "prefixe"),
        Index("idx_cles_api_adresse_ip_creation", "adresse_ip_creation"),
    )


class LicenceSolclim(BaseMeta):
    """Licence d'usage de SolClim-3 accordée à une clé API : le droit au bail."""

    __tablename__ = "licences_solclim"

    # === Identifiants ===
    id: Mapped[int] = mapped_column(BigInteger, Identity(start=1, increment=1), primary_key=True)
    cle_api_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cles_api.id", name="fk_licences_solclim_cle_api_id"),
        nullable=False,
    )

    # === Titulaire ===
    # La personne qui utilise le logiciel, et son organisation : c'est ce
    # que le bail porte et ce que le rapport pourra citer.
    titulaire: Mapped[str] = mapped_column(Text, nullable=False)
    organisation: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes_internes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # === Terme ===
    # Fin de la licence ; ``None`` = sans terme. Le bail ne dépasse jamais
    # cette date, quelle que soit sa durée nominale.
    expire_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Dernier bail émis : dit qui se sert du logiciel, sans journal de plus.
    dernier_bail_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # === Soft delete (retrait de la licence) ===
    actif: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    desactive_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # === Traçabilité (pas d'audit par triggers ici : base de service) ===
    cree_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "(actif = TRUE AND desactive_le IS NULL) "
            "OR (actif = FALSE AND desactive_le IS NOT NULL)",
            name="ck_licences_solclim_desactivation_coherente",
        ),
        Index("idx_licences_solclim_cle_api_id", "cle_api_id"),
        # Une seule licence active par clé : en accorder une seconde
        # passe par le retrait de la première.
        Index(
            "uq_licences_solclim_cle_api_id_active",
            "cle_api_id",
            unique=True,
            postgresql_where=text("actif"),
        ),
    )


def creer_schema_meta() -> None:
    """Crée les tables de la base de service (idempotent).

    Lève si ``META_DB`` n'est pas configurée : on ne provisionne pas
    par accident la base de référence.
    """
    from kuma_data_core.core.config import get_settings
    from kuma_data_core.db.session import get_engine_meta

    if get_settings().meta_db is None:
        raise RuntimeError(
            "META_DB non configurée : le provisioning de la base de service "
            "exige de désigner explicitement sa cible (p.ex. kuma_api_meta)."
        )
    BaseMeta.metadata.create_all(get_engine_meta())


if __name__ == "__main__":
    creer_schema_meta()
    print("Schéma de la base de service créé (tables absentes ajoutées, présentes intactes).")

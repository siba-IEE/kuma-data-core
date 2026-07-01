"""Tests d'intégration de la table ``mesures_ressource``.

Couvre les tests de DDL, d'ingestion et de versioning :

- DDL et contraintes (table, EXCLUDE, 4 CHECK, index partiel, trigger audit)
- INSERT et validations
- Versioning temporel et rotation versionnée
- Statut éditorial machine d'état
- Niveau de confiance dérivé / override
- Ingestion réelle (1826 lignes Conakry GHI)
- Roundtrip Alembic (sous marker regression)

Pattern ``db_session`` fixture conftest.py.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kuma_data_core.db.models.audit_log import AuditLog
from kuma_data_core.db.models.mesures_ressource import MesureRessource
from kuma_data_core.editorial.niveaux_confiance import (
    calculer_niveau_confiance_derive,
    overrider_niveau_confiance,
)
from kuma_data_core.editorial.statuts import transition_statut
from kuma_data_core.editorial.versioning import roter_ligne_versionnee
from kuma_data_core.exceptions import TransitionEditorialeRefusee

pytestmark = pytest.mark.integration


CODE_SERIE_CONAKRY: str = "gin_conakry_ghi_nasa_power_2021_2025"


def _id_serie_conakry(db_session: Session) -> int:
    """Récupère l'id de la série Conakry GHI seedée par migration 016."""
    return int(
        db_session.execute(
            text("SELECT id FROM series_metadonnees WHERE code = :code"),
            {"code": CODE_SERIE_CONAKRY},
        ).scalar_one()
    )


# ---------------------------------------------------------------------------
# DDL et contraintes
# ---------------------------------------------------------------------------


def test_t01_table_existe_avec_colonnes(db_session: Session) -> None:
    """Table mesures_ressource créée avec les colonnes attendues."""
    rows = db_session.execute(
        text(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'mesures_ressource'
            ORDER BY ordinal_position
            """
        )
    ).all()
    noms_colonnes = {r.column_name for r in rows}
    attendus = {
        "id",
        "serie_id",
        "instant_mesure",
        "valeur",
        "valide_du",
        "valide_au",
        "statut",
        "niveau_confiance_derive",
        "niveau_confiance_override",
        "commentaire_editorial",
        "cree_le",
        "cree_par",
        "modifie_le",
        "modifie_par",
    }
    assert attendus.issubset(noms_colonnes)


def test_t02_btree_gist_extension_active(db_session: Session) -> None:
    """Extension btree_gist activée par migration 013."""
    r = db_session.execute(
        text("SELECT extname FROM pg_extension WHERE extname = 'btree_gist'")
    ).first()
    assert r is not None


def test_t03_exclude_constraint_existe(db_session: Session) -> None:
    """Contrainte EXCLUDE ex_mesures_ressource_identite_periode existe."""
    r = db_session.execute(
        text(
            """
            SELECT conname FROM pg_constraint
            WHERE conname = 'ex_mesures_ressource_identite_periode'
            """
        )
    ).first()
    assert r is not None


def test_t04_4_check_constraints_existent(db_session: Session) -> None:
    """4 CHECK constraints nommées correctement."""
    rows = db_session.execute(
        text(
            """
            SELECT conname FROM pg_constraint
            WHERE conrelid = 'mesures_ressource'::regclass
              AND contype = 'c'
            """
        )
    ).all()
    noms = {r.conname for r in rows}
    attendus = {
        "ck_mesures_ressource_statut_valide",
        "ck_mesures_ressource_niveau_confiance_derive_valide",
        "ck_mesures_ressource_niveau_confiance_override_valide",
        "ck_mesures_ressource_periode_coherente",
    }
    assert attendus.issubset(noms)


def test_t05_index_partiel_courantes(db_session: Session) -> None:
    """Index partiel idx_mesures_ressource_courantes WHERE valide_au IS NULL."""
    r = db_session.execute(
        text(
            """
            SELECT indexdef FROM pg_indexes
            WHERE indexname = 'idx_mesures_ressource_courantes'
            """
        )
    ).first()
    assert r is not None
    assert "valide_au IS NULL" in r.indexdef


def test_t06_trigger_audit_pose(db_session: Session) -> None:
    """Trigger trg_audit_mesures_ressource posé."""
    r = db_session.execute(
        text(
            """
            SELECT tgname FROM pg_trigger
            WHERE tgname = 'trg_audit_mesures_ressource'
            """
        )
    ).first()
    assert r is not None


# ---------------------------------------------------------------------------
# INSERT et validations
# ---------------------------------------------------------------------------


def test_t07_insert_valide_avec_server_defaults(db_session: Session) -> None:
    """INSERT minimal accepté ; server_defaults appliqués."""
    serie_id = _id_serie_conakry(db_session)
    m = MesureRessource(
        serie_id=serie_id,
        instant_mesure=date(2030, 1, 1),  # date hors plage seed
        valeur=5.42,
        niveau_confiance_derive="B",
    )
    db_session.add(m)
    db_session.flush()
    db_session.refresh(m)
    assert m.statut == "brut"
    assert m.valide_du is not None
    assert m.valide_au is None
    assert m.cree_le is not None


def test_t08_insert_statut_invalide_refuse(db_session: Session) -> None:
    """INSERT avec statut hors liste rejeté par CHECK."""
    serie_id = _id_serie_conakry(db_session)
    m = MesureRessource(
        serie_id=serie_id,
        instant_mesure=date(2030, 1, 2),
        valeur=5.42,
        niveau_confiance_derive="B",
        statut="invalid",
    )
    db_session.add(m)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_t09_insert_niveau_derive_invalide_refuse(db_session: Session) -> None:
    """INSERT avec niveau_confiance_derive hors {A,B,C} rejeté."""
    serie_id = _id_serie_conakry(db_session)
    m = MesureRessource(
        serie_id=serie_id,
        instant_mesure=date(2030, 1, 3),
        valeur=5.42,
        niveau_confiance_derive="D",
    )
    db_session.add(m)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_t10_insert_periode_incoherente_refusee(db_session: Session) -> None:
    """INSERT avec valide_au < valide_du rejeté par CHECK."""
    serie_id = _id_serie_conakry(db_session)
    m = MesureRessource(
        serie_id=serie_id,
        instant_mesure=date(2030, 1, 4),
        valeur=5.42,
        niveau_confiance_derive="B",
        valide_du=datetime(2025, 1, 1, tzinfo=UTC),
        valide_au=datetime(2024, 1, 1, tzinfo=UTC),  # avant valide_du
    )
    db_session.add(m)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_t11_exclude_refuse_deuxieme_ligne_courante(db_session: Session) -> None:
    """INSERT 2ème ligne courante pour même (serie_id, instant_mesure) rejeté."""
    serie_id = _id_serie_conakry(db_session)
    # La première ligne existe déjà via ingestion migration 018
    instant_existant = date(2024, 7, 15)  # jour milieu d'ingestion
    m_doublon = MesureRessource(
        serie_id=serie_id,
        instant_mesure=instant_existant,
        valeur=999.9,
        niveau_confiance_derive="B",
    )
    db_session.add(m_doublon)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_t12_insert_serie_id_inexistante_refuse(db_session: Session) -> None:
    """INSERT avec serie_id inexistant rejeté par FK."""
    m = MesureRessource(
        serie_id=999_999_999,  # n'existe pas
        instant_mesure=date(2030, 1, 5),
        valeur=5.42,
        niveau_confiance_derive="B",
    )
    db_session.add(m)
    with pytest.raises(IntegrityError):
        db_session.flush()


# ---------------------------------------------------------------------------
# Versioning temporel et rotation
# ---------------------------------------------------------------------------


def test_t13_rotation_simple(db_session: Session) -> None:
    """roter_ligne_versionnee ferme l'ancienne et insère la nouvelle."""
    serie_id = _id_serie_conakry(db_session)
    # Prendre une ligne courante existante
    ligne_courante = db_session.execute(
        select(MesureRessource)
        .where(MesureRessource.serie_id == serie_id)
        .where(MesureRessource.instant_mesure == date(2024, 7, 16))
        .where(MesureRessource.valide_au.is_(None))
    ).scalar_one()
    ancienne_valeur = ligne_courante.valeur

    nouvelle = roter_ligne_versionnee(
        ligne_courante=ligne_courante,
        nouvelles_valeurs={"valeur": ancienne_valeur + 1.0},
        auteur_id=None,
        session=db_session,
    )
    db_session.refresh(ligne_courante)
    assert ligne_courante.valide_au is not None
    assert nouvelle.valide_du == ligne_courante.valide_au
    assert nouvelle.valide_au is None
    assert nouvelle.valeur == ancienne_valeur + 1.0


def test_t14_rotation_identite_metier_refusee() -> None:
    """Rotation tentant de changer l'identité métier lève ValueError."""
    # Test pure Python sans session DB
    from unittest.mock import MagicMock

    ligne = MagicMock(spec=MesureRessource)
    session = MagicMock(spec=Session)
    with pytest.raises(ValueError, match="identité métier"):
        roter_ligne_versionnee(
            ligne_courante=ligne,
            nouvelles_valeurs={"serie_id": 42, "valeur": 5.42},  # serie_id interdit
            auteur_id=None,
            session=session,
        )


def test_t15_audit_2_lignes_post_rotation(db_session: Session) -> None:
    """Après rotation, audit_log contient UPDATE puis INSERT."""
    serie_id = _id_serie_conakry(db_session)
    # Trouver une ligne pour rotation (différente de t13)
    ligne = db_session.execute(
        select(MesureRessource)
        .where(MesureRessource.serie_id == serie_id)
        .where(MesureRessource.instant_mesure == date(2024, 7, 17))
        .where(MesureRessource.valide_au.is_(None))
    ).scalar_one()

    id_ancien = ligne.id
    nouvelle = roter_ligne_versionnee(
        ligne_courante=ligne,
        nouvelles_valeurs={"valeur": 6.66},
        auteur_id=None,
        session=db_session,
    )

    # Audit : UPDATE sur ancienne (id_ancien) + INSERT pour nouvelle
    entrees_audit = (
        db_session.execute(
            select(AuditLog)
            .where(AuditLog.table_auditee == "mesures_ressource")
            .where(AuditLog.id_ligne_auditee.in_([str(id_ancien), str(nouvelle.id)]))
            .order_by(AuditLog.horodatage)
        )
        .scalars()
        .all()
    )
    types_ops = [e.type_operation for e in entrees_audit]
    assert "U" in types_ops
    assert "I" in types_ops


# ---------------------------------------------------------------------------
# Statut éditorial machine d'état
# ---------------------------------------------------------------------------


def test_t16_transition_brut_vers_valide_humain(db_session: Session) -> None:
    """Transition autorisée brut -> valide_humain passe."""
    serie_id = _id_serie_conakry(db_session)
    m = MesureRessource(
        serie_id=serie_id,
        instant_mesure=date(2030, 2, 1),
        valeur=5.42,
        niveau_confiance_derive="B",
    )
    db_session.add(m)
    db_session.flush()
    assert m.statut == "brut"

    transition_statut(m.statut, "valide_humain")
    m.statut = "valide_humain"
    db_session.flush()
    db_session.refresh(m)
    assert m.statut == "valide_humain"


def test_t17_transition_publie_vers_brut_refusee() -> None:
    """Transition publie -> brut refusée par la machine d'état."""
    with pytest.raises(TransitionEditorialeRefusee):
        transition_statut("publie", "brut")


# ---------------------------------------------------------------------------
# Niveau de confiance dérivation et override
# ---------------------------------------------------------------------------


def test_t18_r4_modele_satellitaire_donne_b() -> None:
    """R4 catch-all sur modele_satellitaire + source haute → B."""
    niveau = calculer_niveau_confiance_derive(
        methode_collecte="modele_satellitaire",
        fiabilite_source="haute",
    )
    assert niveau == "B"


def test_t19_insert_avec_niveau_derive_libre(db_session: Session) -> None:
    """La cohérence R1-R4 est applicative, pas DB. INSERT avec C accepté."""
    serie_id = _id_serie_conakry(db_session)
    m = MesureRessource(
        serie_id=serie_id,
        instant_mesure=date(2030, 3, 1),
        valeur=5.42,
        niveau_confiance_derive="C",  # incohérent avec R4 pour modele_satellitaire, mais DB accepte
    )
    db_session.add(m)
    db_session.flush()
    db_session.refresh(m)
    assert m.niveau_confiance_derive == "C"


def test_t20_niveau_effectif_hybrid_property(db_session: Session) -> None:
    """niveau_effectif retourne override si non-NULL, sinon derive."""
    serie_id = _id_serie_conakry(db_session)
    m = MesureRessource(
        serie_id=serie_id,
        instant_mesure=date(2030, 3, 2),
        valeur=5.42,
        niveau_confiance_derive="B",
    )
    db_session.add(m)
    db_session.flush()
    # Sans override
    assert m.niveau_effectif == "B"
    # Avec override
    m.niveau_confiance_override = "A"
    db_session.flush()
    assert m.niveau_effectif == "A"


def test_t21_vue_niveau_effectif_coherent(db_session: Session) -> None:
    """Vue v_mesures_avec_niveau_effectif retourne le niveau effectif SQL."""
    serie_id = _id_serie_conakry(db_session)
    m = MesureRessource(
        serie_id=serie_id,
        instant_mesure=date(2030, 4, 1),
        valeur=5.42,
        niveau_confiance_derive="B",
        niveau_confiance_override="A",
    )
    db_session.add(m)
    db_session.flush()

    r = db_session.execute(
        text(
            "SELECT niveau_effectif FROM v_mesures_avec_niveau_effectif "
            "WHERE serie_id = :sid AND instant_mesure = :inst"
        ),
        {"sid": serie_id, "inst": date(2030, 4, 1)},
    ).scalar_one()
    assert r == "A"


# ---------------------------------------------------------------------------
# Ingestion réelle (1826 lignes Conakry GHI)
# ---------------------------------------------------------------------------


def test_t22_ingestion_compte_lignes(db_session: Session) -> None:
    """Ingestion Conakry GHI produit 1826 lignes (sans sentinelle).

    Filtré sur la série GHI - les autres séries (DNI/DHI/T2M/RH2M)
    ajoutées ensuite sont comptées dans
    ``test_mesures_ressource_grandeurs_conakry.py``.
    """
    serie_id = _id_serie_conakry(db_session)
    n = db_session.scalar(
        select(func.count())
        .select_from(MesureRessource)
        .where(MesureRessource.serie_id == serie_id)
    )
    assert n == 1826  # observé empiriquement, 0 sentinelle sur GHI Conakry 2021-2025


def test_t23_aucune_ligne_sentinelle(db_session: Session) -> None:
    """Aucune ligne avec valeur = -999.0 (sentinelles filtrées à l'ingestion)."""
    n = db_session.scalar(
        select(func.count()).select_from(MesureRessource).where(MesureRessource.valeur == -999.0)
    )
    assert n == 0


def test_t24_serie_conakry_ghi_a_des_lignes(db_session: Session) -> None:
    """La série Conakry GHI a bien ses 1826 lignes ingérées.

    Test reformulé : on ne peut plus assert ``rows != serie_id == 0``
    car les séries DNI/DHI/T2M/RH2M ont leurs propres lignes.
    """
    serie_id = _id_serie_conakry(db_session)
    n = db_session.scalar(
        select(func.count())
        .select_from(MesureRessource)
        .where(MesureRessource.serie_id == serie_id)
    )
    assert n == 1826


def test_t25_toutes_lignes_niveau_b(db_session: Session) -> None:
    """Toutes les lignes ingérées ont niveau_confiance_derive = 'B' (R4 catch-all)."""
    serie_id = _id_serie_conakry(db_session)
    rows = db_session.execute(
        select(MesureRessource.niveau_confiance_derive, func.count())
        .where(MesureRessource.serie_id == serie_id)
        .group_by(MesureRessource.niveau_confiance_derive)
    ).all()
    distribution = {r.niveau_confiance_derive: r.count for r in rows}
    assert distribution == {"B": 1826}


def test_t25_bis_niveau_confiance_override_application(db_session: Session) -> None:
    """Test additionnel : overrider_niveau_confiance + justification."""
    serie_id = _id_serie_conakry(db_session)
    m = db_session.execute(
        select(MesureRessource)
        .where(MesureRessource.serie_id == serie_id)
        .where(MesureRessource.instant_mesure == date(2024, 7, 18))
    ).scalar_one()
    overrider_niveau_confiance(m, "A", "Validation post-audit campagne.")
    db_session.flush()
    db_session.refresh(m)
    assert m.niveau_confiance_override == "A"
    assert m.niveau_effectif == "A"
    assert m.commentaire_editorial is not None
    assert "Override -> A" in m.commentaire_editorial


# ---------------------------------------------------------------------------
# Roundtrip Alembic (marker regression)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_t26_roundtrip_alembic_018() -> None:
    """Downgrade -> 017 puis upgrade head revérifie le compte GHI.

    Cible la révision explicite "017". Filtré sur
    la série GHI - les séries DNI/DHI/T2M/RH2M sont
    re-ingérées par la migration 020 lors du upgrade head, leur
    roundtrip est testé dans ``test_mesures_ressource_grandeurs_conakry.py``.
    """
    from kuma_data_core.db.session import get_engine

    cfg = Config("alembic.ini")
    engine = get_engine()

    with Session(engine) as s:
        serie_id_ghi = _id_serie_conakry(s)
        n_initial = s.scalar(
            select(func.count())
            .select_from(MesureRessource)
            .where(MesureRessource.serie_id == serie_id_ghi)
        )
    assert n_initial == 1826

    command.downgrade(cfg, "017")
    with Session(engine) as s:
        # serie_id_ghi peut avoir été préservée (migrations 019-020 ne touchent pas la série GHI).
        n_apres_down = s.scalar(
            select(func.count())
            .select_from(MesureRessource)
            .where(MesureRessource.serie_id == serie_id_ghi)
        )
    assert n_apres_down == 0

    command.upgrade(cfg, "head")
    with Session(engine) as s:
        serie_id_ghi = _id_serie_conakry(s)
        n_final = s.scalar(
            select(func.count())
            .select_from(MesureRessource)
            .where(MesureRessource.serie_id == serie_id_ghi)
        )
    assert n_final == 1826

"""Tests d'intégration du seed des 15 grandeurs ``grandeurs_referentiel``
et des 4 unités complémentaires ``unites``.

Couvre :

- Présence et cohérence des 4 unités complémentaires (migration 009).
- Présence et cohérence des 15 grandeurs (migration 010).
- Cohérence FK ``unite_id`` ↔ ``unite_code`` (jointure).
- Audit : 4 lignes ``audit_log`` ``table_auditee='unites'`` et 15 lignes
  ``table_auditee='grandeurs_referentiel'``, ``type_operation='I'``,
  ``auteur_applicatif IS NULL``.
- Roundtrip Alembic ``downgrade -2`` puis ``upgrade head`` réversible.

``db_session`` fournie par ``tests/integration/db/conftest.py``
(fixture connection-as-transaction rollback en sortie de test).

Note de drift documentée : ``audit_log.type_operation`` stocke
``'I'`` / ``'U'`` / ``'D'`` (``LEFT(TG_OP, 1)`` posé par la
migration 005). Les assertions testent la valeur réelle.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kuma_data_core.db.models.audit_log import AuditLog
from kuma_data_core.db.models.grandeurs_referentiel import GrandeurReferentiel
from kuma_data_core.db.models.unites import Unite
from kuma_data_core.db.seeds.grandeurs_referentiel_seed_data import (
    GRANDEURS_REFERENTIEL_SEED,
)
from kuma_data_core.db.seeds.unites_complementaires_009_seed_data import (
    UNITES_COMPLEMENTAIRES_009_SEED,
)

pytestmark = pytest.mark.integration


_CODES_UNITES_COMPLEMENTAIRES: tuple[str, ...] = tuple(
    entry["code"] for entry in UNITES_COMPLEMENTAIRES_009_SEED
)
_CODES_GRANDEURS: tuple[str, ...] = tuple(entry["code"] for entry in GRANDEURS_REFERENTIEL_SEED)


# ---------------------------------------------------------------------------
# Tests migration 009 - 4 unités complémentaires
# ---------------------------------------------------------------------------


def test_009_quatre_unites_complementaires_presentes(db_session: Session) -> None:
    n = db_session.scalar(
        select(func.count()).select_from(Unite).where(Unite.code.in_(_CODES_UNITES_COMPLEMENTAIRES))
    )
    assert n == 4


def test_009_codes_individuels(db_session: Session) -> None:
    codes_en_base = set(
        db_session.scalars(
            select(Unite.code).where(Unite.code.in_(_CODES_UNITES_COMPLEMENTAIRES))
        ).all()
    )
    assert codes_en_base == set(_CODES_UNITES_COMPLEMENTAIRES)


def test_009_symboles_attendus(db_session: Session) -> None:
    attendus = {entry["code"]: entry["symbole"] for entry in UNITES_COMPLEMENTAIRES_009_SEED}
    rows = db_session.execute(
        select(Unite.code, Unite.symbole).where(Unite.code.in_(_CODES_UNITES_COMPLEMENTAIRES))
    ).all()
    en_base = {row.code: row.symbole for row in rows}
    assert en_base == attendus


def test_009_grandeurs_attendues(db_session: Session) -> None:
    attendus = {entry["code"]: entry["grandeur"] for entry in UNITES_COMPLEMENTAIRES_009_SEED}
    rows = db_session.execute(
        select(Unite.code, Unite.grandeur).where(Unite.code.in_(_CODES_UNITES_COMPLEMENTAIRES))
    ).all()
    en_base = {row.code: row.grandeur for row in rows}
    assert en_base == attendus


def test_009_facteurs_si_exacts(db_session: Session) -> None:
    rows = db_session.execute(
        select(Unite.code, Unite.facteur_conversion_si).where(
            Unite.code.in_(_CODES_UNITES_COMPLEMENTAIRES)
        )
    ).all()
    facteurs_en_base = {row.code: row.facteur_conversion_si for row in rows}

    facteur_jour_attendu = (Decimal("3600") / Decimal("86400")).quantize(Decimal("1E-30"))
    facteur_mois_attendu = (Decimal("3600") / Decimal("2629746")).quantize(Decimal("1E-30"))

    assert facteurs_en_base["heure_equivalente_pleine"] == Decimal("3600")
    assert facteurs_en_base["degre_jour"] == Decimal("1")
    assert facteurs_en_base["kwh_par_kwc_jour"] == facteur_jour_attendu
    assert facteurs_en_base["kwh_par_kwc_mois"] == facteur_mois_attendu


def test_009_note_methodologique_non_vide(db_session: Session) -> None:
    rows = db_session.execute(
        select(Unite.code, Unite.note_methodologique).where(
            Unite.code.in_(_CODES_UNITES_COMPLEMENTAIRES)
        )
    ).all()
    for row in rows:
        assert row.note_methodologique is not None, row.code
        assert row.note_methodologique.strip() != "", row.code


def test_009_audit_4_lignes_insert_auteur_null(db_session: Session) -> None:
    ids_unites = list(
        db_session.scalars(
            select(Unite.id).where(Unite.code.in_(_CODES_UNITES_COMPLEMENTAIRES))
        ).all()
    )
    id_strs = [str(i) for i in ids_unites]

    lignes = list(
        db_session.scalars(
            select(AuditLog)
            .where(AuditLog.table_auditee == "unites")
            .where(AuditLog.id_ligne_auditee.in_(id_strs))
            .where(AuditLog.type_operation == "I")
        ).all()
    )
    assert len(lignes) == 4
    for ligne in lignes:
        assert ligne.auteur_applicatif is None


# ---------------------------------------------------------------------------
# Tests migration 010 - 15 grandeurs
# ---------------------------------------------------------------------------


def test_010_quinze_grandeurs_presentes_et_actives(db_session: Session) -> None:
    """Migration 010 seed 15 grandeurs traduites. Soft deletes cumules :
    - productible_mensuel desactivee (redondance avec
      productible_specifique_theorique mensuel).
    - rang_referentiel singulier desactivee (decomposee en
      rang_referentiel_temporel + rang_referentiel_spatial
      qui ne sont PAS dans les 15 codes seed).

    13 grandeurs actives + 2 desactivees = 15 lignes totales du seed
    (soft delete preserve la ligne, principe Kuma)."""
    n_actif = db_session.scalar(
        select(func.count())
        .select_from(GrandeurReferentiel)
        .where(GrandeurReferentiel.code.in_(_CODES_GRANDEURS))
        .where(GrandeurReferentiel.actif.is_(True))
    )
    assert n_actif == 13
    # Verification : les 15 lignes du seed existent toujours (soft delete)
    n_total = db_session.scalar(
        select(func.count())
        .select_from(GrandeurReferentiel)
        .where(GrandeurReferentiel.code.in_(_CODES_GRANDEURS))
    )
    assert n_total == 15


def test_010_codes_individuels(db_session: Session) -> None:
    codes_en_base = set(
        db_session.scalars(
            select(GrandeurReferentiel.code).where(GrandeurReferentiel.code.in_(_CODES_GRANDEURS))
        ).all()
    )
    assert codes_en_base == set(_CODES_GRANDEURS)


def test_010_familles_attendues(db_session: Session) -> None:
    attendus = {entry["code"]: entry["famille"] for entry in GRANDEURS_REFERENTIEL_SEED}
    rows = db_session.execute(
        select(GrandeurReferentiel.code, GrandeurReferentiel.famille).where(
            GrandeurReferentiel.code.in_(_CODES_GRANDEURS)
        )
    ).all()
    en_base = {row.code: row.famille for row in rows}
    assert en_base == attendus


def test_010_strategies_attendues(db_session: Session) -> None:
    attendus = {entry["code"]: entry["strategie_calcul"] for entry in GRANDEURS_REFERENTIEL_SEED}
    rows = db_session.execute(
        select(GrandeurReferentiel.code, GrandeurReferentiel.strategie_calcul).where(
            GrandeurReferentiel.code.in_(_CODES_GRANDEURS)
        )
    ).all()
    en_base = {row.code: row.strategie_calcul for row in rows}
    assert en_base == attendus


def test_010_decompte_famille_strategie(db_session: Session) -> None:
    f1_stockee = db_session.scalar(
        select(func.count())
        .select_from(GrandeurReferentiel)
        .where(GrandeurReferentiel.code.in_(_CODES_GRANDEURS))
        .where(GrandeurReferentiel.famille == "F1")
        .where(GrandeurReferentiel.strategie_calcul == "stockee")
    )
    f1_volee = db_session.scalar(
        select(func.count())
        .select_from(GrandeurReferentiel)
        .where(GrandeurReferentiel.code.in_(_CODES_GRANDEURS))
        .where(GrandeurReferentiel.famille == "F1")
        .where(GrandeurReferentiel.strategie_calcul == "calculee_volee")
    )
    f2_volee = db_session.scalar(
        select(func.count())
        .select_from(GrandeurReferentiel)
        .where(GrandeurReferentiel.code.in_(_CODES_GRANDEURS))
        .where(GrandeurReferentiel.famille == "F2")
        .where(GrandeurReferentiel.strategie_calcul == "calculee_volee")
    )
    f2_stockee = db_session.scalar(
        select(func.count())
        .select_from(GrandeurReferentiel)
        .where(GrandeurReferentiel.code.in_(_CODES_GRANDEURS))
        .where(GrandeurReferentiel.famille == "F2")
        .where(GrandeurReferentiel.strategie_calcul == "stockee")
    )
    assert f1_stockee == 8
    assert f1_volee == 2
    assert f2_volee == 5
    assert f2_stockee == 0


def test_010_fk_unite_id_resolue_correctement(db_session: Session) -> None:
    """Pour chaque grandeur seedée, ``unite_id`` pointe bien vers le ``unite_code`` attendu."""
    attendus = {entry["code"]: entry["unite_code"] for entry in GRANDEURS_REFERENTIEL_SEED}
    rows = db_session.execute(
        select(GrandeurReferentiel.code, Unite.code.label("unite_code"))
        .join(Unite, GrandeurReferentiel.unite_id == Unite.id)
        .where(GrandeurReferentiel.code.in_(_CODES_GRANDEURS))
    ).all()
    en_base = {row.code: row.unite_code for row in rows}
    assert en_base == attendus


def test_010_methode_calcul_doc_null(db_session: Session) -> None:
    n = db_session.scalar(
        select(func.count())
        .select_from(GrandeurReferentiel)
        .where(GrandeurReferentiel.code.in_(_CODES_GRANDEURS))
        .where(GrandeurReferentiel.methode_calcul_doc.is_(None))
    )
    assert n == 15


def test_010_version_formule_actuelle_un(db_session: Session) -> None:
    n = db_session.scalar(
        select(func.count())
        .select_from(GrandeurReferentiel)
        .where(GrandeurReferentiel.code.in_(_CODES_GRANDEURS))
        .where(GrandeurReferentiel.version_formule_actuelle == 1)
    )
    assert n == 15


def test_010_actif_true_desactive_le_null(db_session: Session) -> None:
    """Soft deletes cumules :
    - productible_mensuel desactivee.
    - rang_referentiel singulier desactivee.
    13 autres grandeurs restent actives avec desactive_le NULL."""
    n_actif = db_session.scalar(
        select(func.count())
        .select_from(GrandeurReferentiel)
        .where(GrandeurReferentiel.code.in_(_CODES_GRANDEURS))
        .where(GrandeurReferentiel.actif.is_(True))
        .where(GrandeurReferentiel.desactive_le.is_(None))
    )
    assert n_actif == 13


def test_010_audit_metadata(db_session: Session) -> None:
    rows = db_session.execute(
        select(
            GrandeurReferentiel.code,
            GrandeurReferentiel.cree_le,
            GrandeurReferentiel.modifie_le,
            GrandeurReferentiel.cree_par,
            GrandeurReferentiel.modifie_par,
        ).where(GrandeurReferentiel.code.in_(_CODES_GRANDEURS))
    ).all()
    assert len(rows) == 15
    for row in rows:
        assert row.cree_le is not None, row.code
        assert row.modifie_le is not None, row.code
        assert row.cree_par is None, row.code
        assert row.modifie_par is None, row.code


def test_010_audit_15_lignes_insert_auteur_null(db_session: Session) -> None:
    ids = list(
        db_session.scalars(
            select(GrandeurReferentiel.id).where(GrandeurReferentiel.code.in_(_CODES_GRANDEURS))
        ).all()
    )
    id_strs = [str(i) for i in ids]

    lignes = list(
        db_session.scalars(
            select(AuditLog)
            .where(AuditLog.table_auditee == "grandeurs_referentiel")
            .where(AuditLog.id_ligne_auditee.in_(id_strs))
            .where(AuditLog.type_operation == "I")
        ).all()
    )
    assert len(lignes) == 15
    for ligne in lignes:
        assert ligne.auteur_applicatif is None


# ---------------------------------------------------------------------------
# Roundtrip Alembic - downgrade -2 puis upgrade head
# ---------------------------------------------------------------------------


def _alembic_config() -> Config:
    """Construit une Config Alembic pointant sur ``alembic.ini`` du projet."""
    cfg = Config("alembic.ini")
    return cfg


@pytest.mark.regression
def test_roundtrip_alembic_009_010() -> None:
    """``downgrade -2`` (010 -> 009 -> 008) puis ``upgrade head`` reverifie les comptes.

    Test exécuté en dehors d'une fixture ``db_session`` car Alembic ouvre sa
    propre connexion. Vérifications post-roundtrip via une session dédiée.
    """
    from kuma_data_core.db.session import get_engine  # local pour éviter import cycle

    cfg = _alembic_config()

    # Vérification de l'état initial : on est censé être à head (010).
    engine = get_engine()
    with Session(engine) as s:
        n_grandeurs_initial = s.scalar(
            select(func.count())
            .select_from(GrandeurReferentiel)
            .where(GrandeurReferentiel.code.in_(_CODES_GRANDEURS))
        )
        n_unites_complementaires_initial = s.scalar(
            select(func.count())
            .select_from(Unite)
            .where(Unite.code.in_(_CODES_UNITES_COMPLEMENTAIRES))
        )
    assert n_grandeurs_initial == 15
    assert n_unites_complementaires_initial == 4

    # Downgrade vers la révision absolue "008" : grandeurs (010) et unités
    # complémentaires (009) disparues. Révision absolue plutôt que relative
    # (`-2`) pour rester stable face à l'ajout de futures migrations
    # (drift latent activé par 011, fix ultérieur).
    command.downgrade(cfg, "008")
    with Session(engine) as s:
        n_grandeurs_apres_down = s.scalar(
            select(func.count())
            .select_from(GrandeurReferentiel)
            .where(GrandeurReferentiel.code.in_(_CODES_GRANDEURS))
        )
        n_unites_apres_down = s.scalar(
            select(func.count())
            .select_from(Unite)
            .where(Unite.code.in_(_CODES_UNITES_COMPLEMENTAIRES))
        )
    assert n_grandeurs_apres_down == 0
    assert n_unites_apres_down == 0

    # Upgrade head : tout doit revenir.
    command.upgrade(cfg, "head")
    with Session(engine) as s:
        n_grandeurs_final = s.scalar(
            select(func.count())
            .select_from(GrandeurReferentiel)
            .where(GrandeurReferentiel.code.in_(_CODES_GRANDEURS))
        )
        n_unites_final = s.scalar(
            select(func.count())
            .select_from(Unite)
            .where(Unite.code.in_(_CODES_UNITES_COMPLEMENTAIRES))
        )
    assert n_grandeurs_final == 15
    assert n_unites_final == 4

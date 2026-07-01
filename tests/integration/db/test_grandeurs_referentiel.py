"""Tests d'intégration de la table ``grandeurs_referentiel``.

Premier test d'intégration de table du projet - introduit le pattern sous
``tests/integration/db/``. Couvre :

* PK / UNIQUE ``code`` (doublon rejeté).
* 4 ``CheckConstraint`` (``famille_valide``, ``strategie_calcul_valide``,
  ``version_formule_positive``, ``actif_desactive_coherent``).
* 3 ``ForeignKeyConstraint`` (``unite_id`` RESTRICT,
  ``cree_par`` / ``modifie_par`` SET NULL).
* Trigger d'audit ``trg_audit_grandeurs_referentiel`` : INSERT, UPDATE,
  DELETE génèrent des lignes ``audit_log`` correctement renseignées avec
  ``auteur_applicatif`` propagé via ``set_config``.

Le test « migration roundtrip » est délégué au job CI
``Tests d'intégration`` qui exécute ``alembic upgrade head`` +
``alembic check`` à chaque push.

Note de drift : ``type_operation`` était décrit comme
``'INSERT' / 'UPDATE' / 'DELETE'``. La migration 005 stocke en réalité
``LEFT(TG_OP, 1)`` soit ``'I' / 'U' / 'D'`` (cf. ``audit_log`` modèle).
Les assertions ci-dessous testent la valeur réelle.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kuma_data_core.db.models.audit_log import AuditLog
from kuma_data_core.db.models.contributeurs import Contributeur
from kuma_data_core.db.models.grandeurs_referentiel import GrandeurReferentiel
from kuma_data_core.db.models.unites import Unite

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures locales (entités de support)
# ---------------------------------------------------------------------------


@pytest.fixture
def unite_test(db_session: Session) -> Unite:
    """Unité minimale, créée dans la transaction de test."""
    unite = Unite(
        code="test_unite_1_1a",
        libelle="Unite test 1-1A",
        symbole="t",
        grandeur="test",
        systeme="autre",
        code_unite_si="test_unite_1_1a",
    )
    db_session.add(unite)
    db_session.flush()
    return unite


@pytest.fixture
def contributeur_test(db_session: Session) -> Contributeur:
    """Contributeur minimal, créé dans la transaction de test."""
    c = Contributeur(
        code="test_contributeur_1_1a",
        nom_complet="Test 1-1A",
        email_principal="test_1_1a@example.org",
        type_contributeur="agent_automatique",
        statut="actif",
    )
    db_session.add(c)
    db_session.flush()
    return c


def _make_grandeur(unite_id: int, **overrides: object) -> GrandeurReferentiel:
    """Construit une ``GrandeurReferentiel`` valide ; ``overrides`` écrase les defaults."""
    params: dict[str, object] = {
        "code": "hep_test",
        "libelle": "HEP test",
        "unite_id": unite_id,
        "famille": "F1",
        "strategie_calcul": "stockee",
    }
    params.update(overrides)
    return GrandeurReferentiel(**params)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. UNIQUE code
# ---------------------------------------------------------------------------


def test_unique_code_doublon_rejete(db_session: Session, unite_test: Unite) -> None:
    db_session.add(_make_grandeur(unite_test.id, code="g_doublon"))
    db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(_make_grandeur(unite_test.id, code="g_doublon"))


# ---------------------------------------------------------------------------
# 2. CHECK famille_valide
# ---------------------------------------------------------------------------


def test_check_famille_valide_rejette_valeur_inconnue(
    db_session: Session, unite_test: Unite
) -> None:
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(_make_grandeur(unite_test.id, code="g_invalide", famille="F3"))


# ---------------------------------------------------------------------------
# 3. CHECK strategie_calcul_valide
# ---------------------------------------------------------------------------


def test_check_strategie_calcul_valide_rejette_valeur_inconnue(
    db_session: Session, unite_test: Unite
) -> None:
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(_make_grandeur(unite_test.id, code="g_strat", strategie_calcul="inventee"))


# ---------------------------------------------------------------------------
# 4. CHECK version_formule_positive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("version_invalide", [0, -1])
def test_check_version_formule_positive_rejette_zero_et_negatif(
    db_session: Session, unite_test: Unite, version_invalide: int
) -> None:
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            _make_grandeur(
                unite_test.id,
                code=f"g_v{version_invalide}",
                version_formule_actuelle=version_invalide,
            )
        )


def test_check_version_formule_positive_default_a_1(db_session: Session, unite_test: Unite) -> None:
    """Sans valeur explicite, le ``DEFAULT 1`` du serveur s'applique."""
    g = _make_grandeur(unite_test.id, code="g_default")
    db_session.add(g)
    db_session.flush()
    db_session.refresh(g)
    assert g.version_formule_actuelle == 1


def test_check_version_formule_positive_un_accepte(db_session: Session, unite_test: Unite) -> None:
    g = _make_grandeur(unite_test.id, code="g_v1", version_formule_actuelle=1)
    db_session.add(g)
    db_session.flush()


# ---------------------------------------------------------------------------
# 5. CHECK actif_desactive_coherent
# ---------------------------------------------------------------------------


def test_check_actif_desactive_coherent_actif_avec_desactive_le_rejete(
    db_session: Session, unite_test: Unite
) -> None:
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            _make_grandeur(
                unite_test.id,
                code="g_a",
                actif=True,
                desactive_le=datetime.now(UTC),
            )
        )


def test_check_actif_desactive_coherent_inactif_sans_desactive_le_rejete(
    db_session: Session, unite_test: Unite
) -> None:
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            _make_grandeur(
                unite_test.id,
                code="g_b",
                actif=False,
                desactive_le=None,
            )
        )


def test_check_actif_desactive_coherent_actif_sans_desactive_le_accepte(
    db_session: Session, unite_test: Unite
) -> None:
    db_session.add(_make_grandeur(unite_test.id, code="g_c", actif=True, desactive_le=None))
    db_session.flush()


def test_check_actif_desactive_coherent_inactif_avec_desactive_le_accepte(
    db_session: Session, unite_test: Unite
) -> None:
    db_session.add(
        _make_grandeur(
            unite_test.id,
            code="g_d",
            actif=False,
            desactive_le=datetime.now(UTC),
        )
    )
    db_session.flush()


# ---------------------------------------------------------------------------
# 6. FK unite_id (RESTRICT)
# ---------------------------------------------------------------------------


def test_fk_unite_id_inexistant_rejete(db_session: Session) -> None:
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(_make_grandeur(unite_id=999_999_999, code="g_fk_unite"))


def test_fk_unite_id_restrict_empeche_delete_unite_referencee(
    db_session: Session, unite_test: Unite
) -> None:
    db_session.add(_make_grandeur(unite_test.id, code="g_protege"))
    db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.delete(unite_test)
        db_session.flush()


# ---------------------------------------------------------------------------
# 7. FK cree_par / modifie_par (SET NULL)
# ---------------------------------------------------------------------------


def test_fk_cree_par_null_accepte(db_session: Session, unite_test: Unite) -> None:
    g = _make_grandeur(unite_test.id, code="g_null", cree_par=None, modifie_par=None)
    db_session.add(g)
    db_session.flush()


def test_fk_cree_par_inexistant_rejete(db_session: Session, unite_test: Unite) -> None:
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(_make_grandeur(unite_test.id, code="g_fk_cp", cree_par=999_999_999))


def test_fk_cree_par_set_null_au_delete_du_contributeur(
    db_session: Session, unite_test: Unite, contributeur_test: Contributeur
) -> None:
    g = _make_grandeur(
        unite_test.id,
        code="g_set_null",
        cree_par=contributeur_test.id,
        modifie_par=contributeur_test.id,
    )
    db_session.add(g)
    db_session.flush()
    grandeur_id = g.id

    db_session.delete(contributeur_test)
    db_session.flush()

    db_session.expire_all()
    g_relu = db_session.get(GrandeurReferentiel, grandeur_id)
    assert g_relu is not None
    assert g_relu.cree_par is None
    assert g_relu.modifie_par is None


# ---------------------------------------------------------------------------
# 8. Trigger d'audit
# ---------------------------------------------------------------------------


def _set_auteur_applicatif(session: Session, valeur: str) -> None:
    """Positionne ``kuma.auteur_applicatif`` au niveau de la transaction courante."""
    session.execute(
        text("SELECT set_config('kuma.auteur_applicatif', :v, true)"),
        {"v": valeur},
    )


def _audit_lignes(session: Session, grandeur_id: int) -> list[AuditLog]:
    return list(
        session.execute(
            select(AuditLog)
            .where(AuditLog.table_auditee == "grandeurs_referentiel")
            .where(AuditLog.id_ligne_auditee == str(grandeur_id))
            .order_by(AuditLog.horodatage)
        )
        .scalars()
        .all()
    )


def test_trigger_audit_insert_update_delete_avec_auteur_applicatif(
    db_session: Session, unite_test: Unite
) -> None:
    _set_auteur_applicatif(db_session, "test_auteur_1_1a")

    # INSERT
    g = _make_grandeur(unite_test.id, code="g_audit", libelle="Libelle initial")
    db_session.add(g)
    db_session.flush()
    grandeur_id = g.id

    lignes = _audit_lignes(db_session, grandeur_id)
    assert len(lignes) == 1
    assert lignes[0].type_operation == "I"
    assert lignes[0].auteur_applicatif == "test_auteur_1_1a"
    assert lignes[0].id_ligne_auditee == str(grandeur_id)

    # UPDATE
    g.libelle = "Libelle modifie"
    db_session.flush()

    lignes = _audit_lignes(db_session, grandeur_id)
    assert len(lignes) == 2
    assert lignes[1].type_operation == "U"
    assert lignes[1].auteur_applicatif == "test_auteur_1_1a"
    assert lignes[1].champs_modifies is not None
    assert "libelle" in lignes[1].champs_modifies

    # DELETE
    db_session.delete(g)
    db_session.flush()

    lignes = _audit_lignes(db_session, grandeur_id)
    assert len(lignes) == 3
    assert lignes[2].type_operation == "D"
    assert lignes[2].auteur_applicatif == "test_auteur_1_1a"

"""Tests d'intégration de la table ``series_metadonnees``.

Couvre les cas de test :

- UNIQUE simple sur ``code`` (1 test).
- UNIQUE composite ``(localite_id, grandeur_code, source_id)`` :
  doublon strict rejeté + 3 cas où un seul élément diffère (acceptés).
- CHECK ``periode_coherente`` (3 sous-cas paramétrés).
- CHECK ``actif_desactive_coherent`` (2 sous-cas paramétrés).
- FK ``localite_id`` (RESTRICT) : INSERT invalide + DELETE bloqué.
- FK ``grandeur_code`` (vers colonne UNIQUE non-PK - premier usage
  projet) : INSERT invalide + DELETE bloqué + jointure fonctionnelle.
- FK ``source_id`` (RESTRICT) : INSERT invalide + DELETE bloqué.
- FK ``cree_par`` / ``modifie_par`` : NULL accepté + id inexistant
  rejeté.
- Trigger d'audit ``trg_audit_series_metadonnees`` : INSERT, UPDATE,
  DELETE générant chacun une ligne ``audit_log`` correctement
  renseignée avec ``auteur_applicatif`` propagé via ``set_config``.

Note de drift documentée : ``audit_log.type_operation`` stocke
``'I'`` / ``'U'`` / ``'D'`` (``LEFT(TG_OP, 1)`` posé par la
migration 005). Les assertions testent la valeur réelle.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kuma_data_core.db.models.audit_log import AuditLog
from kuma_data_core.db.models.grandeurs_referentiel import GrandeurReferentiel
from kuma_data_core.db.models.localites import Localite
from kuma_data_core.db.models.series_metadonnees import SerieMetadonnees
from kuma_data_core.db.models.sources import Source
from kuma_data_core.db.models.unites import Unite

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures locales (instances figées des entités amont)
# ---------------------------------------------------------------------------


@pytest.fixture
def unite_test(db_session: Session) -> Unite:
    """Unité minimale pour adosser une grandeur de test."""
    unite = Unite(
        code="test_unite_1_1b",
        libelle="Unite test 1-1B",
        symbole="t",
        grandeur="test",
        systeme="autre",
        code_unite_si="test_unite_1_1b",
    )
    db_session.add(unite)
    db_session.flush()
    return unite


@pytest.fixture
def grandeur_test(db_session: Session, unite_test: Unite) -> GrandeurReferentiel:
    """Grandeur de référence : HEP de test."""
    gr = GrandeurReferentiel(
        code="hep_test_1_1b",
        libelle="Heures equivalentes pleines (test 1-1B)",
        unite_id=unite_test.id,
        famille="F1",
        strategie_calcul="stockee",
    )
    db_session.add(gr)
    db_session.flush()
    return gr


def _id_localite(db_session: Session, code: str) -> int:
    """Id d'une localite seedee, pour parenter les localites de test.

    Depuis la migration 084 (trigger ``valider_hierarchie_localites``), une commune
    doit avoir un parent (prefecture ou region). Les localites de test sont donc
    rattachees a une region existante du seed.
    """
    return db_session.scalars(select(Localite.id).where(Localite.code == code)).one()


@pytest.fixture
def localite_test(db_session: Session) -> Localite:
    """Localité de référence : Conakry test (commune, Guinée)."""
    loc = Localite(
        code="gin_conakry_test_1_1b",
        nom="Conakry Test 1-1B",
        type_localite="commune",
        parent_id=_id_localite(db_session, "gin_conakry"),
        pays_iso3="GIN",
    )
    db_session.add(loc)
    db_session.flush()
    return loc


@pytest.fixture
def source_test(db_session: Session) -> Source:
    """Source de référence : NASA POWER de test (base de données)."""
    src = Source(
        code="nasa_power_test_1_1b",
        titre="NASA POWER (test 1-1B)",
        type_source="base_donnees",
        fiabilite="haute",
    )
    db_session.add(src)
    db_session.flush()
    return src


# ---------------------------------------------------------------------------
# Helpers module-level
# ---------------------------------------------------------------------------


def _make_serie(
    localite_id: int,
    grandeur_code: str,
    source_id: int,
    **overrides: object,
) -> SerieMetadonnees:
    """Construit (sans flush) une ``SerieMetadonnees`` valide ; ``overrides`` écrase."""
    params: dict[str, object] = {
        "code": "gin_conakry_hep_nasa_power_test",
        "libelle": "Serie HEP Conakry NASA POWER (test)",
        "localite_id": localite_id,
        "grandeur_code": grandeur_code,
        "source_id": source_id,
        "periode_debut": date(2010, 1, 1),
        "periode_fin": date(2024, 12, 31),
    }
    params.update(overrides)
    return SerieMetadonnees(**params)  # type: ignore[arg-type]


def _set_auteur_applicatif(session: Session, valeur: str) -> None:
    """Positionne ``kuma.auteur_applicatif`` au niveau de la transaction courante."""
    session.execute(
        text("SELECT set_config('kuma.auteur_applicatif', :v, true)"),
        {"v": valeur},
    )


def _audit_lignes(
    session: Session,
    table_auditee: str,
    id_ligne: int | str,
) -> list[AuditLog]:
    """Lignes ``audit_log`` ciblées pour une (table, id_ligne), triées par horodatage."""
    return list(
        session.scalars(
            select(AuditLog)
            .where(AuditLog.table_auditee == table_auditee)
            .where(AuditLog.id_ligne_auditee == str(id_ligne))
            .order_by(AuditLog.horodatage)
        )
    )


# ---------------------------------------------------------------------------
# 1. UNIQUE code
# ---------------------------------------------------------------------------


def test_unique_code_doublon_rejete(
    db_session: Session,
    localite_test: Localite,
    grandeur_test: GrandeurReferentiel,
    source_test: Source,
) -> None:
    db_session.add(
        _make_serie(
            localite_test.id,
            grandeur_test.code,
            source_test.id,
            code="serie_test_code_unique",
        )
    )
    db_session.flush()

    # Pour forcer un conflit sur le `code` uniquement, on crée une seconde série
    # sur un autre triplet d'identité métier (sinon le UNIQUE composite
    # taperait avant).
    autre_localite = Localite(
        code="gin_kankan_test_1_1b",
        nom="Kankan Test 1-1B",
        type_localite="commune",
        parent_id=_id_localite(db_session, "gin_kankan_region"),
        pays_iso3="GIN",
    )
    db_session.add(autre_localite)
    db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            _make_serie(
                autre_localite.id,
                grandeur_test.code,
                source_test.id,
                code="serie_test_code_unique",  # même code, autre triplet
            )
        )
        db_session.flush()


# ---------------------------------------------------------------------------
# 2. UNIQUE composite (localite_id, grandeur_code, source_id) - doublon strict
# ---------------------------------------------------------------------------


def test_unique_composite_doublon_strict_rejete(
    db_session: Session,
    localite_test: Localite,
    grandeur_test: GrandeurReferentiel,
    source_test: Source,
) -> None:
    db_session.add(
        _make_serie(
            localite_test.id,
            grandeur_test.code,
            source_test.id,
            code="serie_composite_a",
            granularite="journalier",
        )
    )
    db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            _make_serie(
                localite_test.id,
                grandeur_test.code,
                source_test.id,
                code="serie_composite_b",  # code différent, identité métier identique
                granularite="journalier",  # cle etendue (migration 106)
            )
        )
        db_session.flush()


# ---------------------------------------------------------------------------
# 3. UNIQUE composite - un seul élément diffère, accepté
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("element_qui_differe", ["localite", "grandeur", "source"])
def test_unique_composite_un_element_qui_differe_accepte(
    db_session: Session,
    localite_test: Localite,
    grandeur_test: GrandeurReferentiel,
    source_test: Source,
    unite_test: Unite,
    element_qui_differe: str,
) -> None:
    db_session.add(
        _make_serie(
            localite_test.id,
            grandeur_test.code,
            source_test.id,
            code="serie_diff_a",
        )
    )
    db_session.flush()

    if element_qui_differe == "localite":
        autre = Localite(
            code="gin_labe_test_1_1b",
            nom="Labe Test 1-1B",
            type_localite="commune",
            parent_id=_id_localite(db_session, "gin_labe_region"),
            pays_iso3="GIN",
        )
        db_session.add(autre)
        db_session.flush()
        seconde = _make_serie(
            autre.id,
            grandeur_test.code,
            source_test.id,
            code="serie_diff_b",
        )
    elif element_qui_differe == "grandeur":
        autre = GrandeurReferentiel(
            code="kt_test_1_1b",
            libelle="Indice de clarte (test 1-1B)",
            unite_id=unite_test.id,
            famille="F1",
            strategie_calcul="stockee",
        )
        db_session.add(autre)
        db_session.flush()
        seconde = _make_serie(
            localite_test.id,
            autre.code,
            source_test.id,
            code="serie_diff_b",
        )
    else:  # source
        autre = Source(
            code="copernicus_test_1_1b",
            titre="Copernicus (test 1-1B)",
            type_source="base_donnees",
            fiabilite="haute",
        )
        db_session.add(autre)
        db_session.flush()
        seconde = _make_serie(
            localite_test.id,
            grandeur_test.code,
            autre.id,
            code="serie_diff_b",
        )

    db_session.add(seconde)
    db_session.flush()  # doit passer sans IntegrityError


# ---------------------------------------------------------------------------
# 4. CHECK periode_coherente
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("periode_debut", "periode_fin", "doit_passer"),
    [
        (date(2024, 6, 1), date(2024, 1, 1), False),  # fin < debut
        (date(2024, 6, 1), date(2024, 6, 1), True),  # fin = debut (toleré)
        (date(2024, 6, 1), None, True),  # fin NULL (serie en cours)
    ],
)
def test_check_periode_coherente(
    db_session: Session,
    localite_test: Localite,
    grandeur_test: GrandeurReferentiel,
    source_test: Source,
    periode_debut: date,
    periode_fin: date | None,
    doit_passer: bool,
) -> None:
    serie = _make_serie(
        localite_test.id,
        grandeur_test.code,
        source_test.id,
        code=f"serie_periode_{periode_debut.isoformat()}_{periode_fin}",
        periode_debut=periode_debut,
        periode_fin=periode_fin,
    )
    if doit_passer:
        db_session.add(serie)
        db_session.flush()
    else:
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.add(serie)
            db_session.flush()


# ---------------------------------------------------------------------------
# 5. CHECK actif_desactive_coherent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("actif", "desactive_le"),
    [
        (True, datetime.now(UTC)),  # actif=TRUE avec desactive_le posé
        (False, None),  # actif=FALSE sans desactive_le
    ],
)
def test_check_actif_desactive_coherent_rejette(
    db_session: Session,
    localite_test: Localite,
    grandeur_test: GrandeurReferentiel,
    source_test: Source,
    actif: bool,
    desactive_le: datetime | None,
) -> None:
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            _make_serie(
                localite_test.id,
                grandeur_test.code,
                source_test.id,
                code=f"serie_actif_{actif}_{desactive_le}",
                actif=actif,
                desactive_le=desactive_le,
            )
        )
        db_session.flush()


# ---------------------------------------------------------------------------
# 6. FK localite_id (RESTRICT)
# ---------------------------------------------------------------------------


def test_fk_localite_id_inexistant_rejete(
    db_session: Session,
    grandeur_test: GrandeurReferentiel,
    source_test: Source,
) -> None:
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            _make_serie(
                999_999_999,
                grandeur_test.code,
                source_test.id,
                code="serie_fk_localite_invalide",
            )
        )
        db_session.flush()


def test_fk_localite_id_restrict_empeche_delete(
    db_session: Session,
    localite_test: Localite,
    grandeur_test: GrandeurReferentiel,
    source_test: Source,
) -> None:
    db_session.add(
        _make_serie(
            localite_test.id,
            grandeur_test.code,
            source_test.id,
            code="serie_protege_localite",
        )
    )
    db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.delete(localite_test)
        db_session.flush()


# ---------------------------------------------------------------------------
# 7. FK grandeur_code (vers colonne UNIQUE non-PK - premier usage projet)
# ---------------------------------------------------------------------------


def test_fk_grandeur_code_inexistant_rejete(
    db_session: Session,
    localite_test: Localite,
    source_test: Source,
) -> None:
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            _make_serie(
                localite_test.id,
                "inventee_test_1_1b",
                source_test.id,
                code="serie_fk_grandeur_invalide",
            )
        )
        db_session.flush()


def test_fk_grandeur_code_restrict_empeche_delete(
    db_session: Session,
    localite_test: Localite,
    grandeur_test: GrandeurReferentiel,
    source_test: Source,
) -> None:
    db_session.add(
        _make_serie(
            localite_test.id,
            grandeur_test.code,
            source_test.id,
            code="serie_protege_grandeur",
        )
    )
    db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.delete(grandeur_test)
        db_session.flush()


def test_fk_grandeur_code_jointure_fonctionnelle(
    db_session: Session,
    localite_test: Localite,
    grandeur_test: GrandeurReferentiel,
    source_test: Source,
) -> None:
    """Jointure SQL via la FK vers colonne UNIQUE non-PK (premier usage projet)."""
    serie = _make_serie(
        localite_test.id,
        grandeur_test.code,
        source_test.id,
        code="serie_jointure_grandeur",
    )
    db_session.add(serie)
    db_session.flush()

    resultat = db_session.execute(
        select(SerieMetadonnees, GrandeurReferentiel)
        .join(
            GrandeurReferentiel,
            SerieMetadonnees.grandeur_code == GrandeurReferentiel.code,
        )
        .where(SerieMetadonnees.id == serie.id)
    ).one()
    serie_jointe, grandeur_jointe = resultat
    assert serie_jointe.id == serie.id
    assert grandeur_jointe.code == grandeur_test.code
    assert grandeur_jointe.libelle == grandeur_test.libelle


# ---------------------------------------------------------------------------
# 8. FK source_id (RESTRICT)
# ---------------------------------------------------------------------------


def test_fk_source_id_inexistant_rejete(
    db_session: Session,
    localite_test: Localite,
    grandeur_test: GrandeurReferentiel,
) -> None:
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            _make_serie(
                localite_test.id,
                grandeur_test.code,
                999_999_999,
                code="serie_fk_source_invalide",
            )
        )
        db_session.flush()


def test_fk_source_id_restrict_empeche_delete(
    db_session: Session,
    localite_test: Localite,
    grandeur_test: GrandeurReferentiel,
    source_test: Source,
) -> None:
    db_session.add(
        _make_serie(
            localite_test.id,
            grandeur_test.code,
            source_test.id,
            code="serie_protege_source",
        )
    )
    db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.delete(source_test)
        db_session.flush()


# ---------------------------------------------------------------------------
# 9. FK cree_par / modifie_par
# ---------------------------------------------------------------------------


def test_fk_cree_par_null_accepte(
    db_session: Session,
    localite_test: Localite,
    grandeur_test: GrandeurReferentiel,
    source_test: Source,
) -> None:
    db_session.add(
        _make_serie(
            localite_test.id,
            grandeur_test.code,
            source_test.id,
            code="serie_cree_par_null",
            cree_par=None,
            modifie_par=None,
        )
    )
    db_session.flush()


def test_fk_cree_par_inexistant_rejete(
    db_session: Session,
    localite_test: Localite,
    grandeur_test: GrandeurReferentiel,
    source_test: Source,
) -> None:
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            _make_serie(
                localite_test.id,
                grandeur_test.code,
                source_test.id,
                code="serie_cree_par_invalide",
                cree_par=999_999_999,
            )
        )
        db_session.flush()


# ---------------------------------------------------------------------------
# 10. Trigger d'audit (INSERT, UPDATE, DELETE)
# ---------------------------------------------------------------------------


def test_trigger_audit_insert(
    db_session: Session,
    localite_test: Localite,
    grandeur_test: GrandeurReferentiel,
    source_test: Source,
) -> None:
    _set_auteur_applicatif(db_session, "test_etape_1_1b_insert")
    serie = _make_serie(
        localite_test.id,
        grandeur_test.code,
        source_test.id,
        code="serie_audit_insert",
    )
    db_session.add(serie)
    db_session.flush()

    lignes = _audit_lignes(db_session, "series_metadonnees", serie.id)
    assert len(lignes) == 1
    assert lignes[0].type_operation == "I"
    assert lignes[0].id_ligne_auditee == str(serie.id)
    assert lignes[0].auteur_applicatif == "test_etape_1_1b_insert"


def test_trigger_audit_update(
    db_session: Session,
    localite_test: Localite,
    grandeur_test: GrandeurReferentiel,
    source_test: Source,
) -> None:
    serie = _make_serie(
        localite_test.id,
        grandeur_test.code,
        source_test.id,
        code="serie_audit_update",
        libelle="Libelle initial",
    )
    db_session.add(serie)
    db_session.flush()

    _set_auteur_applicatif(db_session, "test_etape_1_1b_update")
    serie.libelle = "Libelle modifie"
    db_session.flush()

    lignes = _audit_lignes(db_session, "series_metadonnees", serie.id)
    assert len(lignes) == 2
    update_ligne = lignes[1]
    assert update_ligne.type_operation == "U"
    assert update_ligne.auteur_applicatif == "test_etape_1_1b_update"
    assert update_ligne.champs_modifies is not None
    assert "libelle" in update_ligne.champs_modifies


def test_trigger_audit_delete(
    db_session: Session,
    localite_test: Localite,
    grandeur_test: GrandeurReferentiel,
    source_test: Source,
) -> None:
    serie = _make_serie(
        localite_test.id,
        grandeur_test.code,
        source_test.id,
        code="serie_audit_delete",
    )
    db_session.add(serie)
    db_session.flush()
    serie_id = serie.id

    _set_auteur_applicatif(db_session, "test_etape_1_1b_delete")
    db_session.delete(serie)
    db_session.flush()

    lignes = _audit_lignes(db_session, "series_metadonnees", serie_id)
    assert len(lignes) == 2
    delete_ligne = lignes[1]
    assert delete_ligne.type_operation == "D"
    assert delete_ligne.auteur_applicatif == "test_etape_1_1b_delete"

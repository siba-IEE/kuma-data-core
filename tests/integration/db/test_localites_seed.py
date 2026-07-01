"""Tests d'intégration du seed des 20 localités pilotes Guinée.

Couvre les 11 tests du seed des localités :

1. Compte global : 20 lignes.
2. Distribution ``type_localite`` : 1 + 1 + 8 + 10.
3. Hiérarchie auto-référentielle : chaque ``parent_code`` se résout.
4. Règle hybride (matrice ``type_localite`` → ``annee_population``).
5. Cross-check sommes : 8 régions = 17 521 167 ; 5 communes Conakry = 1 667 864.
6. Mention pilote sur les 5 ``gin_conakry_*``.
7. Mention scission sur ``gin_conakry_matoto`` et ``gin_conakry_ratoma``.
8. Coordonnées identiques : 6 paires (5 régions ↔ chef-lieu + 1).
9. Tags ``[À VÉRIFIER]`` : un seul (``gin_conakry_kaloum``).
10. Traçabilité Q-ID Wikidata : 20 lignes ont ``Q[0-9]+`` dans ``notes``.
11. Audit : 20 lignes ``audit_log`` (``type_operation='I'``,
    ``auteur_applicatif IS NULL``) + roundtrip Alembic optionnel.

Pattern tests d'intégration.
``db_session`` fournie par ``tests/integration/db/conftest.py``
(fixture connection-as-transaction rollback en sortie de test).

Note documentée : ``audit_log.type_operation`` stocke
``'I'`` / ``'U'`` / ``'D'`` (``LEFT(TG_OP, 1)`` posé par la
migration 005).
"""

from __future__ import annotations

import re

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from kuma_data_core.db.models.audit_log import AuditLog
from kuma_data_core.db.models.localites import Localite
from kuma_data_core.db.seeds.localites_seed_data import LOCALITES_SEED

pytestmark = pytest.mark.integration


_CODES_LOCALITES: tuple[str, ...] = tuple(entry["code"] for entry in LOCALITES_SEED)
_PARENT_PAR_CODE: dict[str, str | None] = {
    entry["code"]: entry["parent_code"] for entry in LOCALITES_SEED
}

# Migration 085 (densification prefectorale) re-parente les 5 communes capitales
# regionales : leur parent passe de la region a leur nouvelle prefecture. La base
# d'integration etant a head, l'etat attendu de la hierarchie (test_03) integre ce
# re-parentage. Attente hardcodee (independante du seed densification, pour ne pas
# masquer un bug de ce dernier). gin_boke/gin_faranah restent des regions
# (decision B : pas d'harmonisation), donc le reste du seed pilote est inchange.
_REPARENTAGE_085: dict[str, str] = {
    "gin_kankan": "gin_kankan_prefecture",
    "gin_kindia": "gin_kindia_prefecture",
    "gin_labe": "gin_labe_prefecture",
    "gin_mamou": "gin_mamou_prefecture",
    "gin_nzerekore": "gin_nzerekore_prefecture",
}

_EXPECTED_ANNEE_PAR_TYPE: dict[str, int] = {
    "continent": 2024,
    "pays": 2025,
    "region_administrative": 2025,
    "commune": 2014,
}

# Paires régions ↔ chef-lieu + paire E.15 gin_conakry ↔ gin_conakry_kaloum.
_PAIRES_COORDONNEES_IDENTIQUES: tuple[tuple[str, str], ...] = (
    ("gin_kankan_region", "gin_kankan"),
    ("gin_kindia_region", "gin_kindia"),
    ("gin_labe_region", "gin_labe"),
    ("gin_mamou_region", "gin_mamou"),
    ("gin_nzerekore_region", "gin_nzerekore"),
    ("gin_conakry", "gin_conakry_kaloum"),
)


# ---------------------------------------------------------------------------
# 1. Compte global
# ---------------------------------------------------------------------------


def test_01_compte_global_20(db_session: Session) -> None:
    n = db_session.scalar(
        select(func.count()).select_from(Localite).where(Localite.code.in_(_CODES_LOCALITES))
    )
    assert n == 20


# ---------------------------------------------------------------------------
# 2. Distribution type_localite
# ---------------------------------------------------------------------------


def test_02_distribution_type_localite(db_session: Session) -> None:
    rows = db_session.execute(
        select(Localite.type_localite, func.count())
        .where(Localite.code.in_(_CODES_LOCALITES))
        .group_by(Localite.type_localite)
    ).all()
    distribution = {row.type_localite: row.count for row in rows}
    assert distribution == {
        "continent": 1,
        "pays": 1,
        "region_administrative": 8,
        "commune": 10,
    }


# ---------------------------------------------------------------------------
# 3. Hiérarchie auto-référentielle
# ---------------------------------------------------------------------------


def test_03_hierarchie_afrique_racine(db_session: Session) -> None:
    afrique = db_session.scalars(select(Localite).where(Localite.code == "afrique")).one()
    assert afrique.parent_id is None


def test_03_hierarchie_chaque_parent_resolu(db_session: Session) -> None:
    """Pour chaque entité avec ``parent_code``, la jointure auto-référentielle
    confirme que ``localites.parent_id`` pointe bien vers la ligne de
    code ``parent_code`` attendu.
    """
    parent = aliased(Localite)
    rows = db_session.execute(
        select(Localite.code, parent.code.label("parent_code_resolu"))
        .join(parent, Localite.parent_id == parent.id)
        .where(Localite.code.in_(_CODES_LOCALITES))
    ).all()
    en_base = {row.code: row.parent_code_resolu for row in rows}

    # Etat post-085 : les 5 communes capitales sont re-parentees vers leur prefecture.
    attendus = {
        code: _REPARENTAGE_085.get(code, parent_code)
        for code, parent_code in _PARENT_PAR_CODE.items()
        if parent_code is not None
    }
    assert en_base == attendus


# ---------------------------------------------------------------------------
# 4. Règle hybride (type_localite → annee_population)
# ---------------------------------------------------------------------------


def test_04_regle_hybride_annee_population(db_session: Session) -> None:
    rows = db_session.execute(
        select(Localite.code, Localite.type_localite, Localite.annee_population).where(
            Localite.code.in_(_CODES_LOCALITES)
        )
    ).all()
    for row in rows:
        attendu = _EXPECTED_ANNEE_PAR_TYPE[row.type_localite]
        assert row.annee_population == attendu, (
            f"{row.code} (type {row.type_localite!r}) : "
            f"annee_population={row.annee_population!r}, attendu {attendu!r}"
        )


# ---------------------------------------------------------------------------
# 5. Cross-check sommes
# ---------------------------------------------------------------------------


def test_05_somme_regions_egale_population_pays(db_session: Session) -> None:
    somme_regions = db_session.scalar(
        select(func.sum(Localite.population_estimee)).where(
            Localite.type_localite == "region_administrative",
            Localite.code.in_(_CODES_LOCALITES),
        )
    )
    pop_pays = db_session.scalar(select(Localite.population_estimee).where(Localite.code == "gin"))
    assert somme_regions == 17_521_167
    assert pop_pays == 17_521_167
    assert somme_regions == pop_pays


def test_05_somme_5_communes_conakry(db_session: Session) -> None:
    codes_communes_conakry = (
        "gin_conakry_kaloum",
        "gin_conakry_dixinn",
        "gin_conakry_matam",
        "gin_conakry_matoto",
        "gin_conakry_ratoma",
    )
    somme = db_session.scalar(
        select(func.sum(Localite.population_estimee)).where(
            Localite.code.in_(codes_communes_conakry)
        )
    )
    assert somme == 1_667_864


# ---------------------------------------------------------------------------
# 6. Mention pilote (5 communes Conakry)
# ---------------------------------------------------------------------------


def test_06_mention_pilote_5_communes_conakry(db_session: Session) -> None:
    codes_communes_conakry = (
        "gin_conakry_kaloum",
        "gin_conakry_dixinn",
        "gin_conakry_matam",
        "gin_conakry_matoto",
        "gin_conakry_ratoma",
    )
    rows = db_session.execute(
        select(Localite.code, Localite.notes).where(Localite.code.in_(codes_communes_conakry))
    ).all()
    assert len(rows) == 5
    pattern = "5 communes historiques pré-réforme 2024"
    for row in rows:
        assert pattern in (row.notes or ""), row.code


# ---------------------------------------------------------------------------
# 7. Mention scission (Matoto, Ratoma)
# ---------------------------------------------------------------------------


def test_07_mention_scission_matoto_ratoma(db_session: Session) -> None:
    codes_scindees = ("gin_conakry_matoto", "gin_conakry_ratoma")
    rows = db_session.execute(
        select(Localite.code, Localite.notes).where(Localite.code.in_(codes_scindees))
    ).all()
    assert len(rows) == 2
    pattern = "scindée par la réforme 2024"
    for row in rows:
        assert pattern in (row.notes or ""), row.code


# ---------------------------------------------------------------------------
# 8. Coordonnées identiques : 6 paires
# ---------------------------------------------------------------------------


def test_08_coordonnees_identiques_6_paires(db_session: Session) -> None:
    for region_code, commune_code in _PAIRES_COORDONNEES_IDENTIQUES:
        region = db_session.scalars(select(Localite).where(Localite.code == region_code)).one()
        commune = db_session.scalars(select(Localite).where(Localite.code == commune_code)).one()
        assert region.latitude == commune.latitude, (
            f"{region_code} vs {commune_code} : latitude différente "
            f"({region.latitude} vs {commune.latitude})"
        )
        assert region.longitude == commune.longitude, (
            f"{region_code} vs {commune_code} : longitude différente "
            f"({region.longitude} vs {commune.longitude})"
        )


# ---------------------------------------------------------------------------
# 9. Tags [À VÉRIFIER] (un seul code)
# ---------------------------------------------------------------------------


def test_09_tag_a_verifier_un_seul_code(db_session: Session) -> None:
    rows = db_session.execute(
        select(Localite.code).where(
            Localite.code.in_(_CODES_LOCALITES),
            Localite.notes.ilike("%[À VÉRIFIER]%"),
        )
    ).all()
    codes_avec_tag = {row.code for row in rows}
    assert codes_avec_tag == {"gin_conakry_kaloum"}, (
        f"Codes avec tag [À VÉRIFIER] = {sorted(codes_avec_tag)}, "
        f"attendu uniquement gin_conakry_kaloum (v3 spec § 6 test 9)."
    )


# ---------------------------------------------------------------------------
# 10. Traçabilité Q-ID Wikidata
# ---------------------------------------------------------------------------


def test_10_q_id_wikidata_present_pour_20_lignes(db_session: Session) -> None:
    rows = db_session.execute(
        select(Localite.code, Localite.notes).where(Localite.code.in_(_CODES_LOCALITES))
    ).all()
    assert len(rows) == 20
    pattern = re.compile(r"Q[0-9]+")
    for row in rows:
        assert row.notes is not None, row.code
        assert pattern.search(row.notes) is not None, (
            f"{row.code} : aucune occurrence Q[0-9]+ dans notes"
        )


# ---------------------------------------------------------------------------
# 11. Audit
# ---------------------------------------------------------------------------


def test_11_audit_20_lignes_insert_auteur_null(db_session: Session) -> None:
    ids_localites = list(
        db_session.scalars(select(Localite.id).where(Localite.code.in_(_CODES_LOCALITES))).all()
    )
    id_strs = [str(i) for i in ids_localites]

    lignes = list(
        db_session.scalars(
            select(AuditLog)
            .where(AuditLog.table_auditee == "localites")
            .where(AuditLog.id_ligne_auditee.in_(id_strs))
            .where(AuditLog.type_operation == "I")
        ).all()
    )
    assert len(lignes) == 20
    for ligne in lignes:
        assert ligne.auteur_applicatif is None


# ---------------------------------------------------------------------------
# Roundtrip Alembic (test optionnel, marker regression)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_roundtrip_alembic_011() -> None:
    """``downgrade -1`` puis ``upgrade head`` reverifie le compte de 20.

    Test exécuté en dehors d'une fixture ``db_session`` car Alembic ouvre
    sa propre connexion. Vérifications post-roundtrip via une session
    dédiée.
    """
    from kuma_data_core.db.session import get_engine

    cfg = Config("alembic.ini")
    engine = get_engine()

    with Session(engine) as s:
        n_initial = s.scalar(
            select(func.count()).select_from(Localite).where(Localite.code.in_(_CODES_LOCALITES))
        )
    assert n_initial == 20

    # Cible la révision explicite "010" plutôt que "-1" : "-1" dépend du
    # head courant et casse ce test dès qu'une migration ultérieure est
    # ajoutée. Pattern à reproduire sur les roundtrips
    # ultérieurs (cf. test_sources_seed.py qui cible "011").
    command.downgrade(cfg, "010")
    with Session(engine) as s:
        n_apres_down = s.scalar(
            select(func.count()).select_from(Localite).where(Localite.code.in_(_CODES_LOCALITES))
        )
    assert n_apres_down == 0

    command.upgrade(cfg, "head")
    with Session(engine) as s:
        n_final = s.scalar(
            select(func.count()).select_from(Localite).where(Localite.code.in_(_CODES_LOCALITES))
        )
    assert n_final == 20

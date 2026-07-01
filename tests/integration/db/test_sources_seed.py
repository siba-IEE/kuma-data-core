"""Tests d'intégration du seed des 9 sources éditoriales.

Couvre les 11 tests du seed des sources (adaptés au schéma
SQLAlchemy réel) + roundtrip Alembic
optionnel sous marker ``regression`` :

 1. Compte global : 9 lignes.
 2. Distribution ``type_source`` : 5 ``base_donnees`` + 4
    ``norme_technique``.
 3. Ordre tutelle : énumération nominative des organisations
    attendues (WMO sur 3 sources via substring, IEC sur 2, ECMWF sur 1,
    NASA sur 1, ANM sur 1, WWF sur 1).
 4. Mention β2 normée : sur les 4 sources hydro β2 (``wmo_grdc``,
    ``wwf_hydrosheds``, ``iec_60041_1991``, ``wmo_168_2008``), le
    paragraphe canonique est présent octet-à-octet identique dans
    ``notes``.
 5. ISBN normes IEC : ``iec_61724_1_2021.isbn`` = ``9782832210025`` ;
    ``iec_60041_1991.isbn`` = ``283182222X``.
 6. Acknowledgement présent : pattern
    ``(?i)(acknowledgement|citation)`` dans ``notes`` pour les 9
    sources.
 7. Année dans le code : 4 codes avec année + 5 sans.
 8. Scope Vol I WMO : ``wmo_8_2024.doi`` se termine par ``/1``.
 9. Date consultation uniforme : ``date(2026, 5, 10)`` pour les 9.
10. Fiabilité uniforme : ``'haute'`` pour les 9.
11. Audit : 9 lignes INSERT (``type_operation = 'I'``,
    ``auteur_applicatif IS NULL``).

Plus un roundtrip Alembic ``downgrade -1`` → ``upgrade head`` sous
marker ``regression``.

Pattern tests d'intégration.
``db_session`` fournie par ``tests/integration/db/conftest.py``
(fixture connection-as-transaction rollback en sortie de test).
"""

from __future__ import annotations

import re
from datetime import date

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kuma_data_core.db.models.audit_log import AuditLog
from kuma_data_core.db.models.sources import Source
from kuma_data_core.db.seeds.sources_seed_data import (
    _MENTION_BETA2_NORMEE,
    SOURCES_SEED,
)

pytestmark = pytest.mark.integration


_CODES_SOURCES: tuple[str, ...] = tuple(entry["code"] for entry in SOURCES_SEED)

_CODES_HYDRO_BETA2: tuple[str, ...] = (
    "wmo_grdc",
    "wwf_hydrosheds",
    "iec_60041_1991",
    "wmo_168_2008",
)

_CODES_AVEC_ANNEE: tuple[str, ...] = (
    "iec_61724_1_2021",
    "wmo_8_2024",
    "iec_60041_1991",
    "wmo_168_2008",
)

_CODES_SANS_ANNEE: tuple[str, ...] = (
    "nasa_power",
    "ecmwf_era5",
    "anm_guinee_stations",
    "wmo_grdc",
    "wwf_hydrosheds",
)

# Mapping substring d'organisation -> nombre attendu de sources la mentionnant
# dans le champ ``organisation`` (ordre tutelle).
_ORGANISATIONS_ATTENDUES: dict[str, int] = {
    "WMO": 3,  # wmo_8_2024, wmo_grdc (mandat WMO), wmo_168_2008
    "IEC": 2,  # iec_61724_1_2021, iec_60041_1991
    "ECMWF": 1,  # ecmwf_era5
    "NASA": 1,  # nasa_power
    "ANM": 1,  # anm_guinee_stations
    "WWF": 1,  # wwf_hydrosheds
}


# ---------------------------------------------------------------------------
# 1. Compte global
# ---------------------------------------------------------------------------


def test_01_compte_global_9(db_session: Session) -> None:
    n = db_session.scalar(
        select(func.count()).select_from(Source).where(Source.code.in_(_CODES_SOURCES))
    )
    assert n == 9


# ---------------------------------------------------------------------------
# 2. Distribution type_source
# ---------------------------------------------------------------------------


def test_02_distribution_type_source(db_session: Session) -> None:
    rows = db_session.execute(
        select(Source.type_source, func.count())
        .where(Source.code.in_(_CODES_SOURCES))
        .group_by(Source.type_source)
    ).all()
    distribution = {row.type_source: row.count for row in rows}
    assert distribution == {
        "base_donnees": 5,
        "norme_technique": 4,
    }


# ---------------------------------------------------------------------------
# 3. Ordre tutelle : énumération nominative des organisations
# ---------------------------------------------------------------------------


def test_03_dt1_ordre_tutelle_substrings_organisation(db_session: Session) -> None:
    """Pour chaque substring d'organisme (WMO/IEC/ECMWF/NASA/ANM/WWF),
    le nombre de sources dont ``organisation`` contient cette substring
    correspond à l'énumération attendue.
    """
    organisations_en_base = {
        row.code: row.organisation
        for row in db_session.execute(
            select(Source.code, Source.organisation).where(Source.code.in_(_CODES_SOURCES))
        ).all()
    }
    for substring, attendu in _ORGANISATIONS_ATTENDUES.items():
        compte = sum(1 for org in organisations_en_base.values() if substring in (org or ""))
        assert compte == attendu, (
            f"Substring organisation {substring!r} attendue dans {attendu} source(s), "
            f"trouvée dans {compte}. Détail organisations : {organisations_en_base}"
        )


# ---------------------------------------------------------------------------
# 4. Mention β2 normée octet-à-octet sur les 4 hydro
# ---------------------------------------------------------------------------


def test_04_dt8_mention_beta2_normee_4_hydro(db_session: Session) -> None:
    rows = db_session.execute(
        select(Source.code, Source.notes).where(Source.code.in_(_CODES_HYDRO_BETA2))
    ).all()
    assert len(rows) == 4
    for row in rows:
        assert row.notes is not None, row.code
        assert _MENTION_BETA2_NORMEE in row.notes, (
            f"{row.code} : mention β2 normée DT-8 absente ou modifiée dans notes."
        )


def test_04_dt8_pas_de_mention_beta2_hors_4_hydro(db_session: Session) -> None:
    codes_hors_hydro = tuple(c for c in _CODES_SOURCES if c not in _CODES_HYDRO_BETA2)
    rows = db_session.execute(
        select(Source.code, Source.notes).where(Source.code.in_(codes_hors_hydro))
    ).all()
    assert len(rows) == 5
    for row in rows:
        assert _MENTION_BETA2_NORMEE not in (row.notes or ""), (
            f"{row.code} : mention β2 normée DT-8 présente alors qu'attendue absente "
            f"(source non hydro structurelle)."
        )


# ---------------------------------------------------------------------------
# 5. ISBN normes IEC
# ---------------------------------------------------------------------------


def test_05_dt9_isbn_iec_61724_1_2021(db_session: Session) -> None:
    """ISBN natif IEC `9782832210025` trouvé par vérification
    webstore IEC le 2026-05-10.
    """
    src = db_session.scalars(select(Source).where(Source.code == "iec_61724_1_2021")).one()
    assert src.isbn == "9782832210025"


def test_05_dt9_isbn_iec_60041_1991(db_session: Session) -> None:
    """ISBN-10 natif IEC pré-2007 visible champ « ISBN number » page
    webstore.iec.ch/en/publication/154.
    """
    src = db_session.scalars(select(Source).where(Source.code == "iec_60041_1991")).one()
    assert src.isbn == "283182222X"


def test_05_dt9_isbn_normes_wmo(db_session: Session) -> None:
    """Pour symétrie : les 2 normes WMO ont également un ISBN natif Vol I."""
    src_8 = db_session.scalars(select(Source).where(Source.code == "wmo_8_2024")).one()
    src_168 = db_session.scalars(select(Source).where(Source.code == "wmo_168_2008")).one()
    assert src_8.isbn == "9789263100085"
    assert src_168.isbn == "9789263101686"


def test_05_dt9_pas_disbn_pour_5_bases(db_session: Session) -> None:
    codes_bases = ("nasa_power", "ecmwf_era5", "anm_guinee_stations", "wmo_grdc", "wwf_hydrosheds")
    rows = db_session.execute(
        select(Source.code, Source.isbn).where(Source.code.in_(codes_bases))
    ).all()
    assert len(rows) == 5
    for row in rows:
        assert row.isbn is None, f"{row.code} : isbn attendu NULL, trouvé {row.isbn!r}"


# ---------------------------------------------------------------------------
# 6. Acknowledgement présent dans notes pour les 9
# ---------------------------------------------------------------------------


def test_06_dt10_acknowledgement_present_pour_9_lignes(db_session: Session) -> None:
    """Chaque fiche transcrit un acknowledgement (Acknowledgement / Citation
    canonique / officielle / suggérée / requise) dans le champ ``notes``.
    Pattern case-insensitive ``(acknowledgement|citation)``.
    """
    rows = db_session.execute(
        select(Source.code, Source.notes).where(Source.code.in_(_CODES_SOURCES))
    ).all()
    assert len(rows) == 9
    pattern = re.compile(r"(acknowledgement|citation)", re.IGNORECASE)
    for row in rows:
        assert row.notes is not None, row.code
        assert pattern.search(row.notes) is not None, (
            f"{row.code} : aucun pattern (acknowledgement|citation) trouvé dans notes"
        )


# ---------------------------------------------------------------------------
# 7. Année dans le code (4 avec / 5 sans)
# ---------------------------------------------------------------------------


def test_07_dt11_codes_avec_annee(db_session: Session) -> None:
    pattern = re.compile(r"_(19|20)\d{2}$")
    rows = db_session.execute(select(Source.code).where(Source.code.in_(_CODES_SOURCES))).all()
    codes_en_base = {row.code for row in rows}
    codes_avec_annee_observes = {c for c in codes_en_base if pattern.search(c)}
    assert codes_avec_annee_observes == set(_CODES_AVEC_ANNEE), (
        f"Codes avec année observés : {sorted(codes_avec_annee_observes)} ; "
        f"attendus : {sorted(_CODES_AVEC_ANNEE)}"
    )


def test_07_dt11_codes_sans_annee(db_session: Session) -> None:
    pattern = re.compile(r"_(19|20)\d{2}$")
    rows = db_session.execute(select(Source.code).where(Source.code.in_(_CODES_SOURCES))).all()
    codes_en_base = {row.code for row in rows}
    codes_sans_annee_observes = {c for c in codes_en_base if not pattern.search(c)}
    assert codes_sans_annee_observes == set(_CODES_SANS_ANNEE), (
        f"Codes sans année observés : {sorted(codes_sans_annee_observes)} ; "
        f"attendus : {sorted(_CODES_SANS_ANNEE)}"
    )


# ---------------------------------------------------------------------------
# 8. Scope Vol I WMO : suffixe DOI /1
# ---------------------------------------------------------------------------


def test_08_dt12_wmo_8_2024_doi_suffixe_vol_i(db_session: Session) -> None:
    src = db_session.scalars(select(Source).where(Source.code == "wmo_8_2024")).one()
    assert src.doi == "10.59327/WMO/CIMO/1"
    assert src.doi.endswith("/1"), (
        f"wmo_8_2024 : DOI attendu suffixe /1 (scope Vol I DT-12), trouvé {src.doi!r}"
    )


# ---------------------------------------------------------------------------
# 9. Date consultation uniforme
# ---------------------------------------------------------------------------


def test_09_date_consultation_uniforme(db_session: Session) -> None:
    rows = db_session.execute(
        select(Source.code, Source.date_consultation).where(Source.code.in_(_CODES_SOURCES))
    ).all()
    assert len(rows) == 9
    date_attendue = date(2026, 5, 10)
    for row in rows:
        assert row.date_consultation == date_attendue, (
            f"{row.code} : date_consultation={row.date_consultation!r}, attendu {date_attendue!r}"
        )


# ---------------------------------------------------------------------------
# 10. Fiabilité uniforme
# ---------------------------------------------------------------------------


def test_10_fiabilite_uniforme_haute(db_session: Session) -> None:
    rows = db_session.execute(
        select(Source.code, Source.fiabilite).where(Source.code.in_(_CODES_SOURCES))
    ).all()
    assert len(rows) == 9
    for row in rows:
        assert row.fiabilite == "haute", (
            f"{row.code} : fiabilite={row.fiabilite!r}, attendu 'haute'"
        )


# ---------------------------------------------------------------------------
# 11. Audit
# ---------------------------------------------------------------------------


def test_11_audit_9_lignes_insert_auteur_null(db_session: Session) -> None:
    ids_sources = list(
        db_session.scalars(select(Source.id).where(Source.code.in_(_CODES_SOURCES))).all()
    )
    id_strs = [str(i) for i in ids_sources]

    lignes = list(
        db_session.scalars(
            select(AuditLog)
            .where(AuditLog.table_auditee == "sources")
            .where(AuditLog.id_ligne_auditee.in_(id_strs))
            .where(AuditLog.type_operation == "I")
        ).all()
    )
    assert len(lignes) == 9
    for ligne in lignes:
        assert ligne.auteur_applicatif is None


# ---------------------------------------------------------------------------
# Roundtrip Alembic (test optionnel, marker regression)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_roundtrip_alembic_012() -> None:
    """``downgrade -1`` puis ``upgrade head`` revérifie le compte de 9.

    Test exécuté en dehors d'une fixture ``db_session`` car Alembic ouvre
    sa propre connexion. Vérifications post-roundtrip via une session
    dédiée.
    """
    from kuma_data_core.db.session import get_engine

    cfg = Config("alembic.ini")
    engine = get_engine()

    with Session(engine) as s:
        n_initial = s.scalar(
            select(func.count()).select_from(Source).where(Source.code.in_(_CODES_SOURCES))
        )
    assert n_initial == 9

    # Cible la révision explicite "011" plutôt que "-1" : "-1" dépend du
    # head courant et casserait ce test dès qu'une migration ultérieure
    # serait ajoutée (corrigé conjointement sur le roundtrip
    # localites qui cible désormais "010").
    command.downgrade(cfg, "011")
    with Session(engine) as s:
        n_apres_down = s.scalar(
            select(func.count()).select_from(Source).where(Source.code.in_(_CODES_SOURCES))
        )
    assert n_apres_down == 0

    command.upgrade(cfg, "head")
    with Session(engine) as s:
        n_final = s.scalar(
            select(func.count()).select_from(Source).where(Source.code.in_(_CODES_SOURCES))
        )
    assert n_final == 9

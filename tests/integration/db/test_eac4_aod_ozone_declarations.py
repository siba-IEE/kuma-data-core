"""Tests d'integration des declarations EAC4 AOD 550 nm et ozone de surface.

Verifie l'etat apres ``alembic upgrade head`` (migration 122) : unite
``partie_par_milliard``, quatre grandeurs brutes F1 stockees avec la bonne unite,
leurs seules series etant celles de la reanalyse EAC4 (migrations 123-124, detail
dans ``test_eac4_aod_ozone_series.py``), et des
libelles / descriptions publiables (tables dumpees telles quelles dans l'edition
publique) sans vocabulaire de chantier.

Pattern herite de ``test_vague5_pm_eac4_lot_a.py``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.integration.db._jargon import JARGON_INTERNE as _JARGON_INTERNE

pytestmark = pytest.mark.integration

_UNITE_PAR_GRANDEUR: dict[str, str] = {
    "aod_550": "sans_unite",
    "aod_poussiere_550": "sans_unite",
    "ozone_surface": "partie_par_milliard",
    "ozone_surface_diurne": "partie_par_milliard",
}


def test_unite_partie_par_milliard(db_session: Session) -> None:
    row = db_session.execute(
        text(
            "SELECT symbole, grandeur, systeme, est_unite_de_base, facteur_conversion_si, "
            "decalage_conversion_si, code_unite_si, actif "
            "FROM unites WHERE code = 'partie_par_milliard'"
        )
    ).one()
    assert row.symbole == "ppb"
    assert row.grandeur == "fraction_molaire"
    assert row.systeme == "non_SI_acceptee"
    assert row.est_unite_de_base is False
    assert float(row.facteur_conversion_si) == 1e-9
    assert float(row.decalage_conversion_si) == 0.0
    assert row.code_unite_si == "sans_unite"
    assert row.actif is True


def test_quatre_grandeurs_declarees(db_session: Session) -> None:
    rows = db_session.execute(
        text(
            """
            SELECT gr.code, gr.famille, gr.strategie_calcul, gr.actif, u.code AS unite
            FROM grandeurs_referentiel gr JOIN unites u ON u.id = gr.unite_id
            WHERE gr.code = ANY(:codes)
            """
        ),
        {"codes": list(_UNITE_PAR_GRANDEUR)},
    ).all()
    assert {r.code for r in rows} == set(_UNITE_PAR_GRANDEUR)
    for r in rows:
        assert r.famille == "F1", r.code
        assert r.strategie_calcul == "stockee", r.code
        assert r.actif is True, r.code
        assert r.unite == _UNITE_PAR_GRANDEUR[r.code], r.code


def test_series_uniquement_eac4(db_session: Session) -> None:
    """Les 136 series de ces grandeurs viennent de la reanalyse EAC4 (migrations 123-124)."""
    rows = db_session.execute(
        text(
            "SELECT s.code AS source, COUNT(*) AS n FROM series_metadonnees sm "
            "JOIN sources s ON s.id = sm.source_id "
            "WHERE sm.grandeur_code = ANY(:codes) GROUP BY s.code"
        ),
        {"codes": list(_UNITE_PAR_GRANDEUR)},
    ).all()
    assert [(r.source, int(r.n)) for r in rows] == [("cams_eac4", 136)]


def test_textes_publics_sans_jargon(db_session: Session) -> None:
    rows = db_session.execute(
        text(
            "SELECT code, libelle, description FROM grandeurs_referentiel WHERE code = ANY(:codes)"
        ),
        {"codes": list(_UNITE_PAR_GRANDEUR)},
    ).all()
    unite = db_session.execute(
        text(
            "SELECT code, libelle, note_methodologique FROM unites "
            "WHERE code = 'partie_par_milliard'"
        )
    ).one()
    textes = [(r.code, r.libelle) for r in rows] + [(r.code, r.description) for r in rows]
    textes += [(unite.code, unite.libelle), (unite.code, unite.note_methodologique)]
    assert len(textes) == 10
    fautifs = [(code, t) for code, t in textes if not t or _JARGON_INTERNE.search(t)]
    assert fautifs == [], f"Textes vides ou avec jargon interne : {fautifs}"

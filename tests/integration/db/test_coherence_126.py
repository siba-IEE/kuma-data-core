"""Tests d'intégration de la migration 126 (stratégie de calcul des grandeurs F1).

- Invariant : aucune grandeur ``calculee_volee`` n'a de ligne dans
  ``grandeurs_metier`` (le commentaire de la colonne ``strategie_calcul``
  fait foi : ``stockee`` = valeur persistée dans ``grandeurs_metier``).
- Les cinq grandeurs F1 matérialisées sont ``stockee``.
- Leurs descriptions publiques : sans jargon de chantier, sans annonce d'un
  calcul à la volée, sans couverture chiffrée, conformes au calcul réel.
- ``rang_referentiel`` (désactivée, sans ligne) n'est pas touchée.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.integration.db.test_note_publique_series import _JARGON_INTERNE

pytestmark = pytest.mark.integration

_GRANDEURS_126: tuple[str, ...] = (
    "degenerescence_pixel",
    "ecart_relatif_dni_cams",
    "ecart_relatif_referentiel",
    "rang_referentiel_spatial",
    "rang_referentiel_temporel",
)

# Vocabulaire d'une stratégie « à la volée » ou de stockage interne, à
# proscrire dans la description publique d'une grandeur stockée.
_VOCABULAIRE_VOLEE = re.compile(
    r"vol[ée]e|calculee_volee|mat[ée]rialis|grandeurs_metier|p[ée]rim[èe]tre courant",
    re.IGNORECASE,
)
# Couverture figée (« 2004-2020 », « 6 villes pilotes », « 2021-2025 »).
# La période de référence 1991-2020 du rang temporel fait partie de la
# définition, pas de la couverture : elle est tolérée.
_COUVERTURE_FIGEE = re.compile(r"\b(?!1991-2020\b)(19|20)\d{2}\s*-\s*(19|20)\d{2}\b|\b\d+ villes")


def _descriptions(session: Session) -> dict[str, str]:
    rows = session.execute(
        text("SELECT code, description FROM grandeurs_referentiel WHERE code = ANY(:codes)"),
        {"codes": list(_GRANDEURS_126)},
    ).all()
    return {r.code: r.description for r in rows}


def test_aucune_grandeur_calculee_volee_materialisee(db_session: Session) -> None:
    codes = db_session.execute(
        text(
            """
            SELECT DISTINCT gr.code
            FROM grandeurs_referentiel gr
            JOIN grandeurs_metier gm ON gm.grandeur_code = gr.code
            WHERE gr.strategie_calcul = 'calculee_volee'
            ORDER BY gr.code
            """
        )
    ).scalars()
    assert list(codes) == []


def test_cinq_grandeurs_f1_stockees(db_session: Session) -> None:
    rows = db_session.execute(
        text(
            "SELECT code, famille, strategie_calcul FROM grandeurs_referentiel "
            "WHERE code = ANY(:codes)"
        ),
        {"codes": list(_GRANDEURS_126)},
    ).all()
    assert {r.code: (r.famille, r.strategie_calcul) for r in rows} == dict.fromkeys(
        _GRANDEURS_126, ("F1", "stockee")
    )


@pytest.mark.parametrize("code", _GRANDEURS_126)
def test_description_publique_propre(db_session: Session, code: str) -> None:
    description = _descriptions(db_session)[code]
    assert not _JARGON_INTERNE.search(description), description
    assert not _VOCABULAIRE_VOLEE.search(description), description
    assert not _COUVERTURE_FIGEE.search(description), description
    assert "Niveau de confiance B" in description


def test_description_ecart_referentiel_decrit_le_calcul_reel(db_session: Session) -> None:
    """NASA POWER vs PVGIS-SARAH-3, pas un écart à la moyenne des sites."""
    description = _descriptions(db_session)["ecart_relatif_referentiel"]
    assert "(NASA POWER - SARAH-3) / SARAH-3" in description
    assert "PVGIS-SARAH-3" in description
    assert "moyenne de cette grandeur" not in description


def test_rang_spatial_parmi_six_villes_pilotes(db_session: Session) -> None:
    """La description annonce un rang de 1 à 6 parmi six villes : vrai en base."""
    row = db_session.execute(
        text(
            """
            SELECT COUNT(DISTINCT localite_id) AS n_loc, MIN(valeur) AS vmin,
                   MAX(valeur) AS vmax
            FROM grandeurs_metier
            WHERE grandeur_code = 'rang_referentiel_spatial' AND valide_au IS NULL
            """
        )
    ).one()
    assert (row.n_loc, row.vmin, row.vmax) == (6, 1, 6)
    assert "de 1 à 6" in _descriptions(db_session)["rang_referentiel_spatial"]


def test_rang_referentiel_inactive_intacte(db_session: Session) -> None:
    row = db_session.execute(
        text(
            """
            SELECT gr.strategie_calcul, gr.actif,
                   (SELECT COUNT(*) FROM grandeurs_metier gm
                    WHERE gm.grandeur_code = gr.code) AS n_lignes
            FROM grandeurs_referentiel gr WHERE gr.code = 'rang_referentiel'
            """
        )
    ).one()
    assert (row.strategie_calcul, row.actif, row.n_lignes) == ("calculee_volee", False, 0)

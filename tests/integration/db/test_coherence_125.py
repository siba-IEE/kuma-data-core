"""Tests d'intégration de la migration 125 (cohérence éditoriale).

- Commentaires de table ``unites`` et ``grandeurs_referentiel`` : sans
  décompte chiffré (ils ne peuvent plus vieillir), sans jargon de chantier,
  identiques aux modèles ORM (ces tables sont publiées dans l'édition).
- Source ``cams_eac4`` : la description couvre PM, AOD 550 nm et ozone,
  sans jargon ni période figée ; les métadonnées gardent leurs types.
- Garde de régression sur ``strategie_calcul`` : l'ensemble des grandeurs
  ``calculee_volee`` qui ont pourtant des lignes dans ``grandeurs_metier``
  est figé (aucune nouvelle incohérence) en attendant l'arbitrage sur ces
  cinq grandeurs.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.db.models.grandeurs_referentiel import GrandeurReferentiel
from kuma_data_core.db.models.unites import Unite
from tests.integration.db.test_note_publique_series import _JARGON_INTERNE

pytestmark = pytest.mark.integration

# Nombre isolé (« 153 unités », « 20 entrées ») : interdit dans un commentaire
# de table descriptif. « F1 », « F2 », « 550 nm » dans un code ne matchent pas
# (pas de frontière de mot avant le chiffre pour F1/F2).
_NOMBRE_ISOLE = re.compile(r"\b\d+\b")
# Jargon de chantier propre aux anciens commentaires (identifiants d'étape,
# cadrage) en plus du motif partagé des notes publiques.
_JARGON_COMMENTAIRE = re.compile(r"\b\d+-\d+[A-Za-z]?\b|cadrage|post-", re.IGNORECASE)

_TABLES_MODELES = {
    "unites": Unite,
    "grandeurs_referentiel": GrandeurReferentiel,
}


def _commentaire_table(session: Session, table: str) -> str:
    commentaire = session.execute(
        text("SELECT obj_description(CAST(:t AS regclass), 'pg_class')"), {"t": table}
    ).scalar_one()
    assert commentaire, f"commentaire de table absent sur {table}"
    return str(commentaire)


@pytest.mark.parametrize("table", sorted(_TABLES_MODELES))
def test_commentaire_table_intemporel_sans_jargon(db_session: Session, table: str) -> None:
    commentaire = _commentaire_table(db_session, table)
    assert not _NOMBRE_ISOLE.search(commentaire), commentaire
    assert not _JARGON_INTERNE.search(commentaire), commentaire
    assert not _JARGON_COMMENTAIRE.search(commentaire), commentaire


@pytest.mark.parametrize("table", sorted(_TABLES_MODELES))
def test_commentaire_table_aligne_sur_modele(db_session: Session, table: str) -> None:
    assert _commentaire_table(db_session, table) == _TABLES_MODELES[table].__table__.comment


def test_source_cams_eac4_description_couvre_aod_et_ozone(db_session: Session) -> None:
    row = db_session.execute(
        text("SELECT notes, metadonnees FROM sources WHERE code = 'cams_eac4'")
    ).one()
    notes: str = row.notes
    for attendu in ("PM2.5", "PM10", "épaisseur optique des aérosols à 550 nm", "ozone"):
        assert attendu in notes, attendu
    assert not _JARGON_INTERNE.search(notes), notes
    assert not re.search(r"\b(19|20)\d{2}-\d{2}-\d{2}\b", notes), "période figée dans notes"
    assert "L-SOIL" not in notes and "R3" not in notes

    meta = row.metadonnees
    assert meta["variables_ingerees"] == [
        "pm2.5 (pm2p5)",
        "pm10",
        "aod550",
        "duaod550",
        "go3 (niveau modele 60, le plus bas)",
    ]
    # Types inchangés (str) pour les consommateurs éventuels des métadonnées.
    for cle in ("conversion", "agregation_kuma", "periode_reelle"):
        assert isinstance(meta[cle], str), cle
    assert "2004-02-01 a 2025-12-31" in meta["periode_reelle"]
    assert "2021-01-01 a 2025-08-31" in meta["periode_reelle"]
    assert "go3" in meta["conversion"]


def test_periodes_source_cams_eac4_conformes_aux_series(db_session: Session) -> None:
    """Les périodes déclarées dans ``periode_reelle`` sont celles des séries."""
    rows = db_session.execute(
        text(
            """
            SELECT sm.grandeur_code, MIN(sm.periode_debut) AS debut,
                   MAX(sm.periode_fin) AS fin
            FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
            WHERE s.code = 'cams_eac4'
            GROUP BY sm.grandeur_code
            """
        )
    ).all()
    periodes = {r.grandeur_code: (str(r.debut), str(r.fin)) for r in rows}
    for g in ("pm2_5", "pm10"):
        assert periodes[g] == ("2021-01-01", "2025-08-31"), g
    for g in ("aod_550", "aod_poussiere_550", "ozone_surface", "ozone_surface_diurne"):
        assert periodes[g] == ("2004-02-01", "2025-12-31"), g


# Grandeurs déclarées ``calculee_volee`` mais matérialisées dans
# ``grandeurs_metier`` : incohérence connue, en attente d'arbitrage (déclaration
# à aligner sur ``stockee`` et descriptions à réécrire, ou autre sens). Le jeu
# est figé : aucune nouvelle grandeur ne doit rejoindre ce cas.
_CALCULEE_VOLEE_MATERIALISEES_CONNUES = frozenset(
    {
        "degenerescence_pixel",
        "ecart_relatif_dni_cams",
        "ecart_relatif_referentiel",
        "rang_referentiel_spatial",
        "rang_referentiel_temporel",
    }
)


def test_aucune_nouvelle_grandeur_calculee_volee_materialisee(db_session: Session) -> None:
    codes = set(
        db_session.execute(
            text(
                """
                SELECT DISTINCT gr.code
                FROM grandeurs_referentiel gr
                JOIN grandeurs_metier gm ON gm.grandeur_code = gr.code
                WHERE gr.strategie_calcul = 'calculee_volee'
                """
            )
        ).scalars()
    )
    assert codes == _CALCULEE_VOLEE_MATERIALISEES_CONNUES

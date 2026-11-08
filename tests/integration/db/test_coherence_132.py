"""Tests d'intégration de la migration 132 (couverture complète dans les textes publiés).

- Chaque libellé de série écrit sa localité exactement comme ``localites.nom``
  (``Kaloum``, ``Labé``, ``Nzérékoré``), sans graphie approchante.
- Aucun texte publié (colonnes de texte des ``TABLES_PUBLIEES`` et colonnes non
  neutralisées des ``TABLES_ASSAINIES``) ne présente une partie des localités
  comme « pilotes » : toutes sont couvertes.
- ``ghi_exceedance``, dont la description annonce les 34 localités, répond
  pour chacune.

Seule exception admise : les textes de ``rang_referentiel_spatial``, repris
par la migration 133, qui retirera ``_EXCEPTIONS_RANG_SPATIAL``.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.publication.manifeste import TABLES_ASSAINIES, TABLES_PUBLIEES
from tests.integration.db.test_coherence_128 import _colonnes_texte

pytestmark = pytest.mark.integration

_PILOTE = re.compile(r"pilote", re.IGNORECASE)

# A retirer par la migration 133, qui récrit ces textes.
_EXCEPTIONS_RANG_SPATIAL: frozenset[tuple[str, str, str]] = frozenset(
    {("grandeurs_referentiel", "description", "rang_referentiel_spatial")}
    | {
        (
            "series_metadonnees",
            "note_publique",
            f"{alias}_rang_referentiel_spatial_kuma_calculs_2021_2025",
        )
        for alias in (
            "gin_conakry",
            "gin_kankan",
            "gin_kindia",
            "gin_labe",
            "gin_mamou",
            "gin_nzerekore",
        )
    }
)


def _cle(session: Session, table: str) -> str:
    colonnes = set(
        session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t"
            ),
            {"t": table},
        )
        .scalars()
        .all()
    )
    return "code" if "code" in colonnes else "id"


@pytest.mark.parametrize("table", sorted(TABLES_PUBLIEES | TABLES_ASSAINIES))
def test_aucun_texte_publie_ne_parle_de_pilote(db_session: Session, table: str) -> None:
    cle = _cle(db_session, table)
    fautifs: list[tuple[str, str, str]] = []
    for colonne in _colonnes_texte(db_session, table):
        lignes = db_session.execute(
            text(
                f'SELECT DISTINCT CAST("{cle}" AS text) AS cle, CAST("{colonne}" AS text) AS v '
                f'FROM "{table}" WHERE CAST("{colonne}" AS text) ~* \'pilote\''
            )
        ).all()
        fautifs.extend(
            (colonne, r.cle, r.v[:120])
            for r in lignes
            if _PILOTE.search(r.v) and (table, colonne, r.cle) not in _EXCEPTIONS_RANG_SPATIAL
        )
    assert fautifs == []


def test_exceptions_rang_spatial_toujours_utiles(db_session: Session) -> None:
    """Chaque exception couvre encore un texte « pilote » ; la 133 les retirera."""
    n_desc = db_session.execute(
        text(
            "SELECT count(*) FROM grandeurs_referentiel "
            "WHERE code = 'rang_referentiel_spatial' AND description ~* 'pilote'"
        )
    ).scalar_one()
    n_notes = db_session.execute(
        text(
            "SELECT count(*) FROM series_metadonnees "
            "WHERE grandeur_code = 'rang_referentiel_spatial' AND note_publique ~* 'pilote'"
        )
    ).scalar_one()
    assert n_desc + n_notes == len(_EXCEPTIONS_RANG_SPATIAL)


def test_libelles_ecrivent_localites_nom(db_session: Session) -> None:
    """Hors rang_referentiel_spatial, tout libellé porte le nom exact de sa localité."""
    rows = db_session.execute(
        text(
            """
            SELECT s.code, s.libelle, l.nom FROM series_metadonnees s
            JOIN localites l ON l.id = s.localite_id
            WHERE s.grandeur_code <> 'rang_referentiel_spatial'
              AND s.libelle !~ ('(^|[^[:alnum:]_-])' || l.nom || '($|[^[:alnum:]_-])')
            ORDER BY s.code
            """
        )
    ).all()
    assert rows == []


def test_aucune_graphie_approchante(db_session: Session) -> None:
    rows = db_session.execute(
        text(
            """
            SELECT s.code, s.libelle FROM series_metadonnees s
            WHERE s.grandeur_code <> 'rang_referentiel_spatial'
              AND s.libelle ~ '(Conakry-Kaloum|Labe([^[:alnum:]_]|$)|Nzerekore([^[:alnum:]_]|$))'
            ORDER BY s.code
            """
        )
    ).all()
    assert rows == []


def test_libelles_kaloum_labe_nzerekore(db_session: Session) -> None:
    libelles = dict(
        db_session.execute(
            text(
                "SELECT code, libelle FROM series_metadonnees WHERE code = ANY(:c)",
            ),
            {
                "c": [
                    "gin_conakry_ghi_power_1991_2020",
                    "gin_labe_hep_kuma_calculs_1991_2020",
                    "gin_nzerekore_pm2_5_cams_eac4_2021_2025",
                ]
            },
        ).all()
    )
    assert libelles == {
        "gin_conakry_ghi_power_1991_2020": (
            "GHI mensuel Kaloum 1991-2020 (NASA POWER, fenetre climatologique OMM)"
        ),
        "gin_labe_hep_kuma_calculs_1991_2020": (
            "HEP climato mensuelle Labé 1991-2020 (Kuma calculs, derive de "
            "gin_labe_ghi_power_1991_2020 (GHI mensuel NASA POWER))"
        ),
        "gin_nzerekore_pm2_5_cams_eac4_2021_2025": "PM2.5 journalier Nzérékoré 2021-2025 (EAC4)",
    }


def test_note_horaire_decrit_la_couverture(db_session: Session) -> None:
    n = db_session.execute(
        text(
            "SELECT count(*) FROM series_metadonnees WHERE note_publique LIKE "
            "'%Série horaire : un contrôle qualité, appliqué aux séries horaires de toutes "
            "les localités couvertes, signale les valeurs suspectes sans les supprimer.%'"
        )
    ).scalar_one()
    assert n == 36


def test_ghi_exceedance_pour_toutes_les_localites_couvertes(
    db_session: Session, client: TestClient, headers_auth: dict[str, str]
) -> None:
    """La description annonce 34 localités : chacune a sa série et obtient une réponse."""
    description = db_session.execute(
        text("SELECT description FROM grandeurs_referentiel WHERE code = 'ghi_exceedance'")
    ).scalar_one()
    assert "les 34 localités couvertes disposent de cette série" in description
    localites = (
        db_session.execute(
            text(
                """
                SELECT DISTINCT l.code FROM series_metadonnees s
                JOIN localites l ON l.id = s.localite_id
                ORDER BY l.code
                """
            )
        )
        .scalars()
        .all()
    )
    assert len(localites) == 34
    for code in localites:
        r = client.get(f"/v1/grandeurs/ghi_exceedance/{code}", headers=headers_auth)
        assert r.status_code == 200, code
        assert r.json()["base_annees"] == 30, code

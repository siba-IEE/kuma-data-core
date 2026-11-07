"""Tests d'integration des series EAC4 AOD 550 nm et ozone de surface (migrations 123-124).

Verifie l'etat apres ``alembic upgrade head`` :

- **Structure** : 136 series (34 points x 4 grandeurs), codes
  ``<localite>_<grandeur>_cams_eac4_2004_2025`` (Conakry sous
  ``gin_conakry_kaloum``), source ``cams_eac4``, granularite journaliere,
  methode ``modele_satellitaire``, unite de la grandeur, periode egale a la
  periode reelle de capture (2004-02-01 -> 2025-12-31).
- **Donnees** : 8 005 mesures par serie, confiance B (coherente avec les
  regles R1-R4), valeurs ponctuelles egales au seed, AOD poussieres <= AOD
  totale.
- **Textes publics** : notes et libelles sans jargon interne, caveat des pics
  d'ozone, attribution Copernicus dans le journal interne.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.db.seeds.cams_eac4_aod_ozone_journalier_seed_data import (
    iter_blocs_cams_eac4_aod_ozone,
    iter_captures_cams_eac4_aod_ozone,
)
from kuma_data_core.editorial.niveaux_confiance import calculer_niveau_confiance_derive
from tests.integration.db.test_note_publique_series import _JARGON_INTERNE

pytestmark = pytest.mark.integration

_UNITE_PAR_GRANDEUR: dict[str, str] = {
    "aod_550": "sans_unite",
    "aod_poussiere_550": "sans_unite",
    "ozone_surface": "partie_par_milliard",
    "ozone_surface_diurne": "partie_par_milliard",
}
_GRANDEURS_AOD = ("aod_550", "aod_poussiere_550")
_GRANDEURS_OZONE = ("ozone_surface", "ozone_surface_diurne")
_NB_POINTS = 34
_JOURS_PAR_SERIE = 8_005
_PERIODE = (dt.date(2004, 2, 1), dt.date(2025, 12, 31))
_ATTRIBUTION = (
    "Generated using Copernicus Atmosphere Monitoring Service Information 2026 (licence CC-BY)"
)


def _code_serie(localite_code: str, grandeur: str) -> str:
    return f"{localite_code}_{grandeur}_cams_eac4_2004_2025"


def _localites_seed() -> list[str]:
    return sorted({loc for loc, _ in iter_captures_cams_eac4_aod_ozone()})


def _tous_les_codes() -> list[str]:
    return [_code_serie(loc, g) for loc in _localites_seed() for g in _UNITE_PAR_GRANDEUR]


def _series(db_session: Session) -> list[Any]:
    return list(
        db_session.execute(
            text(
                """
                SELECT sm.id, sm.code, sm.libelle, sm.grandeur_code, sm.granularite,
                       sm.methode_collecte, sm.periode_debut, sm.periode_fin,
                       sm.note_publique, sm.commentaire_editorial,
                       s.code AS source_code, s.fiabilite, l.code AS localite_code,
                       u.code AS unite
                FROM series_metadonnees sm
                JOIN sources s ON s.id = sm.source_id
                JOIN localites l ON l.id = sm.localite_id
                JOIN grandeurs_referentiel gr ON gr.code = sm.grandeur_code
                JOIN unites u ON u.id = gr.unite_id
                WHERE sm.grandeur_code = ANY(:grandeurs)
                """
            ),
            {"grandeurs": list(_UNITE_PAR_GRANDEUR)},
        ).all()
    )


# === Structure =============================================================


def test_136_series_codes_et_metadonnees(db_session: Session) -> None:
    localites = _localites_seed()
    assert len(localites) == _NB_POINTS
    assert "gin_conakry_kaloum" in localites
    rows = _series(db_session)
    assert len(rows) == 136
    assert {r.code for r in rows} == set(_tous_les_codes())
    for r in rows:
        assert r.code == _code_serie(r.localite_code, r.grandeur_code), r.code
        assert r.source_code == "cams_eac4", r.code
        assert r.granularite == "journalier", r.code
        assert r.methode_collecte == "modele_satellitaire", r.code
        assert r.unite == _UNITE_PAR_GRANDEUR[r.grandeur_code], r.code
        assert (r.periode_debut, r.periode_fin) == _PERIODE, r.code


def test_periode_egale_capture(db_session: Session) -> None:
    """La periode des series est la periode reelle de capture, commune aux 34 compagnons."""
    periodes = {
        (c["periode_reelle"]["debut"], c["periode_reelle"]["fin"])
        for _, c in iter_captures_cams_eac4_aod_ozone()
    }
    assert periodes == {("2004-02-01", "2025-12-31")}
    bornes = {(r.periode_debut, r.periode_fin) for r in _series(db_session)}
    assert bornes == {tuple(dt.date.fromisoformat(d) for d in periodes.pop())}


def test_conakry_sous_code_de_localite(db_session: Session) -> None:
    """Conakry porte le code de localite ``gin_conakry_kaloum``, pas l'alias historique."""
    n_alias = db_session.execute(
        text(
            "SELECT COUNT(*) FROM series_metadonnees WHERE code LIKE 'gin\\_conakry\\_%' "
            "AND code NOT LIKE 'gin\\_conakry\\_kaloum\\_%' AND code LIKE '%\\_2004\\_2025' "
            "AND grandeur_code = ANY(:g)"
        ),
        {"g": list(_UNITE_PAR_GRANDEUR)},
    ).scalar_one()
    assert int(n_alias) == 0


# === Donnees ===============================================================


def test_8005_mesures_par_serie(db_session: Session) -> None:
    rows = db_session.execute(
        text(
            """
            SELECT sm.code, COUNT(*) AS n, COUNT(DISTINCT m.instant_mesure) AS n_jours,
                   MIN(m.instant_mesure) AS debut, MAX(m.instant_mesure) AS fin
            FROM mesures_ressource m JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code = ANY(:codes)
            GROUP BY sm.code
            """
        ),
        {"codes": _tous_les_codes()},
    ).all()
    assert len(rows) == 136
    for r in rows:
        assert (r.n, r.n_jours) == (_JOURS_PAR_SERIE, _JOURS_PAR_SERIE), r.code
        assert (r.debut, r.fin) == _PERIODE, r.code


def test_confiance_b_conforme_aux_regles(db_session: Session) -> None:
    niveaux = db_session.execute(
        text(
            """
            SELECT DISTINCT m.niveau_confiance_derive, m.niveau_confiance_override
            FROM mesures_ressource m JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code = ANY(:codes)
            """
        ),
        {"codes": _tous_les_codes()},
    ).all()
    assert [tuple(r) for r in niveaux] == [("B", None)]
    regles = {
        calculer_niveau_confiance_derive(r.methode_collecte, r.fiabilite)
        for r in _series(db_session)
    }
    assert regles == {"B"}


@pytest.mark.parametrize(
    ("localite", "grandeur", "jour"),
    [
        ("gin_conakry_kaloum", "aod_550", "2021-01-01"),
        ("gin_conakry_kaloum", "aod_poussiere_550", "2021-01-01"),
        ("gin_kankan", "ozone_surface", "2016-04-15"),
        ("gin_nzerekore", "ozone_surface_diurne", "2004-02-01"),
        ("gin_labe", "ozone_surface_diurne", "2025-12-31"),
    ],
)
def test_valeur_egale_au_seed(db_session: Session, localite: str, grandeur: str, jour: str) -> None:
    attendu = next(
        b["valeurs"][jour]
        for b in iter_blocs_cams_eac4_aod_ozone()
        if b["localite_code"] == localite and b["grandeur_code"] == grandeur
    )
    valeur = db_session.execute(
        text(
            "SELECT m.valeur FROM mesures_ressource m "
            "JOIN series_metadonnees sm ON sm.id = m.serie_id "
            "WHERE sm.code = :code AND m.instant_mesure = :jour"
        ),
        {"code": _code_serie(localite, grandeur), "jour": dt.date.fromisoformat(jour)},
    ).scalar_one()
    assert valeur == attendu


def test_conakry_aod_550_2021_01_01(db_session: Session) -> None:
    valeur = db_session.execute(
        text(
            "SELECT m.valeur FROM mesures_ressource m "
            "JOIN series_metadonnees sm ON sm.id = m.serie_id "
            "WHERE sm.code = 'gin_conakry_kaloum_aod_550_cams_eac4_2004_2025' "
            "AND m.instant_mesure = '2021-01-01'"
        )
    ).scalar_one()
    assert valeur == pytest.approx(0.3139)


def test_aod_poussiere_inferieure_ou_egale_a_aod_totale(db_session: Session) -> None:
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource tot
            JOIN series_metadonnees st ON st.id = tot.serie_id
            JOIN series_metadonnees sp ON sp.localite_id = st.localite_id
                 AND sp.source_id = st.source_id AND sp.grandeur_code = 'aod_poussiere_550'
                 AND sp.code LIKE '%\\_cams\\_eac4\\_2004\\_2025'
            JOIN mesures_ressource pou ON pou.serie_id = sp.id
                 AND pou.instant_mesure = tot.instant_mesure
            WHERE st.grandeur_code = 'aod_550' AND st.code LIKE '%\\_cams\\_eac4\\_2004\\_2025'
              AND pou.valeur > tot.valeur
            """
        )
    ).scalar_one()
    assert int(n) == 0


# === Textes publics ========================================================


def test_textes_publics_sans_jargon(db_session: Session) -> None:
    rows = _series(db_session)
    textes = [(r.code, r.note_publique) for r in rows] + [(r.code, r.libelle) for r in rows]
    fautifs = [(code, t) for code, t in textes if not t or _JARGON_INTERNE.search(t)]
    assert fautifs == []


def test_note_aod(db_session: Session) -> None:
    for r in _series(db_session):
        if r.grandeur_code not in _GRANDEURS_AOD:
            continue
        for fragment in (
            "550 nm",
            "sans dimension",
            "moyenne des huit analyses",
            "0,75°",
            "80 km",
            "point de grille le plus proche",
            "non une mesure de station",
            "Niveau de confiance B",
        ):
            assert fragment in r.note_publique, (r.code, fragment)


def test_note_ozone_caveat_pics(db_session: Session) -> None:
    for r in _series(db_session):
        if r.grandeur_code not in _GRANDEURS_OZONE:
            continue
        for fragment in (
            "parties par milliard (ppb)",
            "niveau le plus bas du modèle",
            "converties en ppb",
            "février à mai",
            "2006 à 2019",
            "environ 300 ppb en moyenne diurne",
            "jusqu'à environ 340 ppb",
            "médiane d'environ 27 ppb",
            "artefacts du modèle liés aux feux de végétation",
            "conservées telles que fournies par la source",
            "Niveau de confiance B",
        ):
            assert fragment in r.note_publique, (r.code, fragment)
        if r.grandeur_code == "ozone_surface_diurne":
            assert "09 h, 12 h et 15 h UTC" in r.note_publique, r.code


def test_caveat_coherent_avec_le_seed() -> None:
    """Les chiffres du caveat (max ~340, mediane ~27 ppb diurne) restent ceux du seed."""
    valeurs = sorted(
        v
        for b in iter_blocs_cams_eac4_aod_ozone()
        if b["grandeur_code"] == "ozone_surface_diurne"
        for v in b["valeurs"].values()
    )
    assert 330 <= valeurs[-1] <= 350
    assert 26 <= valeurs[len(valeurs) // 2] <= 28


def test_attribution_dans_le_journal_interne(db_session: Session) -> None:
    for r in _series(db_session):
        assert _ATTRIBUTION in r.commentaire_editorial, r.code

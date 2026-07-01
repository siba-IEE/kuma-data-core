"""Tests d'integration de la densification prefectorale.

Migration 085. Verifie l'etat post-085 :

* 33 noeuds ``prefecture`` (``gin_<slug>_prefecture``) sous leur region, portant le
  ``code_administratif_national`` du decret 2025 ;
* 28 nouvelles communes chef-lieu (``gin_<slug>``, ou ``gin_<slug>_centre`` pour
  Boke/Faranah en collision : decision B, pas de re-signification de code) ;
* re-parentage des 5 communes capitales regionales (region -> prefecture) SANS
  recreation (demographie et coordonnees conservees, donc series intactes) ;
* ``gin_boke`` / ``gin_faranah`` restent des regions ;
* demographie NULL sur tous les noeuds crees (D7) ;
* coordonnees corrigees (Forecariah, Lola) effectivement seedees ;
* convention Sec. 5.3 : le noeud prefecture porte les coordonnees du chef-lieu.

Base d'integration a head ; fixture ``db_session`` (connection-as-transaction,
rollback en sortie de test) fournie par ``tests/integration/db/conftest.py``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from kuma_data_core.db.models.localites import Localite

pytestmark = pytest.mark.integration


_CODES_CENTRE: tuple[str, ...] = ("gin_boke_centre", "gin_faranah_centre")

# Communes capitales regionales re-parentees (commune existante -> prefecture).
_REPARENTEES: dict[str, str] = {
    "gin_kankan": "gin_kankan_prefecture",
    "gin_kindia": "gin_kindia_prefecture",
    "gin_labe": "gin_labe_prefecture",
    "gin_mamou": "gin_mamou_prefecture",
    "gin_nzerekore": "gin_nzerekore_prefecture",
}

# Echantillon code decret 2025 (spot-check independant, pas exhaustif).
_CODES_DECRET_ECHANTILLON: dict[str, str] = {
    "gin_boke_prefecture": "BKE",
    "gin_forecariah_prefecture": "FRC",
    "gin_lola_prefecture": "LLA",
    "gin_kankan_prefecture": "KKA",
    "gin_mali_prefecture": "MLI",
}


def test_33_prefectures(db_session: Session) -> None:
    n = db_session.scalar(
        select(func.count()).select_from(Localite).where(Localite.type_localite == "prefecture")
    )
    assert n == 33


def test_total_81_localites(db_session: Session) -> None:
    # 20 pilotes (migration 011) + 33 prefectures + 28 nouvelles communes.
    assert db_session.scalar(select(func.count()).select_from(Localite)) == 81


def test_38_communes_dont_2_centre(db_session: Session) -> None:
    # 38 communes = 10 pilotes (011) + 28 densification.
    n = db_session.scalar(
        select(func.count()).select_from(Localite).where(Localite.type_localite == "commune")
    )
    assert n == 38
    for code in _CODES_CENTRE:
        loc = db_session.scalars(select(Localite).where(Localite.code == code)).one_or_none()
        assert loc is not None, f"commune {code} absente"
        assert loc.type_localite == "commune"


def test_codes_administratifs_33_uniques_format(db_session: Session) -> None:
    codes = [
        r[0]
        for r in db_session.execute(
            select(Localite.code_administratif_national).where(
                Localite.type_localite == "prefecture"
            )
        ).all()
    ]
    assert len(codes) == 33
    assert all(c is not None for c in codes), "un code decret manque sur une prefecture"
    assert len(set(codes)) == 33, "codes decret dupliques"
    assert all(len(c) == 3 and c.isupper() and c.isalpha() for c in codes)
    # Aucun code_administratif_national hors des prefectures.
    autres = db_session.scalar(
        select(func.count())
        .select_from(Localite)
        .where(
            Localite.type_localite != "prefecture",
            Localite.code_administratif_national.isnot(None),
        )
    )
    assert autres == 0


def test_codes_decret_echantillon(db_session: Session) -> None:
    for code, attendu in _CODES_DECRET_ECHANTILLON.items():
        ca = db_session.scalar(
            select(Localite.code_administratif_national).where(Localite.code == code)
        )
        assert ca == attendu, f"{code} : code decret {ca!r}, attendu {attendu!r}"


def test_prefectures_sous_region(db_session: Session) -> None:
    parent = aliased(Localite)
    rows = db_session.execute(
        select(parent.type_localite)
        .select_from(Localite)
        .join(parent, Localite.parent_id == parent.id)
        .where(Localite.type_localite == "prefecture")
    ).all()
    assert len(rows) == 33
    assert all(r[0] == "region_administrative" for r in rows)


def test_communes_sous_prefecture(db_session: Session) -> None:
    # Communes dont le parent est une prefecture = 28 nouvelles + 5 re-parentees = 33.
    parent = aliased(Localite)
    n = db_session.scalar(
        select(func.count())
        .select_from(Localite)
        .join(parent, Localite.parent_id == parent.id)
        .where(Localite.type_localite == "commune", parent.type_localite == "prefecture")
    )
    assert n == 33


def test_reparentage_5_sous_prefecture(db_session: Session) -> None:
    parent = aliased(Localite)
    rows = db_session.execute(
        select(Localite.code, parent.code)
        .join(parent, Localite.parent_id == parent.id)
        .where(Localite.code.in_(tuple(_REPARENTEES)))
    ).all()
    assert {r[0]: r[1] for r in rows} == _REPARENTEES


def test_boke_faranah_restent_regions(db_session: Session) -> None:
    # Decision B : pas de re-signification. gin_boke / gin_faranah = regions.
    for code in ("gin_boke", "gin_faranah"):
        t = db_session.scalar(select(Localite.type_localite).where(Localite.code == code))
        assert t == "region_administrative", f"{code} devrait rester une region, type={t!r}"


def test_conakry_communes_intactes_sous_region(db_session: Session) -> None:
    # Conakry (zone speciale) : ses 5 communes restent sous la region, hors densification.
    parent = aliased(Localite)
    rows = db_session.execute(
        select(parent.code)
        .select_from(Localite)
        .join(parent, Localite.parent_id == parent.id)
        .where(Localite.code.like("gin_conakry_%"))
    ).all()
    assert len(rows) == 5
    assert all(r[0] == "gin_conakry" for r in rows)


def test_demographie_null_sur_densification(db_session: Session) -> None:
    # Tous les noeuds prefecture : demographie NULL (D7).
    n_pref_non_null = db_session.scalar(
        select(func.count())
        .select_from(Localite)
        .where(Localite.type_localite == "prefecture")
        .where((Localite.population_estimee.isnot(None)) | (Localite.annee_population.isnot(None)))
    )
    assert n_pref_non_null == 0
    # Echantillon de nouvelles communes : demographie NULL.
    for code in ("gin_boffa", "gin_boke_centre", "gin_lola"):
        pop = db_session.scalar(select(Localite.population_estimee).where(Localite.code == code))
        an = db_session.scalar(select(Localite.annee_population).where(Localite.code == code))
        assert pop is None and an is None, f"{code} : demographie non nulle ({pop}, {an})"


def test_communes_existantes_non_recreees(db_session: Session) -> None:
    # Les 5 capitales re-parentees conservent leur demographie 2014 : preuve qu'elles
    # ont ete re-parentees (UPDATE), pas supprimees/recreees en demographie NULL.
    for code in _REPARENTEES:
        an = db_session.scalar(select(Localite.annee_population).where(Localite.code == code))
        pop = db_session.scalar(select(Localite.population_estimee).where(Localite.code == code))
        assert an == 2014 and pop is not None, f"{code} : demographie alteree ({pop}, {an})"


def test_coordonnees_corrigees_seedees(db_session: Session) -> None:
    # Forecariah : 9.4325 retenu (correction), PAS la valeur Wikidata erronee 9.717.
    lat_frc = db_session.scalar(select(Localite.latitude).where(Localite.code == "gin_forecariah"))
    assert lat_frc is not None and abs(float(lat_frc) - 9.4325) < 0.01, (
        f"Forecariah lat={lat_frc}, attendu 9.4325 (corrige)"
    )
    # Lola : 7.7997 (OSM) ; le noeud prefecture porte la meme coord (Sec. 5.3).
    lat_lola = db_session.scalar(
        select(Localite.latitude).where(Localite.code == "gin_lola_prefecture")
    )
    assert lat_lola is not None and abs(float(lat_lola) - 7.7997) < 0.01, (
        f"Lola prefecture lat={lat_lola}, attendu 7.7997 (OSM)"
    )


def test_prefecture_porte_coord_chef_lieu(db_session: Session) -> None:
    # Sec. 5.3 : le noeud prefecture porte les coordonnees du chef-lieu = sa commune.
    pref = db_session.scalars(select(Localite).where(Localite.code == "gin_boke_prefecture")).one()
    commune = db_session.scalars(select(Localite).where(Localite.code == "gin_boke_centre")).one()
    assert pref.latitude == commune.latitude
    assert pref.longitude == commune.longitude

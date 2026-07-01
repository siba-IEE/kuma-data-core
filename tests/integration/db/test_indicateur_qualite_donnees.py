"""Tests d'integration `indicateur_qualite_donnees`.

Couvre l'etat post-migration 038 (36 lignes insertees dans
`grandeurs_metier` apres calcul du score qualite sur les 36 series
brutes NASA POWER, dependant de la migration 037 corrective sur
l'EXCLUDE constraint `ex_grandeurs_metier_identite_periode`).

Pattern herite de ``test_grandeurs_metier.py`` : ``db_session``
fixture conftest.py + ``session.begin_nested()`` pour isoler les tests
d'erreur sans casser la transaction exterieure.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kuma_data_core.db.models.grandeurs_metier import GrandeurMetier

pytestmark = pytest.mark.integration


_GRANDEUR_CODE_INDICATEUR: str = "indicateur_qualite_donnees"

# Densification : l'indicateur est etendu aux 28 communes (migration 093).
# Ces tests restent le deliverable des 6 pilotes (migration 038) : scope pilotes pour les
# garder stables ; le decompte communes (168) est verifie dans test_parite_a2.
_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)
_PILOTES_SQL: str = (
    "(SELECT id FROM localites WHERE code IN "
    "('gin_conakry_kaloum','gin_kankan','gin_kindia','gin_labe','gin_mamou','gin_nzerekore'))"
)


def _ids_pilotes(db_session: Session) -> list[int]:
    return [
        int(r[0])
        for r in db_session.execute(
            text("SELECT id FROM localites WHERE code = ANY(:c)"), {"c": list(_PILOTES)}
        ).all()
    ]


def test_ti41_decompte_36_lignes_indicateur(db_session: Session) -> None:
    """`grandeurs_metier` contient 36 lignes
    `grandeur_code='indicateur_qualite_donnees'` pour les 6 pilotes (deliverable migration
    038 ; etendu aux 28 communes, scope pilotes ici)."""
    n = db_session.scalar(
        select(func.count())
        .select_from(GrandeurMetier)
        .where(GrandeurMetier.grandeur_code == _GRANDEUR_CODE_INDICATEUR)
        .where(GrandeurMetier.valide_au.is_(None))
        .where(GrandeurMetier.localite_id.in_(_ids_pilotes(db_session)))
    )
    assert n == 36


def test_ti42_colonnes_constantes_36_lignes(db_session: Session) -> None:
    """Les 36 lignes ont `periode_type='statique'`, `mois IS NULL`,
    `annee_debut=2021`, `annee_fin=2025`, `version_formule=1`,
    `niveau_confiance_derive='B'`."""
    rows = db_session.execute(
        select(
            GrandeurMetier.periode_type,
            GrandeurMetier.mois,
            GrandeurMetier.annee_debut,
            GrandeurMetier.annee_fin,
            GrandeurMetier.version_formule,
            GrandeurMetier.niveau_confiance_derive,
        )
        .where(GrandeurMetier.grandeur_code == _GRANDEUR_CODE_INDICATEUR)
        .where(GrandeurMetier.valide_au.is_(None))
        .where(GrandeurMetier.localite_id.in_(_ids_pilotes(db_session)))
    ).all()
    assert len(rows) == 36
    for r in rows:
        assert r.periode_type == "statique"
        assert r.mois is None
        assert r.annee_debut == 2021
        assert r.annee_fin == 2025
        assert r.version_formule == 1
        assert r.niveau_confiance_derive == "B"


def test_ti43_series_metadonnees_id_pointe_serie_evaluee(db_session: Session) -> None:
    """`series_metadonnees_id` est l'ID de la serie brute evaluee
    (et non d'une serie calculee).

    Assertion explicite : `sm.grandeur_code != 'indicateur_qualite_donnees'`
    sur la serie pointee + `sm.methode_collecte = 'modele_satellitaire'`
    + `s.code = 'nasa_power'` (exception methodologique)."""
    rows = db_session.execute(
        text(
            """
            SELECT
                sm.grandeur_code AS grandeur_pointee,
                sm.methode_collecte,
                s.code AS source_code
            FROM grandeurs_metier gm
            JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
            JOIN sources s ON s.id = sm.source_id
            WHERE gm.grandeur_code = :grandeur_code
              AND gm.valide_au IS NULL
              AND gm.localite_id IN """
            + _PILOTES_SQL
            + """
            """
        ),
        {"grandeur_code": _GRANDEUR_CODE_INDICATEUR},
    ).all()
    assert len(rows) == 36
    for r in rows:
        assert r.grandeur_pointee != _GRANDEUR_CODE_INDICATEUR
        assert r.methode_collecte == "modele_satellitaire"
        assert r.source_code == "nasa_power"


def test_ti44_valeur_dans_plage_effective_phase_1(db_session: Session) -> None:
    """`valeur ∈ {3, 4, 5}` pour les 36 lignes (plage effective,
    jamais 1 ni 2)."""
    valeurs = db_session.execute(
        select(GrandeurMetier.valeur)
        .where(GrandeurMetier.grandeur_code == _GRANDEUR_CODE_INDICATEUR)
        .where(GrandeurMetier.valide_au.is_(None))
        .where(GrandeurMetier.localite_id.in_(_ids_pilotes(db_session)))
    ).all()
    assert len(valeurs) == 36
    for (v,) in valeurs:
        assert int(v) in {3, 4, 5}


def test_ti45_vue_courantes_expose_36_lignes(db_session: Session) -> None:
    """La vue `v_grandeurs_metier_courantes` expose les 36 lignes
    (sanity check sur le filtre automatique
    `valide_au IS NULL + version_formule + statut`)."""
    n = db_session.execute(
        text(
            "SELECT COUNT(*) FROM v_grandeurs_metier_courantes "
            "WHERE grandeur_code = :grandeur_code AND localite_id IN " + _PILOTES_SQL
        ),
        {"grandeur_code": _GRANDEUR_CODE_INDICATEUR},
    ).scalar_one()
    assert n == 36


def test_ti46_check_periode_statique_avec_mois_rejete(db_session: Session) -> None:
    """Insertion test `periode_type='statique'` avec `mois=5` rejetee
    par `ck_grandeurs_metier_periode_coherente` (CHECK posee par migration 036)."""
    serie_id = db_session.execute(
        text(
            "SELECT id FROM series_metadonnees WHERE code = 'gin_conakry_ghi_nasa_power_2021_2025'"
        )
    ).scalar_one()
    localite_id = db_session.execute(
        text("SELECT id FROM localites WHERE code = 'gin_conakry_kaloum'")
    ).scalar_one()

    with db_session.begin_nested():
        ligne = GrandeurMetier(
            grandeur_code=_GRANDEUR_CODE_INDICATEUR,
            localite_id=int(localite_id),
            series_metadonnees_id=int(serie_id),
            periode_type="statique",
            annee_debut=2021,
            annee_fin=2025,
            mois=5,  # incoherent avec periode_type='statique'
            version_formule=1,
            valeur=4.0,
            niveau_confiance_derive="B",
        )
        db_session.add(ligne)
        with pytest.raises(IntegrityError):
            db_session.flush()

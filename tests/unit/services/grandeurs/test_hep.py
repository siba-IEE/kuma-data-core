"""Tests unitaires de ``services.grandeurs.hep`` : agrégation, complétude, garde-fous."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from kuma_data_core.editorial.niveaux_confiance import (
    calculer_niveau_confiance_derive,
)
from kuma_data_core.services.grandeurs.hep import (
    _agreger_hep_journaliers,
    calculer_et_inserer_hep,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers de fixtures
# ---------------------------------------------------------------------------


def _serie_complete_annee(annee: int, valeur_constante: float) -> list[tuple[date, float]]:
    """Série journalière complète d'une année, à valeur constante."""
    debut = date(annee, 1, 1)
    fin = date(annee, 12, 31)
    nb_jours = (fin - debut).days + 1
    return [(debut + timedelta(days=i), valeur_constante) for i in range(nb_jours)]


def _serie_complete_mois(
    annee: int, mois: int, valeur_constante: float
) -> list[tuple[date, float]]:
    """Série journalière complète d'un mois, à valeur constante."""
    import calendar as _calendar  # local pour éviter pollution module

    nb_jours = _calendar.monthrange(annee, mois)[1]
    return [(date(annee, mois, j + 1), valeur_constante) for j in range(nb_jours)]


def test_t1_mapping_unitaire_hep_jour_egale_ghi_jour() -> None:
    """1 kWh/m²/j vaut 1 h_eq/j : février 2025 à 5.0 donne 28 x 5.0."""
    mesures = _serie_complete_mois(2025, 2, 5.0)
    resultat = _agreger_hep_journaliers(mesures)

    assert len(resultat["lignes_mensuelles"]) == 1
    assert len(resultat["lignes_annuelles"]) == 0
    ligne_fev = resultat["lignes_mensuelles"][0]
    assert ligne_fev["annee_debut"] == 2025
    assert ligne_fev["mois"] == 2
    assert ligne_fev["valeur"] == pytest.approx(28 * 5.0)


def test_t2_completude_annuelle_stricte_skip_si_un_jour_manquant() -> None:
    """Un jour manquant en juin écarte l'année et juin, pas les 11 autres mois."""
    mesures = _serie_complete_annee(2025, 5.0)
    mesures = [(d, v) for (d, v) in mesures if d != date(2025, 6, 15)]
    assert len(mesures) == 364

    resultat = _agreger_hep_journaliers(mesures)

    assert resultat["lignes_annuelles"] == []
    assert resultat["annees_skip_completude"] == (2025,)
    assert len(resultat["lignes_mensuelles"]) == 11
    assert (2025, 6) in resultat["mois_skip_completude"]
    assert len(resultat["mois_skip_completude"]) == 1


def test_t3_completude_mensuelle_stricte_skip_si_mois_incomplet() -> None:
    """Février 2025 avec 27 jours est écarté."""
    mesures = [(date(2025, 2, j), 5.0) for j in range(1, 28)]  # 1 à 27 inclus
    assert len(mesures) == 27
    resultat = _agreger_hep_journaliers(mesures)

    assert resultat["lignes_mensuelles"] == []
    assert resultat["mois_skip_completude"] == ((2025, 2),)
    assert resultat["lignes_annuelles"] == []
    assert resultat["annees_skip_completude"] == (2025,)


def test_t4_sanity_hep_annuel_plage_tropicale() -> None:
    """2025 à 5.5 kWh/m²/j : 365 x 5.5 = 2007.5 h_eq, dans [1800, 2200]."""
    mesures = _serie_complete_annee(2025, 5.5)
    resultat = _agreger_hep_journaliers(mesures)

    assert len(resultat["lignes_annuelles"]) == 1
    hep_annuel = resultat["lignes_annuelles"][0]["valeur"]
    assert hep_annuel == pytest.approx(365 * 5.5)
    assert 1800.0 <= hep_annuel <= 2200.0


def test_t5_coherence_somme_mensuel_egale_annuel() -> None:
    """Somme des 12 mois = annuel, sur des valeurs variables."""
    debut = date(2025, 1, 1)
    fin = date(2025, 12, 31)
    nb_jours = (fin - debut).days + 1
    mesures = [(debut + timedelta(days=i), 4.5 + 1.5 * ((i % 30) / 30.0)) for i in range(nb_jours)]
    resultat = _agreger_hep_journaliers(mesures)

    assert len(resultat["lignes_annuelles"]) == 1
    assert len(resultat["lignes_mensuelles"]) == 12
    hep_annuel = resultat["lignes_annuelles"][0]["valeur"]
    somme_mensuels = sum(ligne["valeur"] for ligne in resultat["lignes_mensuelles"])
    assert somme_mensuels == pytest.approx(hep_annuel, rel=1e-9)


def test_t6_runtime_error_si_serie_ghi_amont_absente() -> None:
    """Série GHI amont absente : ``RuntimeError`` qui nomme le code."""
    session = MagicMock()
    # execute : version actuelle (1), série HEP valide, série GHI absente
    serie_hep_row = MagicMock(
        serie_id=42,
        localite_id=1,
        grandeur_code="hep",
        methode_collecte="calcul_derive",
        fiabilite_source="haute",
    )
    session.execute.side_effect = [
        MagicMock(scalar=MagicMock(return_value=1)),
        MagicMock(first=MagicMock(return_value=serie_hep_row)),
        MagicMock(first=MagicMock(return_value=None)),
    ]

    with pytest.raises(RuntimeError, match=r"Serie GHI amont .* introuvable"):
        calculer_et_inserer_hep(
            session=session,
            code_serie_hep="gin_test_hep_kuma_calculs_2021_2025",
            code_serie_ghi_amont="gin_test_ghi_inexistant",
        )


def test_runtime_error_si_serie_amont_pas_ghi() -> None:
    """Série amont d'une autre grandeur : ``RuntimeError`` avant toute lecture de mesures."""
    session = MagicMock()
    serie_hep_row = MagicMock(
        serie_id=42,
        localite_id=1,
        grandeur_code="hep",
        methode_collecte="calcul_derive",
        fiabilite_source="haute",
    )
    serie_t2m_row = MagicMock(serie_id=7, localite_id=1, grandeur_code="t2m")
    session.execute.side_effect = [
        MagicMock(scalar=MagicMock(return_value=1)),
        MagicMock(first=MagicMock(return_value=serie_hep_row)),
        MagicMock(first=MagicMock(return_value=serie_t2m_row)),
    ]

    with pytest.raises(
        RuntimeError,
        match=r"Serie 'gin_test_t2m_nasa_power_2021_2025' : grandeur_code='t2m', attendu 'ghi'\.",
    ):
        calculer_et_inserer_hep(
            session=session,
            code_serie_hep="gin_test_hep_kuma_calculs_2021_2025",
            code_serie_ghi_amont="gin_test_t2m_nasa_power_2021_2025",
        )
    assert session.execute.call_count == 3


def test_t7_runtime_error_si_version_formule_desalignee() -> None:
    """``version_formule=2`` contre 1 au référentiel : ``RuntimeError`` avant toute lecture."""
    session = MagicMock()
    session.execute.return_value.scalar.return_value = 1

    with pytest.raises(RuntimeError, match="Desalignement version_formule"):
        calculer_et_inserer_hep(
            session=session,
            code_serie_hep="gin_test_hep_kuma_calculs_2021_2025",
            code_serie_ghi_amont="gin_test_ghi_nasa_power_2021_2025",
            version_formule=2,
        )


def test_t8_niveau_b_pour_calcul_derive_avec_fiabilite_haute() -> None:
    """``calcul_derive`` + source ``haute`` sans niveaux d'entrée : R4 donne B."""
    niveau = calculer_niveau_confiance_derive(
        methode_collecte="calcul_derive",
        fiabilite_source="haute",
    )
    assert niveau == "B"

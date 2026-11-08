"""Tests unitaires de ``services.grandeurs.ghi_exceedance``."""

from __future__ import annotations

import pytest

from kuma_data_core.services.grandeurs.ghi_exceedance import (
    NOMBRE_ANNEES_BASE,
    PAIRES_COLOCALISEES_D29,
    calculer_ghi_exceedance,
    calculer_totaux_annuels,
)

pytestmark = pytest.mark.unit


def test_t_exc_1_cas_standard_30_valeurs() -> None:
    """30 totaux régulièrement espacés de 1700 à 2099 : médiane et 10ᵉ percentile interpolé."""
    totaux = [1700.0 + i * (399.0 / 29.0) for i in range(30)]
    assert len(totaux) == 30
    r = calculer_ghi_exceedance(totaux)
    # mediane : moyenne des 2 valeurs centrales (indices 14 et 15)
    assert abs(r.p50 - (totaux[14] + totaux[15]) / 2) < 0.01
    # position 0.10 x (30 - 1) = 2.9, entre les indices 2 et 3
    valeur_attendue_p90 = totaux[2] + 0.9 * (totaux[3] - totaux[2])
    assert abs(r.p90 - valeur_attendue_p90) < 0.01


def test_t_exc_2_p90_strictement_inferieur_p50() -> None:
    """P90 (10ᵉ percentile) < P50 sur une distribution non dégénérée."""
    totaux = [1750.0 + i * 10.0 for i in range(30)]
    r = calculer_ghi_exceedance(totaux)
    assert r.p90 < r.p50


def test_t_exc_3_distribution_degeneree_p50_egal_p90() -> None:
    """Distribution constante : P50 == P90."""
    totaux = [2000.0] * 30
    r = calculer_ghi_exceedance(totaux)
    assert r.p50 == 2000.0
    assert r.p90 == 2000.0


def test_t_exc_4_sequence_insuffisante_leve_erreur() -> None:
    """T-EXC-4 : moins de 2 valeurs -> ValueError clair."""
    with pytest.raises(ValueError, match="au moins 2 totaux"):
        calculer_ghi_exceedance([])
    with pytest.raises(ValueError, match="au moins 2 totaux"):
        calculer_ghi_exceedance([2000.0])


def test_t_exc_5_totaux_annuels_annee_commune_vs_bissextile() -> None:
    """5.0 kWh/m²/jour chaque mois : 365 x 5.0 en 1991, 366 x 5.0 en 1992."""
    mesures_1991 = [(1991, m, 5.0) for m in range(1, 13)]
    mesures_1992 = [(1992, m, 5.0) for m in range(1, 13)]
    totaux_1991 = calculer_totaux_annuels(mesures_1991)
    totaux_1992 = calculer_totaux_annuels(mesures_1992)
    assert totaux_1991[1991] == 5.0 * 365  # annee commune
    assert totaux_1992[1992] == 5.0 * 366  # annee bissextile (+1 jour)


def test_t_exc_6_totaux_annuels_pondere_par_jours_mois() -> None:
    """T-EXC-6 : chaque mois pondere par son nombre de jours reel."""
    nb_jours_2023 = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    assert sum(nb_jours_2023) == 365
    # Valeur mensuelle distincte par mois pour eviter une compensation.
    mesures = [(2023, m, float(m)) for m in range(1, 13)]
    totaux = calculer_totaux_annuels(mesures)
    attendu = sum(float(m) * nb_jours_2023[m - 1] for m in range(1, 13))
    assert totaux[2023] == attendu


def test_t_exc_7_paires_colocalisees_d29_reciproques() -> None:
    """T-EXC-7 : Kindia et Mamou se referencent mutuellement."""
    assert PAIRES_COLOCALISEES_D29["gin_kindia"] == "gin_mamou"
    assert PAIRES_COLOCALISEES_D29["gin_mamou"] == "gin_kindia"
    # Ces 2 paires sont les seules connues a date.
    assert set(PAIRES_COLOCALISEES_D29.keys()) == {"gin_kindia", "gin_mamou"}


def test_t_exc_8_nombre_annees_base_constant() -> None:
    """T-EXC-8 : 30 annees (1991-2020 inclus, OMM)."""
    assert NOMBRE_ANNEES_BASE == 30

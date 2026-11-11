"""Dérivées arithmétiques de la ressource et calage par saison."""

from __future__ import annotations

import pytest

from kuma_data_core.services.capsule.arithmetique import (
    JOURS_PAR_MOIS,
    CalageIncompletError,
    caler_climatologie,
    climatologie_source_hep,
    facteurs_calage,
    hep_annuelle,
    hep_annuelle_reconstituee,
)

pytestmark = pytest.mark.unit

_DEUX_SAISONS = [
    {"nom": "seche", "mois": [11, 12, 1, 2, 3, 4], "biais": 0.25},
    {"nom": "pluies", "mois": [5, 6, 7, 8, 9, 10], "biais": -0.20},
]


def test_hep_source_est_la_moyenne_horaire_fois_24_sur_1000() -> None:
    mois = [m for m in range(1, 13) for _ in range(2)]
    ghi = [g for m in range(1, 13) for g in (0.0, 100.0 * m)]
    resultat = climatologie_source_hep(mois, ghi)
    assert resultat == pytest.approx([50.0 * m * 24 / 1000 for m in range(1, 13)])


def test_hep_source_refuse_un_mois_sans_pas_horaire() -> None:
    with pytest.raises(ValueError, match="aucun pas horaire pour le mois 12"):
        climatologie_source_hep(list(range(1, 12)), [1.0] * 11)


def test_hep_source_refuse_un_mois_hors_bornes() -> None:
    with pytest.raises(ValueError, match="hors bornes"):
        climatologie_source_hep([13], [1.0])


def test_facteur_de_calage_est_l_inverse_de_un_plus_biais() -> None:
    facteurs = facteurs_calage(_DEUX_SAISONS)
    assert facteurs[0] == pytest.approx(1 / 1.25)
    assert facteurs[6] == pytest.approx(1 / 0.80)
    assert len(facteurs) == 12


def test_calage_refuse_un_mois_couvert_deux_fois() -> None:
    saisons = [*_DEUX_SAISONS, {"nom": "doublon", "mois": [1], "biais": 0.0}]
    with pytest.raises(CalageIncompletError, match="plusieurs saisons"):
        facteurs_calage(saisons)


def test_calage_refuse_un_mois_non_couvert() -> None:
    with pytest.raises(CalageIncompletError, match="mois 5 couvert par aucune saison"):
        facteurs_calage(_DEUX_SAISONS[:1])


def test_calage_refuse_un_mois_hors_bornes() -> None:
    with pytest.raises(CalageIncompletError, match="hors bornes"):
        facteurs_calage([{"nom": "x", "mois": [0], "biais": 0.0}])


def test_climatologie_calee_applique_le_facteur_du_mois() -> None:
    calee = caler_climatologie([5.0] * 12, _DEUX_SAISONS)
    assert calee[0] == pytest.approx(4.0)
    assert calee[6] == pytest.approx(6.25)


def test_climatologie_calee_exige_douze_mois() -> None:
    with pytest.raises(ValueError, match="12 valeurs"):
        caler_climatologie([5.0] * 11, _DEUX_SAISONS)


def test_hep_annuelle_est_ponderee_par_les_jours_du_mois() -> None:
    climatologie = [0.0] * 12
    climatologie[1] = 365.0  # février : 28 jours
    assert hep_annuelle(climatologie) == pytest.approx(28.0)
    assert sum(JOURS_PAR_MOIS) == 365


def test_hep_reconstituee_sans_calage_est_la_hep_brute() -> None:
    climatologie = [float(m) for m in range(1, 13)]
    assert hep_annuelle_reconstituee(climatologie, None) == hep_annuelle(climatologie)


def test_hep_reconstituee_avec_calage_est_la_hep_de_la_climatologie_calee() -> None:
    climatologie = [5.0] * 12
    attendu = hep_annuelle(caler_climatologie(climatologie, _DEUX_SAISONS))
    assert hep_annuelle_reconstituee(climatologie, _DEUX_SAISONS) == pytest.approx(attendu)

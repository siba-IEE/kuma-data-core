"""Tests unitaires de ``services.grandeurs.referentiels``."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from kuma_data_core.services.grandeurs.referentiels import (
    ContexteRangSpatial,
    _agreger_mensuel,
    _calcul_ecart_relatif,
    _calcul_rang_spatial,
    _calcul_rang_temporel,
    _lignes_rang_spatial,
    calculer_et_inserer_rang_spatial,
)

pytestmark = pytest.mark.unit


def test_t1_agreger_mensuel_moyenne_basique() -> None:
    """T-1 : moyenne arithmetique sur 31 valeurs (mois complet)."""
    valeurs = [5.0] * 31
    assert _agreger_mensuel(valeurs) == pytest.approx(5.0)

    valeurs_var = [4.0, 5.0, 6.0]
    assert _agreger_mensuel(valeurs_var) == pytest.approx(5.0)


def test_t2_agreger_mensuel_vide_rejete() -> None:
    """T-2 : sequence vide -> ValueError."""
    with pytest.raises(ValueError, match="Aucune valeur"):
        _agreger_mensuel([])


def test_t3_calcul_ecart_relatif_signe() -> None:
    """Écart signé : (5.5 - 5.3) / 5.3 ≈ +3.8 %, négatif si Kuma est sous SARAH-3."""
    ecart = _calcul_ecart_relatif(valeur_kuma=5.5, valeur_sarah3=5.3)
    assert ecart == pytest.approx(3.7735849, rel=1e-5)

    # Cas inverse : Kuma sous-estime SARAH-3
    ecart_negatif = _calcul_ecart_relatif(valeur_kuma=5.0, valeur_sarah3=5.5)
    assert ecart_negatif == pytest.approx(-9.0909, rel=1e-3)

    # Cas egalite
    assert _calcul_ecart_relatif(valeur_kuma=5.0, valeur_sarah3=5.0) == pytest.approx(0.0)


def test_t4_calcul_ecart_relatif_sarah3_nul_rejete() -> None:
    """T-4 : division par zero rejete (cas theorique de robustesse)."""
    with pytest.raises(ValueError, match="valeur SARAH-3 nulle"):
        _calcul_ecart_relatif(valeur_kuma=5.0, valeur_sarah3=0.0)


def test_t5_calcul_rang_temporel_mediane_50() -> None:
    """Distribution 1..30 : la valeur 15.5 est au 50ᵉ percentile."""
    distribution = list(range(1, 31))  # 1..30, mediane = 15.5
    # Valeur exactement entre rangs 15 et 16
    percentile_15_5 = _calcul_rang_temporel(15.5, distribution)
    # rang = 15 + (0 + 1) / 2 = 15.5 -> (15.5 - 1) / 29 x 100 = 50
    assert percentile_15_5 == pytest.approx(50.0, abs=0.01)


def test_t6_calcul_rang_temporel_capping() -> None:
    """T-6 : capping 0/100 hors plage haute et basse + n<2 rejete."""
    distribution = [10.0, 20.0, 30.0]
    # Valeur tres en-dessous -> 0
    assert _calcul_rang_temporel(5.0, distribution) == pytest.approx(0.0)
    # Valeur tres au-dessus -> 100
    assert _calcul_rang_temporel(100.0, distribution) == pytest.approx(100.0)

    # n=1 rejete
    with pytest.raises(ValueError, match="Distribution insuffisante"):
        _calcul_rang_temporel(5.0, [10.0])

    # n=0 rejete
    with pytest.raises(ValueError, match="Distribution insuffisante"):
        _calcul_rang_temporel(5.0, [])


def test_t7_calcul_rang_spatial_6_villes() -> None:
    """Rangs 1 à 6 par valeur croissante."""
    valeurs = {
        56: 4.5,  # Conakry  -> rang 1 (le plus bas)
        51: 5.8,  # Kankan   -> rang 6 (le plus haut)
        52: 5.0,  # Kindia   -> rang 3
        53: 4.7,  # Labe     -> rang 2
        54: 5.2,  # Mamou    -> rang 4
        55: 5.5,  # Nzerekore-> rang 5
    }
    rangs = _calcul_rang_spatial(valeurs)
    assert rangs[56] == 1
    assert rangs[53] == 2
    assert rangs[52] == 3
    assert rangs[54] == 4
    assert rangs[55] == 5
    assert rangs[51] == 6

    # Dict vide rejete
    with pytest.raises(ValueError, match="Aucune valeur"):
        _calcul_rang_spatial({})


def test_t8_lignes_rang_spatial_mois_incomplet_non_classe() -> None:
    """Un mois sans valeur pour une localité du pool n'est classé pour aucune."""
    kuma = {
        10: {(2021, 1): 5.0, (2021, 2): 6.0},
        20: {(2021, 1): 4.0},
        30: {(2021, 1): 5.0, (2021, 2): 3.0},
    }
    lignes, non_classes = _lignes_rang_spatial(
        kuma_par_localite=kuma,
        serie_id_par_localite={10: 1, 20: 2, 30: 3},
        annee_debut=2021,
        annee_fin=2021,
        version_formule=2,
        niveau_confiance="B",
    )
    assert non_classes == [(2021, m) for m in range(2, 13)]
    rangs = {(lig["localite_id"], lig["mois"]): lig["valeur"] for lig in lignes}
    # Ex-aequo 10 et 30 : départagés par l'ordre d'entrée.
    assert rangs == {(20, 1): 1.0, (10, 1): 2.0, (30, 1): 3.0}
    assert {lig["version_formule"] for lig in lignes} == {2}
    assert {lig["series_metadonnees_id"] for lig in lignes} == {1, 2, 3}


def test_t9_rang_spatial_version_formule_desalignee() -> None:
    session = MagicMock()
    session.execute.return_value.scalar.return_value = 1
    with pytest.raises(RuntimeError, match="Desalignement version_formule"):
        calculer_et_inserer_rang_spatial(session=session, contextes=[], version_formule=2)


def test_t10_rang_spatial_localite_en_double() -> None:
    session = MagicMock()
    session.execute.return_value.scalar.return_value = 2
    ctx: ContexteRangSpatial = {
        "localite_id": 1,
        "code_serie_kuma_daily": "a",
        "series_metadonnees_id": 9,
    }
    with pytest.raises(RuntimeError, match="localite en double"):
        calculer_et_inserer_rang_spatial(
            session=session,
            contextes=[ctx, ctx],
            version_formule=2,
        )

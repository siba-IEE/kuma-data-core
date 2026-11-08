"""Tests unitaires de ``services.grandeurs.referentiels``."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest

from kuma_data_core.editorial.niveaux_confiance import NiveauxEntrees
from kuma_data_core.services.grandeurs import ecart_dni_cams, referentiels
from kuma_data_core.services.grandeurs.referentiels import (
    CibleConfiance,
    ContexteRangSpatial,
    _agreger_mensuel,
    _calcul_ecart_relatif,
    _calcul_rang_spatial,
    _calcul_rang_temporel,
    _lignes_rang_spatial,
    calculer_et_inserer_rang_spatial,
)

pytestmark = pytest.mark.unit

_CIBLE = CibleConfiance("calcul_derive", "haute")


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
        niveaux_pool=NiveauxEntrees(),
        cible_par_localite=dict.fromkeys((10, 20, 30), _CIBLE),
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


# === Propagation de la confiance (règle P, plafond B) =======================


def _lecteur(
    valeurs: dict[str, dict[tuple[int, int], float]], niveau_c: tuple[str, int, int]
) -> Callable[..., dict[tuple[int, int], float]]:
    """Faux lecteur mensuel : B partout, sauf ``(code, annee, mois)`` en C."""

    def _lire(
        _session: object, code: str, niveaux: NiveauxEntrees | None = None
    ) -> dict[tuple[int, int], float]:
        if niveaux is not None:
            for annee, mois in valeurs[code]:
                c = (code, annee, mois) == niveau_c
                niveaux.ajouter((annee, mois), "C" if c else "B")
        return valeurs[code]

    return _lire


@pytest.fixture
def lignes_inserees(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    lignes: list[dict[str, object]] = []
    for module in (referentiels, ecart_dni_cams):
        monkeypatch.setattr(module, "_lire_cible", lambda _s, _id: _CIBLE)
        monkeypatch.setattr(
            module, "_bulk_insert_grandeurs_metier", lambda _s, ls: lignes.extend(ls)
        )
    return lignes


def _niveaux(lignes: list[dict[str, object]]) -> dict[tuple[object, object], object]:
    return {(lig["annee_debut"], lig["mois"]): lig["niveau_confiance_derive"] for lig in lignes}


def test_ecart_inter_source_entree_c_donne_c(
    monkeypatch: pytest.MonkeyPatch, lignes_inserees: list[dict[str, object]]
) -> None:
    """Un mois de la référence en C met l'écart de ce mois en C, les autres restent B."""
    valeurs = {"nasa": {(2021, m): 5.0 for m in (1, 2)}, "ref": {(2021, m): 5.5 for m in (1, 2)}}
    lire = _lecteur(valeurs, ("ref", 2021, 2))
    monkeypatch.setattr(referentiels, "_lire_kuma_mensuel", lire)
    monkeypatch.setattr(referentiels, "_lire_mensuel", lire)
    referentiels.calculer_et_inserer_ecart_inter_source(
        session=MagicMock(),
        contextes=[
            {
                "localite_id": 1,
                "code_serie_nasa_daily": "nasa",
                "code_serie_reference": "ref",
                "series_metadonnees_id": 9,
            }
        ],
        grandeur_code="ecart_relatif_referentiel",
        annee_debut=2021,
        annee_fin=2021,
    )
    assert _niveaux(lignes_inserees) == {(2021, 1): "B", (2021, 2): "C"}


def test_rang_temporel_climato_c_donne_c(
    monkeypatch: pytest.MonkeyPatch, lignes_inserees: list[dict[str, object]]
) -> None:
    """Une année de climatologie de mars en C met en C le rang de chaque mois de mars."""
    climato = {(a, m): float(a) for a in range(1991, 2021) for m in (3, 4)}
    valeurs = {"kuma": {(2021, 3): 2000.0, (2021, 4): 2000.0}, "clim": climato}
    lire = _lecteur(valeurs, ("clim", 1995, 3))
    monkeypatch.setattr(referentiels, "_lire_kuma_mensuel", lire)
    monkeypatch.setattr(referentiels, "_lire_mensuel", lire)
    referentiels.calculer_et_inserer_rang_temporel(
        session=MagicMock(),
        contextes=[
            {
                "localite_id": 1,
                "code_serie_kuma_daily": "kuma",
                "code_serie_power_1991_2020": "clim",
                "series_metadonnees_id": 9,
            }
        ],
        annee_debut=2021,
        annee_fin=2021,
    )
    assert _niveaux(lignes_inserees) == {(2021, 3): "C", (2021, 4): "B"}


def test_rang_spatial_entree_c_met_le_mois_du_pool_en_c() -> None:
    """Le rang dépend de tout le pool : une localité en C met ce mois en C pour toutes."""
    niveaux_pool = NiveauxEntrees()
    for loc in (10, 20):
        for mois in (1, 2):
            niveaux_pool.ajouter((2021, mois), "C" if (loc, mois) == (20, 1) else "B")
    lignes, _ = _lignes_rang_spatial(
        kuma_par_localite={
            10: {(2021, 1): 5.0, (2021, 2): 6.0},
            20: {(2021, 1): 4.0, (2021, 2): 3.0},
        },
        serie_id_par_localite={10: 1, 20: 2},
        annee_debut=2021,
        annee_fin=2021,
        version_formule=2,
        niveaux_pool=niveaux_pool,
        cible_par_localite={10: _CIBLE, 20: _CIBLE},
    )
    niveaux = {(lig["localite_id"], lig["mois"]): lig["niveau_confiance_derive"] for lig in lignes}
    assert niveaux == {(10, 1): "C", (20, 1): "C", (10, 2): "B", (20, 2): "B"}


def test_ecart_dni_cams_entree_c_donne_c(
    monkeypatch: pytest.MonkeyPatch, lignes_inserees: list[dict[str, object]]
) -> None:
    valeurs = {"nasa": {(2010, m): 5.0 for m in (1, 2)}, "cams": {(2010, m): 6.0 for m in (1, 2)}}
    monkeypatch.setattr(ecart_dni_cams, "_lire_mensuel", _lecteur(valeurs, ("nasa", 2010, 1)))
    ecart_dni_cams.calculer_et_inserer_ecart_dni_cams(
        session=MagicMock(),
        contextes_villes=[
            {
                "localite_id": 1,
                "code_serie_nasa": "nasa",
                "code_serie_cams": "cams",
                "series_metadonnees_id": 9,
            }
        ],
    )
    assert _niveaux(lignes_inserees) == {(2010, 1): "C", (2010, 2): "B"}


def test_plafond_b_meme_avec_entrees_a() -> None:
    """Des entrées A (mesures au sol) ne donnent jamais A à un écart ou un rang."""
    assert referentiels._niveau_derive(_CIBLE, {"A"}) == "B"

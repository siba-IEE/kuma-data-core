"""Résolution d'un point : sa cellule, sinon une cellule voisine, sinon rien.

Grille de 1° x 1°, frontières aux degrés entiers. Les candidates sont
synthétiques ; le point de référence (10,5 ; 5,5) est au centre de la cellule
dont le coin sud-ouest est (10 ; 5).
"""

from __future__ import annotations

from typing import NamedTuple

import pytest

from kuma_data_core.services.resolution import (
    cellule,
    distance_grand_cercle_km,
    plus_proche,
    resoudre,
)

pytestmark = pytest.mark.unit

# Un degré d'arc de grand cercle : π x 6371 / 180.
_KM_PAR_DEGRE = 111.19493


class _Point(NamedTuple):
    nom: str
    latitude: float
    longitude: float


def test_une_candidate_de_la_cellule_l_emporte_sur_une_plus_proche_d_une_autre_cellule() -> None:
    lointaine_de_la_cellule = _Point("cellule", 10.9, 5.1)
    proche_d_une_autre_cellule = _Point("autre", 9.95, 5.99)
    candidates = [proche_d_une_autre_cellule, lointaine_de_la_cellule]

    assert plus_proche(10.05, 5.95, candidates)[0] is proche_d_une_autre_cellule
    resolution = resoudre(10.05, 5.95, candidates)

    assert resolution is not None
    assert resolution.candidate is lointaine_de_la_cellule
    assert resolution.meme_cellule is True
    assert resolution.distance_km == pytest.approx(distance_grand_cercle_km(10.05, 5.95, 10.9, 5.1))


@pytest.mark.parametrize(
    ("ecart_latitude", "ecart_longitude"),
    [
        pytest.param(1, 0, id="côté nord"),
        pytest.param(-1, 0, id="côté sud"),
        pytest.param(0, 1, id="côté est"),
        pytest.param(0, -1, id="côté ouest"),
        pytest.param(1, 1, id="coin nord-est"),
        pytest.param(1, -1, id="coin nord-ouest"),
        pytest.param(-1, 1, id="coin sud-est"),
        pytest.param(-1, -1, id="coin sud-ouest"),
    ],
)
def test_sans_candidate_dans_la_cellule_celle_d_une_cellule_voisine_est_retenue(
    ecart_latitude: int, ecart_longitude: int
) -> None:
    voisine = _Point("voisine", 10.5 + ecart_latitude, 5.5 + ecart_longitude)

    resolution = resoudre(10.5, 5.5, [voisine])

    assert resolution is not None
    assert resolution.candidate is voisine
    assert resolution.meme_cellule is False


def test_une_voisine_l_emporte_sur_une_plus_proche_situee_a_deux_cellules() -> None:
    proche_a_deux_cellules = _Point("deux cellules au sud", 8.99, 5.5)
    lointaine_voisine = _Point("coin nord-est", 11.9, 6.9)
    candidates = [proche_a_deux_cellules, lointaine_voisine]

    assert plus_proche(10.01, 5.5, candidates)[0] is proche_a_deux_cellules
    resolution = resoudre(10.01, 5.5, candidates)

    assert resolution is not None
    assert resolution.candidate is lointaine_voisine
    assert resolution.meme_cellule is False


def test_toutes_les_candidates_a_deux_cellules_ou_plus_point_non_resolu() -> None:
    a_deux_cellules = _Point("deux cellules au nord", 12.1, 5.5)
    a_trois_cellules = _Point("trois cellules à l'ouest", 10.5, 2.9)
    candidates = [a_trois_cellules, a_deux_cellules]

    assert resoudre(10.5, 5.5, candidates) is None
    # La plus proche reste nommable, pour dire à l'appelant où commence la zone couverte.
    la_plus_proche, distance_km = plus_proche(10.5, 5.5, candidates)
    assert la_plus_proche is a_deux_cellules
    assert distance_km == pytest.approx(1.6 * _KM_PAR_DEGRE, abs=1e-3)


def test_sans_candidate_point_non_resolu() -> None:
    assert resoudre(10.5, 5.5, list[_Point]()) is None
    with pytest.raises(ValueError):
        plus_proche(10.5, 5.5, list[_Point]())


def test_la_cellule_d_une_coordonnee_negative_est_sa_partie_entiere_inferieure() -> None:
    assert cellule(-9.3, -13.7) == (-10, -14)
    # De part et d'autre de l'équateur : deux cellules, qu'une troncature confondrait.
    resolution = resoudre(-0.3, 0.5, [_Point("au nord de l'équateur", 0.3, 0.5)])
    assert resolution is not None
    assert resolution.meme_cellule is False


def test_un_point_sur_une_frontiere_appartient_a_la_cellule_qui_y_commence() -> None:
    assert cellule(10.0, 5.0) == (10, 5)
    de_la_cellule = _Point("coin opposé de la cellule", 10.9, 5.9)
    juste_de_l_autre_cote = _Point("cellule du coin sud-ouest", 9.99, 4.99)

    resolution = resoudre(10.0, 5.0, [juste_de_l_autre_cote, de_la_cellule])

    assert resolution is not None
    assert resolution.candidate is de_la_cellule
    assert resolution.meme_cellule is True


def test_longitude_circulaire_les_cellules_de_part_et_d_autre_de_180_sont_voisines() -> None:
    a_l_ouest_de_la_ligne = _Point("179,9° O", 0.0, -179.9)

    resolution = resoudre(0.0, 179.9, [a_l_ouest_de_la_ligne])

    assert resolution is not None
    assert resolution.candidate is a_l_ouest_de_la_ligne
    assert resolution.meme_cellule is False
    # 0,2° d'équateur, et non 359,8°.
    assert resolution.distance_km == pytest.approx(0.2 * _KM_PAR_DEGRE, abs=1e-3)
    # La circularité n'étend pas le voisinage : à deux cellules, toujours rien.
    assert resoudre(0.0, 179.9, [_Point("178,5° O", 0.0, -178.5)]) is None


def test_longitude_circulaire_180_et_moins_180_sont_la_meme_cellule() -> None:
    resolution = resoudre(0.2, 180.0, [_Point("179,5° O", 0.8, -179.5)])

    assert resolution is not None
    assert resolution.meme_cellule is True


def test_la_latitude_ne_boucle_pas_d_un_pole_a_l_autre() -> None:
    assert resoudre(89.5, 5.5, [_Point("près du pôle Sud", -89.5, 5.5)]) is None


def test_a_distance_egale_la_premiere_de_la_liste_est_retenue() -> None:
    au_nord = _Point("nord", 10.75, 5.5)
    au_sud = _Point("sud", 10.25, 5.5)
    assert distance_grand_cercle_km(10.5, 5.5, 10.75, 5.5) == distance_grand_cercle_km(
        10.5, 5.5, 10.25, 5.5
    )

    for premiere, seconde in ((au_nord, au_sud), (au_sud, au_nord)):
        resolution = resoudre(10.5, 5.5, [premiere, seconde])
        assert resolution is not None
        assert resolution.candidate is premiere
        assert plus_proche(10.5, 5.5, [premiere, seconde])[0] is premiere


def test_distance_d_un_degre_de_latitude_et_d_un_quart_de_grand_cercle() -> None:
    """Deux valeurs calculées à la main, pour un rayon terrestre de 6371 km."""
    # π x 6371 / 180 = 111,19493 km.
    assert distance_grand_cercle_km(10.0, 5.0, 11.0, 5.0) == pytest.approx(111.19493, abs=1e-4)
    # De (0 ; 0) à (60 ; 90), le cosinus de l'arc est sin 0 sin 60 + cos 0 cos 60 cos 90 = 0 :
    # un quart de grand cercle, π x 6371 / 2 = 10 007,543 km.
    assert distance_grand_cercle_km(0.0, 0.0, 60.0, 90.0) == pytest.approx(10007.543, abs=1e-3)

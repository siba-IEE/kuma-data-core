"""Champ ``limite`` de ``/v1/grandeurs/ghi_exceedance`` : les localités jumelles y sont nommées."""

from __future__ import annotations

import pytest

from kuma_data_core.api.v1.grandeurs.exceedance import _construire_limite_ghi_exceedance

pytestmark = pytest.mark.unit

_BASE = (
    "Exceedance inter-annuelle uniquement (variabilité d'une année à l'autre sur 30 ans). "
    "Ne propage pas l'incertitude du modèle satellitaire NASA POWER : ce n'est pas un P90 "
    "bancable complet (qui nécessiterait un modèle d'erreur explicite, de type PRUVE, et "
    "idéalement un calage sur des mesures au sol)."
)
_CELLULE_PARTAGEE = (
    " tombent dans la même cellule de la grille CERES SYN1deg de NASA POWER (environ 110 km "
    "de côté) : leurs séries GHI mensuelles 1991-2020 sont strictement identiques, et leurs "
    "P50 et P90 aussi."
)


def test_sans_jumelle_le_texte_de_base_seul() -> None:
    assert _construire_limite_ghi_exceedance([]) == _BASE


@pytest.mark.parametrize(
    ("jumelles", "enumeration"),
    [
        (["zzf_b"], " Cette localité et 'zzf_b'"),
        (["zzf_b", "zzf_c"], " Cette localité, 'zzf_b' et 'zzf_c'"),
        (["zzf_b", "zzf_c", "zzf_d"], " Cette localité, 'zzf_b', 'zzf_c' et 'zzf_d'"),
    ],
)
def test_jumelles_nommees_dans_l_ordre_recu(jumelles: list[str], enumeration: str) -> None:
    attendu = _BASE + enumeration + _CELLULE_PARTAGEE
    assert _construire_limite_ghi_exceedance(jumelles) == attendu

"""Commentaire editorial de ``degenerescence_pixel`` : texte courant et texte historique.

- Le texte courant (``calculer_et_inserer_degenerescence_pixel``, chemin de tout
  nouveau calcul) ne porte aucun motif de ``JARGON_INTERNE``.
- Le texte historique (``calculer_et_inserer_degenerescence``, importe par la
  migration 090 immuable) est identique, a l'octet pres, a celui que la
  migration 090 ecrivait : une base neuve passe par l'etat que la migration 128
  attend (empreinte md5 de ses 140 commentaires).
- Les deux ne different que par la mention historique retiree par la 128.
"""

from __future__ import annotations

import pytest

from kuma_data_core.services.grandeurs import degenerescence_pixel as dp
from tests._jargon import JARGON_INTERNE

pytestmark = pytest.mark.unit

_JUMEAUX = ["gin_kindia", "gin_mamou"]


def _texte_migration_090(cfg: dp._ConfigSource, grandeur: str, codes_jumeaux: list[str]) -> str:
    """Copie litterale du gabarit de ``_commentaire`` tel que la migration 090 l'a execute."""
    if not cfg["grille_fixe"]:
        base = (
            f"Source interpolee au point ({cfg['grille']}, {cfg['resolution']}) : valeurs "
            f"distinctes par construction. Resolution reelle {cfg['resolution']} -> finesse "
            f"sub-maille illusoire (caveat de resolution, pas une degenerescence mesurable)."
        )
    elif codes_jumeaux:
        liste = ", ".join(codes_jumeaux)
        base = (
            f"Degenerescence de pixel : partage la cellule {cfg['grille']} ({cfg['resolution']}) "
            f"avec {len(codes_jumeaux)} autre(s) point(s) ({liste}). Series {grandeur} identiques "
            f"(meme pixel source) -> ne pas presenter comme des mesures independantes "
            f"(D-29 generalise)."
        )
    else:
        base = (
            f"Point resolu sur {cfg['grille']} ({cfg['resolution']}) : aucun autre point "
            f"partageant la cellule pour {grandeur}."
        )
    return base + dp._CAVEAT_CONFIANCE


_CAS = [(cfg, jumeaux) for cfg in dp._CONFIG for jumeaux in (_JUMEAUX, [])]


@pytest.mark.parametrize(("cfg", "jumeaux"), _CAS)
def test_texte_historique_identique_a_la_migration_090(
    cfg: dp._ConfigSource, jumeaux: list[str]
) -> None:
    historique = dp._commentaire(cfg, cfg["grandeur_code"], jumeaux, texte_historique_090=True)
    assert historique == _texte_migration_090(cfg, cfg["grandeur_code"], jumeaux)


@pytest.mark.parametrize(("cfg", "jumeaux"), _CAS)
def test_texte_courant_sans_jargon(cfg: dp._ConfigSource, jumeaux: list[str]) -> None:
    courant = dp._commentaire(cfg, cfg["grandeur_code"], jumeaux)
    assert JARGON_INTERNE.search(courant) is None
    historique = dp._commentaire(cfg, cfg["grandeur_code"], jumeaux, texte_historique_090=True)
    # Transformation exacte de la migration 128 (fragment DEGENERESCENCE).
    assert courant == historique.replace(
        "mesures independantes (D-29 generalise).", "mesures independantes."
    )


def test_orchestrateurs_distincts() -> None:
    """Le nom importe par la migration 090 reste disponible ; le chemin courant est distinct."""
    assert callable(dp.calculer_et_inserer_degenerescence)
    assert callable(dp.calculer_et_inserer_degenerescence_pixel)
    assert dp.calculer_et_inserer_degenerescence is not dp.calculer_et_inserer_degenerescence_pixel

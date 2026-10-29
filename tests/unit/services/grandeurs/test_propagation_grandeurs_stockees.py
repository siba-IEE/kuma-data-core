"""Tests unitaires de la règle de propagation P dans les grandeurs stockées (ADR-0008).

Session SQLAlchemy simulée (``MagicMock`` + ``side_effect``) : chaque ligne
insérée dans ``grandeurs_metier`` doit porter le niveau des seules entrées de sa
période, sans dépasser le plafond de la grandeur.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from kuma_data_core.services.grandeurs.fraction_diffuse import calculer_et_inserer_fraction_diffuse
from kuma_data_core.services.grandeurs.hep import calculer_et_inserer_hep
from kuma_data_core.services.grandeurs.humidex import calculer_et_inserer_humidex
from kuma_data_core.services.grandeurs.indicateur_qualite_donnees import (
    calculer_et_inserer_indicateur_qualite_donnees,
)
from kuma_data_core.services.grandeurs.productible_specifique_theorique import (
    calculer_et_inserer_productible_specifique_theorique,
)
from kuma_data_core.services.grandeurs.variabilite_journaliere import (
    calculer_et_inserer_variabilite_journaliere,
)

pytestmark = pytest.mark.unit

_JOUR_C = date(2025, 3, 10)
_JOURS_2025 = [date(2025, 1, 1) + timedelta(days=i) for i in range(365)]


def _resultat(**attributs: Any) -> MagicMock:
    return MagicMock(**attributs)


def _serie(grandeur: str, methode: str = "calcul_derive") -> MagicMock:
    return MagicMock(
        serie_id=42,
        localite_id=1,
        grandeur_code=grandeur,
        methode_collecte=methode,
        fiabilite_source="haute",
    )


def _mesures(valeur: float, jour_c: date | None = None) -> list[MagicMock]:
    return [
        MagicMock(instant_mesure=j, valeur=valeur, niveau="C" if j == jour_c else "A")
        for j in _JOURS_2025
    ]


def _niveaux_inseres(session: MagicMock) -> dict[tuple[str, int | None], str]:
    params = session.execute.call_args_list[-1].args[1]
    return {(p["periode_type"], p["mois"]): p["niveau_confiance_derive"] for p in params}


def test_hep_chaque_ligne_au_niveau_de_sa_periode() -> None:
    """HEP (calcul exact, plafond A) : une journée C fait passer son mois et son année en C."""
    session = MagicMock()
    session.execute.side_effect = [
        _resultat(scalar=MagicMock(return_value=1)),
        _resultat(first=MagicMock(return_value=_serie("hep"))),
        _resultat(first=MagicMock(return_value=_serie("ghi", "modele_satellitaire"))),
        _resultat(all=MagicMock(return_value=_mesures(5.0, _JOUR_C))),
        MagicMock(),
    ]

    calculer_et_inserer_hep(
        session=session, code_serie_hep="gin_test_hep", code_serie_ghi_amont="gin_test_ghi"
    )

    niveaux = _niveaux_inseres(session)
    assert niveaux[("annuel", None)] == "C"
    assert niveaux[("mensuel", 3)] == "C"
    assert {n for (_, mois), n in niveaux.items() if mois not in (None, 3)} == {"A"}


def test_humidex_prend_le_niveau_de_ses_deux_entrees() -> None:
    """Humidex : une journée C sur RH2M suffit à faire passer son mois en C."""
    session = MagicMock()
    session.execute.side_effect = [
        _resultat(scalar=MagicMock(return_value=1)),
        _resultat(first=MagicMock(return_value=_serie("humidex"))),
        _resultat(first=MagicMock(return_value=_serie("t2m", "reanalyse"))),
        _resultat(first=MagicMock(return_value=_serie("rh2m", "reanalyse"))),
        _resultat(all=MagicMock(return_value=_mesures(30.0))),
        _resultat(all=MagicMock(return_value=_mesures(70.0, _JOUR_C))),
        MagicMock(),
    ]

    calculer_et_inserer_humidex(
        session=session,
        code_serie_humidex="gin_test_humidex",
        code_serie_t2m_amont="gin_test_t2m",
        code_serie_rh2m_amont="gin_test_rh2m",
    )

    niveaux = _niveaux_inseres(session)
    assert niveaux[("mensuel", 3)] == "C"
    assert niveaux[("mensuel", 4)] == "A"


def test_productible_theorique_plafonne_a_b() -> None:
    """PR théorique conventionnel (plafond B) : une ligne HEP A donne B, une ligne C donne C."""
    lignes_hep = [
        MagicMock(
            periode_type="mensuel",
            annee_debut=2025,
            annee_fin=2025,
            mois=1,
            valeur=180.0,
            niveau="A",
        ),
        MagicMock(
            periode_type="mensuel",
            annee_debut=2025,
            annee_fin=2025,
            mois=2,
            valeur=170.0,
            niveau="C",
        ),
    ]
    session = MagicMock()
    session.execute.side_effect = [
        _resultat(scalar=MagicMock(return_value=1)),
        _resultat(first=MagicMock(return_value=_serie("productible_specifique_theorique"))),
        _resultat(first=MagicMock(return_value=_serie("hep"))),
        _resultat(all=MagicMock(return_value=lignes_hep)),
        MagicMock(),
    ]

    calculer_et_inserer_productible_specifique_theorique(
        session=session,
        code_serie_productible="gin_test_psp",
        code_serie_hep_amont="gin_test_hep",
    )

    assert _niveaux_inseres(session) == {("mensuel", 1): "B", ("mensuel", 2): "C"}


@pytest.mark.parametrize(("jour_c", "attendu"), [(None, "B"), (_JOUR_C, "C")])
def test_indicateur_qualite_au_plus_b(jour_c: date | None, attendu: str) -> None:
    """Méta-indicateur (plafond B) : B sur des mesures A, C dès qu'une mesure évaluée est C."""
    mesures = [
        MagicMock(niveau_confiance_derive="A", niveau="C" if j == jour_c else "A")
        for j in _JOURS_2025
    ]
    session = MagicMock()
    session.execute.side_effect = [
        _resultat(scalar=MagicMock(return_value=1)),
        _resultat(first=MagicMock(return_value=_serie("ghi", "mesure_directe"))),
        _resultat(all=MagicMock(return_value=mesures)),
        MagicMock(),
    ]

    calculer_et_inserer_indicateur_qualite_donnees(
        session=session, code_serie_evaluee="gin_test_ghi", annee_debut=2025, annee_fin=2025
    )

    assert session.execute.call_args_list[-1].args[1]["niveau"] == attendu


def test_fraction_diffuse_prend_le_niveau_de_ses_deux_entrees() -> None:
    """Fraction diffuse (ratio exact, plafond A) : un jour C sur le GHI met son mois en C."""
    session = MagicMock()
    session.execute.side_effect = [
        _resultat(scalar=MagicMock(return_value=1)),
        _resultat(first=MagicMock(return_value=_serie("fraction_diffuse"))),
        _resultat(first=MagicMock(return_value=_serie("dhi", "modele_satellitaire"))),
        _resultat(first=MagicMock(return_value=_serie("ghi", "modele_satellitaire"))),
        _resultat(all=MagicMock(return_value=_mesures(2.0))),
        _resultat(all=MagicMock(return_value=_mesures(5.0, _JOUR_C))),
        MagicMock(),
    ]

    calculer_et_inserer_fraction_diffuse(
        session=session,
        code_serie_fraction_diffuse="gin_test_fd",
        code_serie_dhi_amont="gin_test_dhi",
        code_serie_ghi_amont="gin_test_ghi",
    )

    niveaux = _niveaux_inseres(session)
    assert niveaux[("mensuel", 3)] == "C"
    assert niveaux[("mensuel", 1)] == "A"
    assert niveaux[("annuel", None)] == "C"


def test_variabilite_annee_au_niveau_de_ses_jours() -> None:
    """Variabilité journalière (statistique exacte, plafond A) : A, puis C avec une journée C."""
    for jour_c, attendu in ((None, "A"), (_JOUR_C, "C")):
        session = MagicMock()
        session.execute.side_effect = [
            _resultat(scalar=MagicMock(return_value=1)),
            _resultat(first=MagicMock(return_value=_serie("variabilite_journaliere"))),
            _resultat(first=MagicMock(return_value=_serie("ghi", "modele_satellitaire"))),
            _resultat(
                all=MagicMock(
                    return_value=[
                        MagicMock(
                            instant_mesure=j,
                            valeur=4.0 + (i % 7) / 10,
                            niveau="C" if j == jour_c else "A",
                        )
                        for i, j in enumerate(_JOURS_2025)
                    ]
                )
            ),
            MagicMock(),
        ]

        calculer_et_inserer_variabilite_journaliere(
            session=session,
            code_serie_variabilite="gin_test_variabilite",
            code_serie_ghi_amont="gin_test_ghi",
        )

        assert _niveaux_inseres(session) == {("annuel", None): attendu}

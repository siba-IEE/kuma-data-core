"""Assemblage de la ressource et aller-retour du fichier Kuma, sur les valeurs."""

from __future__ import annotations

from typing import Any

import pytest

from kuma_data_core.services.capsule.assembleur import assembler_ressource
from kuma_data_core.services.capsule.client_calage import (
    CalageIndisponibleError,
    referentiel_calage,
)
from kuma_data_core.services.capsule.fichier_kuma import (
    COLONNES_DONNEES,
    REPERE_DONNEES,
    FichierKumaInvalideError,
    lire,
    serialiser,
)

pytestmark = pytest.mark.unit

_CALAGE = {
    "saisons": [
        {"nom": "seche", "mois": [11, 12, 1, 2, 3, 4], "biais": 0.25},
        {"nom": "pluies", "mois": [5, 6, 7, 8, 9, 10], "biais": -0.20},
    ]
}


def _sequence() -> dict[str, Any]:
    return {
        "mois": [m for m in range(1, 13) for _ in range(2)],
        "heures": [h for _ in range(12) for h in (11, 12)],
        "ghi": [g for m in range(1, 13) for g in (400.0, 612.25 + m)],
    }


def _contenu(**options: Any) -> dict[str, Any]:
    return assembler_ressource(
        metadonnees={"point": {"lat": 9.5, "lon": -13.7}, "edition": "e1"},
        periode={"debut": "2021-01-01", "fin": "2023-12-31"},
        sequence_type=_sequence(),
        climatologie_hep=[5.0] * 12,
        domaine_validite={"debut": "2021-01-01", "fin": "2023-12-31"},
        **options,
    )


def test_capsule_brute_sans_calage_ni_temperatures() -> None:
    ressource = _contenu()["ressource"]
    assert ressource["calage"] is None
    assert "temperaturesConception" not in ressource
    assert ressource["hepAnnuelleReconstituee"] == pytest.approx(5.0)
    assert ressource["enregistrementContraignant"] == ressource["enregistrementType"]


def test_capsule_calibree_porte_le_calage_et_la_hep_calee() -> None:
    ressource = _contenu(calage=_CALAGE)["ressource"]
    assert ressource["calage"] == _CALAGE
    assert ressource["hepAnnuelleReconstituee"] != pytest.approx(5.0)
    assert ressource["climatologieHep"] == [5.0] * 12


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"calage": _CALAGE},
        {
            "calage": _CALAGE,
            "corrections": {"thermique": {"gamma": -0.004}},
            "temperatures_conception": {"froidC": 14.2, "chaudC": 41.0, "fenetre": "2001-2023"},
        },
    ],
)
def test_aller_retour_conserve_les_valeurs(options: dict[str, Any]) -> None:
    contenu = _contenu(**options)
    relu = lire(serialiser(contenu))
    assert relu["metadonnees"] == contenu["metadonnees"]
    assert relu["corrections"] == contenu["corrections"]
    for cle, valeur in contenu["ressource"].items():
        assert relu["ressource"][cle] == valeur


def test_entier_ecrit_sans_decimale_et_flottant_au_plus_court() -> None:
    lignes = serialiser(_contenu()).split("\n")
    debut = lignes.index(COLONNES_DONNEES) + 1
    assert lignes[debut] == "type,1,11,400"
    assert lignes[debut + 1] == "type,1,12,613.25"


@pytest.mark.parametrize(
    ("alteration", "message"),
    [
        (lambda t: t.replace(REPERE_DONNEES, "==="), "repère de données absent"),
        (lambda t: "{" + t, "en-tête non JSON"),
        (lambda t: t.replace("kuma-ressource-1", "kuma-ressource-0"), "version de format"),
        (lambda t: t.replace(COLONNES_DONNEES, "a,b"), "colonnes du bloc"),
        (lambda t: t + "\ntype,1,12", "3 colonnes"),
        (lambda t: t + "\nautre,1,12,5", "enregistrement inconnu"),
        (lambda t: t + "\ntype,1,12,abc", "nombre invalide"),
        (lambda t: t + "\ntype,1,12,", "nombre vide"),
    ],
)
def test_fichier_altere_refuse(alteration: Any, message: str) -> None:
    with pytest.raises(FichierKumaInvalideError, match=message):
        lire(alteration(serialiser(_contenu())))


def test_referentiel_de_calage_ne_garde_que_les_saisons() -> None:
    reponse = {"ghi": {"saisons": _CALAGE["saisons"], "residus": [0.1]}, "verdict": "couvert"}
    assert referentiel_calage(reponse) == _CALAGE


@pytest.mark.parametrize("reponse", [{}, {"ghi": None}, {"ghi": {"residus": []}}])
def test_reponse_de_calage_sans_saisons_refusee(reponse: dict[str, Any]) -> None:
    with pytest.raises(CalageIndisponibleError):
        referentiel_calage(reponse)

"""Le contrat de la fiche de contribution (``pv-autonome@1``, ADR-0006).

Ce qui quitte le poste est borné par ce schéma : un champ de plus est
refusé, le point est arrondi, le nom d'un appareil est coupé.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import ValidationError

from kuma_data_core.api.v1.schemas.contributions import (
    LONGUEUR_NOM_APPAREIL,
    DemandeContribution,
)

pytestmark = pytest.mark.unit


def fiche_exemple() -> dict[str, Any]:
    """Une fiche complète et valide d'étude PV autonome."""
    return {
        "module": "pv-autonome",
        "format": "pv-autonome@1",
        "fiche": {
            "logiciel": {"version": "1.1.0", "enregistre_le": "2026-10-02"},
            "lieu": {"sous_prefecture": "GN00400113"},
            "panneaux": {"inclinaison_deg": 12, "orientation_deg": 0, "module_wc": 450},
            "ressource": {"mode": "brut", "version_base": "calage-guinee-v3"},
            "appareils": [
                {
                    "nom": "Réfrigérateur",
                    "puissance_w": 120,
                    "heures_par_jour": 10,
                    "quantite": 1,
                    "moment": "jour_nuit",
                },
                {
                    "nom": "Ampoule",
                    "puissance_w": 9,
                    "heures_par_jour": 5,
                    "quantite": 6,
                    "moment": "soir",
                },
            ],
            "systeme": {"jours_autonomie": 2, "batterie": "lithium"},
            "prix": {
                "monnaie": "GNF",
                "kwc_installe": 9_500_000,
                "kwh_batterie": 4_200_000,
                "onduleur_par_kw": 1_800_000,
                "kwh_evite": 3_500,
            },
            "resultats": {
                "puissance_champ_kwc": 1.35,
                "nombre_modules": 3,
                "capacite_batterie_kwh": 5.1,
                "puissance_onduleur_kw": 1.0,
                "productible_annuel_kwh": 2010.0,
                "taux_autonomie": 0.97,
                "mois_defavorable": 8,
                "cout_installation": 35_000_000,
                "economies_annuelles": 6_200_000,
                "temps_retour_ans": 5.6,
                "energie_non_servie": 0.02,
            },
        },
    }


def test_fiche_complete_acceptee() -> None:
    demande = DemandeContribution.model_validate(fiche_exemple())
    assert demande.fiche.lieu is not None
    assert demande.fiche.lieu.sous_prefecture == "GN00400113"
    assert len(demande.fiche.appareils) == 2


def test_fiche_minimale_acceptee() -> None:
    """Une étude non calculée, sans lieu ni ressource, part quand même."""
    brut = fiche_exemple()
    for cle in ("lieu", "ressource", "resultats"):
        del brut["fiche"][cle]
    DemandeContribution.model_validate(brut)


@pytest.mark.parametrize(
    ("chemin", "cle", "valeur"),
    [
        ((), "nom_etude", "Habitation Camara"),
        (("logiciel",), "chemin_fichier", "C:/Users/x/etude.json"),
        (("lieu",), "nom_localite", "Tokounou"),
        (("panneaux",), "marque", "X"),
    ],
)
def test_champ_hors_contrat_refuse(chemin: tuple[str, ...], cle: str, valeur: str) -> None:
    brut = fiche_exemple()
    cible = brut["fiche"]
    for etape in chemin:
        cible = cible[etape]
    cible[cle] = valeur
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DemandeContribution.model_validate(brut)


def test_point_arrondi_a_un_dixieme() -> None:
    brut = fiche_exemple()
    brut["fiche"]["lieu"] = {"point": {"latitude_deg": 9.53712, "longitude_deg": -13.68264}}
    point = DemandeContribution.model_validate(brut).fiche.lieu.point  # type: ignore[union-attr]
    assert point is not None
    assert (point.latitude_deg, point.longitude_deg) == (9.5, -13.7)


@pytest.mark.parametrize(
    "lieu",
    [
        {},
        {"sous_prefecture": "GN00400113", "point": {"latitude_deg": 9.5, "longitude_deg": -13.7}},
    ],
)
def test_lieu_est_l_un_ou_l_autre(lieu: dict[str, Any]) -> None:
    brut = fiche_exemple()
    brut["fiche"]["lieu"] = lieu
    with pytest.raises(ValidationError, match="l'un des deux"):
        DemandeContribution.model_validate(brut)


def test_code_de_sous_prefecture_controle() -> None:
    brut = fiche_exemple()
    brut["fiche"]["lieu"] = {"sous_prefecture": "Bowe"}
    with pytest.raises(ValidationError):
        DemandeContribution.model_validate(brut)


def test_nom_d_appareil_coupe() -> None:
    brut = fiche_exemple()
    brut["fiche"]["appareils"][0]["nom"] = "  " + "Congélateur coffre " * 6
    nom = DemandeContribution.model_validate(brut).fiche.appareils[0].nom
    assert len(nom) <= LONGUEUR_NOM_APPAREIL
    assert nom.startswith("Congélateur coffre")


@pytest.mark.parametrize(
    ("partie", "cle", "valeur"),
    [
        ("resultats", "taux_autonomie", 97),
        ("resultats", "mois_defavorable", 0),
        ("systeme", "batterie", "nickel"),
        ("prix", "monnaie", "GBP"),
    ],
)
def test_valeurs_hors_bornes_refusees(partie: str, cle: str, valeur: object) -> None:
    brut = copy.deepcopy(fiche_exemple())
    brut["fiche"][partie][cle] = valeur
    with pytest.raises(ValidationError):
        DemandeContribution.model_validate(brut)


def test_module_inconnu_refuse() -> None:
    brut = fiche_exemple()
    brut["module"] = "mini-reseau"
    with pytest.raises(ValidationError):
        DemandeContribution.model_validate(brut)

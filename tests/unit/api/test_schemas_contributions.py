"""Le contrat des fiches de contribution (``pv-autonome@1``, ``minireseau@1``, ADR-0006).

Ce qui quitte le poste est borné par ce schéma : un champ de plus est
refusé, le point est arrondi, le nom d'un appareil est coupé.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from kuma_data_core.api.v1.schemas.contributions import (
    LONGUEUR_NOM_APPAREIL,
    DemandeContribution,
    DemandeMiniReseau,
    DemandePvAutonome,
    TypeDemande,
)

_ADAPTATEUR: TypeAdapter[TypeDemande] = TypeAdapter(DemandeContribution)


def valider(brut: dict[str, Any]) -> TypeDemande:
    return _ADAPTATEUR.validate_python(brut)


def valider_pv(brut: dict[str, Any]) -> DemandePvAutonome:
    demande = valider(brut)
    assert isinstance(demande, DemandePvAutonome)
    return demande


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
    demande = valider_pv(fiche_exemple())
    assert demande.fiche.lieu is not None
    assert demande.fiche.lieu.sous_prefecture == "GN00400113"
    assert len(demande.fiche.appareils) == 2


def test_fiche_minimale_acceptee() -> None:
    """Une étude non calculée, sans lieu ni ressource, part quand même."""
    brut = fiche_exemple()
    for cle in ("lieu", "ressource", "resultats"):
        del brut["fiche"][cle]
    valider_pv(brut)


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
        valider_pv(brut)


def test_point_arrondi_a_un_dixieme() -> None:
    brut = fiche_exemple()
    brut["fiche"]["lieu"] = {"point": {"latitude_deg": 9.53712, "longitude_deg": -13.68264}}
    point = valider_pv(brut).fiche.lieu.point  # type: ignore[union-attr]
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
        valider_pv(brut)


def test_code_de_sous_prefecture_controle() -> None:
    brut = fiche_exemple()
    brut["fiche"]["lieu"] = {"sous_prefecture": "Bowe"}
    with pytest.raises(ValidationError):
        valider_pv(brut)


def test_nom_d_appareil_coupe() -> None:
    brut = fiche_exemple()
    brut["fiche"]["appareils"][0]["nom"] = "  " + "Congélateur coffre " * 6
    nom = valider_pv(brut).fiche.appareils[0].nom
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
        valider_pv(brut)


def test_module_inconnu_refuse() -> None:
    brut = fiche_exemple()
    brut["module"] = "mini-reseau"
    with pytest.raises(ValidationError):
        valider_pv(brut)


# === Mini-réseau, ``minireseau@1`` ===


def fiche_minireseau_exemple() -> dict[str, Any]:
    """Une fiche complète et valide d'étude mini-réseau."""
    profil = [0.02] * 6 + [0.05] * 12 + [0.06] * 4 + [0.02] * 2
    return {
        "module": "minireseau",
        "format": "minireseau@1",
        "fiche": {
            "logiciel": {"version": "1.1.0", "enregistre_le": "2026-10-02"},
            "lieu": {"point": {"latitude_deg": 7.7769, "longitude_deg": -9.1861}},
            "ressource": {"mode": "cale", "version_base": "calage-guinee-v3"},
            "champ": {
                "pr": 0.78,
                "convention_pr": "tout_compris",
                "inclinaison_deg": 10,
                "degradation_annuelle": 0.005,
                "plan_actif": True,
                "orientation_deg": 0,
                "albedo": 0.2,
            },
            "charge": {
                "postes": [
                    {"nom": "Ménages", "energie_jour_kwh": 85.0, "profil_24": profil},
                    {"nom": "Moulin", "energie_jour_kwh": 22.5, "profil_24": profil},
                ],
                "facteurs_mensuels": [1.0] * 12,
                "croissance_annuelle": [1.0, 1.03, 1.06, 1.09],
            },
            "stockage": {
                "eta_charge": 0.95,
                "eta_decharge": 0.95,
                "profondeur_decharge": 0.8,
                "vieillissement_annuel": 0.02,
            },
            "groupe": {
                "puissance_kw": 30,
                "charge_minimale": 0.3,
                "disponibilite": 0.95,
                "conso_demi_charge_lh": 4.6,
                "conso_pleine_charge_lh": 8.2,
                "prix_litre_carburant": 13_500,
                "facteur_emission_kg_par_l": 2.68,
            },
            "dimensionnement": {
                "horizon_annees": 4,
                "cible_lpsp": 0.05,
                "grille_champ": {"min": 20, "max": 120, "pas": 10},
                "grille_stockage": {"min": 50, "max": 400, "pas": 25},
                "grille_auto": True,
            },
            "prix": {
                "monnaie": "GNF",
                "cout_par_kwc": 7_740_000,
                "cout_par_kwh_utile": 4_300_000,
                "taux_actualisation": 0.08,
                "opex_annuel": 25_000_000,
                "capex_complement": None,
                "annee_remplacement_stockage": 10,
            },
            "resultats": {
                "champ_kwc": 60,
                "stockage_kwh": 200,
                "lpsp_hors_groupe": 0.12,
                "lpsp_vecu": 0.01,
                "part_groupe": 0.11,
                "demande_kwh_an": 39_000,
                "non_servie_energie_kwh_an": 300,
                "non_servie_puissance_kwh_an": 0,
                "heures_groupe_an": 610,
                "demarrages_groupe_an": 210,
                "carburant_litres_an": 3_900,
                "cout_carburant_an": 52_650_000,
                "co2_kg_an": 10_452,
                "lcoe_par_kwh": 4_800,
                "part_capex": 0.62,
                "part_opex": 0.12,
                "part_carburant": 0.2,
                "part_remplacement": 0.06,
            },
        },
    }


def test_fiche_minireseau_acceptee() -> None:
    demande = valider(fiche_minireseau_exemple())
    assert isinstance(demande, DemandeMiniReseau)
    assert demande.fiche.lieu is not None and demande.fiche.lieu.point is not None
    assert (demande.fiche.lieu.point.latitude_deg, demande.fiche.lieu.point.longitude_deg) == (
        7.8,
        -9.2,
    )
    assert demande.fiche.charge.postes[1].nom == "Moulin"


def test_fiche_minireseau_minimale_acceptee() -> None:
    """Sans groupe, sans lieu ni résultats : une étude en cours part quand même."""
    brut = fiche_minireseau_exemple()
    for cle in ("lieu", "ressource", "groupe", "resultats"):
        del brut["fiche"][cle]
    assert isinstance(valider(brut), DemandeMiniReseau)


@pytest.mark.parametrize(
    ("module", "format_"),
    [("minireseau", "pv-autonome@1"), ("pv-autonome", "minireseau@1")],
)
def test_module_et_format_vont_ensemble(module: str, format_: str) -> None:
    brut = fiche_minireseau_exemple()
    brut["module"], brut["format"] = module, format_
    with pytest.raises(ValidationError):
        valider(brut)


def test_fiche_pv_sous_le_module_minireseau_refusee() -> None:
    brut = fiche_exemple()
    brut["module"], brut["format"] = "minireseau", "minireseau@1"
    with pytest.raises(ValidationError):
        valider(brut)


@pytest.mark.parametrize("profil", [[0.04] * 23, [0.04] * 25, [-0.01] + [0.04] * 23])
def test_profil_horaire_controle(profil: list[float]) -> None:
    brut = fiche_minireseau_exemple()
    brut["fiche"]["charge"]["postes"][0]["profil_24"] = profil
    with pytest.raises(ValidationError):
        valider(brut)


def test_nom_de_poste_coupe() -> None:
    brut = fiche_minireseau_exemple()
    brut["fiche"]["charge"]["postes"][0]["nom"] = "Centre de santé de la sous-préfecture " * 3
    demande = valider(brut)
    assert isinstance(demande, DemandeMiniReseau)
    nom = demande.fiche.charge.postes[0].nom
    assert len(nom) <= LONGUEUR_NOM_APPAREIL
    assert nom.startswith("Centre de santé")


@pytest.mark.parametrize(
    ("chemin", "cle"),
    [
        ((), "nom_site"),
        ((), "rapport"),
        (("charge",), "client"),
        (("groupe",), "fournisseur"),
    ],
)
def test_minireseau_champ_hors_contrat_refuse(chemin: tuple[str, ...], cle: str) -> None:
    brut = fiche_minireseau_exemple()
    cible = brut["fiche"]
    for etape in chemin:
        cible = cible[etape]
    cible[cle] = "x"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        valider(brut)

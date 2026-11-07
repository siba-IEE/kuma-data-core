"""Tests unitaires des fonctions pures de ``preparer_seed_cams_eac4_aod_ozone.py``.

Aucun réseau ni dépendance scientifique : ``cdsapi`` et ``xarray`` ne sont importés
par le script qu'au téléchargement et à l'ouverture des fichiers, jamais ici.
"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import pytest
from scripts.preparer_seed_cams_eac4_aod_ozone import (
    EMPRISE_GUINEE,
    GRANDEURS,
    HEURES_3H,
    HEURES_DIURNES,
    agreger_annee,
    agreger_journalier,
    calendrier,
    construire_requete,
    coordonnees_34_points,
    ecrire_compagnon,
    intervalles_annuels,
    liste_tronquee,
    mmr_vers_ppb,
    moyenne_des_heures,
    pixel_grille_le_plus_proche,
    regrouper_par_jour,
    unite_est_rapport_massique,
    verifier_emprise,
    verifier_fourchette,
    verifier_unite_ozone,
    verifier_variables_nc,
)

from kuma_data_core.db.seeds import cams_eac4_aod_ozone_journalier_seed_data as chargeur

pytestmark = pytest.mark.unit


def _jour_complet(valeurs: list[float]) -> dict[str, float]:
    return dict(zip(HEURES_3H, valeurs, strict=True))


# === Conversion ozone ======================================================


def test_conversion_mmr_vers_ppb_valeur_de_reference() -> None:
    # 1e-7 kg/kg x (28,9644 / 47,9982) x 1e9 = 100 x 0,6034476... = 60,3448 ppb.
    assert mmr_vers_ppb(1e-7) == pytest.approx(60.34476, abs=1e-4)
    assert mmr_vers_ppb(0.0) == 0.0


def test_unite_rapport_massique_graphies() -> None:
    for graphie in ("kg kg**-1", "kg kg-1", "kg/kg", "KG KG^-1"):
        assert unite_est_rapport_massique(graphie), graphie
    for graphie in ("ppb", "1", "mol mol**-1", "kg m**-3"):
        assert not unite_est_rapport_massique(graphie), graphie


def test_unite_ozone_inattendue_echoue() -> None:
    verifier_unite_ozone("kg kg**-1")
    with pytest.raises(RuntimeError, match="rapport de melange massique"):
        verifier_unite_ozone("mol mol**-1")
    with pytest.raises(RuntimeError):
        verifier_unite_ozone(None)


def test_variables_nc_absentes_listees() -> None:
    verifier_variables_nc(["aod550", "duaod550"], ("aod550", "duaod550"))
    with pytest.raises(RuntimeError, match=r"Variables reelles : \['aod550', 'autre'\]"):
        verifier_variables_nc(["aod550", "autre"], ("aod550", "duaod550"))


# === Agregation journaliere ================================================


def _instants_du_jour(jour: str, heures: tuple[str, ...] = HEURES_3H) -> list[str]:
    return [f"{jour}T{h}:00.000000000" for h in heures]


def test_regrouper_par_jour_ecarte_les_non_finis() -> None:
    instants = [
        "2021-01-01T00:00:00.000000000",
        "2021-01-01T03:00:00.000000000",
        "2021-01-02T00:00:00.000000000",
        "2021-01-03T00:00:00.000000000",
    ]
    par_jour, ecartees = regrouper_par_jour(instants, [0.1, math.nan, 0.3, math.inf])
    # Le jour 3 n'a qu'un pas non fini : present (vide), donc incomplet et non absent.
    assert par_jour == {
        "2021-01-01": {"00:00": 0.1},
        "2021-01-02": {"00:00": 0.3},
        "2021-01-03": {},
    }
    assert ecartees == 2


def test_regrouper_par_jour_pas_en_double_echoue() -> None:
    instants = ["2021-01-01T00:00:00", "2021-01-01T00:00:00"]
    with pytest.raises(RuntimeError, match="double"):
        regrouper_par_jour(instants, [0.1, math.nan])


def test_moyenne_journaliere_des_8_pas() -> None:
    pas = _jour_complet([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
    assert moyenne_des_heures(pas, HEURES_3H) == pytest.approx(0.45)


def test_moyenne_diurne_09_12_15() -> None:
    pas = _jour_complet([1.0, 2.0, 3.0, 10.0, 20.0, 30.0, 4.0, 5.0])
    assert HEURES_DIURNES == ("09:00", "12:00", "15:00")
    assert moyenne_des_heures(pas, HEURES_DIURNES) == pytest.approx(20.0)


def test_calendrier_bornes_incluses() -> None:
    assert calendrier(date(2024, 2, 28), date(2024, 3, 1)) == [
        "2024-02-28",
        "2024-02-29",
        "2024-03-01",
    ]


def test_jour_incomplet_exclu_et_liste() -> None:
    complet = _jour_complet([1.0] * 8)
    incomplet = {h: 1.0 for h in HEURES_3H if h != "21:00"}
    jours = ["2021-01-01", "2021-01-02"]
    agregat = agreger_journalier({"2021-01-01": complet, "2021-01-02": incomplet}, HEURES_3H, jours)
    assert agregat.valeurs == {"2021-01-01": 1.0}
    assert agregat.jours_incomplets == ["2021-01-02"]
    assert agregat.jours_absents == []
    # Le meme jour reste valable pour la moyenne diurne (09/12/15 presents).
    diurne = agreger_journalier({"2021-01-02": incomplet}, HEURES_DIURNES, ["2021-01-02"])
    assert diurne.valeurs == {"2021-01-02": 1.0}
    assert diurne.jours_incomplets == []


def test_jour_entierement_absent_detecte() -> None:
    """Un jour sans aucun pas dans le fichier (trou, fichier tronque) est liste absent."""
    jours = calendrier(date(2021, 1, 1), date(2021, 1, 3))
    par_jour = {"2021-01-01": _jour_complet([1.0] * 8), "2021-01-03": _jour_complet([3.0] * 8)}
    agregat = agreger_journalier(par_jour, HEURES_3H, jours)
    assert agregat.valeurs == {"2021-01-01": 1.0, "2021-01-03": 3.0}
    assert agregat.jours_absents == ["2021-01-02"]
    assert agregat.jours_incomplets == []


def test_jour_hors_calendrier_echoue() -> None:
    with pytest.raises(RuntimeError, match="hors de la fenetre"):
        agreger_journalier({"2021-02-01": _jour_complet([1.0] * 8)}, HEURES_3H, ["2021-01-01"])


def test_agreger_annee_ozone_deux_grandeurs_et_absents() -> None:
    # 2021-01-01 complet ; 2021-01-02 seulement 09/12/15 ; 2021-01-03 absent.
    instants = _instants_du_jour("2021-01-01") + _instants_du_jour("2021-01-02", HEURES_DIURNES)
    valeurs = [1e-7] * len(instants)
    par_grandeur, ecartees = agreger_annee(
        "go3", instants, valeurs, date(2021, 1, 1), date(2021, 1, 3)
    )
    assert ecartees == 0
    assert set(par_grandeur) == {"ozone_surface", "ozone_surface_diurne"}
    ozone = par_grandeur["ozone_surface"]
    assert ozone.valeurs["2021-01-01"] == pytest.approx(60.34476, abs=1e-4)
    assert ozone.jours_incomplets == ["2021-01-02"]
    assert ozone.jours_absents == ["2021-01-03"]
    diurne = par_grandeur["ozone_surface_diurne"]
    assert set(diurne.valeurs) == {"2021-01-01", "2021-01-02"}
    assert diurne.jours_absents == ["2021-01-03"]


def test_agreger_annee_aod() -> None:
    instants = _instants_du_jour("2021-01-01")
    par_grandeur, _ = agreger_annee(
        "aod550", instants, [0.5] * 8, date(2021, 1, 1), date(2021, 1, 1)
    )
    assert par_grandeur["aod_550"].valeurs == {"2021-01-01": pytest.approx(0.5)}
    par_grandeur, _ = agreger_annee(
        "duaod550", instants, [0.25] * 8, date(2021, 1, 1), date(2021, 1, 1)
    )
    assert par_grandeur["aod_poussiere_550"].valeurs == {"2021-01-01": pytest.approx(0.25)}


def test_fusion_de_periodes_disjointes() -> None:
    a = agreger_journalier({"2021-12-31": _jour_complet([1.0] * 8)}, HEURES_3H, ["2021-12-31"])
    b = agreger_journalier({}, HEURES_3H, ["2022-01-01"])
    a.fusionner(b)
    assert a.valeurs == {"2021-12-31": 1.0}
    assert a.jours_absents == ["2022-01-01"]
    with pytest.raises(RuntimeError, match="double"):
        a.fusionner(
            agreger_journalier({"2021-12-31": _jour_complet([2.0] * 8)}, HEURES_3H, ["2021-12-31"])
        )


def test_liste_tronquee() -> None:
    assert liste_tronquee(["2021-01-02", "2021-01-01"]) == {
        "nombre": 2,
        "dates": ["2021-01-01", "2021-01-02"],
        "tronquee": False,
    }
    longue = liste_tronquee(calendrier(date(2020, 1, 1), date(2021, 12, 31)), maximum=500)
    assert longue["nombre"] == 731
    assert len(longue["dates"]) == 500
    assert longue["tronquee"] is True


def test_hors_fourchette_echoue_sans_borne() -> None:
    verifier_fourchette("aod_550", "gin_kankan", {"2021-01-01": 0.0, "2021-01-02": 5.0})
    with pytest.raises(RuntimeError, match="hors"):
        verifier_fourchette("aod_550", "gin_kankan", {"2021-01-01": 5.01})
    with pytest.raises(RuntimeError, match="hors"):
        verifier_fourchette("ozone_surface", "gin_kankan", {"2021-01-01": -0.1})
    with pytest.raises(RuntimeError, match="hors"):
        verifier_fourchette("ozone_surface_diurne", "gin_kankan", {"2021-01-01": 200.5})


# === Perimetre et requetes =================================================


def test_liste_des_34_points() -> None:
    coords = coordonnees_34_points()
    assert len(coords) == 34
    assert {"gin_conakry_kaloum", "gin_nzerekore", "gin_boffa", "gin_yomou"} <= set(coords)


def test_points_et_pixels_dans_l_emprise() -> None:
    verifier_emprise(coordonnees_34_points())
    assert pixel_grille_le_plus_proche(9.509, -13.712) == (9.75, -13.5)
    with pytest.raises(RuntimeError, match="hors emprise"):
        verifier_emprise({"hors": (14.0, -10.0)}, EMPRISE_GUINEE)


def test_intervalles_annuels() -> None:
    assert intervalles_annuels(date(2004, 2, 1), date(2005, 3, 31)) == [
        (date(2004, 2, 1), date(2004, 12, 31)),
        (date(2005, 1, 1), date(2005, 3, 31)),
    ]


def test_requete_ozone_niveau_60() -> None:
    requete = construire_requete("ozone", date(2021, 1, 1), date(2021, 1, 31))
    assert requete["variable"] == ["ozone"]
    assert requete["model_level"] == ["60"]
    assert requete["data_format"] == "netcdf_zip"
    assert requete["date"] == ["2021-01-01/2021-01-31"]
    assert "model_level" not in construire_requete("aod", date(2021, 1, 1), date(2021, 1, 31))


# === Chargeur ==============================================================


def test_chargeur_sans_compagnon_vide(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(chargeur, "_DOSSIER", tmp_path)
    assert list(chargeur.iter_blocs_cams_eac4_aod_ozone()) == []
    assert list(chargeur.iter_captures_cams_eac4_aod_ozone()) == []


def test_chargeur_relit_un_compagnon(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(chargeur, "_DOSSIER", tmp_path)
    ecrire_compagnon(
        tmp_path,
        "gin_kankan",
        (10.5, -9.0),
        {g: {"2021-01-02": 2.0, "2021-01-01": 1.0} for g in GRANDEURS},
        {"periode_reelle": {"debut": "2021-01-01", "fin": "2021-01-02"}},
    )
    blocs = list(chargeur.iter_blocs_cams_eac4_aod_ozone())
    assert [b["grandeur_code"] for b in blocs] == sorted(GRANDEURS)
    assert blocs[0]["pixel"] == {"latitude": 10.5, "longitude": -9.0}
    assert list(blocs[0]["valeurs"]) == ["2021-01-01", "2021-01-02"]
    captures = list(chargeur.iter_captures_cams_eac4_aod_ozone())
    assert captures == [
        ("gin_kankan", {"periode_reelle": {"debut": "2021-01-01", "fin": "2021-01-02"}})
    ]

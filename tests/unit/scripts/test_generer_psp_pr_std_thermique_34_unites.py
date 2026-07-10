"""Tests unitaires des parties déterministes du script hors-base
`generer_psp_pr_std_thermique_34_unites.py` (WP8 Voie 2).

Ne touche pas à la base : ne teste que les fonctions pures (résolution alias,
appariement GHI/T2M par date). La connexion PostgreSQL et l'exécution complète
sont validées par l'exécution hors CI du script.
"""

from __future__ import annotations

from datetime import date

from scripts.generer_psp_pr_std_thermique_34_unites import (
    ALIAS_CODE_PACK_VERS_KDC,
    CODES_UNITES_PACK,
    _codes_kdc_pour_unite,
    apparier_ghi_t2m,
)


def test_liste_34_unites_pack() -> None:
    assert len(CODES_UNITES_PACK) == 34
    assert len(set(CODES_UNITES_PACK)) == 34, "codes uniques attendus"


def test_alias_boke_faranah() -> None:
    assert "gin_boke" in ALIAS_CODE_PACK_VERS_KDC
    assert "gin_faranah" in ALIAS_CODE_PACK_VERS_KDC
    assert "gin_boke_centre" in ALIAS_CODE_PACK_VERS_KDC["gin_boke"]
    assert "gin_faranah_centre" in ALIAS_CODE_PACK_VERS_KDC["gin_faranah"]


def test_resolution_code_sans_alias_retourne_lui_meme() -> None:
    assert _codes_kdc_pour_unite("gin_kankan") == ("gin_kankan",)


def test_resolution_code_avec_alias_boke() -> None:
    codes = _codes_kdc_pour_unite("gin_boke")
    assert "gin_boke" in codes
    assert "gin_boke_centre" in codes


def test_resolution_code_avec_alias_conakry() -> None:
    """Conakry est modelisée comme region_administrative dans le KDC :
    la commune de Kaloum porte les series NASA POWER daily et sert de
    proxy pour l'agglomeration (5 communes a moins de 15 km).
    """
    codes = _codes_kdc_pour_unite("gin_conakry")
    assert "gin_conakry" in codes
    assert "gin_conakry_kaloum" in codes


def test_apparier_ghi_t2m_intersecte_dates() -> None:
    ghi = {
        date(2021, 1, 1): 5.5,
        date(2021, 1, 2): 5.6,
        date(2021, 1, 3): 5.7,  # T2M manquant
    }
    t2m = {
        date(2021, 1, 1): 25.0,
        date(2021, 1, 2): 26.0,
        date(2021, 1, 4): 27.0,  # GHI manquant
    }
    mesures = apparier_ghi_t2m(ghi, t2m)
    assert len(mesures) == 2
    assert mesures[0]["annee"] == 2021
    assert mesures[0]["mois"] == 1
    assert mesures[0]["ghi_kwh_par_m2_jour"] == 5.5
    assert mesures[0]["t_amb_degc"] == 25.0


def test_apparier_ghi_t2m_ordre_chronologique() -> None:
    ghi = {date(2021, 3, 15): 5.0, date(2021, 1, 1): 4.0, date(2021, 2, 1): 4.5}
    t2m = dict.fromkeys(ghi, 25.0)
    mesures = apparier_ghi_t2m(ghi, t2m)
    assert [m["mois"] for m in mesures] == [1, 2, 3]


def test_apparier_ghi_t2m_aucune_date_commune() -> None:
    ghi = {date(2021, 1, 1): 5.5}
    t2m = {date(2022, 1, 1): 25.0}
    mesures = apparier_ghi_t2m(ghi, t2m)
    assert mesures == []

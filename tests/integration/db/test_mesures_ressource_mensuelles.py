"""Tests d'integration de la table ``mesures_ressource_mensuelles``.

Couvre les tests de volumes et de decomptes cumules (UNIQUE, plage
SARAH-3 effective 2021-2023) :

- volumes 2 376 lignes (216 SARAH-3 + 2 160 NASA POWER 1991-2020)
- source ``sarah3_monthly`` inseree dans ``sources``
- 12 series brutes inserees avec nommage correct
- exception Conakry-Kaloum (prefixe ``gin_conakry``) appliquee
- ``mesures_ressource`` inchangee (65 718 lignes journalier strict)
- decomptes cumules (sources, series, mesures)

Pattern ``db_session`` fixture conftest.py.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from kuma_data_core.db.models.mesures_ressource_mensuelles import MesureRessourceMensuelle

pytestmark = pytest.mark.integration


_CODES_SERIES_SARAH3_1_7A: tuple[str, ...] = (
    "gin_conakry_ghi_sarah3_2021_2023",
    "gin_kankan_ghi_sarah3_2021_2023",
    "gin_kindia_ghi_sarah3_2021_2023",
    "gin_labe_ghi_sarah3_2021_2023",
    "gin_mamou_ghi_sarah3_2021_2023",
    "gin_nzerekore_ghi_sarah3_2021_2023",
)

_CODES_SERIES_POWER_1991_2020: tuple[str, ...] = (
    "gin_conakry_ghi_power_1991_2020",
    "gin_kankan_ghi_power_1991_2020",
    "gin_kindia_ghi_power_1991_2020",
    "gin_labe_ghi_power_1991_2020",
    "gin_mamou_ghi_power_1991_2020",
    "gin_nzerekore_ghi_power_1991_2020",
)


def test_ti47_decompte_mesures_ressource_mensuelles(db_session: Session) -> None:
    """Décompte de ``mesures_ressource_mensuelles``.

    Décompte cumulé :
    - 216 SARAH-3 ICDR plage 2021-2023 (migration 041)
    - 2 160 GHI NASA POWER 1991-2020 (migration 041)
    - 8 640 climato 1991-2020 sur 4 grandeurs MERRA-2 (T2M, RH2M,
      vent_2m, vent_10m x 6 villes x 360, migration 050)
    - 5 760 climato 2001-2020 sur 4 grandeurs CERES SYN1deg pur (DHI,
      DNI, KT, albedo_surface x 6 villes x 240, migration 050 ; DHI
      restreint à la fenêtre pure CERES post-validation croisée - biais
      composite SRB/CERES -9 à -17 % observé sur 1991-2020, levé à
      -1.1 à -4.5 % en 2001-2020 pur ; miroir mensuel)
    - 4 320 ERA5-Land 2001-2020 (migration 069 : 3 grandeurs
      ghi/t2m/vent_10m x 6 villes x 240 mois)
    - 1 218 CAMS Radiation DNI 2004-2020 (migration 071 :
      grandeur dni x 6 villes x 203 mois, fenêtre 2004-02 -> 2020-12)
    - 216 CAMS Radiation DNI 2021-2023 (migration 073 :
      grandeur dni x 6 villes x 36 mois, séries récentes séparées)
    - 77 280 climato NASA POWER 28 communes (densification monthly, migration 087 :
      28 x (5 grandeurs x 360 [1991-2020] + 4 grandeurs x 240 [2001-2020]) =
      28 x 2 760). Reporte sur power_1991 -> 61 200 et power_2001 -> 32 640.
    Total : 99 810 lignes.
    """
    total = db_session.scalar(select(func.count()).select_from(MesureRessourceMensuelle))
    # +1 008 densification SARAH-3 (migration 088, 28 communes x 36 mois 2021-2023).
    # +1 008 densification CAMS DNI (migration 089, 28 communes x 36 mois 2021-2023).
    # +5 684 densification CAMS DNI climato (migration 095, 28 communes x
    # 203 mois 2004-02..2020-12) = 107 510.
    # +20 160 densification ERA5-Land mensuel (migration 096, 28 communes x
    # 3 grandeurs ghi/t2m/vent_10m x 240 mois 2001-2020) = 127 670.
    # +156 672 series mensuelles longues NASA POWER (profondeur, 34 points x
    # 4 608 mois = 5 grandeurs x 540 [1981-2025] + 2 x 504 [1984-2025] + 3 x 300 [2001-2025])
    # = 284 342.
    assert total == 284342

    # Decompte par source via JOIN
    n_sarah3 = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code LIKE '%sarah3%'
            """
        )
    ).scalar_one()
    # 216 (6 pilotes) + 1 008 densification (28 communes x 36 mois, migration 088).
    assert n_sarah3 == 1224

    # Decompte CAMS Radiation par source (exclut cams_eac4 PM) :
    # 1 218 climato 2004-2020 pilotes (071) + 216 recent pilotes 2021-2023 (073) + 1 008
    # densification recente 2021-2023 (089) + 5 684 densification climato 2004-2020
    # (migration 095, 28 communes x 203 mois) = 8 126.
    n_cams = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            JOIN sources s ON s.id = sm.source_id
            WHERE s.code = 'cams_radiation'
            """
        )
    ).scalar_one()
    assert n_cams == 8126

    # Decompte des series _power_1991_2020 : 6 GHI + 24 nouvelles
    # brutes (4 grandeurs MERRA-2 x 6 villes x 360) =
    # 10 800 lignes.
    n_power_1991 = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code LIKE '%power_1991%'
            """
        )
    ).scalar_one()
    # +50 400 densification (28 communes x 5 grandeurs ghi/t2m/rh2m/vent_2m/vent_10m
    # x 360 mois 1991-2020, migration 087).
    assert n_power_1991 == 61200

    # Decompte des series _power_2001_2020 (DHI, DNI, KT, albedo_surface,
    # 4 grandeurs x 6 villes x 240 = 5 760 lignes) - fenêtre réduite
    # imposée par la transition SRB 4.x → CERES SYN1deg
    # et par le biais composite sur DHI.
    n_power_2001 = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code LIKE '%power_2001%'
            """
        )
    ).scalar_one()
    # +26 880 densification (28 communes x 4 grandeurs dhi/dni/kt/albedo_surface
    # x 240 mois 2001-2020, migration 087).
    assert n_power_2001 == 32640


def test_ti48_source_sarah3_monthly_inseree(db_session: Session) -> None:
    """Source ``sarah3_monthly`` insérée dans ``sources`` avec
    metadonnees attendues (institution CM SAF/EUMETSAT, fiabilite haute)."""
    row = db_session.execute(
        text(
            """
            SELECT code, type_source, fiabilite, organisation
            FROM sources WHERE code = 'sarah3_monthly'
            """
        )
    ).first()
    assert row is not None
    assert row.type_source == "base_donnees"
    assert row.fiabilite == "haute"
    assert "CM SAF" in row.organisation
    assert "EUMETSAT" in row.organisation


def test_ti49_12_series_brutes_1_7a_inserees(db_session: Session) -> None:
    """12 séries brutes (6 SARAH-3 + 6 NASA POWER 1991-2020)
    insérées dans ``series_metadonnees`` avec nommage correct."""
    codes_1_7a = list(_CODES_SERIES_SARAH3_1_7A) + list(_CODES_SERIES_POWER_1991_2020)
    rows = db_session.execute(
        text("SELECT code FROM series_metadonnees WHERE code = ANY(:codes) ORDER BY code"),
        {"codes": codes_1_7a},
    ).all()
    codes_trouves = {r.code for r in rows}
    assert len(codes_trouves) == 12
    assert codes_trouves == set(codes_1_7a)


def test_ti50_exception_conakry_appliquee(db_session: Session) -> None:
    """Exception Conakry-Kaloum (préfixe ``gin_conakry`` sans
    ``_kaloum``) appliquée via helper ``_prefixe_ville_pour_serie``."""
    # Les deux codes Conakry doivent exister sous gin_conakry (pas gin_conakry_kaloum)
    for code_attendu in (
        "gin_conakry_ghi_sarah3_2021_2023",
        "gin_conakry_ghi_power_1991_2020",
    ):
        n = db_session.execute(
            text("SELECT COUNT(*) FROM series_metadonnees WHERE code = :c"),
            {"c": code_attendu},
        ).scalar_one()
        assert n == 1, f"Code {code_attendu!r} attendu une fois, trouve {n}"

    # Les variants gin_conakry_kaloum_* ne doivent PAS exister
    for code_interdit in (
        "gin_conakry_kaloum_ghi_sarah3_2021_2023",
        "gin_conakry_kaloum_ghi_power_1991_2020",
    ):
        n = db_session.execute(
            text("SELECT COUNT(*) FROM series_metadonnees WHERE code = :c"),
            {"c": code_interdit},
        ).scalar_one()
        assert n == 0, f"Code {code_interdit!r} ne devrait pas exister (exception D-32)"


# === Decompte mesures_ressource derive du seed =============================
# Le NASA daily est servi depuis le seed offline committe (deterministe). Le
# compte attendu est derive du seed (re-seed-proof) pour la part NASA, + un
# litteral pour les sources daily non-NASA (ERA5-Land, CAMS, EAC4 PM,
# precipitation : sources offline deja deterministes, jamais affectees par la
# maturation du seed). La precipitation utilise un seed dedie (hors
# NASA_DAILY_PAYLOADS), donc elle vit dans ce litteral.
# 64272 + 51 128 (migration 094 : precipitation aux 28 communes,
# 28 x 1826 jours, sentinelle-free) = 115 400.
# + 153 384 (migration 097 : ERA5-Land daily aux 28 communes, 3 grandeurs
# x 28 x 1826, seed dedie chunke hors NASA_DAILY_PAYLOADS) = 268 784.
# + 95 424 (migration 098 : PM EAC4 pm2_5/pm10 aux 28 communes, 2 grandeurs
# x 28 x 1704 jours 2021-01..2025-08, seed dedie hors NASA_DAILY_PAYLOADS) = 364 208.
# + 4 147 830 (migration 106 : backfill journalier profondeur 1981/1984/2001-2020
# aux 34 points, 10 grandeurs, seed dedie groupe par serie hors NASA_DAILY_PAYLOADS,
# capture gapless) = 4 512 038.
_MESURES_NON_NASA_DAILY: int = 4512038


def _mesures_ressource_attendu() -> int:
    """Compte attendu de mesures_ressource : part NASA daily derivee du seed offline.

    En mode offline (CI), chaque (ville, parametre) NASA daily est ingere une fois
    avec ses valeurs non-sentinelles du seed -> somme deterministe ; + part non-NASA
    stable. Total = 162 876 au seed du 2026-06-19 (entierement muri).
    """
    from kuma_data_core.db.seeds.nasa_power_daily_seed_data import NASA_DAILY_PAYLOADS

    nasa = sum(
        1
        for payload in NASA_DAILY_PAYLOADS.values()
        for vals in payload["properties"]["parameter"].values()
        for v in vals.values()
        if v != -999.0
    )
    return _MESURES_NON_NASA_DAILY + nasa


def test_ti51_mesures_ressource_journalier_inchange(db_session: Session) -> None:
    """Décompte de ``mesures_ressource`` (journalier strict).

    Décompte cumulé :
    65 718 lignes (une table dédiée mensuelle a préservé cette table) + 32 862
    lignes vent/albédo journalières 2021-2025 (migration 048, 6 villes x 3
    grandeurs, minoré de 6 sentinelles `-999.0` filtrées sur ``albedo_surface``
    2025-12-31) = 98 580 lignes. + 32 868 ERA5-Land journalier
    2021-2025 (migration 069 : 3 grandeurs x 6 villes x 1826
    jours) = 131 448 lignes. + 10 956 precipitation journalier 2021-2025
    (migration 080 : 6 villes x 1826 jours) = 142 404
    lignes. + 6 (maturation kt : 6 dernieres journees sentinelle de 2025
    finalisees cote NASA, ingestion live migration 029, kt 10 950 -> 10 956)
    = 142 410 lignes. + 20 448 PM EAC4 journalier 2021-01..2025-08
    (migration 081 : 6 villes x 2 grandeurs x 1704 jours) = 162 858 lignes.
    """
    n_ressource = db_session.execute(text("SELECT COUNT(*) FROM mesures_ressource")).scalar_one()
    # Exact : le NASA daily est servi offline (seed committe)
    # -> mesures_ressource deterministe. Attendu DERIVE du seed (re-seed-proof)
    # pour la part NASA + litteral non-NASA stable (= 162 876 au seed 2026-06-19).
    assert n_ressource == _mesures_ressource_attendu()


def test_ti52_decomptes_cumules_post_1_7a(db_session: Session) -> None:
    """Decomptes cumules (semantique brutes uniquement).

    Durcissement : filtre les series calculees REFERENTIELLES (la famille
    des ecarts / rangs inter-source : ecart_relatif_referentiel,
    rang_referentiel_temporel/spatial, et ecart_relatif_dni_cams) pour
    preserver la semantique « series brutes + Kuma
    calculees pre-referentielles ». L'exclusion est une CATEGORIE coherente
    (grandeurs calculees referentielles).

    Evolution :
    - migration 047 : +18 series vent/albedo
      brutes journalieres (78 -> 96).
    - migration 050 : +48 series climato mensuelle
      long-terme (96 -> 144). 8 grandeurs brutes x 6 villes (4 MERRA-2
      en 1991-2020 + 4 CERES en 2001-2020 - DHI restreint a 2001-2020
      pure CERES suite a la validation croisee).
    - migration 051 : +18 series climato calculees
      Kuma (hep, productible_specifique_theorique, fraction_diffuse, 3 x
      6 villes). Total hors calculees : 144 -> 162.
        - migration 054 : +6 series horaires brutes pilote
          Conakry-Kaloum 2021-2023 (ghi/dni/dhi/t2m/rh2m/kt). Total hors
          calculees : 162 -> 168.
        - migration 056 : +6 series horaires Kindia
          pleine profondeur 2001-2025 (ghi/dni/dhi/t2m/rh2m/kt). Le seed
          des series est inconditionnel ; seule l'ingestion de masse est
          gardee par KUMA_SKIP_INGESTION_MASSE_HORAIRE,
          le decompte de series est donc invariant. Total hors calculees :
          168 -> 174.
        - migrations 058/060/062/064 : +24 series
          horaires pleine profondeur 2001-2025 pour 4 villes neuves
          (Mamou, Labe, Kankan, Nzerekore x 6 grandeurs). Seed
          inconditionnel. Total hors calculees : 174 -> 198.
        - migrations 068/069 : +1 source (ecmwf_era5_land)
          + 36 series ERA5-Land (3 grandeurs ghi/t2m/vent_10m x 6 villes x
          2 granularites : mensuel 2001-2020 + journalier 2021-2025). Total
          hors calculees : 198 -> 234.
        - migrations 070/071 : +1 source
          (cams_radiation) + 6 series CAMS Radiation DNI mensuel (grandeur
          dni x 6 villes, 2004-02 -> 2020-12). dni n'est pas une grandeur
          calculee referentielle -> comptee. Total : 234 -> 240.
        - migration 072 : +6 series calculees
          ecart_relatif_dni_cams (kuma_calculs). Grandeur calculee
          REFERENTIELLE -> EXCLUE du decompte (meme categorie que les
          ecarts/rangs). Total inchange : 240. mesures_ressource
          (_mensuelles) inchangees : ecrit grandeurs_metier seulement.
        - migration 073 : +6 series
          dni cams recentes (grandeur dni, comptee) + 216 mesures. Total
          hors calculees : 240 -> 246 ; mensuelles 22 314 -> 22 530.
        - migrations 074-076 : +1 source
          (esmap_wapp, mesure sol) + 1 serie GHI sol horaire Kankan
          (gin_kankan_ghi_esmap_wapp_2021_2023, brute confiance A, comptee) +
          17 520 mesures HORAIRES (mesures_ressource_horaires). Total hors
          calculees : 246 -> 247 ; sources 13 -> 14 ; mensuelles inchangees
          (ecrit en horaire, pas en mensuel).
        - migrations 077-078 : +1 serie DNI sol
          horaire Kankan (gin_kankan_dni_esmap_wapp_2021_2023, brute confiance A,
          comptee) + 17 520 mesures HORAIRES. Source esmap_wapp REUTILISEE (pas de
          nouvelle source). Total hors calculees : 247 -> 248 ; sources inchange
          (14) ; mensuelles inchangees.
        - migration 080 : +unite mm_par_jour + grandeur
          precipitation (brute) + 6 series precipitation journalieres NASA POWER
          (comptees) + 10 956 mesures journalieres 2021-2025. Total hors
          calculees : 248 -> 254 ; sources inchange (14, nasa_power reutilise) ;
          mensuelles inchangees (journalier).
        - migration 081 : +source cams_eac4 + unite ug/m3 +
          grandeurs pm2_5/pm10 (brutes) + 12 series PM EAC4 (6 villes x 2 grandeurs,
          comptees) + 20 448 mesures journalieres 2021-01..2025-08. Total hors
          calculees : 254 -> 266 ; sources 14 -> 15 ; mensuelles inchangees (journalier).
        - migration 086 : +252 series brutes daily NASA POWER
          (28 nouvelles communes chef-lieu x 9 grandeurs ghi/dni/dhi/t2m/rh2m/kt/
          vent_2m/vent_10m/albedo_surface, comptees) + mesures journalieres offline
          (derive du seed, +28 payloads dans NASA_DAILY_PAYLOADS). Total hors calculees :
          266 -> 518 ; sources inchange (15, nasa_power reutilise) ; mensuelles
          inchangees (daily). Le compte mesures_ressource reste derive du seed via
          _mesures_ressource_attendu (auto-inclut les 28 nouveaux payloads).
        - migration 087 : +252 series climato
          mensuelles NASA POWER (28 communes x 9 grandeurs, 2 fenetres) + 77 280
          mesures mensuelles offline (28 x 2 760). Total hors calculees : 518 -> 770 ;
          mesures_ressource_mensuelles 22 530 -> 99 810 ; sources inchange (15).

    sources = 15 (14 + cams_eac4)
    series_metadonnees hors calculees referentielles = 770 (518 + 252 densification monthly)
    mesures_ressource = derive du seed (cf. _mesures_ressource_attendu, +28 payloads)
    mesures_ressource_mensuelles = 99 810 (22 530 + 77 280 densification monthly 087)
    """
    n_sources = db_session.execute(text("SELECT COUNT(*) FROM sources")).scalar_one()
    # Exclusion = famille des grandeurs calculees REFERENTIELLES (ecarts / rangs
    # inter-source). ecart_relatif_dni_cams rejoint cette famille -> n'est pas
    # compte dans les series brutes.
    n_series_hors_calculees_ref = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM series_metadonnees
            WHERE grandeur_code NOT IN ('ecart_relatif_referentiel',
                                        'rang_referentiel_temporel',
                                        'rang_referentiel_spatial',
                                        'ecart_relatif_dni_cams')
            """
        )
    ).scalar_one()
    n_ressource = db_session.execute(text("SELECT COUNT(*) FROM mesures_ressource")).scalar_one()
    n_mens = db_session.execute(
        text("SELECT COUNT(*) FROM mesures_ressource_mensuelles")
    ).scalar_one()
    assert n_sources == 15
    # 770 + 28 (densif SARAH-3, migration 088) + 28 (densif CAMS DNI, migration 089)
    # + 168 (migration 092 : hep/psp/fd climato+recent aux 28, 6 series/commune ;
    # ces calculees ne sont pas dans la famille referentielle exclue) = 994.
    # + 56 (migration 093 : humidex + variabilite_journaliere aux 28, 1 serie/commune
    # chacune ; le rang_referentiel_temporel des 28 EST dans la famille exclue -> non compte ;
    # l'indicateur ne cree pas de serie) = 1050.
    # + 28 (migration 094 : precipitation aux 28 communes, 1 serie/commune ;
    # grandeur brute hors famille referentielle exclue) = 1078.
    # + 28 (migration 095 : CAMS DNI climato 2004-2020 aux 28 communes,
    # 1 serie/commune ; brute hors famille referentielle exclue) = 1106.
    # + 84 (migration 096 : ERA5-Land mensuel aux 28 communes, 3 grandeurs/
    # commune ; brutes hors famille referentielle exclue) = 1190.
    # + 84 (migration 097 : ERA5-Land daily aux 28 communes, 3 grandeurs/
    # commune ; brutes hors famille referentielle exclue) = 1274.
    # + 56 (migration 098 : PM EAC4 pm2_5/pm10 aux 28 communes, 2 grandeurs/
    # commune ; brutes hors famille referentielle exclue) = 1330.
    # + 340 (profondeur mensuelle NASA POWER : 34 points x 10 grandeurs, series longues
    # 1981/1984/2001-2025 ; brutes hors famille referentielle exclue) = 1670.
    # + 340 (profondeur journaliere NASA POWER migration 106 : 34 points x 10 grandeurs,
    # backfill 1981/1984/2001-2020 ; brutes hors famille referentielle exclue) = 2010.
    # + 270 (volet horaire : 252 series aux 28 communes + 18 nouvelles aux pilotes,
    # vents/precipitation ; les 36 pilotes historiques sont renommees, pas creees) = 2280.
    assert n_series_hors_calculees_ref == 2280
    # Exact : NASA daily offline (seed) -> deterministe.
    # Attendu derive du seed (cf. _mesures_ressource_attendu, = 162 876).
    assert n_ressource == _mesures_ressource_attendu()
    # 22 530 + 77 280 (densif monthly 087) + 1 008 (densif SARAH-3 088)
    # + 1 008 (densif CAMS DNI recent 089) + 5 684 (densif CAMS DNI climato 2004-2020,
    # migration 095, 28 x 203) = 107 510.
    # + 20 160 (densif ERA5-Land mensuel, migration 096, 28 x 3 x 240) = 127 670.
    # + 156 672 (profondeur mensuelle NASA POWER, 34 x 4 608) = 284 342.
    assert n_mens == 284342

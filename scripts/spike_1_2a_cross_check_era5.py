"""Cross-check ERA5 vs NASA POWER.

Confronte le GHI mensuel agrégé de NASA POWER (depuis le dump
``data/spike_1_2a/raw_01.json`` et ``raw_02.json`` produits par
``spike_1_2a_extract.py``) à ERA5 ``mean_surface_solar_radiation_downwards``
(ECMWF Climate Data Store) sur Conakry-Kaloum et Labé, 2021-2025.

Métriques calculées par site :
- biais moyen (ERA5 - NASA, en kWh/m²/jour)
- biais relatif moyen (en %)
- RMSE (Root Mean Square Error)
- corrélation de Pearson

Sortie :
- ``data/spike_1_2a/era5_monthly.nc`` : NetCDF brut téléchargé depuis CDS
- ``data/spike_1_2a/era5_cross_check.json`` : métriques agrégées

Dépendances : ``cdsapi``, ``xarray``, ``netCDF4`` (dev deps uniquement,
séparation prod/dev).

Authentification : ``~/.cdsapirc`` (format standard cdsapi à 2 lignes
``url`` + ``key``).

Usage : ``uv run --group dev python scripts/spike_1_2a_cross_check_era5.py``
"""

from __future__ import annotations

import json
import math
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import cdsapi  # type: ignore[import-untyped]
import xarray as xr  # type: ignore[import-untyped]

REPERTOIRE_SORTIE = Path("data/spike_1_2a")
CHEMIN_NETCDF = REPERTOIRE_SORTIE / "era5_monthly.nc"
CHEMIN_METRIQUES = REPERTOIRE_SORTIE / "era5_cross_check.json"

# Sites au format (code, latitude, longitude) cohérent avec les 2
# profils climatiques etudies.
SITES = (
    ("gin_conakry_kaloum", 9.50917, -13.71222),
    ("gin_labe", 11.31667, -12.28333),
)

# Bounding box englobant les 2 sites avec une marge 0.5° pour
# permettre la sélection de la cellule la plus proche. Format CDS :
# [Nord, Ouest, Sud, Est].
AREA_BBOX = [12.0, -14.5, 9.0, -11.5]


# === Téléchargement ERA5 ===================================================


def telecharger_era5_monthly() -> None:
    """Télécharge ERA5 monthly means surface solar radiation downwards
    pour 2021-2025 sur la bounding box.
    """
    if CHEMIN_NETCDF.exists():
        print(f"  NetCDF déjà présent : {CHEMIN_NETCDF}")
        return

    print("  Requête CDS API (queue possible)...")
    debut = time.perf_counter()
    client = cdsapi.Client()
    # Deux quirks CDS : (1) la clé `format` est dépréciée, utiliser
    # `data_format` ; (2) `mean_surface_solar_radiation_downwards` est
    # ambigu côté MARS (collision avec « mean square slope of waves »),
    # utiliser `surface_solar_radiation_downwards` qui renvoie la
    # version monthly mean lorsque le product_type est
    # `monthly_averaged_reanalysis`.
    client.retrieve(
        "reanalysis-era5-single-levels-monthly-means",
        {
            "product_type": "monthly_averaged_reanalysis",
            "variable": "surface_solar_radiation_downwards",
            "year": [str(y) for y in range(2021, 2026)],
            "month": [f"{m:02d}" for m in range(1, 13)],
            "time": "00:00",
            "area": AREA_BBOX,
            "data_format": "netcdf",
        },
        str(CHEMIN_NETCDF),
    )
    duree = round(time.perf_counter() - debut, 1)
    print(f"  Téléchargement terminé en {duree}s ({CHEMIN_NETCDF.stat().st_size} octets)")


# === Lecture ERA5 + conversion ============================================


def extraire_era5_par_site() -> dict[str, dict[str, float]]:
    """Pour chaque site, retourne le dictionnaire ``{YYYY-MM: ghi_kwh_m2_j}``.

    La variable réelle retournée par CDS pour ERA5
    monthly_averaged_reanalysis est ``ssrd`` (GRIB shortname), unité
    ``J m**-2`` (Joules par mètre carré, accumulation moyenne quotidienne
    selon le GRIB_stepType ``avgad``).

    Conversion : 1 kWh = 3.6e6 J, donc ``kWh/m²/jour = J/m²/jour / 3.6e6``.
    """
    ds = xr.open_dataset(CHEMIN_NETCDF)

    variable_candidates = ["ssrd", "msdwswrf", "avg_sdswrf"]
    variable_name = next((v for v in variable_candidates if v in ds.data_vars), None)
    if variable_name is None:
        raise RuntimeError(
            f"Aucune variable solaire trouvée dans le NetCDF ERA5. "
            f"Variables disponibles : {list(ds.data_vars)}"
        )
    units_str = str(ds[variable_name].attrs.get("units", "(inconnue)"))
    print(f"  Variable ERA5 détectée : {variable_name} (unité : {units_str})")

    data = ds[variable_name]
    print(f"  Dimensions : {data.dims}, shape : {data.shape}")

    resultat: dict[str, dict[str, float]] = {}
    for code, lat, lon in SITES:
        cell = data.sel(latitude=lat, longitude=lon, method="nearest")
        valeurs_par_mois: dict[str, float] = {}

        time_dim = next(d for d in cell.dims if d in ("time", "valid_time"))
        for i, instant_np in enumerate(cell[time_dim].values):
            cle_mois = str(instant_np)[:7]  # "YYYY-MM"
            valeur_brute = float(cell.isel({time_dim: i}).values)
            # ssrd : J/m^2/jour -> kWh/m^2/jour via division par 3.6e6
            valeur_kwh_m2_j = valeur_brute / 3.6e6
            valeurs_par_mois[cle_mois] = valeur_kwh_m2_j

        resultat[code] = valeurs_par_mois
        cell_lat = float(cell["latitude"].values)
        cell_lon = float(cell["longitude"].values)
        print(
            f"  Site {code:24s} : cellule ERA5 ({cell_lat:.3f}, {cell_lon:.3f}), "
            f"{len(valeurs_par_mois)} mois extraits"
        )

    ds.close()
    return resultat


# === Lecture NASA POWER + agrégation mensuelle ============================


SENTINELLE = -999.0


def charger_nasa_power_daily(chemin: Path) -> dict[str, float]:
    """Charge un payload NASA POWER daily depuis le dump JSON et retourne
    le dictionnaire ``{YYYYMMDD: ghi_kwh_m2_j}``, sentinelles écartées.
    """
    payload = json.loads(chemin.read_text(encoding="utf-8"))
    ghi_par_jour: dict[str, float] = payload["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]
    return {k: v for k, v in ghi_par_jour.items() if v != SENTINELLE}


def agreger_mensuel(daily: dict[str, float]) -> dict[str, float]:
    """Agrège des valeurs journalières en moyenne mensuelle.

    Clés d'entrée : ``YYYYMMDD``. Clés de sortie : ``YYYY-MM``.
    """
    cumuls: dict[str, list[float]] = defaultdict(list)
    for cle_jour, valeur in daily.items():
        cle_mois = f"{cle_jour[:4]}-{cle_jour[4:6]}"
        cumuls[cle_mois].append(valeur)
    return {mois: sum(vals) / len(vals) for mois, vals in cumuls.items() if vals}


# === Métriques cross-check ================================================


def calculer_metriques(nasa: dict[str, float], era5: dict[str, float]) -> dict[str, Any]:
    """Calcule biais moyen, biais relatif, RMSE, corrélation de Pearson sur
    les mois communs aux deux séries.
    """
    mois_communs = sorted(set(nasa.keys()) & set(era5.keys()))
    if not mois_communs:
        return {"nb_mois_communs": 0, "erreur": "aucun mois commun"}

    diffs = [era5[m] - nasa[m] for m in mois_communs]
    n = len(diffs)
    biais_moyen = sum(diffs) / n
    rmse = math.sqrt(sum(d * d for d in diffs) / n)

    moyenne_nasa = sum(nasa[m] for m in mois_communs) / n
    biais_relatif_pct = (biais_moyen / moyenne_nasa) * 100.0 if moyenne_nasa else None

    # Corrélation de Pearson
    moyenne_era5 = sum(era5[m] for m in mois_communs) / n
    cov = sum((nasa[m] - moyenne_nasa) * (era5[m] - moyenne_era5) for m in mois_communs)
    var_nasa = sum((nasa[m] - moyenne_nasa) ** 2 for m in mois_communs)
    var_era5 = sum((era5[m] - moyenne_era5) ** 2 for m in mois_communs)
    correlation = cov / math.sqrt(var_nasa * var_era5) if var_nasa > 0 and var_era5 > 0 else None

    return {
        "nb_mois_communs": n,
        "moyenne_nasa_kwh_m2_j": round(moyenne_nasa, 3),
        "moyenne_era5_kwh_m2_j": round(moyenne_era5, 3),
        "biais_moyen_kwh_m2_j": round(biais_moyen, 3),
        "biais_relatif_pct": round(biais_relatif_pct, 2) if biais_relatif_pct is not None else None,
        "rmse_kwh_m2_j": round(rmse, 3),
        "correlation_pearson": round(correlation, 4) if correlation is not None else None,
    }


# === Main ==================================================================


def main() -> None:
    REPERTOIRE_SORTIE.mkdir(parents=True, exist_ok=True)
    print("=== Spike 1-2a - Cross-check ERA5 vs NASA POWER (C6) ===")

    print("\n[1/4] Téléchargement ERA5 monthly means 2021-2025")
    telecharger_era5_monthly()

    print("\n[2/4] Extraction ERA5 par site")
    era5_par_site = extraire_era5_par_site()

    print("\n[3/4] Agrégation NASA POWER daily -> monthly")
    nasa_par_site: dict[str, dict[str, float]] = {}
    for code, _, _ in SITES:
        suffixe = "01" if code == "gin_conakry_kaloum" else "02"
        chemin = REPERTOIRE_SORTIE / f"raw_{suffixe}.json"
        daily = charger_nasa_power_daily(chemin)
        mensuel = agreger_mensuel(daily)
        nasa_par_site[code] = mensuel
        print(f"  Site {code:24s} : {len(daily)} jours -> {len(mensuel)} mois")

    print("\n[4/4] Calcul métriques par site")
    rapport: dict[str, Any] = {"sites": {}}
    for code, _, _ in SITES:
        metriques = calculer_metriques(nasa_par_site[code], era5_par_site[code])
        rapport["sites"][code] = metriques
        print(f"\n  === {code} ===")
        for cle, val in metriques.items():
            print(f"    {cle:30s} : {val}")

    CHEMIN_METRIQUES.write_text(json.dumps(rapport, indent=2), encoding="utf-8")
    print(f"\nMétriques sauvegardées : {CHEMIN_METRIQUES.resolve()}")


if __name__ == "__main__":
    main()

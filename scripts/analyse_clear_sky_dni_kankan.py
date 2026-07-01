"""Test du socle ciel-clair : DNI sol vs CAMS BNIc sur heures claires - Kankan.

Analyse seule (dev deps), **hors base, hors migration**. Détermine si le sur-biais
CAMS DNI all-sky (+28 %, note de calage DNI) vient du **socle ciel-clair**
de CAMS (turbidité/aérosol sous-estimés) ou de son **traitement nuages**.

Trois parties (les deux premières sans réseau ni base) :

1. **Détection ciel-clair côté sol** (local) : ``pvlib.clearsky.detect_clearsky``
   (Reno-Hansen) sur le **GHI sol 1-min** (CSV WAPP), comparé au GHI clear-sky
   modélisé (Ineichen + turbidité Linke climatologique). Masque clair par minute
   → heure « claire » si ``>= SEUIL_CLAIR`` des minutes de jour sont claires.
   Sortie : nombre d'heures claires détectées, par saison.
2. **Contexte mensuel** (zéro-download) : facteur nuage interne CAMS ``BNI/BNIc``
   par saison, depuis le CSV mensuel déjà sur disque. Confirme « Harmattan ≈ clair »
   (BNI ≈ BNIc) et « mousson très nuageux ». **Contexte, PAS le test** (domaines
   d'intégration différents : BNIc mensuel intègre toutes les heures de jour).
3. **Test du socle** (nécessite l'artefact ``BNIc`` horaire) : sur les heures
   **détectées claires**, compare **DNI sol horaire** (base, confiance A) à **CAMS
   BNIc horaire** (artefact committé). MBD/RMSD, %, par saison. Auto-skippé tant
   que l'artefact est absent (ADS indisponible).

Convention de biais : **biais = CAMS - sol** (positif = sur-estimation CAMS).

Lecture du test :
- écart ≈ +28 % sur heures claires → **socle ciel-clair confirmé** ;
- écart qui s'effondre → c'était le **traitement nuages**.
Ne présume pas le résultat - rapporte ce que la donnée dit.

Usage : ``uv run --group dev python scripts/analyse_clear_sky_dni_kankan.py``
"""

from __future__ import annotations

import gzip
import math
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]
import pvlib  # type: ignore[import-untyped]
from pvlib.location import Location  # type: ignore[import-untyped]

# === Périmètre / constantes ===============================================

_LAT, _LON, _ALT = 10.38333333, -9.30000000, 381.0  # gin_kankan (seed)
_TZ = "UTC"

_REP_WAPP = Path("data/guinee/01-physique")
_FICHIERS_GHI = (
    "solar-measurements_guinea-kankan_qc (1).csv",
    "solar-measurements_guinea-kankan_qc_year2.csv",
)
_CSV_MENSUEL = Path("data/cams/gin_kankan_dni_2021_2023.csv")  # déjà sur disque
_ARTEFACT_HORAIRE = Path("scripts/donnees/cams_bnic_horaire_kankan_2021_2023.csv.gz")

_SOL_DNI_H = "gin_kankan_dni_esmap_wapp_2021_2023"  # série Core (Part 3, base)

# Détection
_FENETRE_DETECT = 10  # minutes (défaut Reno-Hansen)
_SEUIL_JOUR_WM2 = 5.0  # GHI clear-sky modélisé > 5 W/m² => minute de jour
_MIN_MIN_JOUR = 30  # >= 30 minutes de jour dans l'heure pour la juger
_SEUILS_CLAIR = (0.75, 0.85, 0.95)  # fraction de minutes claires (sensibilité)
_SEUIL_CLAIR_REF = 0.85

# Saisons (cohérent analyse_calage_dni_kankan.py)
_HARMATTAN = frozenset({11, 12, 1, 2, 3})
_MOUSSON = frozenset({6, 7, 8, 9})

# Test (Part 3)
_ELEV_MIN_TEST = 10.0  # degrés ; DNI significatif, signal turbidité propre

# Colonnes du CSV mensuel CAMS (0-indexées)
_COL_BNIC_M, _COL_BNI_M = 5, 9


def _saison(mois: int) -> str:
    if mois in _HARMATTAN:
        return "Harmattan"
    if mois in _MOUSSON:
        return "Mousson"
    return "Intersaison"


# ============== PARTIE 1 - détection ciel-clair (sol, local) ===============


def _lire_ghi_minutes() -> pd.Series:
    """GHI sol 1-min (W/m²) des 2 fichiers WAPP → Series indexée UTC, dédupliquée."""
    frames = []
    for nom in _FICHIERS_GHI:
        df = pd.read_csv(
            _REP_WAPP / nom,
            usecols=["Timestamp", "GHI"],
            skiprows=[1],  # 2e ligne = unités
            dtype={"GHI": "string"},
            encoding="latin-1",
        )
        df["t"] = pd.to_datetime(df["Timestamp"], utc=True, errors="coerce")
        # to_numeric sur une colonne 'string' -> Float64 nullable ; detect_clearsky
        # exige du numpy float64 (son indexation .values casse sinon).
        df["ghi"] = pd.to_numeric(df["GHI"], errors="coerce").astype("float64")
        frames.append(df.dropna(subset=["t"])[["t", "ghi"]])
    s = pd.concat(frames, ignore_index=True).drop_duplicates("t").set_index("t")["ghi"]
    return s.sort_index()


def detecter_heures_claires() -> pd.DataFrame:
    """Détecte les heures claires (sol) → DataFrame [heure UTC, frac_clair, n_jour]."""
    ghi = _lire_ghi_minutes()
    grille = pd.date_range(ghi.index.min().floor("h"), ghi.index.max().ceil("h"), freq="1min")
    mesure = ghi.reindex(grille).fillna(0.0)  # gap diurne -> 0 (conservateur : non-clair)

    loc = Location(_LAT, _LON, tz=_TZ, altitude=_ALT)
    cs = loc.get_clearsky(grille, model="ineichen")  # ghi/dni/dhi clear-sky modélisés
    clair_min = pvlib.clearsky.detect_clearsky(mesure, cs["ghi"], window_length=_FENETRE_DETECT)
    jour_min = cs["ghi"] > _SEUIL_JOUR_WM2

    df = pd.DataFrame({"clair": clair_min.to_numpy(), "jour": jour_min.to_numpy()}, index=grille)
    df["heure"] = df.index.floor("h")
    g = df.groupby("heure")
    n_jour = g["jour"].sum()
    n_clair_jour = (df["clair"] & df["jour"]).groupby(df["heure"]).sum()
    out = pd.DataFrame({"n_jour": n_jour, "n_clair_jour": n_clair_jour})
    out["frac_clair"] = out["n_clair_jour"] / out["n_jour"].where(out["n_jour"] > 0)
    out["mois"] = out.index.month
    return out


def _heures_claires_set(detect: pd.DataFrame, seuil: float) -> pd.DatetimeIndex:
    sel = detect[(detect["n_jour"] >= _MIN_MIN_JOUR) & (detect["frac_clair"] >= seuil)]
    return pd.DatetimeIndex(sel.index)


def partie1_detection() -> pd.DataFrame:
    detect = detecter_heures_claires()
    n_h_jour = int((detect["n_jour"] >= _MIN_MIN_JOUR).sum())
    print("====== PARTIE 1 - détection ciel-clair (GHI sol 1-min, Reno-Hansen) ======")
    print(
        f"minutes lues : {int(detect['n_jour'].sum())} de jour | "
        f"heures de jour (>= {_MIN_MIN_JOUR} min jour) : {n_h_jour}"
    )
    print(f"{'seuil frac claire':<20}{'h claires':>10}  | par saison (Harm / Mous / Inter)")
    for seuil in _SEUILS_CLAIR:
        idx = _heures_claires_set(detect, seuil)
        sub = detect.loc[idx]
        par = sub["mois"].map(_saison).value_counts()
        marque = "  <- ref" if abs(seuil - _SEUIL_CLAIR_REF) < 1e-9 else ""
        print(
            f"{seuil:<20.2f}{len(idx):>10}  | "
            f"{par.get('Harmattan', 0):>4} / {par.get('Mousson', 0):>4} / "
            f"{par.get('Intersaison', 0):>4}{marque}"
        )
    return detect


# ============== PARTIE 2 - contexte mensuel CAMS (zéro-download) ============


def partie2_contexte_mensuel() -> None:
    print("\n====== PARTIE 2 - facteur nuage interne CAMS (BNI/BNIc) par saison ======")
    if not _CSV_MENSUEL.exists():
        print(f"  (CSV mensuel absent : {_CSV_MENSUEL}) - contexte ignoré.")
        return
    rows: list[tuple[int, float, float]] = []
    for ln in _CSV_MENSUEL.read_text(encoding="utf-8", errors="replace").splitlines():
        if not ln or ln.startswith("#"):
            continue
        c = ln.split(";")
        if len(c) <= _COL_BNI_M:
            continue
        mois = int(c[0][5:7])
        bnic, bni = float(c[_COL_BNIC_M]), float(c[_COL_BNI_M])
        if not (math.isnan(bnic) or math.isnan(bni)) and bnic > 0:
            rows.append((mois, bnic, bni))
    df = pd.DataFrame(rows, columns=["mois", "bnic", "bni"])
    df["saison"] = df["mois"].map(_saison)
    print(f"{'saison':<14}{'n mois':>7}{'BNI/BNIc':>12}   (1.00 = ciel-clair pur)")
    for saison in ("Harmattan", "Intersaison", "Mousson"):
        sub = df[df["saison"] == saison]
        if len(sub):
            fac = float(sub["bni"].sum() / sub["bnic"].sum())  # agrégé (robuste)
            print(f"{saison:<14}{len(sub):>7}{fac:>12.3f}")
    fac_glob = float(df["bni"].sum() / df["bnic"].sum())
    print(f"{'GLOBAL':<14}{len(df):>7}{fac_glob:>12.3f}")
    print(
        "  Lecture : Harmattan ~ clair (BNI proche de BNIc) -> peu de nuages à mal "
        "traiter ;\n  le sur-biais DNI y est donc essentiellement un effet de socle."
    )


# ============== PARTIE 3 - test du socle (artefact horaire requis) ==========


def _charger_artefact_bnic() -> pd.DataFrame:
    txt = gzip.decompress(_ARTEFACT_HORAIRE.read_bytes()).decode("utf-8")
    lignes = [ligne.split(";") for ligne in txt.splitlines()[1:] if ligne]
    df = pd.DataFrame(lignes, columns=["instant_utc", "bnic", "bni", "fiab"])
    df["t"] = pd.to_datetime(df["instant_utc"], utc=True)
    df["bnic"] = pd.to_numeric(df["bnic"])
    df["bni"] = pd.to_numeric(df["bni"])
    return df[["t", "bnic", "bni"]]


def _charger_sol_dni_horaire() -> pd.DataFrame:
    import sqlalchemy as sa  # import local : Part 3 seule a besoin de la base

    from kuma_data_core.db.session import get_engine

    q = sa.text(
        "SELECT m.instant_mesure AS instant, m.valeur AS dni "
        "FROM mesures_ressource_horaires m JOIN series_metadonnees s ON s.id = m.serie_id "
        "WHERE s.code = :code ORDER BY 1"
    )
    with get_engine().connect() as c:
        rows = c.execute(q, {"code": _SOL_DNI_H}).all()
    # alias 'instant' (pas 't') : 't' entre en collision avec l'accesseur Row.t.
    df = pd.DataFrame(
        [(r._mapping["instant"], float(r._mapping["dni"])) for r in rows], columns=["t", "dni"]
    )
    df["t"] = pd.to_datetime(df["t"], utc=True)
    return df


def _metriques(d_cams: pd.Series, sol: pd.Series, comp: str) -> dict[str, Any]:
    biais = d_cams - sol
    moy_sol = float(sol.mean())
    mbd = float(biais.mean())
    rmsd = math.sqrt(float((biais**2).mean()))
    return {
        "comp": comp,
        "n": len(sol),
        "sol": round(moy_sol, 1),
        "cams": round(float(d_cams.mean()), 1),
        "mbd": round(mbd, 1),
        "mbd_pct": round(100 * mbd / moy_sol, 1) if moy_sol else float("nan"),
        "rmsd": round(rmsd, 1),
        "rmsd_pct": round(100 * rmsd / moy_sol, 1) if moy_sol else float("nan"),
    }


def _ligne(label: str, m: dict[str, Any]) -> str:
    return (
        f"{label:<22} n={m['n']:>5} | sol={m['sol']:>6} {m['comp']}={m['cams']:>6} | "
        f"MBD={m['mbd']:>6} ({m['mbd_pct']:>5}%) | RMSD={m['rmsd']:>6} ({m['rmsd_pct']:>5}%)"
    )


def partie3_test_socle(detect: pd.DataFrame) -> None:
    print("\n====== PARTIE 3 - test du socle : DNI sol vs CAMS BNIc (heures claires) ======")
    if not _ARTEFACT_HORAIRE.exists():
        print(f"  BLOQUÉ : artefact CAMS BNIc horaire absent ({_ARTEFACT_HORAIRE}).")
        print("  Cause : ADS cams-solar-radiation-timeseries indisponible (retrieve 400/502).")
        print("  Action : relancer scripts/preparer_artefact_cams_bnic_horaire.py quand l'ADS")
        print("           répond ; cette partie s'exécutera alors automatiquement.")
        return

    claires = _heures_claires_set(detect, _SEUIL_CLAIR_REF)
    cams = _charger_artefact_bnic()
    sol = _charger_sol_dni_horaire()
    df = sol.merge(cams, on="t", how="inner")
    df = df[df["t"].isin(claires)]  # heures détectées claires (sol)

    # Élévation solaire à l'instant (hour-beginning) ; on garde le DNI significatif.
    pos = pvlib.solarposition.get_solarposition(pd.DatetimeIndex(df["t"]), _LAT, _LON)
    df["elev"] = pos["apparent_elevation"].to_numpy()
    df = df[df["elev"] >= _ELEV_MIN_TEST]
    df["mois"] = df["t"].dt.month

    print(f"heures claires retenues (elev >= {_ELEV_MIN_TEST}deg) : {len(df)}")
    print("--- DNI sol vs CAMS BNIc (socle ciel-clair modélisé) ---")
    print(_ligne("GLOBAL", _metriques(df["bnic"], df["dni"], "bnic")))
    for saison, mois_set in (("Harmattan", _HARMATTAN), ("Mousson", _MOUSSON)):
        sub = df[df["mois"].isin(mois_set)]
        if len(sub):
            print(_ligne(saison, _metriques(sub["bnic"], sub["dni"], "bnic")))
    inter = df[~df["mois"].isin(_HARMATTAN | _MOUSSON)]
    if len(inter):
        print(_ligne("Intersaison", _metriques(inter["bnic"], inter["dni"], "bnic")))
    # Sanity : sur heures claires, l'all-sky BNI doit ~ coïncider avec BNIc.
    print("--- Sanity : CAMS BNI all-sky sur les mêmes heures claires ---")
    print(_ligne("GLOBAL (bni)", _metriques(df["bni"], df["dni"], "bni")))


def main() -> None:
    detect = partie1_detection()
    partie2_contexte_mensuel()
    partie3_test_socle(detect)


if __name__ == "__main__":
    main()

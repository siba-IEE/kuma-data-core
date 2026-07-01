"""Analyse de calage DNI sol vs satellite - Kankan (terrain-lite, 2 volets).

Livrable **humain ponctuel** (dev deps), exécuté hors CI. **Analyse seule** :
aucune écriture en base, aucune migration. Déterministe et reproductible : lit les
séries de la base, recalcule tout, sort les chiffres exacts cités par la note de
calage DNI.

Deux volets (produits satellite distincts) :

- **Volet A** : DNI sol (WAPP, confiance A) vs **NASA POWER horaire** - biais
  horaire, heures de jour (élévation ≥ 5°), par saison, avec/sans heures « rare »,
  stationnarité an 1 vs an 2. Miroir du volet GHI.
- **Volet B** : DNI sol **agrégé mensuel** (kWh/m²/jour) vs **CAMS mensuel** -
  offset mensuel par saison (focus Harmattan). Contrôle d'offset systématique à
  résolution mensuelle (n ≈ 23 mois), **pas** une validation haute-résolution.

Convention de biais : **biais = satellite - sol** (positif = sur-estimation du
satellite). Relatif (%) = biais / moyenne_sol x 100.

Usage : ``uv run --group dev python scripts/analyse_calage_dni_kankan.py``
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd  # type: ignore[import-untyped]
import pvlib  # type: ignore[import-untyped]
import sqlalchemy as sa

from kuma_data_core.db.session import get_engine

_SOL_H = "gin_kankan_dni_esmap_wapp_2021_2023"  # sol horaire W/m2 (A)
_NASA_H = "gin_kankan_dni_nasa_power_2001_2023"  # NASA horaire W/m2 (B)
_CAMS_M = "gin_kankan_dni_cams_2021_2023"  # CAMS mensuel kWh/m2/jour (B)
_LAT, _LON = 10.38333333, -9.30000000  # gin_kankan
_ELEV_MIN = 5.0
_BASCULE_AN2 = pd.Timestamp("2022-10-18", tz="UTC")
_HARMATTAN = frozenset({11, 12, 1, 2, 3})
_MOUSSON = frozenset({6, 7, 8, 9})
_SEUIL_MOIS_PLEIN = 28  # n_jours >= 28 -> mois plein (documenté)


# ============================ VOLET A (horaire) ============================


def _charger_horaire() -> pd.DataFrame:
    q = sa.text(
        """
        SELECT a.instant_mesure AS instant, a.valeur AS sol, b.valeur AS sat,
               (a.commentaire_editorial LIKE '%rare%') AS rare
        FROM mesures_ressource_horaires a
        JOIN series_metadonnees sa_ ON sa_.id = a.serie_id AND sa_.code = :sol
        JOIN mesures_ressource_horaires b ON b.instant_mesure = a.instant_mesure
        JOIN series_metadonnees sb ON sb.id = b.serie_id AND sb.code = :nasa
        ORDER BY a.instant_mesure
        """
    )
    with get_engine().connect() as c:
        rows = c.execute(q, {"sol": _SOL_H, "nasa": _NASA_H}).all()
    df = pd.DataFrame(
        [
            (m["instant"], float(m["sol"]), float(m["sat"]), bool(m["rare"]))
            for m in (r._mapping for r in rows)
        ],
        columns=["t", "sol", "sat", "rare"],
    )
    df["t"] = pd.to_datetime(df["t"], utc=True)
    times = pd.DatetimeIndex(df["t"])
    df["elev"] = pvlib.solarposition.get_solarposition(times, _LAT, _LON)[
        "apparent_elevation"
    ].to_numpy()
    df["mois"] = df["t"].dt.month
    df["an"] = (df["t"] >= _BASCULE_AN2).map({False: 1, True: 2})
    return df


def _metriques(sub: pd.DataFrame) -> dict[str, Any]:
    d = sub["sat"] - sub["sol"]  # biais satellite
    moy_sol = float(sub["sol"].mean())
    mbd = float(d.mean())
    rmsd = math.sqrt(float((d**2).mean()))
    return {
        "n": len(sub),
        "sol": round(moy_sol, 1),
        "sat": round(float(sub["sat"].mean()), 1),
        "mbd": round(mbd, 1),
        "mbd_pct": round(100 * mbd / moy_sol, 1),
        "rmsd": round(rmsd, 1),
        "rmsd_pct": round(100 * rmsd / moy_sol, 1),
    }


def _ligne(label: str, m: dict[str, Any]) -> str:
    return (
        f"{label:<22} n={m['n']:>5} | sol={m['sol']:>6} sat={m['sat']:>6} | "
        f"MBD={m['mbd']:>6} ({m['mbd_pct']:>5}%) | RMSD={m['rmsd']:>6} ({m['rmsd_pct']:>5}%)"
    )


def volet_a() -> None:
    df = _charger_horaire()
    jour = df[df["elev"] >= _ELEV_MIN]
    print("====== VOLET A - DNI sol vs NASA POWER horaire (biais = NASA - sol) ======")
    print(
        f"paires={len(df)} | heures de jour (elev>=5deg)={len(jour)} | rare={int(df['rare'].sum())}"
    )
    print("--- Global + par saison (heures de jour) ---")
    print(_ligne("GLOBAL jour", _metriques(jour)))
    print(_ligne("Harmattan (11-3)", _metriques(jour[jour["mois"].isin(_HARMATTAN)])))
    print(_ligne("Mousson (6-9)", _metriques(jour[jour["mois"].isin(_MOUSSON)])))
    print(
        _ligne("Intersaison (4,5,10)", _metriques(jour[~jour["mois"].isin(_HARMATTAN | _MOUSSON)]))
    )
    print("--- Avec vs sans rare ---")
    print(_ligne("avec rare", _metriques(jour)))
    print(_ligne("sans rare", _metriques(jour[~jour["rare"]])))
    print("--- Stationnarite ---")
    print(_ligne("an 1", _metriques(jour[jour["an"] == 1])))
    print(_ligne("an 2", _metriques(jour[jour["an"] == 2])))


# ============================ VOLET B (mensuel) ============================


def _charger_mensuel() -> pd.DataFrame:
    sol_q = sa.text(
        """
        SELECT EXTRACT(YEAR FROM m.instant_mesure AT TIME ZONE 'UTC')::int AS annee,
               EXTRACT(MONTH FROM m.instant_mesure AT TIME ZONE 'UTC')::int AS mois,
               SUM(m.valeur) / 1000.0
                 / COUNT(DISTINCT (m.instant_mesure AT TIME ZONE 'UTC')::date) AS sol,
               COUNT(DISTINCT (m.instant_mesure AT TIME ZONE 'UTC')::date) AS n_jours
        FROM mesures_ressource_horaires m JOIN series_metadonnees s ON s.id = m.serie_id
        WHERE s.code = :sol GROUP BY 1, 2
        """
    )
    cams_q = sa.text(
        """
        SELECT mm.annee, mm.mois, mm.valeur AS cams
        FROM mesures_ressource_mensuelles mm JOIN series_metadonnees s ON s.id = mm.serie_id
        WHERE s.code = :cams
        """
    )
    with get_engine().connect() as c:
        sol = pd.DataFrame(
            [
                (int(r.annee), int(r.mois), float(r.sol), int(r.n_jours))
                for r in c.execute(sol_q, {"sol": _SOL_H})
            ],
            columns=["annee", "mois", "sol", "n_jours"],
        )
        cams = pd.DataFrame(
            [
                (int(r.annee), int(r.mois), float(r.cams))
                for r in c.execute(cams_q, {"cams": _CAMS_M})
            ],
            columns=["annee", "mois", "cams"],
        )
    sol = sol[sol["n_jours"] >= _SEUIL_MOIS_PLEIN]  # mois pleins seulement
    df = sol.merge(cams, on=["annee", "mois"], how="inner")
    df["offset"] = df["cams"] - df["sol"]  # biais CAMS
    return df


def _offset(sub: pd.DataFrame) -> dict[str, Any]:
    moy_sol = float(sub["sol"].mean())
    off = float(sub["offset"].mean())
    std = float(sub["offset"].std(ddof=1)) if len(sub) > 1 else float("nan")
    se = std / math.sqrt(len(sub)) if len(sub) > 1 else float("nan")
    return {
        "n": len(sub),
        "sol": round(moy_sol, 2),
        "cams": round(float(sub["cams"].mean()), 2),
        "offset": round(off, 2),
        "offset_pct": round(100 * off / moy_sol, 1),
        "std": round(std, 2),
        "se": round(se, 2),
    }


def _ligne_b(label: str, m: dict[str, Any]) -> str:
    return (
        f"{label:<22} n={m['n']:>3} mois | sol={m['sol']:>5} cams={m['cams']:>5} kWh/m2/j | "
        f"offset={m['offset']:>6} ({m['offset_pct']:>5}%) | sd={m['std']:>5} se={m['se']:>5}"
    )


def volet_b() -> None:
    df = _charger_mensuel()
    print("\n====== VOLET B - DNI sol mensuel vs CAMS (kWh/m2/jour ; biais = CAMS - sol) ======")
    print(f"mois pleins apparies (n_jours>={_SEUIL_MOIS_PLEIN}) = {len(df)}")
    print(_ligne_b("GLOBAL", _offset(df)))
    print(_ligne_b("Harmattan (11-3)", _offset(df[df["mois"].isin(_HARMATTAN)])))
    print(_ligne_b("Mousson (6-9)", _offset(df[df["mois"].isin(_MOUSSON)])))
    print(_ligne_b("Intersaison (4,5,10)", _offset(df[~df["mois"].isin(_HARMATTAN | _MOUSSON)])))


def main() -> None:
    volet_a()
    volet_b()


if __name__ == "__main__":
    main()

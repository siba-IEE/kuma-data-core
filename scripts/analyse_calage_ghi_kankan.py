"""Analyse de calage GHI sol vs satellite - Kankan (terrain-lite).

Livrable **humain ponctuel** (dev deps), exécuté hors CI. Caractérise le **biais
du GHI satellite NASA POWER vs la mesure sol WAPP** au pixel co-localisé de Kankan,
sur le recouvrement 2021-10 → 2023-10. **Analyse seule** : aucune écriture en base,
aucune migration, aucune propagation au record long (B-calibré différé).

Déterministe et reproductible : lit les deux séries horaires de la base, recalcule
tout (cycle diurne, MBD/RMSD par saison, avec/sans heures « rare », stationnarité
an 1 vs an 2) et sort les chiffres exacts cités par la note de calage.

Convention de biais : **biais = satellite - sol** (erreur du produit satellite ;
positif = sur-estimation). Relatif (%) = biais / moyenne_sol x 100 (comparable a
l'ecart inter-source). Heures de jour : **elevation solaire >= 5 deg** (pvlib, UTC).

Usage : ``uv run --group dev python scripts/analyse_calage_ghi_kankan.py``
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd  # type: ignore[import-untyped]
import pvlib  # type: ignore[import-untyped]
import sqlalchemy as sa

from kuma_data_core.db.session import get_engine

_WAPP = "gin_kankan_ghi_esmap_wapp_2021_2023"  # sol mesure (confiance A)
_NASA = "gin_kankan_ghi_nasa_power_2001_2025"  # satellite (confiance B)
_LAT, _LON = 10.38333333, -9.30000000  # gin_kankan (seed migration 011)
_ELEV_MIN = 5.0  # heures de jour
_BASCULE_AN2 = pd.Timestamp("2022-10-18", tz="UTC")  # an 1 / an 2

# Saisons Haute-Guinee (mois UTC) - definitions explicites portees dans la note.
_HARMATTAN = frozenset({11, 12, 1, 2, 3})  # saison seche / Harmattan
_MOUSSON = frozenset({6, 7, 8, 9})  # saison humide / mousson
# intersaison = {4, 5, 10} (transition) - rapportee separement, rien de cache.


def charger() -> pd.DataFrame:
    """Paires (instant, sol, sat, rare) en inner join sur l'instant."""
    q = sa.text(
        """
        SELECT a.instant_mesure AS instant, a.valeur AS sol, b.valeur AS sat,
               (a.commentaire_editorial LIKE '%rare%') AS rare
        FROM mesures_ressource_horaires a
        JOIN series_metadonnees sa_ ON sa_.id = a.serie_id AND sa_.code = :wapp
        JOIN mesures_ressource_horaires b ON b.instant_mesure = a.instant_mesure
        JOIN series_metadonnees sb ON sb.id = b.serie_id AND sb.code = :nasa
        ORDER BY a.instant_mesure
        """
    )
    with get_engine().connect() as c:
        rows = c.execute(q, {"wapp": _WAPP, "nasa": _NASA}).all()
    df = pd.DataFrame(
        [
            (m["instant"], float(m["sol"]), float(m["sat"]), bool(m["rare"]))
            for m in (r._mapping for r in rows)
        ],
        columns=["t", "sol", "sat", "rare"],
    )
    df["t"] = pd.to_datetime(df["t"], utc=True)
    return df


def enrichir(df: pd.DataFrame) -> pd.DataFrame:
    times = pd.DatetimeIndex(df["t"])
    df["elev"] = pvlib.solarposition.get_solarposition(times, _LAT, _LON)[
        "apparent_elevation"
    ].to_numpy()
    df["mois"] = df["t"].dt.month
    df["an"] = (df["t"] >= _BASCULE_AN2).map({False: 1, True: 2})
    return df


def metriques(sub: pd.DataFrame) -> dict[str, Any]:
    d = sub["sat"] - sub["sol"]  # biais satellite
    moy_sol = float(sub["sol"].mean())
    mbd = float(d.mean())
    rmsd = math.sqrt(float((d**2).mean()))
    return {
        "n": len(sub),
        "moy_sol": round(moy_sol, 1),
        "moy_sat": round(float(sub["sat"].mean()), 1),
        "mbd": round(mbd, 1),
        "mbd_pct": round(100 * mbd / moy_sol, 1),
        "rmsd": round(rmsd, 1),
        "rmsd_pct": round(100 * rmsd / moy_sol, 1),
    }


def _ligne(label: str, m: dict[str, Any]) -> str:
    return (
        f"{label:<22} n={m['n']:>5} | sol={m['moy_sol']:>6} sat={m['moy_sat']:>6} | "
        f"MBD={m['mbd']:>6} ({m['mbd_pct']:>5}%) | RMSD={m['rmsd']:>6} ({m['rmsd_pct']:>5}%)"
    )


def main() -> None:
    df = enrichir(charger())
    jour = df[df["elev"] >= _ELEV_MIN]
    print("=== Calage GHI Kankan sol(WAPP) vs satellite(NASA) - biais = sat - sol ===")
    print(
        f"paires totales={len(df)} | heures de jour (elev>=5deg)={len(jour)} | "
        f"heures rare={int(df['rare'].sum())}"
    )

    print("\n--- Global + par saison (heures de jour, toutes heures) ---")
    print(_ligne("GLOBAL jour", metriques(jour)))
    print(_ligne("Harmattan (11-3)", metriques(jour[jour["mois"].isin(_HARMATTAN)])))
    print(_ligne("Mousson (6-9)", metriques(jour[jour["mois"].isin(_MOUSSON)])))
    inter = jour[~jour["mois"].isin(_HARMATTAN | _MOUSSON)]
    print(_ligne("Intersaison (4,5,10)", metriques(inter)))

    print("\n--- Avec vs sans les heures 'rare' (heures de jour) ---")
    print(_ligne("avec rare", metriques(jour)))
    print(_ligne("sans rare", metriques(jour[~jour["rare"]])))

    print("\n--- Stationnarite an1 (2021-10..2022-10) vs an2 (2022-10..2023-10) ---")
    print(_ligne("an 1", metriques(jour[jour["an"] == 1])))
    print(_ligne("an 2", metriques(jour[jour["an"] == 2])))


if __name__ == "__main__":
    main()

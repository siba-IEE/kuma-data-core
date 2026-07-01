"""Script d'extraction NASA POWER.

Exécute un plan d'extraction (10 appels variés). Sauvegarde les payloads
bruts JSON et un fichier de métriques agrégées dans ``data/spike_1_2a/``
(gitignored).

Plan d'extraction (10 appels variés) :

 1. Conakry-Kaloum / daily / 2021-01-01 → 2025-12-31 / 7 paramètres
 2. Labé / daily / 2021-01-01 → 2025-12-31 / 7 paramètres
 3. Conakry-Kaloum / hourly / 2024-07-01 → 2024-07-31 / 7 paramètres
 4. Conakry-Kaloum / hourly / 2026-02-15 → 2026-02-21 / 7 paramètres
 5. Conakry-Kaloum / daily / 2024-01-01 → 2024-12-31 / 7 paramètres
 6. Conakry-Kaloum / daily / 2021-01-01 → 2021-12-31 / 7 paramètres
 7. Conakry-Kaloum / daily / 2021-01-01 → 2025-12-31 / 1 paramètre (GHI seul)
 8. Conakry-Kaloum / daily / 2021-01-01 → 2025-12-31 / 1 paramètre (T2M seul)
 9. Labé / daily / 2024-01-01 → 2024-12-31 / 7 paramètres
10. Conakry-Kaloum / daily / 2023-07-01 → 2023-07-31 / 7 paramètres

Sortie :
- ``data/spike_1_2a/raw_<id>.json`` : payload JSON brut par appel
- ``data/spike_1_2a/metrics.json`` : métriques agrégées (latence,
  taille payload, nombre de sentinelles, observations)

Usage : ``uv run python scripts/spike_1_2a_extract.py``
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from typing import Any

from kuma_data_core.exceptions import NasaPowerError
from kuma_data_core.external.nasa_power import (
    SENTINELLE_VALEUR_MANQUANTE,
    NasaPowerResponse,
    fetch_daily,
    fetch_hourly,
)

# === Configuration ========================================================

PARAMS_7_COMPLETS: tuple[str, ...] = (
    "ALLSKY_SFC_SW_DWN",
    "ALLSKY_SFC_SW_DNI",
    "ALLSKY_SFC_SW_DIFF",
    "CLRSKY_SFC_SW_DWN",
    "ALLSKY_KT",
    "T2M",
    "RH2M",
)

SITE_CONAKRY = {"code": "gin_conakry_kaloum", "lat": 9.50917, "lon": -13.71222}
SITE_LABE = {"code": "gin_labe", "lat": 11.31667, "lon": -12.28333}

REPERTOIRE_SORTIE = Path("data/spike_1_2a")


# === Définition du plan d'extraction ======================================


def plan_extraction() -> list[dict[str, Any]]:
    """Énumération exhaustive des 10 appels du plan d'extraction."""
    return [
        {
            "id": 1,
            "site": SITE_CONAKRY,
            "endpoint": "daily",
            "start": date(2021, 1, 1),
            "end": date(2025, 12, 31),
            "params": PARAMS_7_COMPLETS,
            "label": "Conakry / daily / 5 ans / 7 params (pivot C1+C2+C4+C5)",
        },
        {
            "id": 2,
            "site": SITE_LABE,
            "endpoint": "daily",
            "start": date(2021, 1, 1),
            "end": date(2025, 12, 31),
            "params": PARAMS_7_COMPLETS,
            "label": "Labé / daily / 5 ans / 7 params (divergence climatique)",
        },
        {
            "id": 3,
            "site": SITE_CONAKRY,
            "endpoint": "hourly",
            "start": date(2024, 7, 1),
            "end": date(2024, 7, 31),
            "params": PARAMS_7_COMPLETS,
            "label": "Conakry / hourly / juillet 2024 mousson",
        },
        {
            "id": 4,
            "site": SITE_CONAKRY,
            "endpoint": "hourly",
            "start": date(2026, 2, 15),
            "end": date(2026, 2, 21),
            "params": PARAMS_7_COMPLETS,
            "label": "Conakry / hourly / 7j février 2026 (frontière NRT)",
        },
        {
            "id": 5,
            "site": SITE_CONAKRY,
            "endpoint": "daily",
            "start": date(2024, 1, 1),
            "end": date(2024, 12, 31),
            "params": PARAMS_7_COMPLETS,
            "label": "Conakry / daily / 1 an 2024 / 7 params (latence vs 5 ans)",
        },
        {
            "id": 6,
            "site": SITE_CONAKRY,
            "endpoint": "daily",
            "start": date(2021, 1, 1),
            "end": date(2021, 12, 31),
            "params": PARAMS_7_COMPLETS,
            "label": "Conakry / daily / 1 an 2021 / 7 params (latence variation)",
        },
        {
            "id": 7,
            "site": SITE_CONAKRY,
            "endpoint": "daily",
            "start": date(2021, 1, 1),
            "end": date(2025, 12, 31),
            "params": ("ALLSKY_SFC_SW_DWN",),
            "label": "Conakry / daily / 5 ans / GHI seul (param subset)",
        },
        {
            "id": 8,
            "site": SITE_CONAKRY,
            "endpoint": "daily",
            "start": date(2021, 1, 1),
            "end": date(2025, 12, 31),
            "params": ("T2M",),
            "label": "Conakry / daily / 5 ans / T2M seul (climat-only)",
        },
        {
            "id": 9,
            "site": SITE_LABE,
            "endpoint": "daily",
            "start": date(2024, 1, 1),
            "end": date(2024, 12, 31),
            "params": PARAMS_7_COMPLETS,
            "label": "Labé / daily / 1 an 2024 / 7 params (latence Labé)",
        },
        {
            "id": 10,
            "site": SITE_CONAKRY,
            "endpoint": "daily",
            "start": date(2023, 7, 1),
            "end": date(2023, 7, 31),
            "params": PARAMS_7_COMPLETS,
            "label": "Conakry / daily / 1 mois 2023-07 / 7 params (latence courte)",
        },
    ]


# === Métriques par appel ==================================================


def compter_sentinelles_et_valeurs(
    response: NasaPowerResponse,
) -> dict[str, dict[str, int | float | None]]:
    """Pour chaque paramètre : nombre de valeurs, sentinelles, min, max, moyenne.

    La moyenne est calculée hors sentinelles.
    """
    resultat: dict[str, dict[str, int | float | None]] = {}
    for nom_param, valeurs_par_date in response.properties.parameter.items():
        valeurs = list(valeurs_par_date.values())
        nb_sentinelles = sum(1 for v in valeurs if v == SENTINELLE_VALEUR_MANQUANTE)
        valeurs_valides = [v for v in valeurs if v != SENTINELLE_VALEUR_MANQUANTE]
        moyenne = sum(valeurs_valides) / len(valeurs_valides) if valeurs_valides else None
        resultat[nom_param] = {
            "nb_valeurs": len(valeurs),
            "nb_sentinelles": nb_sentinelles,
            "min": min(valeurs_valides) if valeurs_valides else None,
            "max": max(valeurs_valides) if valeurs_valides else None,
            "moyenne": moyenne,
        }
    return resultat


def detecter_anomalies_ghi_clrsky(response: NasaPowerResponse) -> dict[str, int]:
    """Compte les anomalies GHI > CLRSKY si les 2 paramètres sont présents."""
    params = response.properties.parameter
    if "ALLSKY_SFC_SW_DWN" not in params or "CLRSKY_SFC_SW_DWN" not in params:
        return {"verifie": 0, "anomalies": 0, "applicable": 0}
    ghi_par_date = params["ALLSKY_SFC_SW_DWN"]
    clrsky_par_date = params["CLRSKY_SFC_SW_DWN"]
    verifie = 0
    anomalies = 0
    for cle_date in ghi_par_date:
        if cle_date not in clrsky_par_date:
            continue
        ghi = ghi_par_date[cle_date]
        clrsky = clrsky_par_date[cle_date]
        if ghi == SENTINELLE_VALEUR_MANQUANTE or clrsky == SENTINELLE_VALEUR_MANQUANTE:
            continue
        verifie += 1
        if ghi > clrsky:
            anomalies += 1
    return {"verifie": verifie, "anomalies": anomalies, "applicable": 1}


# === Exécution ============================================================


def executer_appel(appel: dict[str, Any]) -> dict[str, Any]:
    """Exécute un appel selon la définition du plan, retourne métriques + payload."""
    site = appel["site"]
    start_appel = time.perf_counter()
    try:
        if appel["endpoint"] == "daily":
            response = fetch_daily(
                latitude=site["lat"],
                longitude=site["lon"],
                parameters=appel["params"],
                start=appel["start"],
                end=appel["end"],
            )
        elif appel["endpoint"] == "hourly":
            response = fetch_hourly(
                latitude=site["lat"],
                longitude=site["lon"],
                parameters=appel["params"],
                start=appel["start"],
                end=appel["end"],
            )
        else:
            raise ValueError(f"Endpoint inconnu : {appel['endpoint']!r}")
        latence_s = time.perf_counter() - start_appel
    except NasaPowerError as exc:
        latence_s = time.perf_counter() - start_appel
        return {
            "id": appel["id"],
            "label": appel["label"],
            "site": site["code"],
            "endpoint": appel["endpoint"],
            "params": list(appel["params"]),
            "start": str(appel["start"]),
            "end": str(appel["end"]),
            "succes": False,
            "type_erreur": type(exc).__name__,
            "message_erreur": str(exc)[:500],
            "latence_s": round(latence_s, 3),
        }

    payload_dict = response.model_dump()
    payload_taille_o = len(json.dumps(payload_dict).encode("utf-8"))

    metriques: dict[str, Any] = {
        "id": appel["id"],
        "label": appel["label"],
        "site": site["code"],
        "endpoint": appel["endpoint"],
        "params": list(appel["params"]),
        "start": str(appel["start"]),
        "end": str(appel["end"]),
        "succes": True,
        "latence_s": round(latence_s, 3),
        "payload_taille_octets": payload_taille_o,
        "api_version": response.header.api.version,
        "api_name": response.header.api.name,
        "fill_value": response.header.fill_value,
        "time_standard": response.header.time_standard,
        "nb_messages": len(response.messages),
        "messages": response.messages[:5] if response.messages else [],
        "valeurs_par_param": compter_sentinelles_et_valeurs(response),
        "anomalies_ghi_clrsky": detecter_anomalies_ghi_clrsky(response),
    }

    chemin_raw = REPERTOIRE_SORTIE / f"raw_{appel['id']:02d}.json"
    chemin_raw.write_text(json.dumps(payload_dict, indent=2), encoding="utf-8")
    return metriques


def main() -> None:
    REPERTOIRE_SORTIE.mkdir(parents=True, exist_ok=True)
    plan = plan_extraction()
    print(f"Spike 1-2a : {len(plan)} appels NASA POWER à exécuter.")
    print(f"Sortie : {REPERTOIRE_SORTIE.resolve()}")

    metriques_tous: list[dict[str, Any]] = []
    debut_global = time.perf_counter()
    for appel in plan:
        print(f"  [{appel['id']:02d}/{len(plan)}] {appel['label']}...", end=" ", flush=True)
        metriques_appel = executer_appel(appel)
        statut = "OK" if metriques_appel["succes"] else f"ERR ({metriques_appel['type_erreur']})"
        print(f"{statut} en {metriques_appel['latence_s']}s")
        metriques_tous.append(metriques_appel)

    duree_totale = round(time.perf_counter() - debut_global, 1)
    rapport = {
        "duree_totale_s": duree_totale,
        "nb_appels": len(plan),
        "nb_succes": sum(1 for m in metriques_tous if m["succes"]),
        "nb_echecs": sum(1 for m in metriques_tous if not m["succes"]),
        "appels": metriques_tous,
    }

    chemin_metriques = REPERTOIRE_SORTIE / "metrics.json"
    chemin_metriques.write_text(json.dumps(rapport, indent=2), encoding="utf-8")
    print(f"\nDurée totale : {duree_totale}s")
    print(f"Succès : {rapport['nb_succes']}/{rapport['nb_appels']}")
    print(f"Métriques agrégées : {chemin_metriques.resolve()}")


if __name__ == "__main__":
    main()

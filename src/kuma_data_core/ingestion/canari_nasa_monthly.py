"""Canari de dérive NASA POWER mensuel.

Compare la réponse actuelle de NASA POWER au seed versionné, sur toute la
période : la climatologie de long terme n'étant pas révisée au fil de l'eau, un
écart supérieur à ``SEUIL_DERIVE`` signale un retraitement amont.

Codes de sortie et exigence du mode ``live`` : comme ``canari_nasa_daily`` ; le
seed se régénère par ``scripts/preparer_seed_nasa_monthly.py``.
"""

from __future__ import annotations

import httpx

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE
from kuma_data_core.db.seeds.localites_seed_data import LOCALITES_SEED
from kuma_data_core.db.seeds.nasa_power_monthly_seed_data import NASA_MONTHLY_PAYLOADS
from kuma_data_core.exceptions import (
    NasaPowerHttpError,
    NasaPowerRateLimitError,
    NasaPowerTimeoutError,
)
from kuma_data_core.external.nasa_power import fetch_monthly_raw
from kuma_data_core.ingestion._mode import MODE_OFFLINE, mode_ingestion
from kuma_data_core.ingestion.nasa_power_monthly import (
    _cle_ville_offline,
    ecart_relatif_max_nasa_monthly,
)

LOCALITES_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)
LOCALITES_DENSIFICATION: tuple[str, ...] = tuple(
    p["commune_code"] for p in PREFECTURES_GUINEE if p["existante"] is None
)
PARAMETRES_NASA_MONTHLY: tuple[str, ...] = (
    "ALLSKY_SFC_SW_DWN",
    "T2M",
    "RH2M",
    "WS2M",
    "WS10M",
    "ALLSKY_SFC_SW_DIFF",
    "ALLSKY_SFC_SW_DNI",
    "ALLSKY_KT",
    "ALLSKY_SRF_ALB",
)
ANNEE_DEBUT, ANNEE_FIN = 1991, 2020
# Même seuil, pour la même raison, que le canari journalier.
SEUIL_DERIVE: float = 1e-3

_ERREURS_FETCH: tuple[type[Exception], ...] = (
    NasaPowerTimeoutError,
    NasaPowerHttpError,
    NasaPowerRateLimitError,
    httpx.HTTPError,
    RuntimeError,
)


def _coordonnees_tous_points() -> dict[str, tuple[float, float]]:
    """Coordonnées (lat, lon) des points surveillés."""
    index = {e["code"]: e for e in LOCALITES_SEED}
    coords: dict[str, tuple[float, float]] = {
        c: (float(index[c]["latitude"]), float(index[c]["longitude"])) for c in LOCALITES_PILOTES
    }
    for p in PREFECTURES_GUINEE:
        if p["existante"] is None:
            coords[p["commune_code"]] = (float(p["lat"]), float(p["lon"]))
    return coords


def executer_canari(*, httpx_client: httpx.Client | None = None) -> int:
    """Exécute le canari ; rend le code de sortie (0 : pas de dérive, 1 : dérive)."""
    if mode_ingestion() == MODE_OFFLINE:
        raise RuntimeError(
            "Le canari requiert KUMA_INGESTION_MODE=live (compare le fetch reel au seed)."
        )

    derives: list[tuple[str, float]] = []
    blips: list[str] = []
    ecart_global = 0.0

    for code, (lat, lon) in _coordonnees_tous_points().items():
        try:
            live = fetch_monthly_raw(
                latitude=lat,
                longitude=lon,
                parameters=list(PARAMETRES_NASA_MONTHLY),
                annee_debut=ANNEE_DEBUT,
                annee_fin=ANNEE_FIN,
                httpx_client=httpx_client,
            )
        except _ERREURS_FETCH as exc:
            print(
                f"::warning::Canari NASA monthly {code}: fetch indisponible "
                f"({type(exc).__name__}) - blip reseau, ignore."
            )
            blips.append(code)
            continue

        seed = NASA_MONTHLY_PAYLOADS[_cle_ville_offline(lat, lon)]
        ecart = ecart_relatif_max_nasa_monthly(live, seed)
        ecart_global = max(ecart_global, ecart)
        statut = "DERIVE" if ecart > SEUIL_DERIVE else "OK"
        if ecart > SEUIL_DERIVE:
            derives.append((code, ecart))
        print(f"  {code}: ecart_max={ecart:.2e} [{statut}]")

    if derives:
        print(
            f"::error::Derive NASA monthly reelle (seuil {SEUIL_DERIVE}): {derives}. "
            f"Reprocessing / version POWER probable -> re-seed "
            f"(scripts/preparer_seed_nasa_monthly.py)."
        )
        return 1
    if blips:
        print(
            f"::warning::Canari NASA monthly incomplet : {len(blips)} ville(s) injoignable(s) "
            f"{blips} (blip reseau). Aucune derive sur les joignables -> nightly verte."
        )
        return 0
    print(
        f"Canari NASA monthly OK : ecart_max_global={ecart_global:.2e} <= {SEUIL_DERIVE} "
        f"(climato figee, comparaison complete)."
    )
    return 0

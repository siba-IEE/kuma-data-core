"""Canari de dérive PVGIS-SARAH3.

Compare la réponse actuelle de PVGIS au seed versionné. SARAH-3 est un jeu
historique figé : un écart relatif supérieur à ``SEUIL_DERIVE`` (1e-3, au-dessus
du bruit d'arrondi flottant et bien en dessous de l'écart d'un retraitement,
typiquement > 1 %) signale un retraitement par le JRC.

Code de sortie : 1 en cas de dérive (seed à régénérer par
``scripts/preparer_seed_sarah3.py``) ; 0 sinon, y compris quand PVGIS est
injoignable (simple avertissement : un aléa réseau ne doit pas faire échouer le
contrôle nocturne). Exige ``KUMA_INGESTION_MODE=live``.
"""

from __future__ import annotations

import httpx

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE
from kuma_data_core.db.seeds.localites_seed_data import LOCALITES_SEED
from kuma_data_core.db.seeds.sarah3_monthly_seed_data import SARAH3_PAYLOADS
from kuma_data_core.exceptions import (
    PvgisHttpError,
    PvgisRateLimitError,
    PvgisTimeoutError,
)
from kuma_data_core.ingestion._mode import MODE_OFFLINE, mode_ingestion
from kuma_data_core.ingestion.sarah3_monthly import (
    _cle_payload_offline,
    _fetch_sarah3_monthly_raw,
    ecart_relatif_max_sarah3,
)

LOCALITES_1_7A: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)
# Communes chefs-lieux de préfecture qui ne figurent pas dans ``LOCALITES_SEED``.
LOCALITES_DENSIFICATION: tuple[str, ...] = tuple(
    p["commune_code"] for p in PREFECTURES_GUINEE if p["existante"] is None
)
ANNEE_DEBUT, ANNEE_FIN = 2021, 2023
SEUIL_DERIVE: float = 1e-3

# Échecs de requête traités comme des aléas réseau (avertissement, code de sortie 0).
_ERREURS_FETCH: tuple[type[Exception], ...] = (
    PvgisTimeoutError,
    PvgisHttpError,
    PvgisRateLimitError,
    httpx.HTTPError,
    RuntimeError,
)


def _coordonnees_tous_points() -> dict[str, tuple[float, float]]:
    """Coordonnées (lat, lon) des points surveillés."""
    index = {e["code"]: e for e in LOCALITES_SEED}
    coords: dict[str, tuple[float, float]] = {
        c: (float(index[c]["latitude"]), float(index[c]["longitude"])) for c in LOCALITES_1_7A
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
            live = _fetch_sarah3_monthly_raw(
                latitude=lat,
                longitude=lon,
                annee_debut=ANNEE_DEBUT,
                annee_fin=ANNEE_FIN,
                timeout=60.0,
                httpx_client=httpx_client,
            )
        except _ERREURS_FETCH as exc:
            print(
                f"::warning::Canari {code}: fetch PVGIS indisponible "
                f"({type(exc).__name__}) - blip reseau, ignore."
            )
            blips.append(code)
            continue

        seed = SARAH3_PAYLOADS[_cle_payload_offline(lat, lon, ANNEE_DEBUT, ANNEE_FIN)]
        ecart = ecart_relatif_max_sarah3(live, seed)
        ecart_global = max(ecart_global, ecart)
        statut = "DERIVE" if ecart > SEUIL_DERIVE else "OK"
        if ecart > SEUIL_DERIVE:
            derives.append((code, ecart))
        print(f"  {code}: ecart_max={ecart:.2e} [{statut}]")

    if derives:
        print(
            f"::error::Derive SARAH-3 reelle (seuil {SEUIL_DERIVE}): {derives}. "
            f"Reprocessing JRC probable -> re-seed (scripts/preparer_seed_sarah3.py)."
        )
        return 1
    if blips:
        print(
            f"::warning::Canari incomplet : {len(blips)} ville(s) injoignable(s) "
            f"{blips} (blip reseau). Aucune derive sur les villes joignables -> nightly verte."
        )
        return 0
    print(f"Canari OK : ecart_max_global={ecart_global:.2e} <= {SEUIL_DERIVE}")
    return 0

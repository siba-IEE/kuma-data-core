"""Canari de dérive PVGIS-SARAH3.

Compare la donnée PVGIS **live** au seed committé. **Logique d'exit
différenciée** :

- **fetch live indisponible** (blip réseau JRC) → **exit 0** (warning, nightly
  verte) : un aléa réseau ne doit pas rougir la nightly (on fuit la flakiness) ;
- **fetch réussi + écart > ``SEUIL_DERIVE``** (reprocessing JRC réel) → **exit 1**
  (la nightly rougit, ce qui force le **re-seed humain** via
  ``scripts/preparer_seed_sarah3.py``).

SARAH-3 ICDR est un jeu historique figé : un écart non nul sur un fetch réussi
signale un reprocessing amont. Seuil ``1e-3`` (0,1 % relatif) : absorbe le bruit
de représentation flottante, capte un reprocessing (décalage typiquement > 1 %).

Requiert le mode ``live`` (le caller / step CI pose ``KUMA_INGESTION_MODE=live``) :
en offline, ``_fetch`` renverrait le seed et le canari serait aveugle → garde.
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
# Densification : 28 nouvelles communes (seedees offline en plus des pilotes).
LOCALITES_DENSIFICATION: tuple[str, ...] = tuple(
    p["commune_code"] for p in PREFECTURES_GUINEE if p["existante"] is None
)
ANNEE_DEBUT, ANNEE_FIN = 2021, 2023
SEUIL_DERIVE: float = 1e-3

# Échecs de fetch traités comme blips réseau (-> exit 0, warning).
_ERREURS_FETCH: tuple[type[Exception], ...] = (
    PvgisTimeoutError,
    PvgisHttpError,
    PvgisRateLimitError,
    httpx.HTTPError,
    RuntimeError,
)


def _coordonnees_tous_points() -> dict[str, tuple[float, float]]:
    """34 points : 6 pilotes (``LOCALITES_SEED``) + 28 communes (densification)."""
    index = {e["code"]: e for e in LOCALITES_SEED}
    coords: dict[str, tuple[float, float]] = {
        c: (float(index[c]["latitude"]), float(index[c]["longitude"])) for c in LOCALITES_1_7A
    }
    for p in PREFECTURES_GUINEE:
        if p["existante"] is None:
            coords[p["commune_code"]] = (float(p["lat"]), float(p["lon"]))
    return coords


def executer_canari(*, httpx_client: httpx.Client | None = None) -> int:
    """Exécute le canari. Retourne le code de sortie (0 OK/blip, 1 dérive réelle)."""
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

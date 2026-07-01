"""Canari de dérive NASA POWER daily - maturation-aware.

Compare la donnée NASA POWER **live** au seed committé, pour détecter une dérive
amont (reprocessing / changement de version POWER) que l'offline masquerait sinon.

**Spécificité NASA (vs canari SARAH-3)** : NASA POWER NRT **mûrit** (la queue
récente change légitimement), contrairement à SARAH-3 ICDR figé. Le canari ne
compare donc que la **fenêtre stable** (dates mûries à la capture du seed,
``<= DERNIERE_DATE_STABLE`` = capture moins 12 mois conservateur), excluant la
queue maturante. Une fine bande près de la frontière reste non surveillée (choix
acté) : c'est l'historique profond qui révèle un changement de version POWER.

Logique d'exit différenciée (idem SARAH-3) :

- **blip réseau** (fetch indisponible) -> **exit 0** (warning, nightly verte) ;
- **dérive réelle** (fetch OK + écart > seuil dans l'historique mûri) -> **exit 1**
  -> re-seed humain (``scripts/preparer_seed_nasa_daily.py``).

Requiert ``KUMA_INGESTION_MODE=live`` (en offline, ``fetch_daily_raw`` renverrait
le seed et le canari serait aveugle -> garde).
"""

from __future__ import annotations

from datetime import date

import httpx

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE
from kuma_data_core.db.seeds.localites_seed_data import LOCALITES_SEED
from kuma_data_core.db.seeds.nasa_power_daily_seed_data import NASA_DAILY_PAYLOADS
from kuma_data_core.exceptions import (
    NasaPowerHttpError,
    NasaPowerRateLimitError,
    NasaPowerTimeoutError,
)
from kuma_data_core.external.nasa_power import fetch_daily_raw
from kuma_data_core.ingestion._mode import MODE_OFFLINE, mode_ingestion
from kuma_data_core.ingestion.nasa_power_daily import (
    _cle_ville_offline,
    ecart_relatif_max_nasa_daily,
)

LOCALITES_DAILY: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)
# Densification : les 28 nouvelles communes chef-lieu, seedees
# offline en plus des 6 pilotes. Le canari surveille desormais les 34 points.
LOCALITES_DAILY_DENSIFICATION: tuple[str, ...] = tuple(
    p["commune_code"] for p in PREFECTURES_GUINEE if p["existante"] is None
)
PARAMETRES_NASA_DAILY: tuple[str, ...] = (
    "ALLSKY_SFC_SW_DWN",
    "ALLSKY_SFC_SW_DNI",
    "ALLSKY_SFC_SW_DIFF",
    "T2M",
    "RH2M",
    "ALLSKY_KT",
    "WS2M",
    "WS10M",
    "ALLSKY_SRF_ALB",
)
ANNEE_DEBUT, ANNEE_FIN = 2021, 2025

# Date de capture du seed (preparer_seed_nasa_daily.py) ; mettre a jour au re-seed.
SEED_CAPTURE: date = date(2026, 6, 19)
# Fenetre stable = dates muries a la capture (capture moins 12 mois ; latence
# reelle 10 mois, marge conservatrice). La queue (> cette date) est exclue : sa
# derive est de la maturation normale, pas un reprocessing.
DERNIERE_DATE_STABLE: date = SEED_CAPTURE.replace(year=SEED_CAPTURE.year - 1)
# Seuil d'ecart relatif : 1e-3 absorbe le bruit flottant, capte un reprocessing
# (decalage typiquement > 1 %). Coherent avec le canari SARAH-3.
SEUIL_DERIVE: float = 1e-3

_ERREURS_FETCH: tuple[type[Exception], ...] = (
    NasaPowerTimeoutError,
    NasaPowerHttpError,
    NasaPowerRateLimitError,
    httpx.HTTPError,
    RuntimeError,
)


def _coordonnees_tous_points() -> dict[str, tuple[float, float]]:
    """Coordonnees (lat, lon) des 34 points surveilles.

    6 pilotes (``LOCALITES_SEED``) + 28 nouvelles communes (seed
    densification). Memes coordonnees que les cles offline du seed daily.
    """
    index = {e["code"]: e for e in LOCALITES_SEED}
    coords: dict[str, tuple[float, float]] = {
        c: (float(index[c]["latitude"]), float(index[c]["longitude"])) for c in LOCALITES_DAILY
    }
    for p in PREFECTURES_GUINEE:
        if p["existante"] is None:
            coords[p["commune_code"]] = (float(p["lat"]), float(p["lon"]))
    return coords


def executer_canari(*, httpx_client: httpx.Client | None = None) -> int:
    """Exécute le canari NASA daily. Retourne le code de sortie (0 OK/blip, 1 dérive)."""
    if mode_ingestion() == MODE_OFFLINE:
        raise RuntimeError(
            "Le canari requiert KUMA_INGESTION_MODE=live (compare le fetch reel au seed)."
        )

    derives: list[tuple[str, float]] = []
    blips: list[str] = []
    ecart_global = 0.0

    for code, (lat, lon) in _coordonnees_tous_points().items():
        try:
            live = fetch_daily_raw(
                latitude=lat,
                longitude=lon,
                parameters=list(PARAMETRES_NASA_DAILY),
                start=date(ANNEE_DEBUT, 1, 1),
                end=date(ANNEE_FIN, 12, 31),
                httpx_client=httpx_client,
            )
        except _ERREURS_FETCH as exc:
            print(
                f"::warning::Canari NASA {code}: fetch indisponible "
                f"({type(exc).__name__}) - blip reseau, ignore."
            )
            blips.append(code)
            continue

        seed = NASA_DAILY_PAYLOADS[_cle_ville_offline(lat, lon)]
        ecart = ecart_relatif_max_nasa_daily(live, seed, derniere_date_stable=DERNIERE_DATE_STABLE)
        ecart_global = max(ecart_global, ecart)
        statut = "DERIVE" if ecart > SEUIL_DERIVE else "OK"
        if ecart > SEUIL_DERIVE:
            derives.append((code, ecart))
        print(f"  {code}: ecart_max_stable={ecart:.2e} [{statut}]")

    if derives:
        print(
            f"::error::Derive NASA daily reelle (seuil {SEUIL_DERIVE}, fenetre "
            f"<= {DERNIERE_DATE_STABLE}): {derives}. Reprocessing / version POWER "
            f"probable -> re-seed (scripts/preparer_seed_nasa_daily.py)."
        )
        return 1
    if blips:
        print(
            f"::warning::Canari NASA incomplet : {len(blips)} ville(s) injoignable(s) "
            f"{blips} (blip reseau). Aucune derive sur les joignables -> nightly verte."
        )
        return 0
    print(
        f"Canari NASA daily OK : ecart_max_global={ecart_global:.2e} <= {SEUIL_DERIVE} "
        f"(fenetre stable <= {DERNIERE_DATE_STABLE})"
    )
    return 0

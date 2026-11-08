"""Canari de dérive NASA POWER monthly - climato figée.

Compare la donnée NASA POWER monthly **live** au seed committé, pour détecter une
dérive amont (reprocessing / changement de version POWER) que l'offline
masquerait sinon.

**Spécificité (vs canari daily)** : la climato long-terme est **figée** (ne mûrit
pas, contrairement au daily NRT). Donc **pas de fenêtre maturation** : on compare
**tout** l'historique. Tout écart non nul (> seuil) signale un reprocessing
-> exit 1, re-seed (gel/compare, comme ``canari_sarah3``).

Logique d'exit différenciée (idem daily / SARAH-3) :

- **blip réseau** (fetch indisponible) -> **exit 0** (warning, nightly verte) ;
- **dérive réelle** (fetch OK + écart > seuil) -> **exit 1** -> re-seed
  (``scripts/preparer_seed_nasa_monthly.py``).

Requiert ``KUMA_INGESTION_MODE=live`` (en offline, ``fetch_monthly_raw``
renverrait le seed et le canari serait aveugle -> garde).
"""

from __future__ import annotations

import httpx

from kuma_data_core.db.seeds.nasa_power_monthly_seed_data import NASA_MONTHLY_PAYLOADS
from kuma_data_core.exceptions import (
    NasaPowerHttpError,
    NasaPowerRateLimitError,
    NasaPowerTimeoutError,
)
from kuma_data_core.external.nasa_power import fetch_monthly_raw
from kuma_data_core.ingestion._canari import ERREURS_RESEAU, MessagesCanari
from kuma_data_core.ingestion._canari import executer_canari as _executer_canari
from kuma_data_core.ingestion.nasa_power_monthly import (
    _cle_ville_offline,
    ecart_relatif_max_nasa_monthly,
)

# 34 points surveilles : 6 pilotes + 28 nouvelles communes (memes que le seed).
LOCALITES_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
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
# Seuil d'ecart relatif : 1e-3 absorbe le bruit flottant, capte un reprocessing.
# Coherent avec les canaris daily / SARAH-3.
SEUIL_DERIVE: float = 1e-3

_ERREURS_FETCH: tuple[type[Exception], ...] = (
    NasaPowerTimeoutError,
    NasaPowerHttpError,
    NasaPowerRateLimitError,
    *ERREURS_RESEAU,
)

_MESSAGES = MessagesCanari(
    blip=(
        "::warning::Canari NASA monthly {code}: fetch indisponible ({erreur}) "
        "- blip reseau, ignore."
    ),
    point="  {code}: ecart_max={ecart:.2e} [{statut}]",
    derive=(
        "::error::Derive NASA monthly reelle (seuil {seuil}): {derives}. "
        "Reprocessing / version POWER probable -> re-seed "
        "(scripts/preparer_seed_nasa_monthly.py)."
    ),
    incomplet=(
        "::warning::Canari NASA monthly incomplet : {nb_blips} ville(s) injoignable(s) "
        "{blips} (blip reseau). Aucune derive sur les joignables -> nightly verte."
    ),
    ok=(
        "Canari NASA monthly OK : ecart_max_global={ecart_global:.2e} <= {seuil} "
        "(climato figee, comparaison complete)."
    ),
)


def executer_canari(*, httpx_client: httpx.Client | None = None) -> int:
    """Exécute le canari NASA monthly. Retourne le code de sortie (0 OK/blip, 1 dérive)."""
    return _executer_canari(
        pilotes=LOCALITES_PILOTES,
        fetch=lambda lat, lon: fetch_monthly_raw(
            latitude=lat,
            longitude=lon,
            parameters=list(PARAMETRES_NASA_MONTHLY),
            annee_debut=ANNEE_DEBUT,
            annee_fin=ANNEE_FIN,
            httpx_client=httpx_client,
        ),
        seed=lambda lat, lon: NASA_MONTHLY_PAYLOADS[_cle_ville_offline(lat, lon)],
        ecart=ecart_relatif_max_nasa_monthly,
        erreurs_fetch=_ERREURS_FETCH,
        seuil=SEUIL_DERIVE,
        messages=_MESSAGES,
    )

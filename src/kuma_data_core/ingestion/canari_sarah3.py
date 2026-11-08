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

from kuma_data_core.db.seeds.sarah3_monthly_seed_data import SARAH3_PAYLOADS
from kuma_data_core.exceptions import (
    PvgisHttpError,
    PvgisRateLimitError,
    PvgisTimeoutError,
)
from kuma_data_core.ingestion._canari import ERREURS_RESEAU, MessagesCanari
from kuma_data_core.ingestion._canari import executer_canari as _executer_canari
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
# Le canari surveille aussi les 28 communes densifiees (COMMUNES_DENSIFICATION).
ANNEE_DEBUT, ANNEE_FIN = 2021, 2023
SEUIL_DERIVE: float = 1e-3

# Échecs de fetch traités comme blips réseau (-> exit 0, warning).
_ERREURS_FETCH: tuple[type[Exception], ...] = (
    PvgisTimeoutError,
    PvgisHttpError,
    PvgisRateLimitError,
    *ERREURS_RESEAU,
)

_MESSAGES = MessagesCanari(
    blip="::warning::Canari {code}: fetch PVGIS indisponible ({erreur}) - blip reseau, ignore.",
    point="  {code}: ecart_max={ecart:.2e} [{statut}]",
    derive=(
        "::error::Derive SARAH-3 reelle (seuil {seuil}): {derives}. "
        "Reprocessing JRC probable -> re-seed (scripts/preparer_seed_sarah3.py)."
    ),
    incomplet=(
        "::warning::Canari incomplet : {nb_blips} ville(s) injoignable(s) {blips} "
        "(blip reseau). Aucune derive sur les villes joignables -> nightly verte."
    ),
    ok="Canari OK : ecart_max_global={ecart_global:.2e} <= {seuil}",
)


def executer_canari(*, httpx_client: httpx.Client | None = None) -> int:
    """Exécute le canari. Retourne le code de sortie (0 OK/blip, 1 dérive réelle)."""
    return _executer_canari(
        pilotes=LOCALITES_1_7A,
        fetch=lambda lat, lon: _fetch_sarah3_monthly_raw(
            latitude=lat,
            longitude=lon,
            annee_debut=ANNEE_DEBUT,
            annee_fin=ANNEE_FIN,
            timeout=60.0,
            httpx_client=httpx_client,
        ),
        seed=lambda lat, lon: SARAH3_PAYLOADS[
            _cle_payload_offline(lat, lon, ANNEE_DEBUT, ANNEE_FIN)
        ],
        ecart=ecart_relatif_max_sarah3,
        erreurs_fetch=_ERREURS_FETCH,
        seuil=SEUIL_DERIVE,
        messages=_MESSAGES,
    )

"""CLI du canari de dérive NASA POWER daily - nightly.

Wrapper mince : la logique vit dans
``kuma_data_core.ingestion.canari_nasa_daily.executer_canari`` (testable,
maturation-aware). Exit 1 sur dérive réelle dans l'historique mûri (reprocessing
-> re-seed via ``scripts/preparer_seed_nasa_daily.py``) ; blip réseau -> exit 0
(nightly verte).

**Doit tourner en mode LIVE** (le step CI pose ``KUMA_INGESTION_MODE=live`` ;
``executer_canari`` lève sinon). Hors CI :
``KUMA_INGESTION_MODE=live uv run --group dev python scripts/canari_nasa_daily.py``.
"""

from __future__ import annotations

import sys

from kuma_data_core.ingestion.canari_nasa_daily import executer_canari

if __name__ == "__main__":
    print("=== Canari de dérive NASA POWER daily (D-40 / D-74 lot 2) ===")
    sys.exit(executer_canari())

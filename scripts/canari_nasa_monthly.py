"""CLI du canari de dérive NASA POWER monthly - nightly.

Wrapper mince : la logique vit dans
``kuma_data_core.ingestion.canari_nasa_monthly.executer_canari`` (climato figée,
comparaison complète, testable). Exit 1 sur dérive réelle (reprocessing -> re-seed
via ``scripts/preparer_seed_nasa_monthly.py``) ; blip réseau -> exit 0
(nightly verte).

**Doit tourner en mode LIVE** (le step CI pose ``KUMA_INGESTION_MODE=live`` ;
``executer_canari`` lève sinon). Hors CI :
``KUMA_INGESTION_MODE=live uv run --group dev python scripts/canari_nasa_monthly.py``.
"""

from __future__ import annotations

import sys

from kuma_data_core.ingestion.canari_nasa_monthly import executer_canari

if __name__ == "__main__":
    print("=== Canari de dérive NASA POWER monthly (D-40 lot 3) ===")
    sys.exit(executer_canari())

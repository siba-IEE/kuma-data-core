"""CLI du canari de dérive PVGIS-SARAH3 - nightly.

Wrapper mince : la logique vit dans
``kuma_data_core.ingestion.canari_sarah3.executer_canari`` (testable). Sort en
**exit 1** uniquement sur **dérive réelle** (fetch réussi + écart > seuil =
reprocessing JRC → re-seed via ``scripts/preparer_seed_sarah3.py``) ; un **blip
réseau** (fetch indisponible) sort en **exit 0** (warning, nightly verte).

**Doit tourner en mode LIVE** (le step CI pose ``KUMA_INGESTION_MODE=live`` ;
``executer_canari`` lève sinon). Hors CI :
``KUMA_INGESTION_MODE=live uv run --group dev python scripts/canari_sarah3.py``.
"""

from __future__ import annotations

import sys

from kuma_data_core.ingestion.canari_sarah3 import executer_canari

if __name__ == "__main__":
    print("=== Canari de dérive PVGIS-SARAH3 (D-40 lot 1) ===")
    sys.exit(executer_canari())

"""Tests unitaires de l'agregation 1-min -> horaire du seed ESMAP/WAPP.

Verrouille les regles de ``scripts/preparer_seed_esmap_wapp.py::agreger_horaire`` :

- **complétude** : heure emise si >= 48/60 minutes valides, exclue sinon ;
- **clamp nuit** : GHI negatif (offset thermopile) -> 0 avant moyenne ;
- **hour-beginning** : minutes [H:00, H+1:00) -> label H:00 UTC.

Le script n'est pas un package importable -> chargement par ``importlib``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd  # type: ignore[import-untyped]
import pytest

pytestmark = pytest.mark.unit

_CHEMIN_SCRIPT = Path(__file__).parents[3] / "scripts" / "preparer_seed_esmap_wapp.py"


def _charger_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("prep_esmap_wapp", _CHEMIN_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _minutes(debut_iso: str, n: int, ghi: float | None) -> pd.DataFrame:
    """n minutes consecutives a partir de ``debut_iso`` (UTC), GHI constant (ou NaN)."""
    base = pd.Timestamp(debut_iso, tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": [base + pd.Timedelta(minutes=i) for i in range(n)],
            "valeur": [ghi for _ in range(n)],
        }
    )


def test_regles_agregation() -> None:
    prep = _charger_module()
    df = pd.concat(
        [
            _minutes("2021-06-01T12:00:00", 60, 500.0),  # heure pleine -> emise (500)
            _minutes("2021-06-01T13:00:00", 50, 600.0),  # 50/60 valides -> emise (600)
            pd.concat(  # 13:00 complete a 60 mais 10 NaN -> 50 valides (idempotent au-dessus)
                [_minutes("2021-06-01T14:00:00", 40, 700.0)]  # 40/60 -> EXCLUE (< 48)
            ),
            _minutes("2021-06-01T00:00:00", 60, -3.0),  # nuit : clamp -> 0
        ],
        ignore_index=True,
    )

    horaire, stats = prep.agreger_horaire(df)
    par_instant = {r["instant_mesure"]: r["valeur"] for r in horaire}

    # Complétude : 12:00, 13:00 (>=48) et 00:00 émises ; 14:00 (40 min) exclue.
    assert "2021-06-01T12:00:00+00:00" in par_instant
    assert "2021-06-01T13:00:00+00:00" in par_instant
    assert "2021-06-01T14:00:00+00:00" not in par_instant
    assert stats["heures_incompletes_exclues"] == 1

    # Valeurs + hour-beginning (label = début d'heure UTC).
    assert par_instant["2021-06-01T12:00:00+00:00"] == 500.0
    assert par_instant["2021-06-01T13:00:00+00:00"] == 600.0

    # Clamp nuit : GHI négatif -> 0 avant moyenne.
    assert par_instant["2021-06-01T00:00:00+00:00"] == 0.0

    # Tri chronologique de la sortie.
    instants = [r["instant_mesure"] for r in horaire]
    assert instants == sorted(instants)


def test_heure_sous_seuil_strict() -> None:
    """47/60 minutes -> exclue ; 48/60 -> émise (frontiere du seuil 80 %)."""
    prep = _charger_module()
    df47 = _minutes("2022-01-01T10:00:00", 47, 400.0)
    df48 = _minutes("2022-01-01T11:00:00", 48, 400.0)
    horaire, stats = prep.agreger_horaire(pd.concat([df47, df48], ignore_index=True))
    instants = {r["instant_mesure"] for r in horaire}
    assert "2022-01-01T11:00:00+00:00" in instants  # 48 -> émise
    assert "2022-01-01T10:00:00+00:00" not in instants  # 47 -> exclue
    assert stats["heures_emises"] == 1
    assert stats["heures_incompletes_exclues"] == 1

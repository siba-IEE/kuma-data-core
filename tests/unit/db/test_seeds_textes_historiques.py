"""Textes historiques des seeds importes par des migrations immuables (085, 101).

Les notes des localites de la migration 085 et la provenance du referentiel de
calage de la migration 101 portent des codes internes que les migrations 128 et
129 retirent des textes publies, sous garde md5 du texte de depart exact. Ces
seeds ne doivent donc plus changer : une base neuve reconstruite de 001 a la tete
doit passer par le meme etat. Les empreintes ci-dessous figent leur sortie.
"""

from __future__ import annotations

import hashlib

import pytest

from kuma_data_core.db.seeds.localites_prefectures_seed_data import (
    NOUVELLES_COMMUNES,
    PREFECTURE_NODES,
)
from kuma_data_core.db.seeds.referentiels_calage_101_seed_data import (
    REFERENTIELS_CALAGE_101_SEED,
)

pytestmark = pytest.mark.unit


def _md5(textes: list[str]) -> str:
    return hashlib.md5("\n".join(textes).encode("utf-8")).hexdigest()


def test_notes_prefectures_migration_085_figees() -> None:
    notes = [str(n["notes"]) for n in PREFECTURE_NODES]
    assert len(notes) == 33
    assert _md5(notes) == "1f9d0f3500c6cea888475066bb1c65f8"


def test_notes_communes_migration_085_figees() -> None:
    notes = [str(n["notes"]) for n in NOUVELLES_COMMUNES]
    assert len(notes) == 28
    assert _md5(notes) == "b41da9224a38272c94f7c706e15cab0b"


def test_provenance_calage_migration_101_figee() -> None:
    provenances = [str(r["provenance"]) for r in REFERENTIELS_CALAGE_101_SEED]
    assert len(provenances) == 3
    assert _md5(provenances) == "1ed495aa4cc6f19617391c885c0103bb"

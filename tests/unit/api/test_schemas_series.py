"""Le schéma de réponse n'est pas plus étroit que ce que la table admet."""

from __future__ import annotations

import re

import annotated_types
import pytest

from kuma_data_core.api.v1.schemas.series import MesureMensuelle
from kuma_data_core.db.models.mesures_ressource_mensuelles import MesureRessourceMensuelle

pytestmark = pytest.mark.unit


def test_bornes_annee_egales_a_la_contrainte_de_la_table() -> None:
    contrainte = next(
        c
        for c in MesureRessourceMensuelle.__table__.constraints
        if c.name == "ck_mesures_ressource_mensuelles_annee_valide"
    )
    minimum, maximum = (int(a) for a in re.findall(r"\d{4}", str(contrainte.sqltext)))
    metadonnees = MesureMensuelle.model_fields["annee"].metadata
    assert next(m.ge for m in metadonnees if isinstance(m, annotated_types.Ge)) == minimum
    assert next(m.le for m in metadonnees if isinstance(m, annotated_types.Le)) == maximum

"""Donnée de seed de l'unité ``kwh_par_kwc_periode`` (migration 100).

Résorption de la dette D-63 (option a, arbitrage du 2026-07-04) : les
valeurs de ``productible_specifique_theorique`` sont des totaux par
période (mensuelle ou annuelle) alors que l'unité déclarée était
``kwh_par_kwc_jour``. Plutôt que recalculer les valeurs (option b), le
référentiel bascule sur une unité au libellé exact : le total sur la
période de la mesure.

Pattern reproduit de ``unites_complementaires_009_seed_data.py`` :
dict prêt pour ``op.bulk_insert``, ``cree_par``/``modifie_par`` NULL,
``actif``/``cree_le``/``modifie_le`` aux ``server_default``.

Dimensionnellement, kWh/kWc = heure (énergie / puissance) : mêmes
conventions SI que ``heure_equivalente_pleine`` (facteur 3600 s).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

D = Decimal

UNITES_PSP_PERIODE_100_SEED: list[dict[str, Any]] = [
    {
        "code": "kwh_par_kwc_periode",
        "libelle": "kilowattheure par kilowatt-crête sur la période",
        "symbole": "kWh/kWc",
        "grandeur": "productible_specifique_periode",
        "systeme": "composee_mixte",
        "est_unite_de_base": False,
        "facteur_conversion_si": D("3600"),
        "decalage_conversion_si": D("0"),
        "code_unite_si": "seconde",
        "note_methodologique": (
            "Productible spécifique d'un système photovoltaïque exprimé en "
            "total sur la période de la mesure (mensuelle ou annuelle), sans "
            "normalisation journalière. Unité introduite pour corriger le "
            "drift d'étiquette de productible_specifique_theorique (les "
            "valeurs stockées sont des totaux par période, pas des moyennes "
            "journalières). Dimensionnellement identique à l'heure "
            "(facteur SI = 3600), comme l'heure équivalente pleine."
        ),
        "references_normatives": [
            "IEC 61724-1 (Photovoltaic system performance - Part 1 : Monitoring)",
            "IEA PVPS Task 13",
        ],
    },
]

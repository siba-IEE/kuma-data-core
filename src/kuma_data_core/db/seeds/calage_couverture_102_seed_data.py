"""Domaine de couverture initial du calage GHI de Kankan.

Les 5 communes points d'ingestion des préfectures de la région administrative
de Kankan (Kankan, Kérouané, Kouroussa, Mandiana, Siguiri).

Justification : même régime climatique soudanien que la station de référence,
portée régionale du biais aérosol, et précédent de transport déclaré dans
l'étude publique de Tokounou (76 km, cellule de Kérouané).
"""

from __future__ import annotations

REFERENTIEL_CODE_102 = "gin_kankan_ghi_calage_saisonnier"

JUSTIFICATION_102 = (
    "Domaine initial arrete par le fondateur le 2026-07-20 : region "
    "administrative de Kankan. Meme regime climatique soudanien que la "
    "station de reference, portee regionale du biais aerosol (guide 8), "
    "precedent de transport declare de l'etude publique de Tokounou "
    "(76 km de la station, cellule de Kerouane). Extension par la "
    "recherche : qualification inter-source, campagnes de mesure, "
    "leave-one-out a la deuxieme station sol."
)

LOCALITES_COUVERTES_102: list[str] = [
    "gin_kankan",
    "gin_kerouane",
    "gin_kouroussa",
    "gin_mandiana",
    "gin_siguiri",
]

"""Seed du domaine de couverture initial du calage GHI Kankan (migration 102).

Domaine initial arrete par le fondateur le 2026-07-20 : la region
administrative de Kankan, soit les 5 communes points d'ingestion des
prefectures (Kankan, Kerouane, Kouroussa, Mandiana, Siguiri).

Justification : meme regime climatique soudanien que la station de
reference, portee regionale du biais aerosol (guide 8), precedent de
transport declare de l'etude publique de Tokounou (76 km, cellule de
Kerouane). L'extension du domaine passe par la recherche
(qualification par coherence inter-source, campagnes de mesure,
leave-one-out quand une deuxieme station sol existera), une edition
a la fois.
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

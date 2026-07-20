"""Seed du référentiel de calage GHI de Kankan (migration 101).

Biais relatif moyen satellite moins sol par saison, mesuré au pixel
co-localisé de la station ESMAP/WAPP de Kankan (série sol
``gin_kankan_ghi_esmap_wapp_2021_2023``, confiance A, 17 520 h) sur
le recouvrement 2021-10 vers 2023-10.

Source des chiffres : note ``docs/methodologie/
calage-ghi-kankan-terrain-lite.md`` (script reproductible
``scripts/analyse_calage_ghi_kankan.py``) et recalcul mensuel local
de l'étude publique de Tokounou (2026-07-17). Les biais retenus sont
ceux consommés par la chaîne de dimensionnement mini-réseau
(harmattan +4,4 %, mousson +1,5 %, intersaison +1,9 % ; facteurs
k = 1/(1+b) : 0,9579 / 0,9852 / 0,9814).

Le ``localite_id`` est résolu par la migration (sous-requête sur le
code ``gin_kankan``), pas seedé en dur.
"""

from __future__ import annotations

_PROVENANCE = (
    "Biais satellite moins sol mesure au pixel co-localise de la "
    "station ESMAP/WAPP de Kankan (serie sol "
    "gin_kankan_ghi_esmap_wapp_2021_2023, confiance A, 17 520 h, "
    "recouvrement 2021-10 a 2023-10). Note "
    "docs/methodologie/calage-ghi-kankan-terrain-lite.md, script "
    "reproductible scripts/analyse_calage_ghi_kankan.py, biais "
    "saisonniers du recalcul mensuel de l'etude Tokounou (2026-07-17)."
)

_PORTEE = (
    "Transport valable en premiere approche dans le meme regime "
    "climatique soudanien que la station (portee regionale du biais "
    "aerosol, guide 8). L'application a un site distant est une "
    "hypothese a statut : afficher la distance a la station et le "
    "geste de levee (campagne de mesure au site)."
)

REFERENTIELS_CALAGE_101_SEED: list[dict[str, object]] = [
    {
        "code": "gin_kankan_ghi_calage_saisonnier",
        "grandeur_code": "ghi",
        "saison": "harmattan",
        "mois": [11, 12, 1, 2, 3],
        "biais": "0.044",
        "provenance": _PROVENANCE,
        "portee": _PORTEE,
        "version": "v1",
    },
    {
        "code": "gin_kankan_ghi_calage_saisonnier",
        "grandeur_code": "ghi",
        "saison": "mousson",
        "mois": [6, 7, 8, 9],
        "biais": "0.015",
        "provenance": _PROVENANCE,
        "portee": _PORTEE,
        "version": "v1",
    },
    {
        "code": "gin_kankan_ghi_calage_saisonnier",
        "grandeur_code": "ghi",
        "saison": "intersaison",
        "mois": [4, 5, 10],
        "biais": "0.019",
        "provenance": _PROVENANCE,
        "portee": _PORTEE,
        "version": "v1",
    },
]

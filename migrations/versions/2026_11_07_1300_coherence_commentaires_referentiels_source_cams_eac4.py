"""coherence_commentaires_referentiels_source_cams_eac4

Revision ID: 125
Revises: 124
Create Date: 2026-11-07 13:00:00.000000+00:00

Migration de coherence editoriale, sans DDL de structure ni donnee mesuree :

1. **Commentaires de table** ``unites`` et ``grandeurs_referentiel`` : les textes
   poses par les migrations 002 et 015 annoncaient des
   decomptes figes (« 153 unites sur 30 grandeurs », « 20 entrees ») devenus faux
   et du jargon de chantier. Ces tables sont publiees telles quelles dans
   l'edition publique (manifeste de publication). Nouveaux textes descriptifs,
   sans decompte (ils ne peuvent plus vieillir), sans jargon. L'ancienne phrase
   sur le lieu de stockage (« determine par series_metadonnees.methode_collecte »)
   est retiree : le routage reel passe par la source et la granularite de la
   serie (``resolve_table_from_series_metadata``). Les modeles ORM portent les
   memes textes (``alembic check``).
2. **Source ``cams_eac4``** (migration 081) : ``notes`` et ``metadonnees``
   ne decrivaient que les PM (2021-01 -> 2025-08). Depuis les migrations 123-124
   la source porte aussi l'epaisseur optique des aerosols a 550 nm (totale et
   poussieres) et l'ozone de surface (2004-02-01 -> 2025-12-31). ``notes``
   (publique) est reecrite sans jargon et sans periode figee (la periode est
   portee par chaque serie) ; ``metadonnees`` est completee par fusion JSONB
   (cles ``variables_ingerees``, ``conversion``, ``agregation_kuma``,
   ``periode_reelle`` ; types inchanges).

Gardes : chaque UPDATE verifie l'etat de depart exact (texte ou JSON) et
touche exactement 1 ligne ; le downgrade restaure les valeurs d'origine a
l'identique. Trigger d'audit : ``kuma_log_audit()`` journalise l'UPDATE
``sources`` ; ``modifie_le`` non touche (precedent migration 100).
Aucun reseau.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "125"
down_revision: str | Sequence[str] | None = "124"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === 1. Commentaires de table ==============================================

_COMMENTAIRE_UNITES_ANCIEN = (
    "Référentiel des unités de mesure de Kuma Data Core. "
    "153 unités sur 30 grandeurs, validées contre 20+ organismes "
    "normatifs internationaux (BIPM, AIE, ONU, NIST, IUPAC, IEC, "
    "DIN, ISO, IPCC, IRENA, UNECE, etc.)."
)
_COMMENTAIRE_UNITES_NOUVEAU = (
    "Référentiel des unités de mesure de Kuma Data Core. Chaque unité porte "
    "son symbole, la grandeur qu'elle mesure, son système, sa conversion vers "
    "l'unité de référence de cette grandeur (facteur et décalage) et ses "
    "références normatives (BIPM, ISO, IEC, NIST, etc.)."
)

_COMMENTAIRE_GRANDEURS_ANCIEN = (
    "Referentiel des grandeurs Kuma. 15 grandeurs traduites (1-1C) + "
    "5 grandeurs brutes ingerees (1-2b) = 20 entrees post-1-2b. "
    "Le lieu de stockage physique d'une F1 stockee est determine par "
    "series_metadonnees.methode_collecte (cadrage Q7 v1.3)."
)
_COMMENTAIRE_GRANDEURS_NOUVEAU = (
    "Referentiel des grandeurs de Kuma Data Core : une entree par grandeur, "
    "identifiee par un code stable, avec son libelle, son unite, sa famille "
    "(F1 ou F2) et sa strategie de calcul. Cite par series_metadonnees et "
    "grandeurs_metier via la cle naturelle code."
)


# === 2. Source cams_eac4 ===================================================

_SOURCE_CODE = "cams_eac4"

_NOTES_ANCIENNES = (
    "Reanalyse de composition atmospherique EAC4 (ECMWF Atmospheric "
    "Composition Reanalysis 4, CAMS), servie par l'ADS Copernicus. Fournit "
    "PM2.5 et PM10 de surface (kg/m3 natif, converti ug/m3) au pas 3-horaire, "
    "agreges en moyenne journaliere par Kuma. Entree particules du modele de "
    "salissure HSU (proxy taux_salissure_proxy, Vague 5 Lot C) : le HSU "
    "consomme les PM, pas l'AOD. Confiance B derivee (modele satellitaire, pas "
    "mesure directe -> R3 ne donne pas A). Grille grossiere 0,75 deg (caveat "
    "L-SOIL-4). Couverture reelle 2021-01-01 a 2025-08-31 (latence de reanalyse "
    "10 mois). Licence Copernicus (CC-BY) ; attribution : Generated using "
    "Copernicus Atmosphere Monitoring Service Information 2026. DOI dataset et "
    "annee de publication non confirmes (non inventes) ; reference methodologique "
    "Inness et al. 2019 (doi:10.5194/acp-19-3515-2019)."
)
_NOTES_NOUVELLES = (
    "Réanalyse de composition atmosphérique EAC4 (ECMWF Atmospheric Composition "
    "Reanalysis 4) du service Copernicus de surveillance de l'atmosphère (CAMS), "
    "servie par l'Atmosphere Data Store (ADS). Grille de 0,75°, pas de 3 heures ; "
    "Kuma retient le point de grille le plus proche de chaque localité. Variables "
    "ingérées : particules PM2.5 et PM10 de surface (kg/m³ natif, converties en "
    "µg/m³), épaisseur optique des aérosols à 550 nm, totale et part due aux "
    "poussières (sans unité), et ozone au niveau le plus bas du modèle (rapport "
    "de mélange massique natif, converti en fraction molaire, ppb). Valeurs "
    "journalières : moyenne des pas de 3 heures du jour ; l'ozone diurne est la "
    "moyenne des pas de 09 h, 12 h et 15 h UTC. Les PM alimentent le modèle de "
    "salissure HSU, qui consomme les particules de surface et non l'épaisseur "
    "optique. Confiance B : donnée de modèle, pas une mesure directe. Grille "
    "grossière : des localités proches peuvent partager la même cellule. La "
    "période couverte dépend de la variable et figure sur chaque série ; la "
    "réanalyse est publiée avec plusieurs mois de retard. Licence Copernicus "
    "(CC-BY) ; attribution : Generated using Copernicus Atmosphere Monitoring "
    "Service Information 2026. DOI du jeu de données et année de publication non "
    "confirmés ; référence méthodologique Inness et al. 2019 "
    "(doi:10.5194/acp-19-3515-2019)."
)

# Etat exact des metadonnees ecrit par la migration 081 (garde + downgrade).
_METADONNEES_ANCIENNES: dict[str, Any] = {
    "dataset_id": "cams-global-reanalysis-eac4",
    "store": "ADS (Atmosphere Data Store, Copernicus)",
    "licence": "Copernicus (CC-BY)",
    "resolution_grille": "0,75 deg",
    "pas_temporel_source": "3-horaire (00/03/06/09/12/15/18/21 UTC)",
    "agregation_kuma": "moyenne journaliere des pas 3-horaires (concentration intensive)",
    "conversion": "kg/m3 (natif) -> ug/m3 (x 1e9)",
    "variables_ingerees": ["pm2.5 (pm2p5)", "pm10"],
    "periode_reelle": "2021-01-01 a 2025-08-31",
    "latence_reanalyse": "10 mois (juin 2026 : EAC4 borne a aout 2025)",
    "note_hsu": "le modele HSU consomme les PM de surface, pas l'AOD",
    "annee_publication_statut": "reanalyse continue ; reference methodologique Inness et al. 2019",
    "reference_methodologique": (
        "Inness, A. et al. (2019), The CAMS reanalysis of atmospheric "
        "composition, Atmos. Chem. Phys. 19, 3515-3556, "
        "doi:10.5194/acp-19-3515-2019"
    ),
}
# Cles remplacees par fusion (``||``) ; types identiques aux anciens.
_METADONNEES_COMPLEMENT: dict[str, Any] = {
    "variables_ingerees": [
        "pm2.5 (pm2p5)",
        "pm10",
        "aod550",
        "duaod550",
        "go3 (niveau modele 60, le plus bas)",
    ],
    "conversion": (
        "pm2p5, pm10 : kg/m3 (natif) -> ug/m3 (x 1e9) ; "
        "aod550, duaod550 : sans unite, aucune conversion ; "
        "go3 : kg/kg (natif) -> ppb (x 28.9644/47.9982 x 1e9)"
    ),
    "agregation_kuma": (
        "moyenne journaliere des pas 3-horaires (concentration intensive) ; "
        "ozone diurne : moyenne des pas 09/12/15 UTC"
    ),
    "periode_reelle": (
        "pm2p5, pm10 : 2021-01-01 a 2025-08-31 ; aod550, duaod550, go3 : 2004-02-01 a 2025-12-31"
    ),
}


def _update_source(
    *,
    notes_attendues: str,
    metadonnees_attendues: dict[str, Any],
    notes: str,
    metadonnees: dict[str, Any],
) -> None:
    """UPDATE garde de la ligne ``cams_eac4`` : etat de depart exact, 1 ligne."""
    resultat = op.get_bind().execute(
        sa.text(
            """
            UPDATE sources
            SET notes = :notes, metadonnees = CAST(:metadonnees AS JSONB)
            WHERE code = :code
              AND notes = :notes_attendues
              AND metadonnees = CAST(:metadonnees_attendues AS JSONB)
            """
        ),
        {
            "code": _SOURCE_CODE,
            "notes": notes,
            "metadonnees": json.dumps(metadonnees),
            "notes_attendues": notes_attendues,
            "metadonnees_attendues": json.dumps(metadonnees_attendues),
        },
    )
    if resultat.rowcount != 1:
        raise RuntimeError(
            f"Migration 125 : source {_SOURCE_CODE!r} attendue dans son etat de depart "
            f"exact (notes + metadonnees), {resultat.rowcount} ligne(s) mise(s) a jour "
            "au lieu de 1. Abandon sans ecriture partielle."
        )


def upgrade() -> None:
    op.create_table_comment(
        "unites",
        _COMMENTAIRE_UNITES_NOUVEAU,
        existing_comment=_COMMENTAIRE_UNITES_ANCIEN,
    )
    op.create_table_comment(
        "grandeurs_referentiel",
        _COMMENTAIRE_GRANDEURS_NOUVEAU,
        existing_comment=_COMMENTAIRE_GRANDEURS_ANCIEN,
    )
    _update_source(
        notes_attendues=_NOTES_ANCIENNES,
        metadonnees_attendues=_METADONNEES_ANCIENNES,
        notes=_NOTES_NOUVELLES,
        metadonnees={**_METADONNEES_ANCIENNES, **_METADONNEES_COMPLEMENT},
    )


def downgrade() -> None:
    _update_source(
        notes_attendues=_NOTES_NOUVELLES,
        metadonnees_attendues={**_METADONNEES_ANCIENNES, **_METADONNEES_COMPLEMENT},
        notes=_NOTES_ANCIENNES,
        metadonnees=_METADONNEES_ANCIENNES,
    )
    op.create_table_comment(
        "grandeurs_referentiel",
        _COMMENTAIRE_GRANDEURS_ANCIEN,
        existing_comment=_COMMENTAIRE_GRANDEURS_NOUVEAU,
    )
    op.create_table_comment(
        "unites",
        _COMMENTAIRE_UNITES_ANCIEN,
        existing_comment=_COMMENTAIRE_UNITES_NOUVEAU,
    )

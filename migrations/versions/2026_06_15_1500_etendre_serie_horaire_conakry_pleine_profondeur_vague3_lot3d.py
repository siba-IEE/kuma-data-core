"""etendre_serie_horaire_conakry_pleine_profondeur_vague3_lot3d

Revision ID: 066
Revises: 065
Create Date: 2026-06-15 15:00:00.000000+00:00

Backfill Conakry 2001-2020 par **extension de la serie
pilote**, pour atteindre la pleine profondeur 2001-2023 comme
les 5 autres villes. Pas de nouvelle serie, pas de re-ingestion 2021-2023.

Operation (par grandeur, sur les 6 series Conakry horaire) :

1. Renommage du code ``gin_conakry_<g>_nasa_power_2021_2023`` ->
   ``_2001_2023``, ``periode_debut = 2001-01-01``, libelle et commentaire
   ajustes. **Inconditionnel** (metadonnee = cible, coherent avec les
   autres villes en CI).
2. Ingestion des annees 2001-2020 dans le **meme serie_id** (gardee par
   ``KUMA_SKIP_INGESTION_MASSE_HORAIRE``). L'EXCLUDE BTree-GiST ne bloque
   pas : instants 2001-2020 disjoints de 2021-2023.

Le QC des lignes neuves est la migration 067, **scopee a 2001-2020** pour
ne pas retoucher les decisions QC anterieures sur 2021-2023 (29 rejets DHI).

Contraintes verifiees : ``uq_series_metadonnees_code`` et
``uq_..._identite_metier_plage`` ne collisionnent pas (nouveau code +
tuple (localite, grandeur, source, 2001-01-01, 2023-12-31) inedits).
Aucun test ne reference le code horaire ``_2021_2023``. La migration 055
(QC pilote) s'execute avant 066 dans la chaine, le renommage ne
l'invalide pas.

Volume : 6 x 20 = 120 appels NASA POWER hourly ; 960 k lignes brut.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.ingestion.nasa_power_hourly import ingerer_serie_horaire

# revision identifiers, used by Alembic.
revision: str = "066"
down_revision: str | Sequence[str] | None = "065"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_VARIABLE_ENV_SKIP_MASSE: str = "KUMA_SKIP_INGESTION_MASSE_HORAIRE"


def _skip_ingestion_masse() -> bool:
    return os.environ.get(_VARIABLE_ENV_SKIP_MASSE, "").strip().lower() in ("1", "true", "yes")


_LOCALITE_CODE: str = "gin_conakry_kaloum"

# Mapping grandeur Kuma -> parametre NASA POWER (hourly), identique aux
# lots precedents.
_MAPPING_GRANDEURS: dict[str, str] = {
    "ghi": "ALLSKY_SFC_SW_DWN",
    "dni": "ALLSKY_SFC_SW_DNI",
    "dhi": "ALLSKY_SFC_SW_DIFF",
    "t2m": "T2M",
    "rh2m": "RH2M",
    "kt": "ALLSKY_KT",
}

_ANNEE_BACKFILL_DEBUT: int = 2001
_ANNEE_BACKFILL_FIN: int = 2020

_FENETRE_ANCIENNE: str = "2021_2023"
_FENETRE_NOUVELLE: str = "2001_2023"
_LIBELLE_ANCIEN: str = "2021-2023"
_LIBELLE_NOUVEAU: str = "2001-2023"

_NOTE_BACKFILL: str = (
    " Profondeur etendue a 2001-2020 en lot 3d (backfill, meme serie ; QC "
    "applique sur les seules lignes neuves, lot 2 sur 2021-2023 preserve)."
)


def _code_ancien(grandeur: str) -> str:
    return f"gin_conakry_{grandeur}_nasa_power_{_FENETRE_ANCIENNE}"


def _code_nouveau(grandeur: str) -> str:
    return f"gin_conakry_{grandeur}_nasa_power_{_FENETRE_NOUVELLE}"


def upgrade() -> None:
    bind = op.get_bind()

    ligne_loc = bind.execute(
        sa.text(
            "SELECT CAST(latitude AS DOUBLE PRECISION) AS lat, "
            "CAST(longitude AS DOUBLE PRECISION) AS lon "
            "FROM localites WHERE code = :code"
        ),
        {"code": _LOCALITE_CODE},
    ).first()
    if ligne_loc is None:
        raise RuntimeError(f"Migration 066 : localite {_LOCALITE_CODE!r} introuvable.")
    latitude = float(ligne_loc.lat)
    longitude = float(ligne_loc.lon)

    # === Étape 1 : extension métadonnée (inconditionnelle) ================
    for grandeur in _MAPPING_GRANDEURS:
        ancien = _code_ancien(grandeur)
        row = bind.execute(
            sa.text(
                "SELECT id, libelle, commentaire_editorial "
                "FROM series_metadonnees WHERE code = :code"
            ),
            {"code": ancien},
        ).first()
        if row is None:
            raise RuntimeError(
                f"Migration 066 : serie {ancien!r} introuvable (migration 054 appliquee ?)."
            )
        nouveau_libelle = (row.libelle or "").replace(_LIBELLE_ANCIEN, _LIBELLE_NOUVEAU)
        nouveau_commentaire = (row.commentaire_editorial or "") + _NOTE_BACKFILL
        bind.execute(
            sa.text(
                """
                UPDATE series_metadonnees
                SET code = :nouveau,
                    periode_debut = :debut,
                    libelle = :libelle,
                    commentaire_editorial = :commentaire,
                    modifie_le = now()
                WHERE code = :ancien
                """
            ),
            {
                "nouveau": _code_nouveau(grandeur),
                "debut": date(_ANNEE_BACKFILL_DEBUT, 1, 1),
                "libelle": nouveau_libelle,
                "commentaire": nouveau_commentaire,
                "ancien": ancien,
            },
        )

    # === Étape 2 : ingestion 2001-2020 (gardée) ===========================
    if _skip_ingestion_masse():
        op.execute(
            f"-- Migration 066 : metadonnee etendue (6 series Conakry renommees "
            f"_2001_2023, periode_debut 2001). Ingestion de masse court-circuitee "
            f"({_VARIABLE_ENV_SKIP_MASSE}). 0 ligne 2001-2020 ingeree (livrable "
            f"humain, cf. dette D-64)."
        )
        return

    session = Session(bind=bind)
    try:
        decomptes_totaux: dict[str, int] = {}
        for grandeur, parametre_nasa in _MAPPING_GRANDEURS.items():
            code_serie = _code_nouveau(grandeur)
            n_lignes = ingerer_serie_horaire(
                session=session,
                code_serie=code_serie,
                parametre_nasa=parametre_nasa,
                latitude=latitude,
                longitude=longitude,
                annee_debut=_ANNEE_BACKFILL_DEBUT,
                annee_fin=_ANNEE_BACKFILL_FIN,
            )
            decomptes_totaux[code_serie] = n_lignes

        total = sum(decomptes_totaux.values())
        op.execute(
            f"-- Migration 066 : {total} lignes 2001-2020 inserees dans "
            f"mesures_ressource_horaires (6 grandeurs x Conakry, meme serie_id). "
            f"Decompte par serie : {decomptes_totaux}"
        )
    finally:
        session.close()


def downgrade() -> None:
    bind = op.get_bind()

    # Suppression des lignes neuves (2001-2020) sur les series Conakry horaire.
    codes_nouveaux = [_code_nouveau(g) for g in _MAPPING_GRANDEURS]
    op.execute(
        sa.text(
            """
            DELETE FROM mesures_ressource_horaires
            WHERE serie_id IN (
                SELECT id FROM series_metadonnees WHERE code = ANY(:codes)
            )
            AND (instant_mesure AT TIME ZONE 'UTC')::date < :borne
            """
        ).bindparams(
            sa.bindparam("codes", value=codes_nouveaux),
            sa.bindparam("borne", value=date(2021, 1, 1)),
        )
    )

    # Restauration des metadonnees pilote (rename inverse + periode + textes).
    for grandeur in _MAPPING_GRANDEURS:
        nouveau = _code_nouveau(grandeur)
        row = bind.execute(
            sa.text(
                "SELECT libelle, commentaire_editorial FROM series_metadonnees WHERE code = :code"
            ),
            {"code": nouveau},
        ).first()
        if row is None:
            continue
        ancien_libelle = (row.libelle or "").replace(_LIBELLE_NOUVEAU, _LIBELLE_ANCIEN)
        ancien_commentaire = (row.commentaire_editorial or "").replace(_NOTE_BACKFILL, "")
        bind.execute(
            sa.text(
                """
                UPDATE series_metadonnees
                SET code = :ancien,
                    periode_debut = :debut,
                    libelle = :libelle,
                    commentaire_editorial = :commentaire,
                    modifie_le = now()
                WHERE code = :nouveau
                """
            ),
            {
                "ancien": _code_ancien(grandeur),
                "debut": date(2021, 1, 1),
                "libelle": ancien_libelle,
                "commentaire": ancien_commentaire,
                "nouveau": nouveau,
            },
        )

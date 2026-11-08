"""retirer_etape_atlas_libelles_series

Revision ID: 130
Revises: 129
Create Date: 2026-11-08 18:00:00.000000+00:00

Migration de coherence editoriale, sans DDL ni donnee mesuree. Les 62 series
d'ecart inter-source 2021-2023 creees par la migration 091 portent dans leur
libelle publie le marqueur d'etape interne « (atlas Temps 1) ». Il est retire :
il ne distingue ces series d'aucune autre (libelles uniques avec ou sans lui),
et le reste du libelle garde sa forme.

- ``ecart_relatif_referentiel`` (GHI) : 28 communes ;
- ``ecart_relatif_dni_cams`` (DNI) : 6 villes pilotes et 28 communes.

Correction en place sous le trigger d'audit, ``modifie_le`` inchange. Gardes :
chaque serie est attendue par son code avec son libelle de depart exact,
62 lignes exactement ; aucun libelle d'arrivee ne doit preexister ; plus aucun
libelle ne porte « Temps n » apres. Le downgrade restaure les libelles a
l'identique sous les memes gardes. Aucun reseau.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "130"
down_revision: str | Sequence[str] | None = "129"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MARQUEUR = " (atlas Temps 1)"

_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)
_COMMUNES: tuple[str, ...] = (
    "gin_beyla",
    "gin_boffa",
    "gin_boke_centre",
    "gin_coyah",
    "gin_dabola",
    "gin_dalaba",
    "gin_dinguiraye",
    "gin_dubreka",
    "gin_faranah_centre",
    "gin_forecariah",
    "gin_fria",
    "gin_gaoual",
    "gin_gueckedou",
    "gin_kerouane",
    "gin_kissidougou",
    "gin_koubia",
    "gin_koundara",
    "gin_kouroussa",
    "gin_lelouma",
    "gin_lola",
    "gin_macenta",
    "gin_mali",
    "gin_mandiana",
    "gin_pita",
    "gin_siguiri",
    "gin_telimele",
    "gin_tougue",
    "gin_yomou",
)
_SERIES: tuple[tuple[str, str], ...] = tuple(
    ("ecart_relatif_referentiel", c) for c in _COMMUNES
) + tuple(("ecart_relatif_dni_cams", c) for c in _PILOTES + _COMMUNES)


def _echec(message: str) -> RuntimeError:
    return RuntimeError(f"Migration 130 : {message} Abandon sans ecriture partielle.")


def _libelles() -> list[tuple[str, str, str]]:
    """(code de serie, libelle avec marqueur, libelle sans marqueur)."""
    lignes = []
    for grandeur, localite in _SERIES:
        # Code de serie : Conakry-Kaloum y est abrege en gin_conakry (migration 091).
        alias = "gin_conakry" if localite == "gin_conakry_kaloum" else localite
        sans = f"{grandeur} mensuel {localite} 2021-2023"
        lignes.append((f"{alias}_{grandeur}_kuma_calculs_2021_2023", sans + _MARQUEUR, sans))
    return lignes


def _appliquer(*, sens: int) -> None:
    """``sens`` = 1 retire le marqueur ; ``sens`` = 0 le restaure."""
    lignes = _libelles()
    if len(lignes) != 62:
        raise _echec(f"62 series attendues, {len(lignes)} definies.")
    codes = [c for c, _, _ in lignes]
    departs = [a if sens == 1 else b for _, a, b in lignes]
    arrivees = [b if sens == 1 else a for _, a, b in lignes]
    bind = op.get_bind()

    deja = bind.execute(
        sa.text("SELECT count(*) FROM series_metadonnees WHERE libelle = ANY(:a)"),
        {"a": arrivees},
    ).scalar_one()
    if deja != 0:
        raise _echec(f"{deja} libelle(s) d'arrivee deja present(s).")

    resultat = bind.execute(
        sa.text(
            """
            UPDATE series_metadonnees s SET libelle = v.arrivee
            FROM unnest(CAST(:codes AS text[]), CAST(:departs AS text[]),
                        CAST(:arrivees AS text[])) AS v(code, depart, arrivee)
            WHERE s.code = v.code AND s.libelle = v.depart
            """
        ),
        {"codes": codes, "departs": departs, "arrivees": arrivees},
    )
    if resultat.rowcount != 62:
        raise _echec(f"{resultat.rowcount} ligne(s) mise(s) a jour au lieu de 62.")

    restants = bind.execute(
        sa.text("SELECT count(*) FROM series_metadonnees WHERE libelle ~ 'Temps\\s+\\d'")
    ).scalar_one()
    if restants != (0 if sens == 1 else 62):
        raise _echec(f"{restants} libelle(s) portant « Temps n » apres reecriture.")


def upgrade() -> None:
    _appliquer(sens=1)


def downgrade() -> None:
    _appliquer(sens=0)

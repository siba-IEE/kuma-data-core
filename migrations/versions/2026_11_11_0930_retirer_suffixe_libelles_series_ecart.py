"""retirer_suffixe_libelles_series_ecart

Revision ID: 123
Revises: 122
Create Date: 2026-11-11 09:30:00

Les libellés de 62 séries d'écart 2021-2023 (34 séries
``ecart_relatif_dni_cams`` et 28 séries ``ecart_relatif_referentiel``) se
terminaient par une mention de chantier entre parenthèses. Elle est retirée :
le libellé suit alors le modèle des autres séries de la même grandeur,
« <grandeur> mensuel <localité> <période> ».

Correction sur place d'une table de référentiel, journalisée par le trigger
d'audit. Seule la colonne ``libelle`` change : ``modifie_le`` n'est maintenue
ni par un trigger ni par le modèle, elle reste donc intacte.

Gardes : exactement 62 lignes, empreinte des textes de départ, aucun libellé
cible déjà porté par une autre série, puis contrôle après écriture. Une garde
qui échoue lève ``RuntimeError`` et annule la transaction. Le downgrade rend
les anciens libellés à l'identique.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "123"
down_revision: str | Sequence[str] | None = "122"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SUFFIXE = " (atlas Temps 1)"

# Préfixes de code de série des 34 points ; les six premiers n'ont pas de série
# ``ecart_relatif_referentiel`` concernée (la leur n'a jamais porté le suffixe).
_PREFIXES_SANS_ECART_REFERENTIEL = (
    "gin_conakry",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)
_PREFIXES_AUTRES = (
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
CODES: list[str] = sorted(
    [
        f"{prefixe}_ecart_relatif_dni_cams_kuma_calculs_2021_2023"
        for prefixe in (*_PREFIXES_SANS_ECART_REFERENTIEL, *_PREFIXES_AUTRES)
    ]
    + [
        f"{prefixe}_ecart_relatif_referentiel_kuma_calculs_2021_2023"
        for prefixe in _PREFIXES_AUTRES
    ]
)
_NB_ATTENDU = 62

# md5(string_agg(code || ':' || libelle, '|' ORDER BY code)) des 62 séries.
_EMPREINTE_AVEC_SUFFIXE = "67091847cf4cee8e65b16b8bc700323e"
_EMPREINTE_SANS_SUFFIXE = "e9104f2efe533f0f4e8c0b2a7045c149"

_SQL_EMPREINTE = sa.text(
    "SELECT count(*), md5(COALESCE(string_agg(code || ':' || libelle, '|' ORDER BY code), '')) "
    "FROM series_metadonnees WHERE code = ANY(:codes)"
)
_SQL_COLLISIONS = sa.text(
    "SELECT count(*) FROM series_metadonnees autre "
    "JOIN series_metadonnees visee ON visee.code = ANY(:codes) AND autre.id <> visee.id "
    "WHERE autre.libelle = left(visee.libelle, length(visee.libelle) - length(:suffixe))"
)
_SQL_AVEC_SUFFIXE = sa.text(
    "SELECT count(*) FROM series_metadonnees "
    "WHERE right(libelle, length(:suffixe)) = :suffixe AND (:partout OR code = ANY(:codes))"
)


def _garde(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"Migration 123 : {message}")


def _empreinte(bind: sa.Connection) -> tuple[int, str]:
    n, empreinte = bind.execute(_SQL_EMPREINTE, {"codes": CODES}).one()
    return int(n), str(empreinte)


def _nb_avec_suffixe(bind: sa.Connection, *, partout: bool) -> int:
    return int(
        bind.execute(
            _SQL_AVEC_SUFFIXE, {"suffixe": _SUFFIXE, "codes": CODES, "partout": partout}
        ).scalar_one()
    )


def upgrade() -> None:
    bind = op.get_bind()
    _garde(len(CODES) == _NB_ATTENDU, f"{len(CODES)} codes listés, {_NB_ATTENDU} attendus.")
    _garde(
        _empreinte(bind) == (_NB_ATTENDU, _EMPREINTE_AVEC_SUFFIXE),
        "les libellés de départ ne sont pas ceux attendus, rien n'est écrit.",
    )
    _garde(
        _nb_avec_suffixe(bind, partout=True) == _NB_ATTENDU,
        "des séries hors de la liste portent le suffixe, rien n'est écrit.",
    )
    collisions = bind.execute(_SQL_COLLISIONS, {"codes": CODES, "suffixe": _SUFFIXE}).scalar_one()
    _garde(collisions == 0, f"{collisions} libellés cibles existent déjà, rien n'est écrit.")

    resultat = bind.execute(
        sa.text(
            "UPDATE series_metadonnees "
            "SET libelle = left(libelle, length(libelle) - length(:suffixe)) "
            "WHERE code = ANY(:codes) AND right(libelle, length(:suffixe)) = :suffixe"
        ),
        {"codes": CODES, "suffixe": _SUFFIXE},
    )
    _garde(resultat.rowcount == _NB_ATTENDU, f"{resultat.rowcount} lignes modifiées.")
    _garde(
        _empreinte(bind) == (_NB_ATTENDU, _EMPREINTE_SANS_SUFFIXE),
        "les libellés obtenus ne sont pas ceux attendus.",
    )
    _garde(_nb_avec_suffixe(bind, partout=True) == 0, "un libellé porte encore le suffixe.")


def downgrade() -> None:
    bind = op.get_bind()
    _garde(
        _empreinte(bind) == (_NB_ATTENDU, _EMPREINTE_SANS_SUFFIXE),
        "les libellés ont changé depuis l'upgrade, rien n'est écrit.",
    )
    _garde(_nb_avec_suffixe(bind, partout=True) == 0, "un libellé porte déjà le suffixe.")
    resultat = bind.execute(
        sa.text(
            "UPDATE series_metadonnees SET libelle = libelle || :suffixe WHERE code = ANY(:codes)"
        ),
        {"codes": CODES, "suffixe": _SUFFIXE},
    )
    _garde(resultat.rowcount == _NB_ATTENDU, f"{resultat.rowcount} lignes modifiées.")
    _garde(
        _empreinte(bind) == (_NB_ATTENDU, _EMPREINTE_AVEC_SUFFIXE),
        "les libellés rétablis ne sont pas ceux d'origine.",
    )

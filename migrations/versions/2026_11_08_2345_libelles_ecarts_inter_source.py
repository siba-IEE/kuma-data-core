"""libelles_ecarts_inter_source

Revision ID: 135
Revises: 134
Create Date: 2026-11-08 23:45:00.000000+00:00

Migration de coherence editoriale, sans DDL ni donnee mesuree. Les libelles
publies des deux grandeurs d'ecart inter-source trompaient :

- ``ecart_relatif_referentiel`` s'intitulait « Écart relatif au référentiel
  Kuma » alors qu'elle est l'ecart mensuel du GHI entre NASA POWER et
  PVGIS-SARAH-3, ``(NASA POWER - SARAH-3) / SARAH-3 x 100``, comme le dit sa
  description ;
- ``ecart_relatif_dni_cams`` s'intitulait « Ecart relatif DNI CAMS vs NASA
  POWER », sources dans l'ordre inverse de la formule
  ``(NASA POWER - CAMS) / CAMS x 100`` et sans accent.

Nouveaux libelles : « Écart relatif GHI NASA POWER vs SARAH-3 » et « Écart
relatif DNI NASA POWER vs CAMS » (grandeur, puis source comparee avant la
reference, dans l'ordre et avec les noms de la formule). Les notes publiques
des series qui reprennent le libelle (« Série <libellé> pour <lieu>, ... »),
34 pour le GHI et 40 pour le DNI, le reprennent a l'identique.

Correction en place sous le trigger d'audit, ``modifie_le`` inchange.
Gardes : libelle de depart exact ; notes attendues par leur nombre exact et
l'empreinte md5 de l'ensemble (code et texte) avant et apres ; l'ancien
libelle ne figure dans aucune autre note, le nouveau dans aucune note ni
aucun libelle avant ecriture. Le downgrade restaure les textes a l'identique
sous les memes gardes. Aucun reseau.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "135"
down_revision: str | Sequence[str] | None = "134"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class _Libelle(NamedTuple):
    grandeur: str
    ancien: str
    nouveau: str
    notes: int
    # md5 de string_agg(code || '|' || note_publique, '#' ORDER BY code) des notes visees.
    md5_ancien: str
    md5_nouveau: str


_LIBELLES: tuple[_Libelle, ...] = (
    _Libelle(
        "ecart_relatif_referentiel",
        "Écart relatif au référentiel Kuma",
        "Écart relatif GHI NASA POWER vs SARAH-3",
        34,
        "81bd7244810a5b941c25c206d8119980",
        "08942759a37bb05adadec5ade54b4560",
    ),
    _Libelle(
        "ecart_relatif_dni_cams",
        "Ecart relatif DNI CAMS vs NASA POWER",
        "Écart relatif DNI NASA POWER vs CAMS",
        40,
        "5e51024fe2a0ce42c0e294cc611cccfc",
        "05b4ad3d570ab4f4c9aa89fa0623e9c7",
    ),
)

_EMPREINTE = """
SELECT count(*) AS n, md5(string_agg(code || '|' || note_publique, '#' ORDER BY code)) AS h
FROM series_metadonnees
WHERE grandeur_code = :g AND left(note_publique, length(:p)) = :p
"""


def _echec(message: str) -> RuntimeError:
    return RuntimeError(f"Migration 135 : {message} Abandon sans ecriture partielle.")


def _prefixe(libelle: str) -> str:
    return f"Série {libelle} pour "


def _appliquer(*, sens: int) -> None:
    """``sens`` = 1 pose les nouveaux libelles ; ``sens`` = 0 restaure les anciens."""
    bind = op.get_bind()
    for cible in _LIBELLES:
        depart, arrivee = (
            (cible.ancien, cible.nouveau) if sens == 1 else (cible.nouveau, cible.ancien)
        )
        h_depart, h_arrivee = (
            (cible.md5_ancien, cible.md5_nouveau)
            if sens == 1
            else (cible.md5_nouveau, cible.md5_ancien)
        )
        p_depart, p_arrivee = _prefixe(depart), _prefixe(arrivee)

        n, h = bind.execute(sa.text(_EMPREINTE), {"g": cible.grandeur, "p": p_depart}).one()
        if (n, h) != (cible.notes, h_depart):
            raise _echec(f"{cible.grandeur} : {n} note(s) de depart d'empreinte {h}.")
        ailleurs = bind.execute(
            sa.text(
                "SELECT count(*) FROM series_metadonnees "
                "WHERE strpos(note_publique, :l) > 0 OR strpos(libelle, :l) > 0"
            ),
            {"l": depart},
        ).scalar_one()
        if ailleurs != cible.notes:
            raise _echec(f"« {depart} » figure dans {ailleurs} texte(s) de serie.")
        deja = bind.execute(
            sa.text(
                "SELECT (SELECT count(*) FROM series_metadonnees "
                "        WHERE strpos(note_publique, :l) > 0 OR strpos(libelle, :l) > 0)"
                " + (SELECT count(*) FROM grandeurs_referentiel WHERE libelle = :l)"
            ),
            {"l": arrivee},
        ).scalar_one()
        if deja != 0:
            raise _echec(f"« {arrivee} » deja present dans {deja} texte(s).")

        libelle = bind.execute(
            sa.text(
                "UPDATE grandeurs_referentiel SET libelle = :a WHERE code = :g AND libelle = :d"
            ),
            {"g": cible.grandeur, "d": depart, "a": arrivee},
        )
        if libelle.rowcount != 1:
            raise _echec(f"{cible.grandeur} : {libelle.rowcount} libelle(s) mis a jour.")
        notes = bind.execute(
            sa.text(
                """
                UPDATE series_metadonnees
                SET note_publique = :pa || substr(note_publique, length(:pd) + 1)
                WHERE grandeur_code = :g AND left(note_publique, length(:pd)) = :pd
                """
            ),
            {"g": cible.grandeur, "pd": p_depart, "pa": p_arrivee},
        )
        if notes.rowcount != cible.notes:
            raise _echec(
                f"{cible.grandeur} : {notes.rowcount} note(s) mise(s) a jour "
                f"au lieu de {cible.notes}."
            )
        n, h = bind.execute(sa.text(_EMPREINTE), {"g": cible.grandeur, "p": p_arrivee}).one()
        if (n, h) != (cible.notes, h_arrivee):
            raise _echec(f"{cible.grandeur} : {n} note(s) d'arrivee d'empreinte {h}.")


def upgrade() -> None:
    _appliquer(sens=1)


def downgrade() -> None:
    _appliquer(sens=0)

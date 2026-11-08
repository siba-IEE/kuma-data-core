"""nommer_localites_libelles_series

Revision ID: 131
Revises: 130
Create Date: 2026-11-08 20:00:00.000000+00:00

Migration de coherence editoriale, sans DDL ni donnee mesuree. 314 libelles
publies de series calculees par Kuma designent leur localite par son code
(``gin_fria``) et non par son nom (``Fria``), comme le reste de la base :

- ``ecart_relatif_dni_cams mensuel <code> 2021-2023`` : 34 (6 villes pilotes et
  28 communes, migration 091) ;
- ``ecart_relatif_referentiel mensuel <code> 2021-2023`` : 28 communes
  (migration 091) ;
- ``<grandeur> <code> <debut>-<fin> (calcul Kuma)`` : 9 gabarits x 28 communes
  (migrations de parite A1 et A2).

Le code est remplace par ``localites.nom`` de la localite de la serie ; le
reste du libelle garde sa forme.

Correction en place sous le trigger d'audit, ``modifie_le`` inchange. Gardes :
chaque serie est attendue par son code avec son libelle de depart exact,
314 lignes exactement ; aucun libelle d'arrivee ne doit preexister ; le nom
employe est celui de la localite de la serie ; plus aucun libelle ne porte un
code de localite comme mot entier apres. Le downgrade restaure les libelles a
l'identique sous les memes gardes. Aucun reseau.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "131"
down_revision: str | Sequence[str] | None = "130"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ATTENDU = 314

# Code de localite -> localites.nom.
_PILOTES: dict[str, str] = {
    "gin_conakry_kaloum": "Kaloum",
    "gin_kankan": "Kankan",
    "gin_kindia": "Kindia",
    "gin_labe": "Labé",
    "gin_mamou": "Mamou",
    "gin_nzerekore": "Nzérékoré",
}
_COMMUNES: dict[str, str] = {
    "gin_beyla": "Beyla",
    "gin_boffa": "Boffa",
    "gin_boke_centre": "Boke",
    "gin_coyah": "Coyah",
    "gin_dabola": "Dabola",
    "gin_dalaba": "Dalaba",
    "gin_dinguiraye": "Dinguiraye",
    "gin_dubreka": "Dubreka",
    "gin_faranah_centre": "Faranah",
    "gin_forecariah": "Forecariah",
    "gin_fria": "Fria",
    "gin_gaoual": "Gaoual",
    "gin_gueckedou": "Gueckedou",
    "gin_kerouane": "Kerouane",
    "gin_kissidougou": "Kissidougou",
    "gin_koubia": "Koubia",
    "gin_koundara": "Koundara",
    "gin_kouroussa": "Kouroussa",
    "gin_lelouma": "Lelouma",
    "gin_lola": "Lola",
    "gin_macenta": "Macenta",
    "gin_mali": "Mali",
    "gin_mandiana": "Mandiana",
    "gin_pita": "Pita",
    "gin_siguiri": "Siguiri",
    "gin_telimele": "Telimele",
    "gin_tougue": "Tougue",
    "gin_yomou": "Yomou",
}

# (grandeur, debut, fin, forme, localites) ; forme "mensuel" ou "calcul".
_GABARITS: tuple[tuple[str, int, int, str, dict[str, str]], ...] = (
    ("ecart_relatif_dni_cams", 2021, 2023, "mensuel", _PILOTES | _COMMUNES),
    ("ecart_relatif_referentiel", 2021, 2023, "mensuel", _COMMUNES),
    ("fraction_diffuse", 2001, 2020, "calcul", _COMMUNES),
    ("fraction_diffuse", 2021, 2025, "calcul", _COMMUNES),
    ("hep", 1991, 2020, "calcul", _COMMUNES),
    ("hep", 2021, 2025, "calcul", _COMMUNES),
    ("humidex", 2021, 2025, "calcul", _COMMUNES),
    ("productible_specifique_theorique", 1991, 2020, "calcul", _COMMUNES),
    ("productible_specifique_theorique", 2021, 2025, "calcul", _COMMUNES),
    ("rang_referentiel_temporel", 2021, 2025, "calcul", _COMMUNES),
    ("variabilite_journaliere", 2021, 2025, "calcul", _COMMUNES),
)

# Un code de localite employe comme mot entier (pas dans un code de serie).
_CODE_EN_MOT = "s.libelle ~ ('(^|[^a-z0-9_])' || l.code || '($|[^a-z0-9_])')"


def _echec(message: str) -> RuntimeError:
    return RuntimeError(f"Migration 131 : {message} Abandon sans ecriture partielle.")


def _libelle(grandeur: str, debut: int, fin: int, forme: str, lieu: str) -> str:
    if forme == "mensuel":
        return f"{grandeur} mensuel {lieu} {debut}-{fin}"
    return f"{grandeur} {lieu} {debut}-{fin} (calcul Kuma)"


def _libelles() -> list[tuple[str, str, str, str]]:
    """(code de serie, libelle par code, libelle par nom, nom)."""
    lignes = []
    for grandeur, debut, fin, forme, localites in _GABARITS:
        for localite, nom in localites.items():
            # Code de serie : Conakry-Kaloum y est abrege en gin_conakry (migration 091).
            alias = "gin_conakry" if localite == "gin_conakry_kaloum" else localite
            lignes.append(
                (
                    f"{alias}_{grandeur}_kuma_calculs_{debut}_{fin}",
                    _libelle(grandeur, debut, fin, forme, localite),
                    _libelle(grandeur, debut, fin, forme, nom),
                    nom,
                )
            )
    return lignes


def _appliquer(*, sens: int) -> None:
    """``sens`` = 1 nomme la localite ; ``sens`` = 0 restaure son code."""
    lignes = _libelles()
    if len(lignes) != _ATTENDU:
        raise _echec(f"{_ATTENDU} series attendues, {len(lignes)} definies.")
    codes = [c for c, _, _, _ in lignes]
    noms = [n for _, _, _, n in lignes]
    departs = [a if sens == 1 else b for _, a, b, _ in lignes]
    arrivees = [b if sens == 1 else a for _, a, b, _ in lignes]
    bind = op.get_bind()

    deja = bind.execute(
        sa.text("SELECT count(*) FROM series_metadonnees WHERE libelle = ANY(:a)"),
        {"a": arrivees},
    ).scalar_one()
    if deja != 0:
        raise _echec(f"{deja} libelle(s) d'arrivee deja present(s).")

    ecarts = bind.execute(
        sa.text(
            """
            SELECT count(*) FROM unnest(CAST(:codes AS text[]), CAST(:noms AS text[]))
                AS v(code, nom)
            LEFT JOIN series_metadonnees s ON s.code = v.code
            LEFT JOIN localites l ON l.id = s.localite_id
            WHERE l.nom IS DISTINCT FROM v.nom
            """
        ),
        {"codes": codes, "noms": noms},
    ).scalar_one()
    if ecarts != 0:
        raise _echec(f"{ecarts} serie(s) absente(s) ou dont la localite porte un autre nom.")

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
    if resultat.rowcount != _ATTENDU:
        raise _echec(f"{resultat.rowcount} ligne(s) mise(s) a jour au lieu de {_ATTENDU}.")

    restants = bind.execute(
        sa.text(
            f"""
            SELECT count(*) FROM series_metadonnees s
            WHERE EXISTS (SELECT 1 FROM localites l WHERE {_CODE_EN_MOT})
            """
        )
    ).scalar_one()
    if restants != (0 if sens == 1 else _ATTENDU):
        raise _echec(f"{restants} libelle(s) portant un code de localite apres reecriture.")


def upgrade() -> None:
    _appliquer(sens=1)


def downgrade() -> None:
    _appliquer(sens=0)

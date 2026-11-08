"""couverture_complete_textes_publies

Revision ID: 132
Revises: 131
Create Date: 2026-11-08 22:00:00.000000+00:00

Migration de coherence editoriale, sans DDL ni donnee mesuree. Deux
corrections de textes publies :

1. 141 libelles de series ecrivent leur localite autrement que
   ``localites.nom`` : ``Conakry-Kaloum`` pour ``Kaloum`` (commune de Conakry
   nommee, comme Dixinn, Matam, Matoto et Ratoma, par son seul nom),
   ``Labe`` pour ``Labé`` et ``Nzerekore`` pour ``Nzérékoré`` ; 47 gabarits x
   3 localites. Le reste du libelle garde sa forme.
2. Les textes publies qui presentaient une partie des localites comme
   « pilotes » decrivent la couverture reelle, qui s'etend a toutes les
   localites : 36 notes publiques de series horaires (le controle qualite
   s'applique aux series horaires de toutes les localites couvertes), la
   description de ``ghi_exceedance`` (les 34 localites ont la serie GHI
   mensuelle 1991-2020 qui la fonde), celle de ``rang_referentiel``
   (desactivee) et la note de la source ``esmap_wapp``.

Les textes de ``rang_referentiel_spatial`` (description, libelles et notes de
ses series) restent hors de cette migration : la grandeur est reprise a part.

Correction en place sous le trigger d'audit, ``modifie_le`` inchange. Gardes :
chaque ligne est attendue par sa cle avec son texte de depart exact, nombre
de lignes exact par lot ; aucun libelle d'arrivee ne doit preexister ni se
repeter ; le nom employe est celui de la localite de la serie ; apres
ecriture, le nombre de textes portant « pilote » est celui attendu. Le
downgrade restaure les textes a l'identique sous les memes gardes. Aucun
reseau.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "132"
down_revision: str | Sequence[str] | None = "131"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# === 1. Libelles : localite ecrite comme localites.nom ====================

# Code de localite -> (prefixe des codes de serie, graphie de depart, localites.nom).
_LOCALITES: dict[str, tuple[str, str, str]] = {
    "gin_conakry_kaloum": ("gin_conakry", "Conakry-Kaloum", "Kaloum"),
    "gin_labe": ("gin_labe", "Labe", "Labé"),
    "gin_nzerekore": ("gin_nzerekore", "Nzerekore", "Nzérékoré"),
}

# (suffixe du code de serie, gabarit du libelle) ; {alias} = prefixe du code.
_GABARITS: tuple[tuple[str, str], ...] = (
    (
        "albedo_surface_nasa_power_2021_2025",
        "Albedo de surface journalier {lieu} 2021-2025 (NASA POWER)",
    ),
    (
        "albedo_surface_power_2001_2020",
        "Albedo de surface mensuel climato {lieu} 2001-2020 (NASA POWER monthly)",
    ),
    ("dhi_nasa_power_2001_2025", "DHI horaire brut {lieu} 2001-2025 (NASA POWER hourly, UTC)"),
    ("dhi_nasa_power_2021_2025", "DHI journalier {lieu} 2021-2025 (NASA POWER)"),
    ("dhi_power_2001_2020", "DHI mensuel climato {lieu} 2001-2020 (NASA POWER monthly)"),
    ("dni_cams_2004_2020", "DNI CAMS Radiation mensuel {lieu} 2004-2020"),
    ("dni_cams_2021_2023", "DNI CAMS Radiation mensuel {lieu} 2021-2023"),
    ("dni_nasa_power_2001_2025", "DNI horaire brut {lieu} 2001-2025 (NASA POWER hourly, UTC)"),
    ("dni_nasa_power_2021_2025", "DNI journalier {lieu} 2021-2025 (NASA POWER)"),
    ("dni_power_2001_2020", "DNI mensuel climato {lieu} 2001-2020 (NASA POWER monthly)"),
    (
        "fraction_diffuse_kuma_calculs_2021_2025",
        "Fraction diffuse annuelle et mensuelle {lieu} 2021-2025 (calcul Kuma)",
    ),
    (
        "fraction_diffuse_kuma_calculs_2001_2020",
        "Fraction diffuse climato mensuelle {lieu} 2001-2020 (Kuma calculs, derive de DHI "
        "{alias}_dhi_power_2001_2020 / GHI {alias}_ghi_power_1991_2020 restreint 2001-2020)",
    ),
    ("ghi_era5_land_2021_2025", "GHI ERA5-Land journalier {lieu} 2021-2025"),
    ("ghi_era5_land_2001_2020", "GHI ERA5-Land mensuel {lieu} 2001-2020"),
    ("ghi_nasa_power_2001_2025", "GHI horaire brut {lieu} 2001-2025 (NASA POWER hourly, UTC)"),
    ("ghi_nasa_power_2021_2025", "GHI journalier {lieu} 2021-2025 (NASA POWER)"),
    (
        "ghi_power_1991_2020",
        "GHI mensuel {lieu} 1991-2020 (NASA POWER, fenetre climatologique OMM)",
    ),
    ("ghi_sarah3_2021_2023", "GHI mensuel {lieu} 2021-2023 (PVGIS-SARAH3 ICDR)"),
    ("hep_kuma_calculs_2021_2025", "HEP {lieu} 2021-2025 (calcul Kuma)"),
    (
        "hep_kuma_calculs_1991_2020",
        "HEP climato mensuelle {lieu} 1991-2020 (Kuma calculs, derive de "
        "{alias}_ghi_power_1991_2020 (GHI mensuel NASA POWER))",
    ),
    (
        "humidex_kuma_calculs_2021_2025",
        "Humidex moyen annuel et mensuel {lieu} 2021-2025 (calcul Kuma)",
    ),
    (
        "rh2m_nasa_power_2001_2025",
        "Humidite relative 2m horaire brute {lieu} 2001-2025 (NASA POWER hourly, UTC)",
    ),
    (
        "rh2m_nasa_power_2021_2025",
        "Humidite relative 2m journaliere {lieu} 2021-2025 (NASA POWER)",
    ),
    (
        "rh2m_power_1991_2020",
        "Humidite relative 2m mensuelle climato {lieu} 1991-2020 (NASA POWER monthly)",
    ),
    (
        "kt_nasa_power_2001_2025",
        "Indice de clarte horaire brut {lieu} 2001-2025 (NASA POWER hourly, UTC)",
    ),
    (
        "kt_power_2001_2020",
        "Indice de clarte mensuel climato {lieu} 2001-2020 (NASA POWER monthly)",
    ),
    ("kt_nasa_power_2021_2025", "Kt journalier {lieu} 2021-2025 (NASA POWER)"),
    ("pm10_cams_eac4_2021_2025", "PM10 journalier {lieu} 2021-2025 (EAC4)"),
    ("pm2_5_cams_eac4_2021_2025", "PM2.5 journalier {lieu} 2021-2025 (EAC4)"),
    (
        "precipitation_nasa_power_2021_2025",
        "Precipitation journaliere {lieu} 2021-2025 (NASA POWER)",
    ),
    (
        "productible_specifique_theorique_kuma_calculs_2021_2025",
        "Productible specifique theorique annuel et mensuel {lieu} 2021-2025 (calcul Kuma)",
    ),
    (
        "productible_specifique_theorique_kuma_calculs_1991_2020",
        "Productible specifique theorique climato mensuel {lieu} 1991-2020 (Kuma calculs, "
        "derive de {alias}_hep_kuma_calculs_1991_2020 (HEP climato) * PR_theorique=0.8)",
    ),
    ("t2m_era5_land_2021_2025", "Temperature 2m ERA5-Land journalier {lieu} 2021-2025"),
    ("t2m_era5_land_2001_2020", "Temperature 2m ERA5-Land mensuel {lieu} 2001-2020"),
    (
        "t2m_nasa_power_2001_2025",
        "Temperature 2m horaire brute {lieu} 2001-2025 (NASA POWER hourly, UTC)",
    ),
    ("t2m_nasa_power_2021_2025", "Temperature 2m journaliere {lieu} 2021-2025 (NASA POWER)"),
    (
        "t2m_power_1991_2020",
        "Temperature 2m mensuelle climato {lieu} 1991-2020 (NASA POWER monthly)",
    ),
    (
        "variabilite_journaliere_kuma_calculs_2021_2025",
        "Variabilite journaliere annuelle (CoV) {lieu} 2021-2025 (calcul Kuma)",
    ),
    ("vent_10m_era5_land_2021_2025", "Vent 10m ERA5-Land journalier {lieu} 2021-2025"),
    ("vent_10m_era5_land_2001_2020", "Vent 10m ERA5-Land mensuel {lieu} 2001-2020"),
    ("vent_10m_nasa_power_2021_2025", "Vent 10m journalier {lieu} 2021-2025 (NASA POWER)"),
    (
        "vent_10m_power_1991_2020",
        "Vent 10m mensuel climato {lieu} 1991-2020 (NASA POWER monthly)",
    ),
    ("vent_2m_nasa_power_2021_2025", "Vent 2m journalier {lieu} 2021-2025 (NASA POWER)"),
    ("vent_2m_power_1991_2020", "Vent 2m mensuel climato {lieu} 1991-2020 (NASA POWER monthly)"),
    (
        "ecart_relatif_dni_cams_kuma_calculs_2004_2020",
        "ecart_relatif_dni_cams mensuel {lieu} 2004-2020",
    ),
    (
        "ecart_relatif_referentiel_kuma_calculs_2021_2023",
        "ecart_relatif_referentiel mensuel {lieu} 2021-2023",
    ),
    (
        "rang_referentiel_temporel_kuma_calculs_2021_2025",
        "rang_referentiel_temporel mensuel {lieu} 2021-2025",
    ),
)
_LIBELLES_ATTENDUS = 141

# === 2. Textes « pilote » : couverture reelle ============================

_PHRASE_HORAIRE_PILOTE = (
    "Série horaire du programme pilote : un contrôle qualité signale les valeurs "
    "suspectes sans les supprimer."
)
_PHRASE_HORAIRE_COUVERTURE = (
    "Série horaire : un contrôle qualité, appliqué aux séries horaires de toutes les "
    "localités couvertes, signale les valeurs suspectes sans les supprimer."
)
_SERIES_HORAIRES: tuple[str, ...] = tuple(
    f"{alias}_{grandeur}_nasa_power_2001_2025"
    for alias in (
        "gin_conakry",
        "gin_kankan",
        "gin_kindia",
        "gin_labe",
        "gin_mamou",
        "gin_nzerekore",
    )
    for grandeur in ("ghi", "dni", "dhi", "t2m", "rh2m", "kt")
)

# (table, colonne texte, colonne cle, cles, fragment de depart, fragment d'arrivee).
_REMPLACEMENTS: tuple[tuple[str, str, str, tuple[str, ...], str, str], ...] = (
    (
        "series_metadonnees",
        "note_publique",
        "code",
        _SERIES_HORAIRES,
        _PHRASE_HORAIRE_PILOTE,
        _PHRASE_HORAIRE_COUVERTURE,
    ),
    (
        "grandeurs_referentiel",
        "description",
        "code",
        ("ghi_exceedance",),
        "Pour une ville pilote donnée, le calcul reconstruit",
        "Pour une localité donnée (les 34 localités couvertes disposent de cette série), "
        "le calcul reconstruit",
    ),
    (
        "grandeurs_referentiel",
        "description",
        "code",
        ("rang_referentiel",),
        "rang_referentiel_spatial (rang d'une ville parmi les villes pilotes pour un même mois)",
        "rang_referentiel_spatial (rang d'une localité parmi les localités classées "
        "pour un même mois)",
    ),
    (
        "sources",
        "notes",
        "code",
        ("esmap_wapp",),
        "co-localisee < 2 km du pilote gin_kankan",
        "a environ 2 km du point de reference de la localite Kankan, gin_kankan",
    ),
)

# Textes portant encore « pilote » (ceux de rang_referentiel_spatial) : (avant, apres).
_PILOTE_RESTANTS: dict[tuple[str, str], tuple[int, int]] = {
    ("series_metadonnees", "note_publique"): (42, 6),
    ("grandeurs_referentiel", "description"): (3, 1),
    ("sources", "notes"): (1, 0),
}


def _echec(message: str) -> RuntimeError:
    return RuntimeError(f"Migration 132 : {message} Abandon sans ecriture partielle.")


def _libelles() -> list[tuple[str, str, str, str]]:
    """(code de serie, libelle de depart, libelle d'arrivee, localites.nom)."""
    lignes = []
    for alias, ancien, nom in _LOCALITES.values():
        for suffixe, gabarit in _GABARITS:
            lignes.append(
                (
                    f"{alias}_{suffixe}",
                    gabarit.format(alias=alias, lieu=ancien),
                    gabarit.format(alias=alias, lieu=nom),
                    nom,
                )
            )
    return lignes


def _renommer_libelles(*, sens: int) -> None:
    """``sens`` = 1 ecrit ``localites.nom`` ; ``sens`` = 0 restaure la graphie de depart."""
    lignes = _libelles()
    if len(lignes) != _LIBELLES_ATTENDUS:
        raise _echec(f"{_LIBELLES_ATTENDUS} libelles attendus, {len(lignes)} definis.")
    codes = [c for c, _, _, _ in lignes]
    noms = [n for _, _, _, n in lignes]
    departs = [a if sens == 1 else b for _, a, b, _ in lignes]
    arrivees = [b if sens == 1 else a for _, a, b, _ in lignes]
    if len(set(arrivees)) != len(arrivees):
        raise _echec("libelles d'arrivee repetes.")
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
    if resultat.rowcount != _LIBELLES_ATTENDUS:
        raise _echec(f"{resultat.rowcount} libelle(s) mis a jour au lieu de {_LIBELLES_ATTENDUS}.")

    doublons = bind.execute(
        sa.text("SELECT count(*) - count(DISTINCT libelle) FROM series_metadonnees")
    ).scalar_one()
    if doublons != 0:
        raise _echec(f"{doublons} libelle(s) en double apres reecriture.")


def _occurrences(table: str, colonne: str, cle: str) -> str:
    return (
        f'SELECT "{cle}" AS cle, (length("{colonne}") - '
        f"length(replace(\"{colonne}\", CAST(:f AS text), ''))) / length(CAST(:f AS text)) AS n "
        f'FROM "{table}" WHERE "{cle}" = ANY(:cles)'
    )


def _remplacer_textes(*, sens: int) -> None:
    """``sens`` = 1 decrit la couverture reelle ; ``sens`` = 0 restaure les textes."""
    bind = op.get_bind()
    for table, colonne, cle, cles, ancien, nouveau in _REMPLACEMENTS:
        depart, arrivee = (ancien, nouveau) if sens == 1 else (nouveau, ancien)
        cibles = list(cles)
        lus = bind.execute(
            sa.text(_occurrences(table, colonne, cle)), {"f": depart, "cles": cibles}
        ).all()
        conformes = {r.cle for r in lus if r.n == 1}
        if conformes != set(cibles) or len(lus) != len(cibles):
            raise _echec(
                f"{table}.{colonne} : {len(cibles) - len(conformes)} ligne(s) sans le "
                f"texte de depart exactement une fois."
            )
        arrivees_presentes = bind.execute(
            sa.text(
                f'SELECT count(*) FROM "{table}" '
                f'WHERE position(CAST(:f AS text) IN "{colonne}") > 0'
            ),
            {"f": arrivee},
        ).scalar_one()
        if arrivees_presentes != 0:
            raise _echec(f"{table}.{colonne} : texte d'arrivee deja present.")
        resultat = bind.execute(
            sa.text(
                f'UPDATE "{table}" SET "{colonne}" = '
                f'replace("{colonne}", CAST(:d AS text), CAST(:a AS text)) '
                f'WHERE "{cle}" = ANY(:cles) AND position(CAST(:d AS text) IN "{colonne}") > 0'
            ),
            {"d": depart, "a": arrivee, "cles": cibles},
        )
        if resultat.rowcount != len(cibles):
            raise _echec(
                f"{table}.{colonne} : {resultat.rowcount} ligne(s) mise(s) a jour "
                f"au lieu de {len(cibles)}."
            )

    for (table, colonne), (avant, apres) in _PILOTE_RESTANTS.items():
        attendu = apres if sens == 1 else avant
        restants = bind.execute(
            sa.text(f'SELECT count(*) FROM "{table}" WHERE "{colonne}" ~* \'pilote\'')
        ).scalar_one()
        if restants != attendu:
            raise _echec(
                f"{table}.{colonne} : {restants} texte(s) portant « pilote » au lieu de {attendu}."
            )


def upgrade() -> None:
    _renommer_libelles(sens=1)
    _remplacer_textes(sens=1)


def downgrade() -> None:
    _remplacer_textes(sens=0)
    _renommer_libelles(sens=0)

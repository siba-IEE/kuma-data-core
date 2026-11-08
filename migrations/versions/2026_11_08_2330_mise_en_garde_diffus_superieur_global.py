"""mise_en_garde_diffus_superieur_global

Revision ID: 134
Revises: 133
Create Date: 2026-11-08 23:30:00.000000+00:00

Migration de coherence editoriale, sans DDL ni donnee mesuree. Les series
NASA POWER de DHI longues (journalieres 1984-2020, mensuelles 1984-2025)
contiennent des jours, ou des mois, ou l'irradiation diffuse depasse
l'irradiation globale de la meme fenetre de serie, ce qui est physiquement
impossible : 8 222 jours sur 459 510 (34 series journalieres, toutes
touchees) et 7 mois sur 17 136 (3 series mensuelles). Les valeurs sont
celles que livre NASA POWER (``ALLSKY_SFC_SW_DIFF`` contre
``ALLSKY_SFC_SW_DWN``, meme unite) ; tous ces cas sont anterieurs a 2001,
annees pour lesquelles l'API annonce la source ``SRB`` (GEWEX SRB) au lieu
de ``SYN1DEG``. Aucun cas sur les series journalieres 2021-2025, sur la
climatologie mensuelle 2001-2020 ni chez CAMS.

La note publique de chaque serie DHI touchee recoit une mise en garde
chiffree. Elle est posee sur le DHI seul : le GHI garde le meme niveau de
part et d'autre de 2001 (5,43 contre 5,39 kWh/m2 par jour en moyenne sur
les 34 series), alors que le DHI baisse d'un quart (3,33 contre 2,51) ;
l'anomalie porte sur la part diffuse. Les chiffres sont figes : fenetres
closes, alimentees par des seeds commites sans reseau. Les series horaires
restent hors de cette migration, leur contenu dependant de l'environnement
(ingestion de masse sautee en CI).

Correction en place sous le trigger d'audit, ``modifie_le`` inchange.
Gardes : chaque note est attendue avec l'empreinte md5 exacte de son texte
de depart, nombre de lignes exact ; les chiffres annonces sont recomptes en
base avant ecriture ; aucune autre serie DHI journaliere ou mensuelle NASA
POWER ne presente de cas. Le downgrade retire la phrase ajoutee et verifie
l'empreinte de depart. Aucun reseau.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "134"
down_revision: str | Sequence[str] | None = "133"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Code de serie DHI -> (pas compares, pas ou DHI > GHI, md5 de la note de depart).
_CIBLES: dict[str, tuple[int, int, str]] = {
    "gin_beyla_dhi_nasa_power_journalier_1984_2020": (
        13515,
        548,
        "e932c751eda8d007b6cfc23873f9c073",
    ),
    "gin_boffa_dhi_nasa_power_journalier_1984_2020": (
        13515,
        29,
        "0379341d9e226080e562683558e51c15",
    ),
    "gin_boke_centre_dhi_nasa_power_journalier_1984_2020": (
        13515,
        29,
        "f2040ddc3f76036f83d805028bcbd456",
    ),
    "gin_conakry_dhi_nasa_power_journalier_1984_2020": (
        13515,
        52,
        "0ebe8ae0c1282cb018ca4b0e20a1a7e7",
    ),
    "gin_coyah_dhi_nasa_power_journalier_1984_2020": (
        13515,
        52,
        "b0c5c8e74e3e91b7f2facc4bcc3e3a57",
    ),
    "gin_dabola_dhi_nasa_power_journalier_1984_2020": (
        13515,
        240,
        "33648f473a2da39201403e04f5d6fdbc",
    ),
    "gin_dalaba_dhi_nasa_power_journalier_1984_2020": (
        13515,
        200,
        "acb41f8a254ffb4876a94e2b115e8ef8",
    ),
    "gin_dinguiraye_dhi_nasa_power_journalier_1984_2020": (
        13515,
        43,
        "1e95123ec756749afa9278b5358c0e1c",
    ),
    "gin_dubreka_dhi_nasa_power_journalier_1984_2020": (
        13515,
        52,
        "427c1f3b0b90afebb539f7e056f39a47",
    ),
    "gin_faranah_centre_dhi_nasa_power_journalier_1984_2020": (
        13515,
        75,
        "905af10fd0e90ec0cf80d58d03e5cf9c",
    ),
    "gin_forecariah_dhi_nasa_power_journalier_1984_2020": (
        13515,
        52,
        "a09bee03e5f880ae76ebb9bf26e2b5e1",
    ),
    "gin_fria_dhi_nasa_power_journalier_1984_2020": (
        13515,
        300,
        "d307d6386df1c668e28e73946ea146e9",
    ),
    "gin_gaoual_dhi_nasa_power_journalier_1984_2020": (
        13515,
        31,
        "19d3391ab5b2f57c0e1c0508d5963c0b",
    ),
    "gin_gueckedou_dhi_nasa_power_journalier_1984_2020": (
        13515,
        435,
        "17ad517b051a5a33dd868bcfea933363",
    ),
    "gin_kankan_dhi_nasa_power_journalier_1984_2020": (
        13515,
        110,
        "c5cec31fda55b7043fb94df4b24de954",
    ),
    "gin_kerouane_dhi_nasa_power_journalier_1984_2020": (
        13515,
        287,
        "187e417dfc851903d08eea142e984ed8",
    ),
    "gin_kindia_dhi_nasa_power_journalier_1984_2020": (
        13515,
        200,
        "8be55199a0f88b4cf3c0b2b77bdb4ac0",
    ),
    "gin_kissidougou_dhi_nasa_power_journalier_1984_2020": (
        13515,
        192,
        "04b70c8f92163544c2699ac98be39ceb",
    ),
    "gin_koubia_dhi_nasa_power_journalier_1984_2020": (
        13515,
        96,
        "177fdb305ec90d20b9150698859331a2",
    ),
    "gin_koundara_dhi_nasa_power_journalier_1984_2020": (
        13515,
        37,
        "16bc394dab5a9f3de63646d8d9a8f0e4",
    ),
    "gin_kouroussa_dhi_nasa_power_journalier_1984_2020": (
        13515,
        110,
        "8f9c78b0d7ecac1aaeedea919786bc9e",
    ),
    "gin_labe_dhi_nasa_power_journalier_1984_2020": (13515, 72, "ec88e42a68ba3c3cdfc27e28b5bc28a5"),
    "gin_lelouma_dhi_nasa_power_journalier_1984_2020": (
        13515,
        72,
        "8782cec237f66a3b14f014033151432b",
    ),
    "gin_lola_dhi_nasa_power_journalier_1984_2020": (
        13515,
        1049,
        "04ad71c9f87497f4a9203ebcb4cee8b9",
    ),
    "gin_lola_dhi_nasa_power_mensuel_1984_2025": (504, 1, "dcddcdcc18cc88c7270425370790d52f"),
    "gin_macenta_dhi_nasa_power_journalier_1984_2020": (
        13515,
        848,
        "a9a4aad90e64b7b476eddefb724dcbb7",
    ),
    "gin_mali_dhi_nasa_power_journalier_1984_2020": (13515, 24, "4676f9983579626aaca4af512c4a82be"),
    "gin_mamou_dhi_nasa_power_journalier_1984_2020": (
        13515,
        200,
        "65aae6e8717bf0a86ae113ca198c79cf",
    ),
    "gin_mandiana_dhi_nasa_power_journalier_1984_2020": (
        13515,
        69,
        "7487cae6a7f20afc4a6e9e88296351b7",
    ),
    "gin_nzerekore_dhi_nasa_power_journalier_1984_2020": (
        13515,
        1049,
        "3bcf2a10cb6046202905be871363316d",
    ),
    "gin_nzerekore_dhi_nasa_power_mensuel_1984_2025": (504, 1, "1ef8995aa01b0fcc68698397e68c1c45"),
    "gin_pita_dhi_nasa_power_journalier_1984_2020": (13515, 72, "42a66d3325bc2da41350f174af229f99"),
    "gin_siguiri_dhi_nasa_power_journalier_1984_2020": (
        13515,
        35,
        "c7894f5be9ee80ee08421a3b18e76426",
    ),
    "gin_telimele_dhi_nasa_power_journalier_1984_2020": (
        13515,
        300,
        "18c2208b1a3fe5ade11ebd3e4db4e64b",
    ),
    "gin_tougue_dhi_nasa_power_journalier_1984_2020": (
        13515,
        96,
        "d29623b3292cd140cbcf0ebc042f4a9b",
    ),
    "gin_yomou_dhi_nasa_power_journalier_1984_2020": (
        13515,
        1166,
        "72890a221b6d87e8fbd36f517796edaf",
    ),
    "gin_yomou_dhi_nasa_power_mensuel_1984_2025": (504, 5, "54e438d0c05d20b05f821b755ecd0f2d"),
}
_CIBLES_ATTENDUES = 37

# Recompte par serie DHI NASA POWER journaliere ou mensuelle, appariee au GHI
# de la meme fenetre (localite, source, bornes, granularite).
_RECOMPTE = """
WITH paires AS (
    SELECT sm_dhi.code, CAST(extract(YEAR FROM g.instant_mesure) AS int) AS annee,
           d.valeur AS dhi, g.valeur AS ghi
    FROM mesures_ressource g
    JOIN series_metadonnees sm_ghi ON sm_ghi.id = g.serie_id
    JOIN series_metadonnees sm_dhi
         ON sm_dhi.localite_id = sm_ghi.localite_id
        AND sm_dhi.source_id = sm_ghi.source_id
        AND sm_dhi.periode_debut = sm_ghi.periode_debut
        AND sm_dhi.periode_fin IS NOT DISTINCT FROM sm_ghi.periode_fin
        AND sm_dhi.granularite IS NOT DISTINCT FROM sm_ghi.granularite
        AND sm_dhi.grandeur_code = 'dhi'
    JOIN mesures_ressource d
         ON d.serie_id = sm_dhi.id AND d.instant_mesure = g.instant_mesure
    JOIN sources s ON s.id = sm_ghi.source_id
    WHERE s.code = 'nasa_power' AND sm_ghi.grandeur_code = 'ghi'
      AND g.valide_au IS NULL AND d.valide_au IS NULL
    UNION ALL
    SELECT sm_dhi.code, g.annee, d.valeur, g.valeur
    FROM mesures_ressource_mensuelles g
    JOIN series_metadonnees sm_ghi ON sm_ghi.id = g.serie_id
    JOIN series_metadonnees sm_dhi
         ON sm_dhi.localite_id = sm_ghi.localite_id
        AND sm_dhi.source_id = sm_ghi.source_id
        AND sm_dhi.periode_debut = sm_ghi.periode_debut
        AND sm_dhi.periode_fin IS NOT DISTINCT FROM sm_ghi.periode_fin
        AND sm_dhi.granularite IS NOT DISTINCT FROM sm_ghi.granularite
        AND sm_dhi.grandeur_code = 'dhi'
    JOIN mesures_ressource_mensuelles d
         ON d.serie_id = sm_dhi.id AND d.annee = g.annee AND d.mois = g.mois
    JOIN sources s ON s.id = sm_ghi.source_id
    WHERE s.code = 'nasa_power' AND sm_ghi.grandeur_code = 'ghi'
      AND g.valide_au IS NULL AND d.valide_au IS NULL
)
SELECT code, count(*) AS n, count(*) FILTER (WHERE dhi > ghi) AS v,
       count(*) FILTER (WHERE dhi > ghi AND annee >= 2001) AS v_depuis_2001
FROM paires GROUP BY code
"""


def _echec(message: str) -> RuntimeError:
    return RuntimeError(f"Migration 134 : {message} Abandon sans ecriture partielle.")


def _nombre(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def mise_en_garde(code: str, compares: int, cas: int) -> str:
    """Phrase ajoutee a la note : chiffres de la serie, au pas journalier ou mensuel."""
    pct = f"{100 * cas / compares:.1f}".replace(".", ",")
    journalier = "_journalier_" in code
    pas = "jours" if journalier else "mois"
    grandeur = (
        "une irradiation diffuse superieure a l'irradiation globale"
        if journalier
        else "une moyenne d'irradiation diffuse superieure a celle de l'irradiation globale"
    )
    # « jour » s'accorde au singulier, « mois » est invariable.
    unite = "jour" if journalier and cas == 1 else pas
    if cas == 1:
        verbe, rappel, cible = "presente", f"Ce {unite} est anterieur", "ce"
    else:
        verbe, rappel, cible = "presentent", f"Ces {unite} sont tous anterieurs", "ces"
    return (
        f" Mise en garde : sur les {_nombre(compares)} {pas} ou l'irradiation globale et "
        f"l'irradiation diffuse sont toutes deux disponibles, {_nombre(cas)} ({pct} %) "
        f"{verbe} {grandeur}, ce qui est physiquement impossible. {rappel} a 2001, "
        "periode pour laquelle NASA POWER fournit un rayonnement issu du jeu satellitaire "
        "GEWEX SRB ; les valeurs sont conservees telles que fournies par la source. Pour "
        f"{cible} {unite}, utiliser la part diffuse avec prudence, par exemple en la "
        "limitant a l'irradiation globale."
    )


def _verifier_comptes() -> None:
    """Les chiffres annonces sont ceux de la base ; aucune autre serie touchee."""
    if len(_CIBLES) != _CIBLES_ATTENDUES:
        raise _echec(f"{_CIBLES_ATTENDUES} series attendues, {len(_CIBLES)} definies.")
    lignes = op.get_bind().execute(sa.text(_RECOMPTE)).all()
    comptes = {r.code: (r.n, r.v) for r in lignes}
    recents = sum(r.v_depuis_2001 for r in lignes)
    if recents != 0:
        raise _echec(f"{recents} cas en 2001 ou apres : la phrase les dit tous anterieurs.")
    touchees = {code for code, (_, v) in comptes.items() if v > 0}
    if touchees != set(_CIBLES):
        raise _echec(
            f"series touchees en base ({len(touchees)}) differentes des cibles ({len(_CIBLES)})."
        )
    ecarts = [c for c, (n, v, _) in _CIBLES.items() if comptes[c] != (n, v)]
    if ecarts:
        raise _echec(f"{len(ecarts)} serie(s) dont le recompte differe : {ecarts[:3]}.")


def _empreintes_conformes(attendues: dict[str, str]) -> None:
    lus = dict(
        op.get_bind()
        .execute(
            sa.text("SELECT code, md5(note_publique) FROM series_metadonnees WHERE code = ANY(:c)"),
            {"c": list(attendues)},
        )
        .all()
    )
    ecarts = [c for c, h in attendues.items() if lus.get(c) != h]
    if ecarts:
        raise _echec(f"{len(ecarts)} note(s) hors du texte attendu : {ecarts[:3]}.")


def _ecrire(codes: list[str], sql: str, ajouts: list[str]) -> None:
    resultat = op.get_bind().execute(sa.text(sql), {"codes": codes, "ajouts": ajouts})
    if resultat.rowcount != _CIBLES_ATTENDUES:
        raise _echec(f"{resultat.rowcount} note(s) mise(s) a jour au lieu de {_CIBLES_ATTENDUES}.")


_MARQUEUR = "SELECT count(*) FROM series_metadonnees WHERE note_publique ~ 'GEWEX SRB'"


def upgrade() -> None:
    bind = op.get_bind()
    _verifier_comptes()
    _empreintes_conformes({c: h for c, (_, _, h) in _CIBLES.items()})
    deja = bind.execute(sa.text(_MARQUEUR)).scalar_one()
    if deja != 0:
        raise _echec(f"{deja} note(s) portant deja la mise en garde.")
    codes = list(_CIBLES)
    ajouts = [mise_en_garde(c, n, v) for c, (n, v, _) in _CIBLES.items()]
    _ecrire(
        codes,
        """
        UPDATE series_metadonnees s SET note_publique = s.note_publique || v.ajout
        FROM unnest(CAST(:codes AS text[]), CAST(:ajouts AS text[])) AS v(code, ajout)
        WHERE s.code = v.code
        """,
        ajouts,
    )
    termines = bind.execute(
        sa.text(
            """
            SELECT count(*) FROM series_metadonnees s
            JOIN unnest(CAST(:codes AS text[]), CAST(:ajouts AS text[])) AS v(code, ajout)
              ON s.code = v.code
            WHERE right(s.note_publique, length(v.ajout)) = v.ajout
            """
        ),
        {"codes": codes, "ajouts": ajouts},
    ).scalar_one()
    porteuses = bind.execute(sa.text(_MARQUEUR)).scalar_one()
    if termines != _CIBLES_ATTENDUES or porteuses != _CIBLES_ATTENDUES:
        raise _echec(
            f"{termines} note(s) terminee(s) par leur mise en garde, {porteuses} la portant, "
            f"au lieu de {_CIBLES_ATTENDUES}."
        )


def downgrade() -> None:
    codes = list(_CIBLES)
    ajouts = [mise_en_garde(c, n, v) for c, (n, v, _) in _CIBLES.items()]
    _ecrire(
        codes,
        """
        UPDATE series_metadonnees s
        SET note_publique = left(s.note_publique, length(s.note_publique) - length(v.ajout))
        FROM unnest(CAST(:codes AS text[]), CAST(:ajouts AS text[])) AS v(code, ajout)
        WHERE s.code = v.code AND right(s.note_publique, length(v.ajout)) = v.ajout
        """,
        ajouts,
    )
    _empreintes_conformes({c: h for c, (_, _, h) in _CIBLES.items()})

"""ecart_dni_cams_climato_28_communes

Revision ID: 118
Revises: 117
Create Date: 2026-08-11 09:00:00

Residu du cadrage densification, cote au plus bas du chantier : l'ecart
relatif DNI inter-source **climato 2004-2020** existait aux 6 pilotes
(migration 072) mais pas aux 28 communes chef-lieu, alors que son substrat
brut y est complet depuis la migration 095 (CAMS DNI climato) et la 087
(NASA DNI climato). Ce lot ferme le residu : **28 series calculees** +
**5 684 lignes** ``grandeurs_metier`` (203 mois communs 2004-02 -> 2020-12
par commune), **zero reseau, calcul integralement deterministe depuis la
base** via l'orchestrateur de la 072, reutilise sans modification.

Miroir strict de la 072 (formule ``(nasa - cams)/cams x 100``, confiance
derivee B, ``methode_collecte='calcul_derive'``, ``granularite`` NULL,
source ``kuma_calculs``), avec les disciplines contemporaines :

- enumeration DATA-DRIVEN des 28 communes (CAMS DNI climato present, NASA
  DNI climato present, ecart climato absent), garde ``len != 28`` ;
- resolution des series nouvelles scopee par codes (les 6 series pilotes de
  la 072 partagent grandeur et source) ;
- garde d'egalite stricte sur le nombre de lignes inserees (jeu fige) ;
- ``note_publique`` renseignee a l'insertion.

Le caveat de fond de la 072 est reconduit dans le commentaire editorial :
l'offset moyen (NASA lit moins de DNI que CAMS) est un ecart de produits,
pas la correction Harmattan ; ne pas sur-interpreter le signe.

Downgrade : DELETE des lignes (via series) puis des 28 series. La grandeur
``ecart_relatif_dni_cams`` appartient a la 072 et n'est pas touchee.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.services.grandeurs.ecart_dni_cams import (
    GRANDEUR_ECART_DNI_CAMS,
    ContexteVilleEcartDniCams,
    calculer_et_inserer_ecart_dni_cams,
)

# revision identifiers, used by Alembic.
revision: str = "118"
down_revision: str | Sequence[str] | None = "117"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Constantes (miroir 072) ===============================================
_SOURCE_KUMA_CALCULS = "kuma_calculs"
_METHODE_COLLECTE_CALCUL = "calcul_derive"
_PLAGE = "2004_2020"
_PERIODE_DEBUT = date(2004, 2, 1)  # debut reel de la fenetre commune (CAMS 2004-02)
_PERIODE_FIN = date(2020, 12, 31)
_NB_COMMUNES = 28
_MOIS_FENETRE = 203
_LIGNES_ATTENDUES = _NB_COMMUNES * _MOIS_FENETRE  # 5 684


def _code_serie_calculee(commune_code: str) -> str:
    return f"{commune_code}_{GRANDEUR_ECART_DNI_CAMS}_kuma_calculs_{_PLAGE}"


def _code_serie_nasa(commune_code: str) -> str:
    return f"{commune_code}_dni_power_2001_2020"


def _code_serie_cams(commune_code: str) -> str:
    return f"{commune_code}_dni_cams_2004_2020"


def _commentaire(ville: str) -> str:
    return (
        f"Serie calculee Kuma ecart_relatif_dni_cams : ecart relatif inter-source "
        f"du DNI entre NASA POWER (primaire, numerateur) et CAMS Radiation "
        f"(reference d'ecart aerosol-corrigee, denominateur), formule "
        f"(nasa - cams)/cams x 100, iso-periode 2004-2020 mois-a-mois. Localite : "
        f"{ville} (chef-lieu de prefecture), Guinee. Niveau de confiance derive 'B' "
        f"(signal indirect par construction). CAVEAT reconduit de la migration 072 : "
        f"l'offset moyen observe (NASA lit moins de DNI que CAMS) est un ecart de "
        f"FOND entre produits (NASA/CERES vs CAMS/Heliosat-4), PAS la correction "
        f"Harmattan ; le signal aerosol releve de la SAISONNALITE de l'ecart. Ne pas "
        f"sur-interpreter le signe. Residu du cadrage densification ferme ici : le "
        f"substrat brut etait aux 28 depuis les migrations 087 et 095, seul le "
        f"calcul manquait. Meme orchestrateur que les pilotes, sans modification."
    )


def _note_publique(ville: str) -> str:
    return (
        f"Ecart relatif entre deux estimations satellitaires de l'irradiation "
        f"directe (DNI) : NASA POWER comparee a Copernicus CAMS Radiation, mois "
        f"par mois sur 2004-2020, en pourcentage signe. Calcule par Kuma a partir "
        f"des series des deux sources pour {ville}, Guinee. C'est une mesure du "
        f"desaccord entre sources, utile pour juger l'incertitude locale, pas une "
        f"mesure de la ressource elle-meme. Niveau de confiance B : derive de "
        f"donnees de modele, non valide par une mesure au sol a ce jour."
    )


def _communes_cibles(bind: sa.engine.Connection) -> list[tuple[int, str, str]]:
    """Enumeration data-driven des 28 communes : CAMS DNI climato (095) present,
    NASA DNI climato (087) present, ecart climato absent (exclut les pilotes,
    couverts par la 072)."""
    rows = bind.execute(
        sa.text(
            """
            SELECT l.id, l.code, l.nom FROM localites l
            WHERE EXISTS (
                SELECT 1 FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
                WHERE sm.localite_id = l.id AND s.code = 'cams_radiation'
                  AND sm.grandeur_code = 'dni' AND sm.granularite = 'mensuel'
                  AND sm.periode_debut = '2004-02-01')
              AND EXISTS (
                SELECT 1 FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
                WHERE sm.localite_id = l.id AND s.code = 'nasa_power'
                  AND sm.grandeur_code = 'dni' AND sm.granularite = 'mensuel'
                  AND sm.periode_fin = '2020-12-31')
              AND NOT EXISTS (
                SELECT 1 FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
                WHERE sm.localite_id = l.id AND s.code = 'kuma_calculs'
                  AND sm.grandeur_code = :g AND sm.periode_debut = '2004-02-01')
            ORDER BY l.code
            """
        ),
        {"g": GRANDEUR_ECART_DNI_CAMS},
    ).all()
    return [(int(r.id), str(r.code), str(r.nom)) for r in rows]


def upgrade() -> None:
    bind = op.get_bind()

    # === 1. Grandeur (posee par la 072) + source kuma_calculs ================
    grandeur_ok = bind.execute(
        sa.text("SELECT 1 FROM grandeurs_referentiel WHERE code = :c AND actif = TRUE"),
        {"c": GRANDEUR_ECART_DNI_CAMS},
    ).scalar_one_or_none()
    if grandeur_ok is None:
        raise RuntimeError(
            f"Migration 118 : grandeur {GRANDEUR_ECART_DNI_CAMS!r} introuvable/inactive "
            f"(migration 072)."
        )
    source_kuma_calculs_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_KUMA_CALCULS},
    ).scalar_one_or_none()
    if source_kuma_calculs_id is None:
        raise RuntimeError("Migration 118 : source 'kuma_calculs' introuvable (migration 025).")

    # === 2. Enumeration data-driven des 28 communes (garde len != 28) ========
    points = _communes_cibles(bind)
    if len(points) != _NB_COMMUNES:
        raise RuntimeError(
            f"Migration 118 : attendu {_NB_COMMUNES} communes, enumere {len(points)}."
        )
    localite_id_par_code = {code: lid for lid, code, _ in points}
    nom_par_code = {code: nom for _, code, nom in points}

    # === 3. Insertion des 28 series calculees (note_publique a l'insertion) ==
    series_table = sa.table(
        "series_metadonnees",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("localite_id", sa.BigInteger),
        sa.column("grandeur_code", sa.String),
        sa.column("source_id", sa.BigInteger),
        sa.column("periode_debut", sa.Date),
        sa.column("periode_fin", sa.Date),
        sa.column("methode_collecte", sa.String),
        sa.column("commentaire_editorial", sa.Text),
        sa.column("note_publique", sa.Text),
    )
    series_a_inserer: list[dict[str, Any]] = [
        {
            "code": _code_serie_calculee(code),
            "libelle": (
                f"ecart_relatif_dni_cams mensuel {nom_par_code[code]} {_PLAGE.replace('_', '-')}"
            ),
            "localite_id": localite_id_par_code[code],
            "grandeur_code": GRANDEUR_ECART_DNI_CAMS,
            "source_id": int(source_kuma_calculs_id),
            "periode_debut": _PERIODE_DEBUT,
            "periode_fin": _PERIODE_FIN,
            "methode_collecte": _METHODE_COLLECTE_CALCUL,
            "commentaire_editorial": _commentaire(nom_par_code[code]),
            "note_publique": _note_publique(nom_par_code[code]),
        }
        for code in sorted(localite_id_par_code)
    ]
    assert len(series_a_inserer) == _NB_COMMUNES, (
        f"Attendu {_NB_COMMUNES} series, obtenu {len(series_a_inserer)}"
    )
    op.bulk_insert(series_table, series_a_inserer)

    # Resolution scopee par codes : les 6 series pilotes (072) partagent
    # grandeur et source, la requete de la 072 les attraperait.
    codes_nouveaux = [ligne["code"] for ligne in series_a_inserer]
    serie_id_par_localite: dict[int, int] = {
        int(r.localite_id): int(r.id)
        for r in bind.execute(
            sa.text("SELECT id, localite_id FROM series_metadonnees WHERE code = ANY(:codes)"),
            {"codes": codes_nouveaux},
        ).all()
    }
    if len(serie_id_par_localite) != _NB_COMMUNES:
        raise RuntimeError(
            f"Migration 118 : {len(serie_id_par_localite)} series resolues "
            f"(attendu {_NB_COMMUNES})."
        )

    # === 4. Calcul + insertion (5 684 lignes attendues, garde stricte) =======
    session = Session(bind=bind)
    try:
        contextes: list[ContexteVilleEcartDniCams] = [
            {
                "localite_id": localite_id_par_code[code],
                "code_serie_nasa": _code_serie_nasa(code),
                "code_serie_cams": _code_serie_cams(code),
                "series_metadonnees_id": serie_id_par_localite[localite_id_par_code[code]],
            }
            for code in sorted(localite_id_par_code)
        ]
        resultat = calculer_et_inserer_ecart_dni_cams(session=session, contextes_villes=contextes)
        if resultat["nb_insere"] != _LIGNES_ATTENDUES:
            raise RuntimeError(
                f"Migration 118 : {resultat['nb_insere']} lignes inserees, attendu "
                f"{_LIGNES_ATTENDUES} ({_NB_COMMUNES} x {_MOIS_FENETRE} mois, jeu fige)."
            )
        op.execute(
            f"-- Migration 118 : 28 series ecart_relatif_dni_cams climato 2004-2020 "
            f"(kuma_calculs) + {resultat['nb_insere']} lignes grandeurs_metier "
            f"(28 communes x 203 mois, residu du cadrage densification ferme)."
        )
    finally:
        session.close()


def downgrade() -> None:
    bind = op.get_bind()
    codes_series = [
        str(r.code)
        for r in bind.execute(
            sa.text(
                """
                SELECT sm.code FROM series_metadonnees sm
                JOIN sources s ON s.id = sm.source_id
                JOIN localites l ON l.id = sm.localite_id
                WHERE s.code = 'kuma_calculs' AND sm.grandeur_code = :g
                  AND sm.periode_debut = '2004-02-01'
                  AND l.code NOT IN ('gin_conakry_kaloum', 'gin_kankan', 'gin_kindia',
                                     'gin_labe', 'gin_mamou', 'gin_nzerekore')
                """
            ),
            {"g": GRANDEUR_ECART_DNI_CAMS},
        ).all()
    ]
    op.execute(
        sa.text(
            "DELETE FROM grandeurs_metier WHERE series_metadonnees_id IN "
            "(SELECT id FROM series_metadonnees WHERE code = ANY(:codes))"
        ).bindparams(sa.bindparam("codes", value=codes_series))
    )
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_series)
        )
    )

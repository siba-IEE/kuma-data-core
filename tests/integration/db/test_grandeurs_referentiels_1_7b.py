"""Tests d'integration des 3 grandeurs F1 calculee_volee.

Couvre les cas de test :

- 936 nouvelles lignes grandeurs_metier ventilees par grandeur
  (216 ecart + 360 rang_temp + 360 rang_spat).
- decompte cumule grandeurs_metier.
- grandeurs_referentiel : rang_referentiel singulier desactivee
  (actif=FALSE) et rang_referentiel_temporel +
  rang_referentiel_spatial actives.
- 18 series calculees avec nommage correct.
- regression non-doublon EXCLUDE grandeurs_metier (les 936
  nouvelles n'entrent pas en collision avec les 1 614 existantes).
- niveau_confiance_derive='B' uniforme sur les 936 nouvelles lignes.
- valeurs ecart_relatif_referentiel dans plage attendue
  (Afrique tropicale ouest, ecarts modestes ±15%).
- valeurs rang_referentiel_spatial entre 1 et 6 (rang ordinal).

Pattern herite des tests d'integration precedents (db_session fixture).
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from kuma_data_core.db.models.grandeurs_metier import GrandeurMetier

pytestmark = pytest.mark.integration


_GRANDEURS_1_7B: tuple[str, ...] = (
    "ecart_relatif_referentiel",
    "rang_referentiel_temporel",
    "rang_referentiel_spatial",
)

# Les 6 villes pilotes du livrable (l'atlas Temps 1 etend l'ecart au-dela).
_LOCALITES_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)


def test_ti53_decomptes_par_grandeur_1_7b(db_session: Session) -> None:
    """936 lignes grandeurs_metier (216 + 360 + 360) **aux 6 pilotes**.

    Scope explicite aux 6 villes pilotes : l'atlas Temps 1 (migration 091) etend
    ``ecart_relatif_referentiel`` aux 28 communes. Ce test verifie le
    livrable, pas le total global de l'ecart."""
    rows = db_session.execute(
        text(
            """
            SELECT grandeur_code, COUNT(*) AS n FROM grandeurs_metier
            WHERE grandeur_code = ANY(:codes) AND valide_au IS NULL
              AND localite_id IN (SELECT id FROM localites WHERE code = ANY(:pilotes))
            GROUP BY grandeur_code ORDER BY grandeur_code
            """
        ),
        {"codes": list(_GRANDEURS_1_7B), "pilotes": list(_LOCALITES_PILOTES)},
    ).all()
    decompte = {r.grandeur_code: r.n for r in rows}
    assert decompte["ecart_relatif_referentiel"] == 216
    assert decompte["rang_referentiel_temporel"] == 360
    assert decompte["rang_referentiel_spatial"] == 360
    assert sum(decompte.values()) == 936


def test_ti54_grandeurs_metier_cumule_post_1_7b(db_session: Session) -> None:
    """decompte cumule grandeurs_metier.

    Evolution :
    - migration 043 : 1 614 + 936 (ecart_relatif
      + rang_referentiel_temporel + rang_referentiel_spatial) = 2 550 lignes.
    - migration 051 : +6 240 lignes climato sur 3
      grandeurs calculees Kuma (hep 2 340 + productible_specifique_theorique
      2 340 + fraction_diffuse 1 560). Les calculees
      sont stockees comme les brutes, ratio des moyennes mensuelles.
    - migration 072 : +1 218 lignes
      ecart_relatif_dni_cams (203 mois communs x 6 villes, iso-periode
      2004-2020). Total : 8 790 + 1 218 = 10 008 lignes.
    """
    total = db_session.scalar(
        select(func.count()).select_from(GrandeurMetier).where(GrandeurMetier.valide_au.is_(None))
    )
    # Exact : DHI daily depuis seed offline -> deterministe.
    # 10 020 = 10 008 + 12 (fraction_diffuse au max 390, seed entierement muri).
    # + 374 (degenerescence_pixel, densification migration 090) = 10 394.
    # + 2 232 (atlas Temps 1 migration 091 : ecart GHI 28 communes x 36 = 1 008
    # + ecart DNI recent 34 points x 36 = 1 224) = 12 626.
    # + 34 580 (parite A1 migration 092 : hep/psp/fd climato+recent aux 28 communes,
    # 28 x 1 235 lignes/commune = meme traitement que les 6 pilotes) = 47 206.
    # + 3 808 (parite A2 migration 093 : humidex/variabilite/rang_temporel/indicateur aux
    # 28 communes, 28 x 136 lignes/commune (65 humidex + 5 variabilite + 60 rang_temporel
    # + 6 indicateur) = meme traitement que les 6 pilotes) = 51 014.
    # + 5 684 (migration 118 : ecart_relatif_dni_cams climato 2004-2020 aux
    # 28 communes, 28 x 203 mois) = 56 698.
    assert total == 56698


def test_ti55_grandeurs_referentiel_post_d39(db_session: Session) -> None:
    """grandeurs_referentiel 26 entrees.

    - rang_referentiel singulier desactivee (actif=FALSE)
    - rang_referentiel_temporel + rang_referentiel_spatial actives (nouvelles)
    - ecart_relatif_referentiel deja seedee, restee active
    - vent_2m, vent_10m, albedo_surface actives (migration 047)
    - ghi_exceedance active (migration 049, F1 calculee_volee)
    - ecart_relatif_dni_cams active (migration 072, F1 calculee_volee,
      ecart DNI NASA vs CAMS)
    Total : 22 + 3 + 1 + 1 = 27 entrees.
    """
    rows = db_session.execute(
        text(
            """
            SELECT code, actif FROM grandeurs_referentiel
            WHERE code IN ('rang_referentiel', 'rang_referentiel_temporel',
                           'rang_referentiel_spatial', 'ecart_relatif_referentiel',
                           'vent_2m', 'vent_10m', 'albedo_surface',
                           'ghi_exceedance', 'ecart_relatif_dni_cams')
            ORDER BY code
            """
        )
    ).all()
    par_code = {r.code: r.actif for r in rows}
    assert par_code["rang_referentiel"] is False, (
        "rang_referentiel singulier doit etre desactivee (D-39)"
    )
    assert par_code["rang_referentiel_temporel"] is True
    assert par_code["rang_referentiel_spatial"] is True
    assert par_code["ecart_relatif_referentiel"] is True
    assert par_code["vent_2m"] is True, "vent_2m doit etre active (Phase 2 vague 1)"
    assert par_code["vent_10m"] is True, "vent_10m doit etre active (Phase 2 vague 1)"
    assert par_code["albedo_surface"] is True, "albedo_surface doit etre active (Phase 2 vague 1)"
    assert par_code["ghi_exceedance"] is True, (
        "ghi_exceedance doit etre active (Phase 2 vague 1 chantier B)"
    )
    assert par_code["ecart_relatif_dni_cams"] is True, (
        "ecart_relatif_dni_cams doit etre active (Vague 4 Lot B)"
    )

    # Total : 26 + 1 (ecart_relatif_dni_cams)
    # + 1 (poa_bifacial) + 1 (precipitation)
    # + 2 (pm2_5, pm10, migration 081)
    # + 1 (taux_salissure_proxy, migration 082)
    # + 1 (pr_realiste, PR realiste saisonnier migration 083) = 33
    # + 1 (degenerescence_pixel, densification migration 090) = 34.
    total = db_session.execute(text("SELECT COUNT(*) FROM grandeurs_referentiel")).scalar_one()
    assert total == 34


def test_ti56_18_series_calculees_1_7b(db_session: Session) -> None:
    """18 series calculees (3 grandeurs x 6 pilotes) avec nommage correct.

    Scope aux 6 pilotes : l'atlas Temps 1 (091) cree des series calculees
    ``ecart_relatif_referentiel`` supplementaires aux 28 communes."""
    rows = db_session.execute(
        text(
            """
            SELECT sm.code, sm.grandeur_code, s.code AS source_code
            FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            WHERE sm.grandeur_code = ANY(:codes)
              AND s.code = 'kuma_calculs'
              AND sm.localite_id IN (SELECT id FROM localites WHERE code = ANY(:pilotes))
            ORDER BY sm.code
            """
        ),
        {"codes": list(_GRANDEURS_1_7B), "pilotes": list(_LOCALITES_PILOTES)},
    ).all()
    assert len(rows) == 18

    # Nommage : tous commencent par gin_<ville>_ et finissent par kuma_calculs_<plage>
    for r in rows:
        assert r.code.startswith("gin_"), f"Naming D-32 violation : {r.code}"
        assert "_kuma_calculs_" in r.code, f"Source dans code manquante : {r.code}"

    # 6 series par grandeur
    decompte_par_grandeur: dict[str, int] = {}
    for r in rows:
        decompte_par_grandeur[r.grandeur_code] = decompte_par_grandeur.get(r.grandeur_code, 0) + 1
    for grandeur in _GRANDEURS_1_7B:
        assert decompte_par_grandeur[grandeur] == 6


def test_ti57_regression_non_doublon_exclude(db_session: Session) -> None:
    """aucune doublure sur la cle EXCLUDE.

    Verifie que la migration 037 corrective (EXCLUDE plage-aware)
    a bien permis l'insertion des 936 nouvelles lignes sans collision
    avec les 1 614 existantes.
    """
    n_doublons = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM (
                SELECT grandeur_code, localite_id, series_metadonnees_id,
                       periode_type, annee_debut, annee_fin, COALESCE(mois, 0),
                       version_formule, COUNT(*) AS n
                FROM grandeurs_metier
                WHERE valide_au IS NULL
                GROUP BY grandeur_code, localite_id, series_metadonnees_id,
                         periode_type, annee_debut, annee_fin, COALESCE(mois, 0),
                         version_formule
                HAVING COUNT(*) > 1
            ) d
            """
        )
    ).scalar_one()
    assert n_doublons == 0


def test_ti58_niveau_confiance_b_uniforme_1_7b(db_session: Session) -> None:
    """niveau_confiance_derive='B' uniforme sur les 936 nouvelles lignes."""
    niveaux = {
        r[0]
        for r in db_session.execute(
            select(GrandeurMetier.niveau_confiance_derive)
            .where(GrandeurMetier.grandeur_code.in_(list(_GRANDEURS_1_7B)))
            .where(GrandeurMetier.valide_au.is_(None))
            .distinct()
        ).all()
    }
    assert niveaux == {"B"}


def test_ti59_ecart_relatif_dans_borne_physique(db_session: Session) -> None:
    """valeurs ecart_relatif_referentiel dans la borne physique ``[-100, +100]``.

    Post-migration 046 (correction du bug 045), l'écart est désormais
    calculé avec un garde-fou ``SEUIL_SARAH3_MIN_DEFAUT = 0.5 kWh/m²/jour``
    : si la valeur SARAH-3 mensuelle est en dessous (donnée amont
    pathologique, sentinelle ou couverture satellitaire dégradée), la
    ligne est stockée avec ``valeur = NULL`` plutôt qu'une amplification
    mathématiquement absurde par 1/s.

    Le test conserve l'assertion ``len(rows) == 216`` parce que la
    migration 046 ré-insère les 216 lignes (6 villes x 36 mois), seule
    la valeur peut être NULL pour les rows dégradées. Le bound check
    physique filtre explicitement les NULL.

    Borne haute resserrée à ``+100`` post-046 (vs. ``+200`` toléré pour
    l'outlier 045 bugué) : sur Afrique tropicale ouest la divergence
    inter-source documentée Ouhechou 2023 est de l'ordre ±15 %. Une
    valeur au-delà de ±100 % serait suspecte et signalerait une
    régression.

    Caveat méthodologique sur la divergence systématique inter-source
    CMSAF/CERES (Ouhechou 2023) - propriété attendue de la grandeur,
    pas un bug.
    """
    rows = db_session.execute(
        text(
            """
            SELECT valeur FROM grandeurs_metier
            WHERE grandeur_code = 'ecart_relatif_referentiel' AND valide_au IS NULL
              AND localite_id IN (SELECT id FROM localites WHERE code = ANY(:pilotes))
            """
        ),
        {"pilotes": list(_LOCALITES_PILOTES)},
    ).all()
    assert len(rows) == 216, (
        f"Attendu 216 lignes ecart_relatif_referentiel aux 6 pilotes (6 x 36 mois), "
        f"observé {len(rows)}. (L'atlas Temps 1 etend l'ecart aux communes, hors scope ici.)"
    )
    valeurs_non_nulles = [r.valeur for r in rows if r.valeur is not None]
    for valeur in valeurs_non_nulles:
        assert -100.0 <= valeur <= 100.0, (
            f"Ecart hors plage physique post-046 : {valeur}. Borne resserrée à "
            f"±100 % après correction du bug 045 (cf. migration 046 docstring)."
        )


def test_ti60_rang_spatial_dans_1_6(db_session: Session) -> None:
    """valeurs rang_referentiel_spatial entre 1 et 6 (rang ordinal)."""
    rows = db_session.execute(
        text(
            """
            SELECT DISTINCT valeur FROM grandeurs_metier
            WHERE grandeur_code = 'rang_referentiel_spatial' AND valide_au IS NULL
            ORDER BY valeur
            """
        )
    ).all()
    valeurs_distinctes = {int(r.valeur) for r in rows}
    assert valeurs_distinctes == {1, 2, 3, 4, 5, 6}

    # Verifie que chaque ville a bien 60 mois x rangs distribues
    rows_compte = db_session.execute(
        text(
            """
            SELECT valeur, COUNT(*) AS n FROM grandeurs_metier
            WHERE grandeur_code = 'rang_referentiel_spatial' AND valide_au IS NULL
            GROUP BY valeur ORDER BY valeur
            """
        )
    ).all()
    # Sum total = 360 (6 villes x 60 mois)
    assert sum(r.n for r in rows_compte) == 360
    # Chaque rang attribue exactement 60 fois (1 par mois sur 60 mois)
    for r in rows_compte:
        assert r.n == 60

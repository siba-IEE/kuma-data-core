"""Grandeurs référentielles stockées : écart relatif, rangs temporel et spatial."""

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

# L'écart est aussi calculé ailleurs : ces tests se limitent aux 6 pilotes.
_LOCALITES_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)


def test_ti53_decomptes_par_grandeur_1_7b(db_session: Session) -> None:
    """936 lignes aux 6 pilotes : 216 écarts + 360 rangs temporels + 360 rangs spatiaux."""
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
    """Décompte total de ``grandeurs_metier``."""
    total = db_session.scalar(
        select(func.count()).select_from(GrandeurMetier).where(GrandeurMetier.valide_au.is_(None))
    )
    # Pilotes : 1 626 calculées récentes + 936 référentielles + 6 240 climato
    #   + 1 218 écart DNI (6 x 203) = 10 020
    # 374 dégénérescence + 1 008 écart GHI (28 x 36) + 1 224 écart DNI (34 x 36)
    # 28 communes : 34 580 (28 x 1 235) + 3 808 (28 x 136) + 5 684 écart DNI (28 x 203)
    assert total == 56698


def test_ti55_grandeurs_referentiel_post_d39(db_session: Session) -> None:
    """Activation des grandeurs référentielles et total du référentiel."""
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

    # 26 + ecart_relatif_dni_cams + poa_bifacial + precipitation + pm2_5 + pm10
    # + taux_salissure_proxy + pr_realiste + degenerescence_pixel + 4 AOD/ozone = 38
    total = db_session.execute(text("SELECT COUNT(*) FROM grandeurs_referentiel")).scalar_one()
    assert total == 38


def test_ti56_18_series_calculees_1_7b(db_session: Session) -> None:
    """18 séries calculées (3 grandeurs x 6 pilotes), nommées ``gin_..._kuma_calculs_...``."""
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

    for r in rows:
        assert r.code.startswith("gin_"), f"Naming D-32 violation : {r.code}"
        assert "_kuma_calculs_" in r.code, f"Source dans code manquante : {r.code}"

    decompte_par_grandeur: dict[str, int] = {}
    for r in rows:
        decompte_par_grandeur[r.grandeur_code] = decompte_par_grandeur.get(r.grandeur_code, 0) + 1
    for grandeur in _GRANDEURS_1_7B:
        assert decompte_par_grandeur[grandeur] == 6


def test_ti57_regression_non_doublon_exclude(db_session: Session) -> None:
    """Aucun doublon sur la clé EXCLUDE de ``grandeurs_metier``."""
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
    """216 lignes d'écart, valeurs non nulles dans [-100, +100] %.

    Une valeur NULL marque un mois SARAH-3 sous le seuil. La divergence
    inter-source CMSAF/CERES attendue en Afrique de l'Ouest est d'environ ±15 %
    (Ouhechou 2023) : au-delà de ±100 %, c'est une régression.
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
    """Rangs spatiaux entiers de 1 à 6, chacun attribué 60 fois (une fois par mois)."""
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

    rows_compte = db_session.execute(
        text(
            """
            SELECT valeur, COUNT(*) AS n FROM grandeurs_metier
            WHERE grandeur_code = 'rang_referentiel_spatial' AND valide_au IS NULL
            GROUP BY valeur ORDER BY valeur
            """
        )
    ).all()
    # 6 villes x 60 mois
    assert sum(r.n for r in rows_compte) == 360
    for r in rows_compte:
        assert r.n == 60

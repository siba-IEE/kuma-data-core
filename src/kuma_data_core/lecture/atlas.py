"""Lecture de l'atlas d'incertitude inter-source : écarts entre sources et dégénérescence de pixel.

Ces grandeurs calculées sont lues dans ``grandeurs_metier``, pas dans la vue
``v_grandeurs_metier_courantes``.
"""

from __future__ import annotations

from typing import NamedTuple

from sqlalchemy import text
from sqlalchemy.orm import Session

# Version en vigueur de chaque valeur (alias ``gm``), tous statuts et toutes versions de formule.
_VALEURS_COURANTES = "gm.valide_au IS NULL"


class DegenerescencePixel(NamedTuple):
    """Dégénérescence de pixel d'une localité, avec les niveaux de confiance de sa ligne."""

    n_jumeaux: int
    note: str
    niveau_derive: str
    niveau_override: str | None


class PointAtlas(NamedTuple):
    """Localité qui porte au moins un écart inter-source."""

    localite_id: int
    code: str


def lire_ecarts_mensuels(
    session: Session,
    code_localite: str,
    grandeur_ecart: str,
    annee_debut: int,
    annee_fin: int,
) -> tuple[list[float], list[tuple[str, str | None]]]:
    """Écarts mensuels d'une localité pour une grandeur d'écart, années bornes incluses.

    Le filtre sur ``annee_debut`` écarte les écarts calculés sur d'autres fenêtres
    (climatologie DNI 2004-2020). Renvoie ``(valeurs_signees, niveaux)`` sur les
    mois renseignés, chaque niveau étant ``(dérivé, override)``, ou ``([], [])``
    si la localité n'en a pas.
    """
    rows = session.execute(
        text(
            f"""
            SELECT gm.valeur, gm.niveau_confiance_derive AS derive,
                   gm.niveau_confiance_override AS override
            FROM grandeurs_metier gm
            JOIN localites l ON l.id = gm.localite_id
            WHERE l.code = :loc AND gm.grandeur_code = :g
              AND gm.annee_debut BETWEEN :a1 AND :a2
              AND {_VALEURS_COURANTES}
            ORDER BY gm.annee_debut, gm.mois
            """
        ),
        {"loc": code_localite, "g": grandeur_ecart, "a1": annee_debut, "a2": annee_fin},
    ).all()
    valeurs = [float(r.valeur) for r in rows if r.valeur is not None]
    niveaux = [(str(r.derive), r.override) for r in rows if r.valeur is not None]
    return valeurs, niveaux


def lire_degenerescence_pixel(session: Session, code_localite: str) -> DegenerescencePixel | None:
    """Dégénérescence de pixel de la localité sur la grille CERES de NASA POWER, ou ``None``.

    GHI et DNI partagent cette grille : la ligne de la série ``ghi`` de
    ``nasa_power`` vaut pour les deux.
    """
    row = session.execute(
        text(
            f"""
            SELECT gm.valeur, gm.commentaire_editorial AS note,
                   gm.niveau_confiance_derive AS derive,
                   gm.niveau_confiance_override AS override
            FROM grandeurs_metier gm
            JOIN localites l ON l.id = gm.localite_id
            JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
            JOIN sources s ON s.id = sm.source_id
            WHERE l.code = :loc AND gm.grandeur_code = 'degenerescence_pixel'
              AND s.code = 'nasa_power' AND sm.grandeur_code = 'ghi'
              AND {_VALEURS_COURANTES}
            """
        ),
        {"loc": code_localite},
    ).first()
    if row is None or row.valeur is None:
        return None
    return DegenerescencePixel(
        n_jumeaux=int(row.valeur),
        note=str(row.note or ""),
        niveau_derive=str(row.derive),
        niveau_override=row.override,
    )


def lister_points_atlas(session: Session, annee_debut: int) -> list[PointAtlas]:
    """Localités qui ont un écart inter-source depuis ``annee_debut``, triées par code.

    La liste suit la donnée, pas une énumération fixe.
    """
    rows = session.execute(
        text(
            f"""
            SELECT DISTINCT l.id, l.code
            FROM grandeurs_metier gm
            JOIN localites l ON l.id = gm.localite_id
            WHERE gm.grandeur_code IN ('ecart_relatif_referentiel', 'ecart_relatif_dni_cams')
              AND gm.annee_debut >= :a1 AND {_VALEURS_COURANTES}
            ORDER BY l.code
            """
        ),
        {"a1": annee_debut},
    ).all()
    return [PointAtlas(localite_id=int(r.id), code=str(r.code)) for r in rows]

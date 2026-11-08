"""Atlas d'incertitude inter-source : fiche par localité et collection des points."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated, Literal, NamedTuple

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.grandeurs._commun import _coordonnees_ou_erreur
from kuma_data_core.api.v1.schemas.grandeurs import (
    DegenerescenceFiche,
    EcartPaireInterSource,
    FichePointIncertitude,
    ReponseIncertitudeInterSource,
    ReponseIncertitudeInterSourceCollection,
)
from kuma_data_core.db.session import obtenir_session

routeur = APIRouter()

# === Endpoint incertitude_inter_source (lecture et assemblage) ===============

_AN_DEBUT_ATLAS = 2021
_AN_FIN_ATLAS = 2023
_FENETRE_ATLAS_STR = "2021-2023"
_GRILLE_CERES = "CERES SYN1deg (1 deg / 110 km)"
# (grandeur exposée, grandeur_code de l'écart matérialisé, libellé de la paire).
_PAIRES_ECART_ATLAS: tuple[tuple[Literal["ghi", "dni"], str, str], ...] = (
    ("ghi", "ecart_relatif_referentiel", "NASA POWER vs PVGIS-SARAH3"),
    ("dni", "ecart_relatif_dni_cams", "NASA POWER vs CAMS"),
)
_GRANDEURS_ECART_ATLAS: tuple[str, ...] = tuple(g for _, g, _ in _PAIRES_ECART_ATLAS)


def _mediane_abs(valeurs: Sequence[float]) -> float:
    """Médiane des valeurs absolues (pur). ``valeurs`` non vide (garanti par l'appelant)."""
    absolues = sorted(abs(v) for v in valeurs)
    n = len(absolues)
    milieu = n // 2
    if n % 2 == 1:
        return absolues[milieu]
    return (absolues[milieu - 1] + absolues[milieu]) / 2.0


_Niveaux = list[tuple[str, str | None]]
"""(niveau dérivé, override) des lignes lues."""


def _lire_ecarts_recents(
    session: Session, codes_localites: Sequence[str]
) -> dict[tuple[str, str], tuple[list[float], _Niveaux]]:
    """Écarts mensuels récents (2021-2023) non NULL, par (localité, grandeur d'écart).

    La fenêtre exclut le climato DNI 2004-2020 (anti-mélange de fenêtres). Valeurs
    signées dans l'ordre (année, mois) ; une localité hors atlas n'a pas de clé.
    """
    rows = session.execute(
        text(
            """
            SELECT l.code, gm.grandeur_code, gm.valeur,
                   gm.niveau_confiance_derive AS derive,
                   gm.niveau_confiance_override AS override
            FROM v_grandeurs_metier_courantes gm
            JOIN localites l ON l.id = gm.localite_id
            WHERE l.code = ANY(:codes) AND gm.grandeur_code = ANY(:grandeurs)
              AND gm.annee_debut BETWEEN :a1 AND :a2
              AND gm.valeur IS NOT NULL
            ORDER BY l.code, gm.grandeur_code, gm.annee_debut, gm.mois, gm.id
            """
        ),
        {
            "codes": list(codes_localites),
            "grandeurs": list(_GRANDEURS_ECART_ATLAS),
            "a1": _AN_DEBUT_ATLAS,
            "a2": _AN_FIN_ATLAS,
        },
    ).all()
    lus: dict[tuple[str, str], tuple[list[float], _Niveaux]] = {}
    for r in rows:
        valeurs, niveaux = lus.setdefault((str(r.code), str(r.grandeur_code)), ([], []))
        valeurs.append(float(r.valeur))
        niveaux.append((str(r.derive), r.override))
    return lus


def _lire_degenerescences(
    session: Session, codes_localites: Sequence[str]
) -> dict[str, tuple[DegenerescenceFiche, _Niveaux]]:
    """Dégénérescence niveau-localité (grille NASA CERES, via la série ghi), par localité.

    GHI et DNI partagent la grille CERES : la ligne ``nasa_power`` + ``ghi`` est
    représentative et unique par localité. Une localité sans ligne, ou à valeur
    NULL, n'a pas de clé.
    """
    rows = session.execute(
        text(
            """
            SELECT DISTINCT ON (l.code)
                   l.code, gm.valeur, gm.commentaire_editorial AS note,
                   gm.niveau_confiance_derive AS derive,
                   gm.niveau_confiance_override AS override
            FROM v_grandeurs_metier_courantes gm
            JOIN localites l ON l.id = gm.localite_id
            JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
            JOIN sources s ON s.id = sm.source_id
            WHERE l.code = ANY(:codes) AND gm.grandeur_code = 'degenerescence_pixel'
              AND s.code = 'nasa_power' AND sm.grandeur_code = 'ghi'
            ORDER BY l.code, gm.id
            """
        ),
        {"codes": list(codes_localites)},
    ).all()
    return {
        str(r.code): (
            DegenerescenceFiche(
                n_jumeaux=int(r.valeur), grille=_GRILLE_CERES, note=str(r.note or "")
            ),
            [(str(r.derive), r.override)],
        )
        for r in rows
        if r.valeur is not None
    }


def _niveau_confiance_fiche(
    niveaux: Sequence[tuple[str, str | None]], code_localite: str
) -> Literal["B", "C"]:
    """Confiance effective de la fiche (override sinon derive) : le plus bas de ses lignes.

    Une ligne en A (réservé aux mesures au sol) ou un niveau absent trahit une
    dérive de la donnée : 500 explicite plutôt qu'un niveau affiché à tort.
    """
    effectifs = {(override if override is not None else derive) for derive, override in niveaux}
    if not effectifs or not effectifs <= {"B", "C"}:
        raise ExceptionKuma(
            code=CodeErreur.SERVEUR_ERREUR_INTERNE,
            message=(
                f"Incoherence de confiance pour {code_localite!r} : la fiche inter-source "
                f"attend des donnees en confiance B ou C, trouve {sorted(effectifs)}. "
                "L'atlas est inter-source ; A est reserve aux mesures terrain."
            ),
            statut_http=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return "C" if "C" in effectifs else "B"


def _construire_limite_incertitude_inter_source(niveau: str) -> str:
    """Avertissement éditorial anti-survente."""
    return (
        "Incertitude inter-source / relative : divergence entre NASA POWER et les references "
        "satellite (SARAH-3 pour le GHI, CAMS pour le DNI), fenetre 2021-2023, "
        f"confiance {niveau}. "
        "Ne quantifie PAS l'incertitude absolue vs mesure sol (qui exige des mesures terrain) : "
        "ce n'est pas une barre d'erreur calibree au sol."
    )


class _FicheIncomplete(Exception):
    """Écart ou dégénérescence absent pour la localité ; chaque route rend son erreur."""

    def __init__(self, sans_ecart: bool) -> None:
        super().__init__()
        self.sans_ecart = sans_ecart


def _composer_ecarts(
    code_localite: str, lus: Mapping[tuple[str, str], tuple[list[float], _Niveaux]]
) -> tuple[list[EcartPaireInterSource], _Niveaux]:
    """Écart par paire (médiane des |écarts|, moyenne signée) et niveaux des lignes lues."""
    ecarts: list[EcartPaireInterSource] = []
    niveaux: _Niveaux = []
    for grandeur, grandeur_ecart, paire in _PAIRES_ECART_ATLAS:
        valeurs, niv = lus.get((code_localite, grandeur_ecart), ([], []))
        if not valeurs:
            continue
        ecarts.append(
            EcartPaireInterSource(
                grandeur=grandeur,
                paire=paire,
                ecart_abs_pct=round(_mediane_abs(valeurs), 4),
                ecart_signe_pct=round(sum(valeurs) / len(valeurs), 4),
                n_mois=len(valeurs),
            )
        )
        niveaux += niv
    return ecarts, niveaux


def _composer_fiche(
    code_localite: str,
    ecarts: list[EcartPaireInterSource],
    niveaux: _Niveaux,
    degenerescence: tuple[DegenerescenceFiche, _Niveaux] | None,
) -> ReponseIncertitudeInterSource:
    """Fiche d'une localité : deux axes distincts, confiance lue et limite éditoriale.

    Lève ``_FicheIncomplete`` sans écart ou sans dégénérescence, 500 sur
    incohérence de confiance.
    """
    if not ecarts:
        raise _FicheIncomplete(sans_ecart=True)
    if degenerescence is None:
        raise _FicheIncomplete(sans_ecart=False)
    fiche_degenerescence, niv_degen = degenerescence
    niveau = _niveau_confiance_fiche([*niveaux, *niv_degen], code_localite)
    return ReponseIncertitudeInterSource(
        code_localite=code_localite,
        fenetre=_FENETRE_ATLAS_STR,
        ecarts=ecarts,
        degenerescence=fiche_degenerescence,
        niveau_confiance=niveau,
        limite=_construire_limite_incertitude_inter_source(niveau),
    )


def _assembler_fiche(session: Session, code_localite: str) -> ReponseIncertitudeInterSource:
    """Fiche d'incertitude inter-source d'une localité, assemblée en lecture.

    La dégénérescence n'est lue que si un écart l'est.
    """
    ecarts, niveaux = _composer_ecarts(
        code_localite, _lire_ecarts_recents(session, [code_localite])
    )
    if not ecarts:
        raise _FicheIncomplete(sans_ecart=True)
    degenerescence = _lire_degenerescences(session, [code_localite]).get(code_localite)
    return _composer_fiche(code_localite, ecarts, niveaux, degenerescence)


@routeur.get(
    "/incertitude_inter_source/{code_localite}",
    response_model=ReponseIncertitudeInterSource,
    status_code=status.HTTP_200_OK,
    summary="Fiche d'incertitude inter-source (ecart + degenerescence de pixel)",
    tags=["grandeurs-F1"],
)
def grandeur_incertitude_inter_source(
    code_localite: str,
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> ReponseIncertitudeInterSource:
    """Assemble en LECTURE la fiche d'incertitude inter-source d'une localité.

    Deux axes d'honnêteté DISTINCTS, non fusionnés :

    - ``ecarts`` : écart inter-source par paire/grandeur (GHI : NASA vs SARAH-3 ; DNI :
      NASA vs CAMS, fenêtre récente 2021-2023). ``ecart_abs_pct`` (médiane des |écarts|) =
      signal primaire ; ``ecart_signe_pct`` orientationnel seulement.
    - ``degenerescence`` : propriété niveau-localité (grille NASA CERES), rendue une fois.

    Lecture/assemblage pur des grandeurs DÉJÀ matérialisées, zéro calcul de
    substrat. Confiance lue : B, ou C si une ligne lue est en C (jamais A : A =
    terrain). 404 si la localité n'est pas couverte par l'atlas (33 préfectures
    + Conakry, 34 points).
    """
    try:
        return _assembler_fiche(session, code_localite)
    except _FicheIncomplete as exc:
        if exc.sans_ecart:
            raise ExceptionKuma(
                code=CodeErreur.RESSOURCE_LOCALITE_INCONNUE,
                message=(
                    f"Localite {code_localite!r} non couverte par l'atlas d'incertitude "
                    "inter-source (33 prefectures + Conakry, 34 points d'ingestion sur 2021-2023)."
                ),
                statut_http=status.HTTP_404_NOT_FOUND,
            ) from None
        raise ExceptionKuma(
            code=CodeErreur.SERVEUR_ERREUR_INTERNE,
            message=(
                f"Incoherence : ecart inter-source present pour {code_localite!r} mais "
                "degenerescence_pixel (NASA/ghi) absente."
            ),
            statut_http=status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from None


class _PointAtlas(NamedTuple):
    localite_id: int
    code: str
    latitude: float | None
    longitude: float | None


# Périmètre de l'atlas : les localités ayant un écart non NULL dans la fenêtre de
# lecture des fiches (sinon un point serait listé sans fiche lisible, 500). La
# liste suit la donnée, pas une énumération figée.
_SQL_POINTS_ATLAS = """
    WITH points AS (
        SELECT DISTINCT l.id, l.code, l.latitude, l.longitude
        FROM v_grandeurs_metier_courantes gm
        JOIN localites l ON l.id = gm.localite_id
        WHERE gm.grandeur_code = ANY(:grandeurs)
          AND gm.annee_debut BETWEEN :a1 AND :a2
          AND gm.valeur IS NOT NULL
    )
"""


def _lire_page_atlas(session: Session, limit: int, offset: int) -> tuple[int, list[_PointAtlas]]:
    """Nombre total de points de l'atlas et la page demandée, triée par code."""
    params = {
        "grandeurs": list(_GRANDEURS_ECART_ATLAS),
        "a1": _AN_DEBUT_ATLAS,
        "a2": _AN_FIN_ATLAS,
        "limit": limit,
        "offset": offset,
    }
    rows = session.execute(
        text(
            _SQL_POINTS_ATLAS
            + """
            SELECT id, code, latitude, longitude, count(*) OVER () AS total
            FROM points ORDER BY code LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).all()
    if rows:
        total = int(rows[0].total)
    else:
        # Page au-delà du dernier point : le total vient d'un comptage séparé.
        total = int(
            session.execute(
                text(_SQL_POINTS_ATLAS + "SELECT count(*) FROM points"), params
            ).scalar_one()
        )
    page = [
        _PointAtlas(
            int(r.id),
            str(r.code),
            None if r.latitude is None else float(r.latitude),
            None if r.longitude is None else float(r.longitude),
        )
        for r in rows
    ]
    return total, page


def _fiche_point(
    point: _PointAtlas,
    ecarts_lus: Mapping[tuple[str, str], tuple[list[float], _Niveaux]],
    degenerescences: Mapping[str, tuple[DegenerescenceFiche, _Niveaux]],
) -> FichePointIncertitude:
    """Fiche d'un point de l'atlas : la fiche par localité augmentée de ses coordonnées.

    Lève 500 sur incohérence (un point du périmètre sans écart ou sans
    dégénérescence ne devrait pas exister).
    """
    ecarts, niveaux = _composer_ecarts(point.code, ecarts_lus)
    try:
        fiche = _composer_fiche(point.code, ecarts, niveaux, degenerescences.get(point.code))
    except _FicheIncomplete:
        raise ExceptionKuma(
            code=CodeErreur.SERVEUR_ERREUR_INTERNE,
            message=(
                f"Incoherence collection atlas : point {point.code!r} sans ecart ou "
                "degenerescence (devrait etre garanti par le perimetre data-driven)."
            ),
            statut_http=status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from None
    latitude, longitude = _coordonnees_ou_erreur(point.localite_id, point.latitude, point.longitude)
    return FichePointIncertitude(**dict(fiche), latitude_deg=latitude, longitude_deg=longitude)


@routeur.get(
    "/incertitude_inter_source",
    response_model=ReponseIncertitudeInterSourceCollection,
    status_code=status.HTTP_200_OK,
    summary="Collection des fiches d'incertitude inter-source (points de l'atlas)",
    tags=["grandeurs-F1"],
)
def grandeur_incertitude_inter_source_collection(
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReponseIncertitudeInterSourceCollection:
    """Toutes les fiches d'incertitude inter-source des points de l'atlas, paginées.

    Un appel pour le snapshot média (carte) au lieu de N. Chaque item = la MÊME fiche
    que l'endpoint par-localité (deux axes distincts, confiance, limite éditoriale) + lat/lon.
    Lecture/assemblage pur des grandeurs déjà matérialisées (écart inter-source
    mensuel + dégénérescence), zéro substrat.
    Enveloppe paginée identique à /v1/series (items / total / limit / offset).
    """
    total, page = _lire_page_atlas(session, limit, offset)
    codes = [point.code for point in page]
    ecarts_lus = _lire_ecarts_recents(session, codes) if page else {}
    degenerescences = _lire_degenerescences(session, codes) if page else {}
    items = [_fiche_point(point, ecarts_lus, degenerescences) for point in page]
    return ReponseIncertitudeInterSourceCollection(
        items=items, total=total, limit=limit, offset=offset
    )

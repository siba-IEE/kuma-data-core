"""Atlas d'incertitude inter-source : fiche par localité et collection des points."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.grandeurs._commun import _resoudre_coordonnees
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


def _mediane_abs(valeurs: Sequence[float]) -> float:
    """Médiane des valeurs absolues (pur). ``valeurs`` non vide (garanti par l'appelant)."""
    absolues = sorted(abs(v) for v in valeurs)
    n = len(absolues)
    milieu = n // 2
    if n % 2 == 1:
        return absolues[milieu]
    return (absolues[milieu - 1] + absolues[milieu]) / 2.0


def _lire_ecart_paire_recent(
    session: Session, code_localite: str, grandeur_ecart: str
) -> tuple[list[float], list[tuple[str, str | None]]]:
    """Lit les écarts mensuels RECENTS (2021-2023) d'une (localité, grandeur d'écart).

    Filtre ``annee_debut`` entre 2021 et 2023 : isole la fenêtre récente et exclut le climato DNI
    2004-2020 (artefact pilote, anti-mélange de fenêtres). Renvoie ``(valeurs_signees,
    niveaux)`` sur les mois non-NULL, ou ``([], [])`` si aucune (localité hors atlas).
    """
    rows = session.execute(
        text(
            """
            SELECT gm.valeur, gm.niveau_confiance_derive AS derive,
                   gm.niveau_confiance_override AS override
            FROM v_grandeurs_metier_courantes gm
            JOIN localites l ON l.id = gm.localite_id
            WHERE l.code = :loc AND gm.grandeur_code = :g
              AND gm.annee_debut BETWEEN :a1 AND :a2
            ORDER BY gm.annee_debut, gm.mois
            """
        ),
        {"loc": code_localite, "g": grandeur_ecart, "a1": _AN_DEBUT_ATLAS, "a2": _AN_FIN_ATLAS},
    ).all()
    valeurs = [float(r.valeur) for r in rows if r.valeur is not None]
    niveaux = [(str(r.derive), r.override) for r in rows if r.valeur is not None]
    return valeurs, niveaux


def _lire_degenerescence_localite(
    session: Session, code_localite: str
) -> tuple[DegenerescenceFiche | None, list[tuple[str, str | None]]]:
    """Lit la dégénérescence niveau-localité (grille NASA CERES, via la série ghi).

    GHI et DNI partagent la grille CERES -> la ligne ``nasa_power`` + ``ghi`` est
    représentative et unique par localité. Renvoie ``(fiche, niveaux)`` ou ``(None, [])``.
    """
    row = session.execute(
        text(
            """
            SELECT gm.valeur, gm.commentaire_editorial AS note,
                   gm.niveau_confiance_derive AS derive,
                   gm.niveau_confiance_override AS override
            FROM v_grandeurs_metier_courantes gm
            JOIN localites l ON l.id = gm.localite_id
            JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
            JOIN sources s ON s.id = sm.source_id
            WHERE l.code = :loc AND gm.grandeur_code = 'degenerescence_pixel'
              AND s.code = 'nasa_power' AND sm.grandeur_code = 'ghi'
            """
        ),
        {"loc": code_localite},
    ).first()
    if row is None or row.valeur is None:
        return None, []
    fiche = DegenerescenceFiche(
        n_jumeaux=int(row.valeur), grille=_GRILLE_CERES, note=str(row.note or "")
    )
    return fiche, [(str(row.derive), row.override)]


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


def _assembler_fiche(session: Session, code_localite: str) -> ReponseIncertitudeInterSource:
    """Fiche d'incertitude inter-source d'une localité, assemblée en lecture.

    Deux axes distincts (écart par paire, dégénérescence de pixel), confiance lue
    et limite éditoriale. Lève ``_FicheIncomplete`` si aucun écart n'est lu (la
    dégénérescence n'est alors pas lue) ou si la dégénérescence manque, 500 sur
    incohérence de confiance.
    """
    ecarts: list[EcartPaireInterSource] = []
    niveaux: list[tuple[str, str | None]] = []
    for grandeur, grandeur_ecart, paire in _PAIRES_ECART_ATLAS:
        valeurs, niv = _lire_ecart_paire_recent(session, code_localite, grandeur_ecart)
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
    if not ecarts:
        raise _FicheIncomplete(sans_ecart=True)

    degenerescence, niv_degen = _lire_degenerescence_localite(session, code_localite)
    if degenerescence is None:
        raise _FicheIncomplete(sans_ecart=False)
    niveaux += niv_degen
    niveau = _niveau_confiance_fiche(niveaux, code_localite)

    return ReponseIncertitudeInterSource(
        code_localite=code_localite,
        fenetre=_FENETRE_ATLAS_STR,
        ecarts=ecarts,
        degenerescence=degenerescence,
        niveau_confiance=niveau,
        limite=_construire_limite_incertitude_inter_source(niveau),
    )


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


def _lister_points_atlas(session: Session) -> list[tuple[int, str]]:
    """(localite_id, code) des points portant l'écart inter-source récent = périmètre atlas.

    Data-driven : les localités ayant un écart 2021-2023 (ghi vs SARAH-3 et/ou dni vs CAMS).
    Robuste à une densification future (la liste suit la donnée, pas une énumération figée).
    """
    rows = session.execute(
        text(
            """
            SELECT DISTINCT l.id, l.code
            FROM v_grandeurs_metier_courantes gm
            JOIN localites l ON l.id = gm.localite_id
            WHERE gm.grandeur_code IN ('ecart_relatif_referentiel', 'ecart_relatif_dni_cams')
              AND gm.annee_debut BETWEEN :a1 AND :a2
            ORDER BY l.code
            """
        ),
        # Même fenêtre que _lire_ecart_paire_recent : un point hors fenêtre
        # serait listé sans fiche lisible (500).
        {"a1": _AN_DEBUT_ATLAS, "a2": _AN_FIN_ATLAS},
    ).all()
    return [(int(r.id), str(r.code)) for r in rows]


def _assembler_fiche_point(
    session: Session, localite_id: int, code_localite: str
) -> FichePointIncertitude:
    """Fiche d'un point de l'atlas : la fiche par localité augmentée de ses coordonnées.

    Lève 500 sur incohérence (un point du périmètre sans écart ou sans
    dégénérescence ne devrait pas exister).
    """
    try:
        fiche = _assembler_fiche(session, code_localite)
    except _FicheIncomplete:
        raise ExceptionKuma(
            code=CodeErreur.SERVEUR_ERREUR_INTERNE,
            message=(
                f"Incoherence collection atlas : point {code_localite!r} sans ecart ou "
                "degenerescence (devrait etre garanti par le perimetre data-driven)."
            ),
            statut_http=status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from None
    latitude, longitude = _resoudre_coordonnees(session, localite_id)
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
    points = _lister_points_atlas(session)
    total = len(points)
    page = points[offset : offset + limit]
    items = [_assembler_fiche_point(session, loc_id, code) for loc_id, code in page]
    return ReponseIncertitudeInterSourceCollection(
        items=items, total=total, limit=limit, offset=offset
    )

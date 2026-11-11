"""Lecture du catalogue des séries : liste, détail et recherche d'une série par ses attributs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, NamedTuple

from sqlalchemy import Row, text
from sqlalchemy.orm import Session

from kuma_data_core.editorial.selection import lignes_en_vigueur_validees


class SerieCatalogue(NamedTuple):
    """Série du catalogue, avec sa localité, sa grandeur et sa source.

    ``grandeur_label`` est le libellé de la grandeur, ``grandeur_unit`` le
    symbole de son unité, ``source_label`` le titre de la source, ``notes_fr``
    la note publique ; ``created_at`` et ``updated_at`` sont ``cree_le`` et
    ``modifie_le``.
    """

    id: int
    code: str
    libelle: str
    localite_id: int
    localite_code: str
    localite_nom: str
    localite_iso3: str | None
    grandeur_code: str
    grandeur_label: str
    grandeur_unit: str
    source_id: int
    source_code: str
    source_label: str
    source_url: str | None
    periode_debut: date
    periode_fin: date | None
    methode_collecte: str | None
    notes_fr: str | None
    created_at: datetime
    updated_at: datetime
    actif: bool


class SerieDetaillee(NamedTuple):
    """Série du catalogue, avec sa granularité et le code de son unité."""

    catalogue: SerieCatalogue
    granularite: str | None
    unite_code: str


class SerieSourceResolue(NamedTuple):
    """Métadonnées de la série source.

    ``source_code`` et ``granularite`` déterminent la table de mesures à lire.
    ``granularite`` sert aussi à choisir les séries compagnes : séries horaires
    et journalières peuvent partager le même ``periode_debut``.
    ``fuseau_horaire`` est le nom IANA du fuseau de la localité, ``'UTC'`` si
    elle n'en a pas : il fixe le jour local des mesures horaires.
    """

    serie_id: int
    localite_id: int
    source_id: int
    grandeur_code: str
    localite_code: str
    periode_debut: date
    source_code: str
    granularite: str | None
    periode_fin: date | None
    fuseau_horaire: str


class SerieIdentifiee(NamedTuple):
    """Identifiant et code d'une série."""

    serie_id: int
    code_serie: str


class SerieHoraireStockee(NamedTuple):
    """Série horaire qui porte des mesures validées, avec la période qu'elle déclare."""

    serie_id: int
    periode_debut: date
    periode_fin: date


def _serie_catalogue(r: Row[Any]) -> SerieCatalogue:
    """Convertit les colonnes de catalogue, communes à la liste et au détail."""
    return SerieCatalogue(
        id=int(r.id),
        code=r.code,
        libelle=r.libelle,
        localite_id=int(r.localite_id),
        localite_code=r.localite_code,
        localite_nom=r.localite_nom,
        localite_iso3=r.localite_iso3,
        grandeur_code=r.grandeur_code,
        grandeur_label=r.grandeur_label,
        grandeur_unit=r.grandeur_unit,
        source_id=int(r.source_id),
        source_code=r.source_code,
        source_label=r.source_label,
        source_url=r.source_url,
        periode_debut=r.periode_debut,
        periode_fin=r.periode_fin,
        methode_collecte=r.methode_collecte,
        notes_fr=r.notes_fr,
        created_at=r.created_at,
        updated_at=r.updated_at,
        actif=r.actif,
    )


def lire_page_series(
    session: Session,
    *,
    localite: str | None,
    grandeur: str | None,
    source: str | None,
    actif: bool | None,
    limit: int,
    offset: int,
) -> tuple[int, list[SerieCatalogue]]:
    """``(total, page)`` des séries qui passent les filtres, triées par code.

    Un filtre à ``None`` n'est pas appliqué. ``total`` compte toutes les pages.
    """
    clauses: list[str] = []
    params: dict[str, object] = {"limit": limit, "offset": offset}

    if localite is not None:
        clauses.append("l.code = :localite_code")
        params["localite_code"] = localite
    if grandeur is not None:
        clauses.append("sm.grandeur_code = :grandeur_code")
        params["grandeur_code"] = grandeur
    if source is not None:
        clauses.append("s.code = :source_code")
        params["source_code"] = source
    if actif is not None:
        clauses.append("sm.actif = :actif")
        params["actif"] = actif

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    total = session.execute(
        text(
            f"""
            SELECT COUNT(*) AS n
            FROM series_metadonnees sm
            JOIN localites l ON l.id = sm.localite_id
            JOIN sources s ON s.id = sm.source_id
            {where_sql}
            """
        ),
        {k: v for k, v in params.items() if k not in ("limit", "offset")},
    ).scalar_one()

    rows = session.execute(
        text(
            f"""
            SELECT
                sm.id,
                sm.code,
                sm.libelle,
                sm.localite_id,
                l.code AS localite_code,
                l.nom AS localite_nom,
                l.pays_iso3 AS localite_iso3,
                sm.grandeur_code,
                gr.libelle AS grandeur_label,
                u.symbole AS grandeur_unit,
                sm.source_id,
                s.code AS source_code,
                s.titre AS source_label,
                s.url AS source_url,
                sm.periode_debut,
                sm.periode_fin,
                sm.methode_collecte,
                sm.note_publique AS notes_fr,
                sm.cree_le AS created_at,
                sm.modifie_le AS updated_at,
                sm.actif
            FROM series_metadonnees sm
            JOIN localites l ON l.id = sm.localite_id
            JOIN sources s ON s.id = sm.source_id
            JOIN grandeurs_referentiel gr ON gr.code = sm.grandeur_code
            JOIN unites u ON u.id = gr.unite_id
            {where_sql}
            ORDER BY sm.code
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).all()
    return int(total), [_serie_catalogue(r) for r in rows]


def lire_serie(session: Session, code_serie: str) -> SerieDetaillee | None:
    """Série de ce code, active ou non, ou ``None``."""
    row = session.execute(
        text(
            """
            SELECT
                sm.id,
                sm.code,
                sm.libelle,
                sm.localite_id,
                l.code AS localite_code,
                l.nom AS localite_nom,
                l.pays_iso3 AS localite_iso3,
                sm.grandeur_code,
                gr.libelle AS grandeur_label,
                u.symbole AS grandeur_unit,
                sm.source_id,
                s.code AS source_code,
                s.titre AS source_label,
                s.url AS source_url,
                sm.periode_debut,
                sm.periode_fin,
                sm.granularite,
                sm.methode_collecte,
                sm.note_publique AS notes_fr,
                sm.cree_le AS created_at,
                sm.modifie_le AS updated_at,
                sm.actif,
                u.code AS unite_code
            FROM series_metadonnees sm
            JOIN localites l ON l.id = sm.localite_id
            JOIN sources s ON s.id = sm.source_id
            JOIN grandeurs_referentiel gr ON gr.code = sm.grandeur_code
            JOIN unites u ON u.id = gr.unite_id
            WHERE sm.code = :code
            """
        ),
        {"code": code_serie},
    ).first()
    if row is None:
        return None
    return SerieDetaillee(
        catalogue=_serie_catalogue(row),
        granularite=row.granularite,
        unite_code=row.unite_code,
    )


def compter_series_actives(session: Session) -> int:
    """Nombre de séries actives."""
    total = session.execute(
        text("SELECT count(*) FROM series_metadonnees WHERE actif = TRUE")
    ).scalar()
    return int(total or 0)


def chercher_serie_active(session: Session, code_serie: str) -> SerieSourceResolue | None:
    """Métadonnées de la série active de ce code, ou ``None``."""
    row = session.execute(
        text(
            """
            SELECT sm.id, sm.localite_id, sm.source_id, sm.grandeur_code,
                   l.code AS localite_code, sm.periode_debut,
                   s.code AS source_code, sm.granularite, sm.periode_fin,
                   COALESCE(l.fuseau_horaire, 'UTC') AS fuseau_horaire
            FROM series_metadonnees sm
            JOIN localites l ON l.id = sm.localite_id
            JOIN sources s ON s.id = sm.source_id
            WHERE sm.code = :code
              AND sm.actif = TRUE
            """
        ),
        {"code": code_serie},
    ).first()
    if row is None:
        return None
    return SerieSourceResolue(
        serie_id=int(row.id),
        localite_id=int(row.localite_id),
        source_id=int(row.source_id),
        grandeur_code=row.grandeur_code,
        localite_code=row.localite_code,
        periode_debut=row.periode_debut,
        source_code=row.source_code,
        granularite=row.granularite,
        periode_fin=row.periode_fin,
        fuseau_horaire=row.fuseau_horaire,
    )


def chercher_serie_compagne(
    session: Session,
    localite_id: int,
    source_id: int,
    grandeur_code_compagne: str,
    periode_debut_source: date,
    granularite_source: str | None,
) -> int | None:
    """Identifiant de la série d'une autre grandeur, même localité et même source, ou ``None``.

    La compagne doit avoir le même ``periode_debut`` que la source (ce qui sépare
    les séries climatologiques des séries récentes) et la même granularité :
    séries horaires et journalières partagent leur ``periode_debut``, et sans ce
    second filtre une compagne horaire serait lue dans la table journalière.
    """
    row = session.execute(
        text(
            """
            SELECT id FROM series_metadonnees
            WHERE localite_id = :localite_id
              AND source_id = :source_id
              AND grandeur_code = :grandeur_code
              AND periode_debut = :periode_debut_source
              AND granularite IS NOT DISTINCT FROM :granularite_source
              AND actif = TRUE
            ORDER BY id
            LIMIT 1
            """
        ),
        {
            "localite_id": localite_id,
            "source_id": source_id,
            "grandeur_code": grandeur_code_compagne,
            "periode_debut_source": periode_debut_source,
            "granularite_source": granularite_source,
        },
    ).first()
    return int(row.id) if row else None


def chercher_serie_albedo_journalier(
    session: Session, localite_id: int, source_id: int
) -> int | None:
    """Série ``albedo_surface`` journalière de la localité et de la source, ou ``None``.

    L'albédo n'existe qu'en journalier, y compris pour un calcul horaire : son
    ``periode_debut`` diffère de celui d'un GHI horaire et
    ``chercher_serie_compagne`` ne le trouverait pas.
    """
    row = session.execute(
        text(
            """
            SELECT id FROM series_metadonnees
            WHERE localite_id = :loc AND source_id = :src
              AND grandeur_code = 'albedo_surface' AND granularite = 'journalier'
              AND actif = TRUE
            ORDER BY periode_debut DESC
            LIMIT 1
            """
        ),
        {"loc": localite_id, "src": source_id},
    ).scalar()
    return int(row) if row is not None else None


def chercher_serie_ghi_nasa_power(
    session: Session, code_localite: str, annee_debut: int
) -> SerieIdentifiee | None:
    """Série GHI NASA POWER active de la localité dont la période débute en ``annee_debut``.

    ``None`` si la localité n'en porte pas ou n'existe pas ; la première par
    identifiant s'il y en a plusieurs.
    """
    row = session.execute(
        text(
            """
            SELECT sm.id AS serie_id, sm.code AS code_serie
            FROM series_metadonnees sm
            JOIN localites l ON l.id = sm.localite_id
            JOIN sources s ON s.id = sm.source_id
            WHERE l.code = :code_localite
              AND sm.grandeur_code = 'ghi'
              AND s.code = 'nasa_power'
              AND EXTRACT(YEAR FROM sm.periode_debut) = :annee_debut
              AND sm.actif = TRUE
            ORDER BY sm.id
            LIMIT 1
            """
        ),
        {"code_localite": code_localite, "annee_debut": annee_debut},
    ).first()
    if row is None:
        return None
    return SerieIdentifiee(serie_id=int(row.serie_id), code_serie=str(row.code_serie))


def chercher_serie_precipitation_nasa_power(
    session: Session,
    localite_id: int,
    periode_debut: date,
    periode_fin: date | None,
) -> int | None:
    """Série de précipitation journalière NASA POWER de la localité, ou ``None``.

    La pluie vient de ``nasa_power`` et les PM de ``cams_eac4`` :
    ``chercher_serie_compagne``, qui filtre sur la source, ne la trouverait
    pas. Une localité peut porter plusieurs séries de pluie NASA sur des
    périodes successives : est retenue la première, par ``periode_debut`` puis
    ``id``, dont la plage recouvre la période donnée.
    """
    row = session.execute(
        text(
            """
            SELECT sm.id FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            WHERE sm.localite_id = :localite_id
              AND s.code = 'nasa_power'
              AND sm.grandeur_code = 'precipitation'
              AND sm.granularite = 'journalier'
              AND sm.actif = TRUE
              AND (sm.periode_fin IS NULL OR sm.periode_fin >= :periode_debut)
              AND (CAST(:periode_fin AS DATE) IS NULL OR sm.periode_debut <= :periode_fin)
            ORDER BY sm.periode_debut, sm.id
            LIMIT 1
            """
        ),
        {
            "localite_id": localite_id,
            "periode_debut": periode_debut,
            "periode_fin": periode_fin,
        },
    ).first()
    return int(row.id) if row else None


def chercher_serie_pm_cams_eac4(
    session: Session, localite_id: int, grandeur_code: str
) -> int | None:
    """Série journalière ``pm2_5`` ou ``pm10`` EAC4 de la localité, ou ``None``.

    Les PM viennent de ``cams_eac4``, pas de la source du GHI :
    ``chercher_serie_compagne``, qui filtre sur la source, ne les trouverait pas.
    """
    row = session.execute(
        text(
            """
            SELECT sm.id FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            WHERE sm.localite_id = :localite_id
              AND s.code = 'cams_eac4'
              AND sm.grandeur_code = :grandeur_code
              AND sm.granularite = 'journalier'
              AND sm.actif = TRUE
            ORDER BY sm.periode_debut, sm.id
            LIMIT 1
            """
        ),
        {"localite_id": localite_id, "grandeur_code": grandeur_code},
    ).first()
    return int(row.id) if row else None


def chercher_serie_horaire_stockee(
    session: Session, localite_code: str, grandeur: str
) -> SerieHoraireStockee | None:
    """Série horaire stockée de la localité et de la grandeur, ou ``None``.

    Seules comptent les séries actives qui portent au moins une mesure en
    vigueur et validée : une série vide, ou dont aucune ligne n'a passé le
    contrôle qualité, couvrirait la fenêtre demandée et ferait répondre 200
    sans résultat. ``ORDER BY sm.id`` rend le choix déterministe si plusieurs
    séries conviennent. La jointure sur ``localites.code`` évite de dépendre
    du nom de la série.
    """
    row = session.execute(
        text(
            f"""
            SELECT sm.id, sm.periode_debut, sm.periode_fin
            FROM series_metadonnees sm
            JOIN localites l ON l.id = sm.localite_id
            WHERE l.code = :localite
              AND sm.grandeur_code = :grandeur
              AND sm.granularite = 'horaire'
              AND sm.actif = TRUE
              AND EXISTS (
                  SELECT 1 FROM mesures_ressource_horaires m
                  WHERE m.serie_id = sm.id AND {lignes_en_vigueur_validees("m")}
              )
            ORDER BY sm.id
            LIMIT 1
            """
        ),
        {"localite": localite_code, "grandeur": grandeur},
    ).first()
    if row is None or row.periode_fin is None:
        return None
    return SerieHoraireStockee(
        serie_id=int(row.id), periode_debut=row.periode_debut, periode_fin=row.periode_fin
    )

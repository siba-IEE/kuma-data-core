"""ingerer_vent_albedo_6_villes_pilotes

Revision ID: 048
Revises: 047
Create Date: 2026-05-21 10:30:00.000000+00:00

Ingestion des 18 nouvelles séries vent/albédo journalières 2021-2025
seedées par la migration 047.

Six appels séquentiels à ``ingerer_series_daily_groupe`` (un par
localité, chaque appel ingère les 3 grandeurs en batch via un seul
``fetch_daily`` multi-paramètres). Pattern hérité de la migration 022
(ingestion 5 villes pilotes × 5 grandeurs).

Volume attendu : 32 868 lignes (6 villes × 3 grandeurs × 1826 jours).
Les paramètres MERRA-2 (WS2M, WS10M) ne présentent pas de sentinelle
en pratique sur 2021-2025 (cohérent avec T2M et RH2M déjà ingérés sur
la même fenêtre). Le paramètre CERES SYN1deg ``ALLSKY_SRF_ALB`` peut
afficher une sentinelle ``-999.0`` sur la dernière date (lag de
processing CERES intra-daily sur les paramètres
secondaires) - filtrage transparent par
``ingerer_series_daily_groupe``.

Mapping ``grandeur_code -> parametre_nasa`` :

- ``vent_2m`` -> ``WS2M``
- ``vent_10m`` -> ``WS10M``
- ``albedo_surface`` -> ``ALLSKY_SRF_ALB``

Variable d'environnement ``KUMA_SKIP_NASA_POWER_INGESTION``
court-circuite l'appel réseau si truthy (utile pour CI sans
accès réseau et pour les tests d'intégration qui mockent httpx).

Downgrade : suppression des mesures ingérées pour les 18 séries via
``DELETE FROM mesures_ressource WHERE serie_id IN (...)``. Pattern
hérité de la migration 022.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from alembic import op
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.ingestion.nasa_power_daily import ingerer_series_daily_groupe

# revision identifiers, used by Alembic.
revision: str = "048"
down_revision: str | Sequence[str] | None = "047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Localités et slugs de série (énumération exhaustive) ============
# Mapping localite_code DB -> slug utilisé dans le code série, identique à
# la migration 047. Conakry-Kaloum utilise le slug court ``conakry``.
_LOCALITES_PILOTES: list[tuple[str, str]] = [
    # (localite_code, slug_serie)
    ("gin_conakry_kaloum", "gin_conakry"),
    ("gin_kankan", "gin_kankan"),
    ("gin_kindia", "gin_kindia"),
    ("gin_labe", "gin_labe"),
    ("gin_mamou", "gin_mamou"),
    ("gin_nzerekore", "gin_nzerekore"),
]

# === Grandeurs ingérées (énumération exhaustive) ====================
_GRANDEURS_VENT_ALBEDO: tuple[str, ...] = ("vent_2m", "vent_10m", "albedo_surface")

# Mapping grandeur Kuma -> paramètre NASA POWER.
_MAPPING_GRANDEUR_PARAMETRE_NASA: dict[str, str] = {
    "vent_2m": "WS2M",
    "vent_10m": "WS10M",
    "albedo_surface": "ALLSKY_SRF_ALB",
}

_SOURCE_CODE: str = "nasa_power"
_PERIODE_DEBUT: date = date(2021, 1, 1)
_PERIODE_FIN: date = date(2025, 12, 31)


def _code_serie(slug_serie: str, grandeur_code: str) -> str:
    """Convention de naming, identique à la migration 047."""
    return f"{slug_serie}_{grandeur_code}_{_SOURCE_CODE}_2021_2025"


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        # === Résolution des coordonnées des 6 localités ===
        codes_localites: list[str] = [loc[0] for loc in _LOCALITES_PILOTES]
        rows = bind.execute(
            text(
                "SELECT code, CAST(latitude AS DOUBLE PRECISION) AS lat, "
                "CAST(longitude AS DOUBLE PRECISION) AS lon "
                "FROM localites WHERE code = ANY(:codes)"
            ),
            {"codes": codes_localites},
        ).all()
        coordonnees_par_localite: dict[str, tuple[float, float]] = {
            r.code: (float(r.lat), float(r.lon)) for r in rows
        }
        if set(coordonnees_par_localite) != set(codes_localites):
            manquantes = set(codes_localites) - set(coordonnees_par_localite)
            raise RuntimeError(
                f"Migration 048 : localite(s) sans coordonnees : "
                f"{sorted(manquantes)}. Verifier migration 011."
            )

        # === 6 appels séquentiels à ingerer_series_daily_groupe ===
        decomptes_totaux: dict[str, int] = {}
        for localite_code, slug_serie in _LOCALITES_PILOTES:
            lat, lon = coordonnees_par_localite[localite_code]
            codes_series_localite = [_code_serie(slug_serie, g) for g in _GRANDEURS_VENT_ALBEDO]
            decompte_localite = ingerer_series_daily_groupe(
                session=session,
                codes_series=codes_series_localite,
                mapping_grandeur_parametre_nasa=_MAPPING_GRANDEUR_PARAMETRE_NASA,
                latitude=lat,
                longitude=lon,
                periode_debut=_PERIODE_DEBUT,
                periode_fin=_PERIODE_FIN,
            )
            decomptes_totaux.update(decompte_localite)

        total = sum(decomptes_totaux.values())
        op.execute(
            f"-- Migration 048 : {total} lignes inserees dans mesures_ressource "
            f"sur 6 villes pilotes x 3 grandeurs vent/albedo. "
            f"Decompte par serie : {decomptes_totaux}"
        )
    finally:
        session.close()


def downgrade() -> None:
    codes_series = [
        _code_serie(slug_serie, g)
        for _, slug_serie in _LOCALITES_PILOTES
        for g in _GRANDEURS_VENT_ALBEDO
    ]
    op.execute(
        text(
            """
            DELETE FROM mesures_ressource
            WHERE serie_id IN (
                SELECT id FROM series_metadonnees WHERE code = ANY(:codes)
            )
            """
        ).bindparams(codes=codes_series)
    )

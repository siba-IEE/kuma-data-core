"""ingerer_mesures_5_villes_pilotes

Revision ID: 022
Revises: 021
Create Date: 2026-05-11 17:30:00.000000+00:00

Ingestion des 25 nouvelles séries (5 villes guinéennes pilotes ×
5 grandeurs brutes). 5 appels séquentiels à
``ingerer_series_daily_groupe`` (1 par localité, chaque appel ingère
les 5 grandeurs en batch via 1 fetch_daily multi-paramètres).

Volume attendu : 45 640 lignes (5 villes × 5 grandeurs × 1825-1826
jours). Sentinelles DNI/DHI attendues 1/série (10 lignes
filtrées sur 5 villes), GHI/T2M/RH2M sans sentinelle.

Avec les 9128 lignes Conakry déjà présentes, la table
``mesures_ressource`` atteint 54 768 lignes.

**Conakry-Kaloum n'est PAS réingéré** : la cohorte cible
uniquement les 5 nouvelles villes (Kankan, Kindia, Labé, Mamou,
Nzérékoré).

Pattern hérité de la migration 020 qui ingérait 4 séries
Conakry en 1 appel multi-paramètres, appliqué en 5 boucles,
une par nouvelle localité.

Variable d'env ``KUMA_SKIP_NASA_POWER_INGESTION``
court-circuite l'appel réseau si truthy.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from alembic import op
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.ingestion.nasa_power_daily import ingerer_series_daily_groupe

# revision identifiers, used by Alembic.
revision: str = "022"
down_revision: str | Sequence[str] | None = "021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Énumération exhaustive des 5 nouvelles villes pilotes.
# Conakry-Kaloum déjà ingéré, exclu ici.
_LOCALITES_1_4: tuple[str, ...] = (
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)

_GRANDEURS: tuple[str, ...] = ("ghi", "dni", "dhi", "t2m", "rh2m")

# Mapping grandeur Kuma -> paramètre NASA POWER.
_MAPPING_GRANDEUR_PARAMETRE_NASA: dict[str, str] = {
    "ghi": "ALLSKY_SFC_SW_DWN",
    "dni": "ALLSKY_SFC_SW_DNI",
    "dhi": "ALLSKY_SFC_SW_DIFF",
    "t2m": "T2M",
    "rh2m": "RH2M",
}

_PERIODE_DEBUT: date = date(2021, 1, 1)
_PERIODE_FIN: date = date(2025, 12, 31)
_SOURCE_CODE: str = "nasa_power"


def _code_serie(localite_code: str, grandeur_code: str) -> str:
    """Convention naming reprise de la migration 021."""
    return f"{localite_code}_{grandeur_code}_{_SOURCE_CODE}_2021_2025"


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        # === Résolution des coordonnées des 5 localités ===
        rows = bind.execute(
            text(
                "SELECT code, CAST(latitude AS DOUBLE PRECISION) AS lat, "
                "CAST(longitude AS DOUBLE PRECISION) AS lon "
                "FROM localites WHERE code = ANY(:codes)"
            ),
            {"codes": list(_LOCALITES_1_4)},
        ).all()
        coordonnees_par_localite: dict[str, tuple[float, float]] = {
            r.code: (float(r.lat), float(r.lon)) for r in rows
        }
        if set(coordonnees_par_localite) != set(_LOCALITES_1_4):
            manquantes = set(_LOCALITES_1_4) - set(coordonnees_par_localite)
            raise RuntimeError(
                f"Migration 022 : localite(s) sans coordonnees : "
                f"{sorted(manquantes)}. Verifier migration 011."
            )

        # === 5 appels séquentiels à ingerer_series_daily_groupe ===
        decomptes_totaux: dict[str, int] = {}
        for localite_code in _LOCALITES_1_4:
            lat, lon = coordonnees_par_localite[localite_code]
            codes_series_localite = [_code_serie(localite_code, g) for g in _GRANDEURS]
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
            f"-- Migration 022 : {total} lignes inserees dans mesures_ressource "
            f"sur 5 villes pilotes (Kankan, Kindia, Labe, Mamou, Nzerekore) x "
            f"5 grandeurs. Decompte par serie : {decomptes_totaux}"
        )
    finally:
        session.close()


def downgrade() -> None:
    codes_series = [_code_serie(loc, gr) for loc in _LOCALITES_1_4 for gr in _GRANDEURS]
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

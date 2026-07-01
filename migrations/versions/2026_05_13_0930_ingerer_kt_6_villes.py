"""ingerer_kt_6_villes

Revision ID: 029
Revises: 028
Create Date: 2026-05-13 09:30:00.000000+00:00

Ingestion du paramètre NASA POWER `ALLSKY_KT` (indice de clarté Kt)
pour les 6 villes guinéennes pilotes. 6 appels séquentiels
à `ingerer_series_daily_groupe` (1 par localité), chaque appel ingère
1 seule grandeur (`kt`) via `fetch_daily` mono-paramètre.

Volume attendu : 10 950 lignes (6 villes × 1825 jours valides après
filtrage sentinelle `-999.0`). Vérification factuelle : 1 seule
sentinelle sur Conakry-Kaloum 2021-2025.

Avec les 45 640 lignes brutes déjà présentes, la
table `mesures_ressource` atteint 56 590 lignes.

Pattern hérité de la migration 022 (ingestion 25 séries 5 villes),
adapté pour 1 grandeur × 6 villes (Conakry-Kaloum inclus cette fois).

Variable d'env `KUMA_SKIP_NASA_POWER_INGESTION`
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
revision: str = "029"
down_revision: str | Sequence[str] | None = "028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Énumération exhaustive des 6 villes pilotes.
_LOCALITES_1_6A: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)

_GRANDEUR_CODE: str = "kt"
_SOURCE_CODE: str = "nasa_power"
_PERIODE_DEBUT: date = date(2021, 1, 1)
_PERIODE_FIN: date = date(2025, 12, 31)

# Mapping grandeur Kuma -> paramètre NASA POWER. `kt` -> `ALLSKY_KT`
# (ingéré directement depuis NASA POWER, paramètre ALLSKY_KT).
_MAPPING_GRANDEUR_PARAMETRE_NASA: dict[str, str] = {
    "kt": "ALLSKY_KT",
}


def _prefixe_ville_pour_serie(localite_code: str) -> str:
    """Préfixe ville pour code série (cf. migration 028)."""
    if localite_code == "gin_conakry_kaloum":
        return "gin_conakry"
    return localite_code


def _code_serie(localite_code: str) -> str:
    """Convention naming reprise de la migration 028."""
    return f"{_prefixe_ville_pour_serie(localite_code)}_{_GRANDEUR_CODE}_{_SOURCE_CODE}_2021_2025"


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        # === Résolution des coordonnées des 6 localités ===
        rows = bind.execute(
            text(
                "SELECT code, CAST(latitude AS DOUBLE PRECISION) AS lat, "
                "CAST(longitude AS DOUBLE PRECISION) AS lon "
                "FROM localites WHERE code = ANY(:codes)"
            ),
            {"codes": list(_LOCALITES_1_6A)},
        ).all()
        coordonnees_par_localite: dict[str, tuple[float, float]] = {
            r.code: (float(r.lat), float(r.lon)) for r in rows
        }
        if set(coordonnees_par_localite) != set(_LOCALITES_1_6A):
            manquantes = set(_LOCALITES_1_6A) - set(coordonnees_par_localite)
            raise RuntimeError(
                f"Migration 029 : localite(s) sans coordonnees : "
                f"{sorted(manquantes)}. Verifier migration 011."
            )

        # === 6 appels séquentiels à ingerer_series_daily_groupe ===
        decomptes_totaux: dict[str, int] = {}
        for localite_code in _LOCALITES_1_6A:
            lat, lon = coordonnees_par_localite[localite_code]
            codes_series_localite = [_code_serie(localite_code)]
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
            f"-- Migration 029 : {total} lignes inserees dans mesures_ressource "
            f"pour kt sur 6 villes pilotes (Conakry-Kaloum, Kankan, Kindia, Labe, "
            f"Mamou, Nzerekore). Decompte par serie : {decomptes_totaux}"
        )
    finally:
        session.close()


def downgrade() -> None:
    codes_series = [_code_serie(loc) for loc in _LOCALITES_1_6A]
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

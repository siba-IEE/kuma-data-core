"""parite_a2_humidex_variab_rangtemp_indicateur_28_communes

Revision ID: 093
Revises: 092
Create Date: 2026-06-21 20:00:00

Parite : etend 4 grandeurs calculees aux **28 communes chef-lieu**, meme
traitement Core qu'aux 6 pilotes. Migration SEULE (zero modif d'orchestrateur existant ;
l'ajout focalise ``calculer_et_inserer_rang_temporel`` est livre dans le meme cycle dans
``referentiels.py``).

- **humidex** (recent 2021-2025) : orchestrateur ``calculer_et_inserer_humidex`` (T2M +
  RH2M daily). Confiance DERIVEE en interne (R4 -> B). 65 lignes/commune (5 annuel + 60
  mensuel).
- **variabilite_journaliere** (recent 2021-2025) : orchestrateur
  ``calculer_et_inserer_variabilite_journaliere`` (GHI daily, CoV annuel). Confiance derivee
  (R4 -> B). 5 lignes/commune (annuel seul).
- **rang_referentiel_temporel** (recent 2021-2025) : fonction FOCALISEE
  ``calculer_et_inserer_rang_temporel`` (NASA daily agrege mensuel vs climato 1991-2020
  stratifiee par mois). JAMAIS l'orchestrateur combine ``calculer_et_inserer_referentiels``,
  qui recalculerait le rang SPATIAL sur un pool elargi et corromprait le pool-6 fige des
  consommateurs media. **Aucune ligne rang_referentiel_spatial creee.** 60 lignes/commune.
- **indicateur_qualite_donnees** (statique) : orchestrateur
  ``calculer_et_inserer_indicateur_qualite_donnees`` applique aux series brutes daily des
  communes, pour les **memes 6 grandeurs** que l'indicateur des pilotes (ghi/t2m/rh2m/dni/
  dhi/kt). Parite stricte : le set des grandeurs evaluees est LU depuis l'indicateur des
  pilotes (pas etendu aux 9 series daily des communes ; etendre vent/albedo serait une
  decision separee qui devrait aussi couvrir les pilotes). Restriction ``granularite =
  'journalier'`` : le daily ET le monthly climato portent ``methode_collecte =
  'modele_satellitaire'``, seule la granularite disambigue (sinon 336 au lieu de 168).
  Confiance 'B' hardcodee dans l'orchestrateur. 6 lignes/commune.

Total : 28 x (65 + 5 + 60 + 6) = 28 x 136 = 3 808 lignes ``grandeurs_metier`` ; 84
nouvelles series calculees (humidex/variabilite/rang_temporel, fenetre recente seule ;
l'indicateur ne cree pas de serie, il pointe la serie brute evaluee).

Enumeration data-driven des 28 : localites ayant le GHI daily 2021-2025 ET le GHI monthly
1991-2020, SANS serie humidex (robuste, prouve 28 ; les pilotes ont deja humidex -> exclus).
Series amont presentes aux 28 (densification migration 086 daily, migration
087 monthly). Naming des series : ``gin_<commune>_<grandeur>_kuma_calculs_2021_2025``. Grandeurs
declarees en 010 (immuable) : pas de re-declaration.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.services.grandeurs.humidex import calculer_et_inserer_humidex
from kuma_data_core.services.grandeurs.indicateur_qualite_donnees import (
    calculer_et_inserer_indicateur_qualite_donnees,
)
from kuma_data_core.services.grandeurs.referentiels import (
    ContexteRangTemporel,
    calculer_et_inserer_rang_temporel,
)
from kuma_data_core.services.grandeurs.variabilite_journaliere import (
    calculer_et_inserer_variabilite_journaliere,
)

# revision identifiers, used by Alembic.
revision: str = "093"
down_revision: str | Sequence[str] | None = "092"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Constantes ============================================================
_SOURCE_KUMA = "kuma_calculs"
_METHODE = "calcul_derive"
_VERSION = 1
_RECENT_DEBUT, _RECENT_FIN = 2021, 2025
_CLIMATO_DEBUT, _CLIMATO_FIN = 1991, 2020
_URL_DOC_BASE = "docs/methodologie/grandeurs"
_GRANDEUR_INDICATEUR = "indicateur_qualite_donnees"
_PILOTES = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)


def _code(commune: str, grandeur: str, source: str, an_debut: int, an_fin: int) -> str:
    return f"{commune}_{grandeur}_{source}_{an_debut}_{an_fin}"


# === Helpers I/O ===========================================================


def _points_a2(session: Session) -> list[tuple[int, str]]:
    """Enumeration data-driven des 28 communes (GHI daily 2021-2025 + GHI monthly
    1991-2020, SANS serie humidex). Les pilotes ont deja humidex -> exclus. Robuste a
    une densification future."""
    rows = session.execute(
        sa.text(
            """
            SELECT l.id, l.code FROM localites l
            WHERE EXISTS (
                SELECT 1 FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
                WHERE sm.localite_id = l.id AND s.code = 'nasa_power'
                  AND sm.grandeur_code = 'ghi' AND sm.granularite = 'journalier'
                  AND sm.periode_debut = '2021-01-01')
              AND EXISTS (
                SELECT 1 FROM series_metadonnees sm
                WHERE sm.localite_id = l.id AND sm.grandeur_code = 'ghi'
                  AND sm.granularite = 'mensuel' AND sm.periode_debut = '1991-01-01')
              AND NOT EXISTS (
                SELECT 1 FROM series_metadonnees sm WHERE sm.localite_id = l.id
                  AND sm.grandeur_code = 'humidex')
            ORDER BY l.code
            """
        )
    ).all()
    return [(int(r.id), str(r.code)) for r in rows]


def _seed_serie(
    session: Session,
    *,
    code: str,
    grandeur: str,
    localite_id: int,
    source_id: int,
    commune: str,
    amont_label: str,
) -> int:
    """Cree une serie calculee recente kuma_calculs (mirror convention 030) et retourne
    son id. Doc/url renseignes (recent), comme les series calculees recentes existantes."""
    doc = f"{_URL_DOC_BASE}/{grandeur}.md"
    session.execute(
        sa.text(
            """
            INSERT INTO series_metadonnees
                (code, libelle, localite_id, grandeur_code, source_id, periode_debut,
                 periode_fin, methode_collecte, methode_collecte_doc, commentaire_editorial,
                 url_documentation)
            VALUES (:code, :libelle, :loc, :g, :src, :pd, :pf, :meth, :doc, :comm, :doc)
            """
        ),
        {
            "code": code,
            "libelle": f"{grandeur} {commune} {_RECENT_DEBUT}-{_RECENT_FIN} (calcul Kuma)",
            "loc": localite_id,
            "g": grandeur,
            "src": source_id,
            "pd": date(_RECENT_DEBUT, 1, 1),
            "pf": date(_RECENT_FIN, 12, 31),
            "meth": _METHODE,
            "doc": doc,
            "comm": f"Serie {grandeur} calculee Kuma a partir de {amont_label}. "
            f"Densification parite A2 (meme traitement que les 6 pilotes). Confiance B.",
        },
    )
    return int(
        session.execute(
            sa.text("SELECT id FROM series_metadonnees WHERE code = :c"), {"c": code}
        ).scalar_one()
    )


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        source_id = int(
            session.execute(
                sa.text("SELECT id FROM sources WHERE code = :c"), {"c": _SOURCE_KUMA}
            ).scalar_one()
        )
        points = _points_a2(session)
        if len(points) != 28:
            raise RuntimeError(f"Migration 093 : attendu 28 communes, enumere {len(points)}.")

        # === Grandeurs calculees recentes (humidex, variabilite, rang_temporel) =====
        for localite_id, commune in points:
            ghi_rec = _code(commune, "ghi", "nasa_power", _RECENT_DEBUT, _RECENT_FIN)

            # humidex (orchestrateur derive la confiance)
            code_humidex = _code(commune, "humidex", "kuma_calculs", _RECENT_DEBUT, _RECENT_FIN)
            _seed_serie(
                session,
                code=code_humidex,
                grandeur="humidex",
                localite_id=localite_id,
                source_id=source_id,
                commune=commune,
                amont_label=f"T2M + RH2M daily {commune} {_RECENT_DEBUT}-{_RECENT_FIN}",
            )
            calculer_et_inserer_humidex(
                session=session,
                code_serie_humidex=code_humidex,
                code_serie_t2m_amont=_code(
                    commune, "t2m", "nasa_power", _RECENT_DEBUT, _RECENT_FIN
                ),
                code_serie_rh2m_amont=_code(
                    commune, "rh2m", "nasa_power", _RECENT_DEBUT, _RECENT_FIN
                ),
                version_formule=_VERSION,
            )

            # variabilite_journaliere (orchestrateur derive la confiance)
            code_variab = _code(
                commune, "variabilite_journaliere", "kuma_calculs", _RECENT_DEBUT, _RECENT_FIN
            )
            _seed_serie(
                session,
                code=code_variab,
                grandeur="variabilite_journaliere",
                localite_id=localite_id,
                source_id=source_id,
                commune=commune,
                amont_label=ghi_rec,
            )
            calculer_et_inserer_variabilite_journaliere(
                session=session,
                code_serie_variabilite=code_variab,
                code_serie_ghi_amont=ghi_rec,
                version_formule=_VERSION,
            )

            # rang_referentiel_temporel (fonction FOCALISEE, jamais l'orchestrateur combine)
            code_rang = _code(
                commune, "rang_referentiel_temporel", "kuma_calculs", _RECENT_DEBUT, _RECENT_FIN
            )
            serie_rang_id = _seed_serie(
                session,
                code=code_rang,
                grandeur="rang_referentiel_temporel",
                localite_id=localite_id,
                source_id=source_id,
                commune=commune,
                amont_label=f"NASA daily {commune} vs climato GHI {_CLIMATO_DEBUT}-{_CLIMATO_FIN}",
            )
            contexte: ContexteRangTemporel = {
                "localite_id": localite_id,
                "code_serie_kuma_daily": ghi_rec,
                "code_serie_power_1991_2020": _code(
                    commune, "ghi", "power", _CLIMATO_DEBUT, _CLIMATO_FIN
                ),
                "series_metadonnees_id": serie_rang_id,
            }
            calculer_et_inserer_rang_temporel(session=session, contextes=[contexte])

        # === indicateur_qualite_donnees (parite stricte : 6 grandeurs des pilotes) ====
        grandeurs_indicateur = [
            str(r[0])
            for r in session.execute(
                sa.text(
                    """
                    SELECT DISTINCT sm.grandeur_code
                    FROM grandeurs_metier gm
                    JOIN series_metadonnees sm ON sm.id = gm.series_metadonnees_id
                    WHERE gm.grandeur_code = :ind
                    """
                ),
                {"ind": _GRANDEUR_INDICATEUR},
            ).all()
        ]
        if len(grandeurs_indicateur) != 6:
            raise RuntimeError(
                f"Migration 093 : attendu 6 grandeurs couvertes par l'indicateur pilote, "
                f"lu {len(grandeurs_indicateur)} ({sorted(grandeurs_indicateur)})."
            )

        commune_ids = [lid for lid, _ in points]
        codes_brutes = [
            str(r[0])
            for r in session.execute(
                sa.text(
                    """
                    SELECT sm.code FROM series_metadonnees sm
                    JOIN sources s ON s.id = sm.source_id
                    WHERE s.code = 'nasa_power'
                      AND sm.methode_collecte = 'modele_satellitaire'
                      AND sm.granularite = 'journalier'
                      AND sm.grandeur_code = ANY(:g)
                      AND sm.localite_id = ANY(:loc)
                    ORDER BY sm.code
                    """
                ),
                {"g": grandeurs_indicateur, "loc": commune_ids},
            ).all()
        ]
        if len(codes_brutes) != 168:
            raise RuntimeError(
                f"Migration 093 : attendu 168 series brutes daily (28 x 6), lu {len(codes_brutes)}."
            )
        for code_serie in codes_brutes:
            calculer_et_inserer_indicateur_qualite_donnees(
                session=session,
                code_serie_evaluee=code_serie,
                annee_debut=_RECENT_DEBUT,
                annee_fin=_RECENT_FIN,
                version_formule=_VERSION,
            )

        session.commit()
        op.execute(
            "-- Migration 093 parite A2 : humidex/variabilite/rang_temporel (focalise) + "
            "indicateur sur 28 communes. Zero ligne rang_referentiel_spatial creee."
        )
    finally:
        session.close()


def downgrade() -> None:
    # Communes = localites non pilotes ayant le GHI daily 2021-2025.
    filtre_communes = """
        sm.localite_id IN (
            SELECT l.id FROM localites l WHERE EXISTS (
                SELECT 1 FROM series_metadonnees x JOIN sources xs ON xs.id = x.source_id
                WHERE x.localite_id = l.id AND xs.code = 'nasa_power'
                  AND x.grandeur_code = 'ghi' AND x.granularite = 'journalier'
                  AND x.periode_debut = '2021-01-01')
            AND l.code NOT IN ('gin_conakry_kaloum','gin_kankan','gin_kindia',
                               'gin_labe','gin_mamou','gin_nzerekore'))
    """

    # 1. Lignes indicateur des communes (pointent les series brutes daily nasa_power).
    op.execute(
        sa.text(
            f"""
            DELETE FROM grandeurs_metier gm
            USING series_metadonnees sm, sources s
            WHERE gm.series_metadonnees_id = sm.id AND sm.source_id = s.id
              AND gm.grandeur_code = 'indicateur_qualite_donnees'
              AND s.code = 'nasa_power' AND sm.granularite = 'journalier'
              AND {filtre_communes}
            """
        )
    )

    # 2. Lignes grandeurs_metier des series calculees (humidex/variabilite/rang_temporel).
    op.execute(
        sa.text(
            f"""
            DELETE FROM grandeurs_metier WHERE series_metadonnees_id IN (
                SELECT sm.id FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
                WHERE s.code = 'kuma_calculs'
                  AND sm.grandeur_code IN ('humidex', 'variabilite_journaliere',
                                           'rang_referentiel_temporel')
                  AND {filtre_communes})
            """
        )
    )

    # 3. Series calculees elles-memes.
    op.execute(
        sa.text(
            f"""
            DELETE FROM series_metadonnees sm USING sources s
            WHERE sm.source_id = s.id AND s.code = 'kuma_calculs'
              AND sm.grandeur_code IN ('humidex', 'variabilite_journaliere',
                                       'rang_referentiel_temporel')
              AND {filtre_communes}
            """
        )
    )

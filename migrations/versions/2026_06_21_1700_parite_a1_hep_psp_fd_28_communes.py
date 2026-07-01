"""parite_a1_hep_psp_fd_28_communes

Revision ID: 092
Revises: 091
Create Date: 2026-06-21 17:00:00

Parite : etend les 3 grandeurs calculees radiatif-derivees (hep,
productible_specifique_theorique, fraction_diffuse) aux **28 communes chef-lieu**,
fenetres **climato** (hep/psp 1991-2020, fraction_diffuse 2001-2020) ET **recente**
(2021-2025). Meme traitement Core qu'aux 6 pilotes.

Migration SEULE (zero modif de module, zero fetch, zero impact pilote) :

- **Climato** : helpers purs DUPLIQUES VERBATIM de la migration 051 (immuable) -
  ``_calculer_hep_climato`` / ``_calculer_fraction_diffuse_climato`` (psp = hep * 0.8) ;
  confiance B hardcodee comme 051 (regle R4 appliquee uniforme inline). Fidelite > amelioration :
  on ne remplace PAS le B litteral par un appel derive (ferait diverger les 28 des 6).
- **Recent** : seed des series calculees (convention 030) puis appel des **orchestrateurs**
  existants ``calculer_et_inserer_hep`` / ``_fraction_diffuse`` / ``_productible_specifique_theorique``
  qui DERIVENT la confiance en interne (R4 -> B). Ordre obligatoire : hep -> fraction_diffuse
  -> productible (le productible consomme les lignes hep de grandeurs_metier).

Enumeration **data-driven** des 28 : localites ayant le GHI daily 2021-2025 ET le GHI
monthly 1991-2020, SANS serie hep (robuste, prouve 28). Series amont presentes aux 28
(densification migration 086 daily, migration 087 monthly). Naming des series :
``gin_<commune>_<grandeur>_kuma_calculs_<fenetre>`` (pas d'alias, les communes ne sont pas
Conakry). Grandeurs declarees en 010 (immuable) : pas de re-declaration.

rang_referentiel_spatial HORS lot (pool pilote fige, consommateurs media pool-6 codes en
dur). humidex/variabilite/rang_temporel/indicateur sont traites separement.
"""

from __future__ import annotations

import calendar
from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.services.grandeurs.fraction_diffuse import calculer_et_inserer_fraction_diffuse
from kuma_data_core.services.grandeurs.hep import calculer_et_inserer_hep
from kuma_data_core.services.grandeurs.productible_specifique_theorique import (
    PR_THEORIQUE_DEFAUT,
    calculer_et_inserer_productible_specifique_theorique,
)

# revision identifiers, used by Alembic.
revision: str = "092"
down_revision: str | Sequence[str] | None = "091"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Constantes ============================================================
_SOURCE_KUMA = "kuma_calculs"
_METHODE = "calcul_derive"
_NIVEAU_CONFIANCE_CLIMATO = "B"  # hardcode mirror 051 (fidelite verbatim, NE PAS deriver).
_STATUT = "brut"
_VERSION = 1
_PR_THEORIQUE = 0.8  # mirror 051 (= PR_THEORIQUE_DEFAUT du module recent).

_HEP_PSP_CLIMATO_DEBUT, _HEP_PSP_CLIMATO_FIN = 1991, 2020
_FD_CLIMATO_DEBUT, _FD_CLIMATO_FIN = 2001, 2020
_RECENT_DEBUT, _RECENT_FIN = 2021, 2025
_URL_DOC_BASE = "docs/methodologie/grandeurs"


# === Helpers purs DUPLIQUES VERBATIM de la migration 051 (immuable) ========
# Toute modification de formule ici ferait diverger les 28 des 6 pilotes.


def _calculer_hep_climato(
    valeurs_ghi_mensuelles: list[tuple[int, int, float]],
) -> tuple[list[tuple[int, int, float]], list[tuple[int, float]]]:
    """HEP mensuel + annuel depuis le GHI mensuel climato (verbatim 051)."""
    mensuelles: list[tuple[int, int, float]] = []
    annuelles_par_annee: dict[int, float] = {}
    for annee, mois, ghi_kwh_m2_jour in valeurs_ghi_mensuelles:
        nb_jours = calendar.monthrange(annee, mois)[1]
        hep_mois = float(ghi_kwh_m2_jour) * nb_jours
        mensuelles.append((annee, mois, hep_mois))
        annuelles_par_annee[annee] = annuelles_par_annee.get(annee, 0.0) + hep_mois
    annuelles = sorted(annuelles_par_annee.items())
    return mensuelles, annuelles


def _calculer_fraction_diffuse_climato(
    valeurs_dhi_mensuelles: list[tuple[int, int, float]],
    valeurs_ghi_mensuelles_2001_2020: list[tuple[int, int, float]],
) -> tuple[list[tuple[int, int, float]], list[tuple[int, float]]]:
    """fraction_diffuse mensuelle + annuelle sur le recouvrement 2001-2020 (verbatim 051)."""
    dhi_par_cle: dict[tuple[int, int], float] = {
        (y, m): float(v) for y, m, v in valeurs_dhi_mensuelles
    }
    ghi_par_cle: dict[tuple[int, int], float] = {
        (y, m): float(v) for y, m, v in valeurs_ghi_mensuelles_2001_2020
    }
    cles_communes = sorted(set(dhi_par_cle) & set(ghi_par_cle))
    if len(cles_communes) != len(dhi_par_cle) or len(cles_communes) != len(ghi_par_cle):
        raise RuntimeError("Migration 092 : couverture DHI/GHI heterogene sur 2001-2020.")
    mensuelles: list[tuple[int, int, float]] = []
    energie_dhi_par_annee: dict[int, float] = {}
    energie_ghi_par_annee: dict[int, float] = {}
    for annee, mois in cles_communes:
        dhi_mois = dhi_par_cle[(annee, mois)]
        ghi_mois = ghi_par_cle[(annee, mois)]
        if ghi_mois <= 0.0:
            raise RuntimeError(f"Migration 092 : GHI mensuel <= 0 pour ({annee}, {mois}).")
        mensuelles.append((annee, mois, dhi_mois / ghi_mois))
        nb_jours = calendar.monthrange(annee, mois)[1]
        energie_dhi_par_annee[annee] = energie_dhi_par_annee.get(annee, 0.0) + dhi_mois * nb_jours
        energie_ghi_par_annee[annee] = energie_ghi_par_annee.get(annee, 0.0) + ghi_mois * nb_jours
    annuelles: list[tuple[int, float]] = []
    for annee in sorted(energie_dhi_par_annee):
        e_dhi, e_ghi = energie_dhi_par_annee[annee], energie_ghi_par_annee[annee]
        if e_ghi <= 0.0:
            raise RuntimeError(f"Migration 092 : energie annuelle GHI <= 0 pour {annee}.")
        annuelles.append((annee, e_dhi / e_ghi))
    return mensuelles, annuelles


# === Helpers I/O ===========================================================


def _points_a1(session: Session) -> list[tuple[int, str]]:
    """Enumeration data-driven : les 28 communes (GHI daily 2021-2025 + monthly 1991-2020,
    sans serie hep). Robuste a une densification future."""
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
                  AND sm.grandeur_code = 'hep')
            ORDER BY l.code
            """
        )
    ).all()
    return [(int(r.id), str(r.code)) for r in rows]


def _lire_mensuel(session: Session, code_serie: str) -> list[tuple[int, int, float]]:
    rows = session.execute(
        sa.text(
            """
            SELECT m.annee, m.mois, m.valeur FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            WHERE sm.code = :c AND m.valide_au IS NULL ORDER BY m.annee, m.mois
            """
        ),
        {"c": code_serie},
    ).all()
    if not rows:
        raise RuntimeError(
            f"Migration 092 : serie mensuelle amont {code_serie!r} introuvable/vide."
        )
    return [(int(r.annee), int(r.mois), float(r.valeur)) for r in rows]


def _seed_serie_calculee(
    session: Session,
    *,
    code: str,
    grandeur: str,
    localite_id: int,
    source_id: int,
    an_debut: int,
    an_fin: int,
    commune: str,
    amont_label: str,
    avec_doc: bool,
) -> None:
    """Cree une serie calculee kuma_calculs. ``avec_doc`` : recent (mirror 030, doc/url
    renseignes) vs climato (mirror 051, doc/url NULL)."""
    doc = f"{_URL_DOC_BASE}/{grandeur}.md" if avec_doc else None
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
            "libelle": f"{grandeur} {commune} {an_debut}-{an_fin} (calcul Kuma)",
            "loc": localite_id,
            "g": grandeur,
            "src": source_id,
            "pd": date(an_debut, 1, 1),
            "pf": date(an_fin, 12, 31),
            "meth": _METHODE,
            "doc": doc,
            "comm": f"Serie {grandeur} calculee Kuma a partir de {amont_label}. "
            f"Densification parite A1 (meme traitement que les 6 pilotes). Confiance B.",
        },
    )


def _id_serie(session: Session, code: str) -> int:
    return int(
        session.execute(
            sa.text("SELECT id FROM series_metadonnees WHERE code = :c"), {"c": code}
        ).scalar_one()
    )


def _inserer_climato(
    session: Session,
    *,
    grandeur: str,
    localite_id: int,
    serie_id: int,
    mensuelles: list[tuple[int, int, float]],
    annuelles: list[tuple[int, float]],
) -> int:
    """Bulk insert grandeurs_metier climato (confiance B hardcodee, mirror 051)."""
    lignes: list[dict[str, Any]] = []
    for annee, mois, valeur in mensuelles:
        lignes.append(
            {
                "grandeur_code": grandeur,
                "localite_id": localite_id,
                "series_metadonnees_id": serie_id,
                "periode_type": "mensuel",
                "annee_debut": annee,
                "annee_fin": annee,
                "mois": mois,
                "version_formule": _VERSION,
                "valeur": valeur,
                "niveau_confiance_derive": _NIVEAU_CONFIANCE_CLIMATO,
                "statut": _STATUT,
            }
        )
    for annee, valeur in annuelles:
        lignes.append(
            {
                "grandeur_code": grandeur,
                "localite_id": localite_id,
                "series_metadonnees_id": serie_id,
                "periode_type": "annuel",
                "annee_debut": annee,
                "annee_fin": annee,
                "mois": None,
                "version_formule": _VERSION,
                "valeur": valeur,
                "niveau_confiance_derive": _NIVEAU_CONFIANCE_CLIMATO,
                "statut": _STATUT,
            }
        )
    session.execute(
        sa.text(
            """
            INSERT INTO grandeurs_metier
                (grandeur_code, localite_id, series_metadonnees_id, periode_type,
                 annee_debut, annee_fin, mois, version_formule, valeur,
                 niveau_confiance_derive, statut)
            VALUES (:grandeur_code, :localite_id, :series_metadonnees_id, :periode_type,
                    :annee_debut, :annee_fin, :mois, :version_formule, :valeur,
                    :niveau_confiance_derive, :statut)
            """
        ),
        lignes,
    )
    return len(lignes)


def _code(commune: str, grandeur: str, source: str, an_debut: int, an_fin: int) -> str:
    return f"{commune}_{grandeur}_{source}_{an_debut}_{an_fin}"


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        source_id = int(
            session.execute(
                sa.text("SELECT id FROM sources WHERE code = :c"), {"c": _SOURCE_KUMA}
            ).scalar_one()
        )
        points = _points_a1(session)
        if len(points) != 28:
            raise RuntimeError(f"Migration 092 : attendu 28 communes, enumere {len(points)}.")

        for localite_id, commune in points:
            # === CLIMATO (mirror 051) =====================================
            ghi_clim = _lire_mensuel(session, _code(commune, "ghi", "power", 1991, 2020))
            # hep climato 1991-2020
            hep_m, hep_a = _calculer_hep_climato(ghi_clim)
            code_hep_clim = _code(commune, "hep", "kuma_calculs", 1991, 2020)
            _seed_serie_calculee(
                session,
                code=code_hep_clim,
                grandeur="hep",
                localite_id=localite_id,
                source_id=source_id,
                an_debut=1991,
                an_fin=2020,
                commune=commune,
                amont_label=f"GHI mensuel {commune} 1991-2020",
                avec_doc=False,
            )
            _inserer_climato(
                session,
                grandeur="hep",
                localite_id=localite_id,
                serie_id=_id_serie(session, code_hep_clim),
                mensuelles=hep_m,
                annuelles=hep_a,
            )
            # psp climato = hep * 0.8
            psp_m = [(y, m, v * _PR_THEORIQUE) for y, m, v in hep_m]
            psp_a = [(y, v * _PR_THEORIQUE) for y, v in hep_a]
            code_psp_clim = _code(
                commune, "productible_specifique_theorique", "kuma_calculs", 1991, 2020
            )
            _seed_serie_calculee(
                session,
                code=code_psp_clim,
                grandeur="productible_specifique_theorique",
                localite_id=localite_id,
                source_id=source_id,
                an_debut=1991,
                an_fin=2020,
                commune=commune,
                amont_label=f"HEP climato {commune} * PR={_PR_THEORIQUE}",
                avec_doc=False,
            )
            _inserer_climato(
                session,
                grandeur="productible_specifique_theorique",
                localite_id=localite_id,
                serie_id=_id_serie(session, code_psp_clim),
                mensuelles=psp_m,
                annuelles=psp_a,
            )
            # fraction_diffuse climato 2001-2020
            dhi_clim = _lire_mensuel(session, _code(commune, "dhi", "power", 2001, 2020))
            ghi_2001 = [(y, m, v) for y, m, v in ghi_clim if y >= 2001]
            fd_m, fd_a = _calculer_fraction_diffuse_climato(dhi_clim, ghi_2001)
            code_fd_clim = _code(commune, "fraction_diffuse", "kuma_calculs", 2001, 2020)
            _seed_serie_calculee(
                session,
                code=code_fd_clim,
                grandeur="fraction_diffuse",
                localite_id=localite_id,
                source_id=source_id,
                an_debut=2001,
                an_fin=2020,
                commune=commune,
                amont_label=f"DHI/GHI mensuels {commune} 2001-2020",
                avec_doc=False,
            )
            _inserer_climato(
                session,
                grandeur="fraction_diffuse",
                localite_id=localite_id,
                serie_id=_id_serie(session, code_fd_clim),
                mensuelles=fd_m,
                annuelles=fd_a,
            )

            # === RECENT (orchestrateurs, ordre hep -> fd -> psp) ==========
            ghi_rec = _code(commune, "ghi", "nasa_power", 2021, 2025)
            dhi_rec = _code(commune, "dhi", "nasa_power", 2021, 2025)
            code_hep_rec = _code(commune, "hep", "kuma_calculs", 2021, 2025)
            code_fd_rec = _code(commune, "fraction_diffuse", "kuma_calculs", 2021, 2025)
            code_psp_rec = _code(
                commune, "productible_specifique_theorique", "kuma_calculs", 2021, 2025
            )
            _seed_serie_calculee(
                session,
                code=code_hep_rec,
                grandeur="hep",
                localite_id=localite_id,
                source_id=source_id,
                an_debut=2021,
                an_fin=2025,
                commune=commune,
                amont_label=ghi_rec,
                avec_doc=True,
            )
            _seed_serie_calculee(
                session,
                code=code_fd_rec,
                grandeur="fraction_diffuse",
                localite_id=localite_id,
                source_id=source_id,
                an_debut=2021,
                an_fin=2025,
                commune=commune,
                amont_label=f"{dhi_rec} + {ghi_rec}",
                avec_doc=True,
            )
            _seed_serie_calculee(
                session,
                code=code_psp_rec,
                grandeur="productible_specifique_theorique",
                localite_id=localite_id,
                source_id=source_id,
                an_debut=2021,
                an_fin=2025,
                commune=commune,
                amont_label=code_hep_rec,
                avec_doc=True,
            )
            calculer_et_inserer_hep(
                session=session,
                code_serie_hep=code_hep_rec,
                code_serie_ghi_amont=ghi_rec,
                version_formule=_VERSION,
            )
            calculer_et_inserer_fraction_diffuse(
                session=session,
                code_serie_fraction_diffuse=code_fd_rec,
                code_serie_dhi_amont=dhi_rec,
                code_serie_ghi_amont=ghi_rec,
                version_formule=_VERSION,
            )
            calculer_et_inserer_productible_specifique_theorique(
                session=session,
                code_serie_productible=code_psp_rec,
                code_serie_hep_amont=code_hep_rec,
                pr_theorique=PR_THEORIQUE_DEFAUT,
                version_formule=_VERSION,
            )
        session.commit()
        op.execute("-- Migration 092 parite A1 : hep/psp/fd climato+recent sur 28 communes.")
    finally:
        session.close()


def downgrade() -> None:
    # Toutes les series calculees des communes (suffixes des 3 grandeurs x 3 fenetres).
    op.execute(
        sa.text(
            """
            DELETE FROM grandeurs_metier WHERE series_metadonnees_id IN (
                SELECT sm.id FROM series_metadonnees sm JOIN sources s ON s.id = sm.source_id
                WHERE s.code = 'kuma_calculs'
                  AND sm.grandeur_code IN ('hep', 'productible_specifique_theorique', 'fraction_diffuse')
                  AND sm.localite_id IN (
                    SELECT l.id FROM localites l WHERE EXISTS (
                      SELECT 1 FROM series_metadonnees x JOIN sources xs ON xs.id = x.source_id
                      WHERE x.localite_id = l.id AND xs.code = 'nasa_power'
                        AND x.grandeur_code = 'ghi' AND x.granularite = 'journalier'
                        AND x.periode_debut = '2021-01-01')
                    AND l.code NOT IN ('gin_conakry_kaloum','gin_kankan','gin_kindia',
                                       'gin_labe','gin_mamou','gin_nzerekore')))
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM series_metadonnees sm USING sources s
            WHERE sm.source_id = s.id AND s.code = 'kuma_calculs'
              AND sm.grandeur_code IN ('hep', 'productible_specifique_theorique', 'fraction_diffuse')
              AND sm.localite_id IN (
                SELECT l.id FROM localites l WHERE EXISTS (
                  SELECT 1 FROM series_metadonnees x JOIN sources xs ON xs.id = x.source_id
                  WHERE x.localite_id = l.id AND xs.code = 'nasa_power'
                    AND x.grandeur_code = 'ghi' AND x.granularite = 'journalier'
                    AND x.periode_debut = '2021-01-01')
                AND l.code NOT IN ('gin_conakry_kaloum','gin_kankan','gin_kindia',
                                   'gin_labe','gin_mamou','gin_nzerekore'))
            """
        )
    )

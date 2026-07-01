"""seed_et_calcul_climato_kuma_hep_psp_fd_voletC_lot1

Revision ID: 051
Revises: 050
Create Date: 2026-05-25 11:00:00.000000+00:00

Donne aux 3 grandeurs F1 calculees
Kuma agregeables (linearites simples) la profondeur climatologique
mensuelle que seules les brutes possedent.

3 grandeurs F1 stockees seedees + calculees + insertion dans
``grandeurs_metier`` :

| Grandeur                         | Source(s)        | Fenetre   | Lignes/serie |
|----------------------------------|------------------|-----------|--------------|
| hep                              | GHI mensuel 1991 | 1991-2020 | 30 ans + 360 mois = 390 |
| productible_specifique_theorique | hep climato      | 1991-2020 | 390          |
| fraction_diffuse                 | DHI 2001 + GHI 1991 (recouvrement) | 2001-2020 | 20 ans + 240 mois = 260 |

18 series x 6 villes seedees ; volume cible 6 240 lignes
(2 340 hep + 2 340 productible + 1 560 fraction_diffuse).

Resolution explicite des series source par code, AUCUN appel a
``_chercher_serie_compagne`` (pas d'inference de fenetre, contournement
du filtre strict ``periode_debut = source.periode_debut``).

Formules (alignees sur les modules services/grandeurs/ existants,
adaptees aux moyennes mensuelles climato) :

- HEP_mensuel(y, m) = GHI_mois(y, m) * calendar.monthrange(y, m)[1]
  ou GHI_mois est la moyenne quotidienne mensuelle climato en
  kWh/m²/jour. Numeriquement equivalent a SUM(GHI_jour) sur le mois
  (convention HEP 1 kWh/m² = 1 h_eq a 1 kW/m² STC).
- HEP_annuel(y) = somme des 12 HEP_mensuels de l'annee y.
- PSP_mensuel(y, m) = HEP_mensuel(y, m) * 0.8 (PR_THEORIQUE_DEFAUT,
  cf. services/grandeurs/productible_specifique_theorique.py).
- PSP_annuel(y) = HEP_annuel(y) * 0.8.
- FD_mensuel(y, m) = DHI_mois(y, m) / GHI_mois(y, m), ratio des
  moyennes quotidiennes (= ratio des sommes mensuelles).
- FD_annuel(y) = somme(DHI_mois * nb_jours) / somme(GHI_mois * nb_jours)
  sur les 12 mois de l'annee y, ratio des totaux annuels en
  kWh/m²/an.

Niveau de confiance derive 'B' uniforme (cf.
``editorial.niveaux_confiance.calculer_niveau_confiance_derive``
appliquee a methode_collecte='calcul_derive' + source.fiabilite='haute'
-> R4 catch-all). Hardcode pour eviter une dependance applicative.

Naming aligne strictement sur le pattern existant 2021-2025 :
``gin_<ville>_<grandeur>_kuma_calculs_<an_debut>_<an_fin>``. Source SQL :
``kuma_calculs`` (seed initial des sources, id=10, fiabilite=haute).
Exception Conakry-Kaloum : prefixe ``gin_conakry`` via helper local
``_prefixe_ville_pour_serie`` (duplique de 041/050).

Exposition automatique via ``/v1/series`` (resolution table-cible
``resolve_table_from_series_metadata('kuma_calculs', ...)`` ->
``grandeurs_metier``, independante de l'annee). Aucune modification de
code applicatif.

Cycle alembic downgrade/upgrade verifie reversible et idempotent : le
downgrade utilise les codes du mapping
courant pour supprimer exactement ce que l'upgrade ajoute.

Hors scope : ``humidex`` (non-linearite Masterton-Richardson, a
arbitrer apres mesure empirique du biais), ``poa_parametrable``
(chantier dedie), F2 parametrables (calcul a la volee, chantier
ulterieur si requis). Variabilite_journaliere et degre_jour_climatisation
definitivement hors perimetre climato (CoV intra-periode / comptage de
seuils non agregeables).
"""

from __future__ import annotations

import calendar
from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "051"
down_revision: str | Sequence[str] | None = "050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Constantes (énumérations exhaustives) =========================

_LOCALITES_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)

_LIBELLES_VILLES: dict[str, str] = {
    "gin_conakry_kaloum": "Conakry-Kaloum",
    "gin_kankan": "Kankan",
    "gin_kindia": "Kindia",
    "gin_labe": "Labe",
    "gin_mamou": "Mamou",
    "gin_nzerekore": "Nzerekore",
}

_SOURCE_CODE_SQL: str = "kuma_calculs"
_METHODE_COLLECTE: str = "calcul_derive"
_NIVEAU_CONFIANCE_DERIVE: str = "B"
_STATUT_INITIAL: str = "brut"
_VERSION_FORMULE: int = 1

# Constante PR theorique alignee sur
# services/grandeurs/productible_specifique_theorique.py:PR_THEORIQUE_DEFAUT.
_PR_THEORIQUE: float = 0.8

# Fenetres des series climato a creer.
_FENETRE_HEP_PSP_DEBUT: int = 1991
_FENETRE_HEP_PSP_FIN: int = 2020
_FENETRE_FD_DEBUT: int = 2001
_FENETRE_FD_FIN: int = 2020

# Codes des series climato amont (migration 050).
# Pas d'inference via _chercher_serie_compagne : resolution par code.


def _prefixe_ville_pour_serie(localite_code: str) -> str:
    """Prefixe ville pour code serie (exception Conakry-Kaloum).

    Duplique du helper des migrations 041 / 050 (immuabilite post-merge
    des migrations : pas d'import croise).
    """
    if localite_code == "gin_conakry_kaloum":
        return "gin_conakry"
    return localite_code


def _code_serie_brute_mensuelle(localite_code: str, grandeur: str, annee_debut: int) -> str:
    """Code d'une serie brute mensuelle ``power`` (climato mensuelle)."""
    return (
        f"{_prefixe_ville_pour_serie(localite_code)}_{grandeur}_power_"
        f"{annee_debut}_{_FENETRE_HEP_PSP_FIN}"
    )


def _code_serie_calculee(localite_code: str, grandeur: str, annee_debut: int) -> str:
    """Code d'une serie calculee Kuma climato."""
    return (
        f"{_prefixe_ville_pour_serie(localite_code)}_{grandeur}_kuma_calculs_"
        f"{annee_debut}_{_FENETRE_HEP_PSP_FIN}"
    )


# === Helpers de calcul (pures) ============================================


def _calculer_hep_climato(
    valeurs_ghi_mensuelles: list[tuple[int, int, float]],
) -> tuple[list[tuple[int, int, float]], list[tuple[int, float]]]:
    """Calcule HEP mensuel + annuel a partir du GHI mensuel climato.

    Args:
        valeurs_ghi_mensuelles : liste de (annee, mois, GHI_kWh_par_m2_jour).

    Returns:
        Tuple (lignes_mensuelles, lignes_annuelles) ou :
        - lignes_mensuelles = list[(annee, mois, hep_mensuel)]
        - lignes_annuelles = list[(annee, hep_annuel)]
        HEP mensuel/annuel exprime en h_eq (numerique = kWh/m²/periode).
    """
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
    """Calcule fraction_diffuse mensuelle + annuelle sur le recouvrement 2001-2020.

    Args:
        valeurs_dhi_mensuelles : liste (annee, mois, DHI_kWh_par_m2_jour),
            attendue sur 2001-2020 (240 entrees).
        valeurs_ghi_mensuelles_2001_2020 : liste (annee, mois,
            GHI_kWh_par_m2_jour), restreinte a 2001-2020 (240 entrees).

    Returns:
        Tuple (lignes_mensuelles, lignes_annuelles).

    Raises:
        RuntimeError : si les deux series ne couvrent pas exactement les
            memes (annee, mois) sur 2001-2020.
    """
    dhi_par_cle: dict[tuple[int, int], float] = {
        (y, m): float(v) for y, m, v in valeurs_dhi_mensuelles
    }
    ghi_par_cle: dict[tuple[int, int], float] = {
        (y, m): float(v) for y, m, v in valeurs_ghi_mensuelles_2001_2020
    }
    cles_communes = sorted(set(dhi_par_cle) & set(ghi_par_cle))
    if len(cles_communes) != len(dhi_par_cle) or len(cles_communes) != len(ghi_par_cle):
        manquantes_dhi = set(ghi_par_cle) - set(dhi_par_cle)
        manquantes_ghi = set(dhi_par_cle) - set(ghi_par_cle)
        raise RuntimeError(
            f"Migration 051 : couverture DHI/GHI heterogene sur 2001-2020. "
            f"DHI sans GHI : {sorted(manquantes_ghi)[:5]}... "
            f"GHI sans DHI : {sorted(manquantes_dhi)[:5]}..."
        )

    mensuelles: list[tuple[int, int, float]] = []
    energie_dhi_par_annee: dict[int, float] = {}
    energie_ghi_par_annee: dict[int, float] = {}
    for annee, mois in cles_communes:
        dhi_mois = dhi_par_cle[(annee, mois)]
        ghi_mois = ghi_par_cle[(annee, mois)]
        if ghi_mois <= 0.0:
            raise RuntimeError(
                f"Migration 051 : GHI mensuel <= 0 pour ({annee}, {mois}), calcul ratio impossible."
            )
        mensuelles.append((annee, mois, dhi_mois / ghi_mois))
        nb_jours = calendar.monthrange(annee, mois)[1]
        energie_dhi_par_annee[annee] = energie_dhi_par_annee.get(annee, 0.0) + dhi_mois * nb_jours
        energie_ghi_par_annee[annee] = energie_ghi_par_annee.get(annee, 0.0) + ghi_mois * nb_jours

    annuelles: list[tuple[int, float]] = []
    for annee in sorted(energie_dhi_par_annee):
        e_dhi = energie_dhi_par_annee[annee]
        e_ghi = energie_ghi_par_annee[annee]
        if e_ghi <= 0.0:
            raise RuntimeError(
                f"Migration 051 : energie annuelle GHI <= 0 pour {annee}, ratio annuel impossible."
            )
        annuelles.append((annee, e_dhi / e_ghi))

    return mensuelles, annuelles


# === Helpers de seed + insert (orchestrateurs SQL) ========================


def _resoudre_serie_amont(bind: sa.engine.Connection, code_serie: str) -> int:
    """Resout un code D-32 -> serie_id. RuntimeError si absente."""
    serie_id = bind.execute(
        sa.text("SELECT id FROM series_metadonnees WHERE code = :code"),
        {"code": code_serie},
    ).scalar_one_or_none()
    if serie_id is None:
        raise RuntimeError(
            f"Migration 051 : serie amont {code_serie!r} introuvable. "
            f"Verifier que la migration 050 (vague 2 volet A) a bien ete appliquee."
        )
    return int(serie_id)


def _lire_serie_mensuelle(
    bind: sa.engine.Connection, serie_id: int
) -> list[tuple[int, int, float]]:
    """Lit toutes les valeurs mensuelles courantes d'une serie."""
    rows = bind.execute(
        sa.text(
            """
            SELECT annee, mois, valeur
            FROM mesures_ressource_mensuelles
            WHERE serie_id = :serie_id AND valide_au IS NULL
            ORDER BY annee, mois
            """
        ),
        {"serie_id": serie_id},
    ).all()
    return [(int(r.annee), int(r.mois), float(r.valeur)) for r in rows]


def _seed_serie_calculee(
    bind: sa.engine.Connection,
    code: str,
    grandeur: str,
    localite_id: int,
    source_id: int,
    annee_debut: int,
    annee_fin: int,
    libelle_ville: str,
    source_amont_label: str,
) -> int:
    """Insere une serie dans series_metadonnees et retourne son id."""
    libelle_grandeurs = {
        "hep": "HEP climato mensuelle",
        "productible_specifique_theorique": "Productible specifique theorique climato mensuel",
        "fraction_diffuse": "Fraction diffuse climato mensuelle",
    }
    libelle = (
        f"{libelle_grandeurs[grandeur]} {libelle_ville} {annee_debut}-{annee_fin} "
        f"(Kuma calculs, derive de {source_amont_label})"
    )
    commentaire = (
        f"Serie calculee Kuma climato (vague 2 volet C lot 1, mai 2026). "
        f"Grandeur {grandeur} calculee a partir de {source_amont_label} sur la "
        f"fenetre {annee_debut}-{annee_fin}. Localite : {libelle_ville}, Guinee. "
        f"Niveau de confiance derive B (catch-all R4, source kuma_calculs "
        f"fiabilite haute, methode_collecte calcul_derive)."
    )
    serie_id = bind.execute(
        sa.text(
            """
            INSERT INTO series_metadonnees (
                code, libelle, localite_id, grandeur_code, source_id,
                periode_debut, periode_fin,
                methode_collecte, methode_collecte_doc,
                commentaire_editorial, url_documentation
            )
            VALUES (
                :code, :libelle, :localite_id, :grandeur, :source_id,
                :periode_debut, :periode_fin,
                :methode_collecte, NULL,
                :commentaire, NULL
            )
            RETURNING id
            """
        ),
        {
            "code": code,
            "libelle": libelle,
            "localite_id": localite_id,
            "grandeur": grandeur,
            "source_id": source_id,
            "periode_debut": date(annee_debut, 1, 1),
            "periode_fin": date(annee_fin, 12, 31),
            "methode_collecte": _METHODE_COLLECTE,
            "commentaire": commentaire,
        },
    ).scalar_one()
    return int(serie_id)


def _inserer_lignes_grandeurs_metier(
    bind: sa.engine.Connection,
    grandeur: str,
    localite_id: int,
    serie_id: int,
    mensuelles: list[tuple[int, int, float]],
    annuelles: list[tuple[int, float]],
) -> int:
    """Bulk INSERT des lignes mensuelles + annuelles dans grandeurs_metier."""
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
                "version_formule": _VERSION_FORMULE,
                "valeur": valeur,
                "niveau_confiance_derive": _NIVEAU_CONFIANCE_DERIVE,
                "statut": _STATUT_INITIAL,
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
                "version_formule": _VERSION_FORMULE,
                "valeur": valeur,
                "niveau_confiance_derive": _NIVEAU_CONFIANCE_DERIVE,
                "statut": _STATUT_INITIAL,
            }
        )
    if not lignes:
        return 0
    bind.execute(
        sa.text(
            """
            INSERT INTO grandeurs_metier (
                grandeur_code, localite_id, series_metadonnees_id,
                periode_type, annee_debut, annee_fin, mois, version_formule,
                valeur, niveau_confiance_derive, statut
            )
            VALUES (
                :grandeur_code, :localite_id, :series_metadonnees_id,
                :periode_type, :annee_debut, :annee_fin, :mois, :version_formule,
                :valeur, :niveau_confiance_derive, :statut
            )
            """
        ),
        lignes,
    )
    return len(lignes)


def upgrade() -> None:
    bind = op.get_bind()

    # === Etape 1 : resolution des IDs (localites + source kuma_calculs) ===
    lignes_localites = bind.execute(
        sa.text("SELECT code, id FROM localites WHERE code = ANY(:codes)"),
        {"codes": list(_LOCALITES_PILOTES)},
    ).all()
    localite_id_par_code: dict[str, int] = {r.code: int(r.id) for r in lignes_localites}
    manquantes = set(_LOCALITES_PILOTES) - localite_id_par_code.keys()
    if manquantes:
        raise RuntimeError(f"Migration 051 : localites introuvables : {sorted(manquantes)}")

    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :code"),
        {"code": _SOURCE_CODE_SQL},
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(f"Migration 051 : source {_SOURCE_CODE_SQL!r} introuvable (seed 1-1E).")

    # === Etape 2 : boucle par ville, calcul + seed + insert =================
    decomptes_par_serie: dict[str, int] = {}
    for localite_code in _LOCALITES_PILOTES:
        localite_id = localite_id_par_code[localite_code]
        libelle_ville = _LIBELLES_VILLES[localite_code]

        # Lecture commune : serie GHI mensuelle 1991-2020 (pour HEP/PSP).
        code_ghi = _code_serie_brute_mensuelle(localite_code, "ghi", _FENETRE_HEP_PSP_DEBUT)
        serie_ghi_id = _resoudre_serie_amont(bind, code_ghi)
        valeurs_ghi = _lire_serie_mensuelle(bind, serie_ghi_id)

        # 2.a HEP climato 1991-2020 (390 lignes)
        hep_mens, hep_annu = _calculer_hep_climato(valeurs_ghi)
        code_hep = _code_serie_calculee(localite_code, "hep", _FENETRE_HEP_PSP_DEBUT)
        serie_hep_id = _seed_serie_calculee(
            bind,
            code=code_hep,
            grandeur="hep",
            localite_id=localite_id,
            source_id=int(source_id),
            annee_debut=_FENETRE_HEP_PSP_DEBUT,
            annee_fin=_FENETRE_HEP_PSP_FIN,
            libelle_ville=libelle_ville,
            source_amont_label=f"{code_ghi} (GHI mensuel NASA POWER)",
        )
        decomptes_par_serie[code_hep] = _inserer_lignes_grandeurs_metier(
            bind, "hep", localite_id, serie_hep_id, hep_mens, hep_annu
        )

        # 2.b PSP climato 1991-2020 (hep * 0.8, 390 lignes)
        psp_mens = [(y, m, v * _PR_THEORIQUE) for y, m, v in hep_mens]
        psp_annu = [(y, v * _PR_THEORIQUE) for y, v in hep_annu]
        code_psp = _code_serie_calculee(
            localite_code, "productible_specifique_theorique", _FENETRE_HEP_PSP_DEBUT
        )
        serie_psp_id = _seed_serie_calculee(
            bind,
            code=code_psp,
            grandeur="productible_specifique_theorique",
            localite_id=localite_id,
            source_id=int(source_id),
            annee_debut=_FENETRE_HEP_PSP_DEBUT,
            annee_fin=_FENETRE_HEP_PSP_FIN,
            libelle_ville=libelle_ville,
            source_amont_label=f"{code_hep} (HEP climato) * PR_theorique={_PR_THEORIQUE}",
        )
        decomptes_par_serie[code_psp] = _inserer_lignes_grandeurs_metier(
            bind,
            "productible_specifique_theorique",
            localite_id,
            serie_psp_id,
            psp_mens,
            psp_annu,
        )

        # 2.c fraction_diffuse climato 2001-2020 (recouvrement)
        code_dhi = _code_serie_brute_mensuelle(localite_code, "dhi", _FENETRE_FD_DEBUT)
        serie_dhi_id = _resoudre_serie_amont(bind, code_dhi)
        valeurs_dhi = _lire_serie_mensuelle(bind, serie_dhi_id)
        valeurs_ghi_2001_2020 = [(y, m, v) for y, m, v in valeurs_ghi if y >= _FENETRE_FD_DEBUT]
        fd_mens, fd_annu = _calculer_fraction_diffuse_climato(valeurs_dhi, valeurs_ghi_2001_2020)
        code_fd = _code_serie_calculee(localite_code, "fraction_diffuse", _FENETRE_FD_DEBUT)
        # Note : annee_fin de la serie = 2020, identique au pattern HEP/PSP.
        # Le calcul fraction_diffuse partage la meme annee_fin.
        serie_fd_id = _seed_serie_calculee(
            bind,
            code=code_fd,
            grandeur="fraction_diffuse",
            localite_id=localite_id,
            source_id=int(source_id),
            annee_debut=_FENETRE_FD_DEBUT,
            annee_fin=_FENETRE_HEP_PSP_FIN,
            libelle_ville=libelle_ville,
            source_amont_label=f"DHI {code_dhi} / GHI {code_ghi} restreint 2001-2020",
        )
        decomptes_par_serie[code_fd] = _inserer_lignes_grandeurs_metier(
            bind, "fraction_diffuse", localite_id, serie_fd_id, fd_mens, fd_annu
        )

    total = sum(decomptes_par_serie.values())
    op.execute(
        f"-- Migration 051 (volet C lot 1) : {total} lignes inserees dans "
        f"grandeurs_metier sur 18 series (6 villes x 3 grandeurs). "
        f"Decompte par serie : {decomptes_par_serie}"
    )


def downgrade() -> None:
    # Codes series a supprimer (deterministe, mapping courant).
    codes_series: list[str] = []
    for localite_code in _LOCALITES_PILOTES:
        codes_series.append(_code_serie_calculee(localite_code, "hep", _FENETRE_HEP_PSP_DEBUT))
        codes_series.append(
            _code_serie_calculee(
                localite_code, "productible_specifique_theorique", _FENETRE_HEP_PSP_DEBUT
            )
        )
        codes_series.append(
            _code_serie_calculee(localite_code, "fraction_diffuse", _FENETRE_FD_DEBUT)
        )

    # Suppression des lignes grandeurs_metier avant les series.
    op.execute(
        sa.text(
            """
            DELETE FROM grandeurs_metier
            WHERE series_metadonnees_id IN (
                SELECT id FROM series_metadonnees WHERE code = ANY(:codes)
            )
            """
        ).bindparams(codes=codes_series)
    )
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_series)
        )
    )

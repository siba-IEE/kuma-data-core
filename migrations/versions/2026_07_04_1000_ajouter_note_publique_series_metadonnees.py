"""ajouter_note_publique_series_metadonnees

Revision ID: 099
Revises: 098
Create Date: 2026-07-04 10:00:00.000000+00:00

Sépare le passeport public d'une série de son journal de chantier.

``commentaire_editorial`` a servi de journal de bord interne depuis la
phase 0 : 80 % des 1444 notes portent du vocabulaire de chantier
(étapes, cohortes, lots, vagues, identifiants de dettes D-n, renvois
PR/spec du dépôt privé). Or ce champ est devenu public trois fois :
l'API le sert sous l'alias ``notes_fr``, le site kuma-science
l'affiche sur chaque fiche (bloc « Note de série »), et l'édition
publique le dumpe.

Décision (2026-07-04, prolonge l'esprit ADR-0003) :

- nouvelle colonne ``note_publique`` : le passeport public
  auto-portant, généré ici par gabarits (source x granularité, avec
  déclinaisons par grandeur pour ``kuma_calculs`` et notes sur mesure
  pour la station sol ESMAP/WAPP). Charpente commune : quoi et où,
  d'où ça vient et comment, niveau de confiance et pourquoi, limites
  connues s'il y en a. Corpus prévisualisé et validé éditorialement
  avant cette migration.
- ``commentaire_editorial`` reste le journal interne, intact. Il sort
  du périmètre public : bascule de ``series_metadonnees`` en table
  assainie du manifeste de publication (même PR), et l'API sert
  désormais ``note_publique`` sous l'alias ``notes_fr``.

La note PSP anticipe la migration 100 (résorption D-63, option a) :
elle annonce des valeurs en totaux par période.

Doctrine pour les ingestions futures : toute nouvelle série doit
renseigner ``note_publique`` à l'insertion. La colonne reste nullable
(les séries antérieures à une future ingestion ratée ne doivent pas
bloquer l'upgrade), le test d'intégration dédié verrouille la
non-nullité effective du parc.

Trigger d'audit : ``kuma_log_audit()`` journalise les UPDATE ;
``auteur_applicatif`` NULL (seedé par migration, pattern phase 0).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "099"
down_revision: str | Sequence[str] | None = "098"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Gabarits de note publique (corpus validé le 2026-07-04)
# ---------------------------------------------------------------------------

_GRAN_LISIBLE: dict[str, str] = {
    "mensuel": "au pas mensuel",
    "journalier": "au pas journalier",
    "horaire": "au pas horaire",
}

_CONF_B_MODELE = (
    "Niveau de confiance B : donnée de modèle, non validée par une mesure au sol à ce jour."
)

_SOURCES_CORPS: dict[str, str] = {
    "nasa_power": (
        "Données ingérées depuis NASA POWER, le service de données solaires et "
        "météorologiques de la NASA (rayonnement du modèle satellitaire CERES SYN1deg, "
        "variables météo de la réanalyse MERRA-2)."
    ),
    "ecmwf_era5_land": (
        "Données issues de la réanalyse ERA5-Land du centre européen ECMWF "
        "(résolution d'environ 9 km), utilisée comme source de recoupement."
    ),
    "cams_radiation": (
        "Données issues du service Copernicus CAMS Radiation (méthode Héliosat-4, "
        "prise en compte des aérosols), référence de cette base pour l'irradiation directe."
    ),
    "cams_eac4": (
        "Données issues de la réanalyse de composition atmosphérique Copernicus CAMS EAC4 "
        "(résolution d'environ 80 km). Le signal est régional : il décrit l'environnement "
        "d'empoussièrement de la zone, pas un point précis."
    ),
    "sarah3_monthly": (
        "Données issues du jeu satellitaire SARAH-3 du CM SAF (EUMETSAT), construit sur les "
        "satellites géostationnaires Meteosat, utilisé comme source de recoupement pour "
        "l'irradiation."
    ),
}

_CAVEAT_OMM = (
    " La fenêtre 1991-2020 correspond à la normale climatologique de l'Organisation "
    "météorologique mondiale. L'homogénéité de la période longue repose sur "
    "l'harmonisation interne du producteur, documentée comme limite connue."
)

_KUMA_CALCULS: dict[str, str] = {
    "hep": (
        "Heures équivalentes plein soleil, calculées par Kuma à partir de l'irradiation "
        "globale (GHI) de la même localité : l'énergie reçue sur la période, ramenée à un "
        "éclairement de référence de 1 kW/m²."
    ),
    "productible_specifique_theorique": (
        "Productible spécifique théorique calculé par Kuma à partir des heures "
        "équivalentes plein soleil, avec un ratio de performance forfaitaire de 0,8 : un "
        "ordre de grandeur amont, pas une étude de production. Les valeurs sont des "
        "totaux sur la période de la mesure (mensuelle ou annuelle)."
    ),
    "kt": (
        "Indice de clarté calculé par Kuma : rapport entre le rayonnement reçu au sol et le "
        "rayonnement hors atmosphère, à partir du GHI et de la géométrie solaire."
    ),
    "fraction_diffuse": (
        "Part diffuse du rayonnement estimée par Kuma par corrélation à partir de l'indice "
        "de clarté de la même localité."
    ),
    "humidex": (
        "Indice de confort thermique combinant température et humidité, calculé par Kuma "
        "à partir des séries de température (T2M) et d'humidité relative (RH2M)."
    ),
    "variabilite_journaliere": (
        "Variabilité de la ressource calculée par Kuma : dispersion de l'irradiation "
        "journalière au sein de chaque mois, à partir de la série journalière GHI."
    ),
    "rang_referentiel_temporel": (
        "Position relative de chaque période dans la distribution de référence de la "
        "localité, calculée par Kuma à partir de la série GHI : un repère sans unité, "
        "pas une mesure physique."
    ),
    "rang_referentiel_spatial": (
        "Position relative de la localité parmi les six villes pilotes du programme "
        "initial, calculée par Kuma à partir des séries GHI : un repère sans unité, pas "
        "une mesure physique."
    ),
    "ecart_relatif_referentiel": (
        "Écart relatif entre la source principale et la référence de recoupement "
        "(SARAH-3), calculé par Kuma mois par mois : une mesure du désaccord entre "
        "sources, pas de la qualité du site."
    ),
    "ecart_relatif_dni_cams": (
        "Écart relatif entre la source principale et CAMS Radiation pour l'irradiation "
        "directe, calculé par Kuma mois par mois : une mesure du désaccord entre sources, "
        "pas de la qualité du site."
    ),
}

_CONF_KUMA = (
    " Niveau de confiance B, hérité des intrants satellitaires ; la méthode et la formule "
    "sont versionnées dans le dépôt public du moteur."
)


def _periode_lisible(debut: str, fin: str | None) -> str:
    a = debut[:4]
    b = fin[:4] if fin else ""
    if not b:
        return f"depuis {a}"
    if a == b:
        return f"année {a}"
    return f"{a}-{b}"


def _phrase_coeur(
    libelle_grandeur: str, granularite: str | None, localite: str, periode: str
) -> str:
    gran = _GRAN_LISIBLE.get(granularite or "", "")
    espace = f" {gran}" if gran else ""
    return f"Série {libelle_grandeur}{espace} pour {localite}, {periode}."


def _note_publique(
    source_code: str,
    grandeur_code: str,
    libelle_grandeur: str,
    granularite: str | None,
    localite: str,
    periode_debut: str,
    periode_fin: str | None,
) -> str:
    periode = _periode_lisible(periode_debut, periode_fin)
    coeur = _phrase_coeur(libelle_grandeur, granularite, localite, periode)

    if source_code == "esmap_wapp":
        instrument = (
            "pyrhéliomètre thermopile Kipp & Zonen CHP1"
            if grandeur_code == "dni"
            else "pyranomètre thermopile"
        )
        return (
            f"{coeur} Mesures de la station au sol du programme ESMAP/WAPP (Banque "
            f"mondiale) installée au poste électrique de Kankan : {instrument}, pas natif "
            "d'une minute agrégé au pas horaire. Niveau de confiance A : mesure de "
            "terrain. Un contrôle qualité signale les valeurs suspectes sans les supprimer."
        )

    if source_code == "kuma_calculs":
        corps = _KUMA_CALCULS.get(grandeur_code)
        if corps is None:
            return f"{coeur} Série calculée par Kuma.{_CONF_KUMA}"
        return f"{coeur} {corps}{_CONF_KUMA}"

    corps = _SOURCES_CORPS.get(source_code)
    if corps is None:
        return f"{coeur} {_CONF_B_MODELE}"

    if source_code == "nasa_power" and granularite == "horaire":
        return (
            f"{coeur} {_SOURCES_CORPS['nasa_power']} Série horaire du programme pilote : un "
            "contrôle qualité signale les valeurs suspectes sans les supprimer. "
            f"{_CONF_B_MODELE}"
        )

    note = f"{coeur} {corps} {_CONF_B_MODELE}"
    if (
        source_code == "nasa_power"
        and granularite == "mensuel"
        and periode_debut[:4] == "1991"
        and periode_fin is not None
        and periode_fin[:4] == "2020"
    ):
        note += _CAVEAT_OMM
    return note


def upgrade() -> None:
    op.add_column(
        "series_metadonnees",
        sa.Column(
            "note_publique",
            sa.Text(),
            nullable=True,
            comment=(
                "Passeport public de la série (servi par l'API sous l'alias "
                "notes_fr, affiché sur les fiches du site). Auto-portant : "
                "aucune référence de chantier interne. Toute nouvelle série "
                "doit le renseigner à l'insertion ; commentaire_editorial "
                "reste le journal interne, assaini à l'export d'édition."
            ),
        ),
    )

    bind = op.get_bind()
    lignes = bind.execute(
        sa.text(
            """
            SELECT sm.code,
                   s.code   AS source_code,
                   sm.grandeur_code,
                   gr.libelle AS libelle_grandeur,
                   sm.granularite,
                   l.nom    AS localite_nom,
                   sm.periode_debut::text AS periode_debut,
                   sm.periode_fin::text   AS periode_fin
            FROM series_metadonnees sm
            JOIN sources s ON s.id = sm.source_id
            JOIN grandeurs_referentiel gr ON gr.code = sm.grandeur_code
            JOIN localites l ON l.id = sm.localite_id
            """
        )
    ).mappings()

    parametres = [
        {
            "code": ligne["code"],
            "note": _note_publique(
                ligne["source_code"],
                ligne["grandeur_code"],
                ligne["libelle_grandeur"],
                ligne["granularite"],
                ligne["localite_nom"],
                ligne["periode_debut"],
                ligne["periode_fin"],
            ),
        }
        for ligne in lignes
    ]
    if parametres:
        bind.execute(
            sa.text("UPDATE series_metadonnees SET note_publique = :note WHERE code = :code"),
            parametres,
        )


def downgrade() -> None:
    op.drop_column("series_metadonnees", "note_publique")

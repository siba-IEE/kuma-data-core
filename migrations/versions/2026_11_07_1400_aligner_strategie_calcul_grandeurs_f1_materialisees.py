"""aligner_strategie_calcul_grandeurs_f1_materialisees

Revision ID: 126
Revises: 125
Create Date: 2026-11-07 14:00:00.000000+00:00

Migration de coherence du referentiel, sans DDL ni donnee mesuree.

Cinq grandeurs F1 etaient declarees ``strategie_calcul = 'calculee_volee'``
alors que leurs valeurs sont calculees par Kuma une fois, puis persistees dans
``grandeurs_metier`` (lues telles quelles par l'API, jamais recalculees a la
consultation) : ``degenerescence_pixel``, ``ecart_relatif_dni_cams``,
``ecart_relatif_referentiel``, ``rang_referentiel_spatial``,
``rang_referentiel_temporel``. Le commentaire de la colonne
``strategie_calcul`` fait foi (« stockee : valeur persistee dans
grandeurs_metier ») : ces cinq grandeurs passent en ``stockee``.

Leurs ``description`` (publiques : ``grandeurs_referentiel`` est publiee telle
quelle dans l'edition) annoncaient un calcul a la volee, portaient du
vocabulaire de chantier et, pour deux d'entre elles, une couverture perimee ;
celle de ``ecart_relatif_referentiel`` decrivait un ecart a la moyenne des sites
Kuma, alors que le calcul est l'ecart NASA POWER / PVGIS-SARAH-3
(``services/grandeurs/referentiels.py``). Nouveaux textes : ce que le calcul
fait reellement (sources comparees, formule, sens de la valeur), sans
couverture chiffree (portee par les series), sans jargon, accents francais.

``rang_referentiel`` (desactivee, sans ligne) et les libelles ne sont pas
touches.

Gardes : l'UPDATE de strategie exige que les cinq lignes soient dans l'etat
de depart (exactement 5 lignes mises a jour) ; chaque UPDATE de description
exige le texte de depart exact (exactement 1 ligne). Le downgrade restaure
l'etat d'origine a l'identique, garde de la meme facon. Trigger d'audit :
``kuma_log_audit()`` journalise chaque UPDATE ; ``modifie_le`` non touche
(precedent migrations 100 et 125). Aucun reseau.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "126"
down_revision: str | Sequence[str] | None = "125"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_STRATEGIE_ANCIENNE = "calculee_volee"
_STRATEGIE_NOUVELLE = "stockee"

# code -> (description de depart exacte, nouvelle description)
_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "degenerescence_pixel": (
        (
            "Indicateur d'honnetete structurelle de l'atlas : pour une (localite, "
            "source, parametre), nombre d'autres points partageant la meme cellule "
            "source (0 = point reellement resolu). Detection empirique par identite "
            "de series climato mensuelles sur grille fixe (NASA radiation CERES "
            "1deg, meteo MERRA 0.5deg). Services interpoles (SARAH-3 / CAMS 5 km) : "
            "compte 0 + caveat de resolution. F1 calculee_volee, materialisee "
            "statique, confiance B (A reservee aux mesures terrain ; exactitude dite "
            "par caveat, pas par une remontee en A)."
        ),
        (
            "Indique si une localité partage la cellule de grille d'une source avec "
            "d'autres localités. Pour chaque localité et chaque couple (source, "
            "paramètre) examiné, la valeur est le nombre d'autres localités dont la "
            "série climatologique mensuelle est strictement identique : elles lisent "
            "la même cellule de la grille et leurs valeurs ne sont pas des mesures "
            "indépendantes. 0 signifie qu'aucune autre localité ne partage la "
            "cellule. Sont examinées les grilles fixes de NASA POWER : rayonnement "
            "(GHI, DNI, DHI, indice de clarté, albédo) sur une grille de 1°, "
            "météorologie (température et humidité à 2 m, vent à 2 m et à 10 m) sur "
            "une grille d'environ 0,5°. PVGIS-SARAH-3 (GHI) et CAMS Radiation (DNI) "
            "sont interpolés au point de chaque localité : leurs valeurs diffèrent "
            "d'une localité à l'autre et l'indicateur vaut 0, sans garantir une "
            "précision plus fine que la résolution de ces services. Niveau de "
            "confiance B : le constat est exact, mais le niveau A est réservé aux "
            "mesures au sol."
        ),
    ),
    "ecart_relatif_dni_cams": (
        (
            "Ecart relatif inter-source du DNI entre NASA POWER (primaire) et CAMS "
            "Radiation (reference d'ecart aerosol-corrigee), formule (nasa - "
            "cams)/cams x 100, en pourcent signe. Calculee a la volee, materialisee "
            "dans grandeurs_metier par (annee, mois) sur la fenetre commune "
            "2004-2020 (6 villes pilotes). Famille F1."
        ),
        (
            "Écart relatif mensuel entre deux estimations satellitaires de "
            "l'irradiation normale directe (DNI) : NASA POWER et CAMS Radiation "
            "(Copernicus). Pour chaque localité et chaque mois couvert par les deux "
            "sources, Kuma calcule (NASA POWER - CAMS) / CAMS × 100 à partir des "
            "moyennes mensuelles de DNI, en pourcentage signé : une valeur négative "
            "signifie que NASA POWER donne moins de DNI que CAMS. C'est une mesure "
            "du désaccord entre sources, utile pour juger l'incertitude locale, et "
            "non une correction ni une mesure de la ressource. Niveau de confiance "
            "B : écart entre deux produits satellitaires, pas une mesure au sol."
        ),
    ),
    "ecart_relatif_referentiel": (
        (
            "Écart relatif au référentiel Kuma. Différence entre la valeur d'une "
            "série et la moyenne de cette grandeur calculée sur l'ensemble des sites "
            "du référentiel Kuma, exprimée en pourcent. Calculée à la volée, "
            "dépendante du périmètre courant."
        ),
        (
            "Écart relatif mensuel de l'irradiation globale horizontale (GHI) entre "
            "NASA POWER, source principale de Kuma, et PVGIS-SARAH-3, référence de "
            "recoupement. Pour chaque localité et chaque mois couvert par les deux "
            "sources, Kuma calcule (NASA POWER - SARAH-3) / SARAH-3 × 100, où NASA "
            "POWER est la moyenne mensuelle de ses valeurs journalières, en "
            "pourcentage signé : une valeur négative signifie que NASA POWER donne "
            "moins de GHI que SARAH-3. C'est une mesure du désaccord entre sources, "
            "utile pour juger l'incertitude locale, et non une mesure de la qualité "
            "du site. Niveau de confiance B : écart entre deux produits "
            "satellitaires, pas une mesure au sol."
        ),
    ),
    "rang_referentiel_spatial": (
        (
            "Rang spatial dans le perimetre Kuma (rang ordinal 1-6 parmi les 6 "
            "villes pilotes guineennes pour le meme mois). Calcule a la volee a "
            "partir des mesures NASA POWER 2021-2025 agregees mensuellement. "
            "Decomposition de rang_referentiel singulier seede en 1-1C (D-39 fermee "
            "dans le meme cycle 1-7b). Cf. note methodologique amont PR #53 et spec "
            "1-7 PR #54."
        ),
        (
            "Rang d'une ville parmi les six villes pilotes (Kaloum à Conakry, "
            "Kankan, Kindia, Labé, Mamou, Nzérékoré) pour un même mois, de 1 à 6. "
            "Kuma classe les six villes par ordre croissant de la moyenne mensuelle "
            "de l'irradiation globale horizontale (GHI) NASA POWER, calculée à "
            "partir des valeurs journalières : 1 = irradiation la plus faible du "
            "mois, 6 = la plus forte. Un mois n'est classé que si les six villes ont "
            "une valeur. Kindia et Mamou lisent la même cellule de la grille NASA "
            "POWER et ont des valeurs identiques : leur ordre relatif est "
            "arbitraire. Repère sans unité, pas une mesure physique. Niveau de "
            "confiance B : classement sur six villes seulement."
        ),
    ),
    "rang_referentiel_temporel": (
        (
            "Rang temporel dans la climatologie de reference (percentile calcule par "
            "mois calendrier sur la distribution NASA POWER 1991-2020 par localite). "
            "Formule type 7 numpy/R : p = (rang - 1) / (n - 1) x 100, capping [0, "
            "100]. Plage de calcul phase 1 : 2021-2025 sur les 6 villes pilotes "
            "guineennes. Decomposition de rang_referentiel singulier seede en 1-1C "
            "(D-39 fermee dans le meme cycle 1-7b). Cf. note methodologique amont PR "
            "#53 et spec 1-7 PR #54."
        ),
        (
            "Position d'un mois dans la climatologie de sa localité, en percentile "
            "de 0 à 100. Kuma compare la moyenne mensuelle de l'irradiation globale "
            "horizontale (GHI) NASA POWER, calculée à partir des valeurs "
            "journalières, aux valeurs NASA POWER du même mois calendaire sur "
            "1991-2020, une par année : percentile = (r - 1) / (n - 1) × 100, borné "
            "entre 0 et 100, où n est le nombre d'années de référence et r le nombre "
            "de valeurs de référence inférieures augmenté de (e + 1) / 2, e étant le "
            "nombre de valeurs égales. 0 : mois plus faible que toutes les années de "
            "référence ; 100 : plus fort que toutes ; autour de 50 : proche de la "
            "médiane. Comparaison interne à NASA POWER, sans seconde source. Repère "
            "sans unité, pas une mesure physique. Niveau de confiance B."
        ),
    ),
}

_CODES: tuple[str, ...] = tuple(sorted(_DESCRIPTIONS))


def _update_strategie(*, attendue: str, nouvelle: str) -> None:
    """UPDATE garde de ``strategie_calcul`` des cinq grandeurs : 5 lignes exactement."""
    resultat = op.get_bind().execute(
        sa.text(
            """
            UPDATE grandeurs_referentiel
            SET strategie_calcul = :nouvelle
            WHERE code IN :codes AND strategie_calcul = :attendue
            """
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"nouvelle": nouvelle, "attendue": attendue, "codes": list(_CODES)},
    )
    if resultat.rowcount != len(_CODES):
        raise RuntimeError(
            f"Migration 126 : {len(_CODES)} grandeurs attendues en strategie_calcul "
            f"{attendue!r} ({', '.join(_CODES)}), {resultat.rowcount} ligne(s) mise(s) "
            "a jour. Abandon sans ecriture partielle."
        )


def _update_description(*, code: str, attendue: str, nouvelle: str) -> None:
    """UPDATE garde de la description d'une grandeur : texte de depart exact, 1 ligne."""
    resultat = op.get_bind().execute(
        sa.text(
            """
            UPDATE grandeurs_referentiel
            SET description = :nouvelle
            WHERE code = :code AND description = :attendue
            """
        ),
        {"code": code, "nouvelle": nouvelle, "attendue": attendue},
    )
    if resultat.rowcount != 1:
        raise RuntimeError(
            f"Migration 126 : description de {code!r} attendue dans son etat de depart "
            f"exact, {resultat.rowcount} ligne(s) mise(s) a jour au lieu de 1. Abandon "
            "sans ecriture partielle."
        )


def upgrade() -> None:
    _update_strategie(attendue=_STRATEGIE_ANCIENNE, nouvelle=_STRATEGIE_NOUVELLE)
    for code in _CODES:
        ancienne, nouvelle = _DESCRIPTIONS[code]
        _update_description(code=code, attendue=ancienne, nouvelle=nouvelle)


def downgrade() -> None:
    for code in _CODES:
        ancienne, nouvelle = _DESCRIPTIONS[code]
        _update_description(code=code, attendue=nouvelle, nouvelle=ancienne)
    _update_strategie(attendue=_STRATEGIE_NOUVELLE, nouvelle=_STRATEGIE_ANCIENNE)

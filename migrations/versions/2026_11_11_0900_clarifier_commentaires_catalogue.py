"""clarifier_commentaires_catalogue

Revision ID: 122
Revises: 121
Create Date: 2026-11-11 09:00:00

Les commentaires du catalogue (tables, colonnes, vues, fonctions) partent avec
l'édition publique. Vingt-quatre d'entre eux renvoyaient à l'histoire du projet
ou énonçaient un fait qui n'est plus vrai (décompte figé, exemple de code
inexistant, document absent du dépôt, règle d'unicité incomplète). Chacun est
réécrit d'après le schéma et les données ; un renvoi à un document devient son
URL publique.

Garde : le texte de départ de chaque commentaire doit être exactement celui
attendu, sinon rien n'est écrit. Le downgrade rend les anciens textes à
l'identique. Les ``comment=`` des modèles portent les mêmes textes.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "122"
down_revision: str | Sequence[str] | None = "121"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (genre, objet, colonne, ancien texte, nouveau texte) ; colonne vide pour l'objet lui-même.
COMMENTAIRES: list[tuple[str, str, str, str, str]] = [
    (
        "fonction",
        "valider_hierarchie_localites",
        "",
        (
            "Valide la matrice parent-enfant de localites (BEFORE INSERT OR UPDATE). Cloture "
            "datee de la dette du trigger 007 (annonce des migration 003, jamais bati). Portee "
            "minimale : matrice + continent-racine ; pas de detection de cycles."
        ),
        (
            "Valide la hiérarchie des localités avant insertion ou mise à jour (trigger BEFORE "
            "INSERT OR UPDATE sur localites) : un continent n'a pas de parent, tout autre type en"
            " exige un, et le type du parent doit être admis pour le type de l'enfant. Ne détecte"
            " pas les cycles."
        ),
    ),
    (
        "table",
        "calage_couverture",
        "",
        (
            "Domaine de couverture des referentiels de calage : localites qualifiees pour le "
            "transport, avec justification. Pilote la couverture geographique des consommateurs "
            "(ADR-0004, couverture progressive)."
        ),
        (
            "Domaine de couverture des référentiels de calage : localités qualifiées pour le "
            "transport d'un calage, avec la justification de chacune. Cette liste détermine où un"
            " calage s'applique ; les clients de l'API la lisent au lieu de la coder. Voir "
            "https://github.com/siba-IEE/kuma-data-core/blob/main/docs/decisions/0004-exposition-etudes-au-point.md"
        ),
    ),
    (
        "table",
        "grandeurs_metier",
        "",
        (
            "Grandeurs metier calculees par Kuma a partir des mesures brutes. Premiere table de "
            "fabrication editoriale phase 1 (etape 1-5). F1 stockee, agregations annuelles et "
            "mensuelles. Versioning temporel par (valide_du, valide_au) + EXCLUDE BTree-GiST sur "
            "identite metier etendue avec version_formule. Statut editorial et niveau de "
            "confiance derive/override par couche service editoriale."
        ),
        (
            "Grandeurs métier calculées par Kuma à partir des mesures : valeurs annuelles, "
            "mensuelles ou statiques (periode_type). Versionnement temporel par (valide_du, "
            "valide_au) et contrainte EXCLUDE BTree-GiST sur l'identité métier étendue à "
            "version_formule. Statut éditorial et niveau de confiance dérivé ou forcé par la "
            "couche de service éditoriale."
        ),
    ),
    (
        "table",
        "grandeurs_metier",
        "niveau_confiance_derive",
        (
            "Niveau de confiance derive automatiquement par la couche service a partir des regles"
            " R1-R4 (cf. spec mecaniques-transverses-phase-1 sec. 6.4). A = haute, B = moyenne, C"
            " = basse. Recalcule a chaque modification de methode_collecte ou source_id de la "
            "serie."
        ),
        (
            "Niveau de confiance dérivé par la couche de service selon la méthode de collecte de "
            "la série, la fiabilité de sa source et, pour une valeur calculée, le niveau de ses "
            "entrées. A = haute, B = moyenne, C = basse. Règles de dérivation : voir "
            "https://github.com/siba-IEE/kuma-data-core/blob/main/docs/contribution/confiance-et-statuts.md"
        ),
    ),
    (
        "table",
        "grandeurs_metier",
        "periode_type",
        (
            "Granularite temporelle de l'agregation : annuel (1 ligne par (localite, grandeur, "
            "annee, version_formule), mois NULL) ou mensuel (12 lignes par annee, mois 1-12). Cf."
            " cadrage phase 1 Q2 et Q6."
        ),
        (
            "Granularité temporelle de la valeur : annuel (une valeur par année, mois NULL), "
            "mensuel (une valeur par mois, mois de 1 à 12) ou statique (une valeur pour toute la "
            "période annee_debut à annee_fin, mois NULL)."
        ),
    ),
    (
        "table",
        "grandeurs_metier",
        "version_formule",
        (
            "Version de la formule de calcul en vigueur au moment de l'insertion. Lien implicite "
            "avec grandeurs_referentiel.version_formule_actuelle pour la grandeur concernee. "
            "Incremente lors de toute revision methodologique. Inclus dans l'EXCLUDE pour "
            "permettre la coexistence v1/v2 apres upgrade (spec 1-5 sec. 3.2, cadrage Q7)."
        ),
        (
            "Version de la formule de calcul en vigueur à l'insertion, liée à "
            "grandeurs_referentiel.version_formule_actuelle de la grandeur et incrémentée à "
            "chaque révision méthodologique. Incluse dans la contrainte EXCLUDE pour que deux "
            "versions coexistent après une révision."
        ),
    ),
    (
        "table",
        "grandeurs_referentiel",
        "",
        (
            "Referentiel des grandeurs Kuma. 15 grandeurs traduites (1-1C) + 5 grandeurs brutes "
            "ingerees (1-2b) = 20 entrees post-1-2b. Le lieu de stockage physique d'une F1 "
            "stockee est determine par series_metadonnees.methode_collecte (cadrage Q7 v1.3)."
        ),
        (
            "Référentiel des grandeurs Kuma : grandeurs brutes ingérées et grandeurs calculées "
            "par Kuma. La table qui porte les valeurs d'une série dépend de sa source et de sa "
            "granularité (series_metadonnees.granularite) : grandeurs_metier pour les séries de "
            "la source kuma_calculs, sinon mesures_ressource (journalier), "
            "mesures_ressource_mensuelles (mensuel) ou mesures_ressource_horaires (horaire)."
        ),
    ),
    (
        "table",
        "grandeurs_referentiel",
        "code",
        (
            "Cle naturelle metier (ASCII pur, snake_case, citee par les FK aval). Cf. "
            "01-naming.md section Codes metier des referentiels."
        ),
        (
            "Clé naturelle métier (ASCII pur, snake_case, citée par les clés étrangères des "
            "tables aval). Convention : section « Codes métier des référentiels » de "
            "https://github.com/siba-IEE/kuma-data-core/blob/main/docs/conventions/01-naming.md"
        ),
    ),
    (
        "table",
        "localites",
        "type_localite",
        (
            "7 valeurs : continent, region_supranationale, pays, region_administrative, "
            "prefecture, commune, site. prefecture ajoutee en densification prefectorale Etape 1 "
            "(niveau pays > region > prefecture > commune)."
        ),
        (
            "7 valeurs : continent, region_supranationale, pays, region_administrative, "
            "prefecture, commune, site. En Guinée : pays, région administrative, préfecture, "
            "commune ; les communes de Conakry sont rattachées directement à leur région "
            "administrative."
        ),
    ),
    (
        "table",
        "mesures_ressource",
        "",
        (
            "Mesures journalieres ingerees depuis sources externes. Premiere table metier "
            "operationnelle phase 1. Versioning temporel par (valide_du, valide_au) + EXCLUDE "
            "BTree-GiST sur identite metier (serie_id, instant_mesure). Statut editorial et "
            "niveau de confiance derive/override par couche service editoriale."
        ),
        (
            "Mesures journalières ingérées depuis les sources externes. Versionnement temporel "
            "par (valide_du, valide_au) et contrainte EXCLUDE BTree-GiST sur l'identité métier "
            "(serie_id, instant_mesure). Statut éditorial et niveau de confiance dérivé ou forcé "
            "par la couche de service éditoriale."
        ),
    ),
    (
        "table",
        "mesures_ressource",
        "niveau_confiance_derive",
        (
            "Niveau de confiance derive automatiquement par la couche service a partir des regles"
            " R1-R4 (cf. spec mecaniques-transverses-phase-1 sec. 6.4). A = haute, B = moyenne, C"
            " = basse. Recalcule a chaque modification de methode_collecte ou source_id de la "
            "serie."
        ),
        (
            "Niveau de confiance dérivé par la couche de service selon la méthode de collecte de "
            "la série et la fiabilité de sa source. A = haute, B = moyenne, C = basse. Règles de "
            "dérivation : voir "
            "https://github.com/siba-IEE/kuma-data-core/blob/main/docs/contribution/confiance-et-statuts.md"
        ),
    ),
    (
        "table",
        "mesures_ressource_horaires",
        "",
        (
            "Mesures horaires ingerees depuis sources externes (NASA POWER, Vague 3). Pendant "
            "horaire de mesures_ressource (journalier) et mesures_ressource_mensuelles (mensuel)."
            " instant_mesure en TIMESTAMPTZ (UTC) pour le controle qualite horaire (position "
            "solaire sans ambiguite de fuseau). Versioning temporel par (valide_du, valide_au) + "
            "EXCLUDE BTree-GiST sur identite metier (serie_id, instant_mesure). Statut editorial "
            "et niveau de confiance derive/override par couche service editoriale."
        ),
        (
            "Mesures horaires ingérées depuis les sources externes : modèle satellitaire NASA "
            "POWER et mesures au sol de la campagne ESMAP/WAPP. Pendant horaire de "
            "mesures_ressource (journalier) et de mesures_ressource_mensuelles (mensuel). "
            "instant_mesure en TIMESTAMPTZ (UTC) pour le contrôle qualité horaire (position "
            "solaire sans ambiguïté de fuseau). Versionnement temporel par (valide_du, valide_au)"
            " et contrainte EXCLUDE BTree-GiST sur l'identité métier (serie_id, instant_mesure). "
            "Statut éditorial et niveau de confiance dérivé ou forcé par la couche de service "
            "éditoriale."
        ),
    ),
    (
        "table",
        "mesures_ressource_mensuelles",
        "",
        (
            "Mesures mensuelles ingerees depuis sources externes (SARAH-3 ICDR + NASA POWER "
            "1991-2020, etape 1-7a). Pendant mensuel de mesures_ressource (journalier strict, "
            "cadrage Q2 phase 1). Versioning temporel par (valide_du, valide_au) + EXCLUDE "
            "BTree-GiST sur identite metier (serie_id, annee, mois). Statut editorial et niveau "
            "de confiance derive/override par couche service editoriale."
        ),
        (
            "Mesures mensuelles ingérées depuis les sources externes (NASA POWER, SARAH-3 via "
            "PVGIS, CAMS Radiation, ERA5-Land). Pendant mensuel de mesures_ressource "
            "(journalier). Versionnement temporel par (valide_du, valide_au) et contrainte "
            "EXCLUDE BTree-GiST sur l'identité métier (serie_id, annee, mois). Statut éditorial "
            "et niveau de confiance dérivé ou forcé par la couche de service éditoriale."
        ),
    ),
    (
        "table",
        "referentiels_calage",
        "",
        (
            "Referentiel de calage satellite/sol : biais saisonniers mesures aux stations de "
            "reference, publies avec provenance et portee de transport (ADR-0004)."
        ),
        (
            "Référentiel de calage satellite/sol : biais saisonniers mesurés aux stations de "
            "référence, publiés avec leur provenance et la portée de leur transport. Voir "
            "https://github.com/siba-IEE/kuma-data-core/blob/main/docs/decisions/0004-exposition-etudes-au-point.md"
        ),
    ),
    (
        "table",
        "series_metadonnees",
        "",
        (
            "Referentiel editorial des series de mesures Kuma. Une serie = un triplet (localite, "
            "grandeur, source) avec ses metadonnees editoriales communes."
        ),
        (
            "Référentiel éditorial des séries de mesures Kuma. Une série est identifiée par sa "
            "localité, sa grandeur, sa source, sa période et sa granularité ; elle porte les "
            "métadonnées éditoriales communes à ses mesures."
        ),
    ),
    (
        "table",
        "series_metadonnees",
        "code",
        (
            "Cle naturelle metier (ASCII pur, snake_case). Convention : "
            "<localite>_<grandeur>_<source>[_<periode>] ex. gin_conakry_hep_nasa_power_2010_2024."
        ),
        (
            "Clé naturelle métier (ASCII pur, snake_case). Convention : "
            "<localite>_<grandeur>_<source>[_<granularite>]_<periode>, ex. "
            "gin_conakry_hep_kuma_calculs_2021_2025. Voir "
            "https://github.com/siba-IEE/kuma-data-core/blob/main/docs/conventions/01-naming.md"
        ),
    ),
    (
        "table",
        "series_metadonnees",
        "granularite",
        (
            "Discriminant de granularite temporelle pour le routage table-cible "
            "(journalier/mensuel/horaire). NULL pour les series kuma_calculs (routees par source "
            "vers grandeurs_metier ; temporalite portee par grandeurs_metier.periode_type). "
            "Resout D-36 (Vague 3 lot 1)."
        ),
        (
            "Discriminant de granularité temporelle, qui désigne la table des mesures de la série"
            " : journalier (mesures_ressource), mensuel (mesures_ressource_mensuelles) ou horaire"
            " (mesures_ressource_horaires). NULL pour les séries de la source kuma_calculs, dont "
            "les valeurs sont dans grandeurs_metier et la temporalité dans "
            "grandeurs_metier.periode_type."
        ),
    ),
    (
        "table",
        "series_metadonnees",
        "methode_collecte",
        (
            "Methode dominante de collecte de la serie. Liste indicative des 6 valeurs en spec "
            "mecaniques-transverses sec. 6.4. CHECK formel pose en 1-2b."
        ),
        (
            "Méthode dominante de collecte de la série : mesure_directe, modele_satellitaire, "
            "interpolation_geographique, extrapolation_temporelle, calcul_derive ou "
            "expertise_humaine (contrainte CHECK, NULL admis). Elle entre dans le niveau de "
            "confiance dérivé : voir "
            "https://github.com/siba-IEE/kuma-data-core/blob/main/docs/contribution/confiance-et-statuts.md"
        ),
    ),
    (
        "table",
        "sources",
        "code",
        (
            "Identifiant court unique. Convention : <organisme>_<theme>[_<annee>]. Ex: "
            "irena_lcoe_2024, bcrg_rapport_annuel_2023, iso_50001_2018. Pour les publications "
            "recurrentes, inclure l'annee."
        ),
        (
            "Identifiant court unique. Convention : <organisme>_<theme>[_<annee>], ex. "
            "ecmwf_era5_land, cams_radiation, wmo_8_2024. Pour les publications récurrentes ou "
            "éditées, inclure l'année."
        ),
    ),
    (
        "table",
        "sources",
        "fiabilite",
        (
            "Qualification editoriale Kuma (3 niveaux). Voir docs/architecture/04-api.md pour le "
            "mapping editorial complet."
        ),
        (
            "Qualification éditoriale Kuma de la source : haute, moyenne ou faible. Elle entre "
            "dans le niveau de confiance dérivé : voir "
            "https://github.com/siba-IEE/kuma-data-core/blob/main/docs/contribution/confiance-et-statuts.md"
        ),
    ),
    (
        "table",
        "sources",
        "type_source",
        (
            "11 valeurs autorisees : rapport, article_scientifique, texte_legal, communique, "
            "page_web, base_donnees, livre, chapitre_livre, these, norme_technique (10 valeurs "
            "documentaires externes initiales, migration 004) + auteur_kuma (couche editoriale "
            "interne Kuma, introduite en 1-5D-i pour la source synthetique kuma_calculs)."
        ),
        (
            "11 valeurs autorisées : rapport, article_scientifique, texte_legal, communique, "
            "page_web, base_donnees, livre, chapitre_livre, these, norme_technique (sources "
            "documentaires externes) et auteur_kuma (couche éditoriale interne, source "
            "kuma_calculs)."
        ),
    ),
    (
        "table",
        "unites",
        "",
        (
            "Référentiel des unités de mesure de Kuma Data Core. 153 unités sur 30 grandeurs, "
            "validées contre 20+ organismes normatifs internationaux (BIPM, AIE, ONU, NIST, "
            "IUPAC, IEC, DIN, ISO, IPCC, IRENA, UNECE, etc.)."
        ),
        (
            "Référentiel des unités de mesure de Kuma Data Core, avec leur conversion vers le "
            "Système international et leurs références normatives (BIPM, AIE, ONU, NIST, IUPAC, "
            "IEC, DIN, ISO, IPCC, IRENA, UNECE, etc.)."
        ),
    ),
    (
        "vue",
        "v_grandeurs_metier_courantes",
        "",
        (
            "Vue projetant les lignes courantes de grandeurs_metier (valide_au IS NULL) en "
            "version de formule actuelle (version_formule = "
            "grandeurs_referentiel.version_formule_actuelle) et hors statut deprecie. Ajoute la "
            "colonne calculee niveau_effectif = COALESCE(niveau_confiance_override, "
            "niveau_confiance_derive). Equivalent SQL de l'hybrid_property "
            "GrandeurMetier.niveau_effectif. Cf. spec 1-5 sec. 4."
        ),
        (
            "Vue des lignes courantes de grandeurs_metier (valide_au IS NULL), dans la version de"
            " formule actuelle (version_formule = grandeurs_referentiel.version_formule_actuelle)"
            " et hors statut deprecie. Ajoute la colonne calculée niveau_effectif = "
            "COALESCE(niveau_confiance_override, niveau_confiance_derive), équivalent SQL de la "
            "propriété GrandeurMetier.niveau_effectif."
        ),
    ),
    (
        "vue",
        "v_mesures_avec_niveau_effectif",
        "",
        (
            "Vue projetant mesures_ressource + colonne calculee niveau_effectif = "
            "COALESCE(niveau_confiance_override, niveau_confiance_derive). Equivalent SQL de "
            "l'hybrid_property MesureRessource.niveau_effectif. Permet d'eviter le scan "
            "applicatif Python pour les requetes lecture massives. Cf. spec 1-2b sec. 3.4."
        ),
        (
            "Vue de mesures_ressource, versions closes comprises, avec la colonne calculée "
            "niveau_effectif = COALESCE(niveau_confiance_override, niveau_confiance_derive), "
            "équivalent SQL de la propriété MesureRessource.niveau_effectif. Évite de calculer le"
            " niveau côté application dans les lectures massives."
        ),
    ),
]


def _lire(bind: sa.Connection, genre: str, objet: str, colonne: str) -> str | None:
    """Commentaire actuel de l'objet dans le catalogue."""
    if genre == "fonction":
        return bind.execute(
            sa.text("SELECT obj_description(CAST(:f AS regprocedure), 'pg_proc')"),
            {"f": f"public.{objet}()"},
        ).scalar_one_or_none()
    if colonne:
        return bind.execute(
            sa.text(
                "SELECT col_description(attrelid, attnum) FROM pg_attribute "
                "WHERE attrelid = CAST(:t AS regclass) AND attname = :c"
            ),
            {"t": f"public.{objet}", "c": colonne},
        ).scalar_one_or_none()
    return bind.execute(
        sa.text("SELECT obj_description(CAST(:t AS regclass), 'pg_class')"),
        {"t": f"public.{objet}"},
    ).scalar_one_or_none()


def _ecarts(bind: sa.Connection, attendus: list[tuple[str, str, str, str]]) -> list[str]:
    """Objets dont le commentaire actuel n'est pas le texte attendu."""
    return [
        f"{objet}.{colonne}" if colonne else objet
        for genre, objet, colonne, texte in attendus
        if _lire(bind, genre, objet, colonne) != texte
    ]


def _appliquer(changements: list[tuple[str, str, str, str, str]]) -> None:
    """Passe chaque commentaire de son texte de départ à son texte cible, ou n'écrit rien."""
    bind = op.get_bind()
    modifies = _ecarts(bind, [(g, o, c, depart) for g, o, c, depart, _ in changements])
    if modifies:
        raise RuntimeError(
            f"Migration 122 : commentaires absents ou déjà modifiés, rien n'est écrit : {modifies}"
        )
    for genre, objet, colonne, depart, cible in changements:
        if genre == "table" and colonne:
            op.alter_column(objet, colonne, comment=cible, existing_comment=depart)
        elif genre == "table":
            op.create_table_comment(objet, cible, existing_comment=depart)
        else:
            nom = f"VIEW public.{objet}" if genre == "vue" else f"FUNCTION public.{objet}()"
            litteral = bind.execute(sa.text("SELECT quote_literal(:t)"), {"t": cible}).scalar_one()
            # COMMENT ON n'accepte pas de paramètre lié. no_parameters vaut pour cette
            # seule instruction et évite que le pilote lise un « % » comme un marqueur.
            bind.exec_driver_sql(
                f"COMMENT ON {nom} IS {litteral}", execution_options={"no_parameters": True}
            )
    restants = _ecarts(bind, [(g, o, c, cible) for g, o, c, _, cible in changements])
    if restants:
        raise RuntimeError(f"Migration 122 : commentaires non écrits : {restants}")


def upgrade() -> None:
    _appliquer(COMMENTAIRES)


def downgrade() -> None:
    _appliquer([(g, o, c, nouveau, ancien) for g, o, c, ancien, nouveau in COMMENTAIRES])

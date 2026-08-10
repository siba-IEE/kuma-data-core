"""horaire_pilotes_extension_2025_et_grandeurs

Revision ID: 116
Revises: 115
Create Date: 2026-08-10 13:00:00

Chantier profondeur maximale par source, volet horaire - pilotes : aligne
les 6 villes pilotes sur le parc des 28 communes (revisions precedentes).

Trois gestes :

1. **Extension in-place 2024-2025** (patron migration 066) : les 36 series
   horaires pilotes ``*_nasa_power_2001_2023`` sont renommees
   ``*_nasa_power_2001_2025`` (periode_fin, libelle et note_publique
   ajustes), et les lignes 2024-2025 sont ingerees dans les MEMES series.
   L'extension in-place preserve la mono-serie par (ville, grandeur)
   exigee par le routeur horaire et les tests d'unicite ; une serie
   separee 2024-2025 les casserait.
2. **3 grandeurs nouvelles aux 6 pilotes** : vent_2m, vent_10m,
   precipitation en 2001-2025 (18 series), meme fenetre commune que le
   reste du parc horaire (contrainte du resolveur de compagnes F2).
3. **Ingestion gardee** par ``KUMA_SKIP_INGESTION_MASSE_HORAIRE`` (CI :
   renommage et seed appliques, 0 mesure ; rejeu manuel hors CI),
   appels groupes multi-parametres par annee, trigger d'audit suspendu
   (decision 2026-08-10, ``docs/architecture/03-audit.md``).

Compatibilite cle UNIQUE : depuis la migration 106 la cle d'identite des
series inclut la granularite - les series horaires renommees (2001-01-01 ->
2025-12-31) coexistent avec les series mensuelles longues de meme plage.

Exception Conakry : prefixe de serie ``gin_conakry`` pour la localite
``gin_conakry_kaloum`` (cf. 01-naming.md).

QC : la revision suivante requalifie les lignes nouvelles (l'application
est idempotente sur les lignes deja qualifiees).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.ingestion.nasa_power_hourly import ingerer_series_horaires_groupe

# revision identifiers, used by Alembic.
revision: str = "116"
down_revision: str | Sequence[str] | None = "115"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VARIABLE_ENV_SKIP_MASSE = "KUMA_SKIP_INGESTION_MASSE_HORAIRE"
_TABLE_MESURES = "mesures_ressource_horaires"
_TRIGGER_AUDIT = "trg_audit_mesures_ressource_horaires"
_SOURCE_CODE = "nasa_power"
_METHODE_COLLECTE = "modele_satellitaire"
_METHODE_COLLECTE_DOC = "https://power.larc.nasa.gov/docs/methodology/"
_URL_DOCUMENTATION = "https://power.larc.nasa.gov/"
_PERIODE_DEBUT = date(2001, 1, 1)
_PERIODE_FIN = date(2025, 12, 31)

# Localite -> prefixe de code de serie (exception Conakry).
_PILOTES: dict[str, str] = {
    "gin_conakry_kaloum": "gin_conakry",
    "gin_kankan": "gin_kankan",
    "gin_kindia": "gin_kindia",
    "gin_labe": "gin_labe",
    "gin_mamou": "gin_mamou",
    "gin_nzerekore": "gin_nzerekore",
}

_GRANDEURS_EXISTANTES: dict[str, str] = {
    "ghi": "ALLSKY_SFC_SW_DWN",
    "dni": "ALLSKY_SFC_SW_DNI",
    "dhi": "ALLSKY_SFC_SW_DIFF",
    "t2m": "T2M",
    "rh2m": "RH2M",
    "kt": "ALLSKY_KT",
}
_GRANDEURS_NOUVELLES: dict[str, str] = {
    "vent_2m": "WS2M",
    "vent_10m": "WS10M",
    "precipitation": "PRECTOTCORR",
}

_LIBELLES_NOUVELLES: dict[str, str] = {
    "vent_2m": "Vent 2m horaire",
    "vent_10m": "Vent 10m horaire",
    "precipitation": "Precipitations horaires",
}
_NOTE_DESCRIPTIFS_NOUVELLES: dict[str, str] = {
    "vent_2m": "Vitesse du vent a 2 metres du sol, en metres par seconde",
    "vent_10m": "Vitesse du vent a 10 metres du sol, en metres par seconde",
    "precipitation": "Precipitations totales corrigees, en millimetres par heure",
}
_NOTE_CORPS_NASA = (
    "Donnees ingerees depuis NASA POWER, le service de donnees solaires et "
    "meteorologiques de la NASA (rayonnement du modele satellitaire CERES SYN1deg, "
    "variables meteo de la reanalyse MERRA-2)."
)
_NOTE_CONF_B = (
    "Niveau de confiance B : donnee de modele, non validee par une mesure au sol a ce jour."
)
_NOTE_HORS_QC = (
    " Cette grandeur n'est pas couverte par les tests de plausibilite du controle "
    "qualite actuel, qui portent sur le rayonnement, la temperature et l'humidite."
)
_MENTION_EXTENSION = (
    " Fenetre etendue a fin 2025 et codes de serie repointes (extension in-place, "
    "meme serie, decision 2026-08-09)."
)

_COMMENTAIRE_NOUVELLES = (
    "Serie horaire {grandeur_upper} 2001-2025, {ville}, Guinee (ville pilote). "
    "Chantier profondeur maximale par source (decision 2026-08-09), volet horaire "
    "pilotes : alignement sur le parc 9 grandeurs des 28 communes. Fenetre commune "
    "(contrainte du resolveur de compagnes F2). Instants UTC. Ingestion live gardee "
    "par {flag}, appels groupes par annee. Statut brut a l'ingestion, qualification "
    "par la migration QC suivante. Trigger d'audit suspendu pendant le deversement "
    "(decision 2026-08-10, 03-audit.md). Confiance B (modele satellitaire)."
)


def _skip_ingestion_masse() -> bool:
    import os

    valeur = os.environ.get(_VARIABLE_ENV_SKIP_MASSE, "").strip().lower()
    return valeur in ("1", "true", "yes")


def _code_ancien(prefixe: str, grandeur: str) -> str:
    return f"{prefixe}_{grandeur}_nasa_power_2001_2023"


def _code_nouveau(prefixe: str, grandeur: str) -> str:
    return f"{prefixe}_{grandeur}_nasa_power_2001_2025"


def _note_publique_nouvelle(grandeur: str, ville: str) -> str:
    return (
        f"{_NOTE_DESCRIPTIFS_NOUVELLES[grandeur]}. Serie horaire 2001-2025, {ville}, "
        f"Guinee, horodatee en temps universel (UTC). {_NOTE_CORPS_NASA} {_NOTE_CONF_B} "
        f"Serie disponible a partir de 2001.{_NOTE_HORS_QC}"
    )


def upgrade() -> None:
    bind = op.get_bind()

    # === 1. Localites pilotes (id, nom, coordonnees) ==========================
    rows = bind.execute(
        sa.text(
            "SELECT code, id, nom, "
            "CAST(latitude AS DOUBLE PRECISION) AS lat, "
            "CAST(longitude AS DOUBLE PRECISION) AS lon "
            "FROM localites WHERE code = ANY(:codes)"
        ),
        {"codes": list(_PILOTES)},
    ).all()
    info_par_pilote: dict[str, dict[str, Any]] = {
        r.code: {"id": int(r.id), "nom": str(r.nom), "lat": float(r.lat), "lon": float(r.lon)}
        for r in rows
    }
    manquantes = set(_PILOTES) - info_par_pilote.keys()
    if manquantes:
        raise RuntimeError(f"Migration 116 : pilote(s) introuvable(s) : {sorted(manquantes)}.")

    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :c"), {"c": _SOURCE_CODE}
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(f"Migration 116 : source {_SOURCE_CODE!r} introuvable.")
    grandeurs_trouvees = set(
        bind.execute(
            sa.text(
                "SELECT code FROM grandeurs_referentiel WHERE code = ANY(:codes) AND actif = TRUE"
            ),
            {"codes": list(_GRANDEURS_NOUVELLES)},
        )
        .scalars()
        .all()
    )
    grandeurs_manquantes = set(_GRANDEURS_NOUVELLES) - grandeurs_trouvees
    if grandeurs_manquantes:
        raise RuntimeError(
            f"Migration 116 : grandeur(s) introuvable(s)/inactive(s) : "
            f"{sorted(grandeurs_manquantes)}."
        )

    # === 2. Extension in-place des 36 series (INCONDITIONNEL) =================
    n_renommees = 0
    for localite_code, prefixe in _PILOTES.items():
        for grandeur in _GRANDEURS_EXISTANTES:
            resultat = bind.execute(
                sa.text(
                    """
                    UPDATE series_metadonnees
                    SET code = :nouveau,
                        periode_fin = :fin,
                        libelle = REPLACE(libelle, '2001-2023', '2001-2025'),
                        note_publique = REPLACE(note_publique, '2001-2023', '2001-2025'),
                        commentaire_editorial = commentaire_editorial || :mention,
                        modifie_le = now()
                    WHERE code = :ancien
                    """
                ),
                {
                    "ancien": _code_ancien(prefixe, grandeur),
                    "nouveau": _code_nouveau(prefixe, grandeur),
                    "fin": _PERIODE_FIN,
                    "mention": _MENTION_EXTENSION,
                },
            )
            if resultat.rowcount != 1:
                raise RuntimeError(
                    f"Migration 116 : serie {_code_ancien(prefixe, grandeur)!r} introuvable "
                    f"pour extension ({localite_code}). Migrations 054-066 appliquees ?"
                )
            n_renommees += 1
    assert n_renommees == 36, f"Attendu 36 series etendues, obtenu {n_renommees}"

    # === 3. Seed des 18 series nouvelles (INCONDITIONNEL) =====================
    series_table = sa.table(
        "series_metadonnees",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("localite_id", sa.BigInteger),
        sa.column("grandeur_code", sa.String),
        sa.column("source_id", sa.BigInteger),
        sa.column("periode_debut", sa.Date),
        sa.column("periode_fin", sa.Date),
        sa.column("granularite", sa.String),
        sa.column("methode_collecte", sa.String),
        sa.column("methode_collecte_doc", sa.Text),
        sa.column("commentaire_editorial", sa.Text),
        sa.column("note_publique", sa.Text),
        sa.column("url_documentation", sa.Text),
    )
    lignes_series: list[dict[str, Any]] = []
    for localite_code, prefixe in _PILOTES.items():
        ville = info_par_pilote[localite_code]["nom"]
        for grandeur in _GRANDEURS_NOUVELLES:
            lignes_series.append(
                {
                    "code": _code_nouveau(prefixe, grandeur),
                    "libelle": (
                        f"{_LIBELLES_NOUVELLES[grandeur]} {ville} 2001-2025 (NASA POWER hourly)"
                    ),
                    "localite_id": info_par_pilote[localite_code]["id"],
                    "grandeur_code": grandeur,
                    "source_id": int(source_id),
                    "periode_debut": _PERIODE_DEBUT,
                    "periode_fin": _PERIODE_FIN,
                    "granularite": "horaire",
                    "methode_collecte": _METHODE_COLLECTE,
                    "methode_collecte_doc": _METHODE_COLLECTE_DOC,
                    "commentaire_editorial": _COMMENTAIRE_NOUVELLES.format(
                        grandeur_upper=grandeur.upper(),
                        ville=ville,
                        flag=_VARIABLE_ENV_SKIP_MASSE,
                    ),
                    "note_publique": _note_publique_nouvelle(grandeur, ville),
                    "url_documentation": _URL_DOCUMENTATION,
                }
            )
    assert len(lignes_series) == 18, f"Attendu 18 series nouvelles, obtenu {len(lignes_series)}"
    op.bulk_insert(series_table, lignes_series)

    # === 4. Ingestion de masse (gardee ; trigger d'audit suspendu) ============
    if _skip_ingestion_masse():
        op.execute(
            f"-- Migration 116 : ingestion horaire de masse court-circuitee "
            f"({_VARIABLE_ENV_SKIP_MASSE} pose). 36 series etendues + 18 seedees sans "
            f"mesures ; rejeu reel manuel hors CI."
        )
        return

    op.execute(f"ALTER TABLE {_TABLE_MESURES} DISABLE TRIGGER {_TRIGGER_AUDIT}")
    session = Session(bind=bind)
    try:
        total = 0
        decomptes: list[str] = []
        for localite_code, prefixe in _PILOTES.items():
            info = info_par_pilote[localite_code]
            # a) extension 2024-2025 des 6 series existantes (memes series).
            resultat_ext = ingerer_series_horaires_groupe(
                session=session,
                codes_series=[_code_nouveau(prefixe, g) for g in _GRANDEURS_EXISTANTES],
                mapping_grandeur_parametre_nasa=_GRANDEURS_EXISTANTES,
                latitude=info["lat"],
                longitude=info["lon"],
                annee_debut=2024,
                annee_fin=2025,
            )
            # b) pleine profondeur 2001-2025 des 3 grandeurs nouvelles.
            resultat_nouv = ingerer_series_horaires_groupe(
                session=session,
                codes_series=[_code_nouveau(prefixe, g) for g in _GRANDEURS_NOUVELLES],
                mapping_grandeur_parametre_nasa=_GRANDEURS_NOUVELLES,
                latitude=info["lat"],
                longitude=info["lon"],
                annee_debut=2001,
                annee_fin=2025,
            )
            n_ville = sum(resultat_ext.values()) + sum(resultat_nouv.values())
            total += n_ville
            decomptes.append(f"{localite_code}={n_ville}")
        op.execute(
            f"-- Migration 116 : {total} lignes horaires inserees (pilotes : extension "
            f"2024-2025 x 6 grandeurs + 3 grandeurs nouvelles 2001-2025, trigger d'audit "
            f"suspendu). Par ville : {', '.join(decomptes)}."
        )
    finally:
        session.close()
        op.execute(f"ALTER TABLE {_TABLE_MESURES} ENABLE TRIGGER {_TRIGGER_AUDIT}")


def downgrade() -> None:
    bind = op.get_bind()
    codes_nouvelles = [_code_nouveau(p, g) for p in _PILOTES.values() for g in _GRANDEURS_NOUVELLES]
    codes_etendues = [_code_nouveau(p, g) for p in _PILOTES.values() for g in _GRANDEURS_EXISTANTES]

    op.execute(f"ALTER TABLE {_TABLE_MESURES} DISABLE TRIGGER {_TRIGGER_AUDIT}")
    try:
        # Mesures des 18 series nouvelles (toutes) + lignes 2024-2025 des etendues.
        op.execute(
            sa.text(
                f"DELETE FROM {_TABLE_MESURES} WHERE serie_id IN "
                "(SELECT id FROM series_metadonnees WHERE code = ANY(:codes))"
            ).bindparams(sa.bindparam("codes", value=codes_nouvelles))
        )
        op.execute(
            sa.text(
                f"DELETE FROM {_TABLE_MESURES} WHERE serie_id IN "
                "(SELECT id FROM series_metadonnees WHERE code = ANY(:codes)) "
                "AND instant_mesure >= '2024-01-01T00:00:00+00'"
            ).bindparams(sa.bindparam("codes", value=codes_etendues))
        )
    finally:
        op.execute(f"ALTER TABLE {_TABLE_MESURES} ENABLE TRIGGER {_TRIGGER_AUDIT}")

    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_nouvelles)
        )
    )
    for prefixe in _PILOTES.values():
        for grandeur in _GRANDEURS_EXISTANTES:
            bind.execute(
                sa.text(
                    """
                    UPDATE series_metadonnees
                    SET code = :ancien,
                        periode_fin = '2023-12-31',
                        libelle = REPLACE(libelle, '2001-2025', '2001-2023'),
                        note_publique = REPLACE(note_publique, '2001-2025', '2001-2023'),
                        commentaire_editorial = REPLACE(commentaire_editorial, :mention, ''),
                        modifie_le = now()
                    WHERE code = :nouveau
                    """
                ),
                {
                    "ancien": _code_ancien(prefixe, grandeur),
                    "nouveau": _code_nouveau(prefixe, grandeur),
                    "mention": _MENTION_EXTENSION,
                },
            )

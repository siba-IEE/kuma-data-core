"""horaire_communes_lot3_seed_ingestion

Revision ID: 112
Revises: 111
Create Date: 2026-08-10 11:00:00

Chantier profondeur maximale par source, troisieme volet (horaire) - lot 3
sur 4 : series horaires NASA POWER pour **7 communes chef-lieu** (Kissidougou,
Koubia, Koundara, Kouroussa, Lelouma, Lola, Macenta), fenetre commune
**2001-01-01 -> 2025-12-31**, **9 grandeurs** (les 6 du parc pilote + vents
2 m / 10 m + precipitation, sondes API du 2026-08-09 : disponibles des 2001,
gapless ; l'albedo horaire est ecarte, moitie de sentinelles nocturnes pour
une information de surface lentement variable).

La fenetre est identique pour les 9 grandeurs d'une ville : le resolveur de
compagnes des endpoints F2 (``_chercher_serie_compagne``) exige un
``periode_debut`` strictement egal - contrainte dure.

Perimetre : 7 communes x 9 grandeurs = **63 series**. Volume vise hors
garde-fou : de l'ordre de 1,9 million de lignes par commune (les grandeurs
diurnes kt n'ont pas de lignes nocturnes), ingere en **25 appels par
commune** (un appel multi-parametres par annee civile,
``ingerer_series_horaires_groupe``).

Pattern 056 (live garde) : le seed des series est **inconditionnel** ;
l'ingestion est court-circuitee quand ``KUMA_SKIP_INGESTION_MASSE_HORAIRE``
est pose (CI et nightly) -> series sans mesures en CI, decomptes de series
invariants. Le rejeu reel s'execute manuellement hors CI (flag leve), suivi de la
migration QC du lot (revision suivante) qui qualifie les lignes.

Trigger d'audit : suspendu le temps des ecritures de masse
(``ALTER TABLE ... DISABLE TRIGGER``, reactive en fin), decision du
2026-08-10 (cf. ``docs/architecture/03-audit.md``) - l'audit trace
l'edition, pas le deversement reproductible d'une source.

``note_publique`` renseignee a l'insertion (doctrine 099). Confiance B
derivee par le module (modele satellitaire). QC : les vents et la
precipitation ne sont pas couverts par les tests de plausibilite v1
(doctrine QC a etendre) ; assumee et dite dans la note publique.
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
revision: str = "112"
down_revision: str | Sequence[str] | None = "111"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NUMERO_LOT = 3
_COMMUNES: tuple[str, ...] = (
    "gin_kissidougou",
    "gin_koubia",
    "gin_koundara",
    "gin_kouroussa",
    "gin_lelouma",
    "gin_lola",
    "gin_macenta",
)

_VARIABLE_ENV_SKIP_MASSE = "KUMA_SKIP_INGESTION_MASSE_HORAIRE"
_ANNEE_DEBUT, _ANNEE_FIN = 2001, 2025
_PERIODE_DEBUT = date(2001, 1, 1)
_PERIODE_FIN = date(2025, 12, 31)
_SOURCE_CODE = "nasa_power"
_METHODE_COLLECTE = "modele_satellitaire"
_METHODE_COLLECTE_DOC = "https://power.larc.nasa.gov/docs/methodology/"
_URL_DOCUMENTATION = "https://power.larc.nasa.gov/"
_TABLE_MESURES = "mesures_ressource_horaires"
_TRIGGER_AUDIT = "trg_audit_mesures_ressource_horaires"

# Grandeur -> parametre NASA POWER (les 6 du parc pilote + les 3 ajoutees).
_MAPPING_GRANDEURS: dict[str, str] = {
    "ghi": "ALLSKY_SFC_SW_DWN",
    "dni": "ALLSKY_SFC_SW_DNI",
    "dhi": "ALLSKY_SFC_SW_DIFF",
    "t2m": "T2M",
    "rh2m": "RH2M",
    "kt": "ALLSKY_KT",
    "vent_2m": "WS2M",
    "vent_10m": "WS10M",
    "precipitation": "PRECTOTCORR",
}

_LIBELLES: dict[str, str] = {
    "ghi": "GHI horaire",
    "dni": "DNI horaire",
    "dhi": "DHI horaire",
    "t2m": "Temperature 2m horaire",
    "rh2m": "Humidite relative 2m horaire",
    "kt": "Indice de clarte horaire",
    "vent_2m": "Vent 2m horaire",
    "vent_10m": "Vent 10m horaire",
    "precipitation": "Precipitations horaires",
}

# --- note_publique : charpente du corpus valide (quoi/ou -> source ->
# confiance -> limites), sans vocabulaire de chantier interne. --------------
_NOTE_DESCRIPTIFS: dict[str, str] = {
    "ghi": "Irradiation solaire globale recue sur un plan horizontal (GHI), en Wh/m2 par heure",
    "dhi": "Part diffuse de l'irradiation solaire sur plan horizontal (DHI), en Wh/m2 par heure",
    "dni": "Irradiation solaire directe recue face au soleil (DNI), en Wh/m2 par heure",
    "kt": (
        "Indice de clarte du ciel : rapport entre le rayonnement recu au sol et le "
        "rayonnement hors atmosphere (sans unite, entre 0 et 1, defini de jour uniquement)"
    ),
    "t2m": "Temperature de l'air a 2 metres du sol, en degres Celsius",
    "rh2m": "Humidite relative de l'air a 2 metres du sol, en pourcentage",
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
_GRANDEURS_HORS_QC = ("vent_2m", "vent_10m", "precipitation")

_COMMENTAIRE_TEMPLATE = (
    "Serie horaire {grandeur_upper} 2001-2025, {ville}, Guinee. Chantier profondeur "
    "maximale par source (decision 2026-08-09), volet horaire lot {lot}. Fenetre "
    "commune aux 9 grandeurs (contrainte du resolveur de compagnes F2). Instants "
    "UTC. Ingestion live gardee par {flag} (execution manuelle hors CI), appels "
    "groupes multi-parametres par annee. Statut brut a l'ingestion, qualification "
    "par la migration QC du lot. Trigger d'audit suspendu pendant le deversement "
    "(decision 2026-08-10, 03-audit.md). Confiance B (modele satellitaire)."
)


def _skip_ingestion_masse() -> bool:
    import os

    valeur = os.environ.get(_VARIABLE_ENV_SKIP_MASSE, "").strip().lower()
    return valeur in ("1", "true", "yes")


def _code_serie(commune_code: str, grandeur: str) -> str:
    return f"{commune_code}_{grandeur}_nasa_power_{_ANNEE_DEBUT}_{_ANNEE_FIN}"


def _note_publique(grandeur: str, ville: str) -> str:
    note = (
        f"{_NOTE_DESCRIPTIFS[grandeur]}. Serie horaire {_ANNEE_DEBUT}-{_ANNEE_FIN}, "
        f"{ville}, Guinee, horodatee en temps universel (UTC). {_NOTE_CORPS_NASA} "
        f"{_NOTE_CONF_B} Serie disponible a partir de 2001."
    )
    if grandeur in _GRANDEURS_HORS_QC:
        note += _NOTE_HORS_QC
    return note


def upgrade() -> None:
    bind = op.get_bind()

    # === 1. Localites du lot (id, nom, coordonnees) ===========================
    rows = bind.execute(
        sa.text(
            "SELECT code, id, nom, "
            "CAST(latitude AS DOUBLE PRECISION) AS lat, "
            "CAST(longitude AS DOUBLE PRECISION) AS lon "
            "FROM localites WHERE code = ANY(:codes)"
        ),
        {"codes": list(_COMMUNES)},
    ).all()
    info_par_commune: dict[str, dict[str, Any]] = {
        r.code: {"id": int(r.id), "nom": str(r.nom), "lat": float(r.lat), "lon": float(r.lon)}
        for r in rows
    }
    manquantes = set(_COMMUNES) - info_par_commune.keys()
    if manquantes:
        raise RuntimeError(
            f"Migration 112 : commune(s) introuvable(s) : {sorted(manquantes)}. "
            f"Verifier la migration 085."
        )

    # === 2. Source + 9 grandeurs actives ======================================
    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :c"), {"c": _SOURCE_CODE}
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError(f"Migration 112 : source {_SOURCE_CODE!r} introuvable.")
    grandeurs_trouvees = set(
        bind.execute(
            sa.text(
                "SELECT code FROM grandeurs_referentiel WHERE code = ANY(:codes) AND actif = TRUE"
            ),
            {"codes": list(_MAPPING_GRANDEURS)},
        )
        .scalars()
        .all()
    )
    grandeurs_manquantes = set(_MAPPING_GRANDEURS) - grandeurs_trouvees
    if grandeurs_manquantes:
        raise RuntimeError(
            f"Migration 112 : grandeur(s) introuvable(s)/inactive(s) : "
            f"{sorted(grandeurs_manquantes)}."
        )

    # === 3. Seed des 63 series (INCONDITIONNEL, invariant CI) =================
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
    for commune_code in _COMMUNES:
        ville = info_par_commune[commune_code]["nom"]
        for grandeur in _MAPPING_GRANDEURS:
            lignes_series.append(
                {
                    "code": _code_serie(commune_code, grandeur),
                    "libelle": (
                        f"{_LIBELLES[grandeur]} {ville} {_ANNEE_DEBUT}-{_ANNEE_FIN} "
                        f"(NASA POWER hourly)"
                    ),
                    "localite_id": info_par_commune[commune_code]["id"],
                    "grandeur_code": grandeur,
                    "source_id": int(source_id),
                    "periode_debut": _PERIODE_DEBUT,
                    "periode_fin": _PERIODE_FIN,
                    "granularite": "horaire",
                    "methode_collecte": _METHODE_COLLECTE,
                    "methode_collecte_doc": _METHODE_COLLECTE_DOC,
                    "commentaire_editorial": _COMMENTAIRE_TEMPLATE.format(
                        grandeur_upper=grandeur.upper(),
                        ville=ville,
                        lot=_NUMERO_LOT,
                        flag=_VARIABLE_ENV_SKIP_MASSE,
                    ),
                    "note_publique": _note_publique(grandeur, ville),
                    "url_documentation": _URL_DOCUMENTATION,
                }
            )
    assert len(lignes_series) == len(_COMMUNES) * len(_MAPPING_GRANDEURS), (
        f"Attendu {len(_COMMUNES) * len(_MAPPING_GRANDEURS)} series, obtenu {len(lignes_series)}"
    )
    op.bulk_insert(series_table, lignes_series)

    # === 4. Ingestion de masse (gardee ; trigger d'audit suspendu) ============
    if _skip_ingestion_masse():
        op.execute(
            f"-- Migration 112 : ingestion horaire de masse court-circuitee "
            f"({_VARIABLE_ENV_SKIP_MASSE} pose). {len(lignes_series)} series seedees "
            f"sans mesures ; rejeu reel manuel hors CI."
        )
        return

    op.execute(f"ALTER TABLE {_TABLE_MESURES} DISABLE TRIGGER {_TRIGGER_AUDIT}")
    session = Session(bind=bind)
    try:
        total = 0
        decomptes: list[str] = []
        for commune_code in _COMMUNES:
            info = info_par_commune[commune_code]
            resultat = ingerer_series_horaires_groupe(
                session=session,
                codes_series=[_code_serie(commune_code, g) for g in _MAPPING_GRANDEURS],
                mapping_grandeur_parametre_nasa=_MAPPING_GRANDEURS,
                latitude=info["lat"],
                longitude=info["lon"],
                annee_debut=_ANNEE_DEBUT,
                annee_fin=_ANNEE_FIN,
            )
            n_commune = sum(resultat.values())
            total += n_commune
            decomptes.append(f"{commune_code}={n_commune}")
        op.execute(
            f"-- Migration 112 : {total} lignes horaires inserees (lot {_NUMERO_LOT}, "
            f"7 communes x 9 grandeurs, trigger d'audit suspendu). "
            f"Par commune : {', '.join(decomptes)}."
        )
    finally:
        session.close()
        op.execute(f"ALTER TABLE {_TABLE_MESURES} ENABLE TRIGGER {_TRIGGER_AUDIT}")


def downgrade() -> None:
    codes_series = [_code_serie(c, g) for c in _COMMUNES for g in _MAPPING_GRANDEURS]
    op.execute(f"ALTER TABLE {_TABLE_MESURES} DISABLE TRIGGER {_TRIGGER_AUDIT}")
    try:
        op.execute(
            sa.text(
                f"DELETE FROM {_TABLE_MESURES} WHERE serie_id IN "
                "(SELECT id FROM series_metadonnees WHERE code = ANY(:codes))"
            ).bindparams(sa.bindparam("codes", value=codes_series))
        )
    finally:
        op.execute(f"ALTER TABLE {_TABLE_MESURES} ENABLE TRIGGER {_TRIGGER_AUDIT}")
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes_series)
        )
    )

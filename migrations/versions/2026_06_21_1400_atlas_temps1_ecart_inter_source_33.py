"""atlas_temps1_ecart_inter_source_33

Revision ID: 091
Revises: 090
Create Date: 2026-06-21 14:00:00

Atlas d'incertitude, **Temps 1** : etendre l'ecart inter-source aux 33
sur la fenetre commune **2021-2023**. C'est la donnee-coeur de l'atlas (sans elle, la
fiche d'incertitude est vide aux 28).

Deux ecarts, **pairwise par grandeur** (pas un consensus a trois) :

- **GHI** : ``ecart_relatif_referentiel`` = NASA daily agrege vs SARAH-3 (2021-2023).
  Existe deja aux 6 pilotes -> **etendu aux 28 communes** (+28 series calculees
  + 28 x 36 = 1 008 lignes).
- **DNI** : ``ecart_relatif_dni_cams`` = NASA daily agrege vs CAMS, fenetre **recente
  2021-2023**. N'existe nulle part sur cette fenetre (le climato 2004-2020 reste
  un artefact pilote distinct) -> **cree aux 34 points** (+34 series calculees + 34 x
  36 = 1 224 lignes). Surface honnetement le biais CAMS DNI all-sky (+28 %).

Total : **62 series calculees** (kuma_calculs) + **2 232 lignes grandeurs_metier**.
Confiance **B** (inter-source, pas terrain ; A reste terrain). Valeur signee
``(nasa - ref) / ref * 100`` ; ``|ecart|`` primaire cote consommation.

NE FAIT PAS les rangs (second ordre ; re-materialiser le rang spatial changerait
le pool des pilotes). Reutilise ``calculer_et_inserer_ecart_inter_source``
(``referentiels.py``, helpers purs) : zero physique nouvelle, zero reseau. Precondition
couverture 2021-2023 aux 34 verifiee (aucun trou).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE
from kuma_data_core.services.grandeurs.ecart_dni_cams import GRANDEUR_ECART_DNI_CAMS
from kuma_data_core.services.grandeurs.referentiels import (
    GRANDEUR_ECART,
    ContexteEcartInterSource,
    calculer_et_inserer_ecart_inter_source,
)

# revision identifiers, used by Alembic.
revision: str = "091"
down_revision: str | Sequence[str] | None = "090"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# === Perimetres ============================================================
_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)
_COMMUNES: tuple[str, ...] = tuple(
    p["commune_code"] for p in PREFECTURES_GUINEE if p["existante"] is None
)
# GHI ecart : seulement les 28 (pilotes deja faits).
_POINTS_GHI: tuple[str, ...] = _COMMUNES
# DNI ecart recent 2021-2023 : les 34 (nouveau pour tout le monde sur cette fenetre).
_POINTS_DNI: tuple[str, ...] = _PILOTES + _COMMUNES

_AN_DEBUT, _AN_FIN = 2021, 2023
_PERIODE_DEBUT = date(_AN_DEBUT, 1, 1)
_PERIODE_FIN = date(_AN_FIN, 12, 31)
_SOURCE_KUMA = "kuma_calculs"
_METHODE = "calcul_derive"
_PLAGE = "2021_2023"


def _alias(localite_code: str) -> str:
    """Exception Conakry-Kaloum -> gin_conakry dans les codes de serie."""
    return "gin_conakry" if localite_code == "gin_conakry_kaloum" else localite_code


def _code_serie_ecart(localite_code: str, grandeur_code: str) -> str:
    return f"{_alias(localite_code)}_{grandeur_code}_kuma_calculs_{_PLAGE}"


def _code_nasa_daily(localite_code: str, grandeur: str) -> str:
    return f"{_alias(localite_code)}_{grandeur}_nasa_power_2021_2025"


def _code_sarah3(localite_code: str) -> str:
    return f"{_alias(localite_code)}_ghi_sarah3_2021_2023"


def _code_cams(localite_code: str) -> str:
    return f"{_alias(localite_code)}_dni_cams_2021_2023"


_COMMENTAIRE = {
    GRANDEUR_ECART: (
        "Serie calculee Kuma ecart_relatif_referentiel (GHI) : divergence inter-source "
        "NASA POWER (agrege mensuel) vs PVGIS-SARAH3, fenetre commune 2021-2023. "
        "Densification atlas Temps 1. Confiance B (inter-source, pas terrain)."
    ),
    GRANDEUR_ECART_DNI_CAMS: (
        "Serie calculee Kuma ecart_relatif_dni_cams (DNI) : divergence inter-source "
        "NASA POWER (agrege mensuel) vs CAMS Radiation, fenetre RECENTE 2021-2023 "
        "(distincte du climato 2004-2020, artefact pilote). Surface le biais CAMS DNI "
        "all-sky (D-71, +28 %). Densification atlas Temps 1. Confiance B."
    ),
}


def _series_a_creer() -> list[tuple[str, str]]:
    """(localite_code, grandeur_code) pour chaque serie calculee a inserer."""
    paires: list[tuple[str, str]] = []
    paires += [(c, GRANDEUR_ECART) for c in _POINTS_GHI]
    paires += [(c, GRANDEUR_ECART_DNI_CAMS) for c in _POINTS_DNI]
    return paires


def upgrade() -> None:
    bind = op.get_bind()

    # === 1. Resolution localites + source kuma_calculs =====================
    tous = sorted(set(_POINTS_GHI) | set(_POINTS_DNI))
    rows = bind.execute(
        sa.text("SELECT code, id FROM localites WHERE code = ANY(:codes)"),
        {"codes": tous},
    ).all()
    localite_id: dict[str, int] = {r.code: int(r.id) for r in rows}
    manquantes = set(tous) - localite_id.keys()
    if manquantes:
        raise RuntimeError(f"Migration 091 : localite(s) introuvable(s) : {sorted(manquantes)}.")

    source_id = bind.execute(
        sa.text("SELECT id FROM sources WHERE code = :c"), {"c": _SOURCE_KUMA}
    ).scalar_one_or_none()
    if source_id is None:
        raise RuntimeError("Migration 091 : source 'kuma_calculs' introuvable.")

    # === 2. Creation des 62 series calculees ===============================
    series_table = sa.table(
        "series_metadonnees",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("localite_id", sa.BigInteger),
        sa.column("grandeur_code", sa.String),
        sa.column("source_id", sa.BigInteger),
        sa.column("periode_debut", sa.Date),
        sa.column("periode_fin", sa.Date),
        sa.column("methode_collecte", sa.String),
        sa.column("commentaire_editorial", sa.Text),
    )
    lignes_series: list[dict[str, Any]] = [
        {
            "code": _code_serie_ecart(loc, grandeur),
            "libelle": f"{grandeur} mensuel {loc} 2021-2023 (atlas Temps 1)",
            "localite_id": localite_id[loc],
            "grandeur_code": grandeur,
            "source_id": int(source_id),
            "periode_debut": _PERIODE_DEBUT,
            "periode_fin": _PERIODE_FIN,
            "methode_collecte": _METHODE,
            "commentaire_editorial": _COMMENTAIRE[grandeur],
        }
        for loc, grandeur in _series_a_creer()
    ]
    assert len(lignes_series) == 62, f"Attendu 62 series, obtenu {len(lignes_series)}"
    op.bulk_insert(series_table, lignes_series)

    # Resolution des ids des series calculees creees.
    codes_crees = [s["code"] for s in lignes_series]
    serie_id: dict[str, int] = {
        r.code: int(r.id)
        for r in bind.execute(
            sa.text("SELECT code, id FROM series_metadonnees WHERE code = ANY(:c)"),
            {"c": codes_crees},
        ).all()
    }

    # === 3. Materialisation des ecarts =====================================
    session = Session(bind=bind)
    try:
        ctx_ghi: list[ContexteEcartInterSource] = [
            {
                "localite_id": localite_id[loc],
                "code_serie_nasa_daily": _code_nasa_daily(loc, "ghi"),
                "code_serie_reference": _code_sarah3(loc),
                "series_metadonnees_id": serie_id[_code_serie_ecart(loc, GRANDEUR_ECART)],
            }
            for loc in _POINTS_GHI
        ]
        n_ghi, null_ghi = calculer_et_inserer_ecart_inter_source(
            session=session,
            contextes=ctx_ghi,
            grandeur_code=GRANDEUR_ECART,
            annee_debut=_AN_DEBUT,
            annee_fin=_AN_FIN,
        )

        ctx_dni: list[ContexteEcartInterSource] = [
            {
                "localite_id": localite_id[loc],
                "code_serie_nasa_daily": _code_nasa_daily(loc, "dni"),
                "code_serie_reference": _code_cams(loc),
                "series_metadonnees_id": serie_id[_code_serie_ecart(loc, GRANDEUR_ECART_DNI_CAMS)],
            }
            for loc in _POINTS_DNI
        ]
        n_dni, null_dni = calculer_et_inserer_ecart_inter_source(
            session=session,
            contextes=ctx_dni,
            grandeur_code=GRANDEUR_ECART_DNI_CAMS,
            annee_debut=_AN_DEBUT,
            annee_fin=_AN_FIN,
        )
        session.commit()

        assert n_ghi == 1008, f"Attendu 1008 lignes ecart GHI (28 x 36), obtenu {n_ghi}"
        assert n_dni == 1224, f"Attendu 1224 lignes ecart DNI (34 x 36), obtenu {n_dni}"
        op.execute(
            f"-- Migration 091 atlas Temps 1 : {n_ghi} ecart GHI (28 communes, {null_ghi} NULL) "
            f"+ {n_dni} ecart DNI (34 points, {null_dni} NULL), fenetre 2021-2023."
        )
    finally:
        session.close()


def downgrade() -> None:
    codes_series = [_code_serie_ecart(loc, g) for loc, g in _series_a_creer()]
    op.execute(
        sa.text(
            "DELETE FROM grandeurs_metier WHERE series_metadonnees_id IN "
            "(SELECT id FROM series_metadonnees WHERE code = ANY(:c))"
        ).bindparams(sa.bindparam("c", value=codes_series))
    )
    op.execute(
        sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:c)").bindparams(
            sa.bindparam("c", value=codes_series)
        )
    )

"""Quantification du biais de moyennage journalier sur le POA, en comparant
le calcul a entrees journalieres (methode actuelle, Perez au midi solaire sur
les totaux du jour) vs le calcul a entrees horaires (Perez par heure, somme
sur le jour).

Donnee : series horaires stockees (mesures_ressource_horaires, valide_auto),
6 villes pilotes, annee de reference. Aucune ecriture en base ; script
d'analyse one-off (pas de dependance applicative nouvelle).

Sortie : pour chaque ville, le POA annuel calcule par chaque methode et
le biais relatif (journalier - horaire) / horaire. Decide si l'extension
du calcul horaire au POA est justifiee.
"""

from __future__ import annotations

from datetime import date

import pandas as pd  # type: ignore[import-untyped]
import pvlib  # type: ignore[import-untyped]
from sqlalchemy import text

from kuma_data_core.api.v1.schemas.grandeurs import ParametresPOA
from kuma_data_core.db.session import get_engine
from kuma_data_core.services.grandeurs.poa_parametrable import (
    MesureJourPOA,
    calculer_poa_parametrable,
)

_VILLES = (
    "gin_conakry_kaloum",
    "gin_kindia",
    "gin_mamou",
    "gin_labe",
    "gin_kankan",
    "gin_nzerekore",
)
_ANNEE = 2022
# Plan de reference : quasi-horizontal optimal 10°N, plein sud.
_PARAMS = ParametresPOA(
    code_serie_source="x",
    periode_debut=date(_ANNEE, 1, 1),
    periode_fin=date(_ANNEE, 12, 31),
    inclinaison_deg=10.0,
    orientation_deg=180.0,
    albedo_sol=0.2,
)


def _serie_horaire(connexion, loc: str, grandeur: str) -> pd.Series:
    rows = connexion.execute(
        text(
            """
            SELECT mh.instant_mesure AS instant, mh.valeur AS valeur
            FROM mesures_ressource_horaires mh
            JOIN series_metadonnees sm ON sm.id = mh.serie_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE l.code = :loc AND sm.grandeur_code = :g AND sm.granularite = 'horaire'
              AND mh.statut = 'valide_auto' AND mh.valide_au IS NULL
              AND EXTRACT(YEAR FROM (mh.instant_mesure AT TIME ZONE 'UTC')) = :an
            ORDER BY mh.instant_mesure
            """
        ),
        {"loc": loc, "g": grandeur, "an": _ANNEE},
    ).all()
    idx = pd.DatetimeIndex([r.instant for r in rows])
    return pd.Series([float(r.valeur) for r in rows], index=idx, name=grandeur)


def _poa_horaire(lat: float, lon: float, ghi: pd.Series, dni: pd.Series, dhi: pd.Series) -> float:
    """POA annuel (kWh/m²/an) par integration horaire Perez."""
    df = pd.concat([ghi, dni, dhi], axis=1, keys=["ghi", "dni", "dhi"]).dropna()
    if df.empty:
        return 0.0
    times = df.index
    solpos = pvlib.solarposition.get_solarposition(times, lat, lon)
    dni_extra = pvlib.irradiance.get_extra_radiation(times)
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=_PARAMS.inclinaison_deg,
        surface_azimuth=_PARAMS.orientation_deg,
        solar_zenith=solpos["zenith"],
        solar_azimuth=solpos["azimuth"],
        dni=df["dni"],
        ghi=df["ghi"],
        dhi=df["dhi"],
        dni_extra=dni_extra,
        albedo=_PARAMS.albedo_sol,
        model="perez",
    )["poa_global"]
    # W/m² horaires (≈ Wh/m² par heure) -> somme annuelle -> kWh/m²/an.
    return float(poa.clip(lower=0).fillna(0.0).sum()) / 1000.0


def _poa_journalier(
    lat: float, lon: float, ghi: pd.Series, dni: pd.Series, dhi: pd.Series
) -> float:
    """POA annuel (kWh/m²/an) par methode journaliere (agrege horaire -> jour)."""
    df = pd.concat([ghi, dni, dhi], axis=1, keys=["ghi", "dni", "dhi"]).dropna()
    if df.empty:
        return 0.0
    # Agregation horaire -> total journalier (kWh/m²/jour).
    jour = df.groupby(df.index.date).sum() / 1000.0
    mesures: list[MesureJourPOA] = [
        {
            "instant_mesure": j,
            "ghi": float(row["ghi"]),
            "dni": float(row["dni"]),
            "dhi": float(row["dhi"]),
        }
        for j, row in jour.iterrows()
    ]
    resultats = calculer_poa_parametrable(mesures, lat, lon, _PARAMS)
    return sum(r.valeur for r in resultats)


def main() -> None:
    eng = get_engine()
    print(f"Etude L-TR-6 - biais de moyennage POA (annee {_ANNEE}, plan 10°/sud)")
    print(f"{'ville':18s} | {'POA journalier':>15s} | {'POA horaire':>12s} | {'biais %':>9s}")
    with eng.connect() as c:
        for loc in _VILLES:
            coord = c.execute(
                text(
                    "SELECT CAST(latitude AS float) lat, CAST(longitude AS float) lon "
                    "FROM localites WHERE code = :loc"
                ),
                {"loc": loc},
            ).first()
            ghi = _serie_horaire(c, loc, "ghi")
            dni = _serie_horaire(c, loc, "dni")
            dhi = _serie_horaire(c, loc, "dhi")
            if ghi.empty:
                print(f"{loc:18s} | (pas de donnee horaire {_ANNEE})")
                continue
            poa_j = _poa_journalier(coord.lat, coord.lon, ghi, dni, dhi)
            poa_h = _poa_horaire(coord.lat, coord.lon, ghi, dni, dhi)
            biais = 100.0 * (poa_j - poa_h) / poa_h if poa_h else 0.0
            print(f"{loc:18s} | {poa_j:>15.1f} | {poa_h:>12.1f} | {biais:>+8.2f}%")


if __name__ == "__main__":
    main()

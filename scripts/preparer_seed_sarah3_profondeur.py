"""Préparation du seed offline SARAH-3 profondeur (GHI et DNI mensuels 2005-2023).

Script ponctuel (dev deps), exécuté manuellement hors CI. Interroge l'endpoint
PVGIS MRcalc (JRC, radiation PVGIS-SARAH3) pour les **34 points** avec les
paramètres ``horirrad`` (GHI, champ ``H(h)_m``) et ``mr_dni`` (DNI faisceau
normal, champ ``Hb(n)_m``), sur la pleine profondeur servie par l'API :
**2005-2023** (plafond ``endyear=2023`` constaté par sonde, dette D-38 pour
2024-2025). Le DNI SARAH-3 est inédit dans la base : troisième direct mensuel
face à NASA POWER et CAMS.

Conversion : cumul mensuel kWh/m2/mois -> moyenne quotidienne kWh/m2/jour
(division par le nombre réel de jours du mois), arrondi 4 décimales, miroir
de l'ingestion SARAH-3 existante.

Seed NE-OFFLINE ``sarah3_profondeur_seed_data`` (lignes finales plates), la
migration le lit directement, aucun réseau au runtime. La série existante
2021-2023 (référence d'atlas) n'est pas touchée : la série longue 2005-2023
est un produit distinct, chevauchement documenté.

Usage : uv run --group dev python scripts/preparer_seed_sarah3_profondeur.py
"""

from __future__ import annotations

import calendar
import gzip
import json
from pathlib import Path
from typing import Any

import httpx

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE
from kuma_data_core.db.seeds.localites_seed_data import LOCALITES_SEED

LOCALITES_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)

URL_MRCALC = "https://re.jrc.ec.europa.eu/api/v5_3/MRcalc"
ANNEE_DEBUT, ANNEE_FIN = 2005, 2023
CHAMPS = {"H(h)_m": "ghi", "Hb(n)_m": "dni"}

REPERTOIRE_CACHE = Path("data/sarah3_profondeur")
DOSSIER_SEED = Path("src/kuma_data_core/db/seeds")

_LOADER = '''\
"""Seed offline SARAH-3 profondeur (GHI/DNI mensuels 2005-2023) - chargeur, GÉNÉRÉ, ne pas éditer.

Lignes finales ``(localite_code, grandeur_code, annee, mois, valeur)`` des 34
points, converties en kWh/m2/jour. Produit par
scripts/preparer_seed_sarah3_profondeur.py. Patron NE-OFFLINE.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_CHEMIN = Path(__file__).parent / "sarah3_profondeur_seed_data.json.gz"
_DATA: dict[str, Any] = json.loads(gzip.decompress(_CHEMIN.read_bytes()))

SARAH3_PROFONDEUR_SEED: list[dict[str, Any]] = _DATA["mensuel"]
'''


def coordonnees_tous_points() -> dict[str, tuple[float, float]]:
    """Coordonnées (lat, lon) des 34 points : 6 pilotes + 28 communes densification."""
    index = {e["code"]: e for e in LOCALITES_SEED}
    coords: dict[str, tuple[float, float]] = {}
    for code in LOCALITES_PILOTES:
        if code not in index:
            raise RuntimeError(f"Pilote absent de LOCALITES_SEED : {code}")
        coords[code] = (float(index[code]["latitude"]), float(index[code]["longitude"]))
    for p in PREFECTURES_GUINEE:
        if p["existante"] is None:
            coords[p["commune_code"]] = (float(p["lat"]), float(p["lon"]))
    if len(coords) != 34:
        raise RuntimeError(f"Attendu 34 points, obtenu {len(coords)}")
    return coords


def telecharger(client: httpx.Client, code: str, lat: float, lon: float) -> dict[str, Any]:
    REPERTOIRE_CACHE.mkdir(parents=True, exist_ok=True)
    chemin = REPERTOIRE_CACHE / f"{code}_{ANNEE_DEBUT}_{ANNEE_FIN}.json"
    if chemin.exists():
        return json.loads(chemin.read_text(encoding="utf-8"))
    reponse = client.get(
        URL_MRCALC,
        params={
            "lat": lat,
            "lon": lon,
            "horirrad": 1,
            "mr_dni": 1,
            "startyear": ANNEE_DEBUT,
            "endyear": ANNEE_FIN,
            "outputformat": "json",
        },
        timeout=120,
    )
    reponse.raise_for_status()
    payload: dict[str, Any] = reponse.json()
    chemin.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def extraire(code: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    lignes: list[dict[str, Any]] = []
    for entree in payload["outputs"]["monthly"]:
        annee, mois = int(entree["year"]), int(entree["month"])
        n_jours = calendar.monthrange(annee, mois)[1]
        for champ, grandeur in CHAMPS.items():
            brut = entree.get(champ)
            if brut is None:
                continue
            lignes.append(
                {
                    "localite_code": code,
                    "grandeur_code": grandeur,
                    "annee": annee,
                    "mois": mois,
                    "valeur": round(float(brut) / n_jours, 4),
                }
            )
    return lignes


def main() -> None:
    print("=== Préparation seed SARAH-3 profondeur (34 points, 2005-2023) ===")
    coords = coordonnees_tous_points()
    mensuel: list[dict[str, Any]] = []
    with httpx.Client() as client:
        for code, (lat, lon) in coords.items():
            payload = telecharger(client, code, lat, lon)
            lignes = extraire(code, payload)
            print(f"  {code}: {len(lignes)} valeurs")
            mensuel.extend(lignes)
    mensuel.sort(key=lambda r: (r["localite_code"], r["grandeur_code"], r["annee"], r["mois"]))
    chemin_gz = DOSSIER_SEED / "sarah3_profondeur_seed_data.json.gz"
    chemin_gz.write_bytes(
        gzip.compress(
            json.dumps({"mensuel": mensuel}, separators=(",", ":")).encode("utf-8"),
            compresslevel=9,
        )
    )
    (DOSSIER_SEED / "sarah3_profondeur_seed_data.py").write_text(
        _LOADER, encoding="utf-8", newline="\n"
    )
    print(f"OK. {len(mensuel)} valeurs -> {chemin_gz.name}")


if __name__ == "__main__":
    main()

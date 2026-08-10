"""Préparation du seed offline CAMS Radiation DNI.

Script ponctuel (dev deps), exécuté hors CI. Télécharge le DNI
all-sky aérosol-corrigé (`BNI`) de CAMS Radiation depuis l'ADS Copernicus,
extrait par ville pilote, convertit, et écrit un **seed committé** déterministe.
La migration d'insertion ne dépend QUE de ce seed (aucun ``cdsapi`` ni réseau au
runtime migration - discipline alpha).

**Paramétré par fenêtre** (extension 2021-2023, etc.) sans toucher le seed par
défaut :

- défaut ``2004 2020`` → ``cams_radiation_seed_data`` (nom legacy,
  constante ``CAMS_DNI_MENSUEL_SEED``) ;
- ``<debut> <fin>`` → ``cams_radiation_<debut>_<fin>_seed_data`` (constante
  ``CAMS_DNI_MENSUEL_<debut>_<fin>_SEED``). Le seed par défaut reste intact.

Faits API **vérifiés** (sondage ADS 2026-06-16) :

- Endpoint **ADS** ``https://ads.atmosphere.copernicus.eu/api`` ; token du
  ``.cdsapirc`` (licence CC-BY CAMS acceptée).
- Dataset ``cams-solar-radiation-timeseries`` ; ``time_step=1month`` = agrégat
  mensuel natif ; ``sky_type=observed_cloud`` = all-sky ; couverture **2004-02 → J-1**.
- CSV ``;``-séparé, en-têtes ``#`` ; **colonne 10 = `BNI` all-sky** (DNI), unité
  **Wh/m²** intégrés au mois.

**Conversion** vers l'unité de la grandeur ``dni`` (``kwh_par_m2_jour``) :
``kWh/m²/jour = (Wh/m²/mois ÷ 1000) ÷ nb_jours_du_mois`` (``calendar.monthrange``).

Usage : ``uv run --group dev python scripts/preparer_seed_cams.py [debut fin]``
(ex. ``... preparer_seed_cams.py 2021 2023``).
"""

from __future__ import annotations

import argparse
import calendar
import gzip
import json
import math
import os
from pathlib import Path
from typing import Any

import cdsapi  # type: ignore[import-untyped]

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE
from kuma_data_core.db.seeds.localites_seed_data import LOCALITES_SEED

# === Périmètre =============================================================

LOCALITES_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)

# Densification : 28 communes chef-lieu, seed SEPARE par fenetre (les migrations
# pilotes immuables iterent tout leur seed -> on ne doit pas y injecter les communes,
# d'ou des fichiers dedies). Deux fenetres legitimes (allowlist) :
#  - (2021, 2023) : couche atlas recent (migration 089) ;
#  - (2004, 2020) : climato (migration 095).
# Toute autre fenetre est rejetee (la garde reste protectrice : anti-typo / fenetre
# arbitraire), on ajoute juste la fenetre climato legitime.
FENETRE_DENSIFICATION = (2021, 2023)  # couche atlas recent (back-compat)
FENETRES_DENSIFICATION_AUTORISEES: frozenset[tuple[int, int]] = frozenset(
    {(2021, 2023), (2004, 2020)}
)

DATASET = "cams-solar-radiation-timeseries"
ADS_URL = "https://ads.atmosphere.copernicus.eu/api"
FENETRE_DEFAUT = (2004, 2020)  # seed legacy committé
GRANDEUR = "dni"
COL_BNI_ALLSKY = 9  # colonne 10 (1-indexée) du CSV CAMS = BNI all-sky (DNI)
WH_PAR_KWH = 1000.0

REPERTOIRE_DONNEES = Path("data/cams")
REPERTOIRE_SEEDS = Path("src/kuma_data_core/db/seeds")


def _noms_seed(annee_debut: int, annee_fin: int) -> tuple[str, str, str]:
    """(stem fichier, nom constante, libellé fenêtre).

    La fenêtre par défaut garde ses noms historiques.
    """
    if (annee_debut, annee_fin) == FENETRE_DEFAUT:
        return "cams_radiation_seed_data", "CAMS_DNI_MENSUEL_SEED", "Vague 4, Lot B"
    stem = f"cams_radiation_{annee_debut}_{annee_fin}_seed_data"
    var = f"CAMS_DNI_MENSUEL_{annee_debut}_{annee_fin}_SEED"
    return stem, var, f"Vague 4, extension {annee_debut}-{annee_fin}"


def _noms_seed_densification(annee_debut: int, annee_fin: int) -> tuple[str, str, str]:
    """Noms du seed densification (28 communes), distinct du seed pilotes (073)."""
    stem = f"cams_radiation_{annee_debut}_{annee_fin}_densification_seed_data"
    var = f"CAMS_DNI_MENSUEL_{annee_debut}_{annee_fin}_DENSIFICATION_SEED"
    return stem, var, f"densification 28 communes {annee_debut}-{annee_fin}"


def _module_loader(stem: str, var_name: str, fenetre_label: str) -> str:
    """Contenu du module-chargeur généré (gzip+json stdlib, discipline alpha)."""
    return f'''\
"""Seed offline CAMS Radiation DNI ({fenetre_label}) - chargeur, GÉNÉRÉ, ne pas éditer.

Données réelles CAMS Radiation (`BNI` all-sky = DNI aérosol-corrigé, ADS
Copernicus) produites par scripts/preparer_seed_cams.py. La donnée vit dans le
compagnon gzippé {stem}.json.gz (sous la limite de taille du dépôt). gzip + json
stdlib : aucune dépendance scientifique au runtime (discipline alpha).
Attribution CC-BY Copernicus/CAMS requise (cf. commentaire des séries).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_CHEMIN = Path(__file__).parent / "{stem}.json.gz"
_DATA: dict[str, Any] = json.loads(gzip.decompress(_CHEMIN.read_bytes()))

{var_name}: list[dict[str, Any]] = _DATA["mensuel"]
'''


def coordonnees_pilotes() -> dict[str, tuple[float, float]]:
    index = {e["code"]: e for e in LOCALITES_SEED}
    manquants = [c for c in LOCALITES_PILOTES if c not in index]
    if manquants:
        raise RuntimeError(f"Localités absentes de LOCALITES_SEED : {manquants}")
    return {
        c: (float(index[c]["latitude"]), float(index[c]["longitude"])) for c in LOCALITES_PILOTES
    }


def coordonnees_densification() -> dict[str, tuple[float, float]]:
    """28 communes chef-lieu (densification), coords decret 2025 / migration 085."""
    return {
        p["commune_code"]: (float(p["lat"]), float(p["lon"]))
        for p in PREFECTURES_GUINEE
        if p["existante"] is None
    }


def _client() -> cdsapi.Client:
    """Client cdsapi pointé sur l'ADS, token réutilisé du ``.cdsapirc``."""
    rc: dict[str, str] = {}
    with open(os.path.expanduser("~/.cdsapirc")) as f:
        for line in f:
            if line.strip() and ":" in line:
                cle, val = line.split(":", 1)
                rc[cle.strip()] = val.strip()
    return cdsapi.Client(url=ADS_URL, key=rc["key"])


def telecharger_cams(
    client: cdsapi.Client, code: str, lat: float, lon: float, annee_debut: int, annee_fin: int
) -> Path:
    chemin = REPERTOIRE_DONNEES / f"{code}_dni_{annee_debut}_{annee_fin}.csv"
    if chemin.exists():
        return chemin
    REPERTOIRE_DONNEES.mkdir(parents=True, exist_ok=True)
    print(f"  CAMS {code} ({lat:.4f}, {lon:.4f}) - file d'attente possible...")
    client.retrieve(
        DATASET,
        {
            "sky_type": "observed_cloud",
            "location": {"latitude": lat, "longitude": lon},
            "altitude": ["-999."],
            "date": [f"{annee_debut}-01-01/{annee_fin}-12-31"],
            "time_step": "1month",
            "time_reference": "universal_time",
            "format": "csv",
        },
        str(chemin),
    )
    return chemin


def extraire(code: str, chemin: Path) -> list[dict[str, Any]]:
    """Extrait le DNI mensuel converti (kWh/m²/jour) depuis le CSV CAMS."""
    lignes: list[dict[str, Any]] = []
    for ln in chemin.read_text(encoding="utf-8", errors="replace").splitlines():
        if not ln or ln.startswith("#"):
            continue
        cols = ln.split(";")
        if len(cols) <= COL_BNI_ALLSKY:
            continue
        periode = cols[0].strip()  # ex. '2021-01-01T00:00:00.0/2021-02-01T00:00:00.0'
        annee, mois = int(periode[:4]), int(periode[5:7])
        bni_wh = float(cols[COL_BNI_ALLSKY].strip())
        if math.isnan(bni_wh):
            continue
        n_jours = calendar.monthrange(annee, mois)[1]
        # Wh/m²/mois -> kWh/m²/jour : ÷ 1000 puis ÷ nb jours réel du mois.
        valeur = (bni_wh / WH_PAR_KWH) / n_jours
        lignes.append(
            {
                "localite_code": code,
                "grandeur_code": GRANDEUR,
                "annee": annee,
                "mois": mois,
                "valeur": round(valeur, 4),
            }
        )
    return lignes


def emettre_seed(
    mensuel: list[dict[str, Any]], stem: str, var_name: str, fenetre_label: str
) -> None:
    mensuel_tri = sorted(mensuel, key=lambda r: (r["localite_code"], r["annee"], r["mois"]))
    chemin_gz = REPERTOIRE_SEEDS / f"{stem}.json.gz"
    charge = json.dumps({"mensuel": mensuel_tri}, separators=(",", ":")).encode("utf-8")
    chemin_gz.write_bytes(gzip.compress(charge, compresslevel=9))
    (REPERTOIRE_SEEDS / f"{stem}.py").write_text(
        _module_loader(stem, var_name, fenetre_label), encoding="utf-8", newline="\n"
    )
    print(f"  Seed: {len(mensuel_tri)} mesures -> {chemin_gz}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prépare le seed offline CAMS DNI pour une fenêtre."
    )
    parser.add_argument("annee_debut", nargs="?", type=int, default=FENETRE_DEFAUT[0])
    parser.add_argument("annee_fin", nargs="?", type=int, default=FENETRE_DEFAUT[1])
    parser.add_argument(
        "--densification",
        action="store_true",
        help="28 communes (seed separe), fenetre 2021 2023 (atlas) ou 2004 2020 (climato).",
    )
    args = parser.parse_args()
    annee_debut, annee_fin = args.annee_debut, args.annee_fin

    if args.densification:
        if (annee_debut, annee_fin) not in FENETRES_DENSIFICATION_AUTORISEES:
            parser.error(
                "--densification : fenetre limitee a '2021 2023' (atlas) ou '2004 2020' "
                "(climato). Fenetre arbitraire rejetee."
            )
        stem, var_name, fenetre_label = _noms_seed_densification(annee_debut, annee_fin)
        coords = coordonnees_densification()
    else:
        stem, var_name, fenetre_label = _noms_seed(annee_debut, annee_fin)
        coords = coordonnees_pilotes()
    print(f"=== Préparation seed CAMS DNI {fenetre_label} ({stem}) ===")
    client = _client()
    mensuel: list[dict[str, Any]] = []
    for code, (lat, lon) in coords.items():
        chemin = telecharger_cams(client, code, lat, lon, annee_debut, annee_fin)
        lignes = extraire(code, chemin)
        print(f"  {code}: {len(lignes)} mois")
        mensuel.extend(lignes)
    emettre_seed(mensuel, stem, var_name, fenetre_label)
    print("OK.")


if __name__ == "__main__":
    main()

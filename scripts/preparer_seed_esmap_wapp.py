"""Préparation du seed offline ESMAP/WAPP - irradiance sol horaire (terrain-lite).

Livrable **humain ponctuel** (dev deps), exécuté hors CI. Lit les fichiers QC
1-minute d'une station WAPP (campagne ESMAP « Solar Development in Sub-Saharan
Africa », licence **CC-BY-4.0**, en main dans ``data/guinee/01-physique/``),
**agrège à l'horaire**, et écrit un **seed committé** déterministe. La migration
d'insertion ne dépend QUE de ce seed (aucun réseau au runtime migration -
discipline alpha).

**Paramétré par grandeur** (``ghi``, ``dni``, ``dhi``) : même station, mêmes
règles d'agrégation, colonne CSV différente. Chaque grandeur produit son propre
seed ; les seeds des autres grandeurs restent intacts.

Règles d'agrégation :

- **Horodatage** : les CSV sont en **UTC+0** ; on agrège en **UTC hour-beginning**
  (heure ``H`` = moyenne des minutes ``[H:00, H+1:00)``, label ``H:00`` UTC),
  aligné sur la série satellite NASA POWER (instant ``datetime(Y,M,D,H, UTC)``).
- **Clamp nuit** : les offsets négatifs de thermopile (valeur < 0 la nuit) sont
  **clampés à 0** avant moyenne (procédure QC BSRN).
- **Complétude** : une heure n'est émise que si **≥ 80 % des 60 minutes** ont une
  valeur présente (≥ 48 minutes valides). Les heures sous le seuil sont **exclues**
  (non ingérées) et **comptées** dans le rapport (pas de troncature silencieuse).

Sortie : ``<station>_<grandeur>_esmap_wapp_2021_2023_seed_data.py`` + compagnon
``.json.gz`` (``{"horaire": [{"instant_mesure", "valeur"}, ...]}``), gzip + json
stdlib (aucune dépendance scientifique au runtime).

Usage : ``uv run --group dev python scripts/preparer_seed_esmap_wapp.py kankan dni``
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

# === Périmètre =============================================================

REPERTOIRE_DONNEES = Path("data/guinee/01-physique")
REPERTOIRE_SEEDS = Path("src/kuma_data_core/db/seeds")

SEUIL_COMPLETUDE = 48  # ≥ 48/60 minutes valides (80 %) pour une heure émise
SOURCE = "esmap_wapp"

# Grandeur Kuma -> colonne du CSV QC WAPP.
_COLONNE_PAR_GRANDEUR: dict[str, str] = {"ghi": "GHI", "dni": "DNI", "dhi": "DHI"}

# Fichiers QC 1-min par station (an 1 + an 2), tels que livrés sur energydata.info.
_FICHIERS_STATION: dict[str, tuple[str, ...]] = {
    "kankan": (
        "solar-measurements_guinea-kankan_qc (1).csv",
        "solar-measurements_guinea-kankan_qc_year2.csv",
    ),
    "tarambaly": (
        "solar-measurements_guinea-tarambaly_qc (1).csv",
        "solar-measurements_guinea-tarambaly_qc_year2.csv",
    ),
}

_LOCALITE_PAR_STATION: dict[str, str] = {
    "kankan": "gin_kankan",
    # tarambaly : localité non seedée (métadonnées admin non confirmées) - en suivi.
}


def _lire_minutes(chemin: Path, colonne: str) -> pd.DataFrame:
    """Lit un CSV QC 1-min → DataFrame [timestamp UTC, valeur]. Ligne 2 = unités, ignorée."""
    df = pd.read_csv(
        chemin,
        usecols=["Timestamp", colonne],
        skiprows=[1],  # 2e ligne = unités (W/m², ...)
        dtype={colonne: "string"},
        encoding="latin-1",  # fichiers WAPP en latin-1 (² de « W/m² », ° ...)
    )
    df["timestamp"] = pd.to_datetime(df["Timestamp"], utc=True, errors="coerce")
    df["valeur"] = pd.to_numeric(df[colonne], errors="coerce")
    return df.dropna(subset=["timestamp"])[["timestamp", "valeur"]]


def agreger_horaire(df_minutes: pd.DataFrame) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Agrège les minutes en heures UTC hour-beginning (clamp nuit + seuil complétude)."""
    df = df_minutes.copy()
    # Clamp nuit : valeur négative (offset thermopile) -> 0 ; NaN = minute manquante.
    df["valeur_clamp"] = df["valeur"].clip(lower=0.0)
    df["heure"] = df["timestamp"].dt.floor("h")  # hour-beginning UTC

    groupes = df.groupby("heure")
    n_valides = groupes["valeur"].count()  # minutes avec valeur présente (non-NaN)
    moyennes = groupes["valeur_clamp"].mean()

    horaire: list[dict[str, Any]] = []
    n_incompletes = 0
    for heure, n_valide in n_valides.items():
        if n_valide >= SEUIL_COMPLETUDE:
            horaire.append(
                {
                    "instant_mesure": heure.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                    "valeur": round(float(moyennes[heure]), 2),
                }
            )
        else:
            n_incompletes += 1

    horaire.sort(key=lambda r: r["instant_mesure"])
    # Dédup d'éventuelles heures en double au raccord an1/an2 (garde la 1re).
    vus: set[str] = set()
    horaire_unique: list[dict[str, Any]] = []
    for r in horaire:
        if r["instant_mesure"] not in vus:
            vus.add(r["instant_mesure"])
            horaire_unique.append(r)
    n_doublons = len(horaire) - len(horaire_unique)
    stats = {
        "heures_emises": len(horaire_unique),
        "heures_incompletes_exclues": n_incompletes,
        "doublons_raccord": n_doublons,
    }
    return horaire_unique, stats


def _module_loader(stem: str, var_name: str, station: str, grandeur: str) -> str:
    """Contenu du module-chargeur généré (gzip+json stdlib, discipline alpha)."""
    return f'''\
"""Seed offline ESMAP/WAPP {grandeur.upper()} horaire - {station} - chargeur, GÉNÉRÉ, ne pas éditer.

Données réelles {grandeur.upper()} sol (campagne ESMAP/WAPP « Solar Development in
Sub-Saharan Africa », CC-BY-4.0) agrégées 1-min -> horaire par
scripts/preparer_seed_esmap_wapp.py. La donnée vit dans le compagnon gzippé
{stem}.json.gz (sous la limite de taille du dépôt). gzip + json stdlib : aucune
dépendance scientifique au runtime. Attribution CC-BY requise (World Bank / ESMAP
/ WAPP ; cf. commentaire des séries).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

_CHEMIN = Path(__file__).parent / "{stem}.json.gz"
_DATA: dict[str, Any] = json.loads(gzip.decompress(_CHEMIN.read_bytes()))

{var_name}: list[dict[str, Any]] = _DATA["horaire"]
'''


def emettre_seed(horaire: list[dict[str, Any]], station: str, grandeur: str) -> None:
    stem = f"{station}_{grandeur}_esmap_wapp_2021_2023_seed_data"
    var_name = f"{station.upper()}_{grandeur.upper()}_HORAIRE_2021_2023_SEED"
    chemin_gz = REPERTOIRE_SEEDS / f"{stem}.json.gz"
    charge = json.dumps({"horaire": horaire}, separators=(",", ":")).encode("utf-8")
    chemin_gz.write_bytes(gzip.compress(charge, compresslevel=9))
    (REPERTOIRE_SEEDS / f"{stem}.py").write_text(
        _module_loader(stem, var_name, station, grandeur), encoding="utf-8", newline="\n"
    )
    print(f"  Seed: {len(horaire)} heures -> {chemin_gz} ({chemin_gz.stat().st_size} octets)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prépare le seed offline ESMAP/WAPP horaire.")
    parser.add_argument("station", choices=sorted(_FICHIERS_STATION), help="Station WAPP")
    parser.add_argument(
        "grandeur", choices=sorted(_COLONNE_PAR_GRANDEUR), help="Grandeur (ghi/dni/dhi)"
    )
    args = parser.parse_args()
    station, grandeur = args.station, args.grandeur

    if station not in _LOCALITE_PAR_STATION:
        raise SystemExit(
            f"Station {station!r} : localité non seedée (métadonnées admin non confirmées). "
            f"En suivi - ne pas générer de seed sur un devine."
        )

    colonne = _COLONNE_PAR_GRANDEUR[grandeur]
    print(f"=== Préparation seed ESMAP/WAPP {grandeur.upper()} horaire - {station} ===")
    frames = []
    for nom in _FICHIERS_STATION[station]:
        chemin = REPERTOIRE_DONNEES / nom
        df = _lire_minutes(chemin, colonne)
        print(f"  {nom}: {len(df)} minutes lues")
        frames.append(df)
    df_minutes = pd.concat(frames, ignore_index=True)

    horaire, stats = agreger_horaire(df_minutes)
    print(
        f"  Agrégation: {stats['heures_emises']} heures émises, "
        f"{stats['heures_incompletes_exclues']} exclues (< 80 % complétude), "
        f"{stats['doublons_raccord']} doublons raccord retirés."
    )
    if horaire:
        print(f"  Plage: {horaire[0]['instant_mesure']} -> {horaire[-1]['instant_mesure']}")
        vals = [r["valeur"] for r in horaire]
        print(f"  {grandeur.upper()} horaire: min={min(vals)} max={max(vals)} W/m²")
    emettre_seed(horaire, station, grandeur)
    print("OK.")


if __name__ == "__main__":
    main()

"""Export de la grille de donnees du RDS Guinee depuis la base Kuma Data Core.

Produit l'integralite des fichiers de la couche B satellitaire du depot public
rds-guinee (grille par source, format large, CSV virgule UTF-8, manquant =
cellule vide), plus l'archive horaire destinee a Zenodo et le manifeste
(chemin, periode, lignes, localites, sha256). Les fichiers de la couche A
(terrain-kankan) ne sont pas regeneres ici : la station est une entite de
mesure autonome, ses fichiers sont geres a part.

Lit la base designee par POSTGRES_DB (la base de reference profondeur).
Selection data-driven par (source, grandeur, granularite) ; pour le mensuel
NASA POWER, seule la serie longue est retenue (periode_fin 2025-12-31), les
normales climatiques 1991/2001-2020 restant un produit editorial du moteur.
L'horaire ne retient que les lignes qualifiees valide_auto (les rejets du
controle qualite restent en base, comptes dans le manifeste du versement).

Conventions horaires ecrites au dictionnaire du RDS : instant_utc ISO-8601
avec decalage explicite, debut de pas, irradiances en Wh/m2 par pas horaire,
precipitation en mm/h.

Sortie : out/rds-guinee/ (data/... + horaire-nasa-power-2001-2025.zip +
MANIFEST.csv).

Usage : uv run --group dev python scripts/exporter_rds_guinee.py
"""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from kuma_data_core.core.config import get_settings

SORTIE = Path("out/rds-guinee")
SORTIE_DATA = SORTIE / "data"

# Pilotes : le code de serie utilise le prefixe gin_conakry, la localite et le
# RDS utilisent gin_conakry_kaloum. La resolution se fait par localite_id,
# aucun alias necessaire ici.

# === Grille cible : un bloc = un fichier CSV ===============================
# (source_kebab, nom_fichier, granularite, colonnes RDS, filtres series)
# colonne RDS "albedo" = grandeur Kuma "albedo_surface".
_ALIAS_COLONNES = {"albedo": "albedo_surface"}

BLOCS_MENSUELS: list[dict[str, Any]] = [
    {
        "source_kebab": "nasa-power",
        "fichier": "mensuel_1981_2025.csv",
        "source_code": "nasa_power",
        "colonnes": [
            "ghi",
            "dni",
            "dhi",
            "kt",
            "albedo",
            "t2m",
            "rh2m",
            "vent_2m",
            "vent_10m",
            "precipitation",
        ],
        # Serie longue uniquement (les normales 1991/2001-2020 coexistent).
        "filtre_series": "AND sm.periode_fin = '2025-12-31'",
    },
    {
        "source_kebab": "era5-land",
        "fichier": "mensuel_2001_2020.csv",
        "source_code": "ecmwf_era5_land",
        "colonnes": ["ghi", "t2m", "vent_10m"],
        "filtre_series": "",
    },
    {
        "source_kebab": "cams",
        "fichier": "radiation_dni_mensuel_2004_2023.csv",
        "source_code": "cams_radiation",
        "colonnes": ["dni"],
        "filtre_series": "",
    },
    {
        "source_kebab": "sarah3",
        "fichier": "ghi_mensuel_2021_2023.csv",
        "source_code": "sarah3_monthly",
        "colonnes": ["ghi"],
        "filtre_series": "",
    },
]

BLOCS_JOURNALIERS: list[dict[str, Any]] = [
    {
        "source_kebab": "nasa-power",
        "fichier": None,  # decoupe par decennies, cf. DECENNIES_NASA
        "source_code": "nasa_power",
        "colonnes": [
            "ghi",
            "dni",
            "dhi",
            "kt",
            "albedo",
            "t2m",
            "rh2m",
            "vent_2m",
            "vent_10m",
            "precipitation",
        ],
        "filtre_series": "",
    },
    {
        "source_kebab": "era5-land",
        "fichier": "journalier_2021_2025.csv",
        "source_code": "ecmwf_era5_land",
        "colonnes": ["ghi", "t2m", "vent_10m"],
        "filtre_series": "",
    },
    {
        "source_kebab": "cams",
        "fichier": "aerosol_pm_journalier_2021_2025.csv",
        "source_code": "cams_eac4",
        "colonnes": ["pm10", "pm2_5"],
        "filtre_series": "",
    },
]

DECENNIES_NASA: list[tuple[str, str, str]] = [
    ("journalier_1981_1990.csv", "1981-01-01", "1990-12-31"),
    ("journalier_1991_2000.csv", "1991-01-01", "2000-12-31"),
    ("journalier_2001_2010.csv", "2001-01-01", "2010-12-31"),
    ("journalier_2011_2020.csv", "2011-01-01", "2020-12-31"),
    ("journalier_2021_2025.csv", "2021-01-01", "2025-12-31"),
]

COLONNES_HORAIRE = [
    "ghi",
    "dni",
    "dhi",
    "kt",
    "t2m",
    "rh2m",
    "vent_2m",
    "vent_10m",
    "precipitation",
]
ARCHIVE_HORAIRE = "horaire-nasa-power-2001-2025.zip"

_MANIFEST: list[dict[str, Any]] = []


def _grandeur_kuma(colonne: str) -> str:
    return _ALIAS_COLONNES.get(colonne, colonne)


def _fmt(valeur: float | None) -> str:
    """Convention RDS : 4 decimales au plus (les valeurs deja courtes restent telles quelles)."""
    return "" if valeur is None else str(round(valeur, 4))


def _sha256(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def _inscrire_manifest(
    chemin: Path, source: str, granularite: str, periode: str, lignes: int, localites: int
) -> None:
    _MANIFEST.append(
        {
            "chemin": str(chemin.relative_to(SORTIE)).replace("\\", "/"),
            "source": source,
            "granularite": granularite,
            "periode": periode,
            "lignes": lignes,
            "localites": localites,
            "sha256": _sha256(chemin),
        }
    )


def exporter_mensuel(conn: Any, bloc: dict[str, Any]) -> None:
    colonnes = bloc["colonnes"]
    grandeurs = [_grandeur_kuma(c) for c in colonnes]
    rows = conn.execute(
        text(
            f"""
            SELECT l.code AS localite, m.annee, m.mois, sm.grandeur_code, m.valeur
            FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            JOIN sources s ON s.id = sm.source_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE s.code = :source AND sm.grandeur_code = ANY(:grandeurs)
              AND sm.granularite = 'mensuel' AND m.valide_au IS NULL
              {bloc["filtre_series"]}
            ORDER BY l.code, m.annee, m.mois
            """
        ),
        {"source": bloc["source_code"], "grandeurs": grandeurs},
    )
    pivot: dict[tuple[str, int, int], dict[str, float]] = defaultdict(dict)
    for r in rows:
        pivot[(r.localite, int(r.annee), int(r.mois))][r.grandeur_code] = r.valeur

    chemin = SORTIE_DATA / bloc["source_kebab"] / bloc["fichier"]
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with chemin.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["localite", "annee", "mois", *colonnes])
        for (loc, annee, mois), valeurs in sorted(pivot.items()):
            w.writerow(
                [loc, annee, mois, *(_fmt(valeurs.get(_grandeur_kuma(c))) for c in colonnes)]
            )
    annees = sorted({cle[1] for cle in pivot})
    locs = {cle[0] for cle in pivot}
    _inscrire_manifest(
        chemin,
        bloc["source_kebab"],
        "mensuel",
        f"{annees[0]}-{annees[-1]}" if annees else "",
        len(pivot),
        len(locs),
    )
    print(f"  {chemin.relative_to(SORTIE)} : {len(pivot)} lignes, {len(locs)} localites")


def exporter_journalier(
    conn: Any, bloc: dict[str, Any], fichier: str, date_min: str, date_max: str
) -> None:
    colonnes = bloc["colonnes"]
    grandeurs = [_grandeur_kuma(c) for c in colonnes]
    rows = conn.execute(
        text(
            f"""
            SELECT l.code AS localite, m.instant_mesure AS jour, sm.grandeur_code, m.valeur
            FROM mesures_ressource m
            JOIN series_metadonnees sm ON sm.id = m.serie_id
            JOIN sources s ON s.id = sm.source_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE s.code = :source AND sm.grandeur_code = ANY(:grandeurs)
              AND sm.granularite = 'journalier' AND m.valide_au IS NULL
              AND m.instant_mesure BETWEEN :dmin AND :dmax
              {bloc["filtre_series"]}
            ORDER BY l.code, m.instant_mesure
            """
        ),
        {
            "source": bloc["source_code"],
            "grandeurs": grandeurs,
            "dmin": date_min,
            "dmax": date_max,
        },
    )
    pivot: dict[tuple[str, date], dict[str, float]] = defaultdict(dict)
    for r in rows:
        pivot[(r.localite, r.jour)][r.grandeur_code] = r.valeur

    chemin = SORTIE_DATA / bloc["source_kebab"] / fichier
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with chemin.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["localite", "date", *colonnes])
        for (loc, jour), valeurs in sorted(pivot.items()):
            w.writerow(
                [
                    loc,
                    jour.isoformat(),
                    *(_fmt(valeurs.get(_grandeur_kuma(c))) for c in colonnes),
                ]
            )
    locs = {cle[0] for cle in pivot}
    _inscrire_manifest(
        chemin,
        bloc["source_kebab"],
        "journalier",
        f"{date_min}..{date_max}",
        len(pivot),
        len(locs),
    )
    print(f"  {chemin.relative_to(SORTIE)} : {len(pivot)} lignes, {len(locs)} localites")


def exporter_horaire(conn: Any) -> None:
    """Archive zip : un CSV par localite, lignes valide_auto uniquement."""
    localites = [
        (int(r.id), str(r.code))
        for r in conn.execute(
            text(
                """
                SELECT DISTINCT l.id, l.code FROM localites l
                JOIN series_metadonnees sm ON sm.localite_id = l.id
                JOIN sources s ON s.id = sm.source_id
                WHERE s.code = 'nasa_power' AND sm.granularite = 'horaire'
                ORDER BY l.code
                """
            )
        )
    ]
    chemin_zip = SORTIE / ARCHIVE_HORAIRE
    total_lignes = 0
    with zipfile.ZipFile(chemin_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for localite_id, code in localites:
            rows = conn.execution_options(yield_per=50_000).execute(
                text(
                    """
                    SELECT m.instant_mesure AS instant, sm.grandeur_code, m.valeur
                    FROM mesures_ressource_horaires m
                    JOIN series_metadonnees sm ON sm.id = m.serie_id
                    JOIN sources s ON s.id = sm.source_id
                    WHERE s.code = 'nasa_power' AND sm.localite_id = :lid
                      AND sm.granularite = 'horaire'
                      AND m.statut = 'valide_auto' AND m.valide_au IS NULL
                    ORDER BY m.instant_mesure
                    """
                ),
                {"lid": localite_id},
            )
            pivot: dict[Any, dict[str, float]] = defaultdict(dict)
            for r in rows:
                pivot[r.instant][r.grandeur_code] = r.valeur
            tampon = io.StringIO()
            w = csv.writer(tampon, lineterminator="\n")
            w.writerow(["instant_utc", *COLONNES_HORAIRE])
            for instant in sorted(pivot):
                valeurs = pivot[instant]
                w.writerow([instant.isoformat(), *(_fmt(valeurs.get(c)) for c in COLONNES_HORAIRE)])
            nom_membre = f"horaire/nasa-power/{code}_2001_2025.csv"
            zf.writestr(nom_membre, tampon.getvalue())
            total_lignes += len(pivot)
            print(f"  {nom_membre} : {len(pivot)} instants")
            pivot.clear()
    _inscrire_manifest(
        chemin_zip,
        "nasa-power",
        "horaire",
        "2001-01-01..2025-12-31",
        total_lignes,
        len(localites),
    )
    taille_mo = chemin_zip.stat().st_size / (1 << 20)
    print(f"  {ARCHIVE_HORAIRE} : {total_lignes} instants x localites, {taille_mo:.0f} Mo")


def exporter_manifest() -> None:
    chemin = SORTIE / "MANIFEST.csv"
    with chemin.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "chemin",
                "source",
                "granularite",
                "periode",
                "lignes",
                "localites",
                "sha256",
            ],
            lineterminator="\n",
        )
        w.writeheader()
        for ligne in _MANIFEST:
            w.writerow(ligne)
    print(f"  MANIFEST.csv : {len(_MANIFEST)} fichiers")


def main() -> None:
    settings = get_settings()
    print(f"=== Export RDS Guinee depuis la base {settings.postgres_db} ===")
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        for bloc in BLOCS_MENSUELS:
            exporter_mensuel(conn, bloc)
        for bloc in BLOCS_JOURNALIERS:
            if bloc["fichier"] is None:
                for fichier, dmin, dmax in DECENNIES_NASA:
                    exporter_journalier(conn, bloc, fichier, dmin, dmax)
            else:
                borne = bloc["fichier"].rsplit(".", 1)[0].split("_")
                exporter_journalier(
                    conn, bloc, bloc["fichier"], f"{borne[-2]}-01-01", f"{borne[-1]}-12-31"
                )
        exporter_horaire(conn)
    exporter_manifest()
    print("OK.")


if __name__ == "__main__":
    main()

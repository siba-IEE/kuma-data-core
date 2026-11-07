"""Preparation du seed offline EAC4 AOD 550 nm et ozone de surface (34 points).

Script ponctuel (dev deps, hors CI), execute manuellement. Telecharge la reanalyse
de composition atmospherique EAC4 (``cams-global-reanalysis-eac4``, ADS Copernicus)
sur une boite couvrant la Guinee, extrait aux 34 points (6 pilotes + 28 communes
chef-lieu) le point de grille le plus proche, agrege en valeurs journalieres et
ecrit un seed NE-OFFLINE dans un espace de noms separe :

- chargeur ``src/kuma_data_core/db/seeds/cams_eac4_aod_ozone_journalier_seed_data.py``
  (statique, stdlib gzip + json, lecture en flux) ;
- un compagnon par localite
  ``cams_eac4_aod_ozone_journalier_seed_data_<localite>.json.gz``.

Les seeds PM existants (``cams_eac4_seed_data*``, ``cams_eac4_densification_seed_data*``)
ne sont pas touches. Aucune migration ne depend du reseau : elles ne liront que ce seed.

Quatre grandeurs journalieres :

- ``aod_550`` : epaisseur optique totale des aerosols a 550 nm (sans unite),
  moyenne des 8 pas 3-horaires du jour ;
- ``aod_poussiere_550`` : epaisseur optique des poussieres a 550 nm (sans unite),
  moyenne des 8 pas ;
- ``ozone_surface`` : ozone au niveau modele 60, converti en ppb (fraction molaire),
  moyenne des 8 pas ;
- ``ozone_surface_diurne`` : meme champ, moyenne des seuls pas 09:00, 12:00 et
  15:00 UTC (fenetre diurne, heure locale Guinee = UTC).

Un jour dont un pas requis manque (ou est NaN) est EXCLU et liste (incomplet), un jour
sans aucun pas est EXCLU et liste (absent) ; jamais de moyenne partielle. Les pas
3-horaires sont agreges en journalier fichier par fichier (une annee civile au plus),
seules les valeurs journalieres restent en memoire. Une valeur hors fourchette
physique fait echouer le script (pas de
borne silencieuse).

FAITS CONFIRMES (depot ou schema public ADS, consulte le 2026-11-07) :

- dataset ADS ``cams-global-reanalysis-eac4``, endpoint
  ``https://ads.atmosphere.copernicus.eu/api`` (cf. ``preparer_seed_cams_eac4.py``) ;
- grille 0,75 deg (pixels des seeds PM commites : latitudes 7,5 / 8,25 / 9,0 ...) ;
- pas 3-horaire 00:00 -> 21:00 UTC ;
- noms de REQUETE ``total_aerosol_optical_depth_550nm``,
  ``dust_aerosol_optical_depth_550nm``, ``ozone`` ; ``model_level`` de "1" a "60" ;
  ``data_format`` dans {``grib``, ``netcdf_zip``} (schema public du processus).

CONFIRME (sonde ADS du 2026-11-07, janvier 2021, boite Guinee) :

- noms des variables dans le .nc : ``aod550`` (long_name 'Total Aerosol Optical
  Depth at 550nm'), ``duaod550`` ('Dust Aerosol Optical Depth at 550nm'), ``go3``
  ('Ozone mass mixing ratio (full chemistry scheme)') ; le mode complet echoue
  toujours en listant les variables reelles si l'un manque ;
- unite AOD '~' (sans dimension) ; unite ozone 'kg kg**-1' (rapport de melange
  massique, le mode complet echoue sinon) ;
- dimension ``model_level`` presente, valeur 60, avec ``valid_time`` (248 pas pour
  janvier = 31 j x 8), ``latitude`` et ``longitude`` ;
- cle ``date`` (``2021-01-01/2021-01-31``) acceptee, ``data_format`` ``netcdf_zip`` OK ;
- longitudes de l'ozone livrees en 0-360 (344.25, 345.0 ...) alors que l'AOD est en
  -180..180 : ``_ouvrir`` les normalise en [-180, 180) pour tous les fichiers
  (``normaliser_longitudes``), la garde de demi-maille reste en place.

SUPPOSE :

- niveau 60 = niveau le plus bas de la grille L60 d'IFS selon la documentation
  ECMWF (non verifiable par le .nc) ;
- date de fin EAC4 disponible : a trouver avec ``--verifier-fin AAAA-MM``, puis a
  fournir par ``--fin``.

Conversion ozone : ppb = mmr (kg/kg) x (M_air / M_O3) x 1e9, avec
M_air = 28,9644 g/mol (air sec) et M_O3 = 47,9982 g/mol.

Licence Copernicus (CC-BY). Attribution : Generated using Copernicus Atmosphere
Monitoring Service Information <annee> ; reference methodologique Inness et al.
(2019), doi:10.5194/acp-19-3515-2019.

Usage :
    uv run --group dev python scripts/preparer_seed_cams_eac4_aod_ozone.py --sonde
    uv run --group dev python scripts/preparer_seed_cams_eac4_aod_ozone.py --verifier-fin AAAA-MM
    uv run --group dev python scripts/preparer_seed_cams_eac4_aod_ozone.py --fin AAAA-MM-JJ
    (options : --debut AAAA-MM-JJ, defaut 2004-02-01)

Idempotence : les .zip caches dans ``data/cams_eac4_aod_ozone/`` ne sont pas
re-telecharges ; les compagnons sont tries de facon stable.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import zipfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from kuma_data_core.db.seeds.localites_prefectures_seed_data import PREFECTURES_GUINEE
from kuma_data_core.db.seeds.localites_seed_data import LOCALITES_SEED

# === Perimetre =============================================================

LOCALITES_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)
NB_POINTS_ATTENDU = 34
LOCALITE_SONDE = "gin_conakry_kaloum"

# Boite de requete [Nord, Ouest, Sud, Est] couvrant la Guinee avec marge. Les 34
# points (lat 7,57..12,48 ; lon -14,29..-8,53) et leur pixel 0,75 deg le plus proche
# y sont inclus : verifie a l'execution par ``verifier_emprise``.
EMPRISE_GUINEE: tuple[float, float, float, float] = (13.5, -15.75, 6.75, -7.0)
PAS_GRILLE_DEG = 0.75

# === Constantes ADS / EAC4 =================================================

ADS_URL = "https://ads.atmosphere.copernicus.eu/api"
DATASET_EAC4 = "cams-global-reanalysis-eac4"
FORMAT_DONNEES = "netcdf_zip"  # valeurs du schema public : grib, netcdf_zip
# Le schema public du processus ne liste pas de champ date ; le script PM l'envoyait
# avec succes sous ce nom et ce format. A ajuster ici si l'ADS le refuse.
CLE_DATE_REQUETE = "date"

FAMILLE_AOD = "aod"
FAMILLE_OZONE = "ozone"
FAMILLES: tuple[str, ...] = (FAMILLE_AOD, FAMILLE_OZONE)

VARIABLES_REQUETE: dict[str, tuple[str, ...]] = {
    FAMILLE_AOD: ("total_aerosol_optical_depth_550nm", "dust_aerosol_optical_depth_550nm"),
    FAMILLE_OZONE: ("ozone",),
}
# Niveau modele 60 : suppose le plus bas de la grille verticale EAC4 (a confirmer).
NIVEAU_MODELE_OZONE = "60"

# Noms .nc SUPPOSES (a confirmer par --sonde) -> grandeur(s) Kuma.
VAR_NC_AOD_TOTALE = "aod550"
VAR_NC_AOD_POUSSIERE = "duaod550"
VAR_NC_OZONE = "go3"
VARIABLES_NC_ATTENDUES: dict[str, tuple[str, ...]] = {
    FAMILLE_AOD: (VAR_NC_AOD_TOTALE, VAR_NC_AOD_POUSSIERE),
    FAMILLE_OZONE: (VAR_NC_OZONE,),
}

HEURES_3H: tuple[str, ...] = (
    "00:00",
    "03:00",
    "06:00",
    "09:00",
    "12:00",
    "15:00",
    "18:00",
    "21:00",
)
HEURES_DIURNES: tuple[str, ...] = ("09:00", "12:00", "15:00")

# === Conversion ozone ======================================================

# Masse molaire de l'air sec (g/mol), valeur standard de reference.
MASSE_MOLAIRE_AIR_G_MOL = 28.9644
# Masse molaire de l'ozone O3 (g/mol) : 3 x 15,9994.
MASSE_MOLAIRE_O3_G_MOL = 47.9982
# Rapport de melange massique (kg/kg) -> fraction molaire en ppb (nmol/mol).
FACTEUR_MMR_VERS_PPB = MASSE_MOLAIRE_AIR_G_MOL / MASSE_MOLAIRE_O3_G_MOL * 1e9

# === Grandeurs, fourchettes, arrondis ======================================

GRANDEUR_AOD = "aod_550"
GRANDEUR_AOD_POUSSIERE = "aod_poussiere_550"
GRANDEUR_OZONE = "ozone_surface"
GRANDEUR_OZONE_DIURNE = "ozone_surface_diurne"
GRANDEURS: tuple[str, ...] = (
    GRANDEUR_AOD,
    GRANDEUR_AOD_POUSSIERE,
    GRANDEUR_OZONE,
    GRANDEUR_OZONE_DIURNE,
)

# Fourchettes de plausibilite : hors fourchette -> echec explicite, aucune borne.
# Ozone : 500 ppb est un seuil anti-corruption (unite ou variable erronee), pas
# un seuil de realisme. EAC4 produit en fin de saison seche (fevrier-mai) des pics
# locaux de surface jusqu'a ~300 ppb en moyenne diurne (2004-2019), probables
# artefacts du modele lies aux feux ; ils sont conserves tels quels (fidelite a la
# source) et signales dans la note publique des series, pas retires ici.
FOURCHETTES: dict[str, tuple[float, float]] = {
    GRANDEUR_AOD: (0.0, 5.0),
    GRANDEUR_AOD_POUSSIERE: (0.0, 5.0),
    GRANDEUR_OZONE: (0.0, 500.0),
    GRANDEUR_OZONE_DIURNE: (0.0, 500.0),
}

# Arrondis : AOD a 4 decimales (1e-4, cent fois sous l'incertitude d'une AOD
# observee, ~0,01) ; ozone a 2 decimales en ppb (0,01 ppb, tres en dessous de
# l'incertitude d'une reanalyse, valeurs typiques 10-60 ppb).
DECIMALES: dict[str, int] = {
    GRANDEUR_AOD: 4,
    GRANDEUR_AOD_POUSSIERE: 4,
    GRANDEUR_OZONE: 2,
    GRANDEUR_OZONE_DIURNE: 2,
}

# === Sorties ===============================================================

REPERTOIRE_CACHE = Path("data/cams_eac4_aod_ozone")
DOSSIER_SEED = Path("src/kuma_data_core/db/seeds")
PREFIXE_COMPAGNON = "cams_eac4_aod_ozone_journalier_seed_data_"
TAILLE_MAX_COMPAGNON_KO = 1000  # hook pre-commit check-added-large-files : 1024 Ko

DEBUT_DEFAUT = date(2004, 2, 1)
DEBUT_SONDE, FIN_SONDE = date(2021, 1, 1), date(2021, 1, 31)

_NOMS_TEMPS = ("valid_time", "time")


# === Coordonnees (depuis les referentiels, non re-encodees) ================


def coordonnees_34_points() -> dict[str, tuple[float, float]]:
    """(lat, lon) des 34 points : 6 pilotes (``LOCALITES_SEED``) + 28 communes
    chef-lieu (``PREFECTURES_GUINEE``, ``existante is None``). Garde ``len == 34``."""
    index = {e["code"]: e for e in LOCALITES_SEED}
    coords: dict[str, tuple[float, float]] = {}
    for code in LOCALITES_PILOTES:
        if code not in index:
            raise RuntimeError(f"Pilote absent de LOCALITES_SEED : {code}")
        coords[code] = (float(index[code]["latitude"]), float(index[code]["longitude"]))
    for p in PREFECTURES_GUINEE:
        if p["existante"] is None:
            coords[p["commune_code"]] = (float(p["lat"]), float(p["lon"]))
    if len(coords) != NB_POINTS_ATTENDU:
        raise RuntimeError(f"Attendu {NB_POINTS_ATTENDU} points, obtenu {len(coords)}")
    return dict(sorted(coords.items()))


def pixel_grille_le_plus_proche(lat: float, lon: float) -> tuple[float, float]:
    """Noeud de grille 0,75 deg le plus proche (grille alignee sur 0 deg)."""
    return (
        round(lat / PAS_GRILLE_DEG) * PAS_GRILLE_DEG,
        round(lon / PAS_GRILLE_DEG) * PAS_GRILLE_DEG,
    )


def verifier_emprise(
    coords: Mapping[str, tuple[float, float]],
    emprise: tuple[float, float, float, float] = EMPRISE_GUINEE,
) -> None:
    """Echoue si un point ou son pixel 0,75 deg le plus proche sort de la boite."""
    nord, ouest, sud, est = emprise
    hors: list[str] = []
    for code, (lat, lon) in coords.items():
        plat, plon = pixel_grille_le_plus_proche(lat, lon)
        for la, lo in ((lat, lon), (plat, plon)):
            if not (sud <= la <= nord and ouest <= lo <= est):
                hors.append(f"{code} ({la}, {lo})")
    if hors:
        raise RuntimeError(f"Points ou pixels hors emprise {emprise} : {hors}")


# === Requetes ==============================================================


def intervalles_annuels(debut: date, fin: date) -> list[tuple[date, date]]:
    """Decoupe [debut, fin] en intervalles d'une annee civile au plus."""
    if fin < debut:
        raise ValueError(f"Fenetre vide : {debut} > {fin}")
    intervalles: list[tuple[date, date]] = []
    courant = debut
    while courant <= fin:
        fin_annee = min(date(courant.year, 12, 31), fin)
        intervalles.append((courant, fin_annee))
        courant = date(courant.year + 1, 1, 1)
    return intervalles


def construire_requete(famille: str, debut: date, fin: date) -> dict[str, Any]:
    """Requete ADS pour une famille de variables sur [debut, fin], boite Guinee."""
    requete: dict[str, Any] = {
        "variable": list(VARIABLES_REQUETE[famille]),
        CLE_DATE_REQUETE: [f"{debut.isoformat()}/{fin.isoformat()}"],
        "time": list(HEURES_3H),
        "area": list(EMPRISE_GUINEE),
        "data_format": FORMAT_DONNEES,
    }
    if famille == FAMILLE_OZONE:
        requete["model_level"] = [NIVEAU_MODELE_OZONE]
    return requete


def _telecharger(requete: dict[str, Any], chemin: Path) -> None:
    if chemin.exists():
        return
    import cdsapi  # type: ignore[import-untyped]  # dev deps, import tardif

    chemin.parent.mkdir(parents=True, exist_ok=True)
    print(f"  ADS {DATASET_EAC4} -> {chemin.name} (file d'attente possible)...")
    cdsapi.Client(url=ADS_URL).retrieve(DATASET_EAC4, requete, str(chemin))


def normaliser_longitudes(valeurs: Sequence[float]) -> list[float]:
    """Ramene des longitudes en [-180, 180) : 344.25 -> -15.75, -13.5 inchange,
    180 -> -180 (borne superieure exclue). Echoue si deux longitudes se confondent
    apres normalisation (grille qui ferait le tour du globe en double)."""
    resultat = [((float(v) + 180.0) % 360.0) - 180.0 for v in valeurs]
    if len(set(resultat)) != len(resultat):
        raise RuntimeError("Longitudes en double apres normalisation en [-180, 180).")
    return resultat


def _normaliser_longitudes_ds(ds: Any) -> Any:
    """Si le fichier porte des longitudes > 180 (cas constate pour l'ozone EAC4),
    les ramene en [-180, 180) et trie par longitude."""
    if "longitude" not in ds.coords:
        return ds
    valeurs = [float(v) for v in ds["longitude"].values.reshape(-1)]
    if not any(v > 180.0 for v in valeurs):
        return ds
    ds = ds.assign_coords(longitude=("longitude", normaliser_longitudes(valeurs)))
    return ds.sortby("longitude")


def _ouvrir(chemin: Path, aplatir: bool = True) -> Any:
    """Ouvre le(s) .nc d'une archive ADS (fusion si plusieurs), normalise les
    longitudes en [-180, 180). Aplatit les dimensions singleton hors temps si
    ``aplatir``."""
    import xarray as xr  # type: ignore[import-untyped]  # dev deps, import tardif

    if not zipfile.is_zipfile(chemin):
        ds = xr.open_dataset(chemin, engine="netcdf4")
    else:
        rep = chemin.parent / (chemin.stem + "_nc")
        rep.mkdir(exist_ok=True)
        with zipfile.ZipFile(chemin) as z:
            z.extractall(rep)
        ncs = sorted(rep.glob("*.nc"))
        if not ncs:
            raise RuntimeError(f"Aucun .nc dans {chemin.name}.")
        dsets = [xr.open_dataset(n, engine="netcdf4") for n in ncs]
        ds = xr.merge(dsets, compat="override") if len(dsets) > 1 else dsets[0]
    ds = _normaliser_longitudes_ds(ds)
    if not aplatir:
        return ds
    singletons = [d for d in ds.dims if ds.sizes[d] == 1 and d not in _NOMS_TEMPS]
    return ds.squeeze(singletons, drop=True) if singletons else ds


def _coord_temps(ds: Any) -> str:
    for nom in _NOMS_TEMPS:
        if nom in ds.variables:
            return nom
    raise RuntimeError(
        f"Coordonnee temps introuvable (cherche {_NOMS_TEMPS}). "
        f"Variables presentes : {list(ds.variables)}."
    )


# === Controles des noms et unites (rien d'invente) =========================


def verifier_variables_nc(presentes: Iterable[str], attendues: Sequence[str]) -> None:
    """Echoue en listant les variables reelles si un nom attendu est absent."""
    reelles = list(presentes)
    manquantes = [v for v in attendues if v not in reelles]
    if manquantes:
        raise RuntimeError(
            f"Variable(s) {manquantes} absente(s) du .nc EAC4. Variables reelles : "
            f"{reelles}. Confirmer les noms par --sonde puis mettre a jour les constantes "
            "VAR_NC_*."
        )


def unite_est_rapport_massique(unite: str) -> bool:
    """Vrai si ``unite`` note un rapport de melange massique kg/kg, quelle que soit
    la graphie (``kg kg**-1``, ``kg kg-1``, ``kg/kg``, ``kg kg^-1``)."""
    compacte = unite.strip().lower().replace(" ", "").replace("**", "").replace("^", "")
    return compacte in {"kgkg-1", "kg/kg"}


def verifier_unite_ozone(unite: str | None) -> None:
    if unite is None or not unite_est_rapport_massique(unite):
        raise RuntimeError(
            f"Unite de l'ozone {unite!r} : un rapport de melange massique (kg/kg) est "
            "attendu pour la conversion en ppb. Confirmer par --sonde ; aucune "
            "conversion n'est supposee."
        )


# === Fonctions pures d'agregation ==========================================


def mmr_vers_ppb(mmr_kg_kg: float) -> float:
    """Rapport de melange massique (kg/kg) -> fraction molaire (ppb)."""
    return mmr_kg_kg * FACTEUR_MMR_VERS_PPB


def calendrier(debut: date, fin: date) -> list[str]:
    """Jours attendus ``debut`` -> ``fin`` (bornes incluses), en ISO."""
    if fin < debut:
        raise ValueError(f"Fenetre vide : {debut} > {fin}")
    return [(debut + timedelta(days=i)).isoformat() for i in range((fin - debut).days + 1)]


def regrouper_par_jour(
    instants: Sequence[str], valeurs: Sequence[float]
) -> tuple[dict[str, dict[str, float]], int]:
    """Range les pas par jour puis par heure UTC ``HH:MM``.

    ``instants`` : chaines ISO (``2021-01-01T03:00:00...``). Les valeurs non finies
    (NaN, valeur de remplissage decodee, infini) sont ecartees et comptees ; leur jour
    reste present (eventuellement vide) pour etre classe incomplet, pas absent.
    Un pas en double (meme jour, meme heure) fait echouer.

    Returns:
        ``({jour: {heure: valeur}}, nb_valeurs_ecartees)``.
    """
    if len(instants) != len(valeurs):
        raise ValueError(f"{len(instants)} instants pour {len(valeurs)} valeurs")
    par_jour: dict[str, dict[str, float]] = {}
    vus: set[tuple[str, str]] = set()
    ecartees = 0
    for instant, valeur in zip(instants, valeurs, strict=True):
        jour, heure = instant[:10], instant[11:16]
        if (jour, heure) in vus:
            raise RuntimeError(f"Pas en double : {jour} {heure}")
        vus.add((jour, heure))
        pas_du_jour = par_jour.setdefault(jour, {})
        v = float(valeur)
        if not math.isfinite(v):
            ecartees += 1
            continue
        pas_du_jour[heure] = v
    return par_jour, ecartees


def moyenne_des_heures(pas_du_jour: Mapping[str, float], heures: Sequence[str]) -> float | None:
    """Moyenne des pas ``heures`` du jour ; ``None`` si l'un d'eux manque."""
    if any(h not in pas_du_jour for h in heures):
        return None
    return sum(pas_du_jour[h] for h in heures) / len(heures)


@dataclass
class AgregatJournalier:
    """Valeurs journalieres d'une grandeur et jours exclus, par motif."""

    valeurs: dict[str, float] = field(default_factory=dict)
    jours_incomplets: list[str] = field(default_factory=list)  # pas manquant ou non fini
    jours_absents: list[str] = field(default_factory=list)  # aucun pas dans le fichier

    def fusionner(self, autre: AgregatJournalier) -> None:
        """Ajoute une autre periode, disjointe (echoue sinon)."""
        communs = self.valeurs.keys() & autre.valeurs.keys()
        if communs:
            raise RuntimeError(f"Jours en double entre periodes : {sorted(communs)[:5]}")
        self.valeurs.update(autre.valeurs)
        self.jours_incomplets.extend(autre.jours_incomplets)
        self.jours_absents.extend(autre.jours_absents)


def agreger_journalier(
    par_jour: Mapping[str, Mapping[str, float]],
    heures: Sequence[str],
    jours_attendus: Sequence[str],
    conversion: Callable[[float], float] | None = None,
) -> AgregatJournalier:
    """Valeur journaliere (moyenne des ``heures``, puis ``conversion``) sur le
    calendrier ``jours_attendus``. Un jour sans aucun pas est ABSENT, un jour dont
    un pas requis manque ou n'est pas fini est INCOMPLET : les deux sont exclus et
    listes, jamais moyennes partiellement. Un jour hors calendrier fait echouer."""
    attendus = set(jours_attendus)
    hors = sorted(set(par_jour) - attendus)
    if hors:
        raise RuntimeError(f"Jours hors de la fenetre attendue : {hors[:5]}")
    agregat = AgregatJournalier()
    for jour in sorted(attendus):
        if jour not in par_jour:
            agregat.jours_absents.append(jour)
            continue
        moyenne = moyenne_des_heures(par_jour[jour], heures)
        if moyenne is None:
            agregat.jours_incomplets.append(jour)
            continue
        agregat.valeurs[jour] = conversion(moyenne) if conversion is not None else moyenne
    return agregat


# Variable .nc -> grandeurs qu'elle alimente : (grandeur, pas requis, conversion).
REGLES_PAR_VARIABLE: dict[
    str, tuple[tuple[str, tuple[str, ...], Callable[[float], float] | None], ...]
] = {
    VAR_NC_AOD_TOTALE: ((GRANDEUR_AOD, HEURES_3H, None),),
    VAR_NC_AOD_POUSSIERE: ((GRANDEUR_AOD_POUSSIERE, HEURES_3H, None),),
    VAR_NC_OZONE: (
        (GRANDEUR_OZONE, HEURES_3H, mmr_vers_ppb),
        (GRANDEUR_OZONE_DIURNE, HEURES_DIURNES, mmr_vers_ppb),
    ),
}


def agreger_annee(
    var_nc: str,
    instants: Sequence[str],
    valeurs: Sequence[float],
    debut: date,
    fin: date,
) -> tuple[dict[str, AgregatJournalier], int]:
    """Agrege en journalier la serie d'un point pour UN fichier (une annee civile
    au plus, donc aucun jour a cheval sur deux fichiers) : seules les valeurs
    journalieres sont conservees, pas les pas 3-horaires.

    Returns:
        ``({grandeur: AgregatJournalier}, nb_valeurs_non_finies_ecartees)``.
    """
    par_jour, ecartees = regrouper_par_jour(instants, valeurs)
    jours = calendrier(debut, fin)
    return {
        grandeur: agreger_journalier(par_jour, heures, jours, conversion)
        for grandeur, heures, conversion in REGLES_PAR_VARIABLE[var_nc]
    }, ecartees


def verifier_fourchette(grandeur: str, localite: str, valeurs: Mapping[str, float]) -> None:
    """Echoue sur toute valeur hors fourchette physique (aucune borne silencieuse)."""
    bas, haut = FOURCHETTES[grandeur]
    hors = [(j, v) for j, v in sorted(valeurs.items()) if not bas <= v <= haut]
    if hors:
        raise RuntimeError(
            f"{localite}/{grandeur} : {len(hors)} valeur(s) hors [{bas}, {haut}], "
            f"premieres : {hors[:5]}"
        )


def arrondir(grandeur: str, valeurs: Mapping[str, float]) -> dict[str, float]:
    return {j: round(v, DECIMALES[grandeur]) for j, v in sorted(valeurs.items())}


def liste_tronquee(dates: Sequence[str], maximum: int = 500) -> dict[str, Any]:
    """Liste de dates pour la tracabilite : compte, ``maximum`` premieres, troncature."""
    triees = sorted(dates)
    return {"nombre": len(triees), "dates": triees[:maximum], "tronquee": len(triees) > maximum}


# === Extraction au pixel ===================================================


def _pixel_et_serie(ds: Any, var_nc: str, lat: float, lon: float) -> tuple[float, float, Any]:
    """Pixel le plus proche (pas de repli terrestre : EAC4 couvre l'ocean) et sa
    serie temporelle 1-D. Echoue si la serie n'est pas 1-D en temps ou si le pixel
    est a plus d'une demi-maille du point (longitudes 0-360, grille inattendue)."""
    for nom in ("latitude", "longitude"):
        if nom not in ds.coords:
            raise RuntimeError(f"Coordonnee {nom!r} absente. Coordonnees : {list(ds.coords)}.")
    pt = ds[var_nc].sel(latitude=lat, longitude=lon, method="nearest")
    plat, plon = float(pt["latitude"]), float(pt["longitude"])
    demi = PAS_GRILLE_DEG / 2 + 1e-6
    if abs(plat - lat) > demi or abs(plon - lon) > demi:
        raise RuntimeError(f"Pixel ({plat}, {plon}) a plus d'une demi-maille de ({lat}, {lon}).")
    if pt.ndim != 1:
        raise RuntimeError(f"{var_nc} au pixel n'est pas 1-D : dims {pt.dims}.")
    return plat, plon, pt


def _instants(ds: Any) -> list[str]:
    import numpy as np

    return [str(t) for t in np.atleast_1d(ds[_coord_temps(ds)].values)]


# === Ecriture des compagnons ===============================================


def ecrire_compagnon(
    dossier: Path,
    localite: str,
    pixel: tuple[float, float],
    valeurs_par_grandeur: Mapping[str, Mapping[str, float]],
    capture: Mapping[str, Any],
) -> Path:
    """Ecrit ``<prefixe><localite>.json.gz`` : ``{capture, journalier: [blocs]}``.

    Bloc : ``{localite_code, grandeur_code, pixel: {latitude, longitude},
    valeurs: {date: valeur}}``, trie par grandeur puis date.
    """
    blocs = [
        {
            "localite_code": localite,
            "grandeur_code": grandeur,
            "pixel": {"latitude": pixel[0], "longitude": pixel[1]},
            "valeurs": dict(sorted(valeurs_par_grandeur[grandeur].items())),
        }
        for grandeur in sorted(valeurs_par_grandeur)
    ]
    charge = json.dumps(
        {"capture": dict(capture), "journalier": blocs}, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    chemin = dossier / f"{PREFIXE_COMPAGNON}{localite}.json.gz"
    chemin.write_bytes(gzip.compress(charge, compresslevel=9, mtime=0))
    return chemin


def verifier_taille(chemin: Path) -> float:
    taille_ko = chemin.stat().st_size / 1024
    if taille_ko > TAILLE_MAX_COMPAGNON_KO:
        raise RuntimeError(
            f"{chemin.name} : {taille_ko:.0f} Ko > {TAILLE_MAX_COMPAGNON_KO} Ko "
            "(hook 1024 Ko) : decouper davantage avant commit."
        )
    return taille_ko


# === Modes =================================================================


def sonde() -> None:
    """Telecharge janvier 2021 pour les deux familles et affiche ce que contient
    reellement le .nc. N'ecrit aucun seed."""
    lat, lon = coordonnees_34_points()[LOCALITE_SONDE]
    for famille in FAMILLES:
        chemin = REPERTOIRE_CACHE / f"sonde_{famille}_{DEBUT_SONDE}_{FIN_SONDE}.zip"
        _telecharger(construire_requete(famille, DEBUT_SONDE, FIN_SONDE), chemin)
        ds = _ouvrir(chemin, aplatir=False)
        print(f"\n=== Sonde famille {famille} ({chemin.name}) ===")
        print(f"dims : {dict(ds.sizes)}")
        print(f"coords : {list(ds.coords)}")
        for nom in ds.coords:
            vals = ds[nom].values.reshape(-1)
            print(f"  {nom} : {vals[:4].tolist()} ... ({vals.size} valeurs)")
        for nom, var in ds.data_vars.items():
            print(
                f"variable {nom!r} : dims {var.dims}, units={var.attrs.get('units')!r}, "
                f"long_name={var.attrs.get('long_name')!r}"
            )
        instants = _instants(ds)
        print(f"pas de temps : {len(instants)} ; premiers {instants[:3]}")
        for nom in ds.coords:
            if "level" in str(nom):
                print(f"niveau ({nom}) : {ds[nom].values.reshape(-1).tolist()}")
        plat_ds = _ouvrir(chemin)
        for nom in plat_ds.data_vars:
            # Une variable inattendue (auxiliaire, non 1-D) ne doit pas interrompre
            # la sonde avant le verdict noms / unite.
            try:
                plat, plon, serie = _pixel_et_serie(plat_ds, str(nom), lat, lon)
            except Exception as exc:
                print(f"{nom} : extraction au pixel impossible ({exc})")
                continue
            print(f"{nom} au pixel {LOCALITE_SONDE} ({plat}, {plon}) : {serie.values[:8].tolist()}")
        attendues = VARIABLES_NC_ATTENDUES[famille]
        manquantes = [v for v in attendues if v not in ds.data_vars]
        print(f"noms attendus {attendues} : {'OK' if not manquantes else f'ABSENTS {manquantes}'}")
        if famille == FAMILLE_OZONE and VAR_NC_OZONE in ds.data_vars:
            unite = ds[VAR_NC_OZONE].attrs.get("units")
            ok = unite is not None and unite_est_rapport_massique(unite)
            print(f"unite ozone {unite!r} : {'rapport massique OK' if ok else 'A EXAMINER'}")
        ds.close()
    print("\nSonde terminee : aucun seed ecrit.")


def capture_complete(debut: date, fin: date) -> None:
    coords = coordonnees_34_points()
    verifier_emprise(coords)
    # Seules les valeurs journalieres sont conservees, fichier par fichier.
    agregats: dict[str, dict[str, AgregatJournalier]] = {
        code: {g: AgregatJournalier() for g in GRANDEURS} for code in coords
    }
    pixels: dict[str, tuple[float, float]] = {}
    ecartees: dict[str, dict[str, int]] = {code: {} for code in coords}

    for d, f in intervalles_annuels(debut, fin):
        for famille in FAMILLES:
            chemin = REPERTOIRE_CACHE / f"{famille}_{d}_{f}.zip"
            _telecharger(construire_requete(famille, d, f), chemin)
            ds = _ouvrir(chemin)
            verifier_variables_nc(ds.data_vars, VARIABLES_NC_ATTENDUES[famille])
            if famille == FAMILLE_OZONE:
                verifier_unite_ozone(ds[VAR_NC_OZONE].attrs.get("units"))
            instants = _instants(ds)
            for code, (lat, lon) in coords.items():
                for var_nc in VARIABLES_NC_ATTENDUES[famille]:
                    plat, plon, serie = _pixel_et_serie(ds, var_nc, lat, lon)
                    if pixels.setdefault(code, (plat, plon)) != (plat, plon):
                        raise RuntimeError(f"{code} : pixel instable {pixels[code]} / {plat, plon}")
                    par_grandeur, n = agreger_annee(var_nc, instants, serie.values.tolist(), d, f)
                    ecartees[code][var_nc] = ecartees[code].get(var_nc, 0) + n
                    for grandeur, agregat in par_grandeur.items():
                        agregats[code][grandeur].fusionner(agregat)
            ds.close()
            print(f"  {famille} {d}..{f} : {len(instants)} pas")

    date_capture = date.today().isoformat()
    for code in sorted(coords):
        par_grandeur = agregats[code]
        for grandeur, agregat in par_grandeur.items():
            verifier_fourchette(grandeur, code, agregat.valeurs)
        valeurs = {g: arrondir(g, a.valeurs) for g, a in par_grandeur.items()}
        jours = sorted({j for v in valeurs.values() for j in v})
        if not jours:
            raise RuntimeError(f"{code} : aucune valeur journaliere capturee.")
        capture = {
            "dataset": DATASET_EAC4,
            "date_capture": date_capture,
            "periode_demandee": {"debut": debut.isoformat(), "fin": fin.isoformat()},
            "periode_reelle": {"debut": jours[0], "fin": jours[-1]},
            "jours_incomplets": {
                g: liste_tronquee(a.jours_incomplets) for g, a in sorted(par_grandeur.items())
            },
            "jours_absents": {
                g: liste_tronquee(a.jours_absents) for g, a in sorted(par_grandeur.items())
            },
            "valeurs_non_finies_ecartees": dict(sorted(ecartees[code].items())),
            "niveau_modele_ozone": NIVEAU_MODELE_OZONE,
            "conversion_ozone": (
                f"kg/kg x ({MASSE_MOLAIRE_AIR_G_MOL}/{MASSE_MOLAIRE_O3_G_MOL}) x 1e9 -> ppb"
            ),
            "attribution": (
                "Generated using Copernicus Atmosphere Monitoring Service Information "
                f"{date_capture[:4]} (licence CC-BY)"
            ),
        }
        chemin = ecrire_compagnon(DOSSIER_SEED, code, pixels[code], valeurs, capture)
        taille = verifier_taille(chemin)
        resume = {
            g: (len(a.jours_incomplets), len(a.jours_absents)) for g, a in par_grandeur.items()
        }
        print(
            f"  {code} : {jours[0]}..{jours[-1]}, (incomplets, absents) {resume}, {taille:.0f} Ko"
        )


def verifier_fin(mois: str) -> None:
    """Demande UN jour (le 1er de ``mois``, famille AOD) pour savoir si le mois est
    disponible a l'ADS. Affiche « disponible » ou l'erreur ADS ; aucun seed."""
    jour = date.fromisoformat(f"{mois}-01")
    chemin = REPERTOIRE_CACHE / f"verifier_fin_{FAMILLE_AOD}_{jour}.zip"
    try:
        _telecharger(construire_requete(FAMILLE_AOD, jour, jour), chemin)
    except Exception as exc:
        print(f"{mois} : non disponible ou requete refusee par l'ADS : {exc}")
        return
    print(f"{mois} : disponible ({jour} telecharge dans {chemin}).")


def _date(texte: str) -> date:
    return date.fromisoformat(texte)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed offline EAC4 AOD 550 nm et ozone de surface, 34 points."
    )
    parser.add_argument("--sonde", action="store_true", help="Sonde janvier 2021, aucun seed.")
    parser.add_argument("--debut", type=_date, default=DEBUT_DEFAUT, help="AAAA-MM-JJ")
    parser.add_argument(
        "--fin",
        type=_date,
        default=None,
        help="AAAA-MM-JJ, dernier jour du dernier mois EAC4 disponible (obligatoire hors sonde).",
    )
    parser.add_argument(
        "--verifier-fin",
        metavar="AAAA-MM",
        default=None,
        help="Demande le 1er jour du mois (AOD) pour tester sa disponibilite, aucun seed.",
    )
    args = parser.parse_args()
    if args.verifier_fin is not None:
        verifier_fin(args.verifier_fin)
        return
    if args.sonde:
        sonde()
        return
    if args.fin is None:
        parser.error("--fin est obligatoire : la fin de disponibilite EAC4 n'est pas connue ici.")
    if args.fin >= date.today() - timedelta(days=1):
        parser.error("--fin doit etre dans le passe.")
    capture_complete(args.debut, args.fin)


if __name__ == "__main__":
    main()

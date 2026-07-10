"""Génère `pspNormales_par_unite.json` pour le pack Kuma PV v1.1 (WP8).

Livrable **hors CI** : lit les séries NASA POWER daily GHI + T2M disponibles pour
les 34 unités du pack (33 préfectures + Conakry), applique la fonction pure
`calculer_productible_specifique_pr_std_thermique_mensuel` sur la fenêtre
commune, et sort un JSON prêt à intégrer dans le pipeline pack.

Voie 2 (WP8, décidée le 2026-07-10) : correction thermique jour par jour, mais
fenêtre courte 2021-2024 (couverture NASA POWER daily disponible côté KDC).
Le calage sur normales 1991-2020 est différé (WP9 « ingestion daily 30 ans »).
La provenance JSON déclare la fenêtre effective utilisée, sans occulter.

Coefficients scellés utilisés (méthode v1.1) :
- PR_STD = 0.78975  (rend_onduleur * rend_mppt * (1 - pertes_diverses_pct/100))
- NOCT = 45.0 °C
- coeff_temp = -0.4 %/°C

Usage :
    uv run --group dev python scripts/generer_psp_pr_std_thermique_34_unites.py \\
        --sortie ./sortie/psp_normales_pr_std_thermique.json \\
        [--date-debut 2021-01-01] [--date-fin 2024-12-31]

Le script échoue **explicitement** si une unité du pack n'a pas ses deux séries
NASA POWER (GHI et T2M) sur la fenêtre demandée : c'est un gate volontaire, on
préfère un pack v1.1 non émis à un pack v1.1 avec des unités partielles.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from kuma_data_core.db.session import get_engine
from kuma_data_core.services.grandeurs.productible_specifique_pr_std_thermique import (
    MesureJourGhiTamb,
    calculer_productible_specifique_pr_std_thermique_mensuel,
)

# === Constantes méthode v1.1 (scellées) ===================================

PR_STD: float = 0.78975
NOCT_DEGC: float = 45.0
COEFF_TEMP_PCT_PAR_DEGC: float = -0.4
COEFFICIENTS_VERSION: str = "methode-v1.1"

# === Unités du pack (34 codes exposés à l'app) ============================

CODES_UNITES_PACK: tuple[str, ...] = (
    "gin_beyla", "gin_boffa", "gin_boke", "gin_conakry", "gin_coyah",
    "gin_dabola", "gin_dalaba", "gin_dinguiraye", "gin_dubreka", "gin_faranah",
    "gin_forecariah", "gin_fria", "gin_gaoual", "gin_gueckedou", "gin_kankan",
    "gin_kerouane", "gin_kindia", "gin_kissidougou", "gin_koubia", "gin_koundara",
    "gin_kouroussa", "gin_labe", "gin_lelouma", "gin_lola", "gin_macenta",
    "gin_mali", "gin_mamou", "gin_mandiana", "gin_nzerekore", "gin_pita",
    "gin_siguiri", "gin_telimele", "gin_tougue", "gin_yomou",
)

# Le pack expose `gin_boke` et `gin_faranah`, mais côté KDC les communes chef-lieu
# nouvelles portent les codes `gin_boke_centre` et `gin_faranah_centre` (migration
# 085). Alias : quand on résout la série côté base, on cherche les deux codes.
ALIAS_CODE_PACK_VERS_KDC: dict[str, tuple[str, ...]] = {
    "gin_boke": ("gin_boke", "gin_boke_centre"),
    "gin_faranah": ("gin_faranah", "gin_faranah_centre"),
}


# === Résolution des séries ================================================


def _codes_kdc_pour_unite(code_pack: str) -> tuple[str, ...]:
    return ALIAS_CODE_PACK_VERS_KDC.get(code_pack, (code_pack,))


def resoudre_serie_id(
    session: Session, code_unite_kdc: str, grandeur_code: str, source_code: str = "nasa_power"
) -> int | None:
    """Retourne l'id de la série (grandeur × unité × source × granularité journalier).

    None si aucune série correspondante n'existe. Le code métier des séries suit la
    convention `<code_localite>_<grandeur>_<source>_<annee_debut>_<annee_fin>`.
    """
    q = sa.text(
        """
        SELECT sm.id
        FROM series_metadonnees sm
        JOIN localites l ON l.id = sm.localite_id
        JOIN sources s ON s.id = sm.source_id
        WHERE l.code = :code_unite
          AND sm.grandeur_code = :grandeur
          AND s.code = :source
          AND sm.granularite = 'journalier'
        ORDER BY sm.id DESC
        LIMIT 1
        """
    )
    row = session.execute(
        q,
        {"code_unite": code_unite_kdc, "grandeur": grandeur_code, "source": source_code},
    ).first()
    return int(row[0]) if row else None


def charger_mesures_journalieres(
    session: Session, serie_id: int, debut: date, fin: date
) -> dict[date, float]:
    """Retourne {instant_mesure -> valeur} pour la série sur la fenêtre demandée."""
    q = sa.text(
        """
        SELECT instant_mesure, valeur
        FROM mesures_ressource
        WHERE serie_id = :serie_id
          AND instant_mesure BETWEEN :debut AND :fin
        ORDER BY instant_mesure
        """
    )
    rows = session.execute(q, {"serie_id": serie_id, "debut": debut, "fin": fin}).all()
    return {r[0]: float(r[1]) for r in rows}


def apparier_ghi_t2m(
    ghi_par_date: dict[date, float], t2m_par_date: dict[date, float]
) -> list[MesureJourGhiTamb]:
    """Joint GHI + T2M sur les dates communes. Ordre chronologique."""
    dates_communes = sorted(set(ghi_par_date) & set(t2m_par_date))
    return [
        MesureJourGhiTamb(
            annee=d.year,
            mois=d.month,
            ghi_kwh_par_m2_jour=ghi_par_date[d],
            t_amb_degc=t2m_par_date[d],
        )
        for d in dates_communes
    ]


# === Extraction par unité =================================================


def calculer_pour_unite(
    session: Session, code_pack: str, debut: date, fin: date
) -> dict[str, Any]:
    """Assemble les 12 valeurs pspNormales pour une unité, ou lève RuntimeError.

    Retourne un dict {psp_normales, jours_couverts, fenetre_effective, ...}.
    """
    codes_kdc_candidats = _codes_kdc_pour_unite(code_pack)
    ghi_par_date: dict[date, float] = {}
    t2m_par_date: dict[date, float] = {}
    code_kdc_retenu: str | None = None

    for code_kdc in codes_kdc_candidats:
        serie_ghi = resoudre_serie_id(session, code_kdc, "ghi")
        serie_t2m = resoudre_serie_id(session, code_kdc, "t2m")
        if serie_ghi is not None and serie_t2m is not None:
            ghi_par_date = charger_mesures_journalieres(session, serie_ghi, debut, fin)
            t2m_par_date = charger_mesures_journalieres(session, serie_t2m, debut, fin)
            code_kdc_retenu = code_kdc
            break

    if code_kdc_retenu is None:
        raise RuntimeError(
            f"unite {code_pack} : aucune serie NASA POWER daily journaliere "
            f"trouvee (essaye : {codes_kdc_candidats}). Voie 2 non applicable "
            f"pour cette unite -> pack v1.1 non emis."
        )

    mesures = apparier_ghi_t2m(ghi_par_date, t2m_par_date)
    if not mesures:
        raise RuntimeError(
            f"unite {code_pack} : serie(s) presente(s) mais aucune date commune "
            f"GHI/T2M sur {debut} -> {fin}."
        )

    psp_normales = calculer_productible_specifique_pr_std_thermique_mensuel(
        mesures=mesures,
        pr_std=PR_STD,
        noct_degc=NOCT_DEGC,
        coeff_temp_pct_par_degc=COEFF_TEMP_PCT_PAR_DEGC,
    )

    dates_utilisees = [(m["annee"], m["mois"]) for m in mesures]
    return {
        "psp_normales_kwh_par_kwc": psp_normales,
        "psp_annuel_kwh_par_kwc": sum(psp_normales),
        "code_kdc_source": code_kdc_retenu,
        "nb_jours_utilises": len(mesures),
        "annee_min": min(a for a, _ in dates_utilisees),
        "annee_max": max(a for a, _ in dates_utilisees),
    }


# === Point d'entrée =======================================================


def executer(sortie: Path, debut: date, fin: date) -> None:
    engine = get_engine()
    par_unite: dict[str, Any] = {}
    erreurs: list[str] = []
    with Session(engine) as session:
        for code_pack in CODES_UNITES_PACK:
            try:
                par_unite[code_pack] = calculer_pour_unite(session, code_pack, debut, fin)
                print(
                    f"OK  {code_pack}  annuel = "
                    f"{par_unite[code_pack]['psp_annuel_kwh_par_kwc']:.1f} kWh/kWc  "
                    f"(n={par_unite[code_pack]['nb_jours_utilises']} j)"
                )
            except RuntimeError as exc:
                erreurs.append(str(exc))
                print(f"KO  {code_pack} : {exc}")

    if erreurs:
        raise SystemExit(
            f"\n{len(erreurs)} unite(s) sans serie utilisable. Pack v1.1 non emis. "
            f"Voir logs ci-dessus."
        )

    provenance = {
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "grandeur": "productible_specifique_pr_std_thermique_mensuel",
        "methode": {
            "coefficients_version": COEFFICIENTS_VERSION,
            "pr_std": PR_STD,
            "noct_degc": NOCT_DEGC,
            "coeff_temp_pct_par_degc": COEFF_TEMP_PCT_PAR_DEGC,
        },
        "fenetre_demandee": {"debut": debut.isoformat(), "fin": fin.isoformat()},
        "source_donnees": "NASA POWER daily (grandeurs ghi + t2m), granularite journaliere",
        "dette_technique": (
            "Fenetre 2021-2024 (Voie 2 WP8) au lieu de 1991-2020 : le KDC n'a pas encore "
            "de series NASA POWER daily 1991-2020 pour les 34 unites. Le calage sur "
            "normales 30 ans est differé au WP9 (ingestion daily 30 ans)."
        ),
    }

    contenu = {"_provenance": provenance, "psp_par_unite": par_unite}
    payload = json.dumps(contenu, ensure_ascii=False, indent=2, sort_keys=True)
    provenance["hash_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    # Ecriture finale avec hash inclus
    contenu["_provenance"] = provenance
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(
        json.dumps(contenu, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"\nOK  {sortie}  ({len(par_unite)} unites)")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sortie", type=Path, required=True)
    p.add_argument("--date-debut", type=date.fromisoformat, default=date(2021, 1, 1))
    p.add_argument("--date-fin", type=date.fromisoformat, default=date(2024, 12, 31))
    args = p.parse_args()
    executer(args.sortie, args.date_debut, args.date_fin)


if __name__ == "__main__":
    main()

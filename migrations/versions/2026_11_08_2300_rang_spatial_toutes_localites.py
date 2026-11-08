"""rang_spatial_toutes_localites

Revision ID: 133
Revises: 132
Create Date: 2026-11-08 23:00:00.000000+00:00

``rang_referentiel_spatial`` classe desormais chaque mois toutes les
localites couvertes (34) au lieu des six localites de la version 1 (Kaloum,
Kankan, Kindia, Labé, Mamou, Nzérékoré) : rang 1 a 34 par moyenne mensuelle
croissante du GHI NASA POWER journalier, 2021-2025.

Changement de valeur et de sens, donc nouvelle version et non correction en
place :

1. ``grandeurs_referentiel.version_formule_actuelle`` passe de 1 a 2 : le pool
   classe fait partie de la definition du rang (un rang 6 sur 6 et un rang 6
   sur 34 ne disent pas la meme chose). ``v_grandeurs_metier_courantes`` et
   ``/v1/series`` ne servent plus que la version 2.
2. Les 360 lignes de la version 1 sont closes et restent en base pour
   l'historique ; les requetes qui ne filtrent que ``valide_au IS NULL`` ne
   les voient plus. Comme ``editorial.versioning`` : un seul instant ferme
   l'ancienne ligne (``valide_au``, ``modifie_le``) et date la nouvelle
   (``valide_du``, ``cree_le``, ``modifie_le``).
3. 28 series ``<prefixe>_rang_referentiel_spatial_kuma_calculs_2021_2025``
   sont creees pour les localites qui n'en avaient pas, aux conventions des
   six existantes (source ``kuma_calculs``, ``calcul_derive``, 2021-2025,
   libelle ``rang_referentiel_spatial mensuel <localites.nom> 2021-2025``).
4. 34 x 60 = 2 040 lignes version 2, confiance B, calculees hors ligne par
   ``calculer_et_inserer_rang_spatial`` depuis les mesures journalieres en
   base. Un mois n'est classe que si les 34 localites ont une valeur (regle
   de la version 1) ; les 60 mois sont complets.

Ex-aequo : 8 groupes de localites (20 localites) lisent la meme cellule de
la grille NASA POWER et ont des valeurs identiques chaque mois. Le calcul les
departage, comme la version 1, par l'ordre d'entree, ici l'ordre des codes de
localite : rangs consecutifs, ordre relatif arbitraire. La description de la
grandeur le dit et la note publique de chaque serie concernee nomme ses
localites jumelles. Les groupes sont verifies sur la donnee avant ecriture.

Textes (correction editoriale en place, ``modifie_le`` inchange) : description
de la grandeur, et pour les six series existantes libelle (``Kaloum``,
``Labé``, ``Nzérékoré``), note publique et commentaire interne. Chaque texte
de depart est attendu exact.

Downgrade : supprime les 2 040 lignes version 2 et les 28 series, rouvre les
360 lignes version 1 (``valide_au`` NULL, ``modifie_le`` = ``cree_le``,
leur valeur a l'upgrade ; rangs 1 a 6 verifies), restaure textes et version 1.
Aucun reseau.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.services.grandeurs.referentiels import (
    GRANDEUR_RANG_SPATIAL,
    ContexteRangSpatial,
    _lire_kuma_mensuel,
    calculer_et_inserer_rang_spatial,
)

# revision identifiers, used by Alembic.
revision: str = "133"
down_revision: str | Sequence[str] | None = "132"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VERSION_AVANT = 1
_VERSION_APRES = 2
_N_LOCALITES = 34
_AN_DEBUT, _AN_FIN = 2021, 2025
_N_MOIS = (_AN_FIN - _AN_DEBUT + 1) * 12
_N_LIGNES_AVANT = 6 * _N_MOIS
_N_LIGNES_APRES = _N_LOCALITES * _N_MOIS
_SUFFIXE_GHI = "_ghi_nasa_power_2021_2025"
_SUFFIXE_RANG = "_rang_referentiel_spatial_kuma_calculs_2021_2025"

# Six series existantes : code de localite -> graphie du libelle et du commentaire de depart.
_EXISTANTES: dict[str, str] = {
    "gin_conakry_kaloum": "Conakry-Kaloum",
    "gin_kankan": "Kankan",
    "gin_kindia": "Kindia",
    "gin_labe": "Labe",
    "gin_mamou": "Mamou",
    "gin_nzerekore": "Nzerekore",
}

# Localites lisant la meme cellule NASA POWER (valeurs identiques), verifie sur la donnee.
_GROUPES_EGAUX: tuple[tuple[str, ...], ...] = (
    ("gin_boffa", "gin_boke_centre"),
    ("gin_conakry_kaloum", "gin_coyah", "gin_dubreka", "gin_forecariah"),
    ("gin_dalaba", "gin_kindia", "gin_mamou"),
    ("gin_fria", "gin_telimele"),
    ("gin_kankan", "gin_kouroussa"),
    ("gin_koubia", "gin_tougue"),
    ("gin_labe", "gin_lelouma", "gin_pita"),
    ("gin_lola", "gin_nzerekore"),
)

# === Textes =================================================================

_DESCRIPTION_AVANT = (
    "Rang d'une ville parmi les six villes pilotes (Kaloum à Conakry, Kankan, Kindia, Labé, "
    "Mamou, Nzérékoré) pour un même mois, de 1 à 6. Kuma classe les six villes par ordre "
    "croissant de la moyenne mensuelle de l'irradiation globale horizontale (GHI) NASA POWER, "
    "calculée à partir des valeurs journalières : 1 = irradiation la plus faible du mois, "
    "6 = la plus forte. Un mois n'est classé que si les six villes ont une valeur. Kindia et "
    "Mamou lisent la même cellule de la grille NASA POWER et ont des valeurs identiques : leur "
    "ordre relatif est arbitraire. Repère sans unité, pas une mesure physique. Niveau de "
    "confiance B : classement sur six villes seulement."
)
_DESCRIPTION_APRES = (
    "Rang d'une localité parmi toutes les localités couvertes pour un même mois, de 1 au "
    "nombre de localités classées. Kuma classe les localités par ordre croissant de la "
    "moyenne mensuelle de l'irradiation globale horizontale (GHI) NASA POWER, calculée à "
    "partir des valeurs journalières : 1 = irradiation la plus faible du mois. Un mois n'est "
    "classé que si toutes les localités ont une valeur. Des localités voisines lisent la même "
    "cellule de la grille NASA POWER et ont des valeurs identiques : elles reçoivent des rangs "
    "consécutifs dans un ordre arbitraire, et la note de chacune de leurs séries les nomme. "
    "Repère sans unité, pas une mesure physique. Niveau de confiance B : classement de données "
    "de modèle satellitaire, non validées au sol, dont la grille ne distingue pas toutes les "
    "localités."
)

_NOTE_AVANT = (
    "Série Rang spatial dans le perimetre Kuma pour {nom}, 2021-2025. Position relative de la "
    "localité parmi les six villes pilotes du programme initial, calculée par Kuma à partir "
    "des séries GHI : un repère sans unité, pas une mesure physique. Niveau de confiance B, "
    "hérité des intrants satellitaires ; la méthode et la formule sont versionnées dans le "
    "dépôt public du moteur."
)
_NOTE_APRES = (
    "Série Rang spatial dans le perimetre Kuma pour {nom}, 2021-2025. Position relative de la "
    "localité parmi les 34 localités couvertes, classées chaque mois de 1 (irradiation la plus "
    "faible) à 34 (la plus forte), calculée par Kuma à partir des séries GHI : un repère sans "
    "unité, pas une mesure physique.{egalite} Niveau de confiance B, hérité des intrants "
    "satellitaires ; la méthode et la formule sont versionnées dans le dépôt public du moteur."
)
_EGALITE = (
    " {nom} lit la même cellule de la grille NASA POWER que {autres} : leurs valeurs sont "
    "identiques et leurs rangs, consécutifs, sont départagés arbitrairement."
)

_COMMENTAIRE_AVANT = (
    "Serie calculee Kuma rang_referentiel_spatial : rang ordinal 1-6 dans le pool des 6 villes "
    "pilotes Kuma pour le meme mois. Niveau de confiance derive 'B' (limite statistique n=6 "
    "phase 1). Localite : {ville}. Etape 1-7b (decomposition D-39 fermee)."
)
_COMMENTAIRE_APRES = (
    "Serie calculee Kuma rang_referentiel_spatial, version de formule 2 : rang ordinal 1-34 "
    "parmi les 34 localites couvertes pour le meme mois (moyenne mensuelle du GHI NASA POWER "
    "journalier), ex-aequo departages par l'ordre des codes de localite. Niveau de confiance "
    "derive 'B'. Localite : {nom}."
)


def _echec(message: str) -> RuntimeError:
    return RuntimeError(f"Migration 133 : {message} Abandon sans ecriture partielle.")


def _libelle(nom: str) -> str:
    return f"rang_referentiel_spatial mensuel {nom} {_AN_DEBUT}-{_AN_FIN}"


def _enumerer(bind: sa.engine.Connection) -> list[sa.Row[tuple[int, str, str, str]]]:
    """Localites ayant le GHI NASA POWER journalier 2021-2025, par code."""
    rows = bind.execute(
        sa.text(
            """
            SELECT l.id, l.code, l.nom, sm.code AS code_ghi
            FROM localites l
            JOIN series_metadonnees sm ON sm.localite_id = l.id
            JOIN sources s ON s.id = sm.source_id
            WHERE s.code = 'nasa_power' AND sm.grandeur_code = 'ghi'
              AND sm.granularite = 'journalier' AND sm.code LIKE :motif
            ORDER BY l.code
            """
        ),
        {"motif": f"%{_SUFFIXE_GHI}"},
    ).all()
    if len(rows) != _N_LOCALITES or len({r.id for r in rows}) != _N_LOCALITES:
        raise _echec(f"{_N_LOCALITES} localites attendues, {len(rows)} enumerees.")
    if not set(_EXISTANTES) <= {r.code for r in rows}:
        raise _echec("une localite de la version 1 manque a l'enumeration.")
    return list(rows)


def _code_rang(code_ghi: str) -> str:
    return code_ghi.removesuffix(_SUFFIXE_GHI) + _SUFFIXE_RANG


def _textes_series(rows: Sequence[sa.Row[tuple[int, str, str, str]]]) -> dict[str, dict[str, str]]:
    """Code de serie -> textes d'arrivee (libelle, note, commentaire)."""
    noms = {r.code: r.nom for r in rows}
    jumelles: dict[str, list[str]] = {}
    for groupe in _GROUPES_EGAUX:
        for code in groupe:
            jumelles[code] = [noms[c] for c in groupe if c != code]
    textes = {}
    for r in rows:
        autres = jumelles.get(r.code, [])
        egalite = ""
        if autres:
            liste = autres[0] if len(autres) == 1 else ", ".join(autres[:-1]) + " et " + autres[-1]
            egalite = _EGALITE.format(nom=r.nom, autres=liste)
        textes[_code_rang(r.code_ghi)] = {
            "libelle": _libelle(r.nom),
            "note_publique": _NOTE_APRES.format(nom=r.nom, egalite=egalite),
            "commentaire_editorial": _COMMENTAIRE_APRES.format(nom=r.nom),
        }
    return textes


def _verifier_egalites(session: Session, rows: Sequence[sa.Row[tuple[int, str, str, str]]]) -> None:
    """Chaque mois, les valeurs egales forment exactement ``_GROUPES_EGAUX``."""
    kuma = {r.code: _lire_kuma_mensuel(session, r.code_ghi) for r in rows}
    attendus = {frozenset(g) for g in _GROUPES_EGAUX}
    for annee in range(_AN_DEBUT, _AN_FIN + 1):
        for mois in range(1, 13):
            par_valeur: dict[float, set[str]] = {}
            for code, valeurs in kuma.items():
                if (annee, mois) not in valeurs:
                    raise _echec(f"{code} sans valeur en {annee}-{mois:02d}.")
                par_valeur.setdefault(valeurs[(annee, mois)], set()).add(code)
            groupes = {frozenset(c) for c in par_valeur.values() if len(c) > 1}
            if groupes != attendus:
                raise _echec(f"ex-aequo inattendus en {annee}-{mois:02d}.")


def _ecrire_textes(
    bind: sa.engine.Connection, cibles: dict[str, tuple[dict[str, str], dict[str, str]]]
) -> None:
    """``cibles`` : code -> (textes de depart, textes d'arrivee), departs exacts."""
    for code, (depart, arrivee) in cibles.items():
        resultat = bind.execute(
            sa.text(
                """
                UPDATE series_metadonnees
                SET libelle = :l_a, note_publique = :n_a, commentaire_editorial = :c_a
                WHERE code = :code AND grandeur_code = :g
                  AND libelle = :l_d AND note_publique = :n_d AND commentaire_editorial = :c_d
                """
            ),
            {
                "code": code,
                "g": GRANDEUR_RANG_SPATIAL,
                "l_a": arrivee["libelle"],
                "n_a": arrivee["note_publique"],
                "c_a": arrivee["commentaire_editorial"],
                "l_d": depart["libelle"],
                "n_d": depart["note_publique"],
                "c_d": depart["commentaire_editorial"],
            },
        )
        if resultat.rowcount != 1:
            raise _echec(f"{code} : textes de depart non conformes.")


def _textes_avant(rows: Sequence[sa.Row[tuple[int, str, str, str]]]) -> dict[str, dict[str, str]]:
    return {
        _code_rang(r.code_ghi): {
            "libelle": _libelle(_EXISTANTES[r.code]),
            "note_publique": _NOTE_AVANT.format(nom=r.nom),
            "commentaire_editorial": _COMMENTAIRE_AVANT.format(ville=_EXISTANTES[r.code]),
        }
        for r in rows
        if r.code in _EXISTANTES
    }


def _changer_referentiel(bind: sa.engine.Connection, *, sens: int) -> None:
    v_d, v_a = (_VERSION_AVANT, _VERSION_APRES) if sens == 1 else (_VERSION_APRES, _VERSION_AVANT)
    d_d, d_a = (
        (_DESCRIPTION_AVANT, _DESCRIPTION_APRES)
        if sens == 1
        else (_DESCRIPTION_APRES, _DESCRIPTION_AVANT)
    )
    resultat = bind.execute(
        sa.text(
            """
            UPDATE grandeurs_referentiel SET version_formule_actuelle = :v_a, description = :d_a
            WHERE code = :g AND version_formule_actuelle = :v_d AND description = :d_d
            """
        ),
        {"g": GRANDEUR_RANG_SPATIAL, "v_a": v_a, "v_d": v_d, "d_a": d_a, "d_d": d_d},
    )
    if resultat.rowcount != 1:
        raise _echec("grandeurs_referentiel : version ou description de depart non conforme.")


def _compter(bind: sa.engine.Connection, where: str) -> int:
    return int(
        bind.execute(
            sa.text(f"SELECT count(*) FROM grandeurs_metier WHERE grandeur_code = :g AND {where}"),
            {"g": GRANDEUR_RANG_SPATIAL},
        ).scalar_one()
    )


def _verifier_permutations(bind: sa.engine.Connection) -> None:
    """Chaque mois courant : 34 lignes, une par localite, rangs 1..34 chacun une fois."""
    ecarts = bind.execute(
        sa.text(
            """
            SELECT count(*) FROM (
                SELECT annee_debut, mois
                FROM grandeurs_metier
                WHERE grandeur_code = :g AND valide_au IS NULL
                GROUP BY annee_debut, mois
                HAVING count(*) <> :n OR count(DISTINCT localite_id) <> :n
                    OR count(DISTINCT valeur) <> :n OR min(valeur) <> 1 OR max(valeur) <> :n
                    OR bool_or(valeur <> trunc(valeur))
            ) m
            """
        ),
        {"g": GRANDEUR_RANG_SPATIAL, "n": _N_LOCALITES},
    ).scalar_one()
    mois = bind.execute(
        sa.text(
            "SELECT count(DISTINCT (annee_debut, mois)) FROM grandeurs_metier "
            "WHERE grandeur_code = :g AND valide_au IS NULL"
        ),
        {"g": GRANDEUR_RANG_SPATIAL},
    ).scalar_one()
    if ecarts != 0 or mois != _N_MOIS:
        raise _echec(f"{ecarts} mois non permutation 1..{_N_LOCALITES}, {mois} mois classes.")


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        rows = _enumerer(bind)
        _verifier_egalites(session, rows)

        if (
            _compter(bind, "TRUE") != _N_LIGNES_AVANT
            or _compter(
                bind,
                f"valide_au IS NULL AND version_formule = {_VERSION_AVANT} "
                "AND modifie_le = cree_le",
            )
            != _N_LIGNES_AVANT
        ):
            raise _echec(f"{_N_LIGNES_AVANT} lignes version 1 courantes attendues.")

        source_id = int(
            bind.execute(sa.text("SELECT id FROM sources WHERE code = 'kuma_calculs'")).scalar_one()
        )
        textes = _textes_series(rows)
        nouvelles = [r for r in rows if r.code not in _EXISTANTES]
        deja = bind.execute(
            sa.text(
                "SELECT count(*) FROM series_metadonnees "
                "WHERE code = ANY(:c) OR (libelle = ANY(:l) AND NOT code = ANY(:e))"
            ),
            {
                "c": [_code_rang(r.code_ghi) for r in nouvelles],
                "l": [t["libelle"] for t in textes.values()],
                "e": list(textes),
            },
        ).scalar_one()
        if deja != 0:
            raise _echec(f"{deja} serie(s) ou libelle(s) d'arrivee deja pris.")

        # 1. Textes des six series existantes, puis les 28 series manquantes.
        avant = _textes_avant(rows)
        _ecrire_textes(bind, {code: (avant[code], textes[code]) for code in avant})
        for r in nouvelles:
            code = _code_rang(r.code_ghi)
            bind.execute(
                sa.text(
                    """
                    INSERT INTO series_metadonnees
                        (code, libelle, localite_id, grandeur_code, source_id, periode_debut,
                         periode_fin, methode_collecte, commentaire_editorial, note_publique)
                    VALUES (:code, :libelle, :loc, :g, :src, :pd, :pf, 'calcul_derive',
                            :comm, :note)
                    """
                ),
                {
                    "code": code,
                    "libelle": textes[code]["libelle"],
                    "loc": r.id,
                    "g": GRANDEUR_RANG_SPATIAL,
                    "src": source_id,
                    "pd": date(_AN_DEBUT, 1, 1),
                    "pf": date(_AN_FIN, 12, 31),
                    "comm": textes[code]["commentaire_editorial"],
                    "note": textes[code]["note_publique"],
                },
            )

        # 2. Nouvelle version de formule et description.
        _changer_referentiel(bind, sens=1)

        # 3. Cloture de la version 1, puis calcul de la version 2, au meme instant.
        # clock_timestamp() et non now() : une construction a neuf enchaine toutes les
        # migrations dans une transaction, ou now() vaut le valide_du des lignes v1.
        instant = bind.execute(
            sa.text(
                "SELECT c.t AS debut, c.t > max(gm.valide_du) AS apres "
                "FROM (SELECT clock_timestamp() AS t) c, grandeurs_metier gm "
                "WHERE gm.grandeur_code = :g GROUP BY c.t"
            ),
            {"g": GRANDEUR_RANG_SPATIAL},
        ).one()
        if not instant.apres:
            raise _echec("instant de cloture non posterieur aux lignes version 1.")
        closes = bind.execute(
            sa.text(
                """
                UPDATE grandeurs_metier SET valide_au = :t, modifie_le = :t
                WHERE grandeur_code = :g AND version_formule = :v AND valide_au IS NULL
                """
            ),
            {"g": GRANDEUR_RANG_SPATIAL, "v": _VERSION_AVANT, "t": instant.debut},
        ).rowcount
        if closes != _N_LIGNES_AVANT:
            raise _echec(f"{closes} ligne(s) version 1 close(s) au lieu de {_N_LIGNES_AVANT}.")

        serie_id = dict(
            bind.execute(
                sa.text(
                    "SELECT localite_id, id FROM series_metadonnees "
                    "WHERE grandeur_code = :g AND code = ANY(:c)"
                ),
                {"g": GRANDEUR_RANG_SPATIAL, "c": list(textes)},
            ).all()
        )
        if len(serie_id) != _N_LOCALITES:
            raise _echec(f"{len(serie_id)} series de rang resolues au lieu de {_N_LOCALITES}.")
        contextes: list[ContexteRangSpatial] = [
            {
                "localite_id": r.id,
                "code_serie_kuma_daily": r.code_ghi,
                "series_metadonnees_id": int(serie_id[r.id]),
            }
            for r in rows
        ]
        n, non_classes = calculer_et_inserer_rang_spatial(
            session=session,
            contextes=contextes,
            version_formule=_VERSION_APRES,
            valide_du=instant.debut,
        )
        if non_classes or n != _N_LIGNES_APRES:
            raise _echec(f"{n} lignes inserees, mois non classes : {non_classes}.")

        # 4. Gardes finales.
        if (
            _compter(bind, "valide_au IS NULL") != _N_LIGNES_APRES
            or _compter(bind, f"valide_au IS NULL AND version_formule = {_VERSION_APRES}")
            != _N_LIGNES_APRES
        ):
            raise _echec("lignes courantes hors version 2.")
        _verifier_permutations(bind)
        pilotes = bind.execute(
            sa.text(
                """
                SELECT (SELECT count(*) FROM series_metadonnees WHERE grandeur_code = :g
                        AND (note_publique ~* 'pilote' OR libelle ~* 'pilote'))
                     + (SELECT count(*) FROM grandeurs_referentiel WHERE code = :g
                        AND description ~* 'pilote')
                """
            ),
            {"g": GRANDEUR_RANG_SPATIAL},
        ).scalar_one()
        doublons = bind.execute(
            sa.text("SELECT count(*) - count(DISTINCT libelle) FROM series_metadonnees")
        ).scalar_one()
        if pilotes != 0 or doublons != 0:
            raise _echec(f"{pilotes} texte(s) « pilote », {doublons} libelle(s) en double.")
    finally:
        session.close()


def downgrade() -> None:
    bind = op.get_bind()
    rows = _enumerer(bind)
    textes = _textes_series(rows)
    nouvelles = [_code_rang(r.code_ghi) for r in rows if r.code not in _EXISTANTES]

    if (
        _compter(bind, f"valide_au IS NULL AND version_formule = {_VERSION_APRES}")
        != (_N_LIGNES_APRES)
        or _compter(bind, "TRUE") != _N_LIGNES_APRES + _N_LIGNES_AVANT
    ):
        raise _echec("etat version 2 inattendu.")
    if (
        _compter(
            bind,
            f"version_formule = {_VERSION_AVANT} AND valide_au IS NOT NULL "
            "AND valeur BETWEEN 1 AND 6",
        )
        != _N_LIGNES_AVANT
    ):
        raise _echec(f"{_N_LIGNES_AVANT} lignes version 1 closes attendues.")

    supprimees = bind.execute(
        sa.text("DELETE FROM grandeurs_metier WHERE grandeur_code = :g AND version_formule = :v"),
        {"g": GRANDEUR_RANG_SPATIAL, "v": _VERSION_APRES},
    ).rowcount
    if supprimees != _N_LIGNES_APRES:
        raise _echec(f"{supprimees} ligne(s) version 2 supprimee(s).")
    rouvertes = bind.execute(
        sa.text(
            """
            UPDATE grandeurs_metier SET valide_au = NULL, modifie_le = cree_le
            WHERE grandeur_code = :g AND version_formule = :v AND valide_au IS NOT NULL
            """
        ),
        {"g": GRANDEUR_RANG_SPATIAL, "v": _VERSION_AVANT},
    ).rowcount
    if rouvertes != _N_LIGNES_AVANT:
        raise _echec(f"{rouvertes} ligne(s) version 1 rouverte(s).")

    retirees = bind.execute(
        sa.text("DELETE FROM series_metadonnees WHERE grandeur_code = :g AND code = ANY(:c)"),
        {"g": GRANDEUR_RANG_SPATIAL, "c": nouvelles},
    ).rowcount
    if retirees != _N_LOCALITES - len(_EXISTANTES):
        raise _echec(f"{retirees} serie(s) supprimee(s).")

    avant = _textes_avant(rows)
    _ecrire_textes(bind, {code: (textes[code], avant[code]) for code in avant})
    _changer_referentiel(bind, sens=0)

"""Tests d'intégration de la table ``grandeurs_metier``.

Couvre les cas de test :

- DDL, contraintes, EXCLUDE, audit.
- vue ``v_grandeurs_metier_courantes``.
- seed source ``kuma_calculs`` + 6 séries HEP.
- ingestion HEP 6 villes.
- roundtrip Alembic (marker regression).

Pattern hérité de ``test_mesures_ressource.py`` : ``db_session``
fixture conftest.py + ``session.begin_nested()`` pour isoler les tests
d'erreur sans casser la transaction extérieure.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kuma_data_core.db.models.audit_log import AuditLog
from kuma_data_core.db.models.grandeurs_metier import GrandeurMetier

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


CODES_SERIES_HEP: tuple[str, ...] = (
    "gin_conakry_hep_kuma_calculs_2021_2025",
    "gin_kindia_hep_kuma_calculs_2021_2025",
    "gin_mamou_hep_kuma_calculs_2021_2025",
    "gin_labe_hep_kuma_calculs_2021_2025",
    "gin_kankan_hep_kuma_calculs_2021_2025",
    "gin_nzerekore_hep_kuma_calculs_2021_2025",
)

# Les 6 villes pilotes. La parite A1 (migration 092) etend hep/psp/fd aux 28
# communes -> les tests de livrable pilote se scopent a ces 6 (les 28 ont leur propre
# test de densification/parite + anti-regression).
_LOCALITES_PILOTES: tuple[str, ...] = (
    "gin_conakry_kaloum",
    "gin_kankan",
    "gin_kindia",
    "gin_labe",
    "gin_mamou",
    "gin_nzerekore",
)
_SQL_IN_PILOTES = (
    "localite_id IN (SELECT id FROM localites WHERE code IN "
    "('gin_conakry_kaloum','gin_kankan','gin_kindia','gin_labe','gin_mamou','gin_nzerekore'))"
)


def _ids_pilotes(db_session: Session) -> list[int]:
    """Ids des 6 localites pilotes (pour scoper les tests de livrable pilote)."""
    return [
        r[0]
        for r in db_session.execute(
            text("SELECT id FROM localites WHERE code = ANY(:c)"),
            {"c": list(_LOCALITES_PILOTES)},
        ).all()
    ]


def _id_serie_hep_conakry(db_session: Session) -> int:
    return int(
        db_session.execute(
            text("SELECT id FROM series_metadonnees WHERE code = :code"),
            {"code": "gin_conakry_hep_kuma_calculs_2021_2025"},
        ).scalar_one()
    )


def _id_localite_conakry(db_session: Session) -> int:
    return int(
        db_session.execute(
            text("SELECT id FROM localites WHERE code = :code"),
            {"code": "gin_conakry_kaloum"},
        ).scalar_one()
    )


def _construire_ligne_hep(
    db_session: Session,
    *,
    periode_type: str = "annuel",
    annee_debut: int = 2050,
    annee_fin: int | None = None,
    mois: int | None = None,
    version_formule: int = 1,
    valeur: float = 2000.0,
    niveau_confiance_derive: str = "B",
    statut: str | None = None,
) -> GrandeurMetier:
    """Construit une instance GrandeurMetier en utilisant la série HEP Conakry
    et l'année 2050 par défaut (hors plage 2021-2025 seedée pour éviter les
    conflits EXCLUDE avec les 390 lignes existantes)."""
    kwargs: dict[str, object] = {
        "grandeur_code": "hep",
        "localite_id": _id_localite_conakry(db_session),
        "series_metadonnees_id": _id_serie_hep_conakry(db_session),
        "periode_type": periode_type,
        "annee_debut": annee_debut,
        "annee_fin": annee_fin if annee_fin is not None else annee_debut,
        "mois": mois,
        "version_formule": version_formule,
        "valeur": valeur,
        "niveau_confiance_derive": niveau_confiance_derive,
    }
    if statut is not None:
        kwargs["statut"] = statut
    return GrandeurMetier(**kwargs)


# ---------------------------------------------------------------------------
# DDL et contraintes
# ---------------------------------------------------------------------------


def test_ti1_ddl_table_colonnes_et_contraintes(db_session: Session) -> None:
    """Colonnes typées correctement, FK posées, CHECK nommés
    (suffixe `_valide` pour catégoriels), EXCLUDE et index partiel et
    trigger posés."""
    cols = db_session.execute(
        text(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'grandeurs_metier'
            ORDER BY ordinal_position
            """
        )
    ).all()
    noms = {r.column_name for r in cols}
    attendus = {
        "id",
        "grandeur_code",
        "localite_id",
        "series_metadonnees_id",
        "periode_type",
        "annee_debut",
        "annee_fin",
        "mois",
        "version_formule",
        "valeur",
        "valide_du",
        "valide_au",
        "statut",
        "niveau_confiance_derive",
        "niveau_confiance_override",
        "commentaire_editorial",
        "cree_le",
        "cree_par",
        "modifie_le",
        "modifie_par",
    }
    assert attendus.issubset(noms)

    # CHECK constraints nommés
    check_names = {
        r.conname
        for r in db_session.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'grandeurs_metier'::regclass AND contype = 'c'"
            )
        ).all()
    }
    attendus_ck = {
        "ck_grandeurs_metier_periode_type_valide",
        "ck_grandeurs_metier_periode_coherente",
        "ck_grandeurs_metier_annees_coherentes",
        "ck_grandeurs_metier_version_formule_positive",
        "ck_grandeurs_metier_statut_valide",
        "ck_grandeurs_metier_niveau_confiance_derive_valide",
        "ck_grandeurs_metier_niveau_confiance_override_valide",
        "ck_grandeurs_metier_periode_validite_coherente",
    }
    assert attendus_ck.issubset(check_names)

    # EXCLUDE constraint
    excl = db_session.execute(
        text(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'grandeurs_metier'::regclass AND contype = 'x'"
        )
    ).scalar()
    assert excl == "ex_grandeurs_metier_identite_periode"

    # Index partiel courantes
    idx = db_session.execute(
        text("SELECT indexname FROM pg_indexes WHERE indexname = :name"),
        {"name": "idx_grandeurs_metier_courantes"},
    ).scalar()
    assert idx == "idx_grandeurs_metier_courantes"

    # Trigger d'audit
    trg = db_session.execute(
        text(
            "SELECT tgname FROM pg_trigger WHERE tgrelid = 'grandeurs_metier'::regclass "
            "AND tgname = 'trg_audit_grandeurs_metier'"
        )
    ).scalar()
    assert trg == "trg_audit_grandeurs_metier"


def test_ti2_insert_valide_annuel(db_session: Session) -> None:
    """INSERT avec periode_type='annuel', mois IS NULL accepté."""
    ligne = _construire_ligne_hep(db_session, periode_type="annuel", annee_debut=2050, mois=None)
    db_session.add(ligne)
    db_session.flush()
    assert ligne.id is not None


def test_ti3_insert_valide_mensuel(db_session: Session) -> None:
    """INSERT avec periode_type='mensuel', mois ∈ [1, 12] accepté."""
    for m in (1, 6, 12):
        ligne = _construire_ligne_hep(db_session, periode_type="mensuel", annee_debut=2050, mois=m)
        db_session.add(ligne)
        db_session.flush()
        assert ligne.id is not None


def test_ti4_insert_invalide_annuel_avec_mois(db_session: Session) -> None:
    """periode_type='annuel' avec mois=3 rejeté par
    ck_grandeurs_metier_periode_coherente."""
    with db_session.begin_nested():
        ligne = _construire_ligne_hep(db_session, periode_type="annuel", annee_debut=2050, mois=3)
        db_session.add(ligne)
        with pytest.raises(IntegrityError):
            db_session.flush()


def test_ti5_insert_invalide_mensuel_sans_mois(db_session: Session) -> None:
    """periode_type='mensuel' sans mois rejeté par
    ck_grandeurs_metier_periode_coherente."""
    with db_session.begin_nested():
        ligne = _construire_ligne_hep(
            db_session, periode_type="mensuel", annee_debut=2050, mois=None
        )
        db_session.add(ligne)
        with pytest.raises(IntegrityError):
            db_session.flush()


def test_ti6_conflit_exclude_meme_identite_courante(db_session: Session) -> None:
    """Deux INSERT avec même identité métier (incluant
    version_formule) et valide_au IS NULL → second rejeté par EXCLUDE."""
    ligne_a = _construire_ligne_hep(
        db_session,
        periode_type="annuel",
        annee_debut=2050,
        mois=None,
        version_formule=1,
    )
    db_session.add(ligne_a)
    db_session.flush()

    with db_session.begin_nested():
        ligne_b = _construire_ligne_hep(
            db_session,
            periode_type="annuel",
            annee_debut=2050,
            mois=None,
            version_formule=1,
        )
        db_session.add(ligne_b)
        with pytest.raises(IntegrityError):
            db_session.flush()


def test_ti7_coexistence_v1_v2_courantes(db_session: Session) -> None:
    """INSERT v1 puis v2 même identité métier → tous deux acceptés
    (extension orthogonale : version_formule dans EXCLUDE)."""
    ligne_v1 = _construire_ligne_hep(
        db_session,
        periode_type="annuel",
        annee_debut=2050,
        mois=None,
        version_formule=1,
    )
    db_session.add(ligne_v1)
    db_session.flush()
    assert ligne_v1.id is not None

    ligne_v2 = _construire_ligne_hep(
        db_session,
        periode_type="annuel",
        annee_debut=2050,
        mois=None,
        version_formule=2,
    )
    db_session.add(ligne_v2)
    db_session.flush()
    assert ligne_v2.id is not None
    assert ligne_v2.id != ligne_v1.id


def test_ti8_server_default_statut_brut(db_session: Session) -> None:
    """INSERT sans statut explicite → statut='brut' posé par défaut."""
    ligne = _construire_ligne_hep(db_session, periode_type="annuel", annee_debut=2051, mois=None)
    db_session.add(ligne)
    db_session.flush()
    db_session.refresh(ligne)
    assert ligne.statut == "brut"


def test_ti9_niveau_confiance_derive_obligatoire(db_session: Session) -> None:
    """INSERT sans niveau_confiance_derive rejeté par NOT NULL."""
    with db_session.begin_nested():
        ligne = GrandeurMetier(
            grandeur_code="hep",
            localite_id=_id_localite_conakry(db_session),
            series_metadonnees_id=_id_serie_hep_conakry(db_session),
            periode_type="annuel",
            annee_debut=2052,
            annee_fin=2052,
            mois=None,
            version_formule=1,
            valeur=2000.0,
            # niveau_confiance_derive volontairement omis
        )
        db_session.add(ligne)
        with pytest.raises(IntegrityError):
            db_session.flush()


def test_ti10_trigger_audit_declenche(db_session: Session) -> None:
    """INSERT puis lecture audit_log → entrée présente avec
    type_operation='I' et auteur_applicatif propagé via set_config."""
    db_session.execute(
        text("SELECT set_config('kuma.auteur_applicatif', :v, true)"),
        {"v": "test_ti10"},
    )

    ligne = _construire_ligne_hep(
        db_session, periode_type="annuel", annee_debut=2053, mois=None, valeur=1234.5
    )
    db_session.add(ligne)
    db_session.flush()

    audit_row = db_session.execute(
        select(AuditLog)
        .where(AuditLog.table_auditee == "grandeurs_metier")
        .where(AuditLog.type_operation == "I")
        .where(AuditLog.id_ligne_auditee == str(ligne.id))
    ).scalar_one()
    assert audit_row.auteur_applicatif == "test_ti10"


# ---------------------------------------------------------------------------
# Vue v_grandeurs_metier_courantes
# ---------------------------------------------------------------------------


def test_ti11_vue_filtre_version_courante(db_session: Session) -> None:
    """INSERT v1 puis basculement version_formule_actuelle de hep à
    2 → ligne v1 invisible dans la vue mais présente dans la table."""
    ligne_v1 = _construire_ligne_hep(
        db_session, periode_type="annuel", annee_debut=2054, mois=None, version_formule=1
    )
    db_session.add(ligne_v1)
    db_session.flush()

    # Avant bascule : visible
    visible_avant = db_session.execute(
        text("SELECT 1 FROM v_grandeurs_metier_courantes WHERE id = :id"),
        {"id": ligne_v1.id},
    ).scalar()
    assert visible_avant == 1

    # Bascule version actuelle de hep à 2
    db_session.execute(
        text("UPDATE grandeurs_referentiel SET version_formule_actuelle = 2 WHERE code = 'hep'")
    )
    db_session.flush()

    # Après bascule : invisible dans la vue, présente dans la table
    visible_apres = db_session.execute(
        text("SELECT 1 FROM v_grandeurs_metier_courantes WHERE id = :id"),
        {"id": ligne_v1.id},
    ).scalar()
    assert visible_apres is None

    presence_table = db_session.execute(
        text("SELECT 1 FROM grandeurs_metier WHERE id = :id"),
        {"id": ligne_v1.id},
    ).scalar()
    assert presence_table == 1


def test_ti12_vue_filtre_statut_deprecie(db_session: Session) -> None:
    """Ligne avec statut='deprecie' → invisible dans la vue."""
    ligne = _construire_ligne_hep(
        db_session,
        periode_type="annuel",
        annee_debut=2055,
        mois=None,
        statut="deprecie",
    )
    db_session.add(ligne)
    db_session.flush()

    visible = db_session.execute(
        text("SELECT 1 FROM v_grandeurs_metier_courantes WHERE id = :id"),
        {"id": ligne.id},
    ).scalar()
    assert visible is None


def test_ti13_vue_filtre_valide_au_non_null(db_session: Session) -> None:
    """Ligne avec valide_au posé (ligne historique) → invisible
    dans la vue."""
    ligne = _construire_ligne_hep(db_session, periode_type="annuel", annee_debut=2056, mois=None)
    db_session.add(ligne)
    db_session.flush()

    # Pose valide_au pour clôturer la ligne (simule une rotation)
    ligne.valide_au = datetime(2050, 1, 1, tzinfo=UTC)
    db_session.flush()

    visible = db_session.execute(
        text("SELECT 1 FROM v_grandeurs_metier_courantes WHERE id = :id"),
        {"id": ligne.id},
    ).scalar()
    assert visible is None


def test_ti14_niveau_effectif_via_vue(db_session: Session) -> None:
    """INSERT avec niveau_confiance_override='A' → la vue retourne
    niveau_effectif='A'. INSERT sans override → retourne niveau_confiance_derive."""
    ligne_override = _construire_ligne_hep(
        db_session,
        periode_type="annuel",
        annee_debut=2057,
        mois=None,
        niveau_confiance_derive="B",
    )
    ligne_override.niveau_confiance_override = "A"
    db_session.add(ligne_override)
    db_session.flush()

    niveau_override = db_session.execute(
        text("SELECT niveau_effectif FROM v_grandeurs_metier_courantes WHERE id = :id"),
        {"id": ligne_override.id},
    ).scalar_one()
    assert niveau_override == "A"

    ligne_simple = _construire_ligne_hep(
        db_session,
        periode_type="annuel",
        annee_debut=2058,
        mois=None,
        niveau_confiance_derive="B",
    )
    db_session.add(ligne_simple)
    db_session.flush()

    niveau_simple = db_session.execute(
        text("SELECT niveau_effectif FROM v_grandeurs_metier_courantes WHERE id = :id"),
        {"id": ligne_simple.id},
    ).scalar_one()
    assert niveau_simple == "B"


# ---------------------------------------------------------------------------
# Seed kuma_calculs + 6 séries HEP
# ---------------------------------------------------------------------------


def test_ti15_source_kuma_calculs_presente(db_session: Session) -> None:
    """Source kuma_calculs présente avec type_source='auteur_kuma'
    et fiabilite='haute'."""
    row = db_session.execute(
        text("SELECT type_source, fiabilite FROM sources WHERE code = :code"),
        {"code": "kuma_calculs"},
    ).first()
    assert row is not None
    assert row.type_source == "auteur_kuma"
    assert row.fiabilite == "haute"


def test_ti16_check_refuse_valeur_invalide(db_session: Session) -> None:
    """ck_sources_type_source_valide rejette une valeur hors des
    11 valeurs autorisées.

    L'acceptation de ``'auteur_kuma'`` est déjà validée par la présence
    de la source ``kuma_calculs``."""
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO sources (code, titre, type_source, fiabilite, langue) "
                "VALUES (:c, :t, 'valeur_invalide', 'haute', 'fr')"
            ),
            {"c": "_test_ti16_invalide", "t": "Test TI-16 invalide"},
        )
        db_session.flush()


def test_ti17_six_series_hep_presentes(db_session: Session) -> None:
    """6 entrées series_metadonnees calcul_derive sur la fenêtre
    récente 2021-2025.

    6 nouvelles series climato HEP 1991-2020 (kuma_calculs) ont ete
    ajoutees par migration 051. Le test reste cantonne a sa fenetre
    d'origine via filtre explicite sur les codes ``..._2021_2025``
    (preserve la semantique « 6 series HEP seedees »)."""
    codes_1_5 = list(CODES_SERIES_HEP)
    n = db_session.execute(
        text(
            "SELECT COUNT(*) FROM series_metadonnees "
            "WHERE grandeur_code = 'hep' AND methode_collecte = 'calcul_derive' "
            "AND code = ANY(:codes)"
        ),
        {"codes": codes_1_5},
    ).scalar_one()
    assert n == 6

    codes = {
        r.code
        for r in db_session.execute(
            text(
                "SELECT code FROM series_metadonnees "
                "WHERE grandeur_code = 'hep' AND methode_collecte = 'calcul_derive' "
                "AND code = ANY(:codes)"
            ),
            {"codes": codes_1_5},
        ).all()
    }
    assert codes == set(CODES_SERIES_HEP)


def test_ti18_commentaire_editorial_series_hep_renseigne(db_session: Session) -> None:
    """commentaire_editorial non NULL pour les 6 séries HEP
    (discipline éditoriale, pas contrainte DDL)."""
    rows = db_session.execute(
        text("SELECT code, commentaire_editorial FROM series_metadonnees WHERE code = ANY(:codes)"),
        {"codes": list(CODES_SERIES_HEP)},
    ).all()
    assert len(rows) == 6
    for r in rows:
        assert r.commentaire_editorial is not None
        assert r.commentaire_editorial.strip() != ""


# ---------------------------------------------------------------------------
# Ingestion HEP 6 villes
# ---------------------------------------------------------------------------


def test_ti19_decompte_lignes_hep(db_session: Session) -> None:
    """SELECT COUNT(*) FROM grandeurs_metier WHERE grandeur_code='hep'
    retourne 390 (6 villes * 65 = 1 annuel + 12 mensuels * 5 ans) sur la
    fenetre 2021-2025.

    Filtre explicite sur grandeur_code='hep' (la table
    `grandeurs_metier` contient désormais d'autres grandeurs Kuma).
    Restriction `annee_debut >= 2021` pour preserver la semantique
    (l'ingestion climato 1991-2020 ajoutee par migration 051 reside
    hors fenetre).
    Tolérance possible (350-390) si politique de complétude a skipé des
    périodes ; constat factuel : 390/390."""
    total = db_session.scalar(
        select(func.count())
        .select_from(GrandeurMetier)
        .where(GrandeurMetier.valide_au.is_(None))
        .where(GrandeurMetier.grandeur_code == "hep")
        .where(GrandeurMetier.annee_debut >= 2021)
        .where(GrandeurMetier.localite_id.in_(_ids_pilotes(db_session)))
    )
    assert total is not None
    assert 350 <= total <= 390
    # Constat factuel : aucun skip → 390/390 (6 pilotes ; A1 etend aux 28, scope ici)
    assert total == 390


def test_ti20_toutes_lignes_niveau_b(db_session: Session) -> None:
    """SELECT DISTINCT niveau_confiance_derive sur ``grandeurs_metier`` -> {'B'}.

    Invariant tenu **y compris** pour ``degenerescence_pixel`` : la confiance A
    reste reservee aux mesures terrain (06-api-reference-publique.md:682, deja tenue par
    le sol Kankan/Tarambaly) ; un indicateur structurel exact est B + caveat, jamais une
    remontee en A. A vit dans mesures_ressource_horaires (terrain), pas
    dans grandeurs_metier."""
    niveaux = {
        r[0]
        for r in db_session.execute(select(GrandeurMetier.niveau_confiance_derive).distinct()).all()
    }
    assert niveaux == {"B"}


def test_ti21_coherence_sum_mensuel_egale_annuel(db_session: Session) -> None:
    """Pour chaque (localite_id, annee_debut) ayant 13 entrées
    (1 annuel + 12 mensuels) sur la fenetre 2021-2025, sum(valeur mensuel)
    ≈ valeur annuel à rel=1e-9 près.

    Restriction `annee_debut >= 2021` pour preserver la semantique
    (les series climato 1991-2020 migration 051 ne sont pas verifiees
    ici, la coherence sum=annuel y est garantie nativement par
    `_calculer_hep_climato`)."""
    rows = db_session.execute(
        text(
            """
            SELECT
                gm.localite_id,
                gm.annee_debut,
                (SELECT valeur FROM grandeurs_metier
                 WHERE localite_id = gm.localite_id
                   AND grandeur_code = 'hep'
                   AND periode_type = 'annuel'
                   AND annee_debut = gm.annee_debut
                   AND valide_au IS NULL) AS valeur_annuel,
                SUM(gm.valeur) AS somme_mensuels
            FROM grandeurs_metier gm
            WHERE gm.grandeur_code = 'hep'
              AND gm.periode_type = 'mensuel'
              AND gm.valide_au IS NULL
              AND gm.annee_debut >= 2021
              AND gm.localite_id IN (SELECT id FROM localites WHERE code IN
                  ('gin_conakry_kaloum','gin_kankan','gin_kindia','gin_labe','gin_mamou','gin_nzerekore'))
            GROUP BY gm.localite_id, gm.annee_debut
            """
        )
    ).all()
    assert len(rows) == 30  # 6 villes pilotes * 5 ans (A1 etend aux 28, scope ici)
    for r in rows:
        assert r.valeur_annuel == pytest.approx(r.somme_mensuels, rel=1e-9)


def test_ti22_plage_tropicale_hep_annuel(db_session: Session) -> None:
    """Pour chaque ligne periode_type='annuel' sur la fenetre
    2021-2025, valeur entre 1700 et 2100 h_eq/an (plage resserrée
    empiriquement : observée [1727, 2060], cf. fiche méthodo).

    Restriction `annee_debut >= 2021` pour preserver la semantique
    (la plage climato 1991-2020 migration 051 reste tropicale par
    construction mais releve d'une validation distincte au moment de
    l'ingestion)."""
    rows = db_session.execute(
        select(GrandeurMetier.valeur).where(
            GrandeurMetier.periode_type == "annuel",
            GrandeurMetier.valide_au.is_(None),
            GrandeurMetier.grandeur_code == "hep",
            GrandeurMetier.annee_debut >= 2021,
            GrandeurMetier.localite_id.in_(_ids_pilotes(db_session)),
        )
    ).all()
    assert len(rows) == 30  # 6 pilotes (A1 etend aux 28, scope ici)
    for r in rows:
        assert 1700.0 <= r[0] <= 2100.0


def test_ti23_commentaire_editorial_null_a_insert_initial(db_session: Session) -> None:
    """Les lignes seedées par migration 027 ont commentaire_editorial
    IS NULL (pattern symétrique mesures_ressource).

    Exception : ``degenerescence_pixel`` porte intentionnellement un
    commentaire (groupe de jumeaux / caveat de résolution, canal d'honnêteté).
    L'invariant reste vérifié pour toutes les autres grandeurs."""
    n_non_null = db_session.scalar(
        select(func.count())
        .select_from(GrandeurMetier)
        .where(GrandeurMetier.valide_au.is_(None))
        .where(GrandeurMetier.commentaire_editorial.is_not(None))
        .where(GrandeurMetier.grandeur_code != "degenerescence_pixel")
    )
    assert n_non_null == 0


# ---------------------------------------------------------------------------
# Vérifications kt + 4 calculs Kuma + soft delete
# ---------------------------------------------------------------------------


def test_ti25_decompte_par_grandeur_1_6(db_session: Session) -> None:
    """Décompte par grandeur sur la fenetre 2021-2025.

    Décompte réel observé (78 par grandeur était par année ; sur 5 ans
    = 390 par grandeur multi-périodes, 30 pour variabilite annuel seul).

    Tolérance fraction_diffuse : 378 (1 jour DHI manquant en 2024 → 1 année
    + 1 mois skip * 6 villes = 12 lignes skip ; 390 - 12 = 378).

    Restriction `annee_debut >= 2021` pour preserver la semantique
    (les series climato 1991-2020 / 2001-2020 sur hep,
    productible_specifique_theorique, fraction_diffuse ajoutees
    par migration 051 sont volontairement exclues du decompte ici).
    """
    rows = db_session.execute(
        text(
            "SELECT grandeur_code, COUNT(*) FROM grandeurs_metier "
            "WHERE valide_au IS NULL "
            "AND grandeur_code IN ('fraction_diffuse', 'humidex', "
            "'productible_specifique_theorique', 'variabilite_journaliere') "
            "AND annee_debut >= 2021 "
            "AND localite_id IN (SELECT id FROM localites WHERE code IN "
            "('gin_conakry_kaloum','gin_kankan','gin_kindia','gin_labe',"
            "'gin_mamou','gin_nzerekore')) "
            "GROUP BY grandeur_code"
        )
    ).all()
    decompte = {r[0]: r[1] for r in rows}
    # Exact : le DHI daily est servi depuis le seed offline
    # committe (nasa_power_daily) -> deterministe. fraction_diffuse = 390 (0 skip,
    # max theorique 6 villes x 65 : le snapshot a la DHI 2021-2025 entierement
    # muree). Bornes tolerantes retirees.
    assert decompte["fraction_diffuse"] == 390
    assert decompte["humidex"] == 390
    assert decompte["productible_specifique_theorique"] == 390
    assert decompte["variabilite_journaliere"] == 30


def test_ti26_niveau_b_uniforme_grandeurs_1_6(db_session: Session) -> None:
    """niveau_confiance_derive='B' sur 100% des lignes
    (catch-all calcul_derive + fiabilite haute)."""
    niveaux = {
        r[0]
        for r in db_session.execute(
            select(GrandeurMetier.niveau_confiance_derive)
            .where(
                GrandeurMetier.grandeur_code.in_(
                    [
                        "fraction_diffuse",
                        "humidex",
                        "productible_specifique_theorique",
                        "variabilite_journaliere",
                    ]
                )
            )
            .distinct()
        ).all()
    }
    assert niveaux == {"B"}


def test_ti27_coherence_productible_egale_hep_fois_pr(db_session: Session) -> None:
    """Pour chaque (localite, annee, mois) ayant hep ET
    productible_specifique_theorique sur la fenetre 2021-2025,
    productible ≈ hep * 0.8 à ε près.

    Restriction `annee_debut >= 2021` pour preserver la semantique.
    La coherence PR = 0.8 est egalement appliquee aux series climato
    1991-2020 migration 051 par construction (cf. _calculer_psp_climato
    qui consomme directement la serie HEP climato compagne)."""
    rows = db_session.execute(
        text(
            """
            SELECT
                gm_hep.valeur AS valeur_hep,
                gm_prod.valeur AS valeur_prod
            FROM grandeurs_metier gm_hep
            JOIN grandeurs_metier gm_prod
              ON gm_prod.localite_id = gm_hep.localite_id
             AND gm_prod.periode_type = gm_hep.periode_type
             AND gm_prod.annee_debut = gm_hep.annee_debut
             AND COALESCE(gm_prod.mois, 0) = COALESCE(gm_hep.mois, 0)
             AND gm_prod.grandeur_code = 'productible_specifique_theorique'
            WHERE gm_hep.grandeur_code = 'hep'
              AND gm_hep.valide_au IS NULL
              AND gm_prod.valide_au IS NULL
              AND gm_hep.annee_debut >= 2021
              AND gm_hep.localite_id IN (SELECT id FROM localites WHERE code IN
                  ('gin_conakry_kaloum','gin_kankan','gin_kindia','gin_labe','gin_mamou','gin_nzerekore'))
            """
        )
    ).all()
    assert len(rows) == 390  # 6 pilotes (A1 etend aux 28, scope ici) ; ratio verifie sur tous
    for r in rows:
        assert r.valeur_prod == pytest.approx(r.valeur_hep * 0.8, rel=1e-9)


def test_ti28_fraction_diffuse_dans_zero_un(db_session: Session) -> None:
    """Toutes les valeurs fraction_diffuse ∈ [0, 1] (invariance
    physique DHI ≤ GHI) sur la fenetre 2021-2025.

    Restriction `annee_debut >= 2021` pour preserver la semantique.
    L'invariance reste verifiee pour les series climato 2001-2020
    ajoutees par migration 051 par construction (cf.
    _calculer_fraction_diffuse_climato : ratio DHI / GHI mensuel mois
    par mois, intrinsequement dans [0, 1])."""
    rows = db_session.execute(
        select(GrandeurMetier.valeur).where(
            GrandeurMetier.grandeur_code == "fraction_diffuse",
            GrandeurMetier.valide_au.is_(None),
            GrandeurMetier.annee_debut >= 2021,
            GrandeurMetier.localite_id.in_(_ids_pilotes(db_session)),
        )
    ).all()
    assert len(rows) == 390  # 6 pilotes (A1 etend aux 28, scope ici) ; invariant [0,1] sur tous
    for r in rows:
        assert 0.0 <= r[0] <= 1.0


def test_ti29_plage_humidex_tropical(db_session: Session) -> None:
    """humidex moyen annuel ∈ [25, 45] °C apparents sur les
    6 villes pilotes (plage tropicale large, observée [29.0, 38.6])."""
    rows = db_session.execute(
        select(GrandeurMetier.valeur).where(
            GrandeurMetier.grandeur_code == "humidex",
            GrandeurMetier.periode_type == "annuel",
            GrandeurMetier.valide_au.is_(None),
            GrandeurMetier.localite_id.in_(_ids_pilotes(db_session)),
        )
    ).all()
    assert len(rows) == 30  # 6 pilotes (A2 etend aux 28, scope ici) ; plage verifiee en parite A2
    for r in rows:
        assert 25.0 <= r[0] <= 45.0


def test_ti30_plage_cov_tropical(db_session: Session) -> None:
    """variabilite_journaliere CoV ∈ [0.10, 0.40] sur les
    6 villes pilotes (plage tropicale, observée [0.156, 0.269])."""
    rows = db_session.execute(
        select(GrandeurMetier.valeur).where(
            GrandeurMetier.grandeur_code == "variabilite_journaliere",
            GrandeurMetier.valide_au.is_(None),
            GrandeurMetier.localite_id.in_(_ids_pilotes(db_session)),
        )
    ).all()
    assert len(rows) == 30  # 6 pilotes (A2 etend aux 28, scope ici) ; plage verifiee en parite A2
    for r in rows:
        assert 0.10 <= r[0] <= 0.40


def test_ti31_productible_mensuel_desactive(db_session: Session) -> None:
    """grandeur productible_mensuel a actif=FALSE."""
    actif = db_session.execute(
        text("SELECT actif FROM grandeurs_referentiel WHERE code = 'productible_mensuel'")
    ).scalar_one()
    assert actif is False


def test_ti32_kt_ingere_dans_mesures_ressource(db_session: Session) -> None:
    """10 956 lignes kt dans mesures_ressource (6 villes * 1826 jours).

    Scope localite aux 6 pilotes : la densification (migration 086) ajoute kt
    pour 28 communes ; ce test reste cantonne aux pilotes (les 28 sont couvertes
    par test_densification_daily_b1).
    """
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource mr
            JOIN series_metadonnees sm ON sm.id = mr.serie_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE sm.grandeur_code = 'kt' AND mr.valide_au IS NULL
            AND l.code IN ('gin_conakry_kaloum', 'gin_kankan', 'gin_kindia',
                           'gin_labe', 'gin_mamou', 'gin_nzerekore')
            """
        )
    ).scalar_one()
    assert 10_900 <= n <= 10_956
    # Constat actualise 2026-06-19 : 10 956 lignes (6 * 1826). kt est ingere en
    # LIVE depuis NASA POWER (migration 029) ; les dernieres journees
    # 2025 jadis sentinelle (1/ville) ont ete finalisees cote NASA -> 0 sentinelle,
    # kt atteint son maximum 6 * 1826 (verifie ALLSKY_KT : 1826 jours valides/ville).
    assert n == 10_956


# ---------------------------------------------------------------------------
# Decompte cumule grandeurs calculees Kuma hors indicateur
# ---------------------------------------------------------------------------


def test_ti39_decompte_cumule_grandeurs_kuma_hors_indicateur(db_session: Session) -> None:
    """Decompte cumule `grandeurs_metier` a 1 578 lignes
    sur la fenetre recente 2021-2025, en excluant `indicateur_qualite_donnees`
    et les 3 grandeurs F1 calculee_volee
    (ecart_relatif_referentiel, rang_referentiel_temporel,
    rang_referentiel_spatial).

    Exclusion etendue pour preserver la semantique initiale du test :
    « total des 5 grandeurs Kuma F1 stockee calcul_derive » (390 hep +
    378 fraction_diffuse + 390 humidex + 390
    productible_specifique_theorique + 30
    variabilite_journaliere = 1 578).

    Frontiere tracee :
    - 5 grandeurs Kuma calcul_derive stockee (1 578 lignes,
      fenetre 2021-2025)
    - 1 meta-grandeur indicateur_qualite_donnees (36 lignes).
    - 3 grandeurs F1 calculee_volee (936 lignes : 216 + 360 + 360).
    - 3 grandeurs Kuma climato calcul_derive (6 240 lignes : hep 1991-2020,
      productible_specifique_theorique 1991-2020, fraction_diffuse 2001-2020,
      migration 051).

    Restriction `annee_debut >= 2021` pour cantonner le test a la
    fenetre recente et preserver la cible 1 578. Le total cumule global
    (recent + climato + meta) est valide separement (8 790 lignes).
    """
    n_hors_meta = db_session.scalar(
        select(func.count())
        .select_from(GrandeurMetier)
        .where(GrandeurMetier.valide_au.is_(None))
        .where(GrandeurMetier.annee_debut >= 2021)
        .where(GrandeurMetier.localite_id.in_(_ids_pilotes(db_session)))
        .where(
            GrandeurMetier.grandeur_code.notin_(
                [
                    "indicateur_qualite_donnees",
                    "degenerescence_pixel",
                    "ecart_relatif_referentiel",
                    "ecart_relatif_dni_cams",
                    "rang_referentiel_temporel",
                    "rang_referentiel_spatial",
                ]
            )
        )
    )
    # Exact : DHI daily depuis seed offline -> deterministe.
    # 1590 = 1578 + 12 (fraction_diffuse au max 390, seed entierement muri).
    # Exclues : meta-grandeurs d'honnetete (indicateur_qualite_donnees,
    # degenerescence_pixel) et grandeurs referentielles inter-source (ecart_relatif_*,
    # rang_*) - dont l'ecart DNI recent 2021-2023 ajoute par l'atlas Temps 1 (091).
    assert n_hors_meta == 1590


# ---------------------------------------------------------------------------
# Roundtrip Alembic (marker regression)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_ti24_roundtrip_alembic_023_a_027() -> None:
    """downgrade Alembic jusqu'à 022 puis upgrade head.
    Vérifie reproductibilité totale : décompte grandeurs_metier identique
    après ré-upgrade. Marker regression (lent, lance hors run normal)."""
    cfg = Config("alembic.ini")

    command.downgrade(cfg, "022")
    command.upgrade(cfg, "head")

    # Vérification décompte post-upgrade (cumulé hep + grandeurs Kuma)
    from kuma_data_core.db.session import get_engine

    engine = get_engine()
    with engine.connect() as conn:
        # hep doit toujours être à 390
        n_hep = conn.execute(
            text(
                "SELECT COUNT(*) FROM grandeurs_metier "
                "WHERE grandeur_code = 'hep' AND valide_au IS NULL"
            )
        ).scalar_one()
        assert n_hep == 390
        # Total cumulé doit dépasser 1500 lignes (390 hep + 4 grandeurs Kuma)
        n_total = conn.execute(
            text("SELECT COUNT(*) FROM grandeurs_metier WHERE valide_au IS NULL")
        ).scalar_one()
        assert n_total >= 1500

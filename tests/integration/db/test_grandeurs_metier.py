"""Table ``grandeurs_metier`` : DDL, contraintes, vue des courantes, seeds et calculs stockés."""

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
from tests._migrations import RAISON_DOWNGRADE_046 as _RAISON_DOWNGRADE_046

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

# Les 28 communes ont leurs propres tests : ceux-ci se limitent aux 6 pilotes.
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
    """Ligne HEP de Conakry en 2050, hors des années seedées pour éviter l'EXCLUDE."""
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
    """Colonnes, CHECK nommés, EXCLUDE, index partiel et trigger d'audit présents."""
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
    """Un annuel avec mois est rejeté (``ck_grandeurs_metier_periode_coherente``)."""
    with db_session.begin_nested():
        ligne = _construire_ligne_hep(db_session, periode_type="annuel", annee_debut=2050, mois=3)
        db_session.add(ligne)
        with pytest.raises(IntegrityError):
            db_session.flush()


def test_ti5_insert_invalide_mensuel_sans_mois(db_session: Session) -> None:
    """Un mensuel sans mois est rejeté (``ck_grandeurs_metier_periode_coherente``)."""
    with db_session.begin_nested():
        ligne = _construire_ligne_hep(
            db_session, periode_type="mensuel", annee_debut=2050, mois=None
        )
        db_session.add(ligne)
        with pytest.raises(IntegrityError):
            db_session.flush()


def test_ti6_conflit_exclude_meme_identite_courante(db_session: Session) -> None:
    """Deux lignes courantes de même identité (version comprise) : la seconde est rejetée."""
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
    """Deux versions de formule de même identité coexistent."""
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
    """Un INSERT écrit dans ``audit_log`` (``I``, auteur propagé par ``set_config``)."""
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
    """Après bascule de la version actuelle de hep, la ligne v1 sort de la vue."""
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
    """Une ligne clôturée (``valide_au`` posé) sort de la vue."""
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
    """``niveau_effectif`` vaut l'override s'il existe, sinon le niveau dérivé."""
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
    """Source ``kuma_calculs`` : ``auteur_kuma``, fiabilité haute."""
    row = db_session.execute(
        text("SELECT type_source, fiabilite FROM sources WHERE code = :code"),
        {"code": "kuma_calculs"},
    ).first()
    assert row is not None
    assert row.type_source == "auteur_kuma"
    assert row.fiabilite == "haute"


def test_ti16_check_refuse_valeur_invalide(db_session: Session) -> None:
    """``ck_sources_type_source_valide`` rejette un type inconnu."""
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
    """Les 6 séries HEP 2021-2025 existent, en ``calcul_derive``."""
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
    """Les 6 séries HEP ont un ``commentaire_editorial``."""
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
    """390 lignes HEP 2021-2025 aux pilotes : 6 villes x 5 ans x (1 + 12)."""
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
    assert total == 390


def test_ti20_toutes_lignes_niveau_b(db_session: Session) -> None:
    """Tout ``grandeurs_metier`` est en B ; A est réservé aux mesures au sol."""
    niveaux = {
        r[0]
        for r in db_session.execute(select(GrandeurMetier.niveau_confiance_derive).distinct()).all()
    }
    assert niveaux == {"B"}


def test_ti21_coherence_sum_mensuel_egale_annuel(db_session: Session) -> None:
    """Pour chaque année 2021-2025 complète, somme des mois = annuel (rel=1e-9)."""
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
    """HEP annuelle 2021-2025 entre 1700 et 2100 h_eq (observé 1727-2060)."""
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
    """Pas de commentaire à l'insertion, sauf ``degenerescence_pixel`` qui en porte un exprès."""
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
    """Décompte 2021-2025 par grandeur aux pilotes (390, variabilité annuelle seule : 30)."""
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
    # DHI servi par le seed offline, complet : aucune période écartée.
    assert decompte["fraction_diffuse"] == 390
    assert decompte["humidex"] == 390
    assert decompte["productible_specifique_theorique"] == 390
    assert decompte["variabilite_journaliere"] == 30


def test_ti26_niveau_b_uniforme_grandeurs_1_6(db_session: Session) -> None:
    """Niveau dérivé B sur toutes les lignes de ces grandeurs."""
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
    """Productible théorique = HEP x 0.8 pour chaque période 2021-2025."""
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
    """Fraction diffuse 2021-2025 dans [0, 1] (DHI ≤ GHI)."""
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
    """Humidex annuel des pilotes dans [25, 45] °C apparents (observé 29.0-38.6)."""
    rows = db_session.execute(
        select(GrandeurMetier.valeur).where(
            GrandeurMetier.grandeur_code == "humidex",
            GrandeurMetier.periode_type == "annuel",
            GrandeurMetier.valide_au.is_(None),
            GrandeurMetier.localite_id.in_(_ids_pilotes(db_session)),
        )
    ).all()
    assert len(rows) == 30  # 6 pilotes
    for r in rows:
        assert 25.0 <= r[0] <= 45.0


def test_ti30_plage_cov_tropical(db_session: Session) -> None:
    """CoV des pilotes dans [0.10, 0.40] (observé 0.156-0.269)."""
    rows = db_session.execute(
        select(GrandeurMetier.valeur).where(
            GrandeurMetier.grandeur_code == "variabilite_journaliere",
            GrandeurMetier.valide_au.is_(None),
            GrandeurMetier.localite_id.in_(_ids_pilotes(db_session)),
        )
    ).all()
    assert len(rows) == 30  # 6 pilotes
    for r in rows:
        assert 0.10 <= r[0] <= 0.40


def test_ti31_productible_mensuel_desactive(db_session: Session) -> None:
    """grandeur productible_mensuel a actif=FALSE."""
    actif = db_session.execute(
        text("SELECT actif FROM grandeurs_referentiel WHERE code = 'productible_mensuel'")
    ).scalar_one()
    assert actif is False


def test_ti32_kt_ingere_dans_mesures_ressource(db_session: Session) -> None:
    """10 956 lignes kt 2021-2025 aux pilotes (6 x 1 826)."""
    n = db_session.execute(
        text(
            """
            SELECT COUNT(*) FROM mesures_ressource mr
            JOIN series_metadonnees sm ON sm.id = mr.serie_id
            JOIN localites l ON l.id = sm.localite_id
            WHERE sm.grandeur_code = 'kt' AND mr.valide_au IS NULL
            AND sm.periode_debut = '2021-01-01'
            AND l.code IN ('gin_conakry_kaloum', 'gin_kankan', 'gin_kindia',
                           'gin_labe', 'gin_mamou', 'gin_nzerekore')
            """
        )
    ).scalar_one()
    assert 10_900 <= n <= 10_956
    assert n == 10_956


# ---------------------------------------------------------------------------
# Decompte cumule grandeurs calculees Kuma hors indicateur
# ---------------------------------------------------------------------------


def test_ti39_decompte_cumule_grandeurs_kuma_hors_indicateur(db_session: Session) -> None:
    """Lignes 2021-2025 des grandeurs calculées, hors méta-indicateurs et référentielles."""
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
    # 390 hep + 390 fraction_diffuse + 390 humidex + 390 productible + 30 variabilité
    assert n_hors_meta == 1590


# ---------------------------------------------------------------------------
# Roundtrip Alembic (marker regression)
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.skip(reason=_RAISON_DOWNGRADE_046)
def test_ti24_roundtrip_alembic_023_a_027() -> None:
    """Downgrade jusqu'à 022 puis upgrade : mêmes décomptes (lent, marqueur regression)."""
    from kuma_data_core.db.session import get_engine

    sql_hep = text(
        "SELECT COUNT(*) FROM grandeurs_metier WHERE grandeur_code = 'hep' AND valide_au IS NULL"
    )
    sql_total = text("SELECT COUNT(*) FROM grandeurs_metier WHERE valide_au IS NULL")
    engine = get_engine()
    with engine.connect() as conn:
        n_hep_avant = conn.execute(sql_hep).scalar_one()
        n_total_avant = conn.execute(sql_total).scalar_one()

    cfg = Config("alembic.ini")
    command.downgrade(cfg, "022")
    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        assert conn.execute(sql_hep).scalar_one() == n_hep_avant
        assert conn.execute(sql_total).scalar_one() == n_total_avant

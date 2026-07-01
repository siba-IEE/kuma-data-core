"""localites_niveau_prefecture_code_admin_trigger_hierarchie

Revision ID: 084
Revises: 083
Create Date: 2026-06-19 16:00:00

Densification préfectorale - schéma + intégrité,
aucune donnée. Trois changements sur ``localites``, AVANT tout seed préfectoral :

1. Extension du CHECK ``ck_localites_type_valide`` : ajout de la 7e valeur
   ``'prefecture'`` (niveau administratif manquant : pays > région > préfecture >
   commune). Pattern d'extension de liste fermée VARCHAR + CHECK (drop +
   create_check_constraint + COMMENT + downgrade symétrique), conforme mécaniques
   §4.6 et migration 025.

2. Colonne ``code_administratif_national`` (nullable) : le code 3-lettres du décret
   guinéen de codification 2025 (identifiant officiel externe, ex. CKY), sur le
   modèle ``sources.doi`` / ``sources.isbn`` (colonne dédiée + CHECK de format).
   Requêtable, candidat clé de jointure (données INS / gouvernementales).

3. Trigger de matrice hiérarchique ``valider_hierarchie_localites()`` - clôture
   datée de la dette du trigger 007 (annoncé « à venir » dès la migration 003,
   jamais bâti). Pattern ``kuma_log_audit`` (SECURITY DEFINER, plpgsql). Valide la
   matrice parent-enfant en ``BEFORE INSERT OR UPDATE``. Portée minimale : matrice
   parent-enfant des 7 types + règle continent-racine ; PAS de détection de cycles
   (le seed n'en a pas ; différée si coûteuse). Exception Conakry : la région
   spéciale a des communes directement, donc
   ``commune.parent IN (prefecture, region_administrative)``.

Migrations existantes immuables. Aucune donnée touchée : les 20 localités seedées
en migration 011 sont antérieures au trigger (non re-validées à la création) et
toutes conformes à la matrice (donc un futur UPDATE passe aussi).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "084"
down_revision: str | Sequence[str] | None = "083"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TYPES_INITIAUX: tuple[str, ...] = (
    "continent",
    "region_supranationale",
    "pays",
    "region_administrative",
    "commune",
    "site",
)
"""6 valeurs initiales du CHECK ``ck_localites_type_valide`` (migration 003)."""

_TYPES_ETENDUS: tuple[str, ...] = (
    "continent",
    "region_supranationale",
    "pays",
    "region_administrative",
    "prefecture",
    "commune",
    "site",
)
"""7 valeurs après ajout de ``prefecture`` (ordre hiérarchique préservé)."""


def _liste_sql(valeurs: tuple[str, ...]) -> str:
    """Formate une liste catégorielle pour un CHECK IN (...)."""
    return ", ".join(f"'{v}'" for v in valeurs)


def upgrade() -> None:
    # === 1. Extension du CHECK type_localite (drop + recreate, 7 valeurs) ===
    op.drop_constraint("ck_localites_type_valide", "localites", type_="check")
    op.create_check_constraint(
        "ck_localites_type_valide",
        "localites",
        f"type_localite IN ({_liste_sql(_TYPES_ETENDUS)})",
    )
    op.execute(
        "COMMENT ON COLUMN localites.type_localite IS "
        "'7 valeurs : continent, region_supranationale, pays, region_administrative, "
        "prefecture, commune, site. prefecture ajoutee en densification prefectorale "
        "Etape 1 (niveau pays > region > prefecture > commune).'"
    )

    # === 2. Colonne code_administratif_national (code 3-lettres decret 2025) ===
    op.execute("ALTER TABLE localites ADD COLUMN code_administratif_national VARCHAR(8)")
    op.create_check_constraint(
        "ck_localites_code_administratif_format",
        "localites",
        "code_administratif_national IS NULL OR code_administratif_national ~ '^[A-Z]{3}$'",
    )
    op.execute(
        "COMMENT ON COLUMN localites.code_administratif_national IS "
        "'Code administratif officiel externe (decret guineen de codification 2025, "
        "3 lettres majuscules, ex. CKY). Nullable. Convention identifiant externe "
        "comme sources.doi / sources.isbn. Candidat cle de jointure INS / gouvernemental.'"
    )

    # === 3. Fonction de matrice hierarchique (cloture dette trigger 007) ===
    op.execute(
        """
        CREATE OR REPLACE FUNCTION valider_hierarchie_localites() RETURNS TRIGGER AS $$
        DECLARE
            v_type_parent TEXT;
        BEGIN
            -- Continent : racine, jamais de parent (renforce ck_localites_continent_racine).
            IF NEW.type_localite = 'continent' THEN
                IF NEW.parent_id IS NOT NULL THEN
                    RAISE EXCEPTION
                        'Hierarchie localites : un continent ne peut avoir de parent (code=%, parent_id=%)',
                        NEW.code, NEW.parent_id;
                END IF;
                RETURN NEW;
            END IF;

            -- Tout type non-continent doit avoir un parent.
            IF NEW.parent_id IS NULL THEN
                RAISE EXCEPTION
                    'Hierarchie localites : le type % exige un parent (code=%)',
                    NEW.type_localite, NEW.code;
            END IF;

            SELECT type_localite INTO v_type_parent FROM localites WHERE id = NEW.parent_id;
            IF v_type_parent IS NULL THEN
                RAISE EXCEPTION
                    'Hierarchie localites : parent_id=% introuvable (code=%)',
                    NEW.parent_id, NEW.code;
            END IF;

            -- Matrice parent-enfant (Conakry : commune directement sous region_administrative).
            IF NOT (
                (NEW.type_localite = 'region_supranationale' AND v_type_parent = 'continent')
                OR (NEW.type_localite = 'pays'
                    AND v_type_parent IN ('continent', 'region_supranationale'))
                OR (NEW.type_localite = 'region_administrative' AND v_type_parent = 'pays')
                OR (NEW.type_localite = 'prefecture' AND v_type_parent = 'region_administrative')
                OR (NEW.type_localite = 'commune'
                    AND v_type_parent IN ('prefecture', 'region_administrative'))
                OR (NEW.type_localite = 'site'
                    AND v_type_parent IN ('commune', 'prefecture', 'region_administrative'))
            ) THEN
                RAISE EXCEPTION
                    'Hierarchie localites invalide : un % ne peut avoir un parent de type % '
                    '(code=%, parent_id=%)',
                    NEW.type_localite, v_type_parent, NEW.code, NEW.parent_id;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER;
        """
    )
    op.execute(
        "COMMENT ON FUNCTION valider_hierarchie_localites() IS "
        "'Valide la matrice parent-enfant de localites (BEFORE INSERT OR UPDATE). "
        "Cloture datee de la dette du trigger 007 (annonce des migration 003, jamais bati). "
        "Portee minimale : matrice + continent-racine ; pas de detection de cycles.'"
    )

    # === 4. Trigger BEFORE INSERT OR UPDATE sur localites ===
    op.execute(
        """
        CREATE TRIGGER trg_valider_hierarchie_localites
            BEFORE INSERT OR UPDATE ON localites
            FOR EACH ROW EXECUTE FUNCTION valider_hierarchie_localites()
        """
    )


def downgrade() -> None:
    # Symetrie stricte, ordre inverse.

    # 4 + 3. Trigger puis fonction de hierarchie.
    op.execute("DROP TRIGGER IF EXISTS trg_valider_hierarchie_localites ON localites")
    op.execute("DROP FUNCTION IF EXISTS valider_hierarchie_localites()")

    # 2. Colonne code_administratif_national (le CHECK tombe avec la colonne).
    op.execute("COMMENT ON COLUMN localites.code_administratif_national IS NULL")
    op.drop_constraint("ck_localites_code_administratif_format", "localites", type_="check")
    op.execute("ALTER TABLE localites DROP COLUMN code_administratif_national")

    # 1. Restauration du CHECK type_localite a 6 valeurs.
    op.execute("COMMENT ON COLUMN localites.type_localite IS NULL")
    op.drop_constraint("ck_localites_type_valide", "localites", type_="check")
    op.create_check_constraint(
        "ck_localites_type_valide",
        "localites",
        f"type_localite IN ({_liste_sql(_TYPES_INITIAUX)})",
    )

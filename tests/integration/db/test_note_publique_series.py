"""Tests d'intégration du passeport public des séries (migration 099).

Verrouille trois invariants :

- TI-NP-1 : toute série porte une ``note_publique`` non vide (la
  colonne reste nullable en schéma, la non-nullité effective du parc
  est un invariant éditorial).
- TI-NP-2 : aucune note publique ne contient de vocabulaire de
  chantier interne (identifiants de dettes, renvois PR/spec, étapes,
  cohortes, lots, vagues). C'est le contrat qui a motivé la colonne :
  le passeport est auto-portant.
- TI-NP-3 : le journal interne ``commentaire_editorial`` n'a pas été
  altéré par la bascule (il reste renseigné sur tout le parc seedé).

La migration 100 (D-63, option a) est verrouillée par TI-NP-4 :
``productible_specifique_theorique`` pointe l'unité
``kwh_par_kwc_periode`` et sa note publique annonce des totaux par
période.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

# Motifs de vocabulaire de chantier interdits dans une note publique.
_JARGON_INTERNE = re.compile(
    r"(PR\s*#\d+"
    r"|spec\s+\d+-\d+"
    r"|[ée]tape\s+\d+"
    r"|cohorte"
    r"|vague\s+\d"
    r"|volet\s+[A-Z]\b"
    r"|\blot\s+[A-Z0-9]"
    r"|\bD-\d+\b"
    r"|\bTI-\d+\b"
    r"|\bL-[A-Z]+-\d+\b"
    r"|note\s+(méthodologique\s+)?amont"
    r"|densification\s+pr[ée]fectorale"
    r"|parit[ée]\s+[AB]\d)",
    re.IGNORECASE,
)


def test_ti_np1_note_publique_renseignee_partout(db_session: Session) -> None:
    """TI-NP-1 : aucune série sans passeport public."""
    manquantes = db_session.execute(
        text(
            "SELECT code FROM series_metadonnees "
            "WHERE note_publique IS NULL OR BTRIM(note_publique) = '' "
            "ORDER BY code LIMIT 10"
        )
    ).all()
    assert manquantes == [], f"Séries sans note publique : {[r.code for r in manquantes]}"


def test_ti_np2_note_publique_sans_jargon_interne(db_session: Session) -> None:
    """TI-NP-2 : le passeport public est auto-portant."""
    lignes = db_session.execute(
        text("SELECT code, note_publique FROM series_metadonnees WHERE note_publique IS NOT NULL")
    ).all()
    assert lignes, "Parc de séries vide : invariant non évaluable."
    fautives = [
        (ligne.code, _JARGON_INTERNE.search(ligne.note_publique).group(0))  # type: ignore[union-attr]
        for ligne in lignes
        if _JARGON_INTERNE.search(ligne.note_publique)
    ]
    assert fautives == [], f"Jargon interne dans des notes publiques : {fautives[:10]}"


def test_ti_np3_journal_interne_intact(db_session: Session) -> None:
    """TI-NP-3 : la bascule n'a pas touché le journal de chantier."""
    vides = db_session.execute(
        text(
            "SELECT COUNT(*) FROM series_metadonnees "
            "WHERE commentaire_editorial IS NULL OR BTRIM(commentaire_editorial) = ''"
        )
    ).scalar_one()
    assert vides == 0


def test_ti_np4_psp_unite_periode_et_note_coherente(db_session: Session) -> None:
    """TI-NP-4 : D-63 résorbée (option a) : étiquette et note alignées."""
    unite = db_session.execute(
        text(
            "SELECT u.code, u.symbole FROM grandeurs_referentiel gr "
            "JOIN unites u ON u.id = gr.unite_id "
            "WHERE gr.code = 'productible_specifique_theorique'"
        )
    ).one()
    assert unite.code == "kwh_par_kwc_periode"
    assert unite.symbole == "kWh/kWc"

    note = db_session.execute(
        text(
            "SELECT note_publique FROM series_metadonnees "
            "WHERE grandeur_code = 'productible_specifique_theorique' LIMIT 1"
        )
    ).scalar_one_or_none()
    assert note is not None
    assert "totaux sur la période" in note

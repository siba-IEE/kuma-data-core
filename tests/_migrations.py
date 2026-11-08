"""Constantes partagées par les tests de migration Alembic."""

from __future__ import annotations

# La migration 046 lève NotImplementedError au downgrade : tout aller-retour
# qui redescend sous 046 échoue avant d'atteindre sa cible.
RAISON_DOWNGRADE_046 = (
    "Downgrade sous 046 impossible : la migration 046 est corrective et non "
    "réversible (NotImplementedError)."
)

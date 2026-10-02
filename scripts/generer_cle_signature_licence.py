"""Génère la paire Ed25519 qui signe les baux SolClim-3.

À lancer une fois, sur un poste de confiance :

    uv run python scripts/generer_cle_signature_licence.py

- La **graine privée** va dans l'environnement du serveur
  (``LICENCE_CLE_SIGNATURE``), et nulle part ailleurs : ni dépôt, ni
  message, ni capture.
- La **clé publique** s'embarque dans SolClim-3 et dans le service de
  calage : elle ne permet que de vérifier.

Changer de paire invalide tous les baux en circulation à leur prochaine
vérification : chaque logiciel redemande alors un bail au serveur.
"""

from __future__ import annotations

from kuma_data_core.services.bail import generer_paire


def main() -> None:
    graine, publique = generer_paire()
    print("# Graine privée : environnement du serveur uniquement.")
    print(f"LICENCE_CLE_SIGNATURE={graine}")
    print()
    print("# Clé publique : à embarquer dans SolClim-3 et le service de calage.")
    print(f"LICENCE_CLE_PUBLIQUE={publique}")


if __name__ == "__main__":
    main()

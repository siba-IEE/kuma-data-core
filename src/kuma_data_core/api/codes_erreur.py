"""Codes d'erreur stables de l'API.

Identifiants destinés aux outils qui consomment l'API. Un code publié ne
change plus et ne disparaît plus : pour faire évoluer un sens, on crée un
nouveau code et on déprécie l'ancien.

Préfixes : ``AUTH_*`` (authentification), ``VALIDATION_*`` (entrées),
``RESSOURCE_*`` (existence d'une ressource), ``GRANDEUR_F2_*`` (grandeurs
paramétrables), ``PASSE_PLAT_*`` et ``PLAGE_*`` (relais horaire et plages
non servies), ``CLES_*``, ``LICENCE_*``, ``CONTRIBUTION*`` (clés
self-service, licences et contributions SolClim-3), ``INFRASTRUCTURE_*``
(base, cache), ``SERVEUR_*`` (erreurs internes).

``GRANDEUR_F2_INCONNUE``, ``VALIDATION_LIMIT_HORS_BORNES`` et
``INFRASTRUCTURE_CACHE_INDISPONIBLE`` sont réservés : aucun endpoint ne les
renvoie.
"""

from __future__ import annotations

from enum import StrEnum


class CodeErreur(StrEnum):
    """Codes d'erreur stables de l'API Kuma."""

    # Authentification (4xx)
    AUTH_HEADER_MANQUANT = "AUTH_HEADER_MANQUANT"
    AUTH_FORMAT_INVALIDE = "AUTH_FORMAT_INVALIDE"
    AUTH_CLE_INVALIDE = "AUTH_CLE_INVALIDE"

    # Validation (4xx)
    VALIDATION_CHAMP_MANQUANT = "VALIDATION_CHAMP_MANQUANT"
    VALIDATION_VALEUR_INVALIDE = "VALIDATION_VALEUR_INVALIDE"
    VALIDATION_FORMAT_DATE_INVALIDE = "VALIDATION_FORMAT_DATE_INVALIDE"
    VALIDATION_FORMAT_NON_SUPPORTE = "VALIDATION_FORMAT_NON_SUPPORTE"
    VALIDATION_LIMIT_HORS_BORNES = "VALIDATION_LIMIT_HORS_BORNES"

    # Ressources (4xx)
    RESSOURCE_INTROUVABLE = "RESSOURCE_INTROUVABLE"
    CALAGE_INDISPONIBLE = "CALAGE_INDISPONIBLE"
    RESSOURCE_SERIE_INCONNUE = "RESSOURCE_SERIE_INCONNUE"
    RESSOURCE_LOCALITE_INCONNUE = "RESSOURCE_LOCALITE_INCONNUE"

    # Grandeurs paramétrables (4xx)
    GRANDEUR_F2_INCONNUE = "GRANDEUR_F2_INCONNUE"
    INCOMPATIBILITE_SOURCE_GRANDEUR = "INCOMPATIBILITE_SOURCE_GRANDEUR"

    # Passe-plat horaire (4xx + 5xx)
    PLAGE_TEMPORELLE_NON_DISPONIBLE = "PLAGE_TEMPORELLE_NON_DISPONIBLE"
    PASSE_PLAT_INDISPONIBLE = "PASSE_PLAT_INDISPONIBLE"

    # Plafond de débit par adresse, avant authentification (429)
    DEBIT_DEPASSE = "DEBIT_DEPASSE"

    # Clés API self-service (4xx)
    CLES_EMISSION_NON_ACTIVEE = "CLES_EMISSION_NON_ACTIVEE"
    CLES_LIMITE_EMISSION_ATTEINTE = "CLES_LIMITE_EMISSION_ATTEINTE"
    CLES_QUOTA_JOURNALIER_DEPASSE = "CLES_QUOTA_JOURNALIER_DEPASSE"

    # Licences SolClim-3 (4xx)
    LICENCE_NON_ACTIVEE = "LICENCE_NON_ACTIVEE"
    LICENCE_ABSENTE = "LICENCE_ABSENTE"

    # Contributions d'études SolClim-3 (4xx)
    CONTRIBUTIONS_NON_ACTIVEES = "CONTRIBUTIONS_NON_ACTIVEES"
    CONTRIBUTION_INCONNUE = "CONTRIBUTION_INCONNUE"

    # Serveur (5xx)
    INFRASTRUCTURE_BASE_INDISPONIBLE = "INFRASTRUCTURE_BASE_INDISPONIBLE"
    INFRASTRUCTURE_CACHE_INDISPONIBLE = "INFRASTRUCTURE_CACHE_INDISPONIBLE"
    SERVEUR_ERREUR_INTERNE = "SERVEUR_ERREUR_INTERNE"

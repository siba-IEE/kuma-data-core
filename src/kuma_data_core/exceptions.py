"""Hiérarchie d'exceptions transverses : racine ``KumaError``, une sous-racine par domaine."""

from __future__ import annotations


class KumaError(Exception):
    """Racine de la hiérarchie d'exceptions Kuma Data Core."""


class NasaPowerError(KumaError):
    """Racine des erreurs du client NASA POWER (`external.nasa_power`)."""


class NasaPowerHttpError(NasaPowerError):
    """Réponse HTTP non-2xx de l'API NASA POWER (``body`` tronqué à 2000 caractères)."""

    def __init__(self, status_code: int, url: str, body: str) -> None:
        self.status_code: int = status_code
        self.url: str = url
        self.body: str = body[:2000]
        super().__init__(
            f"NASA POWER a retourné HTTP {status_code} pour {url}. Extrait corps : {self.body!r}"
        )


class NasaPowerRateLimitError(NasaPowerHttpError):
    """HTTP 429 de NASA POWER, distinct pour une stratégie de retry dédiée."""


class NasaPowerPayloadError(NasaPowerError):
    """Payload NASA POWER illisible ou non conforme aux schémas ``NasaPowerResponse``."""

    def __init__(self, message: str, url: str, body: str) -> None:
        self.url: str = url
        self.body: str = body[:2000]
        super().__init__(f"{message} (url={url!r}, extrait corps={self.body!r})")


class NasaPowerTimeoutError(NasaPowerError):
    """Timeout ou déconnexion NASA POWER persistant après épuisement du retry."""

    def __init__(self, url: str, timeout_seconds: float) -> None:
        self.url: str = url
        self.timeout_seconds: float = timeout_seconds
        super().__init__(f"Timeout NASA POWER après {timeout_seconds}s pour {url}")


# ===========================================================================
# Exceptions PVGIS
# ===========================================================================


class PvgisError(KumaError):
    """Racine des erreurs du client PVGIS (SARAH-3 ICDR, JRC)."""


class PvgisHttpError(PvgisError):
    """HTTP non-2xx terminal côté PVGIS (``body`` tronqué à 2000 caractères)."""

    def __init__(self, status_code: int, url: str, body: str) -> None:
        self.status_code: int = status_code
        self.url: str = url
        self.body: str = body[:2000]
        super().__init__(f"PVGIS HTTP {status_code} (url={url!r}, extrait corps={self.body!r})")


class PvgisRateLimitError(PvgisHttpError):
    """Rate limit PVGIS (HTTP 429) persistant après épuisement du retry."""


class PvgisTimeoutError(PvgisError):
    """Timeout ou déconnexion PVGIS persistant après épuisement du retry.

    Les déconnexions intermittentes de PVGIS depuis les runners CI justifient ce retry.
    """

    def __init__(self, url: str, timeout_seconds: float) -> None:
        self.url: str = url
        self.timeout_seconds: float = timeout_seconds
        super().__init__(f"Timeout PVGIS après {timeout_seconds}s pour {url}")


# ===========================================================================
# Exceptions éditoriales
# ===========================================================================


class EditorialeError(KumaError):
    """Racine des erreurs des workflows éditoriaux (statut, confiance, versionnement)."""


class TransitionEditorialeRefusee(EditorialeError):  # noqa: N818
    """Transition absente de la matrice de ``editorial.statuts``."""

    def __init__(self, statut_courant: str, nouveau_statut: str) -> None:
        self.statut_courant: str = statut_courant
        self.nouveau_statut: str = nouveau_statut
        super().__init__(
            f"Transition éditoriale refusée : "
            f"{statut_courant!r} -> {nouveau_statut!r} "
            f"n'est pas dans la matrice autorisée § 4.5."
        )


class NiveauConfianceInvalide(EditorialeError):  # noqa: N818
    """Niveau de confiance hors du référentiel A/B/C."""

    def __init__(self, valeur_recue: str) -> None:
        self.valeur_recue: str = valeur_recue
        super().__init__(
            f"Niveau de confiance invalide : {valeur_recue!r}. Valeurs autorisées : 'A', 'B', 'C'."
        )


class JustificationRequise(EditorialeError):  # noqa: N818
    """Opération (ex. override de confiance) sans ``commentaire_editorial``."""

    def __init__(self, operation: str) -> None:
        self.operation: str = operation
        super().__init__(f"Justification éditoriale requise pour l'opération {operation!r}.")

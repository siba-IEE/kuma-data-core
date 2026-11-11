"""Exceptions de Kuma Data Core : une racine ``KumaError``, une sous-racine par domaine."""

from __future__ import annotations


class KumaError(Exception):
    """Racine des exceptions de Kuma Data Core."""


class NasaPowerError(KumaError):
    """Racine des erreurs du client NASA POWER (`external.nasa_power`)."""


class NasaPowerHttpError(NasaPowerError):
    """Réponse HTTP non-2xx de NASA POWER ; ``body`` est tronqué à 2 000 caractères."""

    def __init__(self, status_code: int, url: str, body: str) -> None:
        self.status_code: int = status_code
        self.url: str = url
        self.body: str = body[:2000]
        super().__init__(
            f"NASA POWER a retourné HTTP {status_code} pour {url}. Extrait corps : {self.body!r}"
        )


class NasaPowerRateLimitError(NasaPowerHttpError):
    """HTTP 429 de NASA POWER, distinct pour autoriser une reprise propre au plafond de débit."""


class NasaPowerPayloadError(NasaPowerError):
    """Réponse de NASA POWER illisible ou hors schéma ; ``body`` est tronqué à 2 000 caractères."""

    def __init__(self, message: str, url: str, body: str) -> None:
        self.url: str = url
        self.body: str = body[:2000]
        super().__init__(f"{message} (url={url!r}, extrait corps={self.body!r})")


class NasaPowerTimeoutError(NasaPowerError):
    """Délai dépassé ou déconnexion de NASA POWER, une fois les reprises épuisées."""

    def __init__(self, url: str, timeout_seconds: float) -> None:
        self.url: str = url
        self.timeout_seconds: float = timeout_seconds
        super().__init__(f"Timeout NASA POWER après {timeout_seconds}s pour {url}")


class PvgisError(KumaError):
    """Racine des erreurs du client PVGIS (SARAH-3), levées par ``ingestion.sarah3_monthly``."""


class PvgisHttpError(PvgisError):
    """Réponse HTTP non-2xx définitive de PVGIS ; ``body`` est tronqué à 2 000 caractères."""

    def __init__(self, status_code: int, url: str, body: str) -> None:
        self.status_code: int = status_code
        self.url: str = url
        self.body: str = body[:2000]
        super().__init__(f"PVGIS HTTP {status_code} (url={url!r}, extrait corps={self.body!r})")


class PvgisRateLimitError(PvgisHttpError):
    """HTTP 429 de PVGIS, persistant une fois les reprises épuisées."""


class PvgisTimeoutError(PvgisError):
    """Délai dépassé ou déconnexion de PVGIS, une fois les reprises épuisées."""

    def __init__(self, url: str, timeout_seconds: float) -> None:
        self.url: str = url
        self.timeout_seconds: float = timeout_seconds
        super().__init__(f"Timeout PVGIS après {timeout_seconds}s pour {url}")


class EditorialeError(KumaError):
    """Racine des erreurs éditoriales (paquet ``kuma_data_core.editorial``)."""


class TransitionEditorialeRefusee(EditorialeError):  # noqa: N818
    """Transition de statut absente de ``editorial.statuts.TRANSITIONS_AUTORISEES``."""

    def __init__(self, statut_courant: str, nouveau_statut: str) -> None:
        self.statut_courant: str = statut_courant
        self.nouveau_statut: str = nouveau_statut
        super().__init__(
            f"Transition éditoriale refusée : "
            f"{statut_courant!r} -> {nouveau_statut!r} "
            f"n'est pas dans la matrice autorisée § 4.5."
        )


class NiveauConfianceInvalide(EditorialeError):  # noqa: N818
    """Niveau de confiance autre que A, B ou C."""

    def __init__(self, valeur_recue: str) -> None:
        self.valeur_recue: str = valeur_recue
        super().__init__(
            f"Niveau de confiance invalide : {valeur_recue!r}. Valeurs autorisées : 'A', 'B', 'C'."
        )


class JustificationRequise(EditorialeError):  # noqa: N818
    """Justification absente ou vide pour une opération éditoriale qui l'exige."""

    def __init__(self, operation: str) -> None:
        self.operation: str = operation
        super().__init__(f"Justification éditoriale requise pour l'opération {operation!r}.")

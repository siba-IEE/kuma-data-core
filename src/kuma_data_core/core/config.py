"""Configuration centrale de Kuma Data Core.

Source de vérité unique pour les variables d'environnement. Le fichier
`.env` à la racine du dépôt est la seule source de configuration locale.
La classe ``Settings`` est consommée par la couche base de données
(``db.session``), par Alembic (``migrations/env.py``) et, à terme, par
l'application FastAPI.

Les valeurs par défaut correspondent à l'environnement Docker local
(127.0.0.1:5432). Aucun secret n'est codé en dur : les champs sans
valeur par défaut (mot de passe) doivent être fournis via ``.env``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Racine du dépôt : trois niveaux au-dessus de ce fichier
# (src/kuma_data_core/core/config.py -> racine).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Variables d'environnement consommées par Kuma Data Core.

    Seule la configuration PostgreSQL est requise à ce stade. D'autres
    sections (Redis, API) sont ajoutées au fil des besoins.
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # === PostgreSQL ===
    postgres_user: str = Field(default="kuma_admin")
    postgres_password: str = Field(...)
    postgres_db: str = Field(default="kuma_data_core")
    postgres_host: str = Field(default="127.0.0.1")
    postgres_port: int = Field(default=5432)

    # === Seeds initiaux ===
    # Email du contributeur principal inséré par la migration 001.
    kuma_initial_editor_email: str = Field(default="editeur.principal@kuma-science.org")

    # === Settings API ===
    # Configuration de l'application FastAPI privée.
    api_titre: str = Field(default="Kuma Data Core API")
    api_version: str = Field(default="0.1.0")
    api_environnement: Literal["dev", "integration", "prod"] = Field(default="dev")
    api_docs_actives: bool = Field(default=True)
    # Clés API valides (stockage en variables d'environnement).
    # Migration vers une table ``cles_api`` prévue ultérieurement.
    api_cle_solar_bridge: SecretStr | None = Field(default=None)
    api_cle_admin: SecretStr | None = Field(default=None)

    # === Édition publique (ADR-0003) ===
    # ``edition_db`` : nom de la base d'édition active côté serveur, écrit
    # par ``publier-edition.sh`` dans le fichier pointeur (bascule par
    # repointage, D1). Prime sur ``postgres_db`` quand défini. En local,
    # rester à ``None`` : la base de référence est servie directement.
    edition_db: str | None = Field(default=None)
    # ``edition_figee`` : profil public sans relais temps réel (D6). Le
    # repli passe-plat horaire renvoie PLAGE_TEMPORELLE_NON_DISPONIBLE au
    # lieu d'appeler la source amont ; seul le stocké est servi.
    edition_figee: bool = Field(default=False)
    # ``meta_db`` : nom de la base de service (``kuma_api_meta`` sur le
    # serveur public, D3) qui porte ``cles_api``. ``None`` = pas de base
    # de service : l'émission self-service de clés est désactivée et
    # l'authentification reste env-only (régime local historique).
    meta_db: str | None = Field(default=None)

    # === Settings Logging ===
    # ``texte`` en dev (lisible humainement, couleurs), ``json`` en prod
    # (parsable par les agrégateurs). Le format est validé contre
    # l'environnement par ``valider_coherence_environnement`` ci-dessous.
    log_format: Literal["texte", "json"] = Field(default="texte")
    log_niveau: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")

    @property
    def database_url(self) -> str:
        """DSN SQLAlchemy pour psycopg3 (driver synchrone moderne).

        La base d'édition (``edition_db``, serveur public) prime sur la
        base de référence (``postgres_db``, locale) quand elle est définie.
        """
        base = self.edition_db if self.edition_db is not None else self.postgres_db
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{base}"
        )

    @property
    def database_url_meta(self) -> str | None:
        """DSN de la base de service (``cles_api``), ``None`` si désactivée."""
        if self.meta_db is None:
            return None
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.meta_db}"
        )

    @model_validator(mode="after")
    def valider_coherence_environnement(self) -> Settings:
        """Bloque le démarrage si la configuration est incohérente en prod.

        En production, la documentation OpenAPI doit être désactivée, les
        logs au format JSON, et la clé d'administration obligatoire. Toute
        violation lève une ``ValueError`` au moment de l'instanciation des
        ``Settings`` - l'application ne démarre pas.
        """
        if self.api_environnement == "prod":
            if self.api_docs_actives:
                raise ValueError("api_docs_actives ne peut pas être True en production")
            if self.log_format != "json":
                raise ValueError("log_format doit être 'json' en production")
            if self.api_cle_admin is None:
                raise ValueError("api_cle_admin obligatoire en production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retourne l'instance unique de configuration (memoizée).

    Préférer cette fonction à l'instanciation directe : elle évite de
    relire ``.env`` à chaque accès et garantit qu'une seule instance
    circule dans le processus.
    """
    return Settings()  # type: ignore[call-arg]

"""Configuration centrale : variables d'environnement, lues depuis ``.env`` à la racine.

Défauts alignés sur le Docker local ; aucun secret par défaut (le mot de
passe PostgreSQL est obligatoire).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# src/kuma_data_core/core/config.py -> racine du dépôt
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Variables d'environnement de Kuma Data Core."""

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
    # Contributeur principal créé par la première migration.
    kuma_initial_editor_email: str = Field(default="editeur.principal@kuma-science.org")

    # === Settings API ===
    api_titre: str = Field(default="Kuma Data Core API")
    api_version: str = Field(default="0.1.0")
    api_environnement: Literal["dev", "integration", "prod"] = Field(default="dev")
    api_docs_actives: bool = Field(default=True)
    api_cle_solar_bridge: SecretStr | None = Field(default=None)
    api_cle_admin: SecretStr | None = Field(default=None)
    kuma_calage_base: str | None = Field(default=None)
    kuma_calage_jeton: SecretStr | None = Field(default=None)

    # === Licences SolClim-3 (bail signé) ===
    # Graine Ed25519 (32 octets, base64) qui ne quitte jamais le serveur ; la
    # clé publique est embarquée côté logiciel. ``None`` : pas d'émission de bail.
    licence_cle_signature: SecretStr | None = Field(default=None)
    # Durée hors ligne avant passage en lecture seule.
    licence_duree_jours: int = Field(default=30, ge=1, le=365)
    # En dessous, le logiciel passe en lecture seule et invite à se mettre à jour.
    licence_version_minimale: str = Field(default="1.1.0")

    # === Édition publique (ADR-0003) ===
    # Base d'édition active, écrite par ``publier-edition.sh`` (bascule par
    # repointage). Prime sur ``postgres_db`` ; ``None`` en local.
    edition_db: str | None = Field(default=None)
    # Profil public sans relais temps réel : seul le stocké est servi, le repli
    # horaire renvoie PLAGE_TEMPORELLE_NON_DISPONIBLE.
    edition_figee: bool = Field(default=False)
    # Base de service portant ``cles_api``. ``None`` : pas d'émission
    # self-service, authentification par variables d'environnement seules.
    meta_db: str | None = Field(default=None)
    # Sur le VPS, l'édition tourne en ``kuma_api_ro`` (lecture seule) et la
    # base de service en ``kuma_api_service`` (écriture) : il faut deux couples
    # d'identifiants. À ``None``, repli sur le couple principal ; le moindre
    # privilège n'est tenu en prod que si ces deux valeurs sont fournies.
    meta_user: str | None = Field(default=None)
    meta_password: SecretStr | None = Field(default=None)
    # Quota journalier des clés self-service (Redis), serveur public seulement ;
    # les clés d'environnement (admin, Bridge) ne sont jamais limitées.
    rate_limiting_actif: bool = Field(default=False)
    # Lit l'IP cliente dans ``X-Forwarded-For``. Seulement derrière le reverse
    # proxy (Caddy), qui écrase l'en-tête client : exposée en direct, l'API
    # laisserait un client forger cet en-tête pour contourner la limite par IP.
    derriere_proxy_confiance: bool = Field(default=False)

    # === Redis (compteurs de rate limiting) ===
    redis_host: str = Field(default="127.0.0.1")
    redis_port: int = Field(default=6379)
    redis_password: SecretStr | None = Field(default=None)

    # === Settings Logging ===
    # ``json`` exigé en prod (agrégateurs), ``texte`` lisible en dev.
    log_format: Literal["texte", "json"] = Field(default="texte")
    log_niveau: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")

    @property
    def database_url(self) -> str:
        """DSN psycopg3 ; ``edition_db`` prime sur ``postgres_db`` quand elle est définie."""
        base = self.edition_db if self.edition_db is not None else self.postgres_db
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{base}"
        )

    @property
    def database_url_meta(self) -> str | None:
        """DSN de la base de service (``cles_api``), ``None`` si désactivée.

        Identifiants dédiés ``meta_user``/``meta_password`` s'ils sont fournis,
        sinon le couple principal : c'est ce qui permet au moteur d'édition de
        tourner en lecture seule.
        """
        if self.meta_db is None:
            return None
        utilisateur = self.meta_user if self.meta_user is not None else self.postgres_user
        secret = self.meta_password if self.meta_password is not None else self.postgres_password
        mot_de_passe = secret.get_secret_value() if isinstance(secret, SecretStr) else secret
        return (
            f"postgresql+psycopg://{utilisateur}:{mot_de_passe}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.meta_db}"
        )

    @model_validator(mode="after")
    def valider_coherence_environnement(self) -> Settings:
        """En prod, exige docs OpenAPI coupées, logs JSON et clé admin non vide (``ValueError``)."""
        if self.api_environnement == "prod":
            if self.api_docs_actives:
                raise ValueError("api_docs_actives ne peut pas être True en production")
            if self.log_format != "json":
                raise ValueError("log_format doit être 'json' en production")
            # Une clé vide passerait ``is None`` et ferait d'un Bearer vide un admin.
            if self.api_cle_admin is None or not self.api_cle_admin.get_secret_value():
                raise ValueError("api_cle_admin obligatoire et non vide en production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Instance unique de configuration, ``.env`` lu une seule fois."""
    return Settings()  # type: ignore[call-arg]

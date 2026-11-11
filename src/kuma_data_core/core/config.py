"""Configuration de Kuma Data Core, lue depuis l'environnement et ``.env``.

``Settings`` sert la couche base de données, Alembic et l'API. Les valeurs
par défaut sont celles de l'environnement Docker local ; aucun secret n'a de
valeur par défaut.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _REPO_ROOT / ".env"

LONGUEUR_MIN_CLE_PROD = 32


def _secret_faible(valeur: str) -> bool:
    return len(valeur) < LONGUEUR_MIN_CLE_PROD or valeur.lower().startswith("changeme")


class Settings(BaseSettings):
    """Variables d'environnement de Kuma Data Core (base, API, licences, édition, Redis, logs)."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    postgres_user: str = Field(default="kuma_admin")
    postgres_password: SecretStr = Field(...)
    postgres_db: str = Field(default="kuma_data_core")
    postgres_host: str = Field(default="127.0.0.1")
    postgres_port: int = Field(default=5432)

    # Email du contributeur principal, inséré à la création de ``contributeurs``.
    kuma_initial_editor_email: str = Field(default="editeur.principal@kuma-science.org")

    api_titre: str = Field(default="Kuma Data Core API")
    api_version: str = Field(default="0.1.0")
    api_environnement: Literal["dev", "integration", "prod"] = Field(default="dev")
    api_docs_actives: bool = Field(default=True)
    # Origines CORS, propres à chaque déploiement : l'application de bureau
    # (Vite en dev, Tauri en production) et la console web. Liste JSON.
    cors_origines: list[str] = Field(
        default=[
            "http://localhost:1420",
            "http://127.0.0.1:1420",
            "tauri://localhost",
            "https://tauri.localhost",
            "http://tauri.localhost",
            "https://kumascience.com",
            "https://www.kumascience.com",
        ]
    )
    # Clés d'environnement (Bridge, administration). Les clés self-service
    # vivent dans ``cles_api``, sur la base de service (``meta_db``).
    api_cle_solar_bridge: SecretStr | None = Field(default=None)
    api_cle_admin: SecretStr | None = Field(default=None)
    kuma_calage_base: str | None = Field(default=None)
    kuma_calage_jeton: SecretStr | None = Field(default=None)

    # Graine Ed25519 (32 octets, base64) qui signe les baux SolClim-3. Elle
    # ne quitte jamais le serveur ; la clé publique est embarquée dans le
    # logiciel et le service de calage. ``None`` = pas d'émission de bail.
    licence_cle_signature: SecretStr | None = Field(default=None)
    # Durée d'un bail : ce que le logiciel tient hors ligne avant de passer
    # en lecture seule.
    licence_duree_jours: int = Field(default=30, ge=1, le=365)
    # Version minimale du logiciel inscrite au bail : en dessous, il passe
    # en lecture seule et invite à se mettre à jour.
    licence_version_minimale: str = Field(default="1.1.0")

    # Base d'édition publique active (ADR-0003), repointée par
    # ``publier-edition.sh`` à chaque publication. Prime sur ``postgres_db`` ;
    # ``None`` en local, où la base de référence est servie directement.
    edition_db: str | None = Field(default=None)
    # Profil public sans relais temps réel : l'horaire non stocké renvoie
    # PLAGE_TEMPORELLE_NON_DISPONIBLE au lieu d'appeler la source amont.
    edition_figee: bool = Field(default=False)
    # Base de service, qui porte ``cles_api``. ``None`` = pas d'émission
    # self-service : seules les clés d'environnement authentifient.
    meta_db: str | None = Field(default=None)
    # Identifiants dédiés de la base de service. Sur le serveur, l'édition
    # est lue par un rôle en lecture seule et la base de service écrite par
    # un autre : un seul couple ne peut pas tenir les deux. À ``None``, on
    # retombe sur ``postgres_user``/``postgres_password`` ; le moindre
    # privilège n'est donc tenu que si ces valeurs sont fournies en production.
    meta_user: str | None = Field(default=None)
    meta_password: SecretStr | None = Field(default=None)
    # Quota journalier des clés self-service, via Redis. Serveur public
    # uniquement ; les clés d'environnement ne sont jamais limitées.
    rate_limiting_actif: bool = Field(default=False)
    # Plafond de requêtes par minute et par adresse (IPv6 : par /64),
    # appliqué avant l'authentification quand ``rate_limiting_actif``.
    debit_ip_par_minute: int = Field(default=300, ge=1)
    # Quand vrai, l'adresse cliente (limite d'émission de clés, plafond de
    # débit) est lue dans ``X-Forwarded-For``, posé par le reverse proxy. À
    # laisser faux si l'API est exposée en direct : un client forgerait cet
    # en-tête pour contourner les limites.
    derriere_proxy_confiance: bool = Field(default=False)

    # Redis : compteurs de quota et de débit.
    redis_host: str = Field(default="127.0.0.1")
    redis_port: int = Field(default=6379)
    redis_password: SecretStr | None = Field(default=None)

    # ``json`` est exigé en production par ``valider_coherence_environnement``.
    log_format: Literal["texte", "json"] = Field(default="texte")
    log_niveau: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")

    @property
    def database_url(self) -> str:
        """DSN SQLAlchemy (psycopg 3) ; la base d'édition prime sur la base de référence."""
        base = self.edition_db if self.edition_db is not None else self.postgres_db
        return self._dsn(self.postgres_user, self.postgres_password, base)

    @property
    def database_url_meta(self) -> str | None:
        """DSN de la base de service (``cles_api``), ``None`` si désactivée.

        Utilise ``meta_user``/``meta_password`` quand ils sont fournis, sinon le
        couple principal : c'est ce qui laisse l'édition en lecture seule.
        """
        if self.meta_db is None:
            return None
        utilisateur = self.meta_user if self.meta_user is not None else self.postgres_user
        secret = self.meta_password if self.meta_password is not None else self.postgres_password
        return self._dsn(utilisateur, secret, self.meta_db)

    def _dsn(self, utilisateur: str, mot_de_passe: SecretStr, base: str) -> str:
        # URL.create encode les caractères réservés (@, /, :) du mot de passe.
        return URL.create(
            "postgresql+psycopg",
            username=utilisateur,
            password=mot_de_passe.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=base,
        ).render_as_string(hide_password=False)

    @model_validator(mode="after")
    def valider_coherence_environnement(self) -> Settings:
        """Refuse de démarrer sur une configuration de production incohérente.

        En production : pas de ``*`` dans les origines CORS, pas de documentation
        OpenAPI, logs en JSON, clé d'administration présente et robuste.
        """
        if self.api_environnement == "prod":
            if "*" in self.cors_origines:
                raise ValueError("cors_origines ne peut pas contenir '*' en production")
            if self.api_docs_actives:
                raise ValueError("api_docs_actives ne peut pas être True en production")
            if self.log_format != "json":
                raise ValueError("log_format doit être 'json' en production")
            # Clé admin présente ET non vide : une valeur vide passerait
            # `is None` mais rendrait un Bearer vide administrateur.
            if self.api_cle_admin is None or not self.api_cle_admin.get_secret_value():
                raise ValueError("api_cle_admin obligatoire et non vide en production")
            if _secret_faible(self.api_cle_admin.get_secret_value()):
                raise ValueError(
                    "api_cle_admin trop faible pour la production : au moins "
                    f"{LONGUEUR_MIN_CLE_PROD} caractères, pas de valeur d'exemple"
                )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Instance unique de configuration : ``.env`` n'est lu qu'une fois par processus."""
    return Settings()  # type: ignore[call-arg]

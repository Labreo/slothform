"""Application configuration via Pydantic Settings."""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings loaded from environment or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Browserbase (Headless Cloud Browser)
    BROWSERBASE_API_KEY: str = "bb_live_dummy"
    BROWSERBASE_PROJECT_ID: str = "dummy_project"

    # Paper Instruments / Ultramarine
    PAPER_INSTRUMENTS_API_KEY: str = "pi_live_dummy"
    ULTRAMARINE_MODEL: str = "ultramarine-1-flash"

    # Auth0 for AI Agents
    AUTH0_DOMAIN: str = "your-tenant.us.auth0.com"
    AUTH0_CLIENT_ID: str = "your_auth0_client_id"
    AUTH0_CLIENT_SECRET: str = "your_auth0_client_secret"
    AUTH0_AUDIENCE: str = "https://api.slothform.internal"
    AUTH0_TOKEN_VAULT_KEY: str = "slothform_secure_vault_key_32_bytes_len!!"

    # Application Server & Security
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = "slothform_master_secret_32_bytes_length!"

    # Local Vault Storage
    VAULT_FILE_PATH: str = "data/vault.enc"

    # Sentry (Optional)
    SENTRY_DSN: Optional[str] = None

    # Auth0 CIBA Offline Mode (Enabled by default for testing/offline scenarios)
    AUTH0_OFFLINE_MODE: bool = False

    # Auth0 CIBA Auto-Approval (Disabled by default for human-in-the-loop consent)
    AUTH0_CIBA_AUTO_APPROVE: bool = False


@lru_cache()
def get_settings() -> Settings:
    """Retrieve cached application settings instance."""
    return Settings()

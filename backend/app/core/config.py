"""Application configuration.

Every value comes from the environment (or a local .env file); nothing here
encodes a laptop-specific absolute path. Asset and storage directories are
resolved relative to this package so the app runs from any checkout location.
"""

import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parents[2]
# backend/ -> repository root
REPO_DIR = BACKEND_DIR.parent


def _split_csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General ---------------------------------------------------------
    app_name: str = "PAM Rate Board API"
    environment: str = "development"
    debug: bool = False

    # --- Database --------------------------------------------------------
    # MariaDB 10.4 (XAMPP) speaks the MySQL protocol; PyMySQL is the driver.
    database_url: str = "mysql+pymysql://root:@127.0.0.1:3306/pam_rate_board?charset=utf8mb4"
    db_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_recycle: int = 1800

    # --- Security --------------------------------------------------------
    secret_key: str = ""
    access_token_ttl_minutes: int = 720
    bcrypt_rounds: int = 12

    login_rate_limit_attempts: int = 10
    login_rate_limit_window_seconds: int = 300
    pairing_rate_limit_attempts: int = 20
    pairing_rate_limit_window_seconds: int = 300

    # Keep the pre-2.0 flat endpoints mounted while callers migrate.
    enable_legacy_api: bool = True

    # --- CORS ------------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Storage ---------------------------------------------------------
    storage_dir: str = ""
    assets_dir: str = ""
    public_base_url: str = "http://localhost:8000"

    # --- Display / player defaults --------------------------------------
    heartbeat_interval_seconds: int = 30
    display_offline_after_seconds: int = 90
    player_poll_interval_seconds: int = 300
    pairing_code_ttl_seconds: int = 600

    # --- Jobs / worker ---------------------------------------------------
    job_poll_interval_seconds: float = 2.0
    job_max_attempts: int = 3
    job_timeout_seconds: int = 600
    job_stale_after_seconds: int = 900
    worker_concurrency: int = 1
    video_duration_seconds: int = 600

    # --- Events ----------------------------------------------------------
    event_poll_interval_seconds: float = 2.0
    event_retention_hours: int = 24

    # --- Timezone --------------------------------------------------------
    display_timezone: str = "Asia/Makassar"

    @field_validator("secret_key")
    @classmethod
    def _secret_required_in_production(cls, value: str, info) -> str:
        return value

    @property
    def cors_origin_list(self) -> List[str]:
        return _split_csv(self.cors_origins)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def assets_path(self) -> Path:
        return Path(self.assets_dir) if self.assets_dir else BACKEND_DIR / "assets"

    @property
    def storage_path(self) -> Path:
        return Path(self.storage_dir) if self.storage_dir else REPO_DIR / "storage"

    @property
    def media_path(self) -> Path:
        return self.storage_path / "media"

    @property
    def tmp_path(self) -> Path:
        return self.storage_path / "tmp"

    @property
    def flag_cache_path(self) -> Path:
        return self.storage_path / "flags"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()

    if not settings.secret_key:
        if settings.is_production:
            raise RuntimeError(
                "SECRET_KEY must be set in production. Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        # Development convenience only: a per-process key. Restarting the API
        # invalidates issued tokens, which is acceptable locally and makes the
        # missing-configuration state obvious instead of silently insecure.
        settings.secret_key = secrets.token_urlsafe(48)

    for directory in (
        settings.storage_path,
        settings.media_path,
        settings.tmp_path,
        settings.flag_cache_path,
    ):
        os.makedirs(directory, exist_ok=True)

    return settings

"""Runtime settings from env / .env."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_cache_dir() -> Path:
    override = os.environ.get("SONICMATCH_CACHE_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".cache" / "sonicmatch-mcp"


def repo_root() -> Path:
    """Repo root when running from a checkout; otherwise the package parent."""
    here = Path(__file__).resolve()
    # src/sonicmatch/config.py -> repo
    candidate = here.parents[2]
    if (candidate / "pyproject.toml").exists():
        return candidate
    return here.parents[1]


def seed_catalog_path() -> Path:
    root = repo_root()
    p = root / "data" / "seed_tracks.json"
    if p.exists():
        return p
    bundled = Path(__file__).resolve().parent / "data" / "seed_tracks.json"
    return bundled


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.0-flash", alias="GEMINI_MODEL")
    jamendo_client_id: str | None = Field(default=None, alias="JAMENDO_CLIENT_ID")
    freesound_api_key: str | None = Field(default=None, alias="FREESOUND_API_KEY")
    epidemic_library_path: str | None = Field(default=None, alias="EPIDEMIC_LIBRARY_PATH")
    artlist_library_path: str | None = Field(default=None, alias="ARTLIST_LIBRARY_PATH")
    user_library_path: str | None = Field(default=None, alias="SONICMATCH_LIBRARY_PATH")
    cache_dir: Path = Field(default_factory=_default_cache_dir, alias="SONICMATCH_CACHE_DIR")
    http_host: str = Field(default="127.0.0.1", alias="SONICMATCH_HTTP_HOST")
    http_port: int = Field(default=8765, alias="SONICMATCH_HTTP_PORT")
    max_download_mb: int = Field(default=200, alias="SONICMATCH_MAX_DOWNLOAD_MB")
    max_keyframes: int = 12
    proxy_max_seconds: int = 90

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def has_jamendo(self) -> bool:
        return bool(self.jamendo_client_id)

    @property
    def has_freesound(self) -> bool:
        return bool(self.freesound_api_key)

    @property
    def db_path(self) -> Path:
        return self.cache_dir / "db" / "tracks.sqlite"

    def ensure_dirs(self) -> None:
        (self.cache_dir / "assets").mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "mix").mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "tracks").mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "db").mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "brand").mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "generated").mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "libraries").mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings

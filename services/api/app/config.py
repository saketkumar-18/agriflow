"""AgriFlow API configuration — all secrets and endpoints via environment."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AgriFlow API"
    version: str = "1.0.0"
    environment: str = "development"  # development | production | test

    # Database: SQLite by default (zero-setup dev/demo), PostgreSQL in production.
    database_url: str = "sqlite:///./agriflow.db"
    # Optional: isolate all AgriFlow tables in this Postgres schema (shared instances)
    pg_schema: str = ""

    # Auth
    auth_secret: str = "dev-only-insecure-secret-change-me"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days for low-connectivity farmers
    jwt_algorithm: str = "HS256"

    # Weather provider abstraction: "open_meteo" (free, no key) | "none" (stub).
    weather_provider: str = "open_meteo"
    weather_cache_minutes: int = 30
    # Optional override endpoint (proxy/self-hosted); default is the public Open-Meteo URL.
    weather_base_url: str = "https://api.open-meteo.com"
    open_meteo_api_key: str = ""  # not required for the free personal-use API

    # Redis is optional: with it, cross-process caching/rate-limits use it; without,
    # the app falls back to in-process caches (documented, not faked).
    redis_url: str = ""

    # Email (optional). When unset, notifications persist in-app only and the
    # worker logs that the email channel is not configured — never pretends to send.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    cors_origins: str = "http://localhost:3000,http://localhost:3001"

    # Rate limits (requests per minute)
    rate_limit_auth_per_min: int = 10
    rate_limit_read_per_min: int = 120
    rate_limit_write_per_min: int = 30

    # Recommendation engine tunables (defaults; per-crop/stage overrides live in DB)
    default_mad: float = 0.55          # management allowable depletion, normal stage
    critical_mad: float = 0.40         # tighter during critical growth stages
    moisture_fresh_hours: float = 12.0 # max age for full-confidence moisture
    moisture_max_age_hours: float = 48.0  # beyond this, moisture treated as absent
    rain_defer_mm: float = 8.0         # >= this much rain expected within 48h -> defer
    rain_prob_gate: float = 50.0       # % probability to count forecast rain as meaningful
    recommendation_ttl_hours: float = 12.0

    # Seed accounts (created on first boot when DB empty). Dev convenience, documented.
    demo_seed_enabled: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

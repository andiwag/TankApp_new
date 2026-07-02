from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.branding import DEFAULT_MAIL_FROM, SESSION_COOKIE_DEFAULT

_DEFAULT_SECRET_KEY = "supersecretkey"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "sqlite:///./dev.db"

    SECRET_KEY: str = "supersecretkey"

    SESSION_COOKIE_NAME: str = SESSION_COOKIE_DEFAULT

    ENV: str = "development"

    BASE_URL: str = ""

    REDIS_URL: str = ""

    CRON_SECRET: str = ""

    SENTRY_DSN: str = ""

    ALLOWED_HOSTS: str = "*"

    # Set false in multi-replica production; run scripts/migrate.sh as a one-off job.
    RUN_MIGRATIONS_ON_START: bool = True

    # Allow in-memory rate limits on a single production worker (beta only).
    SINGLE_WORKER_MODE: bool = False

    # When set, new accounts must provide this code at registration (private beta).
    REGISTRATION_INVITE_CODE: str = ""

    MAIL_USERNAME: str = ""

    MAIL_PASSWORD: str = ""

    MAIL_FROM: str = DEFAULT_MAIL_FROM

    MAIL_SERVER: str = "smtp.example.com"

    MAIL_PORT: int = 587

    MAIL_STARTTLS: bool = True

    @field_validator("REGISTRATION_INVITE_CODE", mode="before")
    @classmethod
    def normalize_registration_invite_code(cls, value: object) -> str:
        if not isinstance(value, str):
            return ""
        return value.strip()

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    @property
    def registration_invite_required(self) -> bool:
        return bool(self.REGISTRATION_INVITE_CODE.strip())

    @property
    def mail_configured(self) -> bool:
        return bool(
            self.MAIL_USERNAME
            and self.MAIL_PASSWORD
            and self.MAIL_SERVER
            and self.MAIL_FROM
        )

    @property
    def allowed_hosts(self) -> list[str]:
        raw = self.ALLOWED_HOSTS.strip()

        if not raw or raw == "*":
            return ["*"]

        hosts = [host.strip() for host in raw.split(",") if host.strip()]

        # Northflank/K8s readiness probes often use Host: localhost or 127.0.0.1
        if self.is_production:
            for internal_host in ("localhost", "127.0.0.1"):
                if internal_host not in hosts:
                    hosts.append(internal_host)

        return hosts

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if not self.is_production:
            return self

        if self.SECRET_KEY == _DEFAULT_SECRET_KEY:
            raise ValueError(
                "SECRET_KEY must be set to a unique value when ENV=production"
            )

        if not self.CRON_SECRET:
            raise ValueError("CRON_SECRET must be set when ENV=production")

        if not self.REDIS_URL and not self.SINGLE_WORKER_MODE:
            raise ValueError(
                "REDIS_URL must be set when ENV=production, or set "
                "SINGLE_WORKER_MODE=true for a single-worker beta deployment"
            )

        return self


settings = Settings()

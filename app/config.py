from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "sqlite:///./dev.db"
    SECRET_KEY: str = "supersecretkey"
    SESSION_COOKIE_NAME: str = "tankapp_session"
    ENV: str = "development"
    BASE_URL: str = ""

    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_FROM: str = "noreply@tankapp.example.com"
    MAIL_SERVER: str = "smtp.example.com"
    MAIL_PORT: int = 587
    MAIL_STARTTLS: bool = True

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    @property
    def mail_configured(self) -> bool:
        return bool(
            self.MAIL_USERNAME
            and self.MAIL_PASSWORD
            and self.MAIL_SERVER
            and self.MAIL_FROM
        )


settings = Settings()

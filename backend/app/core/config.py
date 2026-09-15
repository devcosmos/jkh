from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JKH_", env_file=".env")

    database_url: str = "postgresql+psycopg://jkh:jkh@localhost:5432/jkh"
    jwt_secret_key: str = "dev-only-change-me"
    default_prediction_window_hours: int = 24
    auto_draft_risk_threshold: float = 0.5


settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JKH_", env_file=".env")

    database_url: str = "postgresql+psycopg://jkh:jkh@localhost:5432/jkh"
    jwt_secret_key: str = "dev-only-change-me"
    default_prediction_window_hours: int = 24
    auto_draft_risk_threshold: float = 0.5
    # Краткое резюме прогноза для диспетчера (app/services/llm_summary.py) — без ключа
    # функция просто недоступна (None), не роняет карточку риска.
    anthropic_api_key: str | None = None
    # Не задан — SDK идёт на официальный api.anthropic.com. Задан — например, на прокси
    # стороннего провайдера (формат ответа должен быть совместим с Anthropic Messages API).
    anthropic_base_url: str | None = None


settings = Settings()

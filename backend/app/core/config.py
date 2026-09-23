from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore": .env общий для backend, worker и docker-compose (REPLAY_* — только
    # worker, читает их напрямую из os.environ, не через Settings). Без этого Settings() падает
    # на любом ключе .env, которого нет в этом классе, даже без префикса JKH_ (раздел
    # аудита «инструкция запуска» — backend/README.md).
    model_config = SettingsConfigDict(env_prefix="JKH_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://jkh:jkh@localhost:5432/jkh"
    jwt_secret_key: str = "dev-only-change-me"
    default_prediction_window_hours: int = 24
    # Краткое резюме прогноза для диспетчера (app/services/llm_summary.py) — без ключа
    # функция просто недоступна (None), не роняет карточку риска. credentials — это
    # Authorization key (base64 client_id:client_secret) из личного кабинета GigaChat API,
    # не сам access-токен — SDK сам обменивает его на короткоживущий токен по scope.
    gigachat_credentials: str | None = None
    gigachat_scope: str = "GIGACHAT_API_PERS"
    # Путь внутри контейнера до сертификата УЦ Минцифры — GigaChat отдаёт TLS-сертификат,
    # подписанный российским удостоверяющим центром, системные CA-бандлы его не знают.
    gigachat_ca_bundle_file: str | None = None


settings = Settings()

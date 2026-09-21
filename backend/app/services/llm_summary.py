"""Краткое резюме прогноза для диспетчера на естественном языке (идея из TODO.md,
21 сентября 2026) — не заменяет объяснение SHAP на карточке риска, а переводит его
в одно-два предложения человеческим языком: «что случилось и почему это подозрительно».

Считается лениво (по первому запросу карточки конкретного риск-кейса), результат
кешируется в Prediction.llm_summary — повторные просмотры карточки не дёргают API
повторно. Модель — Claude Haiku 4.5: короткая шаблонная суммаризация не требует
топовых reasoning-моделей, а стоимость и задержка для Haiku на порядок ниже.

Ключ и (опционально) base_url настраиваются через JKH_ANTHROPIC_API_KEY /
JKH_ANTHROPIC_BASE_URL — по умолчанию (base_url не задан) SDK идёт на официальный API
Anthropic; сейчас в .env указан прокси cheapai.io (эндпоинт /v1/messages, формат ответа
идентичен официальному Anthropic Messages API — проверено вручную 21 сентября 2026).
Модель на этом прокси называется `claude-haiku-4-5-20251001` (с датой снапшота, не
голым `claude-haiku-4-5`, как на официальном API) — см. GET /v1/models под ключом.

Без настроенного JKH_ANTHROPIC_API_KEY функция просто недоступна (возвращает None) —
карточка риска не должна ломаться из-за отсутствующего ключа стороннего сервиса."""

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = (
    "Ты помогаешь диспетчеру объединённой диспетчерской службы быстро понять, почему "
    "сработал прогноз отказа датчика. Тебе даны вклад признаков (SHAP) в конкретный "
    "прогноз ML-модели и независимый сигнал аномальности. Напиши краткое резюме на "
    "русском языке — 1-2 предложения, разговорным языком, без markdown и списков, "
    "как будто объясняешь коллеге. Опирайся только на переданные данные, ничего не "
    "выдумывай про объект или устройство."
)


def _build_user_prompt(top_features: list[dict], probability: float, is_anomaly: bool | None) -> str:
    lines = [f"Вероятность отказа по модели: {probability:.0%}."]
    if is_anomaly:
        lines.append("Независимая модель отмечает поведение канала как аномальное.")
    lines.append("Вклад признаков в прогноз (по убыванию влияния):")
    for f in top_features:
        direction = "повышает риск" if f["contribution"] >= 0 else "снижает риск"
        lines.append(f"- {f['label']}: {f['value']} ({direction}, вклад {f['contribution']:+.3f})")
    return "\n".join(lines)


def generate_dispatcher_summary(explanation: dict | None, probability: float) -> str | None:
    """Возвращает готовый текст резюме или None (нет ключа, нет данных, ошибка API —
    во всех случаях тихо, карточка риска показывает "недоступно", не падает)."""
    if not settings.anthropic_api_key:
        return None
    top_features = (explanation or {}).get("top_features")
    if not top_features:
        return None

    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package не установлен — резюме недоступно")
        return None

    anomaly = (explanation or {}).get("anomaly") or {}
    user_prompt = _build_user_prompt(top_features, probability, anomaly.get("is_outlier"))

    try:
        client_kwargs = {"api_key": settings.anthropic_api_key}
        if settings.anthropic_base_url:
            client_kwargs["base_url"] = settings.anthropic_base_url
        client = anthropic.Anthropic(**client_kwargs)
        response = client.messages.create(
            model=MODEL,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        return text or None
    except Exception:  # noqa: BLE001 — сторонний API, любая ошибка не должна ронять карточку
        logger.exception("Не удалось получить резюме от LLM")
        return None

"""Краткое резюме прогноза для диспетчера на естественном языке (идея из TODO.md,
21 сентября 2026) — не заменяет объяснение SHAP на карточке риска, а переводит его
в одно-два предложения человеческим языком: «что случилось и почему это подозрительно».

Считается лениво (по первому запросу карточки конкретного риск-кейса), результат
кешируется в Prediction.llm_summary — повторные просмотры карточки не дёргают API
повторно. Модель — GigaChat-2 (базовая линейка, без суффикса Pro/Max/Ultra): короткая
шаблонная суммаризация не требует топовых reasoning-моделей, а на базовой модели
укладываемся в бесплатную месячную квоту токенов для физлиц. Голого имени `GigaChat`
(без версии) в лайнапе уже нет — проверено 23 сентября 2026 через GET /models под
реальным ключом, актуальный список: GigaChat-2(/-Max/-Pro), GigaChat-3-*.

Изначально использовался Anthropic Claude через прокси cheapai.io, но прокси стал
недоступен с прод-VPS (сеть РФ, Beget) — 23 сентября 2026 перешли на GigaChat (Sber)
как на нативный российский сервис. Авторизация — JKH_GIGACHAT_CREDENTIALS (Authorization
key из личного кабинета GigaChat API, строка вида base64(client_id:client_secret), не
сам токен — SDK сам меняет его на короткоживущий access-токен по OAuth). TLS-сертификат
GigaChat подписан УЦ Минцифры, системные CA его не знают — путь до сертификата задаётся
JKH_GIGACHAT_CA_BUNDLE_FILE (см. Dockerfile, где сертификат скачивается при сборке образа).

Без настроенного JKH_GIGACHAT_CREDENTIALS функция просто недоступна (возвращает None) —
карточка риска не должна ломаться из-за отсутствующего ключа стороннего сервиса."""

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

MODEL = "GigaChat-2"
# Вызывается синхронно из GET-запроса карточки риска — без явного тайм-аута повисший
# сторонний API держал бы поток обработки запроса неограниченно долго.
REQUEST_TIMEOUT_SECONDS = 20.0

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
    if not settings.gigachat_credentials:
        return None
    top_features = (explanation or {}).get("top_features")
    if not top_features:
        return None

    try:
        from gigachat import GigaChat
        from gigachat.models import Chat, Messages, MessagesRole
    except ImportError:
        logger.warning("gigachat package не установлен — резюме недоступно")
        return None

    anomaly = (explanation or {}).get("anomaly") or {}
    user_prompt = _build_user_prompt(top_features, probability, anomaly.get("is_outlier"))

    try:
        client_kwargs = {
            "credentials": settings.gigachat_credentials,
            "scope": settings.gigachat_scope,
            "timeout": REQUEST_TIMEOUT_SECONDS,
        }
        if settings.gigachat_ca_bundle_file:
            client_kwargs["ca_bundle_file"] = settings.gigachat_ca_bundle_file
        with GigaChat(**client_kwargs) as client:
            response = client.chat(
                Chat(
                    model=MODEL,
                    messages=[
                        Messages(role=MessagesRole.SYSTEM, content=SYSTEM_PROMPT),
                        Messages(role=MessagesRole.USER, content=user_prompt),
                    ],
                )
            )
        text = response.choices[0].message.content.strip()
        return text or None
    except Exception:  # noqa: BLE001 — сторонний API, любая ошибка не должна ронять карточку
        logger.exception("Не удалось получить резюме от LLM")
        return None

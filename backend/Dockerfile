# OPS-02 (analys_and_todo.md): пин ниже 3.14 намеренный, не случайное расхождение с CI
# (.github/workflows/ci.yml — python-version: "3.14"). Проверено 22 сентября 2026: на
# python:3.14-slim (нет системного C/Rust-тулчейна) сборка Dockerfile.worker падает — catboost
# тянет y-py (Rust-расширение через maturin), готового wheel под cp314 на этой платформе ещё
# нет, компиляция из исходников требует cc/cargo, которых в -slim образе нет. GitHub Actions
# runner собирает те же зависимости на 3.14 без проблем — там уже есть полный тулчейн. backend/
# и Dockerfile.worker используют одну и ту же базу намеренно (проще пин один раз, чем гадать,
# какая версия у какого сервиса ещё соберётся) — поднимать до 3.14 в проде, когда появятся
# готовые wheels под cp314 для тяжёлых ML-зависимостей.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Корневой сертификат УЦ Минцифры — TLS-сертификат GigaChat (app/services/llm_summary.py)
# подписан им, системные CA-бандлы Debian его не знают. Официальный источник — портал
# Госуслуг, не сам Sber (сертификат для доверенных сервисов в целом, GigaChat в частности).
RUN apt-get update \
    && apt-get install --no-install-recommends -y curl ca-certificates \
    && mkdir -p /app/certs \
    && curl -fsSL -o /app/certs/russian_trusted_root_ca.pem \
        https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini .
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

CMD ["./docker-entrypoint.sh"]

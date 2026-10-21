# Payment Processing Service

Асинхронный микросервис процессинга платежей. Принимает запросы на оплату, обрабатывает их через эмуляцию платёжного шлюза и уведомляет клиента о результате через webhook.

## Архитектура

```
Клиент ──► FastAPI ──► PostgreSQL (payments + outbox)
                           │
                           ▼  (Outbox publisher поллит таблицу)
                       RabbitMQ
                           │
              payments.new │          payments.dead (DLQ)
                           ▼                ▲
                       Consumer ────────────┘
                           │  (эмуляция 2–5 сек, 90% успех)
                           ▼
                    Webhook ──► Клиент
```

### Ключевые решения

| Проблема | Решение |
|---|---|
| Гарантированная публикация событий | **Outbox pattern**: событие пишется в таблицу `outbox` в одной транзакции с платежом, отдельный поллер публикует в RabbitMQ |
| Защита от дублей | **Idempotency-Key** в заголовке + уникальный индекс в БД |
| Потерянные сообщения | **Dead Letter Queue** (`payments.dead`): после 3 неудачных попыток обработки сообщение уходит в DLQ |
| Ошибки доставки вебхуков | **Retry с экспоненциальной задержкой**: 3 попытки (1с → 2с → 4с) |
| Аутентификация | Статический **API-ключ** в заголовке `X-API-Key` |

## Стек

- **FastAPI** + **Pydantic v2** — API и валидация
- **SQLAlchemy 2.0** (async) + **asyncpg** — работа с БД
- **PostgreSQL 16** — хранилище
- **RabbitMQ** + **FastStream** — брокер сообщений
- **Alembic** — миграции
- **Docker Compose** — оркестрация
- **uv** — менеджер зависимостей
- **pre-commit** + **ruff** + **mypy** — линтеры

## Структура проекта

```
.
├── alembic/                    # миграции БД
├── app/
│   ├── api/
│   │   ├── deps.py             # аутентификация по API-ключу
│   │   └── routes/payments.py  # эндпоинты
│   ├── consumer/
│   │   ├── main.py             # точка входа consumer'а (FastStream)
│   │   └── worker.py           # обработка платежей, retry, DLQ
│   ├── core/
│   │   ├── config.py           # настройки (pydantic-settings)
│   │   └── database.py         # подключение к БД
│   ├── models/                 # SQLAlchemy-модели
│   │   ├── payment.py
│   │   └── outbox.py
│   ├── schemas/                # Pydantic-схемы
│   │   └── payment.py
│   ├── services/
│   │   ├── payment_service.py  # бизнес-логика
│   │   └── outbox_publisher.py # поллер outbox → RabbitMQ
│   └── main.py                 # FastAPI-приложение
├── docker-compose.yaml
├── Dockerfile
├── pyproject.toml
└── .pre-commit-config.yaml
```

## Быстрый старт

### Требования

- Docker и Docker Compose
- [uv](https://docs.astral.sh/uv/) (для локальной разработки)

### Запуск

```bash
cp .env.example .env
docker compose up --build -d
```

Что происходит:
1. Стартуют `postgres` и `rabbitmq`
2. Контейнер `migrate` применяет миграции (`alembic upgrade head`)
3. Стартуют `api` (порт 8000) и `consumer`

### Полезные адреса

- Swagger UI: http://localhost:8000/docs
- RabbitMQ Management: http://localhost:15672 (guest/guest)

## Примеры запросов

### Создание платежа

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-api-key-12345" \
  -H "Idempotency-Key: order-001" \
  -d '{
    "amount": 1500.50,
    "currency": "RUB",
    "description": "Оплата заказа №12345",
    "metadata": {"order_id": "12345", "customer": "ivan@example.com"},
    "webhook_url": "https://webhook.site/ВАШ-УНИКАЛЬНЫЙ-URL"
  }'
```

**Ответ `202 Accepted`:**

```json
{
  "payment_id": "7f3e9c2a-1b8d-4e5f-a6c7-8d9e0f1a2b3c",
  "status": "pending",
  "created_at": "2026-10-21T14:30:00Z"
}
```

> 💡 Для приёма вебхуков удобно использовать [webhook.site](https://webhook.site) — бесплатный сервис, показывающий входящие запросы в браузере.

### Идемпотентность

Повторный запрос с тем же `Idempotency-Key` вернёт **тот же** платёж, дубль не создастся:

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-api-key-12345" \
  -H "Idempotency-Key: order-001" \
  -d '{ ... тот же body ... }'
```

### Получение статуса платежа

```bash
curl http://localhost:8000/api/v1/payments/7f3e9c2a-1b8d-4e5f-a6c7-8d9e0f1a2b3c \
  -H "X-API-Key: test-api-key-12345"
```

**Ответ:**

```json
{
  "id": "7f3e9c2a-1b8d-4e5f-a6c7-8d9e0f1a2b3c",
  "amount": "1500.50",
  "currency": "RUB",
  "description": "Оплата заказа №12345",
  "metadata": {"order_id": "12345", "customer": "ivan@example.com"},
  "status": "succeeded",
  "idempotency_key": "order-001",
  "webhook_url": "https://webhook.site/...",
  "created_at": "2026-10-21T14:30:00Z",
  "processed_at": "2026-10-21T14:30:03Z"
}
```

### Webhook-уведомление

После обработки consumer отправляет `POST` на `webhook_url`:

```json
{
  "payment_id": "7f3e9c2a-1b8d-4e5f-a6c7-8d9e0f1a2b3c",
  "status": "succeeded",
  "amount": "1500.50",
  "currency": "RUB",
  "processed_at": "2026-10-21T14:30:03Z"
}
```

## Проверка сценариев

### Идемпотентность

```bash
# Два одинаковых запроса подряд — вернётся один и тот же payment_id
for i in 1 2; do
  curl -s -X POST http://localhost:8000/api/v1/payments \
    -H "Content-Type: application/json" \
    -H "X-API-Key: test-api-key-12345" \
    -H "Idempotency-Key: idempotency-test" \
    -d '{"amount": 100, "currency": "RUB", "webhook_url": "https://webhook.site/test"}'
  echo
done
```

### Невалидный запрос (422)

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-api-key-12345" \
  -H "Idempotency-Key: bad-amount" \
  -d '{"amount": -5, "currency": "RUB", "webhook_url": "https://example.com/hook"}'
```

### Неверный API-ключ (401)

```bash
curl http://localhost:8000/api/v1/payments/любой-uuid \
  -H "X-API-Key: wrong-key"
```

### Dead Letter Queue

Самый простой способ увидеть сообщение в `payments.dead` — отправить в очередь «битый» JSON через management-интерфейс RabbitMQ (http://localhost:15672 → Queues → `payments.new` → Publish message). После нескольких неудачных попыток обработки сообщение окажется в `payments.dead`, и consumer залоггирует `DEAD LETTER: ...`.

## Локальная разработка (без Docker)

```bash
uv sync                          # установка зависимостей
uv run pre-commit install        # git-хуки (ruff, mypy, проверки)

# Поднимаем только инфраструктуру
docker compose up -d postgres rabbitmq

# Применяем миграции
uv run alembic upgrade head

# Локальный запуск API
uv run uvicorn app.main:app --reload

# В отдельном терминале — consumer
uv run faststream run app.consumer.main:app
```

### Миграции

```bash
# Создать новую миграцию после изменения моделей
uv run alembic revision --autogenerate -m "описание изменения"

# Применить
uv run alembic upgrade head

# Откатить последнюю
uv run alembic downgrade -1
```

## Конфигурация

Все настройки — через переменные окружения (см. `.env.example`):

| Переменная | По умолчанию | Описание |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://...` | Строка подключения к PostgreSQL |
| `RABBITMQ_URL` | `amqp://guest:guest@...` | Строка подключения к RabbitMQ |
| `API_KEY` | `test-api-key-12345` | Статический ключ аутентификации |
| `OUTBOX_POLL_INTERVAL` | `1.0` | Интервал поллинга outbox (сек) |
| `PAYMENT_MIN_DELAY` / `MAX_DELAY` | `2` / `5` | Диапазон эмуляции обработки (сек) |
| `PAYMENT_SUCCESS_RATE` | `0.9` | Вероятность успеха (90%) |
| `WEBHOOK_MAX_RETRIES` | `3` | Максимум попыток доставки вебхука |
| `MAX_PROCESSING_RETRIES` | `3` | Попыток обработки до отправки в DLQ |

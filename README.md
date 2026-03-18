# CatRuler_Reborn

## Что это

CatRuler_Reborn — SaaS для автопостинга в VK и Telegram с AI-генерацией текста и изображений.

## Стек

- FastAPI
- PostgreSQL
- Redis
- Celery
- aiogram
- Yandex S3

## Быстрый старт

1. Создайте `.env` на основе `.env.example`.
2. Соберите контейнеры:

```bash
make build
```

3. Поднимите API, БД, Redis, worker и beat:

```bash
make up
```

4. Примените миграции:

```bash
make migrate
```

5. Запустите бота:

```bash
make bot-up
```

## Переменные окружения

### APP

- `DEV_MODE` — режим разработки.
- `LOG_LEVEL` — уровень логирования.
- `JWT_SECRET_KEY` — секрет для JWT.
- `JWT_ALGORITHM` — алгоритм подписи JWT.
- `JWT_EXPIRE_MINUTES` — время жизни access token.

### DB

- `DATABASE_URL` — полная строка подключения к БД.
- `PROD_DB_NAME` — имя базы PostgreSQL.
- `PROD_DB_USER` — пользователь PostgreSQL.
- `PROD_DB_PASSWORD` — пароль PostgreSQL.
- `PROD_DB_HOST` — хост PostgreSQL.
- `PROD_DB_PORT` — порт PostgreSQL.

### TG

- `TELEGRAM_BOT_TOKEN` — токен Telegram-бота.
- `INTERNAL_API_URL` — адрес API для внутренних вызовов из бота.
- `INTERNAL_API_SHARED_SECRET` — общий секрет для защищённых внутренних bot->api запросов.
- `BOT_MODE` — режим бота: `polling` или `webhook`.
- `WEBHOOK_BASE_URL` — внешний базовый URL для webhook-режима.
- `WEBHOOK_PATH` — путь webhook endpoint.
- `WEBHOOK_SECRET` — секрет проверки webhook.
- `TELEGRAM_BOT_SECRET_TOKEN` — secret token Telegram webhook.

### LLM

- `OPEN_ROUTER_API_KEY` — ключ OpenRouter.
- `HUGGING_FACE_API_KEY` — ключ Hugging Face.
- `POLLEN_API_KEY` — ключ Pollinations, если нужен провайдеру.

### CRYPTO

- `ENCRYPTION_KEY` — Fernet-ключ для шифрования сохранённых токенов.

### YANDEX_STORAGE

- `YANDEX_ACCESS_KEY` — access key Object Storage.
- `YANDEX_SECRET_KEY` — secret key Object Storage.
- `YANDEX_BUCKET_NAME` — имя бакета для изображений.
- `REDIS_URL` — Redis для кеша и внутренних сервисов.
- `CELERY_BROKER_URL` — Redis broker для Celery.
- `CELERY_RESULT_BACKEND` — Redis backend для Celery.

### Tailscale

- `TAILSCALE_AUTH_KEY` — auth key для Tailscale.
- `TAILSCALE_HOSTNAME` — hostname узла Tailscale.

## API

- `/auth/login` — вход по `telegram_id` и API-паролю.
- `/users/me` — профиль текущего пользователя.
- `/users/me/stats` — лимиты и статистика пользователя.
- `/users/me/api-password` — выдача нового API-пароля для бота.
- `/channels` — управление каналами пользователя.
- `/posts` — очередь постов и ручные посты.
- `/generate/text` — генерация текста.
- `/generate/image` — генерация изображения.
- `/generate/text-image` — генерация текста и изображения.
- `/models` — каталог доступных моделей генерации.

## Бот

Бот умеет:

- генерировать пост по текстовому запросу;
- показывать профиль и текущие лимиты;
- переключать текстовую и графическую модели;
- показывать список подключённых каналов;
- выдавать API-пароль в личные сообщения;
- показывать человекочитаемые ошибки вместо сырых backend-ответов.

## Деплой

- Для внешнего доступа используется Tailscale Funnel.
- В webhook-режиме bot endpoint обслуживается по пути `/webhook/bot`.
- Tailscale проксирует:
  - `/` -> API на `8001`
  - `/webhook/bot` -> bot на `8080`
- Для production нужно задать `BOT_MODE=webhook`, `WEBHOOK_BASE_URL`, `WEBHOOK_SECRET`, `TAILSCALE_AUTH_KEY` и `TAILSCALE_HOSTNAME`.

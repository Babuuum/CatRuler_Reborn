# CatRuler_Reborn

CatRuler_Reborn — сервис автоматической генерации и публикации контента в VK и Telegram. Пользователь выбирает канал до генерации, получает готовый текст и изображение, а затем сохраняет пост в очередь.

## Стек и версии

- FastAPI, SQLAlchemy async, Alembic
- PostgreSQL 16, Redis 7
- Celery и aiogram
- Yandex Object Storage
- Python 3.13 (совпадает с Docker и CI)

Зависимости устанавливаются из `poetry.lock`; обновление зависимостей для запуска не требуется.

## Локальный запуск

1. Создайте `.env` на основе `.env.example` и заполните обязательные значения: `ENCRYPTION_KEY`, параметры PostgreSQL, `JWT_SECRET_KEY`, а для генерации и изображений — ключи провайдеров и Object Storage.
2. Соберите образы:

```bash
make build
```

3. Запустите базу, Redis, миграции, API, worker и beat:

```bash
make up
```

`api`, `worker` и `beat` запускаются только после успешного завершения `alembic upgrade head`. API имеет безопасный liveness endpoint `GET /health`, который возвращает только `{ "status": "ok" }`.

4. Запустите бота отдельным профилем:

```bash
make bot-up
```

Бот ждёт `api` в состоянии `healthy`, а не просто запущенный процесс. Логи:

```bash
make logs
make bot-logs
```

Остановить стек:

```bash
make down
```

Профиль `tailscale` не включён в обычный запуск. Его можно запускать только после отдельной настройки и проверки вашей tailnet-конфигурации:

```bash
docker compose --profile tailscale up -d tailscale
```

Проект сам по себе не обещает Funnel, публичный адрес или готовую маршрутизацию. Для webhook нужно отдельно настроить доступный внешний URL, `BOT_MODE=webhook`, `WEBHOOK_BASE_URL` и `WEBHOOK_SECRET`, затем проверить маршрутизацию до API/бота.

## Тестовый стек

Тесты используют отдельный PostgreSQL на `127.0.0.1:55432`. `.env` для этого не нужен:

```bash
docker compose --env-file /dev/null -f docker-compose.test.yml up -d --wait
.venv/bin/pytest -q
docker compose --env-file /dev/null -f docker-compose.test.yml down -v
```

Для Poetry:

```bash
poetry install --with dev,test --no-interaction
poetry run pytest -q
```

Тестовая база создаётся на каждый тестовый контур и удаляется после него. Не направляйте `docker-compose.test.yml` на рабочую БД.

## Переменные окружения

Секреты не выводятся в логи и не должны добавляться в git.

### Приложение и база

- `DEV_MODE`, `LOG_LEVEL` — режим и уровень логирования.
- `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES` — access token.
- `DATABASE_URL` — полная строка PostgreSQL; если не задана, используется набор `PROD_DB_*`.
- `PROD_DB_NAME`, `PROD_DB_USER`, `PROD_DB_PASSWORD`, `PROD_DB_HOST`, `PROD_DB_PORT` — параметры PostgreSQL.
- `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` — Redis для сессий и Celery.

### Бот и webhook

- `TELEGRAM_BOT_TOKEN` — токен бота.
- `INTERNAL_API_URL`, `INTERNAL_API_SHARED_SECRET` — адрес и секрет внутренних bot→API запросов.
- `BOT_MODE` — `polling` или `webhook`.
- `WEBHOOK_BASE_URL`, `WEBHOOK_PATH`, `WEBHOOK_SECRET`, `TELEGRAM_BOT_SECRET_TOKEN` — параметры webhook.

### Генерация и публикация

- `OPEN_ROUTER_API_KEY`, `HUGGING_FACE_API_KEY`, `POLLEN_API_KEY` — ключи провайдеров генерации.
- `YANDEX_ACCESS_KEY`, `YANDEX_SECRET_KEY`, `YANDEX_BUCKET_NAME` — Object Storage.
- `PUBLISH_REQUEST_TIMEOUT` — timeout внешнего запроса публикации в секундах; соединение ограничивается пятью секундами.
- `ENCRYPTION_KEY` — Fernet-ключ для зашифрованных токенов каналов.

## Каналы, тарифы и генерация

Лимит подключённых активных каналов сохраняется: Free — 1, расширенный Free — 3, Base/Pro — 999. Лимиты проверяются сервером.

В боте откройте «Мои каналы». Для VK укажите ссылку или ID сообщества и токен сообщества. Пароль VK не используется. Для Telegram укажите имя и `@username` или `chat_id`. Секрет VK вводится последним сообщением в личном чате; бот не хранит его открытым в FSM и пытается удалить сообщение после обработки.

Перед генерацией выберите активный канал. Результат содержит текст, фотографию и название выбранного канала. При создании поста выберите «Сейчас» или время в UTC. Повторное нажатие использует один ключ идемпотентности и не должно создавать дубль.

Отключение канала сохраняет историю и прекращает будущие публикации. Уже опубликованные записи во внешней платформе не удаляются.

Публикационная попытка имеет lease и владельца. При hard crash, истёкшем lease, timeout или невозможности определить результат внешнего запроса пост получает статус `unknown`. Такой результат не повторяется автоматически: сначала требуется ручная проверка провайдера.

## API

- `GET /health` — liveness без конфигурации.
- `/auth/login` — вход по Telegram ID и API-паролю.
- `/users/me`, `/users/me/stats` — профиль и лимиты.
- `/channels` — подключение, отключение и список каналов.
- `GET /assets/{asset_id}` — авторизованное получение изображения владельцем.
- `/generate/text`, `/generate/image`, `/generate/text-image` — генерация; выбор канала передаётся через `channel_id`.
- `/posts` — очередь постов, включая `asset_id`, UTC `scheduled_at` и `idempotency_key`.
- `/models` — доступные модели.

## Обновление существующей базы

Перед изменением схемы:

1. Проверьте подключение и текущую ревизию: `alembic current`.
2. Сделайте PostgreSQL backup, например `pg_dump --format=custom ... > backup.dump`; параметры берите из защищённого окружения, не записывайте их в команды/логи.
3. Проверьте свободное место и окно обслуживания.

Обновление выполняется только вперёд:

```bash
alembic upgrade head
alembic current
```

Для Docker `make up` выполняет миграции отдельным сервисом до API и worker. При ошибке миграции зависимые сервисы не стартуют. Не выполняйте destructive downgrade на рабочей базе. Если миграция остановилась, сохраните ошибку, восстановите backup только по утверждённой процедуре и повторите после исправления причины.

Новые миграции T02–T05 добавляют резервации квот, assets, публикационные lease/attempt-поля, статус `unknown` и idempotency key; старые миграции не редактируются.

## Quality gate

```bash
pytest
ruff check .
black --check .
pre-commit run -a
```

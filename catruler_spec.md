# CatRuler — Техническое задание

## Описание продукта

Сервис для автоматизированного ведения каналов в ВКонтакте и Telegram с AI-генерацией контента. Пользователь настраивает тематику и расписание, сервис генерирует и публикует посты автоматически.

Тест-кейс разработчика: паблики с котами в разных стилях.
Целевая аудитория: малый бизнес, блогеры, SMM-специалисты.

---

## Стек

- **Backend:** Python, FastAPI
- **БД:** PostgreSQL + SQLAlchemy
- **Очередь задач:** Celery + Redis
- **AI текст:** OpenRouter + Hugging Face Router (подключаемые провайдеры)
- **AI картинки:** Pollinations + Hugging Face Spaces
- **Соцсети:** ВКонтакте API, Telegram Bot API
- **Управление:** Telegram-бот (UI для пользователя)
- **Деплой:** Docker Compose

---

## Архитектура модулей

```
catruler/
├── api/                  # FastAPI роуты
├── bot/                  # Telegram-бот управления
├── core/
│   ├── config.py         # Настройки через env
│   ├── database.py       # Подключение к БД
│   └── celery_app.py     # Celery конфиг
├── models/               # SQLAlchemy модели
├── generators/
│   ├── base.py           # Абстрактный генератор
│   ├── text/
│   │   ├── openai.py
│   │   └── gemini.py
│   └── image/
│       └── flux.py       # Hugging Face Flux
├── posters/
│   ├── base.py           # Абстрактный постер
│   ├── vk.py
│   └── telegram.py
├── scheduler/            # Celery задачи и beat расписание
├── limits/               # Middleware лимитов
└── ads/                  # Модуль рекламных постов
```

---

## Модели данных

### User
```
id: UUID
telegram_id: bigint (уникальный)
plan: enum [free, base, pro]
extended_free: bool  # расширен через рекламу
api_password_hash: str | null
text_model_key: str
image_model_key: str
created_at: timestamp
```

### Channel
```
id: UUID
user_id: FK User
platform: enum [vk, telegram]
platform_channel_id: str
name: str
is_active: bool
```

### PostQueue
```
id: UUID
channel_id: FK Channel
scheduled_at: timestamp
status: enum [pending, in_progress, sent, failed]
content_type: enum [text, image, text_image]
text_prompt: text
image_prompt: text
generated_text: text
generated_image_key: str
error_message: str
```

### UsageLog
```
id: UUID
user_id: FK User
action: enum [post_generated, post_sent, image_generated]
created_at: timestamp
```

### AdPost
```
id: UUID
content: text
image_url: str
is_active: bool
```

---

## Тарифные планы

| Параметр | Free | Free Extended | Base (299₽) | Pro (1500₽) |
|----------|------|---------------|-------------|-------------|
| Соцсетей | 1 | 3 | все | все |
| Постов/день | 1 | 5 | безлимит | безлимит |
| Генерация очереди | ❌ | ❌ | ✅ | ✅ |
| SMM-инструменты | ❌ | ❌ | ✅ | ✅ |
| AI-инструменты | ❌ | ❌ | ❌ | ✅ |
| Рекламные посты | ❌ | ✅ (условие) | ❌ | ❌ |

**Free Extended** — активируется когда пользователь соглашается получать рекламные посты CatRuler. Рекламный пост вставляется каждые N постов (настраивается в конфиге).

---

## Логика лимитов

```python
# limits/checker.py
async def check_limit(user: User, action: str) -> bool:
    plan = user.plan
    extended = user.extended_free
    
    if action == "post":
        daily_count = await get_daily_posts_count(user.id)
        limit = get_post_limit(plan, extended)
        return daily_count < limit
    
    if action == "add_channel":
        channels_count = await get_channels_count(user.id)
        limit = get_channel_limit(plan, extended)
        return channels_count < limit
```

Middleware проверяет лимиты до выполнения задачи. При превышении — уведомление в бот с предложением апгрейда.

---

## Генераторы

### Архитектура

Единый класс `PostGenerator` в `generators/post_generator.py`. Провайдеры подключаются через реестры моделей — легко добавить новый без изменения ядра.

```python
# Использование
generator = PostGenerator(
    settings=settings,
    text_model=TextModels.OR_GEMINI,
    image_model=ImageModels.POLLEN_FLUX,
)
post = await generator.generate(prompt)
# post.text — текст поста
# post.image_bytes — картинка в байтах
```

### Текстовые провайдеры
- **OpenRouter** (OR_GEMINI, OR_MISTRAL) — бесплатные модели через единый интерфейс
- **HuggingFace Router** (HF_DEEPSEEK, HF_LLAMA, HF_QWEN, HF_PHI) — тот же OpenAI-совместимый интерфейс

### Картиночные провайдеры
- **Pollinations** (POLLEN_FLUX, POLLEN_FLUX_REALISM, POLLEN_TURBO) — бесплатно, без лимитов
- **HuggingFace Spaces** (HF_SD_SPACES) — Stable Diffusion через Gradio SSE

### Ключевые решения
- Один `httpx.AsyncClient` на весь `generate` — текст и картинка генерируются параллельно через `asyncio.gather`
- Картинки всегда возвращаются как `bytes` — единый тип для всех провайдеров
- `ProviderError` с именем провайдера — понятные ошибки при отладке
- `settings` передаётся в конструктор явно — удобно для тестов
- Поддержка прокси через `ProxyConfig`

### Промпты
Промпты НЕ статические. Генератор промптов принимает:
- тематику канала
- теги (стиль, персонаж, фон)
- историю последних постов (избегать повторов)
- платформу (ВК vs ТГ — разная длина и хештеги)

---

## Постеры

### Абстрактный интерфейс
```python
# posters/base.py
class BasePoster:
    async def post(self, channel_id: str, text: str, image: bytes = None) -> bool:
        raise NotImplementedError             
```

### ВКонтакте
Последовательность: getUploadServer → upload → photos.save → wall.post
Токены берутся из env через dotenv.

### Telegram
Метод: sendMessage / sendPhoto через Bot API.

---

## Celery задачи

```python
# scheduler/tasks.py

@celery.task
def generate_and_post(channel_id: str):
    # 1. Получить канал и пользователя
    # 2. Проверить лимиты
    # 3. Сгенерировать текст
    # 4. Сгенерировать картинку (если нужно)
    # 5. Проверить нужен ли рекламный пост
    # 6. Запостить
    # 7. Записать в UsageLog
    # 8. Обновить статус в PostQueue

@celery.task  
def schedule_posts():
    # Каждый час проверяет PostQueue
    # Запускает generate_and_post для pending задач
```

Celery Beat запускает `schedule_posts` каждые 5 минут.

---

## API эндпоинты (FastAPI)

### Auth
- POST `/auth/telegram` — авторизация по telegram_id, создаёт юзера если нет

### Users
- GET `/users/me` — профиль и тариф
- PATCH `/users/me` — обновить публичные настройки пользователя
- POST `/users/me/api-password` — выдать новый API-пароль для логина из бота
- GET `/users/me/stats` — статистика постов

`POST /users/me/api-password` не является публичным пользовательским вызовом:
его вызывает бот с внутренним заголовком `X-Internal-Api-Secret`. Без этого
секрета endpoint должен отклоняться.

`extended_free` read-only в публичном API и не обновляется через `PATCH /users/me`.

### Admin
- GET `/admin/users` — список всех юзеров
- PATCH `/admin/users/{id}/plan` — сменить тариф вручную
- GET `/admin/stats` — общая статистика платформы
- POST `/admin/ads` — создать рекламный пост
- PATCH `/admin/ads/{id}` — обновить рекламный пост

### Channels
- GET `/channels` — список каналов юзера
- POST `/channels` — добавить канал
- DELETE `/channels/{id}` — удалить канал
- PATCH `/channels/{id}` — обновить (активен/неактивен)

### Posts
- GET `/posts` — очередь постов (фильтры: status, channel, дата)
- POST `/posts` — создать пост вручную (текст + фото или запрос к нейронке)
- GET `/posts/{id}` — детали поста
- PATCH `/posts/{id}` — изменить дату, текст, статус
- DELETE `/posts/{id}` — удалить из очереди
- POST `/posts/{id}/retry` — повторить упавший пост

### Generate
- POST `/generate/text` — сгенерировать текст по промпту
- POST `/generate/image` — сгенерировать картинку
- POST `/generate/text-image` — сгенерировать текст и картинку

### Models
- GET `/models` — получить доступные `text_model_keys` и `image_model_keys`

### Billing
- POST `/billing/upgrade` — инициировать оплату
- POST `/billing/webhook` — webhook от ЮKassa / Telegram Payments
- GET `/billing/history` — история платежей

---

## Telegram-бот (управление)

### Хэндлеры
- `/start` → авторизация, автоматически назначается Free тариф
- Кнопка "Профиль" → тариф, лимиты и выбранные модели генерации
- В профиле можно выбрать текстовую и графическую модель из доступного каталога
- Кнопка "Мои каналы" → список подключённых каналов или инструкция перейти в веб-интерфейс
- Кнопка "Сгенерировать пост" → генерация текста и картинки
- При ошибках бот показывает человекочитаемые сообщения вместо сырых backend detail
- API-пароль бот запрашивает только через внутренний защищённый вызов API

---

## Модуль рекламы

```python
# ads/inserter.py
AD_FREQUENCY = 5  # каждые N постов вставляется рекламный

async def should_insert_ad(user_id: str) -> bool:
    count = await get_posts_since_last_ad(user_id)
    return count >= AD_FREQUENCY

async def get_active_ad() -> AdPost:
    # Возвращает случайный активный рекламный пост
```

---

## Docker Compose

```yaml
services:
  api:       # FastAPI
  bot:       # Telegram-бот
  worker:    # Celery worker
  beat:      # Celery beat
  db:        # PostgreSQL
  redis:     # Redis
```

---

## Как запустить

### Через Docker Compose

```bash
cp .env.example .env
docker compose build
docker compose up -d
docker compose run --rm migrate
docker compose --profile bot up -d bot
```

Важно:
- `INTERNAL_API_SHARED_SECRET` должен быть задан в `.env`
- bot и api должны использовать одно и то же значение `INTERNAL_API_SHARED_SECRET`
- bot ходит в API по `INTERNAL_API_URL=http://api:8000` внутри Docker сети

### Через Makefile

```bash
make build
make up
make migrate
make bot-up
```

---

## Как тестировать

```bash
poetry run pytest tests/unit/test_user_service.py -q
poetry run ruff check .
poetry run black --check .
poetry run pre-commit run -a
```

`make test` запускает `poetry run pytest -q`.

---

## Переменные окружения (.env)

```
DATABASE_URL=
REDIS_URL=
CELERY_BROKER_URL=
CELERY_RESULT_BACKEND=
TELEGRAM_BOT_TOKEN=
INTERNAL_API_URL=http://localhost:8000
INTERNAL_API_SHARED_SECRET=
JWT_SECRET_KEY=
ENCRYPTION_KEY=
OPEN_ROUTER_API_KEY=
HUGGING_FACE_API_KEY=
POLLEN_API_KEY=
YANDEX_ACCESS_KEY=
YANDEX_SECRET_KEY=
YANDEX_BUCKET_NAME=
```

Минимально для локального Docker запуска:
- `PROD_DB_NAME`
- `PROD_DB_USER`
- `PROD_DB_PASSWORD`
- `TELEGRAM_BOT_TOKEN`
- `JWT_SECRET_KEY`
- `ENCRYPTION_KEY`
- `INTERNAL_API_SHARED_SECRET`

Для AI-генерации и загрузки изображений дополнительно нужны ключи провайдеров и storage.

---

## Порядок разработки (итерации)

**Итерация 1 — Ядро**
- Модели БД (User, Channel, PostQueue, UsageLog)
- Celery + Redis
- Flux генератор картинок
- Gemini генератор текста
- Постер ВКонтакте

**Итерация 2 — Бот и лимиты**
- Telegram-бот управления
- Логика лимитов по тарифам
- Постер Telegram

**Итерация 3 — Монетизация**
- Тарифы и оплата
- Модуль рекламных постов
- Free Extended логика

**Итерация 4 — SMM инструменты (Base)**
- Генерация очереди постов
- Анализ эффективности по тегам

**Итерация 5 — AI инструменты (Pro)**
- Анализ трендов
- Адаптация под аудиторию
- QA контент

---

## Маркер готовности

Паблики с котами работают автономно 7 дней без ручного вмешательства, посты выходят по расписанию, лайки растут.
```

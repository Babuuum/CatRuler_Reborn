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
- **AI текст:** OpenAI GPT / Gemini (подключаемые модули)
- **AI картинки:** Flux через Hugging Face Inference API
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
status: enum [pending, sent, failed]
content_type: enum [text, image, text_image]
prompt_used: text
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
- PATCH `/users/me` — обновить настройки
- GET `/users/me/stats` — статистика постов

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
- POST `/generate/queue` — сгенерировать очередь постов на N дней (Base+)

### Billing
- POST `/billing/upgrade` — инициировать оплату
- POST `/billing/webhook` — webhook от ЮKassa / Telegram Payments
- GET `/billing/history` — история платежей

---

## Telegram-бот (управление)

### Хэндлеры
- `/start` → авторизация, автоматически назначается Free тариф
- Кнопка "Личный кабинет" → тариф, каналы, лимиты
- Кнопка "Добавить канал" → выбор платформы (ВК/ТГ), ввод ID канала
- Кнопка "Создать пост" → выбор: загрузить фото или нейронка → выбор соцсети → выбор даты → подтверждение
- Кнопка "Очередь" → список запланированных постов, удалить или перенести
- Кнопка "Статистика" → посты за период, успешные/упавшие
- Кнопка "Улучшить тариф" → описание планов, инициировать оплату
- Кнопка "Расширить бесплатно" → объяснение Free Extended, согласие на рекламу

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
  app:       # FastAPI
  bot:       # Telegram-бот
  worker:    # Celery worker
  beat:      # Celery beat
  db:        # PostgreSQL
  redis:     # Redis
```

---

## Переменные окружения (.env)

```
DATABASE_URL=
REDIS_URL=
OPENAI_API_KEY=
GEMINI_API_KEY=
HUGGINGFACE_API_KEY=
VK_ACCESS_TOKEN=
VK_TOKEN=
VK_GROUP_ID=
VK_VERSION=
TELEGRAM_BOT_TOKEN=
AD_FREQUENCY=5
```

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

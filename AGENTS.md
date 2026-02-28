# CatRuler_Reborn — AGENTS.md

## Project context

CatRuler_Reborn is a SaaS for automated social media management with AI content
generation. Users connect VK and Telegram channels, configure schedules, and the
system generates and publishes posts automatically.

Stack: FastAPI, PostgreSQL, SQLAlchemy (async), Celery + Redis, aiogram,
httpx, Alembic, Yandex Object Storage.

## Working agreement

- Before doing anything: restate the task in 5-10 bullets + list missing info.
- Do not invent missing project details. Ask minimal questions.
- No new production dependencies unless explicitly requested.
- No refactors "for beauty" unless requested — prefer minimal diffs.
- Never log or print secrets, tokens, or encryption keys.
- Always end with: changed files list, how to verify, risks/edge cases.

## Architecture rules

- Routes: HTTP only — accept request, validate, call service, return response.
  No business logic, no DB access directly in routes.
- Services: business logic only. Call repositories for DB, call external
  clients for APIs. No direct SQLAlchemy queries.
- Repositories: all DB queries live here. Use async SQLAlchemy sessions.
  Return domain objects, not raw rows.
- Celery tasks: call services directly, never call HTTP endpoints internally.
  Always use IDs as arguments, fetch data inside the task.
- Generators/Posters: accessed only through their registry interfaces.
  Never instantiate providers directly outside of PostGenerator.

## Forbidden zones — do not touch without explicit instruction

- `core/crypto.py` — encryption logic, changes break all stored tokens
- `alembic/versions/` — never edit existing migration files
- `.env` — never read, never modify, never log its contents
- `models/` — discuss schema changes before implementing, always create migration

## Security rules

- Encrypted fields (VK/TG tokens): always use crypto service, never store plain
- User can only access their own resources — always filter by user_id
- Plan limits: check server-side on every request, never trust client data
- Admin endpoints: always verify role === "admin" explicitly

## Quality gate (always after changes)

```bash
pytest
ruff check .
black .
pre-commit run -a
```

## Celery task rules

- Every task must have: max_retries, soft_time_limit, time_limit
- Handle SoftTimeLimitExceeded explicitly
- Log failures with context (task_id, user_id, channel_id where applicable)
- Tasks must be idempotent — safe to retry

## DB rules

- Always use eager loading (selectinload/joinedload) when accessing relationships in loops
- New columns: nullable=True or with default — never add NOT NULL without default to existing table
- Run $db-migrate skill for any schema change

## External API rules

- All httpx calls: explicit timeout (connect=5, read=30)
- Always handle ProviderError — never let provider failures crash the request
- VK and Telegram API errors: log with context, return graceful error to user
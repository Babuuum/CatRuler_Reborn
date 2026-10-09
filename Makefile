.PHONY: build up down migrate logs test bot-up bot-logs

build:
	docker compose build

up:
	docker compose up -d db redis migrate api worker beat

down:
	docker compose down

migrate:
	docker compose up --abort-on-container-exit --exit-code-from migrate migrate

logs:
	docker compose logs -f

bot-up:
	docker compose --profile bot up -d bot

bot-logs:
	docker compose logs -f bot

test:
	poetry run pytest -q

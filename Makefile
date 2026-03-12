.PHONY: build up down migrate logs test bot-up bot-logs

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

migrate:
	docker compose run --rm migrate

logs:
	docker compose logs -f

bot-up:
	docker compose --profile bot up -d bot

bot-logs:
	docker compose logs -f bot

test:
	poetry run pytest -q

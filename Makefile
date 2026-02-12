.PHONY: help build up down restart logs shell migrate makemigrations test coverage clean deploy-prod backup

# Default target
help:
	@echo "BoatRental Management Commands"
	@echo "================================"
	@echo ""
	@echo "Development:"
	@echo "  make build          - Build Docker images"
	@echo "  make up             - Start all services"
	@echo "  make down           - Stop all services"
	@echo "  make restart        - Restart all services"
	@echo "  make logs           - View logs (all services)"
	@echo "  make logs-web       - View Django logs"
	@echo "  make logs-celery    - View Celery worker logs"
	@echo "  make shell          - Open Django shell"
	@echo "  make bash           - Open bash in web container"
	@echo ""
	@echo "Database:"
	@echo "  make migrate        - Run database migrations"
	@echo "  make makemigrations - Create new migrations"
	@echo "  make superuser      - Create Django superuser"
	@echo "  make dbshell        - Open PostgreSQL shell"
	@echo "  make backup         - Backup database"
	@echo "  make restore        - Restore database from backup"
	@echo ""
	@echo "Testing:"
	@echo "  make test           - Run all tests"
	@echo "  make test-app       - Run tests for specific app (APP=boats)"
	@echo "  make coverage       - Run tests with coverage report"
	@echo "  make lint           - Run code linters"
	@echo ""
	@echo "Boat Parsing:"
	@echo "  make parse-test     - Parse 5 boats (sync, test)"
	@echo "  make parse-async    - Parse boats async (LIMIT=100)"
	@echo "  make parse-turkey   - Parse Turkey boats"
	@echo "  make dump-boats     - Dump parsed boats to JSON"
	@echo "  make clear-boats    - Clear all parsed boats"
	@echo ""
	@echo "i18n:"
	@echo "  make messages       - Generate translation messages"
	@echo "  make compilemessages - Compile translation files"
	@echo ""
	@echo "Production:"
	@echo "  make deploy-prod    - Deploy to production"
	@echo "  make setup-ssl      - Setup SSL certificates"
	@echo "  make prod-logs      - View production logs"
	@echo "  make prod-status    - Check production services status"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean          - Remove temporary files"
	@echo "  make clean-all      - Remove all generated files (images, cache)"
	@echo "  make requirements   - Update requirements.txt"
	@echo ""

# Development
build:
	docker-compose build

up:
	docker-compose up -d
	@echo "Services started. Access at http://localhost:8000"

down:
	docker-compose down

restart:
	docker-compose restart

logs:
	docker-compose logs -f

logs-web:
	docker-compose logs -f web

logs-celery:
	docker-compose logs -f celery_worker

shell:
	docker-compose exec web python manage.py shell

bash:
	docker-compose exec web bash

# Database
migrate:
	docker-compose exec web python manage.py migrate

makemigrations:
	docker-compose exec web python manage.py makemigrations

superuser:
	docker-compose exec web python manage.py createsuperuser

dbshell:
	docker-compose exec db psql -U admin -d boat_rental

backup:
	@mkdir -p backups
	@BACKUP_FILE=backups/db_backup_$$(date +%Y%m%d_%H%M%S).sql; \
	docker-compose exec -T db pg_dump -U admin boat_rental > $$BACKUP_FILE; \
	echo "Database backed up to $$BACKUP_FILE"

restore:
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make restore FILE=backups/db_backup_20260101_120000.sql"; \
		exit 1; \
	fi
	@echo "Restoring database from $(FILE)..."
	docker-compose exec -T db psql -U admin boat_rental < $(FILE)
	@echo "Database restored successfully"

# Testing
test:
	docker-compose exec web python manage.py test

test-app:
	@if [ -z "$(APP)" ]; then \
		echo "Usage: make test-app APP=boats"; \
		exit 1; \
	fi
	docker-compose exec web python manage.py test $(APP)

coverage:
	docker-compose exec web coverage run --source='.' manage.py test
	docker-compose exec web coverage report
	docker-compose exec web coverage html
	@echo "Coverage report available at htmlcov/index.html"

lint:
	docker-compose exec web flake8 boats accounts boat_rental --max-line-length=120
	docker-compose exec web pylint boats accounts --disable=C0111,C0103

# Boat Parsing
parse-test:
	docker-compose exec web python manage.py parse_all_boats --sync --limit 5

parse-async:
	@LIMIT=$${LIMIT:-100}; \
	docker-compose exec web python manage.py parse_all_boats --async --limit $$LIMIT --batch-size 50

parse-turkey:
	docker-compose exec web python manage.py parse_all_boats --async --destination turkey --max-pages 5

dump-boats:
	docker-compose exec web python manage.py dump_parsed_boats

clear-boats:
	@read -p "Are you sure you want to clear all parsed boats? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker-compose exec web python manage.py clear_parsed_boats; \
	fi

# i18n
messages:
	docker-compose exec web python manage.py makemessages -l ru
	docker-compose exec web python manage.py makemessages -l en
	docker-compose exec web python manage.py makemessages -l de
	docker-compose exec web python manage.py makemessages -l es
	docker-compose exec web python manage.py makemessages -l fr

compilemessages:
	docker-compose exec web python manage.py compilemessages

# Production
deploy-prod:
	@if [ ! -f .env ]; then \
		echo "Error: .env not found"; \
		echo "Copy .env.example to .env and configure it"; \
		exit 1; \
	fi
	./deploy.sh

setup-ssl:
	@if [ "$$EUID" -ne 0 ]; then \
		echo "Please run with sudo: sudo make setup-ssl"; \
		exit 1; \
	fi
	./setup-ssl.sh

prod-logs:
	docker-compose -f docker-compose.prod.yml logs -f

prod-status:
	docker-compose -f docker-compose.prod.yml ps

# Maintenance
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.log" -delete
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage

clean-all: clean
	rm -rf staticfiles/*
	rm -rf media/boats/boats/*
	@echo "Warning: This will remove all cached boat data"
	@read -p "Continue? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker-compose exec web python manage.py clear_parsed_boats; \
	fi

requirements:
	docker-compose exec web pip freeze > requirements.txt
	@echo "requirements.txt updated"

# Quick development shortcuts
dev: up logs-web

stop: down

refresh: down up logs-web

check:
	docker-compose exec web python manage.py check --deploy

collectstatic:
	docker-compose exec web python manage.py collectstatic --noinput

# Database reset (DANGEROUS!)
reset-db:
	@echo "WARNING: This will delete ALL data in the database!"
	@read -p "Are you ABSOLUTELY sure? Type 'yes' to continue: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		docker-compose down; \
		docker volume rm rent_django_postgres_data || true; \
		docker-compose up -d; \
		sleep 5; \
		make migrate; \
		make superuser; \
	else \
		echo "Cancelled."; \
	fi

# =============================================================================
# CRM Platform - Makefile
# =============================================================================
# Comprehensive build, run, and management commands for the CRM platform.
#
# Usage: make <target> [OPTIONS]
#
# Quick Start:
#   make install    # Install all dependencies
#   make dev        # Run all services in development mode
#   make help       # Show all available commands
# =============================================================================

# Configuration
SHELL := /bin/bash
.DEFAULT_GOAL := help
.PHONY: help install dev run stop clean test lint format docker-up docker-down

# Colors for output
BLUE := \033[34m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
NC := \033[0m # No Color

# Directories
ROOT_DIR := $(shell pwd)
SALES_DIR := $(ROOT_DIR)/src/sales-module
UI_DIR := $(ROOT_DIR)/src/unified-ui
ASSETS_DIR := $(ROOT_DIR)/src/asset-management
DOCKER_DIR := $(ROOT_DIR)/docker
DOCS_DIR := $(ROOT_DIR)/docs

# Default ports (can be overridden: make dev SALES_PORT=9000)
SALES_PORT ?= 8000
UI_PORT ?= 3005
ASSETS_PORT ?= 8001

# Environment (development, production, local)
ENV ?= development

# Docker compose file
COMPOSE_FILE ?= docker/docker-compose.local.yml
ENV_FILE ?= .env.secrets

# Python interpreter
PYTHON ?= python3

# =============================================================================
# HELP
# =============================================================================

help: ## Show this help message
	@echo ""
	@echo "$(BLUE)CRM Platform - Available Commands$(NC)"
	@echo "===================================="
	@echo ""
	@echo "$(GREEN)Quick Start:$(NC)"
	@echo "  make install        Install all dependencies"
	@echo "  make dev            Run all services (development)"
	@echo "  make stop           Stop all services"
	@echo ""
	@echo "$(GREEN)Service Management:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(BLUE)%-18s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)Options (override with VAR=value):$(NC)"
	@echo "  SALES_PORT     Sales module port (default: 8000)"
	@echo "  UI_PORT        Unified UI port (default: 3005)"
	@echo "  ASSETS_PORT    Asset management port (default: 8001)"
	@echo "  ENV            Environment: local|development|production (default: development)"
	@echo "  COMPOSE_FILE   Docker compose file (default: docker-compose.local.yml)"
	@echo "  ENV_FILE       Environment file (default: .env.secrets)"
	@echo ""
	@echo "$(GREEN)Examples:$(NC)"
	@echo "  make dev SALES_PORT=9000 UI_PORT=4000"
	@echo "  make docker-up COMPOSE_FILE=docker-compose.yml"
	@echo "  make test-sales VERBOSE=1"
	@echo ""

# =============================================================================
# INSTALLATION
# =============================================================================

install: install-sales install-ui install-assets ## Install all dependencies
	@echo "$(GREEN)All dependencies installed!$(NC)"

install-sales: ## Install sales-module dependencies
	@echo "$(BLUE)Installing sales-module dependencies...$(NC)"
	@cd $(SALES_DIR) && $(PYTHON) -m pip install -r requirements.txt -q
	@echo "$(GREEN)sales-module dependencies installed$(NC)"

install-ui: ## Install unified-ui dependencies
	@echo "$(BLUE)Installing unified-ui dependencies...$(NC)"
	@cd $(UI_DIR) && $(PYTHON) -m pip install -r requirements.txt -q
	@echo "$(GREEN)unified-ui dependencies installed$(NC)"

install-assets: ## Install asset-management dependencies
	@echo "$(BLUE)Installing asset-management dependencies...$(NC)"
	@cd $(ASSETS_DIR) && $(PYTHON) -m pip install -r requirements.txt -q
	@echo "$(GREEN)asset-management dependencies installed$(NC)"

install-dev: install ## Install dependencies + dev tools
	@echo "$(BLUE)Installing development tools...$(NC)"
	@$(PYTHON) -m pip install ruff pytest pytest-cov pre-commit -q
	@echo "$(GREEN)Development tools installed$(NC)"

venv: ## Create virtual environments
	@echo "$(BLUE)Creating virtual environments...$(NC)"
	@cd $(SALES_DIR) && $(PYTHON) -m venv venv
	@cd $(UI_DIR) && $(PYTHON) -m venv venv
	@echo "$(GREEN)Virtual environments created$(NC)"
	@echo "Activate with: source src/sales-module/venv/bin/activate"

# =============================================================================
# DEVELOPMENT - LOCAL PYTHON
# =============================================================================

dev: ## Run all services in development mode
	@$(PYTHON) run_all_services.py --env $(ENV) --sales-port $(SALES_PORT) --ui-port $(UI_PORT) --assets-port $(ASSETS_PORT)

dev-sales: run-sales ## Alias for run-sales
run-sales: ## Run only sales-module
	@echo "$(BLUE)Starting sales-module on port $(SALES_PORT)...$(NC)"
	@cd $(SALES_DIR) && PORT=$(SALES_PORT) ENVIRONMENT=$(ENV) $(PYTHON) run_service.py

dev-ui: run-ui ## Alias for run-ui
run-ui: ## Run only unified-ui
	@echo "$(BLUE)Starting unified-ui on port $(UI_PORT)...$(NC)"
	@cd $(UI_DIR) && PORT=$(UI_PORT) ENVIRONMENT=$(ENV) SALES_BOT_URL=http://localhost:$(SALES_PORT) $(PYTHON) run_service.py

dev-assets: run-assets ## Alias for run-assets
run-assets: ## Run only asset-management
	@echo "$(BLUE)Starting asset-management on port $(ASSETS_PORT)...$(NC)"
	@cd $(ASSETS_DIR) && PORT=$(ASSETS_PORT) ENVIRONMENT=$(ENV) $(PYTHON) run_service.py

run-bg: ## Run all services in background
	@$(PYTHON) run_all_services.py --env $(ENV) --sales-port $(SALES_PORT) --ui-port $(UI_PORT) --assets-port $(ASSETS_PORT) --background

run-fg: ## Run all services in foreground with logs
	@$(PYTHON) run_all_services.py --env $(ENV) --sales-port $(SALES_PORT) --ui-port $(UI_PORT) --assets-port $(ASSETS_PORT) --foreground

# =============================================================================
# DOCKER
# =============================================================================

docker-up: ## Start services with Docker Compose
	@echo "$(BLUE)Starting Docker services...$(NC)"
	@docker-compose -f $(COMPOSE_FILE) --env-file $(ENV_FILE) up -d
	@echo "$(GREEN)Services started!$(NC)"
	@make docker-status

docker-up-build: ## Build and start Docker services
	@echo "$(BLUE)Building and starting Docker services...$(NC)"
	@docker-compose -f $(COMPOSE_FILE) --env-file $(ENV_FILE) up -d --build

docker-up-fg: ## Start Docker services in foreground
	@docker-compose -f $(COMPOSE_FILE) --env-file $(ENV_FILE) up

docker-down: ## Stop Docker services
	@echo "$(BLUE)Stopping Docker services...$(NC)"
	@docker-compose -f $(COMPOSE_FILE) down
	@echo "$(GREEN)Services stopped$(NC)"

docker-down-v: ## Stop Docker services and remove volumes
	@echo "$(YELLOW)Stopping services and removing volumes...$(NC)"
	@docker-compose -f $(COMPOSE_FILE) down -v

docker-restart: docker-down docker-up ## Restart Docker services

docker-rebuild: ## Rebuild and restart Docker services
	@docker-compose -f $(COMPOSE_FILE) --env-file $(ENV_FILE) up -d --build --force-recreate

docker-logs: ## View Docker logs (all services)
	@docker-compose -f $(COMPOSE_FILE) logs -f

docker-logs-sales: ## View sales-module Docker logs
	@docker-compose -f $(COMPOSE_FILE) logs -f proposal-bot

docker-logs-ui: ## View unified-ui Docker logs
	@docker-compose -f $(COMPOSE_FILE) logs -f unified-ui

docker-logs-assets: ## View asset-management Docker logs
	@docker-compose -f $(COMPOSE_FILE) logs -f asset-management

docker-status: ## Show Docker container status
	@echo "$(BLUE)Container Status:$(NC)"
	@docker-compose -f $(COMPOSE_FILE) ps

docker-shell-sales: ## Shell into sales-module container
	@docker exec -it proposal-bot bash

docker-shell-ui: ## Shell into unified-ui container
	@docker exec -it unified-ui bash

docker-shell-assets: ## Shell into asset-management container
	@docker exec -it asset-management bash

docker-build-sales: ## Build only sales-module image
	@echo "$(BLUE)Building sales-module image...$(NC)"
	@docker build -t proposal-bot $(SALES_DIR)

docker-build-ui: ## Build only unified-ui image
	@echo "$(BLUE)Building unified-ui image...$(NC)"
	@docker build -t unified-ui $(UI_DIR)

docker-build-assets: ## Build only asset-management image
	@echo "$(BLUE)Building asset-management image...$(NC)"
	@docker build -t asset-management $(ASSETS_DIR)

docker-prod: ## Start production Docker compose
	@docker-compose -f docker/docker-compose.yml --env-file $(ENV_FILE) up -d

# =============================================================================
# TESTING
# =============================================================================

test: test-sales test-assets ## Run all tests

test-sales: ## Run sales-module tests
	@echo "$(BLUE)Running sales-module tests...$(NC)"
	@cd $(SALES_DIR) && $(PYTHON) -m pytest $(if $(VERBOSE),-v,) $(if $(COV),--cov=. --cov-report=html,)

test-ui: ## Run unified-ui tests
	@echo "$(BLUE)Running unified-ui tests...$(NC)"
	@cd $(UI_DIR) && $(PYTHON) -m pytest $(if $(VERBOSE),-v,)

test-assets: ## Run asset-management tests
	@echo "$(BLUE)Running asset-management tests...$(NC)"
	@cd $(ASSETS_DIR) && $(PYTHON) -m pytest $(if $(VERBOSE),-v,) $(if $(COV),--cov=. --cov-report=html,)

test-cov: ## Run tests with coverage report
	@make test-sales COV=1
	@echo "$(GREEN)Coverage report: src/sales-module/htmlcov/index.html$(NC)"

test-watch: ## Run tests in watch mode
	@cd $(SALES_DIR) && $(PYTHON) -m pytest --watch

# =============================================================================
# CODE QUALITY
# =============================================================================

lint: lint-sales lint-ui lint-assets ## Lint all code

lint-sales: ## Lint sales-module code
	@echo "$(BLUE)Linting sales-module...$(NC)"
	@cd $(SALES_DIR) && ruff check .

lint-ui: ## Lint unified-ui code
	@echo "$(BLUE)Linting unified-ui...$(NC)"
	@cd $(UI_DIR) && ruff check .

lint-assets: ## Lint asset-management code
	@echo "$(BLUE)Linting asset-management...$(NC)"
	@cd $(ASSETS_DIR) && ruff check .

lint-fix: ## Lint and auto-fix issues
	@echo "$(BLUE)Linting and fixing...$(NC)"
	@cd $(SALES_DIR) && ruff check . --fix
	@cd $(UI_DIR) && ruff check . --fix
	@cd $(ASSETS_DIR) && ruff check . --fix

format: ## Format all code
	@echo "$(BLUE)Formatting code...$(NC)"
	@cd $(SALES_DIR) && ruff format .
	@cd $(UI_DIR) && ruff format .
	@cd $(ASSETS_DIR) && ruff format .

check: lint test ## Run all checks (lint + test)

pre-commit: ## Run pre-commit hooks
	@pre-commit run --all-files

# =============================================================================
# DATABASE
# =============================================================================

db-migrate: ## Run database migrations (placeholder)
	@echo "$(BLUE)Database migrations...$(NC)"
	@echo "Run SQL files in Supabase SQL Editor:"
	@echo "  - src/unified-ui/db/migrations/*.sql for UI Supabase"
	@echo "  - src/sales-module/db/migrations/salesbot/*.sql for SalesBot Supabase"

db-seed: ## Seed database (placeholder)
	@echo "$(BLUE)Seeding database...$(NC)"
	@cd $(SALES_DIR) && $(PYTHON) db/scripts/seed_locations.py --dry-run

db-seed-run: ## Actually seed database
	@cd $(SALES_DIR) && $(PYTHON) db/scripts/seed_locations.py

# =============================================================================
# HEALTH & STATUS
# =============================================================================

health: ## Check health of all services
	@echo "$(BLUE)Checking service health...$(NC)"
	@echo ""
	@echo "Sales Module ($(SALES_PORT)):"
	@curl -sf http://localhost:$(SALES_PORT)/health | jq . || echo "$(RED)Not running$(NC)"
	@echo ""
	@echo "Unified UI ($(UI_PORT)):"
	@curl -sf http://localhost:$(UI_PORT)/health | jq . || echo "$(RED)Not running$(NC)"
	@echo ""
	@echo "Asset Management ($(ASSETS_PORT)):"
	@curl -sf http://localhost:$(ASSETS_PORT)/health | jq . || echo "$(RED)Not running$(NC)"

health-sales: ## Check sales-module health
	@curl -sf http://localhost:$(SALES_PORT)/health | jq . || echo "$(RED)Sales module not running$(NC)"

health-ui: ## Check unified-ui health
	@curl -sf http://localhost:$(UI_PORT)/health | jq . || echo "$(RED)Unified UI not running$(NC)"

health-assets: ## Check asset-management health
	@curl -sf http://localhost:$(ASSETS_PORT)/health | jq . || echo "$(RED)Asset management not running$(NC)"

status: health ## Alias for health

ps: ## Show running Python processes
	@echo "$(BLUE)Running CRM processes:$(NC)"
	@ps aux | grep -E "(run_service|uvicorn)" | grep -v grep || echo "No services running"

# =============================================================================
# UTILITIES
# =============================================================================

clean: ## Clean up generated files
	@echo "$(BLUE)Cleaning up...$(NC)"
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name ".coverage" -delete 2>/dev/null || true
	@echo "$(GREEN)Cleanup complete$(NC)"

clean-docker: ## Clean up Docker resources
	@echo "$(YELLOW)Cleaning Docker resources...$(NC)"
	@docker-compose -f $(COMPOSE_FILE) down -v --rmi local 2>/dev/null || true
	@docker system prune -f
	@echo "$(GREEN)Docker cleanup complete$(NC)"

clean-all: clean clean-docker ## Clean everything

logs: ## View recent logs from both services
	@echo "$(BLUE)Recent logs...$(NC)"
	@echo "Use 'make docker-logs' for Docker or run services with 'make run-fg'"

env-check: ## Check environment configuration
	@echo "$(BLUE)Environment Check$(NC)"
	@echo "================="
	@echo ""
	@echo "ENV_FILE: $(ENV_FILE)"
	@test -f $(ENV_FILE) && echo "$(GREEN)$(ENV_FILE) exists$(NC)" || echo "$(RED)$(ENV_FILE) not found! Copy from .env.example$(NC)"
	@echo ""
	@echo "Required variables:"
	@test -f $(ENV_FILE) && grep -q "PROXY_SECRET" $(ENV_FILE) && echo "  $(GREEN)PROXY_SECRET: Set$(NC)" || echo "  $(RED)PROXY_SECRET: Missing$(NC)"
	@test -f $(ENV_FILE) && grep -q "SALESBOT_DEV_SUPABASE_URL" $(ENV_FILE) && echo "  $(GREEN)SALESBOT_DEV_SUPABASE_URL: Set$(NC)" || echo "  $(RED)SALESBOT_DEV_SUPABASE_URL: Missing$(NC)"
	@test -f $(ENV_FILE) && grep -q "UI_DEV_SUPABASE_URL" $(ENV_FILE) && echo "  $(GREEN)UI_DEV_SUPABASE_URL: Set$(NC)" || echo "  $(RED)UI_DEV_SUPABASE_URL: Missing$(NC)"
	@test -f $(ENV_FILE) && grep -q "OPENAI_API_KEY" $(ENV_FILE) && echo "  $(GREEN)OPENAI_API_KEY: Set$(NC)" || echo "  $(RED)OPENAI_API_KEY: Missing$(NC)"

setup: ## Initial setup for new developers
	@echo "$(BLUE)CRM Platform Setup$(NC)"
	@echo "==================="
	@echo ""
	@test -f $(ENV_FILE) || (cp .env.example $(ENV_FILE) && echo "$(GREEN)Created $(ENV_FILE) from template$(NC)")
	@make install
	@echo ""
	@echo "$(GREEN)Setup complete!$(NC)"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Edit $(ENV_FILE) with your credentials"
	@echo "  2. Run: make dev"
	@echo ""

# =============================================================================
# QUICK SHORTCUTS
# =============================================================================

up: docker-up ## Shortcut for docker-up
down: docker-down ## Shortcut for docker-down
restart: docker-restart ## Shortcut for docker-restart
build: docker-up-build ## Shortcut for docker-up-build
logs-sales: docker-logs-sales ## Shortcut for docker-logs-sales
logs-ui: docker-logs-ui ## Shortcut for docker-logs-ui
logs-assets: docker-logs-assets ## Shortcut for docker-logs-assets

# =============================================================================
# PRODUCTION
# =============================================================================

prod-up: ## Start production services
	@echo "$(YELLOW)Starting PRODUCTION services...$(NC)"
	@docker-compose -f docker/docker-compose.yml up -d
	@make docker-status COMPOSE_FILE=docker/docker-compose.yml

prod-down: ## Stop production services
	@docker-compose -f docker/docker-compose.yml down

prod-logs: ## View production logs
	@docker-compose -f docker/docker-compose.yml logs -f

# =============================================================================
# RENDER DEPLOYMENT
# =============================================================================

deploy-sales: ## Deploy sales-module to Render
	@echo "$(BLUE)Deploying sales-module to Render...$(NC)"
	@cd $(SALES_DIR) && render blueprint apply

deploy-ui: ## Deploy unified-ui to Render
	@echo "$(BLUE)Deploying unified-ui to Render...$(NC)"
	@cd $(UI_DIR) && render blueprint apply

deploy-assets: ## Deploy asset-management to Render
	@echo "$(BLUE)Deploying asset-management to Render...$(NC)"
	@cd $(ASSETS_DIR) && render blueprint apply

deploy: deploy-sales deploy-ui deploy-assets ## Deploy all services to Render

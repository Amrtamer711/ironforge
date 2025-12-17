# Development Guide

Complete guide for setting up and developing the CRM platform locally.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Make Commands Reference](#make-commands-reference)
- [Python Service Runner](#python-service-runner)
- [IDE Setup](#ide-setup)
- [Per-Service Development](#per-service-development)
- [Docker Development](#docker-development)
- [Database Setup](#database-setup)
- [Testing](#testing)
- [API Development](#api-development)
- [Frontend Development](#frontend-development)
- [LLM Provider Configuration](#llm-provider-configuration)
- [Environment Variables Reference](#environment-variables-reference)
- [Debugging Tips](#debugging-tips)
- [Code Style](#code-style)
- [Project Structure](#project-structure)
- [Common Patterns](#common-patterns)
- [Related Documentation](#related-documentation)

---

## Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| Python | 3.11+ | Runtime for both services |
| pip | Latest | Package management |
| Git | Latest | Version control |
| Docker | Optional | Containerized development |
| LibreOffice | Optional | PDF conversion in sales-module |
| Node.js | 18+ | Only if modifying frontend JS |

### macOS

```bash
# Install Python 3.11
brew install python@3.11

# Install LibreOffice (for PDF conversion)
brew install --cask libreoffice
```

### Ubuntu/Debian

```bash
# Install Python 3.11
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip

# Install LibreOffice
sudo apt install libreoffice
```

### Windows

1. Download Python 3.11 from python.org
2. Download LibreOffice from libreoffice.org
3. Ensure both are in PATH

---

## Quick Start

### 1. Clone Repository

```bash
git clone <repo-url>
cd CRM
```

### 2. Environment Setup

```bash
# Copy environment template
cp .env.example .env.secrets

# Edit with your credentials:
# - Supabase URLs and keys (UI and SalesBot projects)
# - OpenAI API key
# - Google API key (for Gemini)
# - PROXY_SECRET (generate a secure random string)
```

**Minimum required for local development:**
```env
# Shared
PROXY_SECRET=your-secure-random-string

# Sales Module
SALESBOT_DEV_SUPABASE_URL=https://xxx.supabase.co
SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY=eyJ...
OPENAI_API_KEY=sk-...

# Unified UI
UI_DEV_SUPABASE_URL=https://yyy.supabase.co
UI_DEV_SUPABASE_ANON_KEY=eyJ...
UI_DEV_SUPABASE_SERVICE_ROLE_KEY=eyJ...
```

### 3. Run All Services

**Using Make (Recommended):**
```bash
make install   # Install all dependencies
make dev       # Run all services
```

**Using Python directly:**
```bash
python run_all_services.py
```

**Access points:**
| Service | URL | Description |
|---------|-----|-------------|
| Unified UI | http://localhost:3005 | Frontend + Gateway |
| Proposal Bot API | http://localhost:8000 | Backend API |
| Swagger Docs | http://localhost:8000/docs | Interactive API docs |

---

## Make Commands Reference

The project includes a comprehensive Makefile for service management. Run `make help` for full list.

### Service Management

```bash
# Run services
make dev                      # Run all services (development mode)
make run-sales                # Run only sales-module
make run-ui                   # Run only unified-ui
make run-fg                   # Run with interleaved logs

# Custom ports
make dev SALES_PORT=9000 UI_PORT=4000

# Different environment
make dev ENV=production
```

### Docker Commands

```bash
# Start/stop
make docker-up                # Start Docker services
make docker-down              # Stop Docker services
make docker-restart           # Restart services

# Build
make build                    # Build and start (--build)
make docker-rebuild           # Force rebuild all

# Logs
make docker-logs              # View all logs
make logs-sales               # Sales module logs only
make logs-ui                  # Unified UI logs only

# Status & debugging
make docker-status            # Show container status
make docker-shell-sales       # Shell into sales container
make docker-shell-ui          # Shell into UI container

# Custom compose file
make docker-up COMPOSE_FILE=docker/docker-compose.yml
```

### Testing & Code Quality

```bash
# Testing
make test                     # Run all tests
make test-sales               # Sales module tests only
make test-cov                 # Tests with coverage report

# Linting
make lint                     # Lint all code
make lint-fix                 # Auto-fix lint issues
make format                   # Format all code

# Combined checks
make check                    # lint + test
make pre-commit               # Run pre-commit hooks
```

### Health & Status

```bash
make health                   # Check health of all services
make health-sales             # Check sales-module
make health-ui                # Check unified-ui
make ps                       # Show running processes
make status                   # Alias for health
```

### Installation & Cleanup

```bash
make install                  # Install all dependencies
make install-dev              # Install + dev tools
make venv                     # Create virtual environments
make setup                    # Full initial setup

make clean                    # Clean generated files
make clean-docker             # Clean Docker resources
make clean-all                # Clean everything
```

### Makefile Variables

Override any variable at runtime:

| Variable | Default | Description |
|----------|---------|-------------|
| `SALES_PORT` | 8000 | Sales module external port |
| `UI_PORT` | 3005 | Unified UI external port |
| `ENV` | development | Environment mode |
| `COMPOSE_FILE` | docker/docker-compose.local.yml | Docker compose file |
| `ENV_FILE` | .env.secrets | Environment file |
| `PYTHON` | python3 | Python interpreter |

**Examples:**
```bash
make dev SALES_PORT=9000 UI_PORT=4000
make docker-up COMPOSE_FILE=docker/docker-compose.yml ENV_FILE=.env.production
make test-sales VERBOSE=1 COV=1
```

---

## Python Service Runner

The `run_all_services.py` script provides flexible service control:

### Basic Usage

```bash
# Run all services (default)
python run_all_services.py

# Run specific service
python run_all_services.py --sales-only
python run_all_services.py --ui-only

# Custom ports
python run_all_services.py --sales-port 9000 --ui-port 4000

# Environment mode
python run_all_services.py --env production
```

### Execution Modes

```bash
# Default (quiet output)
python run_all_services.py

# Foreground (interleaved logs from all services)
python run_all_services.py --foreground

# Background (with log files)
python run_all_services.py --background --log-dir ./logs
```

### Additional Options

```bash
# Wait for health checks
python run_all_services.py --health-check

# Custom timeout
python run_all_services.py --health-check --timeout 60

# Skip banner
python run_all_services.py --no-banner

# Check status only
python run_all_services.py --status
```

### All Flags

| Flag | Short | Description |
|------|-------|-------------|
| `--sales-only` | | Run only sales module |
| `--ui-only` | | Run only unified UI |
| `--sales-port` | | Sales module port (default: 8000) |
| `--ui-port` | | Unified UI port (default: 3005) |
| `--env` | `-e` | Environment: development, production, local |
| `--foreground` | `-f` | Show interleaved logs |
| `--background` | `-b` | Run in background |
| `--health-check` | | Wait for health checks |
| `--timeout` | | Health check timeout (default: 30s) |
| `--log-dir` | | Log directory for background mode |
| `--no-banner` | | Skip startup banner |
| `--status` | | Check service status and exit |

### Environment Variables

Can also be set via environment:

```bash
export SALES_PORT=9000
export UI_PORT=4000
export ENVIRONMENT=production
python run_all_services.py
```

---

## IDE Setup

### VS Code (Recommended)

**Extensions:**
- Python (ms-python.python)
- Pylance (ms-python.vscode-pylance)
- Ruff (charliermarsh.ruff)
- Docker (ms-azuretools.vscode-docker)
- REST Client (humao.rest-client)

**Workspace Settings** (`.vscode/settings.json`):
```json
{
  "python.defaultInterpreterPath": "./src/sales-module/venv/bin/python",
  "python.analysis.extraPaths": [
    "./sales-module",
    "./unified-ui"
  ],
  "[python]": {
    "editor.formatOnSave": true,
    "editor.defaultFormatter": "charliermarsh.ruff"
  },
  "ruff.lint.run": "onSave",
  "ruff.organizeImports": true,
  "files.exclude": {
    "**/__pycache__": true,
    "**/*.pyc": true,
    "**/node_modules": true
  }
}
```

**Launch Configuration** (`.vscode/launch.json`):
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Sales Module",
      "type": "debugpy",
      "request": "launch",
      "module": "uvicorn",
      "args": ["api.server:app", "--reload", "--port", "8000"],
      "cwd": "${workspaceFolder}/sales-module",
      "envFile": "${workspaceFolder}/.env.secrets"
    },
    {
      "name": "Unified UI",
      "type": "debugpy",
      "request": "launch",
      "module": "uvicorn",
      "args": ["backend.main:app", "--reload", "--port", "3005"],
      "cwd": "${workspaceFolder}/unified-ui",
      "envFile": "${workspaceFolder}/.env.secrets"
    }
  ],
  "compounds": [
    {
      "name": "All Services",
      "configurations": ["Sales Module", "Unified UI"]
    }
  ]
}
```

### PyCharm

1. Open CRM folder as project
2. Add two Python interpreters:
   - `src/sales-module/venv/bin/python`
   - `src/unified-ui/venv/bin/python`
3. Mark as Sources Root:
   - `src/sales-module/`
   - `src/unified-ui/`
4. Run configurations:
   - Script: `uvicorn`
   - Parameters: `api.server:app --reload --port 8000`
   - Working directory: `$ProjectFileDir$/sales-module`
   - Environment variables from `.env.secrets`

---

## Per-Service Development

### Sales Module (proposal-bot)

```bash
cd sales-module

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run with hot reload
python run_service.py
# Or directly with uvicorn:
uvicorn api.server:app --reload --port 8000
```

**Directory Structure:**
| Path | Purpose |
|------|---------|
| `api/` | FastAPI routes (chat, proposals, mockups, files, admin, slack) |
| `api/routers/` | Individual route modules |
| `api/schemas.py` | Pydantic request/response models |
| `api/auth.py` | Authentication dependencies |
| `core/` | Business logic |
| `core/llm.py` | LLM orchestration with tool calling |
| `core/chat_api.py` | Unified chat interface |
| `core/proposals.py` | Proposal generation logic |
| `generators/` | Document generation |
| `generators/pptx.py` | PowerPoint creation |
| `generators/pdf.py` | PDF conversion |
| `generators/mockup.py` | Billboard mockup compositing |
| `db/` | Database layer |
| `db/database.py` | Database facade |
| `db/backends/` | SQLite and Supabase implementations |
| `integrations/` | External services |
| `integrations/llm/` | OpenAI and Google providers |
| `workflows/` | Booking order approval workflows |
| `utils/` | Utilities (logging, time, task queue) |

### Unified UI

```bash
cd unified-ui

# Install dependencies (no venv needed if using sales-module venv)
pip install -r requirements.txt

# Set sales-module URL
export SALES_BOT_URL=http://localhost:8000

# Run with hot reload
python run_service.py
```

**Directory Structure:**
| Path | Purpose |
|------|---------|
| `backend/main.py` | FastAPI application entry |
| `backend/config.py` | Environment configuration |
| `backend/middleware/auth.py` | JWT validation, RBAC resolution |
| `backend/routers/proxy.py` | Proxies `/api/sales/*` to sales-module |
| `backend/routers/auth.py` | Authentication endpoints (12) |
| `backend/routers/rbac/` | RBAC management (43 endpoints) |
| `backend/routers/admin.py` | Admin endpoints (8) |
| `backend/services/rbac_service.py` | RBAC data fetching & caching |
| `public/` | Static frontend SPA |
| `public/js/` | Frontend JavaScript modules |
| `public/css/` | Styles (The Void theme) |

---

## Docker Development

### Using Docker Compose (Recommended)

**Quick start:**
```bash
# Using Make (simplest)
make docker-up                # Start all services
make docker-down              # Stop all services

# Or using docker-compose directly
docker-compose -f docker/docker-compose.local.yml --env-file .env.secrets up -d
```

**Selective services with profiles:**
```bash
# Run only sales module
docker-compose -f docker/docker-compose.local.yml --profile sales up -d

# Run only unified UI
docker-compose -f docker/docker-compose.local.yml --profile ui up -d

# Run both (default)
docker-compose -f docker/docker-compose.local.yml --profile all up -d
```

**Custom ports:**
```bash
# Via environment variables
SALES_PORT=9000 UI_PORT=4000 docker-compose -f docker/docker-compose.local.yml up -d

# Or in .env.secrets
echo "SALES_PORT=9000" >> .env.secrets
echo "UI_PORT=4000" >> .env.secrets
```

**Common operations:**
```bash
# View logs
docker-compose -f docker/docker-compose.local.yml logs -f              # All
docker-compose -f docker/docker-compose.local.yml logs -f proposal-bot # Sales only
docker-compose -f docker/docker-compose.local.yml logs -f unified-ui   # UI only

# Rebuild after code changes
docker-compose -f docker/docker-compose.local.yml up -d --build

# Force rebuild everything
docker-compose -f docker/docker-compose.local.yml up -d --build --force-recreate

# Stop and remove volumes
docker-compose -f docker/docker-compose.local.yml down -v
```

### Docker Compose Environment Variables

Both compose files support extensive configuration:

| Variable | Default | Description |
|----------|---------|-------------|
| `SALES_PORT` | 8000 | External sales module port |
| `UI_PORT` | 3005 | External unified-ui port |
| `ENVIRONMENT` | development/production | Environment mode |
| `SALES_CONTAINER_NAME` | proposal-bot | Sales container name |
| `UI_CONTAINER_NAME` | unified-ui | UI container name |
| `SALES_BOT_URL` | http://proposal-bot:8000 | UI's connection to sales |
| `PROXY_SECRET` | (required) | Shared secret for trusted headers |
| `LOG_LEVEL` | INFO | Logging verbosity |
| `CORS_ORIGINS` | localhost:3005,8000 | Allowed CORS origins |
| `NETWORK_NAME` | crm-network | Docker network name |
| `HEALTHCHECK_INTERVAL` | 30s | Health check frequency |
| `HEALTHCHECK_TIMEOUT` | 10s | Health check timeout |

**Production compose additional variables:**
| Variable | Default | Description |
|----------|---------|-------------|
| `SALES_IMAGE` | crm-proposal-bot:latest | Sales module image |
| `UI_IMAGE` | crm-unified-ui:latest | UI image |
| `RESTART_POLICY` | unless-stopped | Container restart policy |
| `SALES_CPU_LIMIT` | 2 | CPU limit for sales |
| `SALES_MEMORY_LIMIT` | 2G | Memory limit for sales |
| `UI_CPU_LIMIT` | 1 | CPU limit for UI |
| `UI_MEMORY_LIMIT` | 1G | Memory limit for UI |

### Individual Service Docker

```bash
# Sales module
cd sales-module
docker build -t proposal-bot .
docker run -p 8000:8000 --env-file ../.env.secrets proposal-bot

# Unified UI (needs network to reach sales-module)
cd unified-ui
docker build -t unified-ui .
docker run -p 3005:3005 \
  -e SALES_BOT_URL=http://host.docker.internal:8000 \
  --env-file ../.env.secrets \
  unified-ui
```

### Debugging in Docker

```bash
# Shell into running container
docker exec -it proposal-bot bash
docker exec -it unified-ui bash

# Check logs
docker logs proposal-bot -f
docker logs unified-ui -f

# Inspect container
docker inspect proposal-bot

# Check network
docker network inspect crm-network

# View resource usage
docker stats proposal-bot unified-ui
```

### Dev Auth in Docker

Enable development authentication to test sales-module API directly via Swagger UI:

1. **Configure `.env.secrets`:**
```env
DEV_AUTH_ENABLED=true
DEV_AUTH_TOKEN=your-secret-token
DEV_AUTH_USER_EMAIL=dev@test.local
DEV_AUTH_USER_PROFILE=system_admin
DEV_AUTH_USER_PERMISSIONS=["*:*:*"]
DEV_AUTH_USER_COMPANIES=["backlite_dubai"]
```

2. **Restart services:**
```bash
make docker-restart
# or
docker-compose -f docker/docker-compose.local.yml up -d
```

3. **Access** http://localhost:8000/docs

4. **Authorize:** Click lock icon → Enter token → Authorize

---

## Database Setup

The platform uses two Supabase projects:

| Project | Purpose | Service |
|---------|---------|---------|
| UI Supabase | Authentication, RBAC, Users | unified-ui |
| SalesBot Supabase | Business data (proposals, BOs) | sales-module |

### Initial Schema Setup

1. **UI Supabase** (for authentication):
   ```bash
   # Run in Supabase SQL Editor
   # Located at: src/sales-module/db/migrations/ui/01_schema.sql
   ```

2. **SalesBot Supabase** (for business data):
   ```bash
   # Run in Supabase SQL Editor
   # Located at: src/sales-module/db/migrations/salesbot/01_schema.sql
   ```

### Multi-Schema Architecture

SalesBot uses per-company schemas for data isolation:

```
public schema (shared)
├── companies (reference table)
├── get_company_and_children()
└── all_* views (cross-company)

backlite_dubai schema
├── locations
├── proposals_log
├── booking_orders
└── ... (16 tables)

backlite_uk schema
└── ... (same structure)
```

See [db/migrations/MIGRATION_GUIDE.md](./src/sales-module/db/migrations/MIGRATION_GUIDE.md) for detailed setup.

### Local SQLite (Alternative)

For quick local development without Supabase:

```env
# In .env.secrets
DB_BACKEND=sqlite
STORAGE_PROVIDER=local
```

Data stored in `src/sales-module/data/proposals.db`.

---

## Testing

### API Testing with Dev Auth

Enable development authentication to test sales-module API directly (bypassing unified-ui):

1. **Configure** `.env.secrets`:
```env
DEV_AUTH_ENABLED=true
DEV_AUTH_TOKEN=your-dev-token
DEV_AUTH_USER_EMAIL=dev@test.local
DEV_AUTH_USER_PROFILE=system_admin
DEV_AUTH_USER_PERMISSIONS=["*:*:*"]
DEV_AUTH_USER_COMPANIES=["backlite_dubai"]
```

2. **Open** http://localhost:8000/docs

3. **Authorize**: Click lock icon -> Enter token in "DevToken" field

4. **Test endpoints** with full permissions

### Unit Tests

```bash
cd sales-module

# Run all tests
pytest

# With coverage
pytest --cov=. --cov-report=html

# Specific test file
pytest tests/test_proposals.py -v

# Specific test
pytest tests/test_proposals.py::test_create_proposal -v

# With output
pytest -s
```

### Integration Tests

```bash
# Test with real Supabase
pytest tests/integration/ --env-file=.env.secrets

# Test specific integration
pytest tests/integration/test_supabase_backend.py -v
```

### Manual API Testing

**Using curl:**
```bash
# Health check
curl http://localhost:8000/health

# Chat (with dev auth)
curl -X POST http://localhost:8000/api/chat/message \
  -H "Authorization: Bearer your-dev-token" \
  -H "Content-Type: application/json" \
  -d '{"message": "Create a proposal for Dubai Gateway"}'
```

**Using REST Client (VS Code):**
```http
### Health Check
GET http://localhost:8000/health

### Chat Message
POST http://localhost:8000/api/chat/message
Authorization: Bearer {{$dotenv DEV_AUTH_TOKEN}}
Content-Type: application/json

{
  "message": "Show me proposals for this month"
}
```

---

## API Development

### Adding a New Endpoint

1. **Create router** (if new domain):
```python
# src/sales-module/api/routers/my_feature.py
from fastapi import APIRouter, Depends
from api.auth import get_current_user

router = APIRouter(prefix="/my-feature", tags=["my-feature"])

@router.get("/")
async def list_items(user = Depends(get_current_user)):
    return {"items": []}
```

2. **Register router**:
```python
# src/sales-module/api/server.py
from api.routers import my_feature
app.include_router(my_feature.router, prefix="/api")
```

3. **Add schemas**:
```python
# src/sales-module/api/schemas.py
class MyFeatureRequest(BaseModel):
    name: str
    value: int

class MyFeatureResponse(BaseModel):
    id: str
    name: str
```

### Adding an LLM Tool

1. **Define tool** in `core/tools.py`:
```python
def get_tools():
    return [
        # ... existing tools
        {
            "type": "function",
            "function": {
                "name": "my_new_tool",
                "description": "Description of what it does",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string", "description": "..."}
                    },
                    "required": ["param1"]
                }
            }
        }
    ]
```

2. **Implement handler** in `core/llm.py`:
```python
async def handle_tool_call(tool_name, args, context):
    if tool_name == "my_new_tool":
        return await my_new_tool_handler(args, context)
```

---

## Frontend Development

### Modifying the SPA

Frontend is vanilla JavaScript in `src/unified-ui/public/`:

```
public/
├── index.html          # Main shell
├── css/
│   └── styles.css      # All styles (The Void theme)
└── js/
    ├── app.js          # App initialization
    ├── auth.js         # Authentication
    ├── api.js          # API client
    ├── chat.js         # Chat UI
    ├── mockup.js       # Mockup generator
    ├── sidebar.js      # Navigation
    ├── modules.js      # Module loader
    └── admin.js        # Admin panel
```

### Hot Reload

Changes to `public/` files are served immediately (no build step).

### Adding a New Module

1. **Create JS file**: `public/js/my_module.js`
```javascript
window.MyModule = {
    init() {
        console.log('My Module initialized');
    },

    render(container) {
        container.innerHTML = '<h1>My Module</h1>';
    }
};
```

2. **Register in** `modules.js`:
```javascript
const MODULES = {
    // ... existing
    'my-module': {
        name: 'My Module',
        icon: 'icon-star',
        permission: 'sales:my_module:use',
        init: () => window.MyModule.init(),
        render: (el) => window.MyModule.render(el)
    }
};
```

3. **Include script** in `index.html`:
```html
<script src="/js/my_module.js"></script>
```

---

## LLM Provider Configuration

### OpenAI (Default)

```env
OPENAI_API_KEY=sk-...
LLM_PROVIDER=openai
LLM_MODEL=gpt-4-turbo-preview
```

### Google Gemini

```env
GOOGLE_API_KEY=...
LLM_PROVIDER=google
LLM_MODEL=gemini-pro
```

### Provider-Specific Settings

```env
# OpenAI
OPENAI_TEMPERATURE=0.7
OPENAI_MAX_TOKENS=4096

# Google
GOOGLE_TEMPERATURE=0.7
GOOGLE_MAX_OUTPUT_TOKENS=4096
```

### Cost Tracking

AI costs are tracked per-request in `ai_costs` table. View in:
- Supabase dashboard: `{company_schema}.ai_costs`
- API: `GET /api/costs/summary`

---

## Environment Variables Reference

### Shared (Both Services)

| Variable | Required | Description |
|----------|----------|-------------|
| `PROXY_SECRET` | Yes | Shared secret for trusted headers |
| `ENVIRONMENT` | No | `local`, `development`, `production` |

### Sales Module

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PORT` | No | `8000` | Server port |
| `DB_BACKEND` | No | `supabase` | `supabase` or `sqlite` |
| `STORAGE_PROVIDER` | No | `supabase` | `supabase`, `local`, or `s3` |
| `SALESBOT_DEV_SUPABASE_URL` | Yes (dev) | - | Dev Supabase URL |
| `SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY` | Yes (dev) | - | Dev Supabase key |
| `SALESBOT_PROD_SUPABASE_*` | Yes (prod) | - | Production credentials |
| `OPENAI_API_KEY` | Yes | - | OpenAI API key |
| `GOOGLE_API_KEY` | No | - | Google Gemini key |
| `SLACK_BOT_TOKEN` | No | - | Slack integration |
| `SLACK_SIGNING_SECRET` | No | - | Slack webhook verification |
| `DEV_AUTH_ENABLED` | No | `false` | Enable dev auth for testing |
| `DEV_AUTH_TOKEN` | No | - | Dev auth token |

### Unified UI

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PORT` | No | `3005` | Server port |
| `SALES_BOT_URL` | Yes | - | Sales module URL |
| `UI_DEV_SUPABASE_URL` | Yes (dev) | - | Dev Supabase URL |
| `UI_DEV_SUPABASE_ANON_KEY` | Yes (dev) | - | Public anon key |
| `UI_DEV_SUPABASE_SERVICE_ROLE_KEY` | Yes (dev) | - | Service role key |
| `UI_PROD_SUPABASE_*` | Yes (prod) | - | Production credentials |
| `CORS_ORIGINS` | No | - | Additional CORS origins |
| `RBAC_CACHE_TTL_SECONDS` | No | `30` | RBAC cache duration |

---

## Debugging Tips

### Check Service Health

```bash
# Sales module
curl http://localhost:8000/health | jq

# Unified UI
curl http://localhost:3005/health | jq
```

### View Request Flow

**unified-ui logs:**
```
[UI] POST /api/sales/chat -> 200 (1250ms)
[PROXY] POST /api/sales/chat -> http://proposal-bot:8000/api/chat
[PROXY] User: john@example.com | Profile: sales_user
```

**sales-module logs:**
```
[API] POST /api/chat | User: john@example.com | Companies: ['backlite_dubai']
[LLM] Tool call: search_locations({"query": "Dubai Gateway"})
[LLM] Response: 1250 tokens | Cost: $0.0125
```

### Common Issues

#### Port Already in Use
```bash
# Find process
lsof -i :8000
netstat -tlnp | grep 8000  # Linux

# Kill it
kill -9 <PID>
```

#### Import Errors
```bash
# Ensure PYTHONPATH is set
export PYTHONPATH=/path/to/CRM/sales-module:$PYTHONPATH
```

#### Supabase Connection Failed
1. Check credentials in `.env.secrets`
2. Verify project is active in Supabase dashboard
3. Check network (VPN, firewall)
4. Try service role key (not anon key) for backend

#### Proxy 502 Errors
1. Ensure sales-module is running
2. Check `SALES_BOT_URL` is correct
3. Verify `PROXY_SECRET` matches both services
4. Check sales-module logs for errors

#### RBAC Not Working
1. Check X-Trusted-* headers in unified-ui logs
2. Verify user exists in users table
3. Check profile assignment
4. Clear RBAC cache: `POST /api/admin/cache/clear`

#### LLM Not Responding
1. Check API key is valid
2. Check rate limits
3. View cost tracker for errors
4. Try different model

---

## Code Style

### Linting with Ruff

```bash
cd sales-module

# Check
ruff check .

# Auto-fix
ruff check . --fix

# Format
ruff format .
```

### Pre-commit Hooks

```bash
# Install
pip install pre-commit
pre-commit install

# Run manually
pre-commit run --all-files
```

### Type Hints

All new code should have type hints:

```python
async def process_chat(
    message: str,
    user_id: str,
    companies: list[str],
) -> ChatResponse:
    ...
```

---

## Project Structure

```
CRM/
├── src/unified-ui/                 # Auth gateway + frontend (port 3005)
│   ├── backend/                # FastAPI backend
│   │   ├── main.py             # Application entry
│   │   ├── config.py           # Settings
│   │   ├── middleware/         # Auth middleware
│   │   ├── routers/            # API routes
│   │   └── services/           # Business logic
│   ├── public/                 # Static SPA
│   ├── run_service.py          # Uvicorn runner
│   ├── render.yaml             # Render.com config
│   └── Dockerfile
│
├── src/sales-module/               # Proposal bot backend (port 8000)
│   ├── api/                    # FastAPI routes
│   │   ├── server.py           # Application entry
│   │   ├── routers/            # Route modules
│   │   ├── schemas.py          # Pydantic models
│   │   └── auth.py             # Auth dependencies
│   ├── core/                   # Business logic
│   │   ├── llm.py              # LLM orchestration
│   │   ├── chat_api.py         # Chat interface
│   │   └── proposals.py        # Proposal generation
│   ├── generators/             # Document generation
│   ├── db/                     # Database layer
│   │   ├── database.py         # Facade
│   │   ├── backends/           # SQLite, Supabase
│   │   └── migrations/         # Schema & guides
│   ├── integrations/           # External services
│   │   ├── llm/                # LLM providers
│   │   ├── auth/               # Auth providers
│   │   └── storage/            # Storage providers
│   ├── workflows/              # Approval workflows
│   ├── utils/                  # Utilities
│   ├── orphan/                 # Deprecated code
│   ├── run_service.py          # Uvicorn runner
│   ├── render.yaml             # Render.com config
│   └── Dockerfile
│
├── run_all_services.py         # Combined runner
├── docker/docker-compose.yml          # Production compose
├── docker/docker-compose.local.yml    # Dev compose
├── .env.example                # Environment template
├── ARCHITECTURE.md             # System architecture
├── DEVELOPMENT.md              # This file
└── DEPLOYMENT.md               # Deployment guide
```

---

## Common Patterns

### Database Query Pattern

```python
# In sales-module
from db.database import get_database

async def get_proposals(company: str, user_id: str):
    db = get_database()
    return await db.query(
        schema=company,
        table="proposals_log",
        filters={"user_id": user_id},
        order_by={"date_generated": "desc"}
    )
```

### Authentication Pattern

```python
# In sales-module router
from api.auth import get_current_user, TrustedUser

@router.get("/my-data")
async def get_my_data(user: TrustedUser = Depends(get_current_user)):
    # user.id, user.email, user.profile, user.companies available
    return await service.get_data(user.companies[0], user.id)
```

### LLM Tool Pattern

```python
# Define tool with schema
tools = [{
    "type": "function",
    "function": {
        "name": "do_something",
        "description": "Does something useful",
        "parameters": {
            "type": "object",
            "properties": {
                "input": {"type": "string"}
            },
            "required": ["input"]
        }
    }
}]

# Handle tool call
if tool_name == "do_something":
    result = await do_something(args["input"])
    return {"result": result}
```

---

## Related Documentation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Full system architecture |
| [DEPLOYMENT.md](./DEPLOYMENT.md) | Production deployment options |
| [src/sales-module/README.md](./src/sales-module/README.md) | Sales module documentation |
| [src/sales-module/FRONTEND_API.md](./src/sales-module/FRONTEND_API.md) | Backend API reference |
| [src/unified-ui/README.md](./src/unified-ui/README.md) | Unified UI documentation |
| [src/unified-ui/FRONTEND_API.md](./src/unified-ui/FRONTEND_API.md) | Frontend API reference |
| [db/migrations/MIGRATION_GUIDE.md](./src/sales-module/db/migrations/MIGRATION_GUIDE.md) | Database setup |

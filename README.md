# CRM Platform

Multi-module CRM system with independent, deployable services.

## Architecture

```
CRM/
├── src/                         # Service modules
│   ├── unified-ui/              # Auth gateway + frontend (port 3005)
│   └── sales-module/            # Proposal bot backend (port 8000)
│       └── orphan/              # Deprecated/unused code
├── docs/                        # Documentation
│   ├── ARCHITECTURE.md          # System architecture
│   ├── DEVELOPMENT.md           # Development guide
│   └── DEPLOYMENT.md            # Deployment guide
├── docker/                      # Docker configuration
│   ├── docker-compose.yml       # Production deployment
│   └── docker-compose.local.yml # Local development
├── run_all_services.py          # Combined service runner
├── Makefile                     # Build and management commands
├── requirements-dev.txt         # Development dependencies
└── .env.example                 # Environment template
```

### Services

| Service | Port | Technology | Description |
|---------|------|------------|-------------|
| **unified-ui** | 3005 | Python FastAPI | Authentication gateway, RBAC, frontend SPA |
| **sales-module** | 8000 | Python FastAPI | Proposal generation, document processing, AI |

### Integration

- `unified-ui` proxies `/api/sales/*` requests to `sales-module`
- Both share a `PROXY_SECRET` for trusted header injection
- 5-level RBAC context is passed via X-Trusted-* headers

## Quick Start

### Option 1: Run All Services Locally (Python)

```bash
# From the CRM root directory
python run_all_services.py
```

### Option 2: Docker Compose (Local Development)

```bash
# Create .env.secrets with your environment variables
cp .env.example .env.secrets
# Edit .env.secrets with your Supabase credentials

# Start all services
docker-compose -f docker/docker-compose.local.yml --env-file .env.secrets up -d

# View logs
docker-compose -f docker/docker-compose.local.yml logs -f

# Stop services
docker-compose -f docker/docker-compose.local.yml down
```

### Option 3: Run Individual Services

```bash
# Sales module
cd src/sales-module
python run_service.py

# Unified UI (in another terminal)
cd src/unified-ui
export SALES_BOT_URL=http://localhost:8000
python run_service.py
```

## Deployment Options

### Deploy All Together (Docker Compose)

```bash
docker-compose -f docker/docker-compose.yml up -d
```

### Deploy Individually (Render.com)

Each module has its own `render.yaml`:

```bash
# Deploy sales-module
cd src/sales-module
render blueprint apply

# Deploy unified-ui
cd src/unified-ui
render blueprint apply
```

## Environment Variables

### Sales Module (src/sales-module/.env)

```env
ENVIRONMENT=production
PORT=8000
DB_BACKEND=supabase
AUTH_PROVIDER=supabase
SALESBOT_PROD_SUPABASE_URL=your-url
SALESBOT_PROD_SUPABASE_SERVICE_ROLE_KEY=your-key
PROXY_SECRET=your-shared-secret
OPENAI_API_KEY=your-key
GOOGLE_API_KEY=your-key
```

### Unified UI (src/unified-ui/.env)

```env
ENVIRONMENT=production
PORT=3005
SALES_BOT_URL=https://your-proposal-bot-url
UI_PROD_SUPABASE_URL=your-url
UI_PROD_SUPABASE_ANON_KEY=your-key
UI_PROD_SUPABASE_SERVICE_ROLE_KEY=your-key
PROXY_SECRET=your-shared-secret
```

## Access Points

| Environment | Unified UI | Proposal Bot API |
|-------------|------------|------------------|
| Local | http://localhost:3005 | http://localhost:8000 |
| Docker | http://localhost:3005 | http://localhost:8000 |
| Production | https://unified-ui.onrender.com | https://proposal-bot.onrender.com |

## Documentation Index

| Document | Description |
|----------|-------------|
| [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) | Full system architecture (services, data flow, integrations) |
| [docs/DEVELOPMENT.md](./docs/DEVELOPMENT.md) | Development setup and local running guide |
| [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md) | Production deployment options |
| [src/sales-module/README.md](./src/sales-module/README.md) | Sales module service documentation |
| [src/sales-module/OVERVIEW.md](./src/sales-module/OVERVIEW.md) | Business overview for non-technical users |
| [src/sales-module/FRONTEND_API.md](./src/sales-module/FRONTEND_API.md) | Backend API reference |
| [src/unified-ui/README.md](./src/unified-ui/README.md) | Unified UI gateway documentation |
| [src/unified-ui/FRONTEND_API.md](./src/unified-ui/FRONTEND_API.md) | Frontend API reference |
| [src/sales-module/db/migrations/](./src/sales-module/db/migrations/) | Sales module database schema |
| [src/unified-ui/db/migrations/](./src/unified-ui/db/migrations/) | Unified UI database schema |

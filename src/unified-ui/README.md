# Unified UI

Authentication gateway and frontend SPA for the MMG Service Platform.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Backend Components](#backend-components)
- [5-Level RBAC System](#5-level-rbac-system)
- [Proxy & Trusted Headers](#proxy--trusted-headers)
- [API Endpoints](#api-endpoints)
- [Frontend SPA](#frontend-spa)
- [Configuration](#configuration)
- [Running](#running)
- [Security](#security)
- [Related Documentation](#related-documentation)

---

## Overview

Unified UI is a FastAPI-based gateway service that sits between the browser and the sales-module backend. It provides:

| Capability | Description |
|------------|-------------|
| **Authentication Gateway** | Validates Supabase JWTs with Microsoft SSO support |
| **RBAC Resolution** | Resolves 5-level role-based access control context |
| **API Proxy** | Forwards authenticated requests to sales-module with trusted headers |
| **Static Frontend** | Serves the SPA web application |
| **RBAC Management** | 43 endpoints for managing users, teams, permissions |

---

## Architecture

### High-Level Flow

```
Browser
    │
    │ 1. Request with JWT token
    ▼
┌─────────────────────────────────────────────────────────────┐
│                    unified-ui:3005                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐                                       │
│  │  JWT Validation  │ 2. Validate token with Supabase       │
│  └────────┬─────────┘                                       │
│           │                                                  │
│           ▼                                                  │
│  ┌──────────────────┐                                       │
│  │  RBAC Resolution │ 3. Fetch profile, permissions,        │
│  │                  │    teams, companies from DB           │
│  └────────┬─────────┘                                       │
│           │                                                  │
│           ▼                                                  │
│  ┌──────────────────┐                                       │
│  │ Header Injection │ 4. Build X-Trusted-* headers          │
│  └────────┬─────────┘                                       │
│           │                                                  │
└───────────┼──────────────────────────────────────────────────┘
            │
            │ 5. Proxy request with trusted headers
            ▼
┌─────────────────────────────────────────────────────────────┐
│                   sales-module:8000                          │
│                                                              │
│  6. Validate X-Proxy-Secret                                  │
│  7. Extract user context from X-Trusted-* headers            │
│  8. Process request with full RBAC context                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Request Types

| Route Pattern | Handling |
|---------------|----------|
| `/api/sales/*` | Proxied to sales-module with trusted headers |
| `/api/base/*` | Handled locally (auth, config) |
| `/api/rbac/*` | Handled locally (43 RBAC management endpoints) |
| `/api/admin/*` | Handled locally (admin operations) |
| `/api/modules/*` | Handled locally (module registry) |
| `/api/channel-identity/*` | Handled locally (Slack/Teams identity) |
| `/*` | Static SPA files or index.html for SPA routing |

---

## Backend Components

### Directory Structure

```
unified-ui/
├── backend/
│   ├── main.py                 # FastAPI application entry
│   ├── config.py               # Environment configuration (Settings class)
│   ├── __init__.py
│   │
│   ├── middleware/
│   │   ├── auth.py             # JWT validation, TrustedUser, require_auth
│   │   ├── rate_limit.py       # Rate limiting for auth endpoints
│   │   └── __init__.py
│   │
│   ├── routers/
│   │   ├── proxy.py            # /api/sales/* -> sales-module proxy
│   │   ├── auth.py             # /api/base/auth/* (12 endpoints)
│   │   ├── admin.py            # /api/admin/* (8 endpoints)
│   │   ├── modules.py          # /api/modules/* (1 endpoint)
│   │   ├── channel_identity.py # /api/channel-identity/* (9 endpoints)
│   │   ├── __init__.py
│   │   └── rbac/               # /api/rbac/* (43 endpoints)
│   │       ├── __init__.py     # Combined router
│   │       ├── users.py        # User CRUD
│   │       ├── profiles.py     # Profile management
│   │       ├── permission_sets.py  # Permission set management
│   │       ├── teams.py        # Team management
│   │       ├── sharing.py      # Record sharing
│   │       └── models.py       # Pydantic models
│   │
│   ├── services/
│   │   ├── supabase_client.py  # Supabase client singleton
│   │   ├── rbac_service.py     # RBAC data fetching & caching
│   │   └── __init__.py
│   │
│   └── models/
│       └── __init__.py
│
├── public/                     # Frontend SPA
│   ├── index.html              # Main HTML shell
│   ├── css/
│   │   └── styles.css          # Design system ("The Void" theme)
│   └── js/
│       ├── app.js              # Application initialization
│       ├── auth.js             # Authentication module
│       ├── api.js              # API client library
│       ├── chat.js             # Chat interface
│       ├── mockup.js           # Mockup generator
│       ├── sidebar.js          # Navigation
│       ├── modules.js          # Module registry
│       └── admin.js            # Admin panel
│
├── run_service.py              # Uvicorn runner
├── render.yaml                 # Render.com deployment config
├── Dockerfile                  # Container image
├── requirements.txt            # Python dependencies
├── FRONTEND_API.md             # Detailed frontend API reference
└── README.md                   # This file
```

### Core Files

#### `backend/main.py`

The FastAPI application entry point:

| Component | Purpose |
|-----------|---------|
| `lifespan()` | Startup/shutdown events, Supabase connection check |
| `add_security_headers()` | Helmet.js-equivalent security headers |
| `log_requests()` | Request logging with timing |
| `serve_frontend()` | SPA catch-all route |
| `get_supabase_config()` | Serves public Supabase credentials to frontend |

**Routers included:**
- `auth.router` - `/api/base/auth/*`
- `modules.router` - `/api/modules/*`
- `proxy.router` - `/api/sales/*`
- `admin.router` - `/api/admin/*`
- `rbac_router` - `/api/rbac/*`
- `channel_identity.router` - `/api/channel-identity/*`

#### `backend/config.py`

Environment configuration using Pydantic Settings:

```python
class Settings(BaseSettings):
    # Environment
    ENVIRONMENT: str = "development"  # local, development, production
    PORT: int = 3005

    # UI Supabase (authentication database)
    UI_PROD_SUPABASE_URL: str | None
    UI_PROD_SUPABASE_SERVICE_ROLE_KEY: str | None
    UI_PROD_SUPABASE_ANON_KEY: str | None
    UI_DEV_SUPABASE_URL: str | None
    UI_DEV_SUPABASE_SERVICE_ROLE_KEY: str | None
    UI_DEV_SUPABASE_ANON_KEY: str | None

    # Service registry
    SALES_BOT_URL: str = "http://localhost:8000"

    # Security
    PROXY_SECRET: str | None  # Shared secret with sales-module

    # Rate limiting
    RATE_LIMIT_WINDOW_MS: int = 60000
    RATE_LIMIT_MAX_REQUESTS: int = 10

    # CORS
    CORS_ORIGINS: str = ""
    RENDER_EXTERNAL_URL: str | None

    # RBAC cache
    RBAC_CACHE_TTL_SECONDS: int = 30
```

**Key Properties:**
- `is_production` - True if ENVIRONMENT == "production"
- `supabase_url` - Auto-selects dev/prod URL based on environment
- `supabase_service_key` - Auto-selects dev/prod key
- `allowed_origins` - Computed CORS origins list

#### `backend/middleware/auth.py`

Authentication dependencies:

| Class/Function | Purpose |
|----------------|---------|
| `AuthUser` | Basic authenticated user dataclass |
| `TrustedUser` | User with full 5-level RBAC context |
| `get_current_user()` | Extract user from JWT (returns None if invalid) |
| `require_auth()` | Dependency that raises 401 if not authenticated |
| `require_profile(*profiles)` | Dependency that checks user has allowed profile |
| `get_trusted_user()` | Full RBAC resolution for proxy requests |

#### `backend/routers/proxy.py`

Proxies `/api/sales/*` to sales-module:

```python
@router.api_route("/api/sales/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_to_sales_bot(path: str, request: Request, user: TrustedUser = Depends(get_trusted_user)):
    # 1. Build target URL: /api/sales/chat -> /api/chat on sales-module
    # 2. Build trusted headers with full RBAC context
    # 3. Proxy request (regular or streaming for SSE)
    # 4. Return response
```

**Features:**
- Path transformation: `/api/sales/chat` -> `/api/chat`
- SSE streaming support for chat
- Timeout handling (300s)
- Connection error handling with dev/prod error detail levels

#### `backend/services/rbac_service.py`

RBAC data fetching with caching:

| Function | Purpose |
|----------|---------|
| `get_user_rbac_data(user_id)` | Fetch complete 5-level RBAC context |
| `invalidate_rbac_cache(user_id)` | Clear cache for specific user |
| `invalidate_rbac_cache_for_users(user_ids)` | Clear cache for multiple users |
| `clear_all_rbac_cache()` | Clear entire cache |

**Caching:**
- In-memory cache with configurable TTL (default 30s)
- Auto-invalidated on permission changes via RBAC endpoints

---

## 5-Level RBAC System

The RBAC system provides hierarchical access control:

### Level 1: Profiles (Base Role)

Profiles define the base job function and permissions.

| Profile | Description | Example Permissions |
|---------|-------------|---------------------|
| `system_admin` | Full system access | `*:*:*` |
| `sales_manager` | Sales team management | `sales:*:*` |
| `sales_user` | Standard sales user | `sales:proposals:*`, `sales:chat:use` |
| `coordinator` | Booking order coordination | `sales:bo:*` |
| `finance` | Financial review | `sales:bo:approve` |
| `viewer` | Read-only access | `*:*:read` |

### Level 2: Permission Sets (Additive)

Permission sets add temporary or permanent permissions on top of profile:

```json
{
  "id": 5,
  "name": "mockup_setup_access",
  "permissions": ["sales:mockups:setup"],
  "expires_at": "2024-03-01T00:00:00Z"
}
```

### Level 3: Teams & Hierarchy

Teams enable organizational access patterns:

- **Team membership**: Users belong to teams
- **Team roles**: `member` or `leader`
- **Manager hierarchy**: Manager can see subordinates' data
- **Team leaders**: Can see all team members' data

### Level 4: Record Sharing

Share specific records with users or teams:

```json
{
  "object_type": "proposal",
  "record_id": "prop-123",
  "shared_with_user_id": "user-456",
  "access_level": "read_write",
  "expires_at": null
}
```

### Level 5: Company Access

Multi-tenant isolation:

- Users are assigned to one or more companies
- Company hierarchy (parent/child relationships)
- Schema isolation in sales-module database

### Trusted Headers

All RBAC context is serialized to headers for sales-module:

| Header | Level | Example Value |
|--------|-------|---------------|
| `X-Trusted-User-Id` | 1 | `"user-uuid-123"` |
| `X-Trusted-User-Email` | 1 | `"john@example.com"` |
| `X-Trusted-User-Name` | 1 | `"John Doe"` |
| `X-Trusted-User-Profile` | 1 | `"sales_user"` |
| `X-Trusted-User-Permissions` | 1+2 | `["sales:*:*", "core:*:read"]` |
| `X-Trusted-User-Permission-Sets` | 2 | `[{"id": 1, "name": "extra_access"}]` |
| `X-Trusted-User-Teams` | 3 | `[{"id": 1, "name": "sales_uae", "role": "member"}]` |
| `X-Trusted-User-Team-Ids` | 3 | `[1, 2, 3]` |
| `X-Trusted-User-Manager-Id` | 3 | `"manager-uuid"` |
| `X-Trusted-User-Subordinate-Ids` | 3 | `["sub1-uuid", "sub2-uuid"]` |
| `X-Trusted-User-Sharing-Rules` | 4 | `[{"id": 1, "objectType": "proposal"}]` |
| `X-Trusted-User-Shared-Records` | 4 | `{"proposal": [{"recordId": "123"}]}` |
| `X-Trusted-User-Shared-From-User-Ids` | 4 | `["user-789"]` |
| `X-Trusted-User-Companies` | 5 | `["backlite_dubai", "backlite_uk"]` |
| `X-Proxy-Secret` | Security | `"shared-secret"` |

---

## Proxy & Trusted Headers

### Why Trusted Headers?

The proxy pattern separates authentication from business logic:

1. **Single authentication point**: Only unified-ui needs Supabase Auth credentials
2. **Simplified backend**: sales-module doesn't validate JWTs
3. **Performance**: No repeated token validation on internal calls
4. **Flexibility**: Can swap auth providers without changing backend

### Security

- `X-Proxy-Secret` must match between services
- Direct calls to sales-module without valid secret are rejected
- Headers are stripped from external requests before proxying
- All headers are JSON-encoded for complex data

### Proxy Flow

```python
# 1. Authenticate user and resolve RBAC
user = get_trusted_user(request)  # Validates JWT, fetches RBAC

# 2. Build headers
headers = {
    "X-Proxy-Secret": settings.PROXY_SECRET,
    "X-Trusted-User-Id": user.id,
    "X-Trusted-User-Email": user.email,
    "X-Trusted-User-Profile": user.profile,
    "X-Trusted-User-Permissions": json.dumps(user.permissions),
    "X-Trusted-User-Companies": json.dumps(user.companies),
    # ... all 5 levels
}

# 3. Forward to sales-module
response = await httpx.request(method, target_url, headers=headers, content=body)
```

---

## API Endpoints

### Authentication (`/api/base/auth/*`) - 12 Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/base/auth/me` | Get current user with RBAC |
| POST | `/api/base/auth/login` | Email/password login |
| POST | `/api/base/auth/logout` | Logout (clear session) |
| POST | `/api/base/auth/refresh` | Refresh JWT token |
| POST | `/api/base/auth/register` | Register new user |
| POST | `/api/base/auth/forgot-password` | Request password reset |
| POST | `/api/base/auth/reset-password` | Reset password with token |
| GET | `/api/base/auth/sso/config` | Get SSO configuration |
| POST | `/api/base/auth/sso/callback` | Handle SSO callback |
| GET | `/api/base/auth/session` | Get current session |
| POST | `/api/base/auth/verify-email` | Verify email address |
| POST | `/api/base/auth/resend-verification` | Resend verification email |

### RBAC Management (`/api/rbac/*`) - 43 Endpoints

#### Users (11 endpoints)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/rbac/users` | List all users |
| GET | `/api/rbac/users/{id}` | Get user details |
| POST | `/api/rbac/users` | Create user |
| PUT | `/api/rbac/users/{id}` | Update user |
| DELETE | `/api/rbac/users/{id}` | Delete user |
| POST | `/api/rbac/users/{id}/activate` | Activate user |
| POST | `/api/rbac/users/{id}/deactivate` | Deactivate user |
| PUT | `/api/rbac/users/{id}/profile` | Update user profile |
| PUT | `/api/rbac/users/{id}/companies` | Update user companies |
| POST | `/api/rbac/users/invite` | Invite user by email |
| POST | `/api/rbac/users/accept-invite` | Accept invitation |

#### Profiles (8 endpoints)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/rbac/profiles` | List all profiles |
| GET | `/api/rbac/profiles/{id}` | Get profile details |
| POST | `/api/rbac/profiles` | Create profile |
| PUT | `/api/rbac/profiles/{id}` | Update profile |
| DELETE | `/api/rbac/profiles/{id}` | Delete profile |
| GET | `/api/rbac/profiles/{id}/permissions` | Get profile permissions |
| PUT | `/api/rbac/profiles/{id}/permissions` | Update profile permissions |
| GET | `/api/rbac/permissions` | List all available permissions |

#### Permission Sets (8 endpoints)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/rbac/permission-sets` | List permission sets |
| GET | `/api/rbac/permission-sets/{id}` | Get permission set |
| POST | `/api/rbac/permission-sets` | Create permission set |
| PUT | `/api/rbac/permission-sets/{id}` | Update permission set |
| DELETE | `/api/rbac/permission-sets/{id}` | Delete permission set |
| POST | `/api/rbac/permission-sets/{id}/assign` | Assign to user |
| POST | `/api/rbac/permission-sets/{id}/revoke` | Revoke from user |
| GET | `/api/rbac/users/{id}/permission-sets` | Get user's permission sets |

#### Teams (10 endpoints)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/rbac/teams` | List all teams |
| GET | `/api/rbac/teams/{id}` | Get team details |
| POST | `/api/rbac/teams` | Create team |
| PUT | `/api/rbac/teams/{id}` | Update team |
| DELETE | `/api/rbac/teams/{id}` | Delete team |
| GET | `/api/rbac/teams/{id}/members` | Get team members |
| POST | `/api/rbac/teams/{id}/members` | Add member to team |
| DELETE | `/api/rbac/teams/{id}/members/{userId}` | Remove member |
| PUT | `/api/rbac/teams/{id}/members/{userId}/role` | Update member role |
| GET | `/api/rbac/users/{id}/teams` | Get user's teams |

#### Sharing (6 endpoints)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/rbac/sharing-rules` | List sharing rules |
| POST | `/api/rbac/sharing-rules` | Create sharing rule |
| DELETE | `/api/rbac/sharing-rules/{id}` | Delete sharing rule |
| GET | `/api/rbac/record-shares` | List record shares |
| POST | `/api/rbac/record-shares` | Share record |
| DELETE | `/api/rbac/record-shares/{id}` | Revoke share |

### Admin (`/api/admin/*`) - 8 Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/stats` | Get system statistics |
| GET | `/api/admin/companies` | List companies |
| POST | `/api/admin/companies` | Create company |
| PUT | `/api/admin/companies/{id}` | Update company |
| GET | `/api/admin/system-settings` | Get system settings |
| PUT | `/api/admin/system-settings` | Update system settings |
| GET | `/api/admin/audit-log` | Get audit log |
| POST | `/api/admin/cache/clear` | Clear all caches |

### Channel Identity (`/api/channel-identity/*`) - 9 Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/channel-identity` | Get current user's identities |
| POST | `/api/channel-identity/link` | Link external identity |
| DELETE | `/api/channel-identity/{id}` | Unlink identity |
| GET | `/api/channel-identity/slack` | Get Slack identity |
| POST | `/api/channel-identity/slack/link` | Link Slack account |
| GET | `/api/channel-identity/teams` | Get Teams identity |
| POST | `/api/channel-identity/teams/link` | Link Teams account |
| GET | `/api/channel-identity/lookup` | Lookup user by external ID |
| POST | `/api/channel-identity/verify` | Verify identity ownership |

### Modules (`/api/modules/*`) - 1 Endpoint

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/modules` | Get accessible modules for current user |

### Sales Proxy (`/api/sales/*`)

All requests to `/api/sales/*` are proxied to sales-module:

| Unified UI Route | Sales Module Route |
|------------------|-------------------|
| `/api/sales/chat/message` | `/api/chat/message` |
| `/api/sales/chat/stream` | `/api/chat/stream` |
| `/api/sales/proposals` | `/api/proposals` |
| `/api/sales/mockup/*` | `/api/mockup/*` |
| `/api/sales/files/*` | `/api/files/*` |

---

## Frontend SPA

### Technology Stack

| Component | Technology |
|-----------|------------|
| Framework | Vanilla JavaScript (ES6+) |
| Styling | Custom CSS Design System |
| Theme | "The Void" (dark, futuristic) |
| Build | No build step (served as-is) |

### Design System

**Color Palette:**

| Category | Colors | Usage |
|----------|--------|-------|
| Void | `#000` - `#1E1E26` | Backgrounds |
| Quantum Blue | `#3381FF` | Primary CTAs |
| Plasma Cyan | `#06B6D4` | Secondary highlights |
| Nebula Purple | `#A855F7` | Tertiary accents |
| Aurora Green | `#22C55E` | Success states |
| Solar Yellow | `#EAB308` | Warnings |
| Crimson Red | `#F43F5E` | Errors |

**Design Features:**
- Glass morphism effects
- Gradient animations
- Quantum glow shadows
- Spring easing animations
- Inter font family

### Module System

Frontend modules are dynamically loaded based on user permissions:

| Module | File | Permission |
|--------|------|------------|
| AI Chat | `chat.js` | `sales:chat:use` |
| Mockup Generator | `mockup.js` | `sales:mockups:*` |
| Admin Panel | `admin.js` | `core:system:admin` |

---

## Configuration

### Environment Variables

#### Core Settings

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ENVIRONMENT` | No | `development` | `local`, `development`, `production` |
| `PORT` | No | `3005` | Server port |

#### Supabase (Development)

| Variable | Required | Description |
|----------|----------|-------------|
| `UI_DEV_SUPABASE_URL` | Yes | Supabase project URL |
| `UI_DEV_SUPABASE_ANON_KEY` | Yes | Public anon key (for frontend) |
| `UI_DEV_SUPABASE_SERVICE_ROLE_KEY` | Yes | Service role key (for backend) |

#### Supabase (Production)

| Variable | Required | Description |
|----------|----------|-------------|
| `UI_PROD_SUPABASE_URL` | Yes | Production Supabase URL |
| `UI_PROD_SUPABASE_ANON_KEY` | Yes | Production anon key |
| `UI_PROD_SUPABASE_SERVICE_ROLE_KEY` | Yes | Production service role key |

#### Service Integration

| Variable | Required | Description |
|----------|----------|-------------|
| `SALES_BOT_URL` | Yes | Sales module URL (e.g., `http://proposal-bot:8000`) |
| `PROXY_SECRET` | Yes | Shared secret for trusted header verification |

#### CORS

| Variable | Required | Description |
|----------|----------|-------------|
| `CORS_ORIGINS` | No | Comma-separated allowed origins |
| `RENDER_EXTERNAL_URL` | No | Auto-set by Render |

#### Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_WINDOW_MS` | `60000` | Rate limit window (ms) |
| `RATE_LIMIT_MAX_REQUESTS` | `10` | Max requests per window |

#### RBAC

| Variable | Default | Description |
|----------|---------|-------------|
| `RBAC_CACHE_TTL_SECONDS` | `30` | RBAC cache TTL |

---

## Running

### Standalone Development

```bash
cd unified-ui

# Install dependencies
pip install -r requirements.txt

# Set environment
export SALES_BOT_URL=http://localhost:8000
export UI_DEV_SUPABASE_URL=https://xxx.supabase.co
export UI_DEV_SUPABASE_ANON_KEY=eyJ...
export UI_DEV_SUPABASE_SERVICE_ROLE_KEY=eyJ...
export PROXY_SECRET=your-secret

# Run
python run_service.py
# Server at http://localhost:3005
```

### With Full Platform

```bash
cd CRM
python run_all_services.py
```

### Docker

```bash
# Build
docker build -t unified-ui .

# Run
docker run -p 3005:3005 \
  -e SALES_BOT_URL=http://proposal-bot:8000 \
  -e PROXY_SECRET=your-secret \
  --env-file .env \
  unified-ui
```

### Docker Compose

```bash
cd CRM
docker-compose -f docker-compose.local.yml --env-file .env.secrets up -d
```

### Render.com

```bash
cd unified-ui
render blueprint apply
```

---

## Security

### Authentication Flow

```
1. User clicks "Sign in with Microsoft"
2. Redirect to Microsoft Azure OAuth
3. User authenticates with Microsoft
4. Microsoft redirects back with auth code
5. Supabase exchanges code for JWT
6. Frontend stores token in localStorage
7. All API requests include Authorization: Bearer <token>
8. unified-ui validates token with Supabase
9. RBAC context resolved and cached
10. Request proxied to sales-module with trusted headers
```

### Security Measures

| Measure | Implementation |
|---------|----------------|
| **CORS** | Strict origin validation |
| **Security Headers** | X-Frame-Options, X-Content-Type-Options, CSP |
| **Rate Limiting** | 10 req/min on auth endpoints |
| **Proxy Secret** | Prevents header spoofing |
| **JWT Validation** | Token validated with Supabase on every request |
| **RBAC Caching** | 30s TTL prevents stale permissions |

### Health Checks

```bash
# Basic health
curl http://localhost:3005/health

# Response:
{
  "status": "ok",
  "service": "unified-ui",
  "supabase": true,
  "sales_bot_url": "http://proposal-bot:8000",
  "environment": "development"
}
```

---

## Related Documentation

| Document | Description |
|----------|-------------|
| [FRONTEND_API.md](./FRONTEND_API.md) | Detailed API reference for frontend developers |
| [/ARCHITECTURE.md](../ARCHITECTURE.md) | Full system architecture |
| [/DEVELOPMENT.md](../DEVELOPMENT.md) | Development setup guide |
| [/DEPLOYMENT.md](../DEPLOYMENT.md) | Deployment options |
| [/sales-module/README.md](../sales-module/README.md) | Sales module documentation |

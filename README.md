# Sales Proposals Bot

An enterprise-grade AI-powered sales intelligence platform that automates proposal generation, billboard mockup creation, and booking order management. Built with a dual-service architecture featuring a Python FastAPI backend and Node.js Express frontend.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Directory Structure](#directory-structure)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Backend (proposal-bot)](#backend-proposal-bot)
- [Frontend (unified-ui)](#frontend-unified-ui)
- [Database Schema](#database-schema)
- [RBAC System](#rbac-system)
- [Deployment](#deployment)
- [Development](#development)
- [Security](#security)

---

## Overview

Sales Proposals Bot provides:

- **AI-Powered Proposal Generation**: Create professional sales proposals with financial calculations, VAT, and currency conversion
- **Billboard Mockup Generation**: Generate realistic billboard mockups with perspective transformation and effects
- **Booking Order Management**: Multi-stage approval workflows with Slack integration
- **Multi-Channel Support**: Slack bot and web interface with feature parity
- **Enterprise RBAC**: 4-level role-based access control with multi-tenancy
- **Microsoft SSO**: Enterprise authentication via Azure AD

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           CLIENTS                                    │
├─────────────────────┬───────────────────────────────────────────────┤
│     Slack Bot       │              Web Browser                       │
│   (Events API)      │                                               │
└─────────┬───────────┴───────────────────┬───────────────────────────┘
          │                               │
          │                               ▼
          │                   ┌───────────────────────┐
          │                   │   unified-ui:3005     │
          │                   │   ─────────────────   │
          │                   │   • Express.js Server │
          │                   │   • JWT Validation    │
          │                   │   • RBAC Lookup       │
          │                   │   • Trusted Headers   │
          │                   │   • SPA Frontend      │
          │                   │   • Microsoft SSO     │
          │                   └───────────┬───────────┘
          │                               │
          ▼                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      proposal-bot:8000 (FastAPI)                     │
├─────────────────────────────────────────────────────────────────────┤
│  API Layer                                                           │
│  ├── /api/chat          Chat messaging & streaming                   │
│  ├── /api/proposals     Proposal CRUD & listing                      │
│  ├── /api/mockup        Mockup generation                            │
│  ├── /api/files         File upload/download                         │
│  ├── /api/admin         User & permission management                 │
│  ├── /slack             Slack events & interactive handlers          │
│  └── /health            Health checks & metrics                      │
├─────────────────────────────────────────────────────────────────────┤
│  Core Layer                                                          │
│  ├── llm.py             Main LLM orchestration loop                  │
│  ├── chat_api.py        Unified chat interface                       │
│  ├── proposals.py       Proposal generation logic                    │
│  └── tools.py           LLM tool definitions                         │
├─────────────────────────────────────────────────────────────────────┤
│  Generators                                                          │
│  ├── pptx.py            PowerPoint generation                        │
│  ├── pdf.py             PDF conversion & merging                     │
│  └── mockup.py          Billboard mockup compositing                 │
├─────────────────────────────────────────────────────────────────────┤
│  Integrations                                                        │
│  ├── llm/               OpenAI & Google Generative AI                │
│  ├── auth/              Supabase Auth                                │
│  ├── storage/           Local & Supabase Storage                     │
│  ├── rbac/              Role-based access control                    │
│  └── channels/          Slack & Web adapters                         │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         DATA LAYER                                   │
├───────────────────────────┬─────────────────────────────────────────┤
│   SQLite (Development)    │     Supabase PostgreSQL (Production)    │
│   proposals.db            │     ├── UI Project (Auth/RBAC)          │
│                           │     └── Sales Bot Project (Business)    │
└───────────────────────────┴─────────────────────────────────────────┘
```

---

## Tech Stack

### Backend (proposal-bot)

| Component | Technology |
|-----------|------------|
| Runtime | Python 3.11 |
| Framework | FastAPI, Uvicorn |
| Database | SQLite (dev) / Supabase PostgreSQL (prod) |
| LLM | OpenAI GPT-4 / Google Gemini Pro |
| Storage | Local filesystem / Supabase Storage |
| Document Gen | python-pptx, LibreOffice, PyPDF2 |
| Image Processing | Pillow, NumPy, OpenCV |

### Frontend (unified-ui)

| Component | Technology |
|-----------|------------|
| Runtime | Node.js 18+ |
| Framework | Express.js |
| Authentication | Supabase Auth, Microsoft SSO |
| Frontend | Vanilla JavaScript SPA |
| Styling | Custom CSS Design System ("The Void") |
| Real-time | Server-Sent Events (SSE) |

---

## Directory Structure

```
Sales Proposals/
├── api/                          # FastAPI application
│   ├── server.py                 # App initialization & middleware
│   ├── auth.py                   # Authentication dependencies
│   ├── schemas.py                # Pydantic request/response models
│   ├── middleware/               # Custom middleware
│   │   ├── security_headers.py
│   │   ├── api_key.py
│   │   └── rate_limit.py
│   └── routers/                  # API endpoint modules
│       ├── proposals.py          # Proposal CRUD
│       ├── chat.py               # Chat messaging
│       ├── mockups.py            # Mockup generation
│       ├── files.py              # File handling
│       ├── slack.py              # Slack integration
│       ├── admin.py              # User management
│       ├── costs.py              # AI cost tracking
│       └── health.py             # Health checks
│
├── core/                         # Business logic
│   ├── llm.py                    # Main LLM loop & tool execution
│   ├── chat_api.py               # Unified chat interface
│   ├── chat_persistence.py       # Session management
│   ├── proposals.py              # Proposal generation
│   ├── tools.py                  # LLM tool definitions
│   ├── bo_messaging.py           # Booking order messaging
│   └── file_utils.py             # File operations
│
├── db/                           # Database layer
│   ├── database.py               # Database facade
│   ├── schema.py                 # Schema definitions
│   ├── cache.py                  # In-memory caching
│   ├── rls.py                    # Row-level security
│   ├── backends/
│   │   ├── sqlite.py             # SQLite backend
│   │   └── supabase.py           # Supabase backend
│   └── migrations/               # Database migrations
│
├── generators/                   # Content generation
│   ├── pptx.py                   # PowerPoint slides
│   ├── pdf.py                    # PDF conversion
│   ├── mockup.py                 # Billboard mockups
│   └── effects/                  # Image effects
│       ├── compositor.py         # Perspective compositing
│       ├── color.py              # Color adjustments
│       ├── depth.py              # Depth effects
│       └── edge.py               # Edge enhancement
│
├── integrations/                 # External services
│   ├── llm/                      # LLM providers
│   │   ├── client.py             # Unified client
│   │   ├── providers/            # OpenAI, Google
│   │   ├── prompts/              # System prompts
│   │   └── cost_tracker.py       # Cost tracking
│   ├── auth/                     # Authentication
│   ├── storage/                  # File storage
│   ├── rbac/                     # Access control
│   └── channels/                 # Slack/Web adapters
│
├── workflows/                    # Business workflows
│   ├── bo_approval.py            # BO approval state machine
│   └── bo_parser.py              # BO parsing & validation
│
├── utils/                        # Utilities
│   ├── logging.py                # Structured logging
│   ├── time.py                   # UAE timezone
│   ├── task_queue.py             # Background tasks
│   └── memory.py                 # Memory management
│
├── unified-ui/                   # Frontend application
│   ├── server.js                 # Express server (auth gateway + proxy)
│   ├── email-service.js          # Email provider abstraction
│   ├── email-templates.js        # HTML email templates
│   ├── package.json              # Node.js dependencies
│   ├── Dockerfile                # Frontend Docker image
│   ├── public/                   # Static assets (SPA)
│   │   ├── index.html            # Main HTML shell
│   │   ├── css/
│   │   │   └── styles.css        # Design system
│   │   └── js/
│   │       ├── app.js            # App initialization
│   │       ├── auth.js           # Authentication module
│   │       ├── api.js            # API client library
│   │       ├── chat.js           # Chat interface
│   │       ├── mockup.js         # Mockup generator
│   │       ├── sidebar.js        # Navigation
│   │       ├── modules.js        # Module registry
│   │       └── admin.js          # Admin panel
│   └── uploads/                  # Frontend file storage
│
├── data/                         # Runtime data
│   ├── templates/                # PowerPoint templates
│   └── currency_config.json      # Currency rates
│
├── config.py                     # Backend configuration
├── requirements.txt              # Python dependencies
├── Dockerfile                    # Backend Docker image
├── docker-compose.local.yml      # Local development
└── render.yaml                   # Render deployment
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- LibreOffice (for PDF conversion)
- Docker & Docker Compose (optional)

### Local Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/Amrtamer711/SalesProposalAI.git
   cd "Sales Proposals"
   ```

2. **Backend Setup**
   ```bash
   # Create virtual environment
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or: venv\Scripts\activate  # Windows

   # Install dependencies
   pip install -r requirements.txt

   # Set up environment
   cp .env.example .env.secrets
   # Edit .env.secrets with your credentials

   # Run backend
   python main.py
   # Server starts at http://localhost:8000
   ```

3. **Frontend Setup** (in a separate terminal)
   ```bash
   cd unified-ui
   npm install
   npm start
   # Frontend starts at http://localhost:3005
   ```

### Docker Development

```bash
# Start both services
docker-compose -f docker-compose.local.yml --env-file .env.secrets up -d

# View logs
docker-compose -f docker-compose.local.yml logs -f

# Stop services
docker-compose -f docker-compose.local.yml down
```

**Access Points:**
- Unified UI: http://localhost:3005
- Proposal Bot API: http://localhost:8000
- Health Check: http://localhost:8000/health

---

## Configuration

### Environment Variables

Create `.env.secrets` from `.env.example`:

```bash
# =============================================================================
# CORE SETTINGS
# =============================================================================
ENVIRONMENT=development          # development | staging | production
DEBUG=true
LOG_LEVEL=INFO

# =============================================================================
# DATABASE (Backend)
# =============================================================================
DB_BACKEND=supabase              # sqlite | supabase

# Supabase - Sales Bot Project (business data)
SALESBOT_DEV_SUPABASE_URL=https://xxx.supabase.co
SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY=eyJ...
SALESBOT_PROD_SUPABASE_URL=https://yyy.supabase.co
SALESBOT_PROD_SUPABASE_SERVICE_ROLE_KEY=eyJ...

# =============================================================================
# AUTHENTICATION (Frontend + Backend)
# =============================================================================
AUTH_PROVIDER=supabase           # local | supabase

# Supabase - UI Project (auth & RBAC)
UI_DEV_SUPABASE_URL=https://aaa.supabase.co
UI_DEV_SUPABASE_ANON_KEY=eyJ...
UI_DEV_SUPABASE_SERVICE_ROLE_KEY=eyJ...
UI_PROD_SUPABASE_URL=https://bbb.supabase.co
UI_PROD_SUPABASE_ANON_KEY=eyJ...
UI_PROD_SUPABASE_SERVICE_ROLE_KEY=eyJ...

# =============================================================================
# LLM PROVIDERS
# =============================================================================
LLM_PROVIDER=openai              # openai | google
IMAGE_PROVIDER=openai            # openai | google
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...

# =============================================================================
# SLACK INTEGRATION
# =============================================================================
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...

# =============================================================================
# STORAGE
# =============================================================================
STORAGE_PROVIDER=supabase        # local | supabase

# =============================================================================
# API SETTINGS
# =============================================================================
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:3005,http://localhost:8000

# Proxy secret for trusted header authentication
PROXY_SECRET=your-secure-random-string

# =============================================================================
# EMAIL SERVICE (Frontend)
# =============================================================================
EMAIL_PROVIDER=resend            # resend | sendgrid | smtp | console
EMAIL_FROM=noreply@yourcompany.com
RESEND_API_KEY=re_...

# =============================================================================
# BUSINESS SETTINGS
# =============================================================================
DEFAULT_CURRENCY=AED
```

---

## Backend (proposal-bot)

### API Endpoints

| Endpoint | Method | Description | Permission |
|----------|--------|-------------|------------|
| **Chat** |
| `/api/chat/message` | POST | Send chat message | `sales:chat:use` |
| `/api/chat/stream` | POST | Stream response (SSE) | `sales:chat:use` |
| **Proposals** |
| `/api/proposals` | GET | List proposals | `sales:proposals:read` |
| `/api/proposals/{id}` | GET | Get proposal details | `sales:proposals:read` |
| `/api/proposals/history` | GET | Get proposal history | `sales:proposals:read` |
| **Mockups** |
| `/api/mockup/locations` | GET | List mockup locations | `sales:mockups:read` |
| `/api/mockup/generate` | POST | Generate mockup | `sales:mockups:create` |
| `/api/mockup/save-frame` | POST | Save frame reference | `sales:mockups:setup` |
| **Files** |
| `/api/files/upload` | POST | Upload single file | authenticated |
| `/api/files/upload/multi` | POST | Upload multiple files | authenticated |
| `/api/files/{id}/{name}` | GET | Download file | authenticated |
| **Admin** |
| `/api/admin/users` | GET/POST | User management | `core:users:manage` |
| `/api/admin/profiles` | GET/POST | Profile management | `core:system:admin` |
| `/api/admin/permissions` | GET | List all permissions | `core:system:admin` |
| **Costs** |
| `/costs` | GET | Get AI cost summary | authenticated |
| `/costs/clear` | DELETE | Clear cost history | `core:ai_costs:manage` |
| **Modules** |
| `/api/modules` | GET | List accessible modules | authenticated |
| **Health** |
| `/health` | GET | Basic health check | public |
| `/health/ready` | GET | Readiness probe | public |
| `/metrics` | GET | Performance metrics | public |
| **Slack** |
| `/slack/events` | POST | Slack Events API | Slack signature |
| `/slack/interactive` | POST | Interactive components | Slack signature |

### Core Modules

#### LLM Orchestration (`core/llm.py`)

Central AI orchestration that:
1. Receives messages from chat or Slack
2. Loads conversation history from session
3. Calls LLM with system prompt and tool definitions
4. Executes tool calls (proposals, mockups, BOs)
5. Handles streaming responses
6. Persists conversation and results

**Available Tools:**
| Tool | Description |
|------|-------------|
| `get_separate_proposals` | Individual location proposals |
| `get_combined_proposal` | Multi-location package proposal |
| `generate_mockup` | Billboard mockup generation |
| `get_booking_orders` | Retrieve booking orders |
| `submit_booking_order` | Create booking order |
| `list_locations` | List available locations |
| `add_location` | Admin: Add new location |
| `delete_location` | Admin: Remove location |

#### Proposal Generation (`core/proposals.py`)

1. Creates financial slides with duration/rate matrix
2. Applies location templates from `data/templates/`
3. Calculates VAT (5%) and municipality fees
4. Converts PPTX to PDF via LibreOffice
5. Merges individual PDFs into combined document
6. Logs proposal to database

#### Mockup Generation (`generators/mockup.py`)

1. Selects location photo (day/night, gold/silver variants)
2. Loads creative image
3. Applies perspective transformation to frame coordinates
4. Composites creative onto billboard
5. Applies post-processing effects
6. Saves and returns mockup URL

---

## Frontend (unified-ui)

### Server Architecture (`server.js`)

The Express.js server acts as:
- **Authentication Gateway**: Validates JWT tokens from Supabase
- **RBAC Provider**: Fetches user profiles, permissions, teams, companies
- **Proxy Layer**: Routes requests to proposal-bot with trusted headers
- **Static Server**: Serves the SPA frontend

#### Trusted Header Injection

When proxying requests to proposal-bot, unified-ui injects:
```
X-Trusted-User-Id: user-uuid
X-Trusted-User-Email: user@example.com
X-Trusted-User-Name: John Doe
X-Trusted-User-Profile: sales_user
X-Trusted-User-Permissions: ["sales:proposals:create", ...]
X-Trusted-User-Companies: ["company-uuid-1", ...]
X-Proxy-Secret: configured-secret
```

### Frontend Modules

| Module | File | Purpose |
|--------|------|---------|
| **Auth** | `auth.js` | Authentication, SSO, session management |
| **API** | `api.js` | Backend communication, token injection |
| **Chat** | `chat.js` | AI chat interface, streaming responses |
| **Mockup** | `mockup.js` | Billboard mockup creation |
| **Sidebar** | `sidebar.js` | Tool navigation |
| **Modules** | `modules.js` | Dynamic module loading |
| **Admin** | `admin.js` | User/permission management |
| **App** | `app.js` | Application initialization |

### Authentication Flow

**Production (Microsoft SSO):**
```
1. User clicks "Sign in with Microsoft"
2. Redirect to Microsoft Azure OAuth
3. User authenticates with Microsoft credentials
4. Microsoft redirects back with auth code
5. Supabase exchanges code for JWT token
6. Frontend stores token in localStorage
7. Frontend fetches user profile from /api/base/auth/me
8. Shows app with user permissions loaded
```

**Development Mode:**
```
Pre-configured test users:
- admin@mmg.com / admin123 (admin, hos, sales_person)
- hos@mmg.com / hos123 (hos, sales_person)
- sales@mmg.com / sales123 (sales_person)
```

### Design System

**Theme: "The Void"** - Dark, futuristic design

| Category | Colors | Usage |
|----------|--------|-------|
| Void | `#000` - `#1E1E26` | Backgrounds |
| Quantum Blue | `#3381FF` | Primary CTAs |
| Plasma Cyan | `#06B6D4` | Secondary highlights |
| Nebula Purple | `#A855F7` | Tertiary accents |
| Aurora Green | `#22C55E` | Success states |
| Solar Yellow | `#EAB308` | Warnings |
| Crimson Red | `#F43F5E` | Errors |

**Features:**
- Glass morphism effects
- Gradient animations
- Quantum glow shadows
- Spring easing animations
- Inter font family

### Tools/Panels

1. **AI Chat** (Default)
   - Streaming AI responses
   - File attachments (images, PDFs, documents)
   - Suggestion buttons
   - Conversation history

2. **Mockup Generator**
   - **Setup Mode** (Admin): Configure billboard frames, upload photos
   - **Generate Mode**: Create mockups from creatives
   - Canvas-based frame drawing
   - Live preview

3. **Proposals**
   - Proposal listing with filters
   - Proposal details view

4. **Admin Panel** (Admins only)
   - User CRUD
   - Profile/permission management
   - Team management
   - Invite system

### Email Service

**Supported Providers:**
- Resend (recommended)
- SendGrid
- SMTP (generic)
- Console (development)

**Templates:**
- User invitation
- Welcome email
- Password reset

---

## Database Schema

### UI Supabase (Auth & RBAC)

```sql
-- Users & Authentication
users (id, email, password_hash, name, created_at)
profiles (id, name, display_name, description, is_system)
user_profiles (user_id, profile_id)

-- RBAC Level 1: Base Permissions
profile_permissions (id, profile_id, permission)

-- RBAC Level 2: Permission Sets
permission_sets (id, name, display_name, is_active)
permission_set_permissions (id, permission_set_id, permission)
user_permission_sets (user_id, permission_set_id)

-- RBAC Level 3: Teams & Hierarchy
teams (id, name, parent_team_id)
team_members (id, team_id, user_id, role)
team_roles (id, team_id, name)

-- RBAC Level 4: Record Sharing
sharing_rules (id, name)
record_shares (id, sharing_rule_id, user_id, record_key)

-- Multi-Tenancy
companies (id, name, is_group, parent_company_id)
user_companies (user_id, company_id)

-- Modules & Sessions
modules (id, name, display_name, icon)
chat_sessions (user_id, session_id, messages)
invite_tokens (token, email, expires_at)
```

### Sales Bot Supabase (Business Data)

```sql
-- Public Schema
proposals_log (id, submitted_by, client_name, date_generated, total_amount)
proposal_locations (proposal_id, location_key, start_date, duration_weeks, net_rate)
booking_orders (id, user_id, client_name, total_value, status)
bo_locations (bo_id, location_key, start_date, end_date, spots, rate)
bo_approval_workflows (id, bo_id, status, stage, assignee)
ai_costs (id, user_id, provider, model, tokens_in, tokens_out, cost, workflow)
documents (id, user_id, filename, file_id, storage_path, created_at)
mockup_files (id, location_key, finish, time_of_day, filename, file_id)

-- Company Schemas (e.g., backlite_dubai, backlite_uk)
locations (id, location_key, display_name, height, width, series)
location_photos (id, location_id, photo_path, time_of_day, finish)
mockup_frames (id, location_id, frame_points, config)
rate_cards (id, location_id, duration, net_rate, upload_fee)
location_occupations (id, location_id, sov, spot_duration, loop_duration)
```

---

## RBAC System

### 4-Level Permission Architecture

| Level | Description | Example |
|-------|-------------|---------|
| **1. Profiles** | Base permission templates | `sales_user` profile has `sales:proposals:create` |
| **2. Permission Sets** | Additive permissions (can expire) | Grant `mockup:setup` temporarily |
| **3. Teams** | Hierarchical access | Team leaders see members' data |
| **4. Record Sharing** | Individual record access | Share specific proposal with user |

### Permission Format

```
{module}:{resource}:{action}
```

**Examples:**
- `sales:proposals:create` - Create proposals
- `sales:*:*` - All sales module actions
- `core:system:admin` - System administration
- `*:*:*` - Super admin

### User Roles

| Role | Description | Permissions |
|------|-------------|-------------|
| `system_admin` | Full system access | `*:*:*` |
| `sales_manager` | Manage sales team | `sales:*:*`, team visibility |
| `sales_user` | Standard sales | `sales:proposals:*`, `sales:chat:use` |
| `coordinator` | BO coordination | `sales:bo:*` |
| `finance` | Financial review | `sales:bo:approve`, cost viewing |
| `viewer` | Read-only access | `*:*:read` |

---

## Deployment

### Render.com (`render.yaml`)

Three microservices:

| Service | Type | Port | Health Check |
|---------|------|------|--------------|
| `proposal-bot` | Docker | 8000 | `/health` |
| `unified-ui` | Docker | 3005 | `/health` |
| `ai-costs-dashboard` | Docker | 3000 | `/health` |

**Environment Strategy:**
- `dev` branch → DEV environment variables
- `main` branch → PROD environment variables

### Docker Images

**Backend (`Dockerfile`):**
```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y libreoffice fonts-dejavu
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

**Frontend (`unified-ui/Dockerfile`):**
```dockerfile
FROM node:18-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
CMD ["node", "server.js"]
```

---

## Development

### Code Quality

```bash
# Linting
ruff check .

# Format
ruff format .

# Type checking
mypy .

# Security scan
bandit -r .
```

### Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=. --cov-report=html

# Specific test
pytest tests/test_proposals.py -v
```

### Database Migrations

```bash
python -m db.migrations
```

---

## Security

### Authentication Flow

```
User Login (Web) → Supabase Auth → JWT Token
    ↓
Request to unified-ui with JWT
    ↓
unified-ui validates token with Supabase
    ↓
Fetches RBAC data (profiles, permissions, teams, companies)
    ↓
Injects trusted headers + proxy secret
    ↓
Routes to proposal-bot
    ↓
proposal-bot reads trusted headers (trusts proxy)
    ↓
Serves protected resources
```

### Security Measures

- **CORS**: Strict origin validation
- **Helmet.js**: Security headers (CSP, COEP, CORP)
- **Rate Limiting**: 10 requests/minute on auth endpoints
- **Proxy Secret**: Prevents header spoofing
- **Row-Level Security**: Supabase RLS policies
- **Company Isolation**: Multi-tenant data separation

---

## License

Proprietary - All rights reserved.

---

## Support

For issues and feature requests, contact the development team or open an issue in the repository.

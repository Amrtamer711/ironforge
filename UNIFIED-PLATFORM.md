# Unified Platform - Complete Technical Documentation

> **Last Updated**: December 2025
> **Status**: Production on Render + Supabase

This document provides a complete overview of everything implemented in the Unified Platform.

---

## Table of Contents

1. [Platform Overview](#platform-overview)
2. [Architecture](#architecture)
3. [What's Implemented](#whats-implemented)
4. [Backend API](#backend-api)
5. [Frontend (Unified UI)](#frontend-unified-ui)
6. [Authentication & Authorization](#authentication--authorization)
7. [Database](#database)
8. [Integrations](#integrations)
9. [Deployment](#deployment)
10. [What's NOT Implemented](#whats-not-implemented)

---

## Platform Overview

The Unified Platform is an AI-powered sales operations system for BackLite Media with two interfaces:

| Interface | Purpose | Status |
|-----------|---------|--------|
| **Slack Bot** | Original interface - sales team uses Slack to generate proposals, mockups, process booking orders | Production |
| **Unified UI** | Web interface - same functionality via browser, token-based auth | Production |

### Core Capabilities

| Feature | Description | Channels |
|---------|-------------|----------|
| **Proposal Generation** | Create branded PowerPoint proposals with automatic calculations | Slack, Web |
| **Mockup Generation** | Visualize creatives on billboard photos (upload or AI-generated) | Slack, Web |
| **Booking Order Processing** | Parse, review, and approve booking orders with multi-stage workflow | Slack only |
| **Chat with AI** | Natural language interface to all tools | Slack, Web |
| **File Upload** | Images, PDFs, Excel, Word documents | Slack, Web |
| **Admin Tools** | Location management, exports, user management | Slack, Web |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENTS                                      │
│  ┌──────────────────┐              ┌──────────────────┐             │
│  │   Slack App      │              │   Web Browser    │             │
│  │   (Original)     │              │   (Unified UI)   │             │
│  └────────┬─────────┘              └────────┬─────────┘             │
└───────────┼─────────────────────────────────┼───────────────────────┘
            │                                 │
            ▼                                 ▼
┌───────────────────────┐         ┌───────────────────────┐
│   Slack Events API    │         │   unified-ui/server.js │
│   (Webhook)           │         │   (Express Gateway)    │
│   /slack/events       │         │   Port 3005            │
│   /slack/interactive  │         │   - Auth routes        │
└───────────┬───────────┘         │   - Invite tokens      │
            │                     │   - Proxy to Sales Bot │
            │                     └───────────┬────────────┘
            │                                 │
            └─────────────┬───────────────────┘
                          │
                          ▼
            ┌─────────────────────────────┐
            │      Sales Bot (FastAPI)    │
            │      Port 8000              │
            │                             │
            │  ┌──────────────────────┐   │
            │  │   API Routers        │   │
            │  │   - /api/chat        │   │
            │  │   - /api/files       │   │
            │  │   - /api/mockup      │   │
            │  │   - /api/proposals   │   │
            │  │   - /api/admin       │   │
            │  │   - /slack/events    │   │
            │  └──────────────────────┘   │
            │                             │
            │  ┌──────────────────────┐   │
            │  │   Core Business      │   │
            │  │   - LLM Processing   │   │
            │  │   - Proposal Gen     │   │
            │  │   - Mockup Gen       │   │
            │  │   - BO Workflows     │   │
            │  └──────────────────────┘   │
            │                             │
            │  ┌──────────────────────┐   │
            │  │   Integrations       │   │
            │  │   - OpenAI/Gemini    │   │
            │  │   - Supabase Auth    │   │
            │  │   - Supabase Storage │   │
            │  │   - Slack SDK        │   │
            │  └──────────────────────┘   │
            └─────────────┬───────────────┘
                          │
                          ▼
            ┌─────────────────────────────┐
            │      Supabase               │
            │                             │
            │   Auth (JWT/JWKS)           │
            │   Database (PostgreSQL)     │
            │   Storage (Files)           │
            └─────────────────────────────┘
```

---

## What's Implemented

### Chat System

| Feature | Status | Details |
|---------|--------|---------|
| Send messages | Done | Text messages to AI |
| Stream responses | Done | Real-time SSE streaming |
| File uploads | Done | Images, PDFs, Excel, Word (200MB max) |
| Chat history | Done | Persisted to database, loads on login |
| Conversation sessions | Done | Per-user sessions |
| Clear conversation | Done | Start fresh |
| Tool execution | Done | AI can call 15 different tools |

### Proposal Generation

| Feature | Status | Details |
|---------|--------|---------|
| Single location proposals | Done | Multiple duration/rate options per slide |
| Multi-location (separate) | Done | Individual PPT per location + combined PDF |
| Combined package deals | Done | One slide with all locations, single total |
| PowerPoint generation | Done | Branded templates with calculations |
| PDF conversion | Done | Combined PDFs for easy sharing |
| Proposal history | Done | Saved to database, exportable to Excel |
| Currency support | Done | AED, USD, EUR, GBP |
| Payment terms | Done | Customizable |

### Mockup Generation

| Feature | Status | Details |
|---------|--------|---------|
| Upload creative | Done | User uploads image(s) |
| AI-generated creative | Done | Describe what you want, AI creates it |
| Frame mapping | Done | Precise corner coordinates |
| Multi-frame support | Done | 1-N frames per billboard |
| Day/night variants | Done | Different photos per time |
| Gold/silver finish | Done | Different billboard finishes |
| 30-min creative cache | Done | Reuse creative for other locations |
| Live preview | Done | Test before saving |
| 14 adjustment sliders | Done | Brightness, contrast, blur, etc. |
| Green screen detection | Done | Auto-detect billboard screen |

### Mockup Setup (Admin)

| Feature | Status | Details |
|---------|--------|---------|
| Photo upload | Done | Upload billboard photos |
| Frame drawing | Done | Click-drag to mark frames |
| Corner editing | Done | Drag or arrow keys for precision |
| Save templates | Done | Multiple frames per photo |
| Time/finish variants | Done | Day/night, gold/silver |

### Booking Order Processing (Slack Only)

| Feature | Status | Details |
|---------|--------|---------|
| Document parsing | Done | Excel, PDF, images |
| Data extraction | Done | Client, locations, fees, dates |
| Multi-stage approval | Done | Sales → Coordinator → HoS → Finance |
| In-thread editing | Done | Change any field, auto-recalculates |
| VAT calculation | Done | 5% automatic |
| PDF generation | Done | Professional booking order docs |
| Digital signatures | Done | HoS signature on approval |
| Rejection workflow | Done | With feedback to previous stage |
| Backlite/Viola support | Done | Both companies |

### Authentication

| Feature | Status | Details |
|---------|--------|---------|
| Supabase Auth | Done | JWT tokens with ES256/JWKS |
| Email/password login | Done | Standard sign-in |
| Invite token signup | Done | Admin creates token, user signs up |
| Token expiry | Done | 1-30 days configurable |
| Role-based access | Done | 6 profile types |
| Session persistence | Done | localStorage + Supabase |
| Local dev mode | Done | Hardcoded test users |

### Admin Features

| Feature | Status | Details |
|---------|--------|---------|
| User management | Done | Create, edit, delete users |
| Role assignment | Done | Assign profiles to users |
| Invite tokens | Done | Create, list, revoke |
| Location management | Done | Add, delete, list locations |
| Export to Excel | Done | Proposals and booking orders |
| Health endpoints | Done | Status, readiness, metrics |
| Cost tracking | Done | AI usage costs |

### File Management

| Feature | Status | Details |
|---------|--------|---------|
| Upload endpoint | Done | Single and multi-file |
| Download endpoint | Done | Auth required |
| Supabase Storage | Done | Cloud storage for production |
| Local storage | Done | Disk storage for development |
| Signed URLs | Done | Temporary download links |
| Path validation | Done | Security against traversal |
| MIME type whitelist | Done | Only allowed types |

---

## Backend API

### API Routers

| Router | Prefix | Auth | Purpose |
|--------|--------|------|---------|
| `auth_routes.py` | `/api/auth` | Varies | Login, logout, user info |
| `chat.py` | `/api/chat` | Required | Chat messaging, streaming, history |
| `files.py` | `/api/files` | Required | File upload/download |
| `proposals.py` | `/api/proposals` | Required | Proposal history |
| `mockups.py` | `/api/mockup` | Required | Mockup generation |
| `admin.py` | `/api/admin` | Admin | RBAC, users, permissions |
| `health.py` | `/health` | None | Health checks, metrics |
| `costs.py` | `/costs` | Admin | AI cost tracking |
| `slack.py` | `/slack` | Slack | Slack events, interactive |

### Key Endpoints

```
# Chat
POST   /api/chat/message      - Send message (sync)
POST   /api/chat/stream       - Send message (SSE streaming)
GET    /api/chat/history      - Load persisted history
POST   /api/chat/conversation - Create new conversation
DELETE /api/chat/conversation/{id} - Clear conversation

# Files
POST   /api/files/upload      - Upload file (multipart)
GET    /api/files/{id}/{name} - Download file

# Mockup
GET    /api/mockup/locations  - List available locations
POST   /api/mockup/generate   - Generate mockup
POST   /api/mockup/save-frame - Save frame config (admin)

# Proposals
GET    /api/proposals/history - Get proposal history

# Health
GET    /health                - Basic health check
GET    /health/ready          - Dependency status
GET    /metrics               - Performance metrics
```

### LLM Tools (15 total)

| Tool | Access | Description |
|------|--------|-------------|
| `get_separate_proposals` | All | Generate individual proposals per location |
| `get_combined_proposal` | All | Generate combined package proposal |
| `list_locations` | All | List available billboard locations |
| `generate_mockup` | All | Generate billboard mockup |
| `parse_booking_order` | All | Parse BO document |
| `refresh_templates` | All | Refresh location templates cache |
| `edit_task_flow` | All | Edit task in approval workflow |
| `add_location` | Admin | Add new location |
| `delete_location` | Admin | Delete location |
| `export_proposals_to_excel` | Admin | Export all proposals |
| `get_proposals_stats` | Admin | Proposal statistics |
| `export_booking_orders_to_excel` | Admin | Export all BOs |
| `fetch_booking_order` | Admin | Fetch BO by number |
| `revise_booking_order` | Admin | Start BO revision |
| `code_interpreter` | Admin | Raw code execution |

---

## Frontend (Unified UI)

### Server (Express)

```javascript
// unified-ui/server.js - Port 3005

Routes:
  GET  /health                     - Server status
  GET  /api/base/config.js         - Supabase credentials
  GET  /api/base/auth/session      - Check session
  GET  /api/base/auth/me           - Get user profile
  POST /api/base/auth/invites      - Create invite (admin)
  GET  /api/base/auth/invites      - List invites (admin)
  DELETE /api/base/auth/invites/:id - Revoke invite (admin)
  POST /api/base/auth/validate-invite - Validate token
  POST /api/base/auth/consume-invite  - Mark token used

  /api/sales/*  →  Proxy to Sales Bot (http://localhost:8000/api/*)

Middleware:
  - Helmet (security headers)
  - CORS (environment-aware)
  - Body parser (10MB limit)
  - Request logging
  - Rate limiting (auth endpoints)
```

### JavaScript Modules

| File | Purpose |
|------|---------|
| `auth.js` | Supabase auth, login/signup, session management |
| `api.js` | Centralized API client with auth headers |
| `chat.js` | Chat interface, streaming, file upload |
| `app.js` | Toast notifications, MockupStudio canvas tool |
| `sidebar.js` | Navigation, tool switching |
| `admin.js` | User/invite management |
| `modules.js` | Module registry (future multi-module) |

### UI Components

```
Landing Page
  - Hero section
  - Features grid
  - Stats section
  - Login button

Login Modal
  - Sign In tab (email/password)
  - Sign Up tab (invite token + email/password)

App Shell
  - Header (logo, user menu)
  - Sidebar (Chat, Mockup, Proposals, Admin)
  - Main content area

Chat Panel
  - Message history
  - Input with file upload
  - Suggestion buttons
  - Streaming responses

Mockup Panel (Setup Mode)
  - Photo upload
  - Canvas with frame drawing
  - 14 adjustment sliders
  - Live preview

Admin Panel
  - User list
  - Invite token management
  - Role assignment
```

---

## Authentication & Authorization

### Auth Providers

| Provider | Environment | Method |
|----------|-------------|--------|
| Supabase | Production | JWT with JWKS (ES256) |
| Local Dev | Development | Hardcoded users, generated tokens |

### Profiles (Roles)

| Profile | Access Level |
|---------|--------------|
| `system_admin` | Full access to everything |
| `sales_manager` | Manage sales team |
| `sales_user` | Generate proposals, mockups |
| `coordinator` | BO coordination |
| `finance` | Financial oversight |
| `viewer` | Read-only |

### Invite Token Flow

```
1. Admin creates invite: POST /api/base/auth/invites
   → Token generated, stored with email + profile

2. User receives invite link/token

3. User enters token + email + password in signup form

4. Frontend validates: POST /api/base/auth/validate-invite
   → Returns profile_name if valid

5. Supabase creates auth user

6. Frontend consumes: POST /api/base/auth/consume-invite
   → Marks token used, creates user record with profile
```

### Permissions System

```
Permission format: module:resource:action

Examples:
  sales:proposals:create
  sales:proposals:view
  admin:users:manage
  mockup:templates:edit

Checked via RBAC client:
  rbac.has_permission(user_id, "sales:proposals:create")
```

---

## Database

### Backends Supported

| Backend | Use Case | Configuration |
|---------|----------|---------------|
| SQLite | Development | Default, no setup needed |
| Supabase | Production | PostgreSQL with RLS |

### Tables (UI Supabase - Auth)

| Table | Purpose |
|-------|---------|
| `profiles` | Role templates (system_admin, sales_user, etc.) |
| `profile_permissions` | Permissions per profile |
| `permission_sets` | Additive permission groups |
| `user_permission_sets` | User → permission set mapping |
| `users` | User accounts (email, name, profile_id) |
| `invite_tokens` | Signup tokens (token, email, profile, expiry) |
| `permissions` | All available permissions |
| `modules` | Feature modules |
| `user_modules` | User → module access |

### Tables (Sales Bot Supabase - Business)

| Table | Purpose |
|-------|---------|
| `proposals` | Generated proposals (user, client, locations, files) |
| `booking_orders` | BOs (bo_number, client, status, workflow_status) |
| `mockups` | Generated mockups (location, user, image_path) |
| `ai_costs` | AI usage tracking (model, tokens, cost, workflow) |
| `chat_sessions` | Persisted chat messages (user_id, messages JSON) |
| `workflows` | BO approval workflow state |

### Chat Persistence

```
Schema: chat_sessions
  - user_id (primary key)
  - messages (JSON array)
  - session_id
  - created_at
  - updated_at

Message format:
{
  "id": "user-1733849522.123",
  "role": "user" | "assistant",
  "content": "Hello",
  "timestamp": "2025-12-10T12:05:22Z",
  "files": [
    {
      "file_id": "abc123",
      "filename": "creative.png",
      "url": "/api/files/abc123/creative.png",
      "mimetype": "image/png"
    }
  ]
}
```

---

## Integrations

### LLM Providers

| Provider | Models | Features |
|----------|--------|----------|
| OpenAI | gpt-4-turbo, gpt-4o, gpt-4o-mini | Vision, function calling, JSON mode |
| Google | gemini-1.5-pro, gemini-1.5-flash | Vision, tool use |

### Image Generation

| Provider | Model | Use |
|----------|-------|-----|
| OpenAI | DALL-E 3 | AI-generated creatives |
| Google | Gemini | Alternative |

### Storage Providers

| Provider | Use Case |
|----------|----------|
| Local | Development (disk) |
| Supabase Storage | Production (cloud) |

### Channel Adapters

| Adapter | Interface |
|---------|-----------|
| Slack | Slack workspace (events, interactive) |
| Web | HTTP/SSE for unified UI |

---

## Deployment

### Services (Render)

| Service | Type | Port | Purpose |
|---------|------|------|---------|
| `proposal-bot` | Web Service | 8000 | FastAPI backend |
| `unified-ui` | Web Service | 3005 | Express frontend |

### Environment Variables

```bash
# Sales Bot (proposal-bot)
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=...
DB_BACKEND=supabase

# Unified UI
SALES_BOT_URL=https://proposal-bot.onrender.com
UI_PROD_SUPABASE_URL=https://xxx.supabase.co
UI_PROD_SUPABASE_SERVICE_ROLE_KEY=...
UI_PROD_SUPABASE_ANON_KEY=...
CORS_ORIGINS=https://unified-ui.onrender.com
```

### Git Branches

| Branch | Environment |
|--------|-------------|
| `dev` | Development/testing |
| `main` | Production |

---

## What's NOT Implemented

### Features Not Yet Built

| Feature | Notes |
|---------|-------|
| **Booking Orders in Web UI** | Only Slack - would need approval buttons |
| **Real-time notifications** | No WebSocket/push notifications |
| **Multi-conversation support** | One conversation per user |
| **Message search** | Can't search chat history |
| **Message reactions** | No like/emoji reactions |
| **Team collaboration** | No shared conversations |
| **Offline support** | No service worker/PWA |
| **Mobile app** | Web only |

### Partially Implemented

| Feature | Current State | Missing |
|---------|---------------|---------|
| **RBAC** | Profiles + permissions defined | Fine-grained UI enforcement |
| **Module system** | Registry exists | Only sales module active |
| **Proposal editing** | Generate only | Can't edit after generation |
| **Mockup variations** | Single output | No batch generation |

### Deferred/Backlog

| Item | Priority | Reason |
|------|----------|--------|
| JWT decode verification | Low | Current impl is safe |
| Redis caching | When scaling | Single instance OK for now |
| WebSocket streaming | Nice-to-have | SSE works fine |
| Dark mode | Nice-to-have | Design exists |
| Data export (GDPR) | Medium | Not yet required |

---

## File Structure

```
/Users/amrtamer711/Documents/Sales Proposals/
├── api/
│   ├── routers/           # API endpoints
│   │   ├── admin.py       # RBAC management
│   │   ├── auth_routes.py # Authentication
│   │   ├── chat.py        # Chat endpoints
│   │   ├── costs.py       # AI cost tracking
│   │   ├── files.py       # File upload/download
│   │   ├── health.py      # Health checks
│   │   ├── mockups.py     # Mockup generation
│   │   ├── proposals.py   # Proposal history
│   │   └── slack.py       # Slack webhooks
│   ├── auth.py            # Auth dependency
│   ├── exceptions.py      # Error handling
│   └── server.py          # FastAPI app
├── core/
│   ├── llm.py             # Main LLM loop
│   ├── chat_api.py        # Web chat processing
│   ├── chat_persistence.py # Message storage
│   ├── proposals.py       # Proposal generation
│   ├── tools.py           # LLM tool definitions
│   ├── bo_messaging.py    # BO notifications
│   └── file_utils.py      # File operations
├── integrations/
│   ├── llm/               # LLM providers
│   ├── auth/              # Auth providers
│   ├── storage/           # Storage providers
│   ├── channels/          # Slack/Web adapters
│   └── rbac/              # Permission system
├── db/
│   ├── database.py        # DB client
│   ├── schema.py          # Table definitions
│   ├── cache.py           # In-memory caches
│   └── backends/          # SQLite/Supabase
├── unified-ui/
│   ├── server.js          # Express server
│   └── public/
│       ├── index.html     # Single page app
│       ├── css/styles.css # Styling
│       └── js/
│           ├── auth.js    # Authentication
│           ├── api.js     # API client
│           ├── chat.js    # Chat interface
│           ├── app.js     # MockupStudio
│           ├── sidebar.js # Navigation
│           ├── admin.js   # Admin panel
│           └── modules.js # Module registry
├── config.py              # Configuration
├── app_settings/          # Pydantic settings
├── requirements.txt       # Python deps
└── render.yaml            # Render deployment
```

---

## Quick Reference

### Test Users (Local Dev)

```
admin@mmg.com / admin123  → system_admin
hos@mmg.com / hos123      → head_of_sales
sales@mmg.com / sales123  → sales_user
```

### Common API Calls

```bash
# Health check
curl http://localhost:8000/health

# Send chat message
curl -X POST http://localhost:8000/api/chat/message \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "list locations"}'

# Upload file
curl -X POST http://localhost:8000/api/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@creative.png"

# Create invite (admin)
curl -X POST http://localhost:3005/api/base/auth/invites \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email": "new@user.com", "profile_name": "sales_user"}'
```

---

*This document reflects the actual implemented state of the codebase as of December 2025.*

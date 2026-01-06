# MMG Service Platform Architecture

A comprehensive technical architecture document for the MMG Service Platform. This document covers the entire system architecture including both unified-ui (authentication gateway) and sales-module (proposal bot) services, detailing system design, component interactions, data flows, and implementation patterns.

> **Scope**: This is the global architecture document. For service-specific details, see [src/unified-ui/README.md](./src/unified-ui/README.md) and [src/sales-module/README.md](./src/sales-module/README.md).

## Table of Contents

- [System Overview](#system-overview)
- [Service Architecture](#service-architecture)
- [Request Flow](#request-flow)
- [Authentication Architecture](#authentication-architecture)
- [RBAC Architecture](#rbac-architecture)
- [Database Architecture](#database-architecture)
- [LLM Integration Architecture](#llm-integration-architecture)
- [File Storage Architecture](#file-storage-architecture)
- [Channel Abstraction](#channel-abstraction)
- [Generator Pipeline](#generator-pipeline)
- [Caching Architecture](#caching-architecture)
- [Concurrency & Performance](#concurrency--performance)
- [Error Handling](#error-handling)
- [Deployment Architecture](#deployment-architecture)
- [Security Architecture](#security-architecture)
- [Monitoring & Observability](#monitoring--observability)

---

## System Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL CLIENTS                                │
├─────────────────────┬─────────────────────────┬─────────────────────────────┤
│     Web Browser     │      Slack Client       │      Mobile Browser         │
└──────────┬──────────┴───────────┬─────────────┴──────────────┬──────────────┘
           │                      │                            │
           ▼                      │                            ▼
┌─────────────────────────────────┼───────────────────────────────────────────┐
│                          GATEWAY LAYER                                       │
├─────────────────────────────────┼───────────────────────────────────────────┤
│  ┌─────────────────────────┐    │    ┌─────────────────────────┐            │
│  │    unified-ui:3005      │    │    │  Slack Events API       │            │
│  │    ─────────────────    │    │    │  (Webhook endpoint)     │            │
│  │  • FastAPI Gateway      │    │    └───────────┬─────────────┘            │
│  │  • JWT Validation       │    │                │                          │
│  │  • RBAC Resolution      │    │                │                          │
│  │  • SPA Static Serving   │    │                │                          │
│  │  • Proxy to Backend     │    │                │                          │
│  └───────────┬─────────────┘    │                │                          │
│              │                  │                │                          │
└──────────────┼──────────────────┼────────────────┼──────────────────────────┘
               │                  │                │
               │  Trusted Headers │                │ Slack Signature
               │  (X-Trusted-*)   │                │ Verification
               ▼                  │                ▼
┌─────────────────────────────────┴────────────────────────────────────────────┐
│                          APPLICATION LAYER                                    │
├──────────────────────────────────────────────────────────────────────────────┤
│                        proposal-bot:8000 (FastAPI)                            │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                           API ROUTERS                                    │ │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐           │ │
│  │  │  chat   │ │proposals│ │ mockups │ │  files  │ │  slack  │           │ │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘           │ │
│  │       │           │           │           │           │                 │ │
│  └───────┼───────────┼───────────┼───────────┼───────────┼─────────────────┘ │
│          │           │           │           │           │                   │
│          ▼           ▼           ▼           ▼           ▼                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                           CORE LAYER                                     │ │
│  │  ┌───────────────────────────────────────────────────────────────────┐  │ │
│  │  │                     main_llm_loop (core/llm.py)                    │  │ │
│  │  │  • Message Processing    • Tool Execution    • Response Streaming  │  │ │
│  │  └───────────────────────────────────────────────────────────────────┘  │ │
│  │       │              │              │              │                     │ │
│  │       ▼              ▼              ▼              ▼                     │ │
│  │  ┌─────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐               │ │
│  │  │proposals│   │  mockup  │   │    bo    │   │  tools   │               │ │
│  │  │generator│   │generator │   │ workflow │   │  router  │               │ │
│  │  └─────────┘   └──────────┘   └──────────┘   └──────────┘               │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                      │                                        │
│                                      ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                        GENERATORS LAYER                                  │ │
│  │  ┌─────────────┐   ┌─────────────┐   ┌─────────────────────────────┐    │ │
│  │  │   pptx.py   │   │   pdf.py    │   │        mockup.py            │    │ │
│  │  │  PowerPoint │   │    PDF      │   │  ┌─────────────────────┐    │    │ │
│  │  │  Generation │   │ Conversion  │   │  │     effects/        │    │    │ │
│  │  └─────────────┘   └─────────────┘   │  │ compositor, color,  │    │    │ │
│  │                                       │  │ depth, edge         │    │    │ │
│  │                                       │  └─────────────────────┘    │    │ │
│  │                                       └─────────────────────────────┘    │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                      │                                        │
└──────────────────────────────────────┼────────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                          INTEGRATION LAYER                                    │
├──────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │    llm/     │  │   auth/     │  │  storage/   │  │   rbac/     │         │
│  │  ─────────  │  │  ─────────  │  │  ─────────  │  │  ─────────  │         │
│  │  OpenAI     │  │  Supabase   │  │  Local      │  │  Static     │         │
│  │  Google     │  │  Local Dev  │  │  Supabase   │  │  Database   │         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
│         │                │                │                │                 │
│  ┌──────┴────────────────┴────────────────┴────────────────┴──────┐         │
│  │                    channels/                                    │         │
│  │  ┌─────────────────┐           ┌─────────────────┐             │         │
│  │  │  SlackAdapter   │           │   WebAdapter    │             │         │
│  │  └─────────────────┘           └─────────────────┘             │         │
│  └────────────────────────────────────────────────────────────────┘         │
└──────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                            DATA LAYER                                         │
├────────────────────────────────┬─────────────────────────────────────────────┤
│       db/database.py           │                                              │
│       (Facade Pattern)         │                                              │
│  ┌─────────────────────────────┴─────────────────────────────────────────┐   │
│  │                                                                        │   │
│  │   ┌─────────────────────┐         ┌─────────────────────┐             │   │
│  │   │  SQLite Backend     │         │  Supabase Backend   │             │   │
│  │   │  (Development)      │         │  (Production)       │             │   │
│  │   │                     │         │                     │             │   │
│  │   │  proposals.db       │         │  ┌───────────────┐  │             │   │
│  │   │                     │         │  │ UI Supabase   │  │             │   │
│  │   │                     │         │  │ (Auth/RBAC)   │  │             │   │
│  │   │                     │         │  └───────────────┘  │             │   │
│  │   │                     │         │  ┌───────────────┐  │             │   │
│  │   │                     │         │  │ Sales Supabase│  │             │   │
│  │   │                     │         │  │ (Business)    │  │             │   │
│  │   │                     │         │  └───────────────┘  │             │   │
│  │   └─────────────────────┘         └─────────────────────┘             │   │
│  │                                                                        │   │
│  └────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Location | Responsibility |
|-----------|----------|----------------|
| **unified-ui** | `src/unified-ui/server.js` | Auth gateway, RBAC resolution, SPA serving, request proxying |
| **proposal-bot** | `api/server.py` | Business logic, AI orchestration, document generation |
| **API Routers** | `api/routers/*.py` | HTTP endpoint handling, request validation |
| **Core Layer** | `core/*.py` | Business logic, LLM orchestration, tool execution |
| **Generators** | `generators/*.py` | Document and image generation |
| **Integrations** | `integrations/` | External service abstractions |
| **Database** | `db/` | Data persistence, caching |

---

## Service Architecture

### unified-ui Service

**File:** `src/unified-ui/server.js`

```
┌─────────────────────────────────────────────────────────────────────┐
│                        unified-ui:3005                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                      MIDDLEWARE STACK                           │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │  1. Helmet.js (Security Headers)                               │ │
│  │     • Content-Security-Policy                                  │ │
│  │     • X-Frame-Options                                          │ │
│  │     • X-Content-Type-Options                                   │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │  2. CORS                                                        │ │
│  │     • Origin validation (localhost, Render URLs)               │ │
│  │     • Credentials support                                      │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │  3. Rate Limiting                                               │ │
│  │     • 10 requests/minute on auth endpoints                     │ │
│  │     • In-memory store                                          │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │  4. Body Parser                                                 │ │
│  │     • JSON parsing                                             │ │
│  │     • URL-encoded parsing                                      │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                       ROUTE HANDLERS                            │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │                                                                 │ │
│  │  /api/base/*          → Direct handling (auth, config)         │ │
│  │  /api/sales/*         → Proxy to proposal-bot                  │ │
│  │  /api/admin/*         → Proxy to proposal-bot (admin check)    │ │
│  │  /api/modules/*       → Direct handling                        │ │
│  │  /*                   → Static file serving (SPA)              │ │
│  │                                                                 │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    AUTH MIDDLEWARE                              │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │  1. Extract JWT from Authorization header                      │ │
│  │  2. Validate token with Supabase Auth                          │ │
│  │  3. Fetch user profile from users table                        │ │
│  │  4. Resolve RBAC (profile → permissions, teams, companies)     │ │
│  │  5. Inject trusted headers for backend                         │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**Key Functions:**

| Function | Purpose |
|----------|---------|
| `authenticateRequest()` | Validates JWT, returns user object |
| `resolveUserRBAC()` | Fetches profile, permissions, teams, companies |
| `proxyToService()` | Forwards request with trusted headers |
| `injectTrustedHeaders()` | Adds X-Trusted-* headers to request |

### proposal-bot Service

**File:** `api/server.py`

```
┌─────────────────────────────────────────────────────────────────────┐
│                       proposal-bot:8000                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    FASTAPI APPLICATION                          │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │                                                                 │ │
│  │  Middleware:                                                    │ │
│  │  • SecurityHeadersMiddleware (api/middleware/security_headers)  │ │
│  │  • CORSMiddleware (FastAPI built-in)                           │ │
│  │  • Request logging middleware                                  │ │
│  │                                                                 │ │
│  │  Lifespan Events:                                              │ │
│  │  • startup: Initialize DB, check LibreOffice, load fonts      │ │
│  │  • shutdown: Cleanup resources                                 │ │
│  │                                                                 │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                      ROUTER REGISTRY                            │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │                                                                 │ │
│  │  api/routers/chat.py       → /api/chat/*                       │ │
│  │  api/routers/proposals.py  → /api/proposals/*                  │ │
│  │  api/routers/mockups.py    → /api/mockup/*                     │ │
│  │  api/routers/files.py      → /api/files/*                      │ │
│  │  api/routers/slack.py      → /slack/*                          │ │
│  │  api/routers/admin.py      → /api/admin/*                      │ │
│  │  api/routers/costs.py      → /costs/*                          │ │
│  │  api/routers/modules.py    → /api/modules/*                    │ │
│  │  api/routers/health.py     → /health/*, /metrics               │ │
│  │                                                                 │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                   BACKGROUND TASKS                              │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │                                                                 │ │
│  │  • Periodic cache cleanup (every 5 minutes)                    │ │
│  │  • Session expiration                                          │ │
│  │  • Memory statistics logging                                   │ │
│  │                                                                 │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Request Flow

### Web Request Flow

```
┌──────────────┐
│   Browser    │
└──────┬───────┘
       │ 1. POST /api/chat/message
       │    Authorization: Bearer <jwt>
       │    Body: { message: "...", file_ids: [...] }
       ▼
┌──────────────────────────────────────────────────────────────────┐
│                        unified-ui:3005                            │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  2. Extract JWT from Authorization header                         │
│     ↓                                                             │
│  3. Validate JWT with Supabase Auth                               │
│     POST https://xxx.supabase.co/auth/v1/user                     │
│     ↓                                                             │
│  4. Fetch user profile                                            │
│     SELECT * FROM users WHERE id = <user_id>                      │
│     ↓                                                             │
│  5. Resolve RBAC                                                  │
│     • Get profile: user_profiles → profiles                       │
│     • Get permissions: profile_permissions + permission_sets      │
│     • Get teams: team_members → teams                             │
│     • Get companies: user_companies → companies                   │
│     ↓                                                             │
│  6. Inject trusted headers                                        │
│     X-Trusted-User-Id: <user_id>                                  │
│     X-Trusted-User-Email: <email>                                 │
│     X-Trusted-User-Name: <name>                                   │
│     X-Trusted-User-Profile: <profile_name>                        │
│     X-Trusted-User-Permissions: ["perm1", "perm2", ...]          │
│     X-Trusted-User-Companies: ["company1", "company2", ...]      │
│     X-Proxy-Secret: <shared_secret>                               │
│     ↓                                                             │
│  7. Proxy request to proposal-bot                                 │
│                                                                   │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                       proposal-bot:8000                           │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  8. Verify X-Proxy-Secret                                         │
│     ↓                                                             │
│  9. Extract user context from trusted headers                     │
│     (api/auth.py: get_current_user)                               │
│     ↓                                                             │
│  10. Check permissions                                            │
│      (api/auth.py: require_permission("sales:chat:use"))          │
│      ↓                                                            │
│  11. Route to handler                                             │
│      (api/routers/chat.py: send_message)                          │
│      ↓                                                            │
│  12. Process request                                              │
│      (core/chat_api.py: process_chat_message)                     │
│      ↓                                                            │
│  13. Execute LLM loop                                             │
│      (core/llm.py: main_llm_loop)                                 │
│      ↓                                                            │
│  14. Return response                                              │
│                                                                   │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────┐
│   Browser    │ ← 15. JSON Response
└──────────────┘
```

### Slack Request Flow

```
┌──────────────┐
│    Slack     │
└──────┬───────┘
       │ 1. POST /slack/events
       │    X-Slack-Signature: v0=...
       │    X-Slack-Request-Timestamp: ...
       │    Body: { event: { type: "message", user: "U...", text: "..." } }
       ▼
┌──────────────────────────────────────────────────────────────────┐
│                       proposal-bot:8000                           │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  2. Verify Slack signature                                        │
│     (api/routers/slack.py: verify_slack_signature)                │
│     ↓                                                             │
│  3. Handle event type                                             │
│     • url_verification → Return challenge                         │
│     • event_callback → Process event                              │
│     ↓                                                             │
│  4. Look up user                                                  │
│     • Get Slack user ID from event                                │
│     • Map to internal user (db lookup or create)                  │
│     ↓                                                             │
│  5. Get/Create SlackAdapter                                       │
│     (integrations/channels/adapters/slack.py)                     │
│     ↓                                                             │
│  6. Execute LLM loop with SlackAdapter                            │
│     (core/llm.py: main_llm_loop)                                  │
│     ↓                                                             │
│  7. SlackAdapter sends response to Slack                          │
│     POST https://slack.com/api/chat.postMessage                   │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
       │
       │ 8. Return 200 OK (acknowledge receipt)
       ▼
┌──────────────┐
│    Slack     │
└──────────────┘
```

---

## Authentication Architecture

### JWT Token Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                     AUTHENTICATION FLOW                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐   │
│  │   Browser   │     │  Supabase Auth  │     │  Microsoft SSO  │   │
│  └──────┬──────┘     └────────┬────────┘     └────────┬────────┘   │
│         │                     │                       │             │
│         │ 1. Click "Sign in   │                       │             │
│         │    with Microsoft"  │                       │             │
│         ├────────────────────►│                       │             │
│         │                     │                       │             │
│         │ 2. Redirect to      │                       │             │
│         │    Microsoft        │                       │             │
│         │◄────────────────────┤                       │             │
│         │                     │                       │             │
│         │ 3. User authenticates with Microsoft        │             │
│         ├─────────────────────────────────────────────►│             │
│         │                                             │             │
│         │ 4. Microsoft redirects back with auth code  │             │
│         │◄─────────────────────────────────────────────┤             │
│         │                     │                       │             │
│         │ 5. Exchange code    │                       │             │
│         │    for token        │                       │             │
│         ├────────────────────►│                       │             │
│         │                     │                       │             │
│         │ 6. Return JWT       │                       │             │
│         │◄────────────────────┤                       │             │
│         │                     │                       │             │
│         │ 7. Store token in   │                       │             │
│         │    localStorage     │                       │             │
│         │                     │                       │             │
└─────────┴─────────────────────┴───────────────────────┴─────────────┘
```

### Token Validation

**File:** `src/unified-ui/server.js`

```javascript
// Token validation flow
async function authenticateRequest(req) {
  // 1. Extract token from header
  const authHeader = req.headers.authorization;
  const token = authHeader?.replace('Bearer ', '');

  // 2. Validate with Supabase
  const { data: { user }, error } = await supabase.auth.getUser(token);

  if (error || !user) {
    throw new UnauthorizedError('Invalid token');
  }

  // 3. Fetch user profile from database
  const { data: profile } = await supabase
    .from('users')
    .select('*, user_profiles(profiles(*))')
    .eq('id', user.id)
    .single();

  return { user, profile };
}
```

### Trusted Header System

**Why Trusted Headers?**

The proposal-bot doesn't validate JWT tokens directly. Instead, it trusts headers injected by unified-ui after validation. This provides:

1. **Single point of authentication**: Only unified-ui needs Supabase Auth credentials
2. **Simplified backend**: No JWT validation logic in Python
3. **Flexibility**: Can swap auth providers without changing backend
4. **Performance**: No repeated token validation on internal calls

**Security:**

- `X-Proxy-Secret` header must match configured secret
- Direct calls to proposal-bot without correct secret are rejected
- Headers are stripped from external requests before proxying

**Header Injection:**

```javascript
// src/unified-ui/server.js
function injectTrustedHeaders(req, user, rbac) {
  return {
    'X-Trusted-User-Id': user.id,
    'X-Trusted-User-Email': user.email,
    'X-Trusted-User-Name': user.name,
    'X-Trusted-User-Profile': rbac.profile.name,
    'X-Trusted-User-Permissions': JSON.stringify(rbac.permissions),
    'X-Trusted-User-Companies': JSON.stringify(rbac.companies.map(c => c.id)),
    'X-Proxy-Secret': process.env.PROXY_SECRET
  };
}
```

**Header Reading:**

```python
# api/auth.py
def get_current_user(request: Request) -> UserContext:
    # Verify proxy secret
    if request.headers.get('X-Proxy-Secret') != settings.PROXY_SECRET:
        raise HTTPException(401, "Invalid proxy secret")

    return UserContext(
        id=request.headers.get('X-Trusted-User-Id'),
        email=request.headers.get('X-Trusted-User-Email'),
        name=request.headers.get('X-Trusted-User-Name'),
        profile=request.headers.get('X-Trusted-User-Profile'),
        permissions=json.loads(request.headers.get('X-Trusted-User-Permissions', '[]')),
        companies=json.loads(request.headers.get('X-Trusted-User-Companies', '[]'))
    )
```

---

## RBAC Architecture

### 4-Level Permission Model

```
┌─────────────────────────────────────────────────────────────────────┐
│                        RBAC HIERARCHY                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Level 1: BASE PROFILES                                              │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  User → Profile → Profile Permissions                          │ │
│  │                                                                 │ │
│  │  ┌─────────┐    ┌──────────────┐    ┌────────────────────────┐ │ │
│  │  │  User   │───►│ sales_user   │───►│ sales:proposals:create │ │ │
│  │  │  John   │    │              │    │ sales:proposals:read   │ │ │
│  │  └─────────┘    │              │    │ sales:chat:use         │ │ │
│  │                 └──────────────┘    │ sales:mockups:read     │ │ │
│  │                                     │ sales:mockups:create   │ │ │
│  │                                     └────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                              +                                       │
│  Level 2: PERMISSION SETS (Additive)                                 │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  User → Permission Set → Permissions                           │ │
│  │                                                                 │ │
│  │  ┌─────────┐    ┌──────────────┐    ┌────────────────────────┐ │ │
│  │  │  User   │───►│ mockup_admin │───►│ sales:mockups:setup    │ │ │
│  │  │  John   │    │ (temporary)  │    │ sales:mockups:delete   │ │ │
│  │  └─────────┘    │ expires: ... │    └────────────────────────┘ │ │
│  │                 └──────────────┘                                │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                              +                                       │
│  Level 3: TEAM HIERARCHY                                             │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  Team Structure + Manager Access                                │ │
│  │                                                                 │ │
│  │  ┌──────────────────────────────────────────┐                  │ │
│  │  │              Sales Team                   │                  │ │
│  │  │  ┌────────────────┐  ┌────────────────┐  │                  │ │
│  │  │  │ Sales North    │  │ Sales South    │  │                  │ │
│  │  │  │                │  │                │  │                  │ │
│  │  │  │ Leader: Alice  │  │ Leader: Bob    │  │                  │ │
│  │  │  │ Members:       │  │ Members:       │  │                  │ │
│  │  │  │ - John         │  │ - Jane         │  │                  │ │
│  │  │  │ - Mike         │  │ - Tom          │  │                  │ │
│  │  │  └────────────────┘  └────────────────┘  │                  │ │
│  │  └──────────────────────────────────────────┘                  │ │
│  │                                                                 │ │
│  │  Access Rules:                                                  │ │
│  │  • Alice sees John's and Mike's proposals                      │ │
│  │  • Bob sees Jane's and Tom's proposals                         │ │
│  │  • Sales Manager sees all team proposals                       │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                              +                                       │
│  Level 4: RECORD SHARING                                             │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  Individual Record Access                                       │ │
│  │                                                                 │ │
│  │  ┌─────────────────────────────────────────────────────────┐   │ │
│  │  │  Record: Proposal #123                                   │   │ │
│  │  │  Owner: John                                             │   │ │
│  │  │                                                          │   │ │
│  │  │  Shared with:                                            │   │ │
│  │  │  • Sarah (read)                                          │   │ │
│  │  │  • Finance Team (read)                                   │   │ │
│  │  │  • Client Portal (read) - expires 2024-02-01             │   │ │
│  │  └─────────────────────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Permission Format

```
{module}:{resource}:{action}

Examples:
├── sales:proposals:create     # Create proposals
├── sales:proposals:read       # Read proposals
├── sales:proposals:*          # All proposal actions
├── sales:*:*                  # All sales module actions
├── core:system:admin          # System administration
└── *:*:*                      # Super admin (all permissions)
```

### Permission Checking

**File:** `api/auth.py`

```python
def check_permission(user: UserContext, required: str) -> bool:
    """
    Check if user has the required permission.
    Supports wildcards: sales:*:* matches sales:proposals:create
    """
    required_parts = required.split(':')

    for permission in user.permissions:
        perm_parts = permission.split(':')

        if len(perm_parts) != 3:
            continue

        match = True
        for i, (perm_part, req_part) in enumerate(zip(perm_parts, required_parts)):
            if perm_part != '*' and perm_part != req_part:
                match = False
                break

        if match:
            return True

    return False


def require_permission(permission: str):
    """Dependency that checks permission before allowing access."""
    def checker(user: UserContext = Depends(get_current_user)):
        if not check_permission(user, permission):
            raise HTTPException(403, f"Permission denied: {permission}")
        return user
    return Depends(checker)
```

### Database Tables

```sql
-- Level 1: Profiles
CREATE TABLE profiles (
    id UUID PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,       -- e.g., 'sales_user'
    display_name VARCHAR(100),               -- e.g., 'Sales User'
    description TEXT,
    is_system BOOLEAN DEFAULT FALSE          -- System profiles can't be deleted
);

CREATE TABLE profile_permissions (
    id UUID PRIMARY KEY,
    profile_id UUID REFERENCES profiles(id),
    permission VARCHAR(100) NOT NULL         -- e.g., 'sales:proposals:create'
);

CREATE TABLE user_profiles (
    user_id UUID REFERENCES users(id),
    profile_id UUID REFERENCES profiles(id),
    PRIMARY KEY (user_id, profile_id)
);

-- Level 2: Permission Sets
CREATE TABLE permission_sets (
    id UUID PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE permission_set_permissions (
    id UUID PRIMARY KEY,
    permission_set_id UUID REFERENCES permission_sets(id),
    permission VARCHAR(100) NOT NULL
);

CREATE TABLE user_permission_sets (
    user_id UUID REFERENCES users(id),
    permission_set_id UUID REFERENCES permission_sets(id),
    granted_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,                    -- NULL = never expires
    granted_by UUID REFERENCES users(id),
    PRIMARY KEY (user_id, permission_set_id)
);

-- Level 3: Teams
CREATE TABLE teams (
    id UUID PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    parent_team_id UUID REFERENCES teams(id) -- Hierarchy support
);

CREATE TABLE team_members (
    id UUID PRIMARY KEY,
    team_id UUID REFERENCES teams(id),
    user_id UUID REFERENCES users(id),
    role VARCHAR(20) DEFAULT 'member'        -- 'leader' or 'member'
);

-- Level 4: Record Sharing
CREATE TABLE record_shares (
    id UUID PRIMARY KEY,
    record_type VARCHAR(50) NOT NULL,        -- e.g., 'proposal'
    record_id UUID NOT NULL,
    shared_with_user_id UUID REFERENCES users(id),
    shared_with_team_id UUID REFERENCES teams(id),
    access_level VARCHAR(20) DEFAULT 'read', -- 'read', 'read_write', 'full'
    expires_at TIMESTAMP,
    shared_by UUID REFERENCES users(id),
    shared_at TIMESTAMP DEFAULT NOW()
);
```

---

## Database Architecture

### Dual Supabase Strategy

```
┌─────────────────────────────────────────────────────────────────────┐
│                     DATABASE ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────┐   ┌─────────────────────────────┐  │
│  │     UI Supabase Project     │   │  Sales Bot Supabase Project │  │
│  │     (Auth & RBAC)           │   │  (Business Data)            │  │
│  ├─────────────────────────────┤   ├─────────────────────────────┤  │
│  │                             │   │                             │  │
│  │  Purpose:                   │   │  Purpose:                   │  │
│  │  • User authentication      │   │  • Business data storage    │  │
│  │  • RBAC data                │   │  • Multi-tenant isolation   │  │
│  │  • Session management       │   │  • Document metadata        │  │
│  │                             │   │                             │  │
│  │  Tables:                    │   │  Tables:                    │  │
│  │  • users                    │   │  • proposals_log            │  │
│  │  • profiles                 │   │  • proposal_locations       │  │
│  │  • profile_permissions      │   │  • booking_orders           │  │
│  │  • permission_sets          │   │  • bo_locations             │  │
│  │  • user_permission_sets     │   │  • bo_approval_workflows    │  │
│  │  • teams                    │   │  • ai_costs                 │  │
│  │  • team_members             │   │  • documents                │  │
│  │  • companies                │   │  • mockup_files             │  │
│  │  • user_companies           │   │                             │  │
│  │  • chat_sessions            │   │  Company Schemas:           │  │
│  │  • invite_tokens            │   │  • backlite_dubai.*         │  │
│  │  • modules                  │   │  • backlite_uk.*            │  │
│  │                             │   │  • (per-company tables)     │  │
│  │  Access:                    │   │                             │  │
│  │  • unified-ui (read/write)  │   │  Access:                    │  │
│  │  • proposal-bot (read)      │   │  • proposal-bot (read/write)│  │
│  │                             │   │                             │  │
│  └─────────────────────────────┘   └─────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Database Facade Pattern

**File:** `db/database.py`

```python
"""
Database facade that provides a unified interface regardless of backend.
Automatically selects SQLite (dev) or Supabase (prod) based on configuration.
"""

class Database:
    def __init__(self):
        if settings.DB_BACKEND == 'supabase':
            self._backend = SupabaseBackend()
        else:
            self._backend = SQLiteBackend()

    # Proposal operations
    def log_proposal(self, **kwargs):
        return self._backend.log_proposal(**kwargs)

    def get_proposals(self, user_id, **filters):
        return self._backend.get_proposals(user_id, **filters)

    # Location operations
    def get_locations(self, company_id):
        return self._backend.get_locations(company_id)

    def add_location(self, company_id, **data):
        return self._backend.add_location(company_id, **data)

    # Booking order operations
    def create_booking_order(self, **data):
        return self._backend.create_booking_order(**data)

    def update_bo_status(self, bo_id, status, **kwargs):
        return self._backend.update_bo_status(bo_id, status, **kwargs)

    # ... more operations


# Global singleton
db = Database()
```

### Multi-Tenant Company Schemas

**File:** `db/backends/supabase.py`

```python
class SupabaseBackend:
    def get_locations(self, company_id: str) -> list:
        """
        Get locations from company-specific schema.
        Each company has its own schema with identical table structure.
        """
        schema = self._get_company_schema(company_id)

        result = self.client.schema(schema).table('locations').select('*').execute()
        return result.data

    def _get_company_schema(self, company_id: str) -> str:
        """Map company ID to PostgreSQL schema name."""
        # Lookup from companies table or config
        schemas = {
            'company-uuid-1': 'backlite_dubai',
            'company-uuid-2': 'backlite_uk',
            # ...
        }
        return schemas.get(company_id, 'public')
```

### Company Schema Structure

```sql
-- Each company has its own schema with these tables:

CREATE SCHEMA backlite_dubai;

-- Locations available for advertising
CREATE TABLE backlite_dubai.locations (
    id UUID PRIMARY KEY,
    location_key VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    height DECIMAL(10,2),
    width DECIMAL(10,2),
    type VARCHAR(50),                        -- LED, Static, Digital
    series VARCHAR(100),                     -- Grouping
    address TEXT,
    latitude DECIMAL(10,8),
    longitude DECIMAL(11,8),
    is_active BOOLEAN DEFAULT TRUE
);

-- Location photos for mockups
CREATE TABLE backlite_dubai.location_photos (
    id UUID PRIMARY KEY,
    location_id UUID REFERENCES backlite_dubai.locations(id),
    photo_path TEXT NOT NULL,
    time_of_day VARCHAR(20),                 -- 'day', 'night'
    finish VARCHAR(20),                      -- 'gold', 'silver'
    uploaded_at TIMESTAMP DEFAULT NOW()
);

-- Billboard frame coordinates for mockup generation
CREATE TABLE backlite_dubai.mockup_frames (
    id UUID PRIMARY KEY,
    location_id UUID REFERENCES backlite_dubai.locations(id),
    photo_id UUID REFERENCES backlite_dubai.location_photos(id),
    frame_points JSONB NOT NULL,             -- [{x, y}, {x, y}, {x, y}, {x, y}]
    config JSONB,                            -- brightness, contrast, etc.
    created_by UUID,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Rate cards (pricing)
CREATE TABLE backlite_dubai.rate_cards (
    id UUID PRIMARY KEY,
    location_id UUID REFERENCES backlite_dubai.locations(id),
    duration_weeks INTEGER NOT NULL,
    net_rate DECIMAL(12,2) NOT NULL,
    upload_fee DECIMAL(10,2) DEFAULT 0,
    municipality_fee_percent DECIMAL(5,2) DEFAULT 0,
    valid_from DATE,
    valid_to DATE,
    currency VARCHAR(3) DEFAULT 'AED'
);

-- Location occupancy tracking
CREATE TABLE backlite_dubai.location_occupations (
    id UUID PRIMARY KEY,
    location_id UUID REFERENCES backlite_dubai.locations(id),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    client_name VARCHAR(200),
    booking_order_id UUID,
    sov DECIMAL(5,2),                        -- Share of voice percentage
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## LLM Integration Architecture

### Provider Abstraction

**Directory:** `integrations/llm/`

```
┌─────────────────────────────────────────────────────────────────────┐
│                     LLM INTEGRATION LAYER                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                     LLMClient (client.py)                        ││
│  │  ─────────────────────────────────────────────────────────────  ││
│  │  • Unified interface for all LLM operations                     ││
│  │  • Provider selection based on config                           ││
│  │  • Cost tracking integration                                    ││
│  └───────────────────────────┬─────────────────────────────────────┘│
│                              │                                       │
│              ┌───────────────┴───────────────┐                      │
│              ▼                               ▼                      │
│  ┌─────────────────────────┐   ┌─────────────────────────┐         │
│  │   OpenAI Provider       │   │   Google Provider       │         │
│  │   (providers/openai.py) │   │   (providers/google.py) │         │
│  ├─────────────────────────┤   ├─────────────────────────┤         │
│  │                         │   │                         │         │
│  │  Models:                │   │  Models:                │         │
│  │  • gpt-4-turbo-preview  │   │  • gemini-pro           │         │
│  │  • gpt-4o               │   │  • gemini-1.5-pro       │         │
│  │                         │   │                         │         │
│  │  Features:              │   │  Features:              │         │
│  │  • Chat completion      │   │  • Chat completion      │         │
│  │  • Tool calling         │   │  • Tool calling         │         │
│  │  • Streaming            │   │  • Streaming            │         │
│  │  • DALL-E 3 images      │   │  • Imagen2 images       │         │
│  │                         │   │                         │         │
│  └─────────────────────────┘   └─────────────────────────┘         │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                   Cost Tracker (cost_tracker.py)                 ││
│  │  ─────────────────────────────────────────────────────────────  ││
│  │  • Tracks tokens (input/output)                                 ││
│  │  • Calculates cost per model                                    ││
│  │  • Persists to ai_costs table                                   ││
│  │  • Aggregation by user/workflow/date                            ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                     Prompts (prompts/)                           ││
│  │  ─────────────────────────────────────────────────────────────  ││
│  │  • chat.py          - Main chat system prompt                   ││
│  │  • mockup.py        - Mockup generation instructions            ││
│  │  • bo_parsing.py    - Booking order parsing                     ││
│  │  • bo_editing.py    - Booking order editing                     ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Main LLM Loop

**File:** `core/llm.py`

```
┌─────────────────────────────────────────────────────────────────────┐
│                       main_llm_loop()                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Input:                                                              │
│  ├── message: str              # User's message                      │
│  ├── channel: ChannelAdapter   # Slack or Web adapter                │
│  ├── user_context: UserContext # User info, permissions, companies  │
│  └── file_ids: list[str]       # Attached file IDs                   │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ 1. LOAD CONTEXT                                                  ││
│  │    • Get/create session for user                                 ││
│  │    • Load conversation history from cache/db                     ││
│  │    • Load attached files from storage                            ││
│  │    • Build system prompt with user context                       ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ 2. BUILD MESSAGES                                                ││
│  │    messages = [                                                  ││
│  │      { role: "system", content: system_prompt },                 ││
│  │      ...conversation_history,                                    ││
│  │      { role: "user", content: message, files: [...] }           ││
│  │    ]                                                             ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ 3. AGENTIC LOOP                                                  ││
│  │    while True:                                                   ││
│  │      response = llm.chat(messages, tools=available_tools)        ││
│  │                                                                  ││
│  │      if response.has_tool_calls:                                 ││
│  │        for tool_call in response.tool_calls:                     ││
│  │          result = execute_tool(tool_call)                        ││
│  │          messages.append(tool_result)                            ││
│  │      else:                                                       ││
│  │        break  # No more tools, final response                    ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ 4. EXECUTE TOOLS                                                 ││
│  │                                                                  ││
│  │    ┌──────────────────────────────────────────────────────────┐ ││
│  │    │ get_separate_proposals → core/proposals.py               │ ││
│  │    │ get_combined_proposal  → core/proposals.py               │ ││
│  │    │ generate_mockup        → generators/mockup.py            │ ││
│  │    │ get_booking_orders     → db.get_booking_orders()         │ ││
│  │    │ submit_booking_order   → workflows/bo_approval.py        │ ││
│  │    │ list_locations         → db.get_locations()              │ ││
│  │    │ add_location           → db.add_location()               │ ││
│  │    │ delete_location        → db.delete_location()            │ ││
│  │    └──────────────────────────────────────────────────────────┘ ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ 5. SEND RESPONSE                                                 ││
│  │    • Stream text to channel                                      ││
│  │    • Upload generated files                                      ││
│  │    • Save conversation to session                                ││
│  │    • Track costs                                                 ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  Output:                                                             │
│  ├── response_text: str        # LLM's response                      │
│  ├── files: list[File]         # Generated files                     │
│  └── session_id: str           # Session identifier                  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Tool Definitions

**File:** `core/tools.py`

```python
# Tool schema format (OpenAI function calling format)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_separate_proposals",
            "description": "Generate individual proposals for each location",
            "parameters": {
                "type": "object",
                "properties": {
                    "client_name": {
                        "type": "string",
                        "description": "Name of the client"
                    },
                    "locations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "location_key": {"type": "string"},
                                "start_date": {"type": "string", "format": "date"},
                                "duration_weeks": {"type": "integer"}
                            }
                        }
                    },
                    "currency": {
                        "type": "string",
                        "enum": ["AED", "USD", "GBP", "EUR"]
                    }
                },
                "required": ["client_name", "locations"]
            }
        }
    },
    # ... more tools
]

def get_base_tools() -> list:
    """Return tools available to all users."""
    return [t for t in TOOLS if t["function"]["name"] not in ADMIN_ONLY_TOOLS]

def get_admin_tools() -> list:
    """Return admin-only tools (add_location, delete_location)."""
    return [t for t in TOOLS if t["function"]["name"] in ADMIN_ONLY_TOOLS]
```

---

## File Storage Architecture

### Storage Provider Abstraction

**Directory:** `integrations/storage/`

```
┌─────────────────────────────────────────────────────────────────────┐
│                    STORAGE ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                   StorageClient (client.py)                      ││
│  │  ─────────────────────────────────────────────────────────────  ││
│  │  • Unified interface for file operations                        ││
│  │  • Automatic provider selection                                 ││
│  │  • Signed URL generation                                        ││
│  └───────────────────────────┬─────────────────────────────────────┘│
│                              │                                       │
│              ┌───────────────┴───────────────┐                      │
│              ▼                               ▼                      │
│  ┌─────────────────────────┐   ┌─────────────────────────┐         │
│  │   Local Provider        │   │   Supabase Provider     │         │
│  │   (providers/local.py)  │   │   (providers/supabase.py)│        │
│  ├─────────────────────────┤   ├─────────────────────────┤         │
│  │                         │   │                         │         │
│  │  Storage:               │   │  Storage:               │         │
│  │  • ./uploads/           │   │  • Supabase Storage     │         │
│  │  • /data/               │   │  • Multiple buckets     │         │
│  │                         │   │                         │         │
│  │  URLs:                  │   │  URLs:                  │         │
│  │  • Direct file paths    │   │  • Signed URLs          │         │
│  │  • /api/files/...       │   │  • Automatic expiry     │         │
│  │                         │   │                         │         │
│  └─────────────────────────┘   └─────────────────────────┘         │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### File Upload Flow

```
┌──────────────┐
│   Browser    │
└──────┬───────┘
       │ POST /api/files/upload
       │ Content-Type: multipart/form-data
       │ Body: file=<binary>
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      api/routers/files.py                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. Validate file                                                    │
│     • Check extension (jpg, png, pdf, docx, etc.)                   │
│     • Check size (max 200MB)                                        │
│     • Check MIME type                                               │
│     ↓                                                               │
│  2. Generate file ID                                                 │
│     file_id = uuid4()                                               │
│     ↓                                                               │
│  3. Upload to storage                                                │
│     storage.upload(file_id, filename, content)                      │
│     ↓                                                               │
│  4. Save metadata to database                                        │
│     db.save_document(file_id, filename, user_id, ...)               │
│     ↓                                                               │
│  5. Return file info                                                 │
│     {                                                               │
│       "file_id": "uuid",                                            │
│       "filename": "creative.jpg",                                   │
│       "url": "/api/files/uuid/creative.jpg",                       │
│       "size": 1048576,                                              │
│       "mime_type": "image/jpeg"                                     │
│     }                                                               │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Bucket Organization (Supabase)

```
Supabase Storage Buckets:
├── uploads/                    # User-uploaded files
│   ├── {user_id}/
│   │   ├── {file_id}/{filename}
│   │   └── ...
│   └── ...
│
├── proposals/                  # Generated proposal documents
│   ├── {proposal_id}/
│   │   ├── Proposal.pdf
│   │   ├── Proposal.pptx
│   │   └── Combined.pdf
│   └── ...
│
├── mockups/                    # Generated mockup images
│   ├── {mockup_id}/
│   │   └── mockup.jpg
│   └── ...
│
└── location-photos/            # Billboard photos for mockups
    ├── {location_key}/
    │   ├── day_gold.jpg
    │   ├── day_silver.jpg
    │   ├── night_gold.jpg
    │   └── night_silver.jpg
    └── ...
```

---

## Channel Abstraction

### Channel Adapter Pattern

**Directory:** `integrations/channels/`

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CHANNEL ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                   ChannelAdapter (base.py)                       ││
│  │  ─────────────────────────────────────────────────────────────  ││
│  │  Abstract base class defining channel operations:                ││
│  │                                                                  ││
│  │  • send_message(text)           - Send text message              ││
│  │  • send_file(file_path, name)   - Send file attachment           ││
│  │  • update_message(id, text)     - Update existing message        ││
│  │  • add_reaction(message_id)     - Add emoji reaction             ││
│  │  • get_user_id()                - Get user identifier            ││
│  │  • get_channel_id()             - Get channel/conversation ID    ││
│  └───────────────────────────┬─────────────────────────────────────┘│
│                              │                                       │
│              ┌───────────────┴───────────────┐                      │
│              ▼                               ▼                      │
│  ┌─────────────────────────┐   ┌─────────────────────────┐         │
│  │     SlackAdapter        │   │      WebAdapter         │         │
│  │  (adapters/slack.py)    │   │   (adapters/web.py)     │         │
│  ├─────────────────────────┤   ├─────────────────────────┤         │
│  │                         │   │                         │         │
│  │  send_message:          │   │  send_message:          │         │
│  │  → Slack API            │   │  → Accumulate in buffer │         │
│  │    chat.postMessage     │   │                         │         │
│  │                         │   │  send_file:             │         │
│  │  send_file:             │   │  → Upload to storage    │         │
│  │  → Slack API            │   │  → Return URL           │         │
│  │    files.upload         │   │                         │         │
│  │                         │   │  Streaming:             │         │
│  │  Buttons:               │   │  → SSE events           │         │
│  │  → Interactive messages │   │                         │         │
│  │                         │   │                         │         │
│  └─────────────────────────┘   └─────────────────────────┘         │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Channel Routing

**File:** `integrations/channels/router.py`

```python
class ChannelRouter:
    """Routes messages to appropriate channel adapter."""

    _adapters: dict[str, ChannelAdapter] = {}

    @classmethod
    def register(cls, user_id: str, adapter: ChannelAdapter):
        """Register an adapter for a user's session."""
        cls._adapters[user_id] = adapter

    @classmethod
    def get(cls, user_id: str) -> ChannelAdapter | None:
        """Get the active adapter for a user."""
        return cls._adapters.get(user_id)

    @classmethod
    def unregister(cls, user_id: str):
        """Remove adapter when session ends."""
        cls._adapters.pop(user_id, None)
```

### Message Formatting

**File:** `integrations/channels/formatting.py`

```python
def format_proposal_message(proposal: Proposal, channel: str) -> str:
    """Format proposal details for specific channel."""

    if channel == 'slack':
        # Slack Block Kit format
        return {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Proposal Generated*\nClient: {proposal.client_name}"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Amount:*\n{proposal.total}"},
                        {"type": "mrkdwn", "text": f"*Locations:*\n{len(proposal.locations)}"}
                    ]
                }
            ]
        }
    else:
        # Plain text/HTML for web
        return f"""
        ## Proposal Generated
        **Client:** {proposal.client_name}
        **Total:** {proposal.total}
        **Locations:** {len(proposal.locations)}
        """
```

---

## Generator Pipeline

### Proposal Generation Pipeline

**Files:** `core/proposals.py`, `generators/pptx.py`, `generators/pdf.py`

```
┌─────────────────────────────────────────────────────────────────────┐
│                   PROPOSAL GENERATION PIPELINE                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Input:                                                              │
│  {                                                                   │
│    client_name: "Acme Corp",                                        │
│    locations: [                                                      │
│      { location_key: "dubai_marina", start_date: "2024-02-01",      │
│        duration_weeks: 4 }                                          │
│    ],                                                               │
│    currency: "AED"                                                  │
│  }                                                                   │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ 1. FETCH DATA (core/proposals.py)                                ││
│  │    • Get location details from db                                ││
│  │    • Get rate cards for each location                            ││
│  │    • Get location templates (PPTX files)                         ││
│  │    • Apply currency conversion if needed                         ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ 2. CALCULATE FINANCIALS                                          ││
│  │    • Net rate for duration                                       ││
│  │    • Municipality fee (percentage of net)                        ││
│  │    • Upload/production fee                                       ││
│  │    • VAT (5% of subtotal)                                        ││
│  │    • Grand total                                                 ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ 3. GENERATE PPTX (generators/pptx.py)                            ││
│  │    For each location:                                            ││
│  │    ├── Load template PPTX from data/templates/                   ││
│  │    ├── Create financial slide                                    ││
│  │    │   ├── Duration options table (1w, 2w, 4w, 8w, etc.)        ││
│  │    │   ├── Rate per duration                                     ││
│  │    │   ├── VAT calculation                                       ││
│  │    │   └── Total amounts                                         ││
│  │    ├── Apply text placeholders                                   ││
│  │    │   ├── {CLIENT_NAME}                                         ││
│  │    │   ├── {START_DATE}                                          ││
│  │    │   ├── {END_DATE}                                            ││
│  │    │   └── {LOCATION_NAME}                                       ││
│  │    └── Save to temp file                                         ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ 4. CONVERT TO PDF (generators/pdf.py)                            ││
│  │    • Use LibreOffice headless mode                               ││
│  │    • Semaphore limits concurrent conversions (max 3)             ││
│  │    • Convert each PPTX to PDF                                    ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ 5. MERGE PDFs                                                    ││
│  │    • Combine all location PDFs                                   ││
│  │    • Create single combined document                             ││
│  │    • Maintain page order                                         ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ 6. UPLOAD & LOG                                                  ││
│  │    • Upload to storage (local/Supabase)                          ││
│  │    • Log to proposals_log table                                  ││
│  │    • Return file URLs                                            ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  Output:                                                             │
│  {                                                                   │
│    proposal_id: "uuid",                                             │
│    files: [                                                         │
│      { name: "Proposal_Location1.pdf", url: "..." },                │
│      { name: "Proposal_Combined.pdf", url: "..." }                  │
│    ]                                                                │
│  }                                                                   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Mockup Generation Pipeline

**Files:** `generators/mockup.py`, `generators/effects/`

```
┌─────────────────────────────────────────────────────────────────────┐
│                    MOCKUP GENERATION PIPELINE                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Input:                                                              │
│  {                                                                   │
│    location_key: "dubai_marina",                                    │
│    creative_file_id: "uuid",                                        │
│    time_of_day: "day",                                              │
│    finish: "gold"                                                   │
│  }                                                                   │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ 1. LOAD RESOURCES                                                ││
│  │    • Load location photo (day/night, gold/silver)                ││
│  │    • Load creative image from storage                            ││
│  │    • Load frame coordinates from mockup_frames table             ││
│  │    • Load effect config (brightness, contrast, etc.)             ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ 2. PERSPECTIVE TRANSFORM (effects/compositor.py)                 ││
│  │    • Define source points (creative corners)                     ││
│  │    • Define destination points (frame coordinates)               ││
│  │    • Calculate perspective matrix                                ││
│  │    • Warp creative to match billboard perspective                ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ 3. APPLY EFFECTS                                                 ││
│  │                                                                  ││
│  │    ┌─────────────────────────────────────────────────────────┐  ││
│  │    │ effects/color.py                                         │  ││
│  │    │ • Brightness adjustment                                  │  ││
│  │    │ • Contrast adjustment                                    │  ││
│  │    │ • Saturation adjustment                                  │  ││
│  │    │ • Color temperature                                      │  ││
│  │    └─────────────────────────────────────────────────────────┘  ││
│  │                              │                                   ││
│  │                              ▼                                   ││
│  │    ┌─────────────────────────────────────────────────────────┐  ││
│  │    │ effects/depth.py                                         │  ││
│  │    │ • Depth-of-field blur (optional)                         │  ││
│  │    │ • Distance simulation                                    │  ││
│  │    └─────────────────────────────────────────────────────────┘  ││
│  │                              │                                   ││
│  │                              ▼                                   ││
│  │    ┌─────────────────────────────────────────────────────────┐  ││
│  │    │ effects/edge.py                                          │  ││
│  │    │ • Edge blending                                          │  ││
│  │    │ • Feathering at boundaries                               │  ││
│  │    └─────────────────────────────────────────────────────────┘  ││
│  │                                                                  ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ 4. COMPOSITE                                                     ││
│  │    • Layer transformed creative onto location photo              ││
│  │    • Apply alpha blending                                        ││
│  │    • Handle transparency                                         ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ 5. SAVE & CLEANUP                                                ││
│  │    • Encode as JPEG                                              ││
│  │    • Upload to storage                                           ││
│  │    • Log to mockup_usage table                                   ││
│  │    • Clear memory (aggressive GC)                                ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  Output:                                                             │
│  {                                                                   │
│    mockup_id: "uuid",                                               │
│    url: "/api/files/uuid/mockup.jpg"                                │
│  }                                                                   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Caching Architecture

### In-Memory Caching

**File:** `db/cache.py`

```
┌─────────────────────────────────────────────────────────────────────┐
│                      CACHING ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                    In-Memory Cache                               ││
│  │                    (db/cache.py)                                 ││
│  ├─────────────────────────────────────────────────────────────────┤│
│  │                                                                  ││
│  │  user_history: dict[str, ChatHistory]                           ││
│  │  ├── Key: user_id                                               ││
│  │  ├── Value: { messages: [...], created_at, last_accessed }      ││
│  │  └── TTL: 1 hour                                                ││
│  │                                                                  ││
│  │  pending_location_additions: dict[str, LocationDraft]           ││
│  │  ├── Key: user_id                                               ││
│  │  ├── Value: { location_data, created_at }                       ││
│  │  └── TTL: 10 minutes                                            ││
│  │                                                                  ││
│  │  mockup_history: dict[str, MockupResult]                        ││
│  │  ├── Key: composite_key (location + creative hash)              ││
│  │  ├── Value: { url, created_at }                                 ││
│  │  └── TTL: 30 minutes                                            ││
│  │                                                                  ││
│  │  pending_booking_orders: dict[str, BODraft]                     ││
│  │  ├── Key: user_id                                               ││
│  │  ├── Value: { bo_data, created_at }                             ││
│  │  └── TTL: 30 minutes                                            ││
│  │                                                                  ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                   Periodic Cleanup                               ││
│  │                   (runs every 5 minutes)                         ││
│  ├─────────────────────────────────────────────────────────────────┤│
│  │                                                                  ││
│  │  async def cleanup_caches():                                     ││
│  │      now = datetime.now()                                        ││
│  │                                                                  ││
│  │      # Remove expired entries                                    ││
│  │      for cache in [user_history, pending_locations, ...]:        ││
│  │          for key, value in list(cache.items()):                  ││
│  │              if now - value.created_at > value.ttl:              ││
│  │                  del cache[key]                                  ││
│  │                                                                  ││
│  │      # Log memory stats                                          ││
│  │      log_memory_usage()                                          ││
│  │                                                                  ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Cache Flow for Chat Sessions

```
┌─────────────────────────────────────────────────────────────────────┐
│                     CHAT SESSION CACHING                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. New Message Arrives                                              │
│     ↓                                                               │
│  2. Check Cache                                                      │
│     if user_id in user_history:                                     │
│         return cached_history                                       │
│     ↓                                                               │
│  3. Cache Miss → Load from DB                                        │
│     history = db.get_chat_session(user_id)                          │
│     user_history[user_id] = history                                 │
│     ↓                                                               │
│  4. Process Message                                                  │
│     response = llm_loop(message, history)                           │
│     ↓                                                               │
│  5. Update Cache                                                     │
│     user_history[user_id].messages.append(message)                  │
│     user_history[user_id].messages.append(response)                 │
│     user_history[user_id].last_accessed = now                       │
│     ↓                                                               │
│  6. Persist to DB (async)                                            │
│     db.save_chat_session(user_id, history)                          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Concurrency & Performance

### Concurrency Controls

```
┌─────────────────────────────────────────────────────────────────────┐
│                   CONCURRENCY CONTROLS                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ PDF CONVERSION SEMAPHORE (generators/pdf.py)                     ││
│  ├─────────────────────────────────────────────────────────────────┤│
│  │                                                                  ││
│  │  pdf_semaphore = asyncio.Semaphore(3)                            ││
│  │                                                                  ││
│  │  Why: LibreOffice is memory-intensive                            ││
│  │  Limit: 3 concurrent conversions                                 ││
│  │                                                                  ││
│  │  async def convert_pptx_to_pdf(pptx_path):                       ││
│  │      async with pdf_semaphore:                                   ││
│  │          # Only 3 conversions run simultaneously                 ││
│  │          return await run_libreoffice(pptx_path)                 ││
│  │                                                                  ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ MOCKUP GENERATION QUEUE (utils/task_queue.py)                    ││
│  ├─────────────────────────────────────────────────────────────────┤│
│  │                                                                  ││
│  │  mockup_queue = TaskQueue(max_concurrent=2)                      ││
│  │                                                                  ││
│  │  Why: Image processing is CPU and memory intensive               ││
│  │  Limit: 2 concurrent mockup generations                          ││
│  │                                                                  ││
│  │  async def generate_mockup(params):                              ││
│  │      return await mockup_queue.submit(                           ││
│  │          _generate_mockup_internal, params                       ││
│  │      )                                                           ││
│  │                                                                  ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ RATE LIMITING (src/unified-ui/server.js)                             ││
│  ├─────────────────────────────────────────────────────────────────┤│
│  │                                                                  ││
│  │  Auth endpoints: 10 requests/minute per IP                       ││
│  │  API endpoints: No limit (relies on token auth)                  ││
│  │                                                                  ││
│  │  const authLimiter = rateLimit({                                 ││
│  │      windowMs: 60 * 1000,                                        ││
│  │      max: 10                                                     ││
│  │  });                                                             ││
│  │                                                                  ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Memory Management

**File:** `utils/memory.py`

```python
import gc
import psutil

def aggressive_cleanup():
    """
    Aggressive memory cleanup for image processing operations.
    Called after mockup generation to free memory immediately.
    """
    # Force garbage collection
    gc.collect()

    # Clear Python's internal freelists
    gc.collect()
    gc.collect()

def log_memory_stats():
    """Log current memory usage for monitoring."""
    process = psutil.Process()
    memory_info = process.memory_info()

    logger.info(
        "Memory stats",
        rss_mb=memory_info.rss / 1024 / 1024,
        vms_mb=memory_info.vms / 1024 / 1024,
        percent=process.memory_percent()
    )
```

---

## Error Handling

### Error Hierarchy

```
┌─────────────────────────────────────────────────────────────────────┐
│                     ERROR HANDLING                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                   Exception Hierarchy                            ││
│  │                   (api/exceptions.py)                            ││
│  ├─────────────────────────────────────────────────────────────────┤│
│  │                                                                  ││
│  │  AppException (base)                                             ││
│  │  ├── AuthenticationError     → 401 Unauthorized                  ││
│  │  ├── AuthorizationError      → 403 Forbidden                     ││
│  │  ├── NotFoundError           → 404 Not Found                     ││
│  │  ├── ValidationError         → 422 Unprocessable Entity          ││
│  │  ├── RateLimitError          → 429 Too Many Requests             ││
│  │  ├── ExternalServiceError    → 502 Bad Gateway                   ││
│  │  └── InternalError           → 500 Internal Server Error         ││
│  │                                                                  ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                   Error Response Format                          ││
│  ├─────────────────────────────────────────────────────────────────┤│
│  │                                                                  ││
│  │  {                                                               ││
│  │    "detail": "Human-readable error message",                     ││
│  │    "code": "ERROR_CODE",                                         ││
│  │    "errors": [                                                   ││
│  │      { "field": "email", "message": "Invalid format" }           ││
│  │    ]                                                             ││
│  │  }                                                               ││
│  │                                                                  ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  ┌─────────────────────────────────────────���───────────────────────┐│
│  │                   Global Exception Handler                       ││
│  │                   (api/server.py)                                ││
│  ├─────────────────────────────────────────────────────────────────┤│
│  │                                                                  ││
│  │  @app.exception_handler(AppException)                            ││
│  │  async def handle_app_exception(request, exc):                   ││
│  │      return JSONResponse(                                        ││
│  │          status_code=exc.status_code,                            ││
│  │          content={                                               ││
│  │              "detail": exc.message,                              ││
│  │              "code": exc.code                                    ││
│  │          }                                                       ││
│  │      )                                                           ││
│  │                                                                  ││
│  │  @app.exception_handler(Exception)                               ││
│  │  async def handle_unexpected(request, exc):                      ││
│  │      logger.exception("Unexpected error")                        ││
│  │      return JSONResponse(                                        ││
│  │          status_code=500,                                        ││
│  │          content={"detail": "Internal server error"}             ││
│  │      )                                                           ││
│  │                                                                  ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Fallback Strategies

| Component | Failure | Fallback |
|-----------|---------|----------|
| Supabase DB | Connection failed | Fall back to SQLite |
| OpenAI API | Rate limit/error | Retry with exponential backoff |
| LibreOffice | Not installed | Return PPTX only (no PDF) |
| Supabase Storage | Upload failed | Store locally, retry later |
| Slack API | Post failed | Log error, notify admin |

---

## Deployment Architecture

### Render.com Deployment

```
┌─────────────────────────────────────────────────────────────────────┐
│                    RENDER DEPLOYMENT                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                     render.yaml                                  ││
│  ├─────────────────────────────────────────────────────────────────┤│
│  │                                                                  ││
│  │  services:                                                       ││
│  │    - name: proposal-bot                                          ││
│  │      type: web                                                   ││
│  │      runtime: docker                                             ││
│  │      region: singapore                                           ││
│  │      plan: standard                                              ││
│  │      healthCheckPath: /health                                    ││
│  │      disk:                                                       ││
│  │        name: data                                                ││
│  │        mountPath: /data                                          ││
│  │        sizeGB: 5                                                 ││
│  │      envVars:                                                    ││
│  │        - key: ENVIRONMENT                                        ││
│  │          value: production                                       ││
│  │        - key: SALESBOT_SUPABASE_URL                              ││
│  │          sync: false  # From Render environment                  ││
│  │                                                                  ││
│  │    - name: unified-ui                                            ││
│  │      type: web                                                   ││
│  │      runtime: docker                                             ││
│  │      region: singapore                                           ││
│  │      plan: standard                                              ││
│  │      healthCheckPath: /health                                    ││
│  │      envVars:                                                    ││
│  │        - key: SALES_BOT_URL                                      ││
│  │          fromService:                                            ││
│  │            name: proposal-bot                                    ││
│  │            type: web                                             ││
│  │            property: hostport                                    ││
│  │                                                                  ││
│  │    - name: ai-costs-dashboard                                    ││
│  │      type: web                                                   ││
│  │      runtime: docker                                             ││
│  │      region: singapore                                           ││
│  │      plan: starter                                               ││
│  │                                                                  ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                   Branch Strategy                                ││
│  ├─────────────────────────────────────────────────────────────────┤│
│  │                                                                  ││
│  │  main branch:                                                    ││
│  │  ├── Deploys to production                                       ││
│  │  ├── Uses PROD Supabase projects                                 ││
│  │  └── URL: https://app.example.com                               ││
│  │                                                                  ││
│  │  dev branch:                                                     ││
│  │  ├── Deploys to staging                                          ││
│  │  ├── Uses DEV Supabase projects                                  ││
│  │  └── URL: https://dev.app.example.com                           ││
│  │                                                                  ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Docker Images

**Backend Dockerfile:**

```dockerfile
FROM python:3.11-slim

# Install LibreOffice for PDF conversion
RUN apt-get update && apt-get install -y \
    libreoffice \
    fonts-dejavu \
    fonts-liberation \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Install custom fonts
COPY data/fonts/ /usr/share/fonts/custom/
RUN fc-cache -f -v

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Run
CMD ["python", "main.py"]
```

**Frontend Dockerfile:**

```dockerfile
FROM node:18-slim

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci --only=production

# Copy application
COPY . .

# Run
EXPOSE 3005
CMD ["node", "server.js"]
```

---

## Security Architecture

### Defense in Depth

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SECURITY LAYERS                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Layer 1: NETWORK                                                    │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │  • HTTPS only (TLS 1.3)                                         ││
│  │  • Render.com managed SSL certificates                          ││
│  │  • CORS origin validation                                       ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  Layer 2: APPLICATION GATEWAY                                        │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │  • Helmet.js security headers                                   ││
│  │  • Rate limiting (10/min on auth)                               ││
│  │  • Request size limits                                          ││
│  │  • Content Security Policy                                      ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  Layer 3: AUTHENTICATION                                             │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │  • Supabase Auth (JWT tokens)                                   ││
│  │  • Microsoft SSO (OAuth 2.0)                                    ││
│  │  • Token expiration (1 hour)                                    ││
│  │  • Secure token storage                                         ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  Layer 4: AUTHORIZATION                                              │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │  • 4-level RBAC system                                          ││
│  │  • Permission checking on every request                         ││
│  │  • Team-based data isolation                                    ││
│  │  • Record-level sharing                                         ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  Layer 5: DATA ISOLATION                                             │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │  • Multi-tenant company schemas                                 ││
│  │  • Row-Level Security (RLS) policies                            ││
│  │  • User company access filtering                                ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  Layer 6: DATA PROTECTION                                            │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │  • Encryption at rest (Supabase)                                ││
│  │  • Encrypted connections (SSL)                                  ││
│  │  • Signed URLs for file access                                  ││
│  │  • No sensitive data in logs                                    ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Trusted Header Security

```
┌─────────────────────────────────────────────────────────────────────┐
│                 TRUSTED HEADER SECURITY                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Problem: How does proposal-bot trust user identity from headers?    │
│                                                                      │
│  Solution: Proxy Secret Verification                                 │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                                                                  ││
│  │  1. unified-ui and proposal-bot share a secret:                  ││
│  │     PROXY_SECRET=<randomly-generated-256-bit-key>                ││
│  │                                                                  ││
│  │  2. unified-ui injects the secret with every request:            ││
│  │     X-Proxy-Secret: <secret>                                     ││
│  │                                                                  ││
│  │  3. proposal-bot validates the secret:                           ││
│  │     if request.headers['X-Proxy-Secret'] != settings.PROXY_SECRET:││
│  │         raise HTTPException(401)                                 ││
│  │                                                                  ││
│  │  4. Only after validation, read trusted headers:                 ││
│  │     user_id = request.headers['X-Trusted-User-Id']               ││
│  │                                                                  ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  External Request (attacker trying to spoof headers):                │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                                                                  ││
│  │  POST /api/chat/message                                          ││
│  │  X-Trusted-User-Id: admin-uuid  ← Attacker's fake header        ││
│  │  X-Proxy-Secret: <missing or wrong>                              ││
│  │                                                                  ││
│  │  Result: 401 Unauthorized                                        ││
│  │                                                                  ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Monitoring & Observability

### Health Checks

**File:** `api/routers/health.py`

```python
# Basic liveness probe
@router.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow()}

# Readiness probe with dependency checks
@router.get("/health/ready")
async def ready():
    checks = {
        "database": await check_database(),
        "storage": await check_storage(),
        "llm": await check_llm_provider()
    }

    all_healthy = all(c["healthy"] for c in checks.values())

    return {
        "status": "ready" if all_healthy else "degraded",
        "checks": checks
    }
```

### Metrics Endpoint

**File:** `api/routers/health.py`

```python
@router.get("/metrics")
async def metrics():
    process = psutil.Process()

    return {
        "memory": {
            "rss_mb": process.memory_info().rss / 1024 / 1024,
            "percent": process.memory_percent()
        },
        "cpu_percent": process.cpu_percent(),
        "queues": {
            "pdf_conversion": pdf_semaphore._value,  # Available slots
            "mockup_generation": mockup_queue.pending_count()
        },
        "caches": {
            "user_sessions": len(user_history),
            "pending_locations": len(pending_location_additions)
        },
        "timestamp": datetime.utcnow()
    }
```

### Structured Logging

**File:** `utils/logging.py`

```python
import structlog

def setup_logging():
    """Configure structured logging."""

    if settings.ENVIRONMENT == "production":
        # JSON format for log aggregation
        structlog.configure(
            processors=[
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer()
            ]
        )
    else:
        # Human-readable for development
        structlog.configure(
            processors=[
                structlog.processors.TimeStamper(fmt="%H:%M:%S"),
                structlog.dev.ConsoleRenderer()
            ]
        )

# Usage
logger = structlog.get_logger()
logger.info("Proposal generated",
    proposal_id=proposal.id,
    client=proposal.client_name,
    locations=len(proposal.locations),
    user_id=user.id
)
```

### Log Output Examples

**Production (JSON):**
```json
{"timestamp": "2024-01-15T10:30:00Z", "level": "info", "event": "Proposal generated", "proposal_id": "uuid", "client": "Acme Corp", "locations": 3, "user_id": "user-uuid"}
```

**Development (Console):**
```
10:30:00 [info] Proposal generated proposal_id=uuid client=Acme Corp locations=3 user_id=user-uuid
```

---

## Appendix: Key File Reference

| File | Purpose |
|------|---------|
| `api/server.py` | FastAPI app initialization, middleware, lifespan |
| `api/auth.py` | Authentication dependencies, permission checking |
| `api/routers/*.py` | HTTP endpoint handlers |
| `core/llm.py` | Main LLM orchestration loop |
| `core/proposals.py` | Proposal generation business logic |
| `core/tools.py` | LLM tool definitions |
| `generators/pptx.py` | PowerPoint generation |
| `generators/pdf.py` | PDF conversion |
| `generators/mockup.py` | Billboard mockup generation |
| `db/database.py` | Database facade |
| `db/backends/*.py` | Database backend implementations |
| `db/cache.py` | In-memory caching |
| `integrations/llm/client.py` | LLM provider client |
| `integrations/auth/client.py` | Auth provider client |
| `integrations/storage/client.py` | Storage provider client |
| `integrations/channels/adapters/*.py` | Channel adapters (Slack, Web) |
| `src/unified-ui/backend/main.py` | FastAPI gateway, auth, proxy |
| `src/unified-ui/public/js/*.js` | Frontend modules |
| `config.py` | Application configuration |
| `render.yaml` | Deployment configuration |

---

*This architecture document provides a comprehensive technical reference for the MMG Service Platform. For setup instructions, see [DEVELOPMENT.md](./DEVELOPMENT.md). For deployment options, see [DEPLOYMENT.md](./DEPLOYMENT.md). For API details, see [src/sales-module/FRONTEND_API.md](./src/sales-module/FRONTEND_API.md).*

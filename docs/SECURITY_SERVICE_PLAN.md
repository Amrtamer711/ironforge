# Security Architecture - Elite Compliance-Ready Setup

## Executive Summary

This plan implements an **enterprise-grade security architecture** with a centralized security service and a published SDK package. This setup is designed for **SOC 2, GDPR, HIPAA, and ISO 27001 compliance**.

### Architecture Philosophy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ELITE SECURITY ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  "Authenticate at the edge, authorize locally, audit centrally"             │
│                                                                              │
│  • Gateway validates tokens ONCE                                             │
│  • SDK handles fast local operations (no network overhead)                   │
│  • Service stores audit logs and manages API keys (centralized)             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Components Overview

| Component | Location | Purpose | Installation |
|-----------|----------|---------|--------------|
| **Security Service** | `src/security/service/` | REST API for persistence & central authority | Deploy as container |
| **Security SDK** | `src/security/sdk/` | Fast local operations | `pip install` from git |
| **Security Database** | Supabase (isolated) | Immutable audit logs, API keys | Separate project |

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              REQUEST FLOW                                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Client                                                                          │
│    │                                                                             │
│    │ JWT Token                                                                   │
│    ▼                                                                             │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                        GATEWAY (unified-ui)                                 │ │
│  │                           Port: 3005                                        │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │  1. Receive JWT from client                                                 │ │
│  │  2. POST /api/auth/validate-token → security-service                       │ │
│  │  3. GET /api/rbac/user-context/{id} → security-service                     │ │
│  │  4. Inject X-Trusted-User-* headers                                         │ │
│  │  5. Inject X-Request-ID for tracing                                         │ │
│  │  6. Proxy to backend service                                                │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│              │                              │                              │     │
│   /api/sales/*                   /api/assets/*                  /api/security/* │
│              ▼                              ▼                              ▼     │
│  ┌────────────────────┐      ┌────────────────────┐      ┌─────────────────────┐│
│  │   SALES-MODULE     │      │  ASSET-MANAGEMENT  │      │  SECURITY-SERVICE   ││
│  │     Port: 8000     │      │     Port: 8001     │      │     Port: 8002      ││
│  ├────────────────────┤      ├────────────────────┤      ├─────────────────────┤│
│  │                    │      │                    │      │                     ││
│  │  ┌──────────────┐  │      │  ┌──────────────┐  │      │ Token Validation    ││
│  │  │  crm_security│  │      │  │  crm_security│  │      │ RBAC Resolution     ││
│  │  │     (SDK)    │  │      │  │     (SDK)    │  │      │ Audit Storage       ││
│  │  ├──────────────┤  │      │  ├──────────────┤  │      │ API Key Mgmt        ││
│  │  │• Middleware  │  │      │  │• Middleware  │  │      │ Rate Limiting       ││
│  │  │• Dependencies│  │      │  │• Dependencies│  │      │ Security Events     ││
│  │  │• RBAC checks │  │      │  │• RBAC checks │  │      │                     ││
│  │  │• @audit dec  │──┼──────┼──┼──────────────┼──┼─────►│ POST /api/audit/log ││
│  │  └──────────────┘  │      │  └──────────────┘  │      │                     ││
│  │                    │      │                    │      │                     ││
│  └────────────────────┘      └────────────────────┘      └──────────┬──────────┘│
│                                                                      │          │
│                                                                      ▼          │
│                                                          ┌─────────────────────┐│
│                                                          │  SECURITY SUPABASE  ││
│                                                          │     (Isolated)      ││
│                                                          ├─────────────────────┤│
│                                                          │ • audit_logs        ││
│                                                          │ • api_keys          ││
│                                                          │ • security_events   ││
│                                                          │ • rate_limit_state  ││
│                                                          │                     ││
│                                                          │ 🔒 Append-only logs ││
│                                                          │ 🔒 Encrypted at rest││
│                                                          └─────────────────────┘│
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
src/
├── security/                           # 🔐 ALL SECURITY CODE LIVES HERE
│   │
│   ├── sdk/                            # 📦 Published as pip package: crm-security
│   │   ├── pyproject.toml              # Package configuration
│   │   ├── README.md                   # SDK documentation
│   │   └── crm_security/               # Package source
│   │       ├── __init__.py             # Public API exports
│   │       ├── config.py               # SDK configuration
│   │       ├── models.py               # AuthUser, TrustedUserContext
│   │       ├── context.py              # Thread-local user context
│   │       ├── rbac.py                 # Permission checking (local, fast)
│   │       ├── trusted_headers.py      # Header parsing
│   │       ├── dependencies.py         # FastAPI dependencies
│   │       ├── middleware.py           # SecurityHeaders, TrustedUser middleware
│   │       ├── audit.py                # Audit client (async HTTP to service)
│   │       ├── security_events.py      # Security event logging
│   │       └── decorators.py           # @audit decorator
│   │
│   └── service/                        # 🚀 Deployed as security-service
│       ├── main.py                     # Entry point
│       ├── config.py                   # Service configuration
│       ├── requirements.txt            # Dependencies
│       ├── Dockerfile                  # Container build
│       ├── api/
│       │   ├── __init__.py
│       │   ├── server.py               # FastAPI app
│       │   ├── dependencies.py         # Service auth
│       │   └── routers/
│       │       ├── __init__.py
│       │       ├── health.py           # GET /health
│       │       ├── auth.py             # POST /api/auth/*
│       │       ├── rbac.py             # GET/POST /api/rbac/*
│       │       ├── audit.py            # POST /api/audit/*
│       │       ├── api_keys.py         # CRUD /api/api-keys/*
│       │       ├── rate_limit.py       # POST /api/rate-limit/*
│       │       └── security_events.py  # POST /api/security-events/*
│       ├── core/                       # Business logic
│       │   ├── __init__.py
│       │   ├── auth.py
│       │   ├── rbac.py
│       │   ├── audit.py
│       │   ├── api_keys.py
│       │   └── rate_limit.py
│       ├── db/                         # Database layer
│       │   ├── __init__.py
│       │   ├── base.py                 # Abstract base
│       │   ├── database.py             # Connection management
│       │   └── backends/
│       │       ├── __init__.py
│       │       └── supabase.py
│       ├── models/                     # Pydantic models
│       │   ├── __init__.py
│       │   ├── auth.py
│       │   ├── rbac.py
│       │   ├── audit.py
│       │   ├── api_keys.py
│       │   └── rate_limit.py
│       └── migrations/
│           ├── 001_initial_schema.sql
│           └── 002_seed_data.sql
│
├── sales-module/
│   ├── requirements.txt                # Includes: crm-security @ git+...
│   ├── api/
│   │   ├── server.py                   # Uses SDK middleware
│   │   └── routers/                    # Uses SDK dependencies
│   └── ...
│
├── asset-management/
│   ├── requirements.txt                # Includes: crm-security @ git+...
│   └── ...
│
└── unified-ui/
    └── ...                             # Calls security-service HTTP API
```

---

## Component Details

### 1. Security SDK (`crm-security`)

**Installation:**
```txt
# In any service's requirements.txt

# Pin to tag (recommended for production)
crm-security @ git+https://github.com/yourorg/CRM.git@v1.0.0#subdirectory=src/security/sdk

# Or latest (for development)
crm-security @ git+https://github.com/yourorg/CRM.git#subdirectory=src/security/sdk
```

**Usage:**
```python
from crm_security import (
    # Middleware
    SecurityHeadersMiddleware,
    TrustedUserMiddleware,

    # FastAPI Dependencies
    require_auth,
    require_permission,
    require_admin,
    get_current_user,

    # RBAC (local, fast - no network)
    has_permission,
    can_access_record,
    get_accessible_user_ids,

    # Audit (async HTTP to security-service)
    audit_log,

    # Decorator
    audit,

    # Models
    AuthUser,
    TrustedUserContext,
)

# In FastAPI app
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(TrustedUserMiddleware, exempt_paths={"/health"})

# In routes
@router.post("/proposals")
@audit(action="create", resource_type="proposal")
async def create_proposal(
    data: ProposalCreate,
    user = Depends(require_permission("sales:proposals:create"))
):
    proposal = await service.create(data, user["id"])
    return proposal
```

**What SDK Handles (Local, No Network):**
- Parse trusted headers from gateway
- Check permissions against user context
- Manage thread-local user context
- Security middleware (headers, timing, request ID)

**What SDK Calls Service For (Async HTTP):**
- Audit logging → `POST /api/audit/log`
- Security events → `POST /api/security-events/`

---

### 2. Security Service

**Endpoints:**

| Endpoint | Method | Called By | Purpose |
|----------|--------|-----------|---------|
| `/api/auth/validate-token` | POST | Gateway | Validate JWT, return user |
| `/api/auth/service-token` | POST | Services | Generate service-to-service token |
| `/api/rbac/user-context/{id}` | GET | Gateway | Full 5-level RBAC context |
| `/api/rbac/check-permission` | POST | Services (fallback) | Check permission |
| `/api/rbac/check-record-access` | POST | Services | Record-level access check |
| `/api/audit/log` | POST | SDK | Store audit event |
| `/api/audit/logs` | GET | Admin | Query audit logs |
| `/api/api-keys/validate` | POST | Services | Validate API key |
| `/api/api-keys` | POST/GET/DELETE | Admin | CRUD API keys |
| `/api/rate-limit/check` | POST | Services | Distributed rate limiting |
| `/api/security-events/` | POST | SDK | Log security incident |

**Service Authentication:**
All requests to security-service must include:
- `X-Service-Secret: <SERVICE_API_SECRET>`
- `X-Service-Name: <calling-service-name>`

---

### 3. Security Database (Supabase)

**Why Isolated?**
- Audit logs must be tamper-proof for compliance
- Different retention policies (7+ years for audit)
- Minimal access (only security-service writes)

**Tables:**

```sql
-- IMMUTABLE - append-only for compliance
audit_logs (
    id, timestamp,
    actor_type, actor_id, actor_email, actor_ip,
    service, action, resource_type, resource_id,
    result, error_message,
    request_id, request_method, request_path,
    response_status, duration_ms,
    metadata
)

-- API key management
api_keys (
    id, key_hash, key_prefix, name,
    scopes, allowed_services, allowed_ips,
    rate_limit_per_minute, rate_limit_per_day,
    is_active, expires_at, last_used_at,
    created_by, created_at
)

-- Security incidents
security_events (
    id, timestamp, event_type, severity,
    service, actor_id, ip_address,
    message, details,
    is_resolved, resolved_at, resolved_by
)

-- Distributed rate limiting
rate_limit_state (
    id, key, window_start, request_count
)
```

---

## SDK Package Structure

**`src/security/sdk/pyproject.toml`:**
```toml
[project]
name = "crm-security"
version = "1.0.0"
description = "Security SDK for MMG Service Platform"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.100.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "httpx>=0.25.0",
]

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["crm_security*"]
```

**`src/security/sdk/crm_security/__init__.py`:**
```python
"""
CRM Security SDK

Fast, local security operations with async audit logging.

Usage:
    from crm_security import require_auth, audit_log, SecurityHeadersMiddleware
"""

# Middleware
from .middleware import SecurityHeadersMiddleware, TrustedUserMiddleware

# Dependencies
from .dependencies import (
    get_current_user,
    require_auth,
    require_permission,
    require_any_permission,
    require_admin,
    require_profile,
)

# RBAC
from .rbac import (
    has_permission,
    has_any_permission,
    has_all_permissions,
    can_access_record,
    can_access_user_data,
    get_accessible_user_ids,
    PERMISSIONS,
)

# Context
from .context import (
    get_user_context,
    set_user_context,
    clear_user_context,
    get_current_user_id,
    is_authenticated,
)

# Audit
from .audit import audit_log, AuditClient

# Security Events
from .security_events import log_security_event, SecurityEventType

# Decorators
from .decorators import audit

# Models
from .models import AuthUser, TrustedUserContext

__all__ = [
    # Middleware
    "SecurityHeadersMiddleware",
    "TrustedUserMiddleware",
    # Dependencies
    "get_current_user",
    "require_auth",
    "require_permission",
    "require_any_permission",
    "require_admin",
    "require_profile",
    # RBAC
    "has_permission",
    "has_any_permission",
    "has_all_permissions",
    "can_access_record",
    "can_access_user_data",
    "get_accessible_user_ids",
    "PERMISSIONS",
    # Context
    "get_user_context",
    "set_user_context",
    "clear_user_context",
    "get_current_user_id",
    "is_authenticated",
    # Audit
    "audit_log",
    "AuditClient",
    # Security Events
    "log_security_event",
    "SecurityEventType",
    # Decorators
    "audit",
    # Models
    "AuthUser",
    "TrustedUserContext",
]
```

---

## Implementation Phases

### Phase 1: Restructure Directory
| Task | Description |
|------|-------------|
| Create `src/security/` | New root for all security code |
| Move `src/security-service/*` → `src/security/service/` | Relocate existing service |
| Move `src/shared/security/*` → `src/security/sdk/crm_security/` | Relocate SDK code |
| Add `pyproject.toml` | Make SDK pip-installable |

### Phase 2: Enhance SDK
| Task | Description |
|------|-------------|
| Update `audit.py` | HTTP client to security-service |
| Add `security_events.py` | Security event logging |
| Add `decorators.py` | @audit decorator |
| Test local install | `pip install -e src/security/sdk` |

### Phase 3: Update Services
| Task | Description |
|------|-------------|
| Delete `sales-module/security/` | Remove duplicate |
| Update `sales-module/requirements.txt` | Add `crm-security @ git+...` |
| Update imports | `from security import` → `from crm_security import` |
| Repeat for `asset-management` | Same process |

### Phase 4: Update Gateway
| Task | Description |
|------|-------------|
| Add security-service calls | Token validation, RBAC context |
| Update header injection | Use response from security-service |

### Phase 5: Cleanup & Test
| Task | Description |
|------|-------------|
| Delete `src/shared/` | No longer needed |
| Delete old `src/security-service/` | Moved to new location |
| Full integration test | Verify end-to-end flow |
| Tag release | `git tag v1.0.0` |

---

## Environment Variables

```bash
# =============================================================================
# ALL SERVICES
# =============================================================================
ENVIRONMENT=local                    # local | development | production
SERVICE_NAME=sales-module            # Name of this service
SERVICE_API_SECRET=                  # Shared secret for service auth

# =============================================================================
# SECURITY SERVICE URL
# =============================================================================
SECURITY_SERVICE_URL=http://localhost:8002

# =============================================================================
# SECURITY SERVICE ONLY
# =============================================================================
# Security Supabase (owns audit_logs, api_keys, etc.)
SECURITY_DEV_SUPABASE_URL=
SECURITY_DEV_SUPABASE_SERVICE_KEY=
SECURITY_PROD_SUPABASE_URL=
SECURITY_PROD_SUPABASE_SERVICE_KEY=

# UI Supabase (read-only for user/profile lookups)
UI_DEV_SUPABASE_URL=
UI_DEV_SUPABASE_SERVICE_KEY=
UI_PROD_SUPABASE_URL=
UI_PROD_SUPABASE_SERVICE_KEY=

# =============================================================================
# SDK CONFIGURATION (set in each service)
# =============================================================================
PROXY_SECRET=                        # Gateway → backend trust
DEV_AUTH_ENABLED=false               # Enable dev auth for /docs testing
DEV_AUTH_TOKEN=                      # Static token for dev auth
```

---

## Compliance Features

### 1. Immutable Audit Logs
```sql
-- RLS policy prevents updates/deletes
CREATE POLICY "Audit logs are append-only"
ON audit_logs FOR ALL
USING (false) WITH CHECK (true);

CREATE POLICY "Services can only insert"
ON audit_logs FOR INSERT
WITH CHECK (true);
```

### 2. Request Tracing
Every request gets a unique ID that flows through all services:
```
X-Request-ID: abc-123-def-456

Gateway → Backend → Security Service
   │          │           │
   └──────────┴───────────┘
         Same ID everywhere

Audit logs reference this ID for full request reconstruction.
```

### 3. Security Event Detection
```python
class SecurityEventType(Enum):
    FAILED_LOGIN = "failed_login"
    BRUTE_FORCE = "brute_force_detected"
    INVALID_TOKEN = "invalid_token"
    PERMISSION_DENIED = "permission_denied"
    SUSPICIOUS_IP = "suspicious_ip"
    API_KEY_ABUSE = "api_key_abuse"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
```

### 4. Full Audit Trail
Every action is logged with:
- **Who**: actor_type, actor_id, actor_email, actor_ip
- **What**: action, resource_type, resource_id
- **When**: timestamp
- **Where**: service, request_path
- **Result**: success/denied/error
- **Context**: request_id for tracing

---

## Service Ports

| Service | Port | Purpose |
|---------|------|---------|
| unified-ui | 3005 | Gateway + Frontend |
| sales-module | 8000 | Business data |
| asset-management | 8001 | Asset data |
| security-service | 8002 | Auth/RBAC/Audit |

---

## Supabase Projects

| Project | Purpose | Accessed By |
|---------|---------|-------------|
| UI Supabase | Users, profiles, permissions, teams | unified-ui, security-service (read) |
| Sales Supabase | Proposals, booking orders, rate cards | sales-module |
| Asset Supabase | Networks, locations, packages | asset-management |
| Security Supabase | Audit logs, API keys, rate limits | security-service (read/write) |

---

## Summary

This architecture provides:

- ✅ **Single source of truth** for security (security-service)
- ✅ **Fast local operations** via SDK (no network overhead for permission checks)
- ✅ **Centralized audit logging** for compliance
- ✅ **Immutable audit trail** (append-only database)
- ✅ **Request tracing** across all services
- ✅ **Easy deployment** (SDK via pip install from git)
- ✅ **Scalable** to 100+ services
- ✅ **Compliance-ready** (SOC 2, GDPR, HIPAA, ISO 27001)

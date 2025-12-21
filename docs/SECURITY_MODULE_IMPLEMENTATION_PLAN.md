# Comprehensive Security Module & Service Integration Plan

> **⚠️ SUPERSEDED**: This plan is based on a **shared library** approach (`src/shared/security/`).
>
> **See the new plan**: [SECURITY_SERVICE_PLAN.md](./SECURITY_SERVICE_PLAN.md)
>
> The new architecture uses a **standalone microservice** (`src/security-service/`) with REST API communication.
> Each module will be its own isolated Render deployment with its own repository - no Python imports between services.

---

## Executive Summary (DEPRECATED)

This plan creates a **modular security system** with its own Supabase project, designed for maximum scalability. The architecture follows the pattern used by Netflix, Google, and AWS: **validate locally, store centrally (async)**.

### What We're Building

| Component | Purpose |
|-----------|---------|
| **Security Supabase** | Dedicated database for audit logs, API keys, service registry |
| **Shared Security Library** | `src/shared/security/` - imported by all services |
| **Asset-Management Auth** | Add authentication to currently unprotected service |
| **Unified-UI Gateway Update** | Add `/api/assets/*` proxy route |
| **Inter-Service Communication** | JWT-based service-to-service auth |

### Supabase Projects (4 Total)

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                              SUPABASE PROJECTS                                  │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐    │
│  │   UI SUPABASE       │  │  SALES SUPABASE     │  │  ASSET SUPABASE     │    │
│  │   (Auth/RBAC)       │  │  (Business Data)    │  │  (Asset Data)       │    │
│  ├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤    │
│  │ • auth.users        │  │ • proposals_log     │  │ • networks          │    │
│  │ • users             │  │ • booking_orders    │  │ • asset_types       │    │
│  │ • profiles          │  │ • rate_cards        │  │ • locations         │    │
│  │ • permissions       │  │ • mockup_frames     │  │ • packages          │    │
│  │ • profile_perms     │  │ • ai_costs          │  │ • package_items     │    │
│  │ • permission_sets   │  │                     │  │                     │    │
│  │ • teams             │  │                     │  │                     │    │
│  │ • team_members      │  │                     │  │                     │    │
│  │ • user_companies    │  │                     │  │                     │    │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘    │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │                        SECURITY SUPABASE (NEW)                           │  │
│  │                     Centralized Security Data Store                      │  │
│  ├─────────────────────────────────────────────────────────────────────────┤  │
│  │ • audit_logs        - All service audit events (compliance-ready)       │  │
│  │ • api_keys          - Centralized API key management                    │  │
│  │ • api_key_usage     - Usage tracking and analytics                      │  │
│  │ • service_registry  - Authorized services and their permissions         │  │
│  │ • rate_limit_state  - Distributed rate limiting (Redis alternative)     │  │
│  │ • security_events   - Security incidents and alerts                     │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL USERS                                      │
│                         (Browser / Mobile / API Clients)                         │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                            JWT Token │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           UNIFIED-UI (Gateway)                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │ 1. Validate JWT against UI Supabase                                      │   │
│  │ 2. Fetch 5-level RBAC context (cached 30s)                               │   │
│  │ 3. Inject X-Trusted-User-* headers                                       │   │
│  │ 4. Inject X-Proxy-Secret header                                          │   │
│  │ 5. Proxy to backend service                                              │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
              │                              │                              │
  /api/sales/*│                  /api/assets/*│              Service-to-Service│
              ▼                              ▼                              ▼
┌──────────────────────┐    ┌──────────────────────┐    ┌──────────────────────┐
│    SALES-MODULE      │    │  ASSET-MANAGEMENT    │    │   FUTURE SERVICES    │
│    Port: 8000        │    │    Port: 8001        │    │                      │
├──────────────────────┤    ├──────────────────────┤    ├──────────────────────┤
│ [shared.security]    │    │ [shared.security]    │    │ [shared.security]    │
│  • Trusted headers   │    │  • Trusted headers   │    │  • Trusted headers   │
│  • RBAC decorators   │    │  • RBAC decorators   │    │  • RBAC decorators   │
│  • Audit logging     │    │  • Audit logging     │    │  • Audit logging     │
│  • Service JWT       │◄──►│  • Service JWT       │◄──►│  • Service JWT       │
└──────────┬───────────┘    └──────────┬───────────┘    └──────────────────────┘
           │                           │                           │
           │                           │                           │
           ▼                           ▼                           ▼
┌──────────────────────┐    ┌──────────────────────┐    ┌──────────────────────┐
│   SALES SUPABASE     │    │   ASSET SUPABASE     │    │  SECURITY SUPABASE   │
│   (Business Data)    │    │   (Asset Data)       │    │  (Centralized)       │
└──────────────────────┘    └──────────────────────┘    │  • audit_logs        │
                                                         │  • api_keys          │
                                                         │  • service_registry  │
                                                         └──────────────────────┘
```

---

## Part 1: Security Supabase Project Setup

### 1.1 Create New Supabase Project

**Manual Step**: Create a new Supabase project named `crm-security`

Required credentials to save:
- `SECURITY_SUPABASE_URL`
- `SECURITY_SUPABASE_ANON_KEY`
- `SECURITY_SUPABASE_SERVICE_ROLE_KEY`

### 1.2 Database Schema

**File to create**: `src/shared/security/migrations/001_initial_schema.sql`

```sql
-- ============================================================================
-- SECURITY SUPABASE SCHEMA
-- Centralized security data for all services
-- ============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- AUDIT LOGS
-- Compliance-ready audit trail for all services
-- ============================================================================

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- When
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Who
    actor_type TEXT NOT NULL,  -- 'user', 'service', 'system', 'anonymous'
    actor_id TEXT,             -- user UUID or service name
    actor_email TEXT,          -- for user actors
    actor_ip TEXT,             -- client IP address

    -- What
    service TEXT NOT NULL,     -- 'sales-module', 'asset-management', 'unified-ui'
    action TEXT NOT NULL,      -- 'create', 'read', 'update', 'delete', 'login', 'logout'
    resource_type TEXT,        -- 'location', 'proposal', 'user', etc.
    resource_id TEXT,          -- specific resource identifier

    -- Result
    result TEXT NOT NULL DEFAULT 'success',  -- 'success', 'denied', 'error'
    error_message TEXT,        -- if result is 'error'

    -- Context
    request_id TEXT,           -- correlation ID
    request_method TEXT,       -- 'GET', 'POST', etc.
    request_path TEXT,         -- '/api/v1/locations/123'
    request_body JSONB,        -- sanitized request body (no secrets)
    response_status INT,       -- HTTP status code
    duration_ms INT,           -- request duration

    -- Additional metadata
    metadata JSONB DEFAULT '{}',

    -- Indexes for common queries
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for audit queries
CREATE INDEX idx_audit_logs_timestamp ON audit_logs(timestamp DESC);
CREATE INDEX idx_audit_logs_actor ON audit_logs(actor_type, actor_id);
CREATE INDEX idx_audit_logs_service ON audit_logs(service);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_logs_result ON audit_logs(result);
CREATE INDEX idx_audit_logs_request_id ON audit_logs(request_id);

-- Composite index for compliance queries
CREATE INDEX idx_audit_logs_compliance ON audit_logs(actor_id, timestamp DESC, action);

-- ============================================================================
-- API KEYS
-- Centralized API key management
-- ============================================================================

CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Key identification
    key_hash TEXT NOT NULL UNIQUE,  -- SHA-256 hash of the key
    key_prefix TEXT NOT NULL,       -- First 8 chars for identification (sk_abc123...)
    name TEXT NOT NULL,             -- Human-readable name
    description TEXT,

    -- Ownership
    created_by TEXT,                -- User ID who created
    organization TEXT,              -- Optional org grouping

    -- Permissions
    scopes TEXT[] NOT NULL DEFAULT '{}',  -- ['read', 'write', 'admin']
    allowed_services TEXT[] DEFAULT NULL, -- NULL = all services
    allowed_ips TEXT[] DEFAULT NULL,      -- NULL = all IPs

    -- Limits
    rate_limit_per_minute INT DEFAULT 100,
    rate_limit_per_day INT DEFAULT 10000,

    -- Lifecycle
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    expires_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    last_used_ip TEXT,
    use_count BIGINT DEFAULT 0,

    -- Metadata
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_prefix ON api_keys(key_prefix);
CREATE INDEX idx_api_keys_active ON api_keys(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_api_keys_created_by ON api_keys(created_by);

-- ============================================================================
-- API KEY USAGE
-- Track API key usage for analytics and billing
-- ============================================================================

CREATE TABLE api_key_usage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    key_id UUID NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,

    -- Request info
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    service TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL,
    status_code INT NOT NULL,

    -- Client info
    ip_address TEXT,
    user_agent TEXT,

    -- Performance
    duration_ms INT,

    -- For time-series queries
    hour_bucket TIMESTAMPTZ GENERATED ALWAYS AS (date_trunc('hour', timestamp)) STORED
);

-- Indexes for usage analytics
CREATE INDEX idx_api_key_usage_key ON api_key_usage(key_id);
CREATE INDEX idx_api_key_usage_timestamp ON api_key_usage(timestamp DESC);
CREATE INDEX idx_api_key_usage_hour ON api_key_usage(hour_bucket);

-- ============================================================================
-- SERVICE REGISTRY
-- Track authorized services and their permissions
-- ============================================================================

CREATE TABLE service_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Service identification
    service_name TEXT NOT NULL UNIQUE,  -- 'sales-module', 'asset-management'
    display_name TEXT NOT NULL,
    description TEXT,

    -- Service details
    base_url TEXT,                      -- 'http://sales-module:8000'
    health_endpoint TEXT DEFAULT '/health',
    version TEXT,

    -- Permissions
    allowed_to_call TEXT[] DEFAULT '{}',  -- Services this one can call
    can_be_called_by TEXT[] DEFAULT '{}', -- Services that can call this one

    -- Status
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_heartbeat TIMESTAMPTZ,

    -- Metadata
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- RATE LIMIT STATE
-- Distributed rate limiting (alternative to Redis)
-- ============================================================================

CREATE TABLE rate_limit_state (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Rate limit key (e.g., "user:123:endpoint:/api/locations")
    key TEXT NOT NULL,

    -- Sliding window state
    window_start TIMESTAMPTZ NOT NULL,
    request_count INT NOT NULL DEFAULT 1,

    -- Metadata
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Unique constraint for upsert
    UNIQUE(key, window_start)
);

-- Index for lookups
CREATE INDEX idx_rate_limit_key ON rate_limit_state(key);
CREATE INDEX idx_rate_limit_window ON rate_limit_state(window_start);

-- Cleanup function for expired windows
CREATE OR REPLACE FUNCTION cleanup_rate_limit_state() RETURNS void AS $$
BEGIN
    DELETE FROM rate_limit_state
    WHERE window_start < NOW() - INTERVAL '5 minutes';
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- SECURITY EVENTS
-- Track security incidents and alerts
-- ============================================================================

CREATE TABLE security_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Event classification
    event_type TEXT NOT NULL,   -- 'failed_login', 'rate_limit_exceeded', 'invalid_token', etc.
    severity TEXT NOT NULL,     -- 'info', 'warning', 'error', 'critical'

    -- Context
    service TEXT NOT NULL,
    actor_type TEXT,
    actor_id TEXT,
    ip_address TEXT,

    -- Details
    message TEXT NOT NULL,
    details JSONB DEFAULT '{}',

    -- Resolution
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    resolved_by TEXT,
    resolution_notes TEXT,

    -- Timestamps
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_security_events_type ON security_events(event_type);
CREATE INDEX idx_security_events_severity ON security_events(severity);
CREATE INDEX idx_security_events_timestamp ON security_events(timestamp DESC);
CREATE INDEX idx_security_events_unresolved ON security_events(is_resolved) WHERE is_resolved = FALSE;

-- ============================================================================
-- ROW LEVEL SECURITY
-- ============================================================================

ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_key_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE service_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE rate_limit_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE security_events ENABLE ROW LEVEL SECURITY;

-- Service role has full access (used by backend services)
CREATE POLICY "Service role full access on audit_logs" ON audit_logs
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access on api_keys" ON api_keys
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access on api_key_usage" ON api_key_usage
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access on service_registry" ON service_registry
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access on rate_limit_state" ON rate_limit_state
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access on security_events" ON security_events
    FOR ALL TO service_role USING (true) WITH CHECK (true);
```

### 1.3 Seed Data

**File to create**: `src/shared/security/migrations/002_seed_data.sql`

```sql
-- ============================================================================
-- SEED DATA FOR SECURITY SUPABASE
-- ============================================================================

-- Register known services
INSERT INTO service_registry (service_name, display_name, description, base_url, allowed_to_call, can_be_called_by) VALUES
('unified-ui', 'Unified UI Gateway', 'API Gateway and authentication proxy', 'http://localhost:3005',
 ARRAY['sales-module', 'asset-management'], ARRAY[]::TEXT[]),

('sales-module', 'Sales Module', 'Proposals, bookings, and rate cards', 'http://localhost:8000',
 ARRAY['asset-management'], ARRAY['unified-ui', 'asset-management']),

('asset-management', 'Asset Management', 'Networks, locations, and packages', 'http://localhost:8001',
 ARRAY['sales-module'], ARRAY['unified-ui', 'sales-module']);
```

---

## Part 2: Shared Security Library

### 2.1 Directory Structure

```
src/shared/
├── __init__.py
├── security/
│   ├── __init__.py              # Public exports
│   ├── config.py                # Pydantic settings for security
│   ├── models.py                # Data models (UserContext, AuditEvent, etc.)
│   ├── trusted_headers.py       # Parse X-Trusted-User-* headers
│   ├── service_auth.py          # Inter-service JWT authentication
│   ├── rbac.py                  # Permission checking decorators
│   ├── audit.py                 # Audit logging to Security Supabase
│   ├── api_keys.py              # API key validation
│   ├── rate_limit.py            # Rate limiting with Supabase backend
│   ├── middleware.py            # FastAPI security middleware
│   ├── dependencies.py          # FastAPI dependencies (require_auth, etc.)
│   ├── exceptions.py            # Security exceptions
│   └── migrations/              # SQL migrations
│       ├── 001_initial_schema.sql
│       └── 002_seed_data.sql
└── README.md
```

### 2.2 Security Config

**File**: `src/shared/security/config.py`

```python
"""
Security configuration.
Loaded from environment variables with sensible defaults.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SecurityConfig(BaseSettings):
    """Security-related configuration for all services."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # =========================================================================
    # ENVIRONMENT
    # =========================================================================

    environment: Literal["local", "development", "production"] = Field(
        default="local",
        description="Deployment environment",
    )

    # =========================================================================
    # PROXY TRUST
    # =========================================================================

    proxy_secret: str | None = Field(
        default=None,
        description="Shared secret from unified-ui gateway (X-Proxy-Secret header)",
    )
    trust_proxy_headers: bool = Field(
        default=True,
        description="Whether to trust X-Trusted-User-* headers from gateway",
    )

    # =========================================================================
    # INTER-SERVICE AUTHENTICATION
    # =========================================================================

    inter_service_secret: str | None = Field(
        default=None,
        description="Shared secret for signing inter-service JWT tokens",
    )
    service_token_expiry_seconds: int = Field(
        default=60,
        description="How long inter-service tokens are valid (seconds)",
    )
    service_name: str = Field(
        default="unknown",
        description="This service's name (for JWT claims)",
    )

    # =========================================================================
    # SECURITY SUPABASE
    # =========================================================================

    # Development
    security_dev_supabase_url: str | None = Field(default=None)
    security_dev_supabase_anon_key: str | None = Field(default=None)
    security_dev_supabase_service_key: str | None = Field(default=None)

    # Production
    security_prod_supabase_url: str | None = Field(default=None)
    security_prod_supabase_anon_key: str | None = Field(default=None)
    security_prod_supabase_service_key: str | None = Field(default=None)

    # =========================================================================
    # AUDIT LOGGING
    # =========================================================================

    audit_enabled: bool = Field(
        default=True,
        description="Enable audit logging to Security Supabase",
    )
    audit_log_request_body: bool = Field(
        default=False,
        description="Include request body in audit logs (careful with PII)",
    )
    audit_async: bool = Field(
        default=True,
        description="Write audit logs asynchronously (non-blocking)",
    )

    # =========================================================================
    # API KEYS
    # =========================================================================

    api_keys_enabled: bool = Field(
        default=True,
        description="Enable API key authentication",
    )

    # =========================================================================
    # RATE LIMITING
    # =========================================================================

    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable rate limiting",
    )
    rate_limit_default: int = Field(
        default=100,
        description="Default requests per minute per client",
    )
    rate_limit_backend: Literal["memory", "supabase"] = Field(
        default="memory",
        description="Rate limit storage backend",
    )

    # =========================================================================
    # COMPUTED PROPERTIES
    # =========================================================================

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_local(self) -> bool:
        return self.environment == "local"

    @property
    def security_supabase_url(self) -> str | None:
        """Get active Security Supabase URL based on environment."""
        if self.environment == "production":
            return self.security_prod_supabase_url
        elif self.environment == "development":
            return self.security_dev_supabase_url
        return None

    @property
    def security_supabase_key(self) -> str | None:
        """Get active Security Supabase service key based on environment."""
        if self.environment == "production":
            return self.security_prod_supabase_service_key
        elif self.environment == "development":
            return self.security_dev_supabase_service_key
        return None


@lru_cache
def get_security_config() -> SecurityConfig:
    """Get cached security config instance."""
    return SecurityConfig()


# Global instance
security_config = get_security_config()
```

### 2.3 Data Models

**File**: `src/shared/security/models.py`

```python
"""
Security data models.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class UserContext:
    """
    Authenticated user context extracted from trusted headers.

    This represents the full RBAC context for the current user,
    as resolved by unified-ui and passed via X-Trusted-User-* headers.
    """
    # Level 1: Identity
    id: str
    email: str
    name: str | None = None
    profile: str | None = None  # system_admin, sales_manager, etc.

    # Level 1+2: Permissions
    permissions: list[str] = field(default_factory=list)
    permission_sets: list[str] = field(default_factory=list)

    # Level 3: Teams & Hierarchy
    teams: list[dict] = field(default_factory=list)
    team_ids: list[int] = field(default_factory=list)
    manager_id: str | None = None
    subordinate_ids: list[str] = field(default_factory=list)

    # Level 4: Sharing
    sharing_rules: list[dict] = field(default_factory=list)
    shared_records: dict[str, list[str]] = field(default_factory=dict)
    shared_from_user_ids: list[str] = field(default_factory=list)

    # Level 5: Companies
    companies: list[str] = field(default_factory=list)

    def has_permission(self, required: str) -> bool:
        """Check if user has a specific permission (supports wildcards)."""
        from .rbac import matches_permission
        return any(matches_permission(p, required) for p in self.permissions)

    def can_access_company(self, company: str) -> bool:
        """Check if user can access a specific company schema."""
        return company in self.companies

    def is_admin(self) -> bool:
        """Check if user has admin profile."""
        return self.profile == "system_admin"


@dataclass
class ServiceContext:
    """
    Service context for inter-service authentication.
    """
    service_name: str
    issued_at: datetime
    expires_at: datetime


@dataclass
class APIKeyInfo:
    """
    Validated API key information.
    """
    id: str
    name: str
    scopes: list[str]
    rate_limit_per_minute: int
    rate_limit_per_day: int
    organization: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_scope(self, scope: str) -> bool:
        """Check if key has a specific scope."""
        if "admin" in self.scopes:
            return True
        if scope == "read" and "write" in self.scopes:
            return True
        return scope in self.scopes


@dataclass
class AuditEvent:
    """
    Structured audit event for compliance logging.
    """
    # Who
    actor_type: str  # 'user', 'service', 'system', 'anonymous'
    actor_id: str | None = None
    actor_email: str | None = None
    actor_ip: str | None = None

    # What
    service: str = ""
    action: str = ""  # 'create', 'read', 'update', 'delete', 'login', etc.
    resource_type: str | None = None
    resource_id: str | None = None

    # Result
    result: str = "success"  # 'success', 'denied', 'error'
    error_message: str | None = None

    # Context
    request_id: str | None = None
    request_method: str | None = None
    request_path: str | None = None
    request_body: dict | None = None
    response_status: int | None = None
    duration_ms: int | None = None

    # Additional
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RateLimitInfo:
    """
    Rate limit status information.
    """
    limit: int
    remaining: int
    reset_at: int  # Unix timestamp
    retry_after: int | None = None  # Seconds until reset (if exceeded)
```

### 2.4 Exceptions

**File**: `src/shared/security/exceptions.py`

```python
"""Security-related exceptions."""


class SecurityError(Exception):
    """Base security exception."""
    pass


class AuthenticationError(SecurityError):
    """Authentication failed."""
    pass


class AuthorizationError(SecurityError):
    """Authorization denied."""
    pass


class ServiceAuthError(SecurityError):
    """Inter-service authentication error."""
    pass


class RateLimitError(SecurityError):
    """Rate limit exceeded."""
    pass
```

### 2.5 Trusted Headers Parser

**File**: `src/shared/security/trusted_headers.py`

```python
"""
Parse trusted user context from gateway headers.

The unified-ui gateway validates the user's JWT against UI Supabase,
resolves the full 5-level RBAC context, and passes it via headers.
Backend services trust these headers after validating X-Proxy-Secret.
"""

import json
import logging
import hmac
from typing import Any

from fastapi import Request

from .config import security_config
from .models import UserContext

logger = logging.getLogger(__name__)

# Header names (matching unified-ui)
HEADER_PROXY_SECRET = "X-Proxy-Secret"
HEADER_USER_ID = "X-Trusted-User-Id"
HEADER_USER_EMAIL = "X-Trusted-User-Email"
HEADER_USER_NAME = "X-Trusted-User-Name"
HEADER_USER_PROFILE = "X-Trusted-User-Profile"
HEADER_USER_PERMISSIONS = "X-Trusted-User-Permissions"
HEADER_USER_PERMISSION_SETS = "X-Trusted-User-Permission-Sets"
HEADER_USER_TEAMS = "X-Trusted-User-Teams"
HEADER_USER_TEAM_IDS = "X-Trusted-User-Team-Ids"
HEADER_USER_MANAGER_ID = "X-Trusted-User-Manager-Id"
HEADER_USER_SUBORDINATE_IDS = "X-Trusted-User-Subordinate-Ids"
HEADER_USER_SHARING_RULES = "X-Trusted-User-Sharing-Rules"
HEADER_USER_SHARED_RECORDS = "X-Trusted-User-Shared-Records"
HEADER_USER_SHARED_FROM_USER_IDS = "X-Trusted-User-Shared-From-User-Ids"
HEADER_USER_COMPANIES = "X-Trusted-User-Companies"


def _safe_json_parse(value: str | None, default: Any = None) -> Any:
    """Safely parse JSON from header value."""
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse JSON header: {value[:100]}...")
        return default


def verify_proxy_secret(request: Request) -> bool:
    """
    Verify the request came from a trusted proxy (unified-ui).

    Returns True if:
    - proxy_secret is not configured (local development)
    - X-Proxy-Secret header matches configured secret
    """
    if not security_config.proxy_secret:
        # Not configured - allow (local development)
        return True

    header_secret = request.headers.get(HEADER_PROXY_SECRET)

    if not header_secret:
        logger.warning("[SECURITY] Missing X-Proxy-Secret header")
        return False

    # Constant-time comparison to prevent timing attacks
    return hmac.compare_digest(header_secret, security_config.proxy_secret)


def parse_user_context(request: Request) -> UserContext | None:
    """
    Parse user context from trusted gateway headers.

    Returns None if no user context is present (unauthenticated request).
    Does NOT verify proxy secret - call verify_proxy_secret() first.
    """
    # Normalize header names to lowercase for case-insensitive lookup
    headers = {k.lower(): v for k, v in request.headers.items()}

    user_id = headers.get(HEADER_USER_ID.lower())
    if not user_id:
        return None

    return UserContext(
        # Level 1: Identity
        id=user_id,
        email=headers.get(HEADER_USER_EMAIL.lower(), ""),
        name=headers.get(HEADER_USER_NAME.lower()),
        profile=headers.get(HEADER_USER_PROFILE.lower()),

        # Level 1+2: Permissions
        permissions=_safe_json_parse(
            headers.get(HEADER_USER_PERMISSIONS.lower()), []
        ),
        permission_sets=_safe_json_parse(
            headers.get(HEADER_USER_PERMISSION_SETS.lower()), []
        ),

        # Level 3: Teams & Hierarchy
        teams=_safe_json_parse(
            headers.get(HEADER_USER_TEAMS.lower()), []
        ),
        team_ids=_safe_json_parse(
            headers.get(HEADER_USER_TEAM_IDS.lower()), []
        ),
        manager_id=headers.get(HEADER_USER_MANAGER_ID.lower()),
        subordinate_ids=_safe_json_parse(
            headers.get(HEADER_USER_SUBORDINATE_IDS.lower()), []
        ),

        # Level 4: Sharing
        sharing_rules=_safe_json_parse(
            headers.get(HEADER_USER_SHARING_RULES.lower()), []
        ),
        shared_records=_safe_json_parse(
            headers.get(HEADER_USER_SHARED_RECORDS.lower()), {}
        ),
        shared_from_user_ids=_safe_json_parse(
            headers.get(HEADER_USER_SHARED_FROM_USER_IDS.lower()), []
        ),

        # Level 5: Companies
        companies=_safe_json_parse(
            headers.get(HEADER_USER_COMPANIES.lower()), []
        ),
    )


def get_user_context(request: Request) -> UserContext | None:
    """
    Get user context from request, verifying proxy trust.

    This is the main entry point for getting authenticated user info.
    Returns None if:
    - Proxy secret verification fails (untrusted request)
    - No user headers present (unauthenticated)
    """
    if security_config.trust_proxy_headers:
        if not verify_proxy_secret(request):
            logger.warning(
                f"[SECURITY] Proxy secret verification failed for {request.url.path}"
            )
            return None

    return parse_user_context(request)
```

### 2.6 RBAC Utilities

**File**: `src/shared/security/rbac.py`

```python
"""
Role-based access control utilities.

Permission format: {module}:{resource}:{action}
Examples:
- sales:proposals:create
- assets:locations:read
- *:*:* (full admin)
- sales:*:* (all sales permissions)
"""

import logging

logger = logging.getLogger(__name__)


def matches_permission(user_permission: str, required: str) -> bool:
    """
    Check if a user permission matches a required permission.

    Supports wildcards:
    - "*:*:*" matches everything
    - "sales:*:*" matches all sales permissions
    - "sales:proposals:*" matches all proposal actions
    - ":manage" action implies all other actions

    Args:
        user_permission: Permission the user has
        required: Permission being checked

    Returns:
        True if user_permission grants access to required
    """
    # Exact match
    if user_permission == required:
        return True

    # Full wildcard
    if user_permission == "*:*:*":
        return True

    user_parts = user_permission.split(":")
    required_parts = required.split(":")

    # Must have 3 parts (module:resource:action)
    if len(user_parts) != 3 or len(required_parts) != 3:
        return False

    for i, (user_part, required_part) in enumerate(zip(user_parts, required_parts)):
        # Wildcard matches anything
        if user_part == "*":
            continue

        # "manage" action implies all other actions
        if i == 2 and user_part == "manage":
            return True

        # Must match exactly
        if user_part != required_part:
            return False

    return True


def has_permission(permissions: list[str], required: str) -> bool:
    """
    Check if any permission in the list grants access to required.
    """
    return any(matches_permission(p, required) for p in permissions)


def has_any_permission(permissions: list[str], required: list[str]) -> bool:
    """
    Check if any permission grants access to any required permission.
    """
    return any(has_permission(permissions, r) for r in required)


def has_all_permissions(permissions: list[str], required: list[str]) -> bool:
    """
    Check if permissions grant access to ALL required permissions.
    """
    return all(has_permission(permissions, r) for r in required)


# Common permission patterns
PERMISSIONS = {
    # Asset Management
    "assets:networks:read": "View networks",
    "assets:networks:create": "Create networks",
    "assets:networks:update": "Update networks",
    "assets:networks:delete": "Delete networks",
    "assets:locations:read": "View locations",
    "assets:locations:create": "Create locations",
    "assets:locations:update": "Update locations",
    "assets:locations:delete": "Delete locations",
    "assets:packages:read": "View packages",
    "assets:packages:create": "Create packages",
    "assets:packages:update": "Update packages",
    "assets:packages:delete": "Delete packages",
    "assets:asset_types:read": "View asset types",
    "assets:asset_types:create": "Create asset types",
    "assets:asset_types:update": "Update asset types",
    "assets:asset_types:delete": "Delete asset types",

    # Sales Module
    "sales:proposals:read": "View proposals",
    "sales:proposals:create": "Create proposals",
    "sales:proposals:update": "Update proposals",
    "sales:proposals:delete": "Delete proposals",
    "sales:bookings:read": "View bookings",
    "sales:bookings:create": "Create bookings",
    "sales:bookings:update": "Update bookings",
    "sales:rate_cards:read": "View rate cards",
    "sales:rate_cards:manage": "Manage rate cards",

    # Admin
    "admin:users:read": "View users",
    "admin:users:manage": "Manage users",
    "admin:audit:read": "View audit logs",
}
```

### 2.7 FastAPI Dependencies

**File**: `src/shared/security/dependencies.py`

```python
"""
FastAPI dependencies for authentication and authorization.

Usage:
    from shared.security import require_auth, require_permission

    @router.get("/protected")
    async def protected_endpoint(user: UserContext = Depends(require_auth)):
        return {"user_id": user.id}

    @router.post("/locations")
    async def create_location(
        user: UserContext = Depends(require_permission("assets:locations:create"))
    ):
        return {"created_by": user.id}
"""

import logging
from typing import Callable

from fastapi import Depends, HTTPException, Request, status

from .models import UserContext
from .trusted_headers import get_user_context
from .rbac import has_permission, has_any_permission

logger = logging.getLogger(__name__)


async def get_current_user(request: Request) -> UserContext | None:
    """
    Get current user from trusted headers.
    Returns None if not authenticated.
    """
    return get_user_context(request)


async def require_auth(
    request: Request,
    user: UserContext | None = Depends(get_current_user),
) -> UserContext:
    """
    Require authentication.
    Raises 401 if not authenticated.
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_permission(permission: str) -> Callable:
    """
    Factory for requiring a specific permission.

    Usage:
        @router.post("/locations")
        async def create_location(
            user: UserContext = Depends(require_permission("assets:locations:create"))
        ):
            ...
    """
    async def _require_permission(
        request: Request,
        user: UserContext = Depends(require_auth),
    ) -> UserContext:
        if not has_permission(user.permissions, permission):
            logger.warning(
                f"[RBAC] User {user.id} ({user.email}) denied: missing {permission}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}",
            )
        return user

    return _require_permission


def require_any_permission(permissions: list[str]) -> Callable:
    """
    Factory for requiring any of the specified permissions.
    """
    async def _require_any_permission(
        request: Request,
        user: UserContext = Depends(require_auth),
    ) -> UserContext:
        if not has_any_permission(user.permissions, permissions):
            logger.warning(
                f"[RBAC] User {user.id} ({user.email}) denied: missing any of {permissions}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: requires one of {permissions}",
            )
        return user

    return _require_any_permission


def require_profile(profile_name: str) -> Callable:
    """
    Factory for requiring a specific profile.
    """
    async def _require_profile(
        request: Request,
        user: UserContext = Depends(require_auth),
    ) -> UserContext:
        if user.profile != profile_name:
            logger.warning(
                f"[RBAC] User {user.id} ({user.email}) denied: not {profile_name}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Profile required: {profile_name}",
            )
        return user

    return _require_profile


def require_company_access(company_param: str = "company") -> Callable:
    """
    Factory for verifying user can access a specific company.

    Usage:
        @router.get("/locations/{company}")
        async def get_locations(
            company: str,
            user: UserContext = Depends(require_company_access("company"))
        ):
            ...
    """
    async def _require_company_access(
        request: Request,
        user: UserContext = Depends(require_auth),
    ) -> UserContext:
        # Get company from path parameters
        company = request.path_params.get(company_param)

        if company and not user.can_access_company(company):
            logger.warning(
                f"[RBAC] User {user.id} ({user.email}) denied: no access to {company}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to company: {company}",
            )
        return user

    return _require_company_access


# Convenience combinations
async def require_admin(
    user: UserContext = Depends(require_auth),
) -> UserContext:
    """Require system admin profile."""
    if not user.is_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
```

### 2.8 Inter-Service Authentication

**File**: `src/shared/security/service_auth.py`

```python
"""
Inter-service authentication using short-lived JWT tokens.

Usage (caller):
    from shared.security import ServiceAuthClient

    client = ServiceAuthClient()
    headers = client.get_auth_headers()
    response = httpx.get("http://asset-management:8001/api/v1/locations", headers=headers)

Usage (receiver):
    from shared.security import verify_service_token

    @router.get("/internal/data")
    async def internal_endpoint(service: str = Depends(verify_service_token)):
        return {"called_by": service}
"""

import logging
from datetime import datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request, status

from .config import security_config

logger = logging.getLogger(__name__)


class ServiceAuthClient:
    """
    Client for making authenticated inter-service requests.
    """

    def __init__(self, service_name: str | None = None):
        """
        Initialize service auth client.

        Args:
            service_name: Override service name (defaults to config)
        """
        self.service_name = service_name or security_config.service_name
        self.secret = security_config.inter_service_secret
        self.expiry = security_config.service_token_expiry_seconds

    def generate_token(self) -> str:
        """
        Generate a short-lived JWT for this service.

        Returns:
            JWT token string

        Raises:
            ValueError: If inter_service_secret not configured
        """
        if not self.secret:
            raise ValueError(
                "INTER_SERVICE_SECRET not configured. "
                "Set this environment variable for service-to-service auth."
            )

        now = datetime.utcnow()
        payload = {
            "service": self.service_name,
            "iat": now,
            "exp": now + timedelta(seconds=self.expiry),
            "type": "service",
        }

        return jwt.encode(payload, self.secret, algorithm="HS256")

    def get_auth_headers(self) -> dict[str, str]:
        """
        Get headers for authenticated inter-service request.

        Returns:
            Dict with Authorization and X-Service-Name headers
        """
        return {
            "Authorization": f"Bearer {self.generate_token()}",
            "X-Service-Name": self.service_name,
        }


def verify_service_token(request: Request) -> str:
    """
    Verify inter-service JWT token from request.

    Use as FastAPI dependency for internal endpoints:

        @router.get("/internal/data")
        async def internal_data(service: str = Depends(verify_service_token)):
            return {"caller": service}

    Returns:
        Service name from token (e.g., "sales-module")

    Raises:
        HTTPException: If token is missing, invalid, or expired
    """
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    token = auth_header[7:]  # Remove "Bearer " prefix

    if not security_config.inter_service_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Inter-service auth not configured",
        )

    try:
        payload = jwt.decode(
            token,
            security_config.inter_service_secret,
            algorithms=["HS256"],
        )

        # Verify this is a service token
        if payload.get("type") != "service":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        service_name = payload.get("service")
        if not service_name:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing service name in token",
            )

        logger.debug(f"[SERVICE AUTH] Verified token from: {service_name}")
        return service_name

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Service token expired",
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"[SERVICE AUTH] Invalid token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service token",
        )


async def require_service_auth(
    service: str = Depends(verify_service_token),
) -> str:
    """
    Alias for verify_service_token for clearer intent.
    """
    return service


def require_service(allowed_services: list[str]):
    """
    Factory for requiring specific services.

    Usage:
        @router.get("/internal/sensitive")
        async def sensitive_data(
            service: str = Depends(require_service(["sales-module"]))
        ):
            ...
    """
    async def _require_service(
        service: str = Depends(verify_service_token),
    ) -> str:
        if service not in allowed_services:
            logger.warning(
                f"[SERVICE AUTH] Service {service} not allowed to access this endpoint"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Service {service} not authorized for this endpoint",
            )
        return service

    return _require_service
```

### 2.9 Audit Logging

**File**: `src/shared/security/audit.py`

```python
"""
Structured audit logging to Security Supabase.

Usage:
    from shared.security import create_audit_logger

    audit_logger = create_audit_logger("asset-management")

    # Log an event
    audit_logger.log(
        actor_type="user",
        actor_id=user.id,
        action="create",
        resource_type="location",
        resource_id="LOC-001",
    )

    # Or use context manager
    with audit_logger.track(request, user) as audit:
        # ... do work ...
        audit.resource_type = "location"
        audit.resource_id = created_location.id
"""

import asyncio
import logging
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from fastapi import Request

from .config import security_config
from .models import AuditEvent, UserContext

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Audit logger that writes to Security Supabase.
    """

    def __init__(self, service_name: str):
        """
        Initialize audit logger for a service.

        Args:
            service_name: Name of the service (e.g., "asset-management")
        """
        self.service_name = service_name
        self._client = None
        self._initialized = False

    def _get_client(self):
        """Lazy-load Supabase client."""
        if self._client is not None:
            return self._client

        url = security_config.security_supabase_url
        key = security_config.security_supabase_key

        if not url or not key:
            logger.debug("[AUDIT] Security Supabase not configured, logging locally only")
            return None

        try:
            from supabase import create_client
            self._client = create_client(url, key)
            self._initialized = True
            logger.info("[AUDIT] Connected to Security Supabase")
            return self._client
        except Exception as e:
            logger.warning(f"[AUDIT] Failed to connect to Security Supabase: {e}")
            return None

    def log(
        self,
        actor_type: str,
        action: str,
        actor_id: str | None = None,
        actor_email: str | None = None,
        actor_ip: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        result: str = "success",
        error_message: str | None = None,
        request_id: str | None = None,
        request_method: str | None = None,
        request_path: str | None = None,
        request_body: dict | None = None,
        response_status: int | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Log an audit event.

        Args:
            actor_type: 'user', 'service', 'system', 'anonymous'
            action: 'create', 'read', 'update', 'delete', etc.
            ... other fields as documented
        """
        if not security_config.audit_enabled:
            return

        event = AuditEvent(
            actor_type=actor_type,
            actor_id=actor_id,
            actor_email=actor_email,
            actor_ip=actor_ip,
            service=self.service_name,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            error_message=error_message,
            request_id=request_id,
            request_method=request_method,
            request_path=request_path,
            request_body=request_body if security_config.audit_log_request_body else None,
            response_status=response_status,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )

        # Always log locally
        log_msg = (
            f"AUDIT: {actor_type}:{actor_id or 'unknown'} "
            f"{action} {resource_type or ''}:{resource_id or ''} "
            f"-> {result}"
        )
        if result == "success":
            logger.info(log_msg)
        elif result == "denied":
            logger.warning(log_msg)
        else:
            logger.error(log_msg)

        # Write to Supabase
        if security_config.audit_async:
            # Fire-and-forget async write
            try:
                asyncio.create_task(self._write_to_supabase(event))
            except RuntimeError:
                # No event loop running, write synchronously
                self._write_to_supabase_sync(event)
        else:
            # Synchronous write (blocks)
            self._write_to_supabase_sync(event)

    async def _write_to_supabase(self, event: AuditEvent) -> None:
        """Async write to Supabase."""
        try:
            client = self._get_client()
            if not client:
                return

            data = {
                "timestamp": event.timestamp.isoformat(),
                "actor_type": event.actor_type,
                "actor_id": event.actor_id,
                "actor_email": event.actor_email,
                "actor_ip": event.actor_ip,
                "service": event.service,
                "action": event.action,
                "resource_type": event.resource_type,
                "resource_id": event.resource_id,
                "result": event.result,
                "error_message": event.error_message,
                "request_id": event.request_id,
                "request_method": event.request_method,
                "request_path": event.request_path,
                "request_body": event.request_body,
                "response_status": event.response_status,
                "duration_ms": event.duration_ms,
                "metadata": event.metadata,
            }

            client.table("audit_logs").insert(data).execute()

        except Exception as e:
            logger.error(f"[AUDIT] Failed to write to Supabase: {e}")

    def _write_to_supabase_sync(self, event: AuditEvent) -> None:
        """Sync write to Supabase."""
        try:
            client = self._get_client()
            if not client:
                return

            data = {
                "timestamp": event.timestamp.isoformat(),
                "actor_type": event.actor_type,
                "actor_id": event.actor_id,
                "actor_email": event.actor_email,
                "actor_ip": event.actor_ip,
                "service": event.service,
                "action": event.action,
                "resource_type": event.resource_type,
                "resource_id": event.resource_id,
                "result": event.result,
                "error_message": event.error_message,
                "request_id": event.request_id,
                "request_method": event.request_method,
                "request_path": event.request_path,
                "request_body": event.request_body,
                "response_status": event.response_status,
                "duration_ms": event.duration_ms,
                "metadata": event.metadata,
            }

            client.table("audit_logs").insert(data).execute()

        except Exception as e:
            logger.error(f"[AUDIT] Failed to write to Supabase: {e}")

    @contextmanager
    def track(self, request: Request, user: UserContext | None = None):
        """
        Context manager for tracking a request.

        Usage:
            with audit_logger.track(request, user) as audit:
                # ... do work ...
                audit.resource_type = "location"
                audit.resource_id = "LOC-001"
        """
        start_time = time.time()
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

        # Mutable audit event
        audit = AuditEvent(
            actor_type="user" if user else "anonymous",
            actor_id=user.id if user else None,
            actor_email=user.email if user else None,
            actor_ip=request.client.host if request.client else None,
            service=self.service_name,
            action=request.method.lower(),
            request_id=request_id,
            request_method=request.method,
            request_path=str(request.url.path),
        )

        try:
            yield audit
            audit.result = "success"
        except Exception as e:
            audit.result = "error"
            audit.error_message = str(e)
            raise
        finally:
            audit.duration_ms = int((time.time() - start_time) * 1000)
            self.log(
                actor_type=audit.actor_type,
                actor_id=audit.actor_id,
                actor_email=audit.actor_email,
                actor_ip=audit.actor_ip,
                action=audit.action,
                resource_type=audit.resource_type,
                resource_id=audit.resource_id,
                result=audit.result,
                error_message=audit.error_message,
                request_id=audit.request_id,
                request_method=audit.request_method,
                request_path=audit.request_path,
                response_status=audit.response_status,
                duration_ms=audit.duration_ms,
                metadata=audit.metadata,
            )


def create_audit_logger(service_name: str) -> AuditLogger:
    """Create an audit logger for a specific service."""
    return AuditLogger(service_name)
```

### 2.10 Security Middleware

**File**: `src/shared/security/middleware.py`

```python
"""
FastAPI security middleware.

Usage:
    from shared.security.middleware import SecurityMiddleware

    app = FastAPI()
    app.add_middleware(SecurityMiddleware, service_name="asset-management")
"""

import time
import uuid
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .config import security_config
from .audit import create_audit_logger
from .trusted_headers import get_user_context

logger = logging.getLogger(__name__)


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Comprehensive security middleware for FastAPI.

    Features:
    - Request ID injection (X-Request-ID)
    - Request timing (X-Response-Time)
    - Security headers
    - Automatic audit logging
    """

    def __init__(self, app, service_name: str):
        super().__init__(app)
        self.service_name = service_name
        self.audit = create_audit_logger(service_name)

    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        # Start timing
        start_time = time.time()

        # Get user context (may be None)
        user = get_user_context(request)

        # Determine actor
        if user:
            actor_type = "user"
            actor_id = user.id
            actor_email = user.email
        else:
            service_header = request.headers.get("X-Service-Name")
            if service_header:
                actor_type = "service"
                actor_id = service_header
                actor_email = None
            else:
                actor_type = "anonymous"
                actor_id = None
                actor_email = None

        # Process request
        response = None
        result = "success"
        try:
            response = await call_next(request)
            if response.status_code >= 400:
                result = "error"
        except Exception:
            result = "error"
            raise
        finally:
            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)

            # Log to audit (skip health checks)
            if not request.url.path.endswith("/health"):
                self.audit.log(
                    actor_type=actor_type,
                    actor_id=actor_id,
                    actor_email=actor_email,
                    actor_ip=request.client.host if request.client else None,
                    action=request.method.lower(),
                    result=result,
                    request_id=request_id,
                    request_method=request.method,
                    request_path=str(request.url.path),
                    response_status=response.status_code if response else 500,
                    duration_ms=duration_ms,
                )

        # Add response headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        if security_config.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        return response
```

### 2.11 Module Exports

**File**: `src/shared/security/__init__.py`

```python
"""
Shared Security Module

Provides consistent security patterns across all services:
- Trusted header parsing (from unified-ui gateway)
- RBAC permission checking
- Inter-service JWT authentication
- Audit logging to Security Supabase
- FastAPI middleware and dependencies

Usage:
    from shared.security import (
        require_auth,
        require_permission,
        UserContext,
        create_audit_logger,
    )

    @router.get("/protected")
    async def protected(user: UserContext = Depends(require_auth)):
        audit_logger.log(
            actor_type="user",
            actor_id=user.id,
            action="read",
            resource_type="data",
        )
        return {"user": user.id}
"""

from .config import security_config, SecurityConfig, get_security_config
from .models import UserContext, ServiceContext, APIKeyInfo, AuditEvent, RateLimitInfo
from .exceptions import (
    SecurityError,
    AuthenticationError,
    AuthorizationError,
    ServiceAuthError,
    RateLimitError,
)
from .trusted_headers import (
    get_user_context,
    parse_user_context,
    verify_proxy_secret,
)
from .rbac import (
    matches_permission,
    has_permission,
    has_any_permission,
    has_all_permissions,
    PERMISSIONS,
)
from .dependencies import (
    get_current_user,
    require_auth,
    require_permission,
    require_any_permission,
    require_profile,
    require_company_access,
    require_admin,
)
from .service_auth import (
    ServiceAuthClient,
    verify_service_token,
    require_service_auth,
    require_service,
)
from .audit import AuditLogger, create_audit_logger
from .middleware import SecurityMiddleware

__all__ = [
    # Config
    "security_config",
    "SecurityConfig",
    "get_security_config",
    # Models
    "UserContext",
    "ServiceContext",
    "APIKeyInfo",
    "AuditEvent",
    "RateLimitInfo",
    # Exceptions
    "SecurityError",
    "AuthenticationError",
    "AuthorizationError",
    "ServiceAuthError",
    "RateLimitError",
    # Trusted Headers
    "get_user_context",
    "parse_user_context",
    "verify_proxy_secret",
    # RBAC
    "matches_permission",
    "has_permission",
    "has_any_permission",
    "has_all_permissions",
    "PERMISSIONS",
    # Dependencies
    "get_current_user",
    "require_auth",
    "require_permission",
    "require_any_permission",
    "require_profile",
    "require_company_access",
    "require_admin",
    # Service Auth
    "ServiceAuthClient",
    "verify_service_token",
    "require_service_auth",
    "require_service",
    # Audit
    "AuditLogger",
    "create_audit_logger",
    # Middleware
    "SecurityMiddleware",
]
```

### 2.12 Shared Module Init

**File**: `src/shared/__init__.py`

```python
"""
Shared modules for CRM services.
"""
```

---

## Part 3: Asset-Management Integration

### 3.1 Update Server with Security Middleware

**File to modify**: `src/asset-management/api/server.py`

```python
"""
Asset Management API Server with Security Integration.
"""

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

import config
from api.routers import health, networks, asset_types, locations, packages, eligibility

# Import security middleware
from security.middleware import SecurityMiddleware

logger = config.get_logger("api.server")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""

    app = FastAPI(
        title="Asset Management API",
        description="Networks, locations, and packages management",
        version="1.0.0",
        docs_url="/docs" if config.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if config.ENVIRONMENT != "production" else None,
    )

    # Security middleware (MUST be first)
    app.add_middleware(SecurityMiddleware, service_name="asset-management")

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.get_cors_origins_list(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Request-ID"],
    )

    # Include routers
    app.include_router(health.router)
    app.include_router(networks.router)
    app.include_router(asset_types.router)
    app.include_router(locations.router)
    app.include_router(packages.router)
    app.include_router(eligibility.router)

    return app


app = create_app()
```

### 3.2 Update Locations Router with Auth

**File to modify**: `src/asset-management/api/routers/locations.py`

```python
"""
Locations API endpoints with authentication.
"""

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))

import config
from core.locations import (
    Location,
    LocationCreate,
    LocationUpdate,
    LocationService,
)
from security import (
    UserContext,
    require_auth,
    require_permission,
)

router = APIRouter(prefix="/api/v1/locations", tags=["Locations"])
logger = config.get_logger("api.routers.locations")

# Service singleton
_service = LocationService()


@router.get("")
def list_locations(
    companies: list[str] = Query(default=None),
    network_id: int | None = None,
    type_id: int | None = None,
    active_only: bool = True,
    include_eligibility: bool = False,
    user: UserContext = Depends(require_permission("assets:locations:read")),
) -> list[Location]:
    """
    List locations across companies.

    Requires: assets:locations:read permission
    """
    # Filter to user's accessible companies
    accessible = companies or user.companies
    filtered = [c for c in accessible if c in user.companies]

    if not filtered:
        return []

    return _service.list_locations(
        companies=filtered,
        network_id=network_id,
        type_id=type_id,
        active_only=active_only,
        include_eligibility=include_eligibility,
    )


@router.get("/by-key/{location_key}")
def get_location_by_key(
    location_key: str,
    companies: list[str] = Query(default=None),
    include_eligibility: bool = True,
    user: UserContext = Depends(require_permission("assets:locations:read")),
) -> Location:
    """
    Get a location by its key.

    Requires: assets:locations:read permission
    """
    accessible = companies or user.companies
    filtered = [c for c in accessible if c in user.companies]

    result = _service.get_location_by_key(location_key, filtered, include_eligibility)
    if not result:
        raise HTTPException(status_code=404, detail="Location not found")
    return result


@router.get("/{company}/{location_id}")
def get_location(
    company: str,
    location_id: int,
    include_eligibility: bool = True,
    user: UserContext = Depends(require_permission("assets:locations:read")),
) -> Location:
    """
    Get a specific location.

    Requires: assets:locations:read permission + company access
    """
    if not user.can_access_company(company):
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    result = _service.get_location(company, location_id, include_eligibility)
    if not result:
        raise HTTPException(status_code=404, detail="Location not found")
    return result


@router.post("/{company}")
def create_location(
    company: str,
    data: LocationCreate,
    user: UserContext = Depends(require_permission("assets:locations:create")),
) -> Location:
    """
    Create a new location.

    Requires: assets:locations:create permission + company access
    """
    if not user.can_access_company(company):
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.id} creating location in {company}")
    return _service.create_location(company, data, created_by=user.id)


@router.patch("/{company}/{location_id}")
def update_location(
    company: str,
    location_id: int,
    data: LocationUpdate,
    user: UserContext = Depends(require_permission("assets:locations:update")),
) -> Location:
    """
    Update a location.

    Requires: assets:locations:update permission + company access
    """
    if not user.can_access_company(company):
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.id} updating location {location_id} in {company}")
    result = _service.update_location(company, location_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Location not found")
    return result


@router.delete("/{company}/{location_id}")
def delete_location(
    company: str,
    location_id: int,
    user: UserContext = Depends(require_permission("assets:locations:delete")),
) -> dict:
    """
    Soft delete a location.

    Requires: assets:locations:delete permission + company access
    """
    if not user.can_access_company(company):
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.id} deleting location {location_id} in {company}")
    success = _service.delete_location(company, location_id)
    if not success:
        raise HTTPException(status_code=404, detail="Location not found")
    return {"deleted": True}
```

### 3.3 Update Networks Router with Auth

**File to modify**: `src/asset-management/api/routers/networks.py`

```python
"""
Networks API endpoints with authentication.
"""

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))

import config
from core.networks import (
    Network,
    NetworkCreate,
    NetworkUpdate,
    NetworkService,
)
from security import (
    UserContext,
    require_permission,
)

router = APIRouter(prefix="/api/v1/networks", tags=["Networks"])
logger = config.get_logger("api.routers.networks")

# Service singleton
_service = NetworkService()


@router.get("")
def list_networks(
    companies: list[str] = Query(default=None),
    active_only: bool = True,
    include_eligibility: bool = False,
    user: UserContext = Depends(require_permission("assets:networks:read")),
) -> list[Network]:
    """
    List networks across companies.

    Requires: assets:networks:read permission
    """
    accessible = companies or user.companies
    filtered = [c for c in accessible if c in user.companies]

    if not filtered:
        return []

    return _service.list_networks(
        companies=filtered,
        active_only=active_only,
        include_eligibility=include_eligibility,
    )


@router.get("/{company}/{network_id}")
def get_network(
    company: str,
    network_id: int,
    include_eligibility: bool = True,
    user: UserContext = Depends(require_permission("assets:networks:read")),
) -> Network:
    """
    Get a specific network.

    Requires: assets:networks:read permission + company access
    """
    if not user.can_access_company(company):
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    result = _service.get_network(company, network_id, include_eligibility)
    if not result:
        raise HTTPException(status_code=404, detail="Network not found")
    return result


@router.post("/{company}")
def create_network(
    company: str,
    data: NetworkCreate,
    user: UserContext = Depends(require_permission("assets:networks:create")),
) -> Network:
    """
    Create a new network.

    Requires: assets:networks:create permission + company access
    """
    if not user.can_access_company(company):
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.id} creating network in {company}")
    return _service.create_network(company, data, created_by=user.id)


@router.patch("/{company}/{network_id}")
def update_network(
    company: str,
    network_id: int,
    data: NetworkUpdate,
    user: UserContext = Depends(require_permission("assets:networks:update")),
) -> Network:
    """
    Update a network.

    Requires: assets:networks:update permission + company access
    """
    if not user.can_access_company(company):
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.id} updating network {network_id} in {company}")
    result = _service.update_network(company, network_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Network not found")
    return result


@router.delete("/{company}/{network_id}")
def delete_network(
    company: str,
    network_id: int,
    user: UserContext = Depends(require_permission("assets:networks:delete")),
) -> dict:
    """
    Soft delete a network.

    Requires: assets:networks:delete permission + company access
    """
    if not user.can_access_company(company):
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.id} deleting network {network_id} in {company}")
    success = _service.delete_network(company, network_id)
    if not success:
        raise HTTPException(status_code=404, detail="Network not found")
    return {"deleted": True}
```

### 3.4 Update Packages Router with Auth

**File to modify**: `src/asset-management/api/routers/packages.py`

```python
"""
Packages API endpoints with authentication.
"""

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))

import config
from core.packages import (
    Package,
    PackageCreate,
    PackageUpdate,
    PackageService,
)
from security import (
    UserContext,
    require_permission,
)

router = APIRouter(prefix="/api/v1/packages", tags=["Packages"])
logger = config.get_logger("api.routers.packages")

# Service singleton
_service = PackageService()


@router.get("")
def list_packages(
    companies: list[str] = Query(default=None),
    active_only: bool = True,
    user: UserContext = Depends(require_permission("assets:packages:read")),
) -> list[Package]:
    """
    List packages across companies.

    Requires: assets:packages:read permission
    """
    accessible = companies or user.companies
    filtered = [c for c in accessible if c in user.companies]

    if not filtered:
        return []

    return _service.list_packages(
        companies=filtered,
        active_only=active_only,
    )


@router.get("/{company}/{package_id}")
def get_package(
    company: str,
    package_id: int,
    user: UserContext = Depends(require_permission("assets:packages:read")),
) -> Package:
    """
    Get a specific package with items.

    Requires: assets:packages:read permission + company access
    """
    if not user.can_access_company(company):
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    result = _service.get_package(company, package_id)
    if not result:
        raise HTTPException(status_code=404, detail="Package not found")
    return result


@router.post("/{company}")
def create_package(
    company: str,
    data: PackageCreate,
    user: UserContext = Depends(require_permission("assets:packages:create")),
) -> Package:
    """
    Create a new package.

    Requires: assets:packages:create permission + company access
    """
    if not user.can_access_company(company):
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.id} creating package in {company}")
    return _service.create_package(company, data, created_by=user.id)


@router.patch("/{company}/{package_id}")
def update_package(
    company: str,
    package_id: int,
    data: PackageUpdate,
    user: UserContext = Depends(require_permission("assets:packages:update")),
) -> Package:
    """
    Update a package.

    Requires: assets:packages:update permission + company access
    """
    if not user.can_access_company(company):
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.id} updating package {package_id} in {company}")
    result = _service.update_package(company, package_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Package not found")
    return result


@router.delete("/{company}/{package_id}")
def delete_package(
    company: str,
    package_id: int,
    user: UserContext = Depends(require_permission("assets:packages:delete")),
) -> dict:
    """
    Soft delete a package.

    Requires: assets:packages:delete permission + company access
    """
    if not user.can_access_company(company):
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.id} deleting package {package_id} in {company}")
    success = _service.delete_package(company, package_id)
    if not success:
        raise HTTPException(status_code=404, detail="Package not found")
    return {"deleted": True}
```

### 3.5 Update Asset Types Router with Auth

**File to modify**: `src/asset-management/api/routers/asset_types.py`

```python
"""
Asset Types API endpoints with authentication.
"""

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))

import config
from core.asset_types import (
    AssetType,
    AssetTypeCreate,
    AssetTypeUpdate,
    AssetTypeService,
)
from security import (
    UserContext,
    require_permission,
)

router = APIRouter(prefix="/api/v1/asset-types", tags=["Asset Types"])
logger = config.get_logger("api.routers.asset_types")

# Service singleton
_service = AssetTypeService()


@router.get("")
def list_asset_types(
    companies: list[str] = Query(default=None),
    network_id: int | None = None,
    active_only: bool = True,
    user: UserContext = Depends(require_permission("assets:asset_types:read")),
) -> list[AssetType]:
    """
    List asset types across companies.

    Requires: assets:asset_types:read permission
    """
    accessible = companies or user.companies
    filtered = [c for c in accessible if c in user.companies]

    if not filtered:
        return []

    return _service.list_asset_types(
        companies=filtered,
        network_id=network_id,
        active_only=active_only,
    )


@router.get("/{company}/{type_id}")
def get_asset_type(
    company: str,
    type_id: int,
    user: UserContext = Depends(require_permission("assets:asset_types:read")),
) -> AssetType:
    """
    Get a specific asset type.

    Requires: assets:asset_types:read permission + company access
    """
    if not user.can_access_company(company):
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    result = _service.get_asset_type(company, type_id)
    if not result:
        raise HTTPException(status_code=404, detail="Asset type not found")
    return result


@router.post("/{company}")
def create_asset_type(
    company: str,
    data: AssetTypeCreate,
    user: UserContext = Depends(require_permission("assets:asset_types:create")),
) -> AssetType:
    """
    Create a new asset type.

    Requires: assets:asset_types:create permission + company access
    """
    if not user.can_access_company(company):
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.id} creating asset type in {company}")
    return _service.create_asset_type(company, data, created_by=user.id)


@router.patch("/{company}/{type_id}")
def update_asset_type(
    company: str,
    type_id: int,
    data: AssetTypeUpdate,
    user: UserContext = Depends(require_permission("assets:asset_types:update")),
) -> AssetType:
    """
    Update an asset type.

    Requires: assets:asset_types:update permission + company access
    """
    if not user.can_access_company(company):
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.id} updating asset type {type_id} in {company}")
    result = _service.update_asset_type(company, type_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Asset type not found")
    return result


@router.delete("/{company}/{type_id}")
def delete_asset_type(
    company: str,
    type_id: int,
    user: UserContext = Depends(require_permission("assets:asset_types:delete")),
) -> dict:
    """
    Soft delete an asset type.

    Requires: assets:asset_types:delete permission + company access
    """
    if not user.can_access_company(company):
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    logger.info(f"User {user.id} deleting asset type {type_id} in {company}")
    success = _service.delete_asset_type(company, type_id)
    if not success:
        raise HTTPException(status_code=404, detail="Asset type not found")
    return {"deleted": True}
```

### 3.6 Update Eligibility Router with Auth

**File to modify**: `src/asset-management/api/routers/eligibility.py`

```python
"""
Eligibility endpoints with authentication.
"""

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))

import config
from core.eligibility import (
    EligibilityCheck,
    EligibilityService,
    BulkEligibilityItem,
)
from security import (
    UserContext,
    require_permission,
)

router = APIRouter(prefix="/api/v1/eligibility", tags=["Eligibility"])
logger = config.get_logger("api.routers.eligibility")

# Service singleton
_service = EligibilityService()


@router.get("/services")
def list_services(
    user: UserContext = Depends(require_permission("assets:locations:read")),
) -> list[str]:
    """List all services that have eligibility requirements."""
    return ["proposal_generator", "mockup_generator", "availability_calendar"]


@router.get("/requirements/{service}")
def get_service_requirements(
    service: str,
    user: UserContext = Depends(require_permission("assets:locations:read")),
) -> dict:
    """
    Get eligibility requirements for a specific service.

    Returns required fields for both locations and networks.
    """
    requirements = _service.get_requirements(service)
    if not requirements:
        raise HTTPException(status_code=404, detail=f"Unknown service: {service}")
    return requirements


@router.get("/check/{company}/{location_id}")
def check_location_eligibility(
    company: str,
    location_id: int,
    service: str | None = Query(default=None),
    user: UserContext = Depends(require_permission("assets:locations:read")),
) -> EligibilityCheck:
    """
    Check eligibility for a specific location.
    """
    if not user.can_access_company(company):
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    result = _service.check_location_eligibility(
        company=company,
        location_id=location_id,
        service=service,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Location not found")
    return result


@router.get("/check-network/{company}/{network_id}")
def check_network_eligibility(
    company: str,
    network_id: int,
    service: str | None = Query(default=None),
    user: UserContext = Depends(require_permission("assets:networks:read")),
) -> EligibilityCheck:
    """
    Check eligibility for a network.
    """
    if not user.can_access_company(company):
        raise HTTPException(status_code=403, detail=f"No access to company: {company}")

    result = _service.check_network_eligibility(
        company=company,
        network_id=network_id,
        service=service,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Network not found")
    return result


@router.post("/bulk-check")
def bulk_check_eligibility(
    items: list[dict],
    service: str = Query(...),
    user: UserContext = Depends(require_permission("assets:locations:read")),
) -> list[EligibilityCheck]:
    """
    Bulk check eligibility for multiple items.
    """
    # Filter items to user's accessible companies
    filtered_items = [
        item for item in items
        if user.can_access_company(item.get("company", ""))
    ]

    bulk_items = [
        BulkEligibilityItem(
            type=item.get("type", ""),
            company=item.get("company", ""),
            id=item.get("id", 0),
        )
        for item in filtered_items
    ]
    return _service.bulk_check_eligibility(items=bulk_items, service=service)


@router.get("/eligible-locations")
def get_eligible_locations(
    service: str = Query(...),
    companies: list[str] = Query(default=None),
    user: UserContext = Depends(require_permission("assets:locations:read")),
) -> list[dict]:
    """
    Get all locations eligible for a specific service.
    """
    accessible = companies or user.companies
    filtered = [c for c in accessible if c in user.companies]

    return _service.get_eligible_locations(
        service=service,
        companies=filtered,
    )


@router.get("/eligible-networks")
def get_eligible_networks(
    service: str = Query(...),
    companies: list[str] = Query(default=None),
    user: UserContext = Depends(require_permission("assets:networks:read")),
) -> list[dict]:
    """
    Get all networks that have at least one eligible location for a service.
    """
    accessible = companies or user.companies
    filtered = [c for c in accessible if c in user.companies]

    return _service.get_eligible_networks(
        service=service,
        companies=filtered,
    )
```

---

## Part 4: Unified-UI Gateway Updates

### 4.1 Add Asset-Management Proxy

**File to modify**: `src/unified-ui/server.js`

Add after the sales-module proxy configuration:

```javascript
// ============================================================================
// ASSET MANAGEMENT PROXY
// ============================================================================

const ASSET_MGMT_URL = process.env.ASSET_MGMT_URL || 'http://localhost:8001';

app.use('/api/assets', proxyAuthMiddleware, createProxyMiddleware({
  target: ASSET_MGMT_URL,
  changeOrigin: true,
  pathRewrite: (path) => '/api/v1' + path.replace('/api/assets', ''),
  proxyTimeout: 60000,
  timeout: 60000,
  on: {
    proxyReq: (proxyReq, req, res) => {
      // Inject trusted user headers (same as sales-module proxy)
      if (req.trustedUser) {
        if (PROXY_SECRET) {
          proxyReq.setHeader('X-Proxy-Secret', PROXY_SECRET);
        }

        proxyReq.setHeader('X-Trusted-User-Id', req.trustedUser.id);
        proxyReq.setHeader('X-Trusted-User-Email', req.trustedUser.email);
        proxyReq.setHeader('X-Trusted-User-Name', req.trustedUser.name || '');
        proxyReq.setHeader('X-Trusted-User-Profile', req.trustedUser.profile || '');
        proxyReq.setHeader('X-Trusted-User-Permissions', JSON.stringify(req.trustedUser.permissions || []));
        proxyReq.setHeader('X-Trusted-User-Permission-Sets', JSON.stringify(req.trustedUser.permissionSets || []));
        proxyReq.setHeader('X-Trusted-User-Teams', JSON.stringify(req.trustedUser.teams || []));
        proxyReq.setHeader('X-Trusted-User-Team-Ids', JSON.stringify(req.trustedUser.teamIds || []));
        if (req.trustedUser.managerId) {
          proxyReq.setHeader('X-Trusted-User-Manager-Id', req.trustedUser.managerId);
        }
        proxyReq.setHeader('X-Trusted-User-Subordinate-Ids', JSON.stringify(req.trustedUser.subordinateIds || []));
        proxyReq.setHeader('X-Trusted-User-Sharing-Rules', JSON.stringify(req.trustedUser.sharingRules || []));
        proxyReq.setHeader('X-Trusted-User-Shared-Records', JSON.stringify(req.trustedUser.sharedRecords || {}));
        proxyReq.setHeader('X-Trusted-User-Shared-From-User-Ids', JSON.stringify(req.trustedUser.sharedFromUserIds || []));
        proxyReq.setHeader('X-Trusted-User-Companies', JSON.stringify(req.trustedUser.companies || []));
      }

      // Forward IP
      const ip = req.headers['x-forwarded-for'] || req.socket.remoteAddress;
      if (ip) proxyReq.setHeader('X-Forwarded-For', ip);
    },
    error: (err, req, res) => {
      console.error(`[PROXY ERROR] Asset Management: ${err.message}`);
      if (!res.headersSent) {
        res.status(502).json({ error: 'Asset Management service unavailable' });
      }
    }
  }
}));

console.log(`[PROXY] Asset Management: /api/assets/* -> ${ASSET_MGMT_URL}`);
```

---

## Part 5: Sales-Module HTTP Client

### 5.1 Create Asset-Management Client

**File**: `src/sales-module/clients/__init__.py`

```python
from .asset_management import asset_mgmt_client

__all__ = ["asset_mgmt_client"]
```

**File**: `src/sales-module/clients/asset_management.py`

```python
"""
Secure HTTP client for Asset-Management service.

Uses short-lived JWT tokens for service-to-service authentication.
"""

import sys
from pathlib import Path
from typing import Any

import httpx

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

from security import ServiceAuthClient
from app_settings import settings


class AssetManagementClient:
    """
    HTTP client for asset-management service with JWT auth.

    Usage:
        from clients import asset_mgmt_client

        locations = asset_mgmt_client.get_locations(["backlite_dubai"])
        location = asset_mgmt_client.get_location("backlite_dubai", 123)
    """

    def __init__(self):
        self.base_url = settings.asset_mgmt_url or "http://localhost:8001"
        self.auth = ServiceAuthClient("sales-module")
        self.timeout = 30.0

    def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> dict[str, Any] | list[dict] | None:
        """Make authenticated request to asset-management."""
        headers = kwargs.pop("headers", {})
        headers.update(self.auth.get_auth_headers())

        try:
            response = httpx.request(
                method,
                f"{self.base_url}{endpoint}",
                headers=headers,
                timeout=self.timeout,
                **kwargs,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
        except httpx.RequestError as e:
            raise ConnectionError(f"Failed to connect to asset-management: {e}")

    # =========================================================================
    # LOCATIONS
    # =========================================================================

    def get_locations(
        self,
        companies: list[str],
        network_id: int | None = None,
    ) -> list[dict]:
        """Get locations for given companies."""
        params = {"companies": companies}
        if network_id:
            params["network_id"] = network_id
        return self._request("GET", "/api/v1/locations", params=params) or []

    def get_location(self, company: str, location_id: int) -> dict | None:
        """Get a specific location by ID."""
        return self._request("GET", f"/api/v1/locations/{company}/{location_id}")

    def get_location_by_key(
        self,
        location_key: str,
        companies: list[str],
    ) -> dict | None:
        """Get a location by its key."""
        return self._request(
            "GET",
            f"/api/v1/locations/by-key/{location_key}",
            params={"companies": companies},
        )

    # =========================================================================
    # NETWORKS
    # =========================================================================

    def get_networks(self, companies: list[str]) -> list[dict]:
        """Get networks for given companies."""
        return self._request(
            "GET",
            "/api/v1/networks",
            params={"companies": companies},
        ) or []

    def get_network(self, company: str, network_id: int) -> dict | None:
        """Get a specific network."""
        return self._request("GET", f"/api/v1/networks/{company}/{network_id}")

    # =========================================================================
    # ELIGIBILITY
    # =========================================================================

    def check_location_eligibility(
        self,
        company: str,
        location_id: int,
        service: str | None = None,
    ) -> dict:
        """Check if a location is eligible for a service."""
        params = {"service": service} if service else {}
        result = self._request(
            "GET",
            f"/api/v1/eligibility/check/{company}/{location_id}",
            params=params,
        )
        return result or {"eligible": False, "error": "Location not found"}

    def get_eligible_locations(
        self,
        service: str,
        companies: list[str],
    ) -> list[dict]:
        """Get all locations eligible for a service."""
        return self._request(
            "GET",
            "/api/v1/eligibility/eligible-locations",
            params={"service": service, "companies": companies},
        ) or []

    # =========================================================================
    # PACKAGES
    # =========================================================================

    def get_packages(self, companies: list[str]) -> list[dict]:
        """Get packages for given companies."""
        return self._request(
            "GET",
            "/api/v1/packages",
            params={"companies": companies},
        ) or []

    def expand_to_locations(self, items: list[dict]) -> list[dict]:
        """Expand packages/networks to flat list of locations."""
        return self._request(
            "POST",
            "/api/v1/locations/expand",
            json=items,
        ) or []


# Singleton instance
asset_mgmt_client = AssetManagementClient()
```

### 5.2 Update Sales-Module Settings

**Add to**: `src/sales-module/app_settings/settings.py`

Add these fields to the Settings class:

```python
    # =========================================================================
    # ASSET MANAGEMENT SERVICE
    # =========================================================================

    asset_mgmt_url: str | None = Field(
        default=None,
        description="Asset-management service URL for inter-service calls",
    )

    # =========================================================================
    # INTER-SERVICE AUTHENTICATION
    # =========================================================================

    inter_service_secret: str | None = Field(
        default=None,
        description="Shared secret for inter-service JWT tokens",
    )
    service_name: str = Field(
        default="sales-module",
        description="This service's name for JWT claims",
    )
```

---

## Part 6: Infrastructure Updates

### 6.1 Docker Compose

**Update**: `docker-compose.yaml`

```yaml
services:
  unified-ui:
    environment:
      - SALES_BOT_URL=http://sales-module:8000
      - ASSET_MGMT_URL=http://asset-management:8001
      - PROXY_SECRET=${PROXY_SECRET}

  sales-module:
    environment:
      # Existing vars...
      - ASSET_MGMT_URL=http://asset-management:8001
      - INTER_SERVICE_SECRET=${INTER_SERVICE_SECRET}
      - SERVICE_NAME=sales-module
      # Security Supabase
      - SECURITY_DEV_SUPABASE_URL=${SECURITY_DEV_SUPABASE_URL}
      - SECURITY_DEV_SUPABASE_SERVICE_KEY=${SECURITY_DEV_SUPABASE_SERVICE_KEY}
      - SECURITY_PROD_SUPABASE_URL=${SECURITY_PROD_SUPABASE_URL}
      - SECURITY_PROD_SUPABASE_SERVICE_KEY=${SECURITY_PROD_SUPABASE_SERVICE_KEY}
    volumes:
      - ./src/shared:/app/shared:ro

  asset-management:
    build:
      context: ./src/asset-management
    ports:
      - "8001:8001"
    environment:
      - ENVIRONMENT=${ENVIRONMENT:-local}
      - DB_BACKEND=${DB_BACKEND:-sqlite}
      - HOST=0.0.0.0
      - PORT=8001
      # Asset Supabase
      - ASSETMGMT_DEV_SUPABASE_URL=${ASSETMGMT_DEV_SUPABASE_URL}
      - ASSETMGMT_DEV_SUPABASE_SERVICE_KEY=${ASSETMGMT_DEV_SUPABASE_SERVICE_KEY}
      - ASSETMGMT_PROD_SUPABASE_URL=${ASSETMGMT_PROD_SUPABASE_URL}
      - ASSETMGMT_PROD_SUPABASE_SERVICE_KEY=${ASSETMGMT_PROD_SUPABASE_SERVICE_KEY}
      # Security
      - PROXY_SECRET=${PROXY_SECRET}
      - INTER_SERVICE_SECRET=${INTER_SERVICE_SECRET}
      - SERVICE_NAME=asset-management
      # Security Supabase
      - SECURITY_DEV_SUPABASE_URL=${SECURITY_DEV_SUPABASE_URL}
      - SECURITY_DEV_SUPABASE_SERVICE_KEY=${SECURITY_DEV_SUPABASE_SERVICE_KEY}
      - SECURITY_PROD_SUPABASE_URL=${SECURITY_PROD_SUPABASE_URL}
      - SECURITY_PROD_SUPABASE_SERVICE_KEY=${SECURITY_PROD_SUPABASE_SERVICE_KEY}
    volumes:
      - ./src/shared:/app/shared:ro
```

### 6.2 Environment Variables

**Update**: `.env.example`

```bash
# =============================================================================
# ENVIRONMENT
# =============================================================================
ENVIRONMENT=local  # local | development | production
DB_BACKEND=sqlite  # sqlite | supabase

# =============================================================================
# SECURITY (CRITICAL)
# =============================================================================
# Shared secret for unified-ui -> backend trust
PROXY_SECRET=  # Generate: openssl rand -hex 32

# Shared secret for service-to-service JWT
INTER_SERVICE_SECRET=  # Generate: openssl rand -hex 32

# =============================================================================
# UI SUPABASE (Auth/RBAC)
# =============================================================================
UI_DEV_SUPABASE_URL=
UI_DEV_SUPABASE_ANON_KEY=
UI_DEV_SUPABASE_SERVICE_KEY=
UI_PROD_SUPABASE_URL=
UI_PROD_SUPABASE_ANON_KEY=
UI_PROD_SUPABASE_SERVICE_KEY=

# =============================================================================
# SALES SUPABASE (Business Data)
# =============================================================================
SALESBOT_DEV_SUPABASE_URL=
SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY=
SALESBOT_PROD_SUPABASE_URL=
SALESBOT_PROD_SUPABASE_SERVICE_ROLE_KEY=

# =============================================================================
# ASSET MANAGEMENT SUPABASE (Asset Data)
# =============================================================================
ASSETMGMT_DEV_SUPABASE_URL=
ASSETMGMT_DEV_SUPABASE_SERVICE_KEY=
ASSETMGMT_PROD_SUPABASE_URL=
ASSETMGMT_PROD_SUPABASE_SERVICE_KEY=

# =============================================================================
# SECURITY SUPABASE (Audit Logs, API Keys) - NEW
# =============================================================================
SECURITY_DEV_SUPABASE_URL=
SECURITY_DEV_SUPABASE_ANON_KEY=
SECURITY_DEV_SUPABASE_SERVICE_KEY=
SECURITY_PROD_SUPABASE_URL=
SECURITY_PROD_SUPABASE_ANON_KEY=
SECURITY_PROD_SUPABASE_SERVICE_KEY=

# =============================================================================
# SERVICE URLS (Internal)
# =============================================================================
SALES_BOT_URL=http://localhost:8000
ASSET_MGMT_URL=http://localhost:8001
```

---

## Part 7: Implementation Order

### Phase 1: Security Foundation (Day 1)

| Step | Task | Files |
|------|------|-------|
| 1.1 | Create Security Supabase project | Supabase Dashboard |
| 1.2 | Run schema migration | `src/shared/security/migrations/001_initial_schema.sql` |
| 1.3 | Run seed data | `src/shared/security/migrations/002_seed_data.sql` |
| 1.4 | Create shared security module | `src/shared/security/*.py` (11 files) |
| 1.5 | Update .env with Security Supabase creds | `.env` |
| 1.6 | Generate PROXY_SECRET and INTER_SERVICE_SECRET | `.env` |

### Phase 2: Asset-Management Integration (Day 1-2)

| Step | Task | Files |
|------|------|-------|
| 2.1 | Update server.py with SecurityMiddleware | `src/asset-management/api/server.py` |
| 2.2 | Update all routers with auth dependencies | `src/asset-management/api/routers/*.py` |
| 2.3 | Test locally with trusted headers | Manual testing |

### Phase 3: Gateway Integration (Day 2)

| Step | Task | Files |
|------|------|-------|
| 3.1 | Add asset-management proxy to unified-ui | `src/unified-ui/server.js` |
| 3.2 | Test end-to-end auth flow | Manual testing |

### Phase 4: Service-to-Service Auth (Day 2-3)

| Step | Task | Files |
|------|------|-------|
| 4.1 | Create sales-module HTTP client | `src/sales-module/clients/asset_management.py` |
| 4.2 | Update sales-module settings | `src/sales-module/app_settings/settings.py` |
| 4.3 | Test inter-service calls | Manual testing |

### Phase 5: Infrastructure (Day 3)

| Step | Task | Files |
|------|------|-------|
| 5.1 | Update docker-compose.yaml | `docker-compose.yaml` |
| 5.2 | Update .env.example | `.env.example` |
| 5.3 | Update run_all_services.py | `run_all_services.py` |
| 5.4 | Full integration test | Manual testing |

---

## Summary

### Files to Create

| Path | Description |
|------|-------------|
| `src/shared/__init__.py` | Shared module init |
| `src/shared/security/__init__.py` | Security module exports |
| `src/shared/security/config.py` | Pydantic settings |
| `src/shared/security/models.py` | Data models |
| `src/shared/security/exceptions.py` | Exceptions |
| `src/shared/security/trusted_headers.py` | Header parsing |
| `src/shared/security/service_auth.py` | Inter-service JWT |
| `src/shared/security/rbac.py` | Permission checking |
| `src/shared/security/dependencies.py` | FastAPI dependencies |
| `src/shared/security/audit.py` | Audit logging |
| `src/shared/security/middleware.py` | Security middleware |
| `src/shared/security/migrations/001_initial_schema.sql` | Database schema |
| `src/shared/security/migrations/002_seed_data.sql` | Seed data |
| `src/sales-module/clients/__init__.py` | Clients module |
| `src/sales-module/clients/asset_management.py` | HTTP client |

### Files to Modify

| Path | Change |
|------|--------|
| `src/asset-management/api/server.py` | Add SecurityMiddleware |
| `src/asset-management/api/routers/locations.py` | Add auth dependencies |
| `src/asset-management/api/routers/networks.py` | Add auth dependencies |
| `src/asset-management/api/routers/packages.py` | Add auth dependencies |
| `src/asset-management/api/routers/asset_types.py` | Add auth dependencies |
| `src/asset-management/api/routers/eligibility.py` | Add auth dependencies |
| `src/unified-ui/server.js` | Add asset-management proxy |
| `src/sales-module/app_settings/settings.py` | Add ASSET_MGMT_URL, INTER_SERVICE_SECRET |
| `docker-compose.yaml` | Add asset-management service |
| `.env.example` | Document all env vars |

### New Environment Variables

| Variable | Purpose |
|----------|---------|
| `PROXY_SECRET` | Trusted proxy verification |
| `INTER_SERVICE_SECRET` | Service-to-service JWT signing |
| `SECURITY_DEV_SUPABASE_URL` | Security Supabase DEV URL |
| `SECURITY_DEV_SUPABASE_SERVICE_KEY` | Security Supabase DEV key |
| `SECURITY_PROD_SUPABASE_URL` | Security Supabase PROD URL |
| `SECURITY_PROD_SUPABASE_SERVICE_KEY` | Security Supabase PROD key |
| `ASSETMGMT_DEV_SUPABASE_URL` | Asset Supabase DEV URL |
| `ASSETMGMT_DEV_SUPABASE_SERVICE_KEY` | Asset Supabase DEV key |
| `ASSETMGMT_PROD_SUPABASE_URL` | Asset Supabase PROD URL |
| `ASSETMGMT_PROD_SUPABASE_SERVICE_KEY` | Asset Supabase PROD key |
| `ASSET_MGMT_URL` | Internal URL for asset-management |

---

## Architecture Assessment & Scaling Path

### Current Readiness Levels

```
┌─────────────────────────────────────────────────────────────────┐
│                    ARCHITECTURE READINESS                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Startup/SMB Scale:     ████████████████████░░░░  80% Ready     │
│  Enterprise Scale:      ████████░░░░░░░░░░░░░░░░  40% Ready     │
│  Compliance (SOC2/ISO): ██████░░░░░░░░░░░░░░░░░░  30% Ready     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Bottom Line:** This is a **solid foundation** using industry-standard patterns (API Gateway, trusted headers, short-lived JWTs). The architecture is correct and upgrades are additive, not rewrites.

---

### What's Solid (Industry-Standard Patterns)

| Pattern | Used By | Our Implementation |
|---------|---------|-------------------|
| API Gateway | Netflix Zuul, AWS API Gateway, Kong | unified-ui validates JWT, injects context |
| Trusted Headers | AWS ALB, GCP IAP, Cloudflare Access | X-Trusted-User-* headers with X-Proxy-Secret |
| Short-lived Service Tokens | OAuth2, mTLS | 60-second inter-service JWT via `ServiceAuthClient` |
| Centralized Auth Module | All microservices architectures | `src/shared/security/` imported by all services |
| RBAC with Wildcards | AWS IAM, K8s RBAC | `module:resource:action` with `*` support |

---

### Current Limitations & Security Concerns

| Issue | Severity | Current State | Risk | Enterprise Solution |
|-------|----------|---------------|------|-------------------|
| **Static Proxy Secret** | HIGH | Single shared secret in `.env`, no rotation | If leaked, all services compromised | HashiCorp Vault with auto-rotation, or AWS Secrets Manager |
| **No mTLS** | HIGH | Plain HTTP between services, headers can be spoofed if network compromised | Internal network breach exposes all services | Istio/Linkerd service mesh (auto-mTLS), or manual cert management |
| **Gateway SPOF** | MEDIUM | Single unified-ui instance | Gateway down = entire system down | Multiple instances behind load balancer (nginx, AWS ALB) |
| **In-Memory Rate Limiting** | MEDIUM | Per-instance, not distributed | Attackers can hit different instances to bypass limits | Redis-backed distributed rate limiting |
| **Supabase for Audit Logs** | MEDIUM | PostgreSQL not designed for high-volume append-only logs | Performance degrades at scale, expensive | ELK Stack, Splunk, AWS CloudWatch Logs, or dedicated TimescaleDB |
| **Trust Internal Network** | MEDIUM | Services trust headers without re-validating JWT | Compromised service can impersonate any user | Zero Trust: each service validates JWT (add fallback mode to shared module) |
| **Secrets in .env Files** | MEDIUM | Plain text on disk | Leaked via git, backups, or access | HashiCorp Vault, AWS Secrets Manager, or encrypted env files |
| **No Request Signing** | LOW | Headers not cryptographically signed | Sophisticated MITM could modify headers | Sign headers with HMAC or use mTLS |

---

### Upgrade Path (Additive, Not Rewrites)

All upgrades are **plug-and-play** - the architecture is designed correctly. No rewrites needed.

#### Phase 1: Quick Wins (1-2 days effort)

| Upgrade | Current | Target | How to Implement |
|---------|---------|--------|------------------|
| Redis Rate Limiting | `MemoryRateLimitBackend` | `RedisRateLimitBackend` | Already stubbed in `rate_limit.py`, just add Redis connection |
| Secret Rotation Script | Manual | Automated | Cron job to rotate `PROXY_SECRET` and `INTER_SERVICE_SECRET` |
| Multiple Gateway Instances | 1 instance | 2+ instances | Deploy multiple unified-ui behind nginx/ALB |

#### Phase 2: Production Hardening (1 week effort)

| Upgrade | Current | Target | How to Implement |
|---------|---------|--------|------------------|
| Proper Log Aggregation | Supabase | ELK/CloudWatch | Change `AuditLogger` to write to log aggregator instead of/in addition to Supabase |
| Health Checks & Alerts | Basic `/health` | Full observability | Add Prometheus metrics, Grafana dashboards, PagerDuty alerts |
| Database Connection Pooling | Direct connections | PgBouncer/Supavisor | Configure connection pooler for Supabase |
| Graceful Degradation | Hard failures | Fallbacks | Add circuit breakers (e.g., `tenacity` library) |

#### Phase 3: Security Hardening (2-3 weeks effort)

| Upgrade | Current | Target | How to Implement |
|---------|---------|--------|------------------|
| mTLS Between Services | Plain HTTP | Mutual TLS | Option A: Istio service mesh (easier), Option B: Manual cert management |
| Secret Management | `.env` files | Vault/Secrets Manager | Add Vault client, read secrets on startup |
| Zero Trust Mode | Trust gateway | Verify everywhere | Add `ZERO_TRUST_MODE` flag to shared module - when enabled, each service validates JWT |

#### Phase 4: Compliance Ready (2-4 weeks effort)

| Upgrade | Current | Target | How to Implement |
|---------|---------|--------|------------------|
| Audit Log Immutability | Mutable DB | Immutable/signed logs | Write to append-only storage (S3 with Object Lock, or blockchain-anchored) |
| Data Encryption at Rest | Supabase managed | Customer-managed keys | Enable Supabase encryption or use client-side encryption |
| PII Handling | Basic | Anonymization/masking | Add PII detection to audit logger, mask sensitive fields |
| Penetration Testing | None | Annual pentest | Hire security firm, document findings |
| SOC2 Type II | None | Certified | 6-12 month process with auditor |

---

### Component Scaling Table

| Component | Current | Scale Trigger | Upgrade To |
|-----------|---------|---------------|------------|
| **Rate Limiting** | In-memory | Multiple gateway instances | Redis with `rate_limit_state` table as fallback |
| **Audit Logs** | Security Supabase | >1M logs/month or query latency >1s | ELK Stack or CloudWatch, partition by month, archive to S3 |
| **API Keys** | Security Supabase | >10K API keys or high lookup frequency | Add Redis caching layer in front of Supabase |
| **RBAC Cache** | In-memory (30s TTL) | >1000 concurrent users | Redis shared cache across instances |
| **Services** | 3 services | Adding new service | Add to `service_registry`, generate inter-service JWT credentials |
| **Gateway** | Single instance | >1000 req/s or HA requirement | Multiple instances behind load balancer |

---

### When to Upgrade

| Trigger | Recommended Action |
|---------|-------------------|
| Preparing for funding round | Phase 1 + Phase 2 (looks professional to investors) |
| First enterprise customer | Phase 2 + Phase 3 (they'll ask about security) |
| SOC2/ISO requirement | All phases + compliance audit |
| Security incident | Immediate Phase 3 |
| >1000 concurrent users | Phase 1 (Redis) + multiple gateway instances |
| >10K requests/second | Full Phase 1-2 + consider Kubernetes |

---

### Architecture Decisions Log

| Decision | Rationale | Trade-off | Revisit When |
|----------|-----------|-----------|--------------|
| Gateway pattern (unified-ui) | Centralized auth, single JWT validation | SPOF, but simpler | Need HA or zero-trust |
| Trusted headers over JWT forwarding | Lower latency, no re-validation | Requires network trust | mTLS available |
| Short-lived inter-service JWT (60s) | Balance security vs overhead | Requires clock sync | Consider mTLS |
| Supabase for audit logs | Already using Supabase, quick to implement | Not ideal for high-volume logs | >1M logs/month |
| In-memory rate limiting | Simple, no dependencies | Not distributed | Multiple instances |
| Shared security module | Consistency, single source of truth | Tight coupling | Never (this is correct) |

---

### Security Checklist for Production

Before going to production, verify:

- [ ] `PROXY_SECRET` is set and is a strong random value (32+ bytes)
- [ ] `INTER_SERVICE_SECRET` is set and different from `PROXY_SECRET`
- [ ] HTTPS enabled on gateway (unified-ui)
- [ ] CORS origins are restricted (not `*`)
- [ ] Rate limiting is enabled
- [ ] Audit logging is enabled and writing to Security Supabase
- [ ] Health endpoints are monitored
- [ ] Error messages don't leak internal details in production
- [ ] `.env` files are not committed to git
- [ ] Supabase RLS policies are enabled on all tables
- [ ] Service accounts have minimal required permissions

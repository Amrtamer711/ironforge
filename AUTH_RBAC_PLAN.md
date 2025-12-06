# Authentication & RBAC Architecture Plan

## Overview

This document outlines the complete authentication, authorization, and storage isolation architecture for the Sales Proposals platform. The design follows the same abstraction patterns used for LLM providers (`integrations/llm/`) and channel adapters (`integrations/channels/`).

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              UNIFIED-UI                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────────┐ │
│  │  auth.js    │───►│  Supabase   │───►│  JWT Token (access_token)   │ │
│  │  (login)    │    │  Auth       │    │  stored in localStorage     │ │
│  └─────────────┘    └─────────────┘    └─────────────────────────────┘ │
│         │                                           │                    │
│         ▼                                           ▼                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    server.js (Proxy)                             │   │
│  │  - Forwards Authorization header to backend services             │   │
│  │  - Adds X-Request-User-ID header for tracing                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           PROPOSAL-BOT (Backend)                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    api/server.py                                 │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │   │
│  │  │ Auth         │  │ RBAC         │  │ Route Handlers       │  │   │
│  │  │ Middleware   │──│ Middleware   │──│ (protected)          │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                    │
│         ┌──────────────────────────┼──────────────────────────┐        │
│         ▼                          ▼                          ▼        │
│  ┌─────────────┐           ┌─────────────┐           ┌─────────────┐  │
│  │ integrations│           │ integrations│           │     db/     │  │
│  │ /auth/      │           │ /rbac/      │           │  database   │  │
│  │             │           │             │           │             │  │
│  │ AuthProvider│           │ RBACProvider│           │ Backend     │  │
│  └─────────────┘           └─────────────┘           └─────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              SUPABASE                                    │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────────┐ │
│  │  auth.users │    │  Database   │    │  Row Level Security (RLS)   │ │
│  │  (Supabase  │    │  Tables     │    │  Policies per table         │ │
│  │   Auth)     │    │             │    │                             │ │
│  └─────────────┘    └─────────────┘    └─────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
Sales Proposals/
├── integrations/
│   ├── auth/                          # NEW: Auth provider abstraction
│   │   ├── __init__.py
│   │   ├── base.py                    # Abstract AuthProvider
│   │   └── providers/
│   │       ├── __init__.py
│   │       ├── supabase.py            # Supabase Auth implementation
│   │       └── local_dev.py           # Local dev mode (hardcoded users)
│   │
│   ├── rbac/                          # NEW: RBAC provider abstraction
│   │   ├── __init__.py
│   │   ├── base.py                    # Abstract RBACProvider
│   │   └── providers/
│   │       ├── __init__.py
│   │       ├── database.py            # Database-backed RBAC
│   │       └── static.py              # Static config-based RBAC
│   │
│   ├── llm/                           # Existing (reference pattern)
│   │   ├── base.py
│   │   └── providers/
│   │
│   └── channels/                      # Existing (reference pattern)
│       ├── base.py
│       └── adapters/
│
├── db/
│   ├── schema.py                      # UPDATED: Has auth tables
│   ├── rls.py                         # NEW: RLS policy generator
│   ├── base.py                        # Existing
│   ├── database.py                    # UPDATED: Add user mgmt methods
│   └── backends/
│       ├── sqlite.py                  # UPDATED: User mgmt methods
│       └── supabase.py                # UPDATED: RLS initialization
│
├── api/
│   └── server.py                      # UPDATED: Auth/RBAC middleware
│
└── unified-ui/
    ├── server.js                      # UPDATED: Forward auth headers
    └── public/js/
        └── auth.js                    # UPDATED: Sync user to backend
```

---

## Implementation Checklist

### Phase 1: Auth Provider Abstraction
- [ ] Create `integrations/auth/__init__.py`
- [ ] Create `integrations/auth/base.py` with `AuthProvider` ABC
- [ ] Create `integrations/auth/providers/__init__.py`
- [ ] Create `integrations/auth/providers/supabase.py`
- [ ] Create `integrations/auth/providers/local_dev.py`

### Phase 2: RBAC Provider Abstraction
- [ ] Create `integrations/rbac/__init__.py`
- [ ] Create `integrations/rbac/base.py` with `RBACProvider` ABC
- [ ] Create `integrations/rbac/providers/__init__.py`
- [ ] Create `integrations/rbac/providers/database.py`
- [ ] Create `integrations/rbac/providers/static.py`

### Phase 3: RLS Policy Generator
- [ ] Create `db/rls.py` with policy definitions
- [ ] Add RLS generation for all tables with user_id
- [ ] Add admin bypass policies
- [ ] Add role-based access policies

### Phase 4: Proxy Auth Forwarding
- [ ] Update `unified-ui/server.js` to forward Authorization header
- [ ] Add X-Request-User-ID header for tracing
- [ ] Test token forwarding

### Phase 5: Backend Auth Middleware
- [ ] Add `get_current_user()` dependency to api/server.py
- [ ] Add `require_auth()` dependency
- [ ] Add `require_role()` dependency factory
- [ ] Add `require_permission()` dependency factory
- [ ] Protect existing endpoints

### Phase 6: Database User Management
- [ ] Add user CRUD methods to `db/base.py`
- [ ] Implement in `db/backends/sqlite.py`
- [ ] Implement in `db/backends/supabase.py`
- [ ] Add default roles/permissions initialization

### Phase 7: Integration & Testing
- [ ] Test local dev auth flow
- [ ] Test Supabase auth flow
- [ ] Test RBAC enforcement
- [ ] Test RLS policies (Supabase only)
- [ ] Document usage

---

## Detailed Specifications

### 1. AuthProvider Interface

```python
# integrations/auth/base.py
class AuthProvider(ABC):
    """Abstract base class for authentication providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'supabase', 'local_dev')."""
        pass

    @abstractmethod
    async def verify_token(self, token: str) -> Optional[AuthUser]:
        """Verify a JWT token and return the authenticated user."""
        pass

    @abstractmethod
    async def get_user_by_id(self, user_id: str) -> Optional[AuthUser]:
        """Get user by their ID."""
        pass

    @abstractmethod
    async def sync_user_to_db(self, user: AuthUser) -> bool:
        """Sync authenticated user to local database."""
        pass
```

### 2. RBACProvider Interface

```python
# integrations/rbac/base.py
class RBACProvider(ABC):
    """Abstract base class for RBAC providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass

    @abstractmethod
    async def get_user_roles(self, user_id: str) -> List[str]:
        """Get all roles assigned to a user."""
        pass

    @abstractmethod
    async def get_user_permissions(self, user_id: str) -> Set[str]:
        """Get all permissions for a user (from all their roles)."""
        pass

    @abstractmethod
    async def has_role(self, user_id: str, role: str) -> bool:
        """Check if user has a specific role."""
        pass

    @abstractmethod
    async def has_permission(self, user_id: str, permission: str) -> bool:
        """Check if user has a specific permission."""
        pass

    @abstractmethod
    async def assign_role(self, user_id: str, role: str, granted_by: Optional[str] = None) -> bool:
        """Assign a role to a user."""
        pass
```

### 3. RLS Policies

```sql
-- Example RLS policy for proposals_log
ALTER TABLE proposals_log ENABLE ROW LEVEL SECURITY;

-- Users can see their own proposals
CREATE POLICY "proposals_select_own" ON proposals_log
    FOR SELECT TO authenticated
    USING (user_id = auth.uid()::text);

-- Users can insert their own proposals
CREATE POLICY "proposals_insert_own" ON proposals_log
    FOR INSERT TO authenticated
    WITH CHECK (user_id = auth.uid()::text);

-- Admins can see all proposals
CREATE POLICY "proposals_admin_all" ON proposals_log
    FOR ALL TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = auth.uid()::text
            AND r.name = 'admin'
        )
    );

-- HOS can see team proposals (same logic for booking_orders, etc.)
CREATE POLICY "proposals_hos_team" ON proposals_log
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = auth.uid()::text
            AND r.name IN ('admin', 'hos')
        )
    );
```

### 4. Default Roles & Permissions

| Role | Permissions |
|------|-------------|
| `admin` | All permissions (wildcard) |
| `hos` | proposals:*, booking_orders:*, mockups:*, users:read, ai_costs:read |
| `sales_person` | proposals:create/read, booking_orders:create/read, mockups:create/read |
| `coordinator` | booking_orders:create/read/update |
| `finance` | booking_orders:read, ai_costs:read |

### 5. Auth Flow

```
1. User visits unified-ui
2. unified-ui/auth.js checks for existing session
3. If no session, show login modal
4. User logs in via Supabase Auth
5. Supabase returns JWT (access_token)
6. auth.js stores token in localStorage
7. auth.js calls backend /api/auth/sync to sync user to DB
8. On API calls:
   a. api.js adds Authorization: Bearer {token}
   b. unified-ui/server.js proxy forwards header
   c. api/server.py validates token via AuthProvider
   d. api/server.py checks permissions via RBACProvider
   e. If authorized, execute request
   f. If not, return 401/403
```

---

## Environment Variables

```bash
# Auth Provider Selection
AUTH_PROVIDER=supabase  # or 'local_dev'

# RBAC Provider Selection
RBAC_PROVIDER=database  # or 'static'

# Supabase (required for supabase provider)
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=xxx  # For client-side
SUPABASE_SERVICE_KEY=xxx  # For server-side (admin)
SUPABASE_JWT_SECRET=xxx  # For token validation

# Database Backend
DB_BACKEND=supabase  # or 'sqlite'
```

---

## Migration Strategy

1. **Phase 1**: Deploy auth/rbac abstractions (no breaking changes)
2. **Phase 2**: Enable auth middleware with `optional=True` (logs but doesn't block)
3. **Phase 3**: Enable RBAC with `optional=True` (logs but doesn't block)
4. **Phase 4**: Switch to `optional=False` (enforced)
5. **Phase 5**: Enable RLS policies in Supabase (data isolation)

---

## Testing Strategy

### Unit Tests
- AuthProvider implementations
- RBACProvider implementations
- Token validation
- Permission checking

### Integration Tests
- Full auth flow (login → token → API call)
- Role assignment and checking
- RLS policy enforcement (Supabase only)

### Manual Testing
- Login with different roles
- Verify data isolation
- Test permission denied scenarios

# Sales Proposals Bot - TODO

## Design Principles

> **IMPORTANT:** All implementations must follow these principles:
>
> 1. **Adapter/Provider Pattern** - Use abstract base classes with swappable implementations (e.g., `AuthProvider`, `DatabaseBackend`, `LLMProvider`, `ChannelAdapter`)
> 2. **Interface-First Design** - Define interfaces before implementations; consumers depend on abstractions, not concretions
> 3. **Configuration-Driven** - Behavior controlled via environment variables and config files, not hardcoded values
> 4. **Pluggable Architecture** - New providers can be added without modifying existing code (Open/Closed Principle)
>
> **Examples in codebase:**
>
> - `integrations/auth/` - `LocalAuthProvider`, `SupabaseAuthProvider`
> - `db/backends/` - `SQLiteBackend`, `SupabaseBackend`
> - `integrations/llm/providers/` - `OpenAIProvider`, `GoogleProvider`
> - `integrations/channels/adapters/` - `SlackAdapter`, `WebAdapter`

---

## Platform Infrastructure

### Authentication & Authorization

- [X] Auth provider abstraction (`integrations/auth/`)
  - [X] Base classes and interfaces
  - [X] Local dev provider (hardcoded users)
  - [X] Supabase provider (JWT validation)
- [X] RBAC system (`integrations/rbac/`)
  - [X] Role management
  - [X] Permission management
  - [X] User-role assignments
  - [X] Database-backed provider
  - [X] **Module-aware RBAC refactor** (for company-wide use)
    - [X] Move `DEFAULT_PERMISSIONS` and `DEFAULT_ROLES` out of `base.py` into module-specific config
    - [X] Add module registration system (`integrations/rbac/modules/`)
    - [X] Update permission format to `{module}:{resource}:{action}` (e.g., `sales:proposals:create`)
    - [X] Create generic company-level roles separate from module-specific roles
    - [X] Unified UI RBAC that translates between module-specific and UI-level permissions
    - [X] Module-to-UI permission mapping layer
- [X] FastAPI auth dependencies (`api/auth.py`)
  - [X] `get_current_user`, `require_auth`
  - [X] `require_permission`, `require_role`
- [X] Apply auth to protected endpoints (chat, proposals, costs, files)
- [X] Admin UI for role/permission management
  - [X] Backend API (`api/routers/admin.py`)
  - [X] Frontend UI (`unified-ui/public/js/admin.js`)
  - [X] CSS styles (`unified-ui/public/css/styles.css` - LAYER 42)
  - [X] User management endpoints (CRUD, role assignment)
  - [X] User management UI tab

### Enterprise RBAC Architecture (CRM-Ready)

> **Goal:** Scalable, enterprise-grade RBAC that supports profiles, permission sets, teams,
> and record-level access control - following patterns from Salesforce/HubSpot.

#### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PERMISSION ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────────┤
│  Level 1: PROFILES (Base Role Template)                             │
│  ─────────────────────────────────────                              │
│  "Sales Rep", "Sales Manager", "Admin"                              │
│  → Defines BASE permissions for a job function                      │
│                                                                      │
│  Level 2: PERMISSION SETS (Additive)                                │
│  ────────────────────────────────────                               │
│  "API Access", "Export Data", "Delete Records"                      │
│  → Can be added to ANY user regardless of profile                   │
│  → Temporary or permanent elevation                                  │
│                                                                      │
│  Level 3: TEAMS & HIERARCHY                                         │
│  ─────────────────────────────                                      │
│  Users belong to teams, teams have managers                         │
│  → Enables "see team data" and "see subordinate data"               │
│                                                                      │
│  Level 4: RECORD-LEVEL ACCESS (Sharing Rules)                       │
│  ────────────────────────────────────────────                       │
│  Who can see which specific records?                                │
│  → Own records, Team records, All records                           │
│  → Ad-hoc sharing (share deal X with user Y)                        │
└─────────────────────────────────────────────────────────────────────┘
```

#### Phase 1: Profiles & Base Permissions
- [ ] **Database Schema Updates** (`db/migrations/ui_schema.sql`)
  - [ ] Create `profiles` table (replaces simple roles for users)
    ```sql
    CREATE TABLE profiles (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,         -- 'Sales Rep', 'Sales Manager'
        description TEXT,
        is_system BOOLEAN DEFAULT false,   -- System profiles can't be deleted
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    ```
  - [ ] Create `profile_permissions` table
    ```sql
    CREATE TABLE profile_permissions (
        id BIGSERIAL PRIMARY KEY,
        profile_id BIGINT REFERENCES profiles(id) ON DELETE CASCADE,
        permission TEXT NOT NULL,          -- 'sales:deals:create'
        UNIQUE(profile_id, permission)
    );
    ```
  - [ ] Add `profile_id` column to `users` table
  - [ ] Migrate existing roles to profiles

- [ ] **Update `db/schema.py`** - Add to `CORE_TABLES`
  - [ ] Add `profiles` table definition
  - [ ] Add `profile_permissions` table definition
  - [ ] Update `users` table with `profile_id` column

- [ ] **Update RBAC Models** (`integrations/rbac/base.py`)
  - [ ] Add `Profile` model class
  - [ ] Add `ProfilePermission` model class
  - [ ] Update `RBACProvider` interface with profile methods

- [ ] **Update DatabaseRBACProvider** (`integrations/rbac/providers/database.py`)
  - [ ] Implement `get_user_profile(user_id)` method
  - [ ] Implement `get_profile_permissions(profile_id)` method
  - [ ] Update `get_user_permissions()` to resolve from profile
  - [ ] Implement profile CRUD operations

- [ ] **Admin API Endpoints** (`api/routers/admin.py`)
  - [ ] `GET /api/admin/profiles` - List all profiles
  - [ ] `POST /api/admin/profiles` - Create profile
  - [ ] `GET /api/admin/profiles/{id}` - Get profile details
  - [ ] `PUT /api/admin/profiles/{id}` - Update profile
  - [ ] `DELETE /api/admin/profiles/{id}` - Delete profile
  - [ ] `GET /api/admin/profiles/{id}/permissions` - Get profile permissions
  - [ ] `PUT /api/admin/profiles/{id}/permissions` - Set profile permissions
  - [ ] `PUT /api/admin/users/{id}/profile` - Assign profile to user

- [ ] **Seed Default Profiles**
  ```python
  DEFAULT_PROFILES = {
      "admin": {
          "description": "Full system access",
          "permissions": ["*:*:*"]
      },
      "sales_manager": {
          "description": "Sales team management",
          "permissions": [
              "sales:*:*",
              "core:users:read",
              "core:ai_costs:read"
          ]
      },
      "sales_rep": {
          "description": "Sales team member",
          "permissions": [
              "sales:proposals:create",
              "sales:proposals:read:own",
              "sales:booking_orders:create",
              "sales:booking_orders:read:own",
              "sales:mockups:*"
          ]
      },
      "coordinator": {
          "description": "Operations coordinator",
          "permissions": [
              "sales:booking_orders:*"
          ]
      },
      "finance": {
          "description": "Finance team",
          "permissions": [
              "sales:booking_orders:read",
              "core:ai_costs:read"
          ]
      }
  }
  ```

#### Phase 2: Permission Sets (Additive Permissions)
- [ ] **Database Schema** (`db/migrations/ui_schema.sql`)
  - [ ] Create `permission_sets` table
    ```sql
    CREATE TABLE permission_sets (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,         -- 'API Access', 'Data Export'
        description TEXT,
        is_active BOOLEAN DEFAULT true,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    ```
  - [ ] Create `permission_set_permissions` table
    ```sql
    CREATE TABLE permission_set_permissions (
        id BIGSERIAL PRIMARY KEY,
        permission_set_id BIGINT REFERENCES permission_sets(id) ON DELETE CASCADE,
        permission TEXT NOT NULL,
        UNIQUE(permission_set_id, permission)
    );
    ```
  - [ ] Create `user_permission_sets` junction table
    ```sql
    CREATE TABLE user_permission_sets (
        id BIGSERIAL PRIMARY KEY,
        user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
        permission_set_id BIGINT REFERENCES permission_sets(id) ON DELETE CASCADE,
        granted_by TEXT REFERENCES users(id),
        granted_at TIMESTAMPTZ DEFAULT NOW(),
        expires_at TIMESTAMPTZ,            -- Optional expiration
        UNIQUE(user_id, permission_set_id)
    );
    ```

- [ ] **Update `db/schema.py`** - Add to `CORE_TABLES`
  - [ ] Add `permission_sets` table definition
  - [ ] Add `permission_set_permissions` table definition
  - [ ] Add `user_permission_sets` table definition

- [ ] **Update RBAC Models** (`integrations/rbac/base.py`)
  - [ ] Add `PermissionSet` model class
  - [ ] Add `UserPermissionSet` model class

- [ ] **Update Permission Resolution** (`integrations/rbac/providers/database.py`)
  - [ ] Update `get_user_permissions()` to include permission sets
  - [ ] Implement permission set expiration checking
  ```python
  async def get_effective_permissions(self, user_id: str) -> Set[str]:
      permissions = set()

      # 1. Get profile permissions
      profile = await self.get_user_profile(user_id)
      if profile:
          permissions.update(await self.get_profile_permissions(profile.id))

      # 2. Add permission set permissions (non-expired)
      user_perm_sets = await self.get_user_permission_sets(user_id)
      for ps in user_perm_sets:
          if not ps.expires_at or ps.expires_at > datetime.now():
              permissions.update(await self.get_permission_set_permissions(ps.id))

      return permissions
  ```

- [ ] **Admin API Endpoints** (`api/routers/admin.py`)
  - [ ] `GET /api/admin/permission-sets` - List all permission sets
  - [ ] `POST /api/admin/permission-sets` - Create permission set
  - [ ] `PUT /api/admin/permission-sets/{id}` - Update permission set
  - [ ] `DELETE /api/admin/permission-sets/{id}` - Delete permission set
  - [ ] `POST /api/admin/users/{id}/permission-sets` - Grant permission set to user
  - [ ] `DELETE /api/admin/users/{id}/permission-sets/{ps_id}` - Revoke permission set

- [ ] **Seed Default Permission Sets**
  ```python
  DEFAULT_PERMISSION_SETS = {
      "api_access": {
          "description": "Programmatic API access",
          "permissions": ["core:api:access"]
      },
      "data_export": {
          "description": "Export data to CSV/Excel",
          "permissions": ["core:export:*"]
      },
      "delete_records": {
          "description": "Delete any records",
          "permissions": ["*:*:delete"]
      },
      "view_all_data": {
          "description": "View all records (bypass ownership)",
          "permissions": ["*:*:read:all"]
      }
  }
  ```

#### Phase 3: Teams & Hierarchy
- [ ] **Database Schema** (`db/migrations/ui_schema.sql`)
  - [ ] Create `teams` table
    ```sql
    CREATE TABLE teams (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        parent_team_id BIGINT REFERENCES teams(id),  -- Hierarchy
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    ```
  - [ ] Create `team_members` table
    ```sql
    CREATE TABLE team_members (
        id BIGSERIAL PRIMARY KEY,
        team_id BIGINT REFERENCES teams(id) ON DELETE CASCADE,
        user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
        role TEXT DEFAULT 'member',        -- 'member', 'leader'
        joined_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(team_id, user_id)
    );
    ```
  - [ ] Add `manager_id` column to `users` table
    ```sql
    ALTER TABLE users ADD COLUMN manager_id TEXT REFERENCES users(id);
    ```

- [ ] **Update `db/schema.py`** - Add to `CORE_TABLES`
  - [ ] Add `teams` table definition
  - [ ] Add `team_members` table definition
  - [ ] Update `users` table with `manager_id`

- [ ] **Update RBAC Models** (`integrations/rbac/base.py`)
  - [ ] Add `Team` model class
  - [ ] Add `TeamMember` model class

- [ ] **Team-Based Permission Resolution** (`integrations/rbac/providers/database.py`)
  - [ ] Implement `get_user_teams(user_id)` method
  - [ ] Implement `get_team_hierarchy(team_id)` - Returns parent chain
  - [ ] Implement `get_subordinates(user_id)` - Direct reports
  - [ ] Implement `get_all_subordinates(user_id)` - Full hierarchy below

- [ ] **Admin API Endpoints** (`api/routers/admin.py`)
  - [ ] `GET /api/admin/teams` - List all teams
  - [ ] `POST /api/admin/teams` - Create team
  - [ ] `PUT /api/admin/teams/{id}` - Update team
  - [ ] `DELETE /api/admin/teams/{id}` - Delete team
  - [ ] `GET /api/admin/teams/{id}/members` - Get team members
  - [ ] `POST /api/admin/teams/{id}/members` - Add member to team
  - [ ] `DELETE /api/admin/teams/{id}/members/{user_id}` - Remove from team
  - [ ] `PUT /api/admin/users/{id}/manager` - Set user's manager

#### Phase 4: Record-Level Access Control
- [ ] **Database Schema** (`db/migrations/ui_schema.sql`)
  - [ ] Create `sharing_rules` table (organization-wide rules)
    ```sql
    CREATE TABLE sharing_rules (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        object_type TEXT NOT NULL,         -- 'proposal', 'booking_order'
        share_from TEXT NOT NULL,          -- 'owner', 'team:sales', 'profile:manager'
        share_to TEXT NOT NULL,            -- 'team:finance', 'profile:admin'
        access_level TEXT NOT NULL,        -- 'read', 'read_write', 'full'
        is_active BOOLEAN DEFAULT true,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    ```
  - [ ] Create `record_shares` table (ad-hoc sharing)
    ```sql
    CREATE TABLE record_shares (
        id BIGSERIAL PRIMARY KEY,
        object_type TEXT NOT NULL,
        record_id TEXT NOT NULL,
        shared_with_user_id TEXT REFERENCES users(id),
        shared_with_team_id BIGINT REFERENCES teams(id),
        access_level TEXT NOT NULL,        -- 'read', 'read_write', 'full'
        shared_by TEXT REFERENCES users(id),
        shared_at TIMESTAMPTZ DEFAULT NOW(),
        expires_at TIMESTAMPTZ,
        CONSTRAINT share_target CHECK (
            (shared_with_user_id IS NOT NULL AND shared_with_team_id IS NULL) OR
            (shared_with_user_id IS NULL AND shared_with_team_id IS NOT NULL)
        )
    );
    CREATE INDEX idx_record_shares_lookup
        ON record_shares(object_type, record_id);
    ```

- [ ] **Update `db/schema.py`** - Add to `CORE_TABLES`
  - [ ] Add `sharing_rules` table definition
  - [ ] Add `record_shares` table definition

- [ ] **Record Access Utility** (`integrations/rbac/record_access.py`)
  - [ ] Create `RecordAccessChecker` class
    ```python
    class RecordAccessChecker:
        async def can_access(
            self,
            user_id: str,
            object_type: str,
            record_id: str,
            access_level: str = "read"
        ) -> bool:
            """
            Check if user can access a specific record.

            Resolution order:
            1. Is user the owner? → Yes
            2. Is user admin? → Yes (bypass)
            3. Does profile have 'view_all' for object? → Yes
            4. Does sharing rule grant access? → Check
            5. Is record directly shared? → Check
            """

        async def get_accessible_record_ids(
            self,
            user_id: str,
            object_type: str,
            access_level: str = "read"
        ) -> List[str]:
            """
            Get all record IDs user can access.
            Used for filtering queries.
            """

        async def share_record(
            self,
            object_type: str,
            record_id: str,
            share_with_user_id: Optional[str] = None,
            share_with_team_id: Optional[int] = None,
            access_level: str = "read",
            shared_by: str,
            expires_at: Optional[datetime] = None
        ) -> bool:
            """Share a record with a user or team."""
    ```

- [ ] **Update Existing Endpoints** - Add record-level checks
  - [ ] `GET /api/proposals` - Filter by accessible records
  - [ ] `GET /api/proposals/{id}` - Check access before returning
  - [ ] `PUT /api/proposals/{id}` - Check write access
  - [ ] `DELETE /api/proposals/{id}` - Check delete access
  - [ ] Apply same pattern to booking_orders, mockups

- [ ] **Sharing API Endpoints** (`api/routers/sharing.py`)
  - [ ] `GET /api/{object_type}/{id}/shares` - List shares for record
  - [ ] `POST /api/{object_type}/{id}/shares` - Share record
  - [ ] `DELETE /api/{object_type}/{id}/shares/{share_id}` - Revoke share

#### Frontend Updates
- [ ] **Admin UI Updates** (`unified-ui/public/js/admin.js`)
  - [ ] Profile management tab
    - [ ] List/create/edit/delete profiles
    - [ ] Permission assignment matrix
  - [ ] Permission Sets tab
    - [ ] List/create/edit/delete permission sets
    - [ ] Grant/revoke from users
  - [ ] Teams tab
    - [ ] Team hierarchy visualization
    - [ ] Team member management
    - [ ] Manager assignment
  - [ ] User detail view updates
    - [ ] Show assigned profile
    - [ ] Show permission sets (with expiration)
    - [ ] Show team memberships
    - [ ] Show effective permissions (computed)

- [ ] **Record Sharing UI** (in relevant modules)
  - [ ] "Share" button on record detail views
  - [ ] Share modal with user/team search
  - [ ] Access level selector
  - [ ] Expiration date picker
  - [ ] Current shares list with revoke option

#### Migration Strategy
- [ ] **Data Migration Script** (`db/migrations/migrate_rbac.py`)
  - [ ] Map existing roles to profiles
    - `admin` role → `admin` profile
    - `sales:hos` role → `sales_manager` profile
    - `sales:sales_person` role → `sales_rep` profile
    - `sales:coordinator` role → `coordinator` profile
    - `sales:finance` role → `finance` profile
  - [ ] Migrate `user_roles` to `users.profile_id`
  - [ ] Keep old tables temporarily for rollback
  - [ ] Verification queries to ensure no permission loss

- [ ] **Backward Compatibility**
  - [ ] Keep `require_role()` working during transition
  - [ ] Add deprecation warnings for old patterns
  - [ ] Document migration path for custom integrations

#### Testing
- [ ] **Unit Tests** (`tests/test_rbac_enterprise.py`)
  - [ ] Profile permission resolution
  - [ ] Permission set additive logic
  - [ ] Permission set expiration
  - [ ] Team hierarchy traversal
  - [ ] Record access checking
  - [ ] Sharing rules evaluation

- [ ] **Integration Tests**
  - [ ] Full permission flow: profile + permission sets + team
  - [ ] Record-level access with sharing rules
  - [ ] Admin API endpoints
  - [ ] Migration script verification

### Database Layer

- [X] Database abstraction (`db/base.py`, `db/backends/`)
  - [X] SQLite backend
  - [X] Supabase backend
- [X] Schema definition (`db/schema.py`)
- [X] User/Role/Permission tables
- [X] Database migrations system
  - [X] Versioned migration files (`db/migrations/versions/`)
  - [X] Migration runner (custom, `python -m db.migrations`)
  - [X] Rollback support

### API Architecture

- [X] Split `api/server.py` into routers (~1400 lines → 170 lines)
  - [X] `api/routers/slack.py` - Slack events & interactive
  - [X] `api/routers/health.py` - Health & metrics
  - [X] `api/routers/costs.py` - AI cost tracking
  - [X] `api/routers/mockups.py` - Mockup generator
  - [X] `api/routers/chat.py` - Unified UI chat
  - [X] `api/routers/auth_routes.py` - Auth endpoints
  - [X] `api/routers/proposals.py` - Proposal endpoints
  - [X] `api/routers/files.py` - File serving
- [X] Centralized error handling (`api/exceptions.py`)
  - [X] Custom exception classes (APIError, NotFoundError, etc.)
  - [X] Global exception handler
  - [X] Consistent error response format

### Shared Utilities

- [X] Create `utils/time.py` for UAE timezone
  - [X] Consolidate `UAE_TZ` definition (updated 7 files)
  - [X] `get_uae_time()` function
  - [X] Update all imports
- [X] Create `utils/constants.py` for shared constants

### Configuration Management

- [X] Pydantic settings class (`app_settings/settings.py`)
  - [X] Environment variable validation
  - [X] Type-safe config access
  - [X] Default values with overrides
- [X] Consolidate scattered `os.getenv()` calls (migrate to use `settings`)
  - [X] Extended `app_settings/settings.py` with all config fields
  - [X] Updated `utils/cache.py`, `utils/job_queue.py`, rate limiting, API key middleware
  - [X] Created `.env.example` documenting all environment variables

### Logging & Monitoring

- [X] Structured logging (`utils/logging.py`)
  - [X] JSON-formatted logs for production
  - [X] Human-readable colored logs for development
  - [X] Request ID tracking via context variables
  - [X] Log levels per module configuration
  - [X] FastAPI middleware for request logging
- [X] Health check improvements (`api/routers/health.py`)
  - [X] `/health` - Basic health check (fast, no external calls)
  - [X] `/health/ready` - Readiness check with dependency status
  - [X] Database connectivity check
  - [X] Slack/LLM provider configuration checks
- [X] **Audit logging** (`utils/audit.py`) - **COMPLETED**
  - [X] Track sensitive operations (user management, permission changes)
  - [X] Structured audit events (who, what, when, where)
  - [X] Database-backed audit log storage (SQLite + Supabase)
  - [ ] Retention policies for audit records (future enhancement)

### Security

- [X] **API Key Authentication** (`api/middleware/api_key.py`)
  - [X] Generate and store API keys per client/app
  - [X] `X-API-Key` header validation middleware
  - [X] Key scoping (read, write, admin, proposals, mockups)
  - [X] Environment-based key store (for simple deployments)
  - [X] Database-backed key store (for production)
  - [X] API key rotation mechanism
  - [X] Audit logging for API key usage
  - [X] Admin API endpoints for key management (`api/routers/admin.py`)
- [X] API rate limiting (`api/middleware/rate_limit.py`)
  - [X] In-memory sliding window algorithm
  - [X] Per-client limiting (IP, user, API key)
  - [X] Configurable limits per endpoint
  - [X] Redis backend for distributed rate limiting
    - Lua script for atomic operations
    - Graceful fallback to memory on Redis failure
    - `RATE_LIMIT_BACKEND=redis` + `REDIS_URL` to enable
- [X] Input validation on all endpoints
  - [X] Created centralized validation schemas (`api/schemas.py`)
  - [X] Added Pydantic validation to costs.py (date format, enums)
  - [X] Added file upload validation to mockups.py (size, MIME type)
  - [X] Form parameter validation with min/max length constraints
  - Note: Slack endpoints use signature verification (handled by Slack SDK)
- [X] Secrets management review
  - [X] All secrets use environment variables (not hardcoded)
  - [X] API keys hashed with SHA256 before storage
  - [X] `.env` properly in `.gitignore`
  - [X] No secrets logged (generic error messages to clients)
  - [X] Centralized settings via `app_settings/settings.py`
- [X] CORS configuration audit
  - [X] CORS origins now read from `CORS_ORIGINS` env var (not hardcoded)
  - [X] Restricted allowed methods to specific list (not `*`)
  - [X] Restricted allowed headers to specific list (not `*`)

### Performance

- [X] Caching layer abstraction (`utils/cache.py`)

  - [X] In-memory LRU cache with TTL
  - [X] Redis backend for distributed caching
  - [X] `@cached` decorator for function memoization
  - [X] Cache statistics tracking

  - `CACHE_BACKEND=redis` + `REDIS_URL` to enable
- [X] Background job queue (`utils/job_queue.py`)

  - [X] Async task queue with concurrency control
  - [X] Job status tracking (pending, running, completed, failed)
  - [X] Progress updates from within jobs
  - [X] Timeout and cancellation support
  - [X] Job history with automatic cleanup

---

## Phase 1: Refactoring (Completed)

- [X] Complete initial refactor (fix remaining import issues)
- [X] Further refactor and decouple long scripts (prompts, parsing logic, etc.)
- [X] Decouple pre/post image modifications in mockup generator for easier customization

  - Created `generators/effects/` module with modular, configurable effects
  - `EffectConfig` dataclass for all parameters
  - Separate classes: `EdgeCompositor`, `DepthEffect`, `VignetteEffect`, `ShadowEffect`, `ColorAdjustment`, `ImageBlur`, `Sharpening`, `OverlayBlending`
- [X] Create centralized AI provider abstraction layer

  - Created `integrations/llm/` module with `LLMClient` unified interface
  - Abstract base classes in `base.py`
  - OpenAI provider implementation in `providers/openai.py`
  - Prompts organized in `prompts/` directory
  - JSON schemas in `schemas/` directory

  - [X] Migrate image generation from GPT-image-1 to Google Nano Banana 2
- [X] Centralize memory management (`utils/memory.py`)
- [X] Create task queue for mockup generation (`utils/task_queue.py`)

## Phase 2: Features (Completed)

- [X] Add currency conversion to sales proposals

## Phase 3: Documentation (Completed)

- [X] Add comprehensive documentation
  - Created `ARCHITECTURE.md` with full technical documentation
  - Project structure, core architecture, module deep dives
  - Data flow diagrams, database schema, configuration system
  - LLM integration patterns, deployment setup, troubleshooting

## Phase 4: Frontend

- [ ] Finish new frontend
  - [ ] All existing features/functionality from current frontend
  - [ ] Native zoom in/out for template editing
  - [ ] Template editing for bad/incorrect templates
  - [ ] Visual template picker in generate mode (preview before selecting)
  - [ ] Pixel enhancer tool
- [ ] Migrate to new frontend

## Phase 5: Templates

- [ ] Fix currently broken location templates
- [ ] Add new location templates

## Phase 6: Booking Order Flow

- [ ] Finish BO flow (Note: Must align on requirements/demands first before implementation)

## Phase 7: CRM/Company Website Backend Components

> **Note:** These are backend modules needed for a complete CRM system. They should be implemented
> following the existing adapter/provider patterns established in the codebase.

### Companies & Contacts Management
- [ ] **Companies module** (`api/routers/companies.py`, `db/` schema extension)
  - Company CRUD operations
  - Company metadata (industry, size, etc.)
  - Company-user relationships
- [ ] **Contacts module** (`api/routers/contacts.py`)
  - Contact CRUD operations
  - Contact-company associations
  - Contact history/activity log

### Sales Pipeline
- [ ] **Leads module** (`api/routers/leads.py`)
  - Lead capture and management
  - Lead scoring and qualification
  - Lead-to-opportunity conversion
- [ ] **Opportunities module** (`api/routers/opportunities.py`)
  - Opportunity pipeline stages
  - Deal tracking (value, probability, expected close)
  - Activity timeline

### Activity & Communication Tracking
- [ ] **Activities module** (`api/routers/activities.py`)
  - Calls, meetings, emails logging
  - Task/reminder management
  - Activity-entity associations (contact, company, opportunity)
- [ ] **Email integration** (`integrations/email/`)
  - SMTP/SendGrid/Resend provider abstraction
  - Email templates
  - Email tracking (opens, clicks)
  - Email-to-activity sync

### File & Document Management
- [X] **File storage abstraction** (`integrations/storage/`) - **COMPLETED**
  - [X] Base interface and client (`base.py`, `client.py`)
  - [X] Local filesystem provider (`providers/local.py`)
  - [X] Supabase Storage provider (`providers/supabase.py`)
  - [ ] S3 provider (`providers/s3.py`) - optional
  - [X] Presigned URLs for secure access
  - [ ] File-entity associations

### Notifications & Alerts
- [ ] **Notifications module** (`api/routers/notifications.py`)
  - In-app notifications
  - Email notifications
  - Webhook notifications for external systems
- [ ] **Notification preferences** per user

### Reporting & Analytics
- [ ] **Reports module** (`api/routers/reports.py`)
  - Sales pipeline reports
  - Activity reports
  - Custom report builder
- [ ] **Dashboard metrics API**
  - KPIs and aggregated stats
  - Time-series data for charts

### User & Team Management (Extensions)
- [ ] **Teams/groups** management
  - Team hierarchy
  - Team-based access control
- [ ] **User profiles** extension
  - Extended profile fields
  - User preferences storage

---

## Vendor/Platform Integrations

This section documents all external vendor and platform integrations used in the project, with setup and configuration guides.

### 1. Supabase (Database & Auth)

**Purpose:** PostgreSQL database backend, JWT authentication
**Environment Variables:**

- `SUPABASE_URL` - Project URL (e.g., `https://xxx.supabase.co`)
- `SUPABASE_SERVICE_KEY` - Service role key (full access)
- `SUPABASE_JWT_SECRET` - JWT secret for token validation
- `DATABASE_URL` - Direct PostgreSQL connection string (optional)

**Integration Points:**

- `db/backends/supabase.py` - Database operations
- `integrations/auth/providers/supabase.py` - JWT validation

**Setup Tutorial:**

- [ ] Create Supabase project at https://supabase.com
- [ ] Enable Row Level Security (RLS) on tables
- [ ] Configure JWT secret in project settings
- [ ] Set up database tables (see `db/schema.py`)
- [ ] Document API rate limits and quotas

### 2. OpenAI (LLM & Image Generation)

**Purpose:** GPT-4 for text completion, DALL-E/GPT-image-1 for images
**Environment Variables:**

- `OPENAI_API_KEY` - API key from OpenAI dashboard

**Integration Points:**

- `integrations/llm/providers/openai.py` - LLM completions
- `core/llm.py` - Image generation

**Setup Tutorial:**

- [ ] Create OpenAI account at https://platform.openai.com
- [ ] Generate API key with appropriate permissions
- [ ] Set usage limits and billing alerts
- [ ] Configure model selection (`gpt-4`, `gpt-4-turbo`, etc.)
- [ ] Document token pricing and rate limits

### 3. Google (Gemini LLM)

**Purpose:** Alternative LLM provider, Imagen for image generation
**Environment Variables:**

- `GOOGLE_API_KEY` - API key from Google AI Studio

**Integration Points:**

- `integrations/llm/providers/google.py` - Gemini completions
- `config.py` - Provider selection (`LLM_PROVIDER`, `IMAGE_PROVIDER`)

**Setup Tutorial:**

- [ ] Create Google Cloud project or use AI Studio
- [ ] Enable Generative AI API
- [ ] Generate API key
- [ ] Configure model selection (`gemini-pro`, `gemini-1.5-pro`, etc.)
- [ ] Document quota limits

### 4. Slack (Messaging Platform)

**Purpose:** Bot integration for Slack workspace messaging
**Environment Variables:**

- `SLACK_BOT_TOKEN` - Bot OAuth token (`xoxb-...`)
- `SLACK_SIGNING_SECRET` - Request signature verification

**Integration Points:**

- `integrations/channels/adapters/slack.py` - Slack API adapter
- `api/routers/slack.py` - Event webhooks and interactive endpoints
- `config.py` - Slack client initialization

**Setup Tutorial:**

- [ ] Create Slack app at https://api.slack.com/apps
- [ ] Configure OAuth scopes (chat:write, files:write, etc.)
- [ ] Set up Event Subscriptions (message events)
- [ ] Configure Interactive Components (buttons, modals)
- [ ] Install to workspace and get bot token
- [ ] Document rate limits (1 req/sec for posting)

### 5. Hosting Platform (Generalized)

**Purpose:** Production deployment and hosting
**Environment Variables:**

- `ENVIRONMENT` - Environment name (`development`, `staging`, `production`)
- `DATA_DIR` - Base directory for persistent data (defaults to `/data/` or local)

**Integration Points:**

- `config.py` - Environment detection and path configuration
- `integrations/hosting/` - Hosting provider abstraction *(planned)*

**Supported Providers:**

- **Render** - Current production host
- **Railway** - Alternative PaaS
- **Docker/K8s** - Self-hosted option
- **Any PaaS** - With persistent storage support

**Setup Tutorial:**

- [ ] Configure environment variables in hosting dashboard
- [ ] Set up persistent storage mount for `DATA_DIR`
- [ ] Configure health check endpoint (`/health`)
- [ ] Set up auto-deploy from GitHub
- [ ] Configure custom domain and SSL

### 6. LibreOffice (Document Conversion)

**Purpose:** PPTX to PDF conversion for proposals
**System Dependency:** `libreoffice` or `soffice` binary

**Integration Points:**

- `generators/pdf.py` - PDF conversion subprocess
- `api/server.py` - Startup check for LibreOffice

**Setup Tutorial:**

- [ ] Install LibreOffice headless (`apt-get install libreoffice`)
- [ ] Verify binary is in PATH
- [ ] Test conversion with sample PPTX
- [ ] Configure fallback for systems without LibreOffice

### 7. Redis (Caching & Job Queue) - *Planned*

**Purpose:** In-memory caching, background job queue, rate limiting
**Environment Variables:**

- `REDIS_URL` - Redis connection string (e.g., `redis://localhost:6379`)
- `REDIS_PASSWORD` - Optional authentication password

**Integration Points:** *(To be implemented)*

- `utils/cache.py` - Caching layer abstraction
- `utils/job_queue.py` - Background task processing
- `api/middleware/rate_limit.py` - API rate limiting

**Setup Tutorial:**

- [ ] Install Redis locally (`brew install redis` / `apt-get install redis`)
- [ ] Configure Redis for production (memory limits, persistence)
- [ ] Set up Redis connection pooling
- [ ] Implement cache invalidation strategy
- [ ] Configure job queue workers

### 8. File Storage (Generalized) - *Planned*

**Purpose:** Cloud file storage for uploads, mockups, generated PDFs
**Environment Variables:**

- `STORAGE_PROVIDER` - Provider to use (`local`, `supabase`, `s3`)
- For Supabase: Uses existing `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`
- For S3: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET`, `AWS_REGION`

**Integration Points:** *(To be implemented)*

- `integrations/storage/base.py` - Abstract storage interface
- `integrations/storage/providers/local.py` - Local filesystem storage
- `integrations/storage/providers/supabase.py` - Supabase Storage (recommended)
- `integrations/storage/providers/s3.py` - Direct AWS S3
- `integrations/storage/client.py` - Storage client factory

**Supported Providers:**

- **Local** - Filesystem storage (dev, self-hosted)
- **Supabase Storage** - S3-compatible, recommended (already using Supabase)
- **AWS S3** - Direct S3 if needed separately

**Setup Tutorial:**

- [X] Create storage abstraction with `StorageProvider` base class
- [X] Implement `LocalStorageProvider` for development
- [X] Implement `SupabaseStorageProvider` (recommended for production)
- [ ] Create storage buckets in Supabase dashboard
- [ ] Configure bucket policies and access rules
- [X] Implement presigned URLs for secure downloads
- [ ] Set up lifecycle rules for temp files cleanup

### 9. SendGrid / Resend (Email) - *Planned*

**Purpose:** Transactional emails (proposal delivery, notifications)
**Environment Variables:**

- `SENDGRID_API_KEY` or `RESEND_API_KEY` - Email provider API key
- `EMAIL_FROM_ADDRESS` - Sender email address

**Integration Points:** *(To be implemented)*

- `integrations/email/` - Email provider abstraction
- `core/notifications.py` - Notification system

**Setup Tutorial:**

- [ ] Create SendGrid/Resend account
- [ ] Verify sender domain/email
- [ ] Create email templates
- [ ] Set up webhook for delivery status
- [ ] Configure rate limits and quotas

### 10. Sentry (Error Monitoring) - *Planned*

**Purpose:** Error tracking, performance monitoring, alerting
**Environment Variables:**

- `SENTRY_DSN` - Sentry Data Source Name

**Integration Points:** *(To be implemented)*

- `api/server.py` - Sentry SDK initialization
- Exception handlers - Automatic error capture

**Setup Tutorial:**

- [ ] Create Sentry project at https://sentry.io
- [ ] Install Sentry SDK (`pip install sentry-sdk[fastapi]`)
- [ ] Configure environment and release tracking
- [ ] Set up alert rules and notifications
- [ ] Configure performance sampling rate

---

## Priority Order for Platform Infrastructure

**High Priority (Completed):**

1. ~~`utils/time.py`~~ ✅ - Quick win, reduces duplication
2. ~~Split `api/server.py`~~ ✅ - Major maintainability improvement (1400 → 170 lines)
3. Database migrations - Critical for production (partial: added user_id migrations)

**Medium Priority (Mostly Done):**
4. Pydantic settings - Better config management
5. ~~Apply auth to endpoints~~ ✅ - Security
6. ~~Centralized error handling~~ ✅ - Better DX

**Lower Priority (Completed):**
7. ~~Structured logging~~ ✅
8. ~~Rate limiting~~ ✅
9. ~~Caching layer~~ ✅
10. ~~Background job queue~~ ✅

---

## Dev Environment Testing Checklist

> **Purpose:** Complete checklist to validate all system components before/after deployment.
> Run through this list when setting up a new dev environment or after major changes.

### Pre-Flight: Environment Setup

```bash
# 1. Copy env file and configure
cp .env.example .env
# Edit .env with your API keys (OPENAI_API_KEY, GOOGLE_API_KEY, etc.)

# 2. Check Python environment
python3 --version  # Should be 3.11+
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Check LibreOffice (for PDF conversion)
which libreoffice || which soffice  # Should return a path
```

### 1. Server Startup

- [ ] **FastAPI server starts without errors**
  ```bash
  python -m uvicorn api.server:app --host 0.0.0.0 --port 8000
  ```
  - Watch for: Import errors, missing env vars, database connection failures
  - Logs should show: `[INFO] Application startup complete`

- [ ] **Unified UI server starts**
  ```bash
  cd unified-ui && PORT=3005 node server.js
  ```

### 2. Health & Connectivity

- [ ] **Basic health check passes**
  ```bash
  curl http://localhost:8000/health
  ```
  - Expected: `{"status": "healthy", ...}`

- [ ] **Readiness check shows all dependencies**
  ```bash
  curl http://localhost:8000/health/ready
  ```
  - Expected: Shows database, Slack, LLM provider status
  - Watch for: Any `"status": "unhealthy"` components

### 3. Database & Migrations

- [ ] **Migration status check**
  ```bash
  python -m db.migrations status
  ```
  - Expected: Shows applied/pending migrations

- [ ] **Run pending migrations**
  ```bash
  python -m db.migrations migrate
  ```
  - Watch for: SQL errors, constraint violations

- [ ] **Database tables exist** (check via SQLite)
  ```bash
  sqlite3 data/app.db ".tables"
  ```
  - Expected: `ai_costs`, `proposals_log`, `users`, `roles`, `permissions`, `_migrations`

### 4. Authentication Flow

- [ ] **Unauthenticated request is rejected**
  ```bash
  curl http://localhost:8000/api/chat/conversations
  ```
  - Expected: 401 Unauthorized with `AUTHENTICATION_REQUIRED` error

- [ ] **Local auth login works** (if AUTH_PROVIDER=local)
  ```bash
  curl -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email": "admin@example.com", "password": "admin123"}'
  ```
  - Expected: Returns JWT access token

- [ ] **Authenticated request succeeds**
  ```bash
  curl http://localhost:8000/api/chat/conversations \
    -H "Authorization: Bearer <token_from_login>"
  ```
  - Expected: 200 OK with conversations list

### 5. API Key Authentication

- [ ] **API key validation works**
  ```bash
  # Set an API key in .env: API_KEY_TEST=mykey123:read,write
  curl http://localhost:8000/api/chat/conversations \
    -H "X-API-Key: mykey123"
  ```

### 6. LLM Integration

- [ ] **OpenAI connection** (if LLM_PROVIDER=openai)
  - Send a chat message, watch logs for:
    - `[LLM] Using provider: openai`
    - `[LLM] Completion successful`
  - Watch for: API key errors, rate limits, model not found

- [ ] **Google Gemini connection** (if LLM_PROVIDER=google)
  - Same as above with `google` in logs

- [ ] **Image generation works** (if IMAGE_PROVIDER is set)
  - Trigger mockup generation, check logs for:
    - `[IMAGE] Generating with provider: ...`
    - `[IMAGE] Generation successful`

### 7. Proposal Generation Flow

- [ ] **Full proposal generation**
  1. Start a chat conversation
  2. Request a proposal with location + media types
  3. Watch logs for each step:
     - `[PROPOSAL] Starting generation`
     - `[LLM] Parsing media specifications`
     - `[TEMPLATE] Loading template for location`
     - `[PPTX] Generating presentation`
     - `[PDF] Converting to PDF`
  4. Verify PDF is generated in `data/proposals/`

- [ ] **Template loading works**
  - Check logs for template-related errors
  - Missing templates should show clear error messages

### 8. Mockup Generation

- [ ] **Mockup generation pipeline**
  1. Request a mockup via API or UI
  2. Watch for:
     - `[MOCKUP] Starting generation`
     - `[EFFECTS] Applying...`
     - `[MOCKUP] Complete`
  3. Verify output image exists

### 9. Caching Layer

- [ ] **Cache operations logged**
  - Look for `[CACHE]` log entries on startup
  - Expected: `[CACHE] Using memory backend` or `[CACHE] Using Redis backend`

- [ ] **Cache hit/miss visible** (when LOG_LEVEL=DEBUG)
  ```bash
  LOG_LEVEL=DEBUG python -m uvicorn api.server:app ...
  ```
  - Look for cache hit/miss statistics

### 10. Rate Limiting

- [ ] **Rate limiting works** (if RATE_LIMIT_ENABLED=true)
  ```bash
  # Rapid requests should trigger rate limit
  for i in {1..20}; do curl http://localhost:8000/health; done
  ```
  - Expected: 429 Too Many Requests after limit exceeded

### 11. Background Jobs

- [ ] **Job queue operations logged**
  - Look for `[JOB_QUEUE]` entries during long operations
  - Job completion should show duration

### 12. File Operations

- [ ] **File uploads work**
  - Upload an image via mockup UI
  - Check `data/uploads/` for file

- [ ] **File serving works**
  - Access a generated file URL
  - Should download correctly

### 13. Slack Integration (if configured)

- [ ] **Slack events received**
  - Send a message to the bot
  - Watch for `[SLACK] Received event`

- [ ] **Slack responses sent**
  - Bot should reply
  - Watch for `[SLACK] Sent message`

### 14. Error Visibility

> **Concerning silent failures?** Here's what to watch:

**Errors that ARE logged (you will see them):**
- All HTTP 4xx/5xx responses → `[API ERROR]` or `[UNHANDLED ERROR]`
- Database errors → `[DB]` errors
- LLM failures → `[LLM]` errors with full traceback
- File I/O errors → Python exceptions logged
- Validation errors → `[VALIDATION ERROR]`

**Potential silent failure points (watch carefully):**
- [ ] **Cache misses silently fall back** - Cache errors return None, not exceptions
  - Mitigation: Enable DEBUG logging to see `[CACHE]` miss logs
- [ ] **Redis connection failures** - Falls back to memory silently
  - Mitigation: Check startup logs for `[CACHE] Using memory backend` when Redis expected
- [ ] **Background job failures** - Logged but job may be forgotten
  - Mitigation: Check job queue stats at `/health/ready`
- [ ] **LLM response parsing** - Malformed JSON from LLM may fail silently
  - Mitigation: Look for `[LLM] Parse error` in logs

**Recommended log monitoring:**
```bash
# Run with debug logging to see everything
LOG_LEVEL=DEBUG python -m uvicorn api.server:app --port 8000 2>&1 | tee app.log

# In another terminal, watch for errors:
tail -f app.log | grep -E "(ERROR|WARNING|FAILED|Exception)"
```

### 15. Quick Smoke Test Script

Run this after environment setup:
```bash
#!/bin/bash
set -e

echo "=== Health Check ==="
curl -s http://localhost:8000/health | jq .

echo "=== Auth Test ==="
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "admin123"}' | jq -r '.access_token')
echo "Got token: ${TOKEN:0:20}..."

echo "=== Authenticated Request ==="
curl -s http://localhost:8000/api/chat/conversations \
  -H "Authorization: Bearer $TOKEN" | jq .

echo "=== Migration Status ==="
python -m db.migrations status

echo "=== All checks passed! ==="
```

### Common Issues & Solutions

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| `OPENAI_API_KEY not set` | Missing env var | Check `.env` file exists and is loaded |
| `unable to open database file` | Missing data directory | Run `mkdir -p data` |
| `No module named 'xxx'` | Missing dependency | Run `pip install -r requirements.txt` |
| `LibreOffice not found` | PDF conversion disabled | Install LibreOffice or skip PDF tests |
| `Connection refused :8000` | Server not running | Start with uvicorn command |
| `401 Unauthorized` on all requests | Auth misconfigured | Check AUTH_PROVIDER and user setup |
| `Redis connection failed` | Redis not running | Install/start Redis or use memory backend |

---

## Post-V1 Infrastructure Enhancements

> **Note:** These items should be implemented AFTER V1 testing is complete.
> Order reflects implementation priority based on dependencies and value.

### 1. Audit Logging (`utils/audit.py`) - **COMPLETED**
Foundation for compliance and debugging. Required before other features.
- [X] `AuditEvent` dataclass (who, what, when, where, details)
- [X] `AuditLogger` class with async logging
- [X] Database table for audit records (already in schema)
- [X] Decorator `@audit_action("action_name")` for endpoints
- [X] Track: user management, role changes, permission changes, login attempts
- [ ] Retention policy configuration (future enhancement)

### 2. Scheduled Tasks (`utils/scheduler.py`)
Build on existing `job_queue.py` for recurring tasks.
- [ ] Cron-like scheduler abstraction
- [ ] Built-in tasks: temp file cleanup, old log rotation
- [ ] Task registration system
- [ ] Admin UI for viewing scheduled tasks
- [ ] Graceful shutdown handling

### 3. Export Utilities (`utils/export.py`)
Data export for reporting needs.
- [ ] CSV export for proposals, costs, users
- [ ] Excel export with formatting
- [ ] PDF report generation (summary reports)
- [ ] Export job queue (async for large datasets)
- [ ] Download endpoint with auth

### 4. Webhook System (`integrations/webhooks/`)
For external integrations when needed.
- [ ] `WebhookProvider` base class
- [ ] Outbound webhook delivery with retries
- [ ] Webhook signature generation (HMAC)
- [ ] Event subscription management
- [ ] Delivery status tracking and retry queue
- [ ] Admin UI for webhook management

### 5. Error Monitoring (Sentry Integration)
Production observability.
- [ ] Sentry SDK integration
- [ ] Environment and release tagging
- [ ] User context attachment
- [ ] Performance monitoring sampling
- [ ] Alert configuration

### 6. API Versioning (when breaking changes needed)
- [ ] `/api/v1/` route prefix structure
- [ ] Version negotiation via header
- [ ] Deprecation warning headers
- [ ] Migration documentation template

---

## Progress Log

> **How to add entries:**
> - Use format: `### [Date] - [Short Title]`
> - Start with what was done (bullet points, keep it brief)
> - End with **Impact:** one-liner on why it matters
> - Link to detailed docs if needed (e.g., `WEEKEND_UPDATE.md`)
> - Keep entries scannable - your future self will thank you

### Dec 6-7, 2024 - Infrastructure Sprint
See [RELEASE_NOTES.md](RELEASE_NOTES.md) for full details.

- Security overhaul (JWT auth, RBAC, API keys, security headers)
- Architecture refactor (1,400-line monolith → modular routers)
- Database abstraction (SQLite + Supabase backends)
- CI/CD pipelines (GitHub Actions + GitLab CI)
- Multi-LLM support (OpenAI + Google Gemini)
- Test infrastructure (pytest, fixtures, coverage)

**Impact:** Prototype → production-ready platform

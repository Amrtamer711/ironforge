# CRM Platform - Comprehensive Testing Plan

> **Created**: 2024-12-22
> **Status**: In Progress
> **Priority**: High

---

## Executive Summary

This plan outlines the systematic testing and integration work required to bring the CRM platform to full production readiness. The work is divided into 7 phases, each building on the previous.

---

## Phase 1: Supabase Schema Completion
**Priority: Critical | Estimated: 2-3 days**

### 1.1 Asset Management Supabase Setup
- [ ] Create Supabase project for Asset Management (or use existing)
- [ ] Write migration script (`src/asset-management/db/migrations/01_schema.sql`)
- [ ] Tables to create:
  - [ ] `networks` (id, company_id, name, description, created_at)
  - [ ] `asset_types` (id, company_id, name, specs, pricing_model)
  - [ ] `locations` (id, network_id, type_id, name, address, coordinates, status)
  - [ ] `packages` (id, company_id, name, description, pricing)
  - [ ] `package_items` (id, package_id, location_id, quantity)
  - [ ] `rate_cards` (id, company_id, asset_type_id, rates_json)
  - [ ] `mockup_frames` (id, location_id, frame_specs, preview_url)
  - [ ] `location_photos` (id, location_id, url, type, uploaded_at)
  - [ ] `location_occupations` (id, location_id, proposal_id, start_date, end_date)
- [ ] Add Supabase backend to `db/backends/supabase.py`
- [ ] Add environment variables to `.env.example`
- [ ] Test connection and CRUD operations

### 1.2 Security Service Supabase Completion
- [ ] Verify/create Supabase project for Security Service
- [ ] Complete migration script with missing tables:
  - [ ] `security_events` (severity, resolution tracking)
  - [ ] `api_key_audit` (rotation history, usage patterns)
  - [ ] `rate_limit_violations` (tracking blocked requests)
- [ ] Populate `permission_sets` table (currently empty per TODO)
- [ ] Add integration with UI Supabase for user context

### 1.3 Chat Persistence Fix
- [ ] Create `chat_messages` table in Sales Supabase:
  ```sql
  CREATE TABLE chat_messages (
    id UUID PRIMARY KEY,
    session_id UUID REFERENCES chat_sessions(id),
    role TEXT NOT NULL, -- 'user' | 'assistant'
    content TEXT NOT NULL,
    tool_calls JSONB,
    parent_id UUID, -- for parallel request tracking
    created_at TIMESTAMPTZ DEFAULT NOW()
  );
  CREATE INDEX idx_messages_session ON chat_messages(session_id);
  ```
- [ ] Migrate existing JSONB messages to new table
- [ ] Update `chat_persistence.py` to use new table
- [ ] Add conversation cleanup job

---

## Phase 2: Service Integration Testing
**Priority: Critical | Estimated: 3-4 days**

### 2.1 Sales Module ↔ Asset Management
- [ ] Verify eligibility endpoint works (`/api/eligibility/check`)
- [ ] Test location lookups from proposals
- [ ] Test package retrieval for pricing
- [ ] Add caching layer for location data
- [ ] Add fallback behavior when Asset service is down
- [ ] Test rate card integration for proposal pricing

### 2.2 Sales Module ↔ Security Service
- [ ] Enable audit logging for all proposal operations
- [ ] Test API key validation flow
- [ ] Verify rate limiting integration
- [ ] Test cost tracking persistence
- [ ] Add security event logging for sensitive actions

### 2.3 Unified UI ↔ Sales Module
- [ ] Test chat API streaming endpoint
- [ ] Verify file upload through chat
- [ ] Test conversation persistence and recovery
- [ ] Verify RBAC context passed correctly
- [ ] Test session management

### 2.4 Cross-Service Authentication
- [ ] Verify trusted headers pass through correctly
- [ ] Test service-to-service authentication
- [ ] Verify RBAC context propagation
- [ ] Test multi-company access scenarios

---

## Phase 3: AI Chat Full Functionality
**Priority: High | Estimated: 4-5 days**

### 3.1 Core Chat Operations
- [ ] Test basic message/response flow
- [ ] Test streaming responses (SSE)
- [ ] Test parallel request handling
- [ ] Test conversation context maintenance
- [ ] Test file attachments (PDF, images)

### 3.2 Proposal Generation
- [ ] Test proposal creation via chat
- [ ] Verify location eligibility checks work
- [ ] Test pricing calculation with rate cards
- [ ] Test PDF generation
- [ ] Test proposal storage and retrieval
- [ ] Verify proposal audit trail

### 3.3 Mockup Generation
- [ ] Test mockup request parsing
- [ ] Verify frame selection from Asset Management
- [ ] Test image generation pipeline
- [ ] Test mockup storage
- [ ] Verify file serving

### 3.4 Asset Queries
- [ ] Test location availability queries
- [ ] Test network/package lookups
- [ ] Test pricing inquiries
- [ ] Test multi-company asset access
- [ ] Verify RBAC filters apply correctly

### 3.5 Booking Orders
- [ ] Test BO creation from proposals
- [ ] Verify approval workflow triggers
- [ ] Test status updates
- [ ] Verify location occupation tracking

---

## Phase 4: Admin Panel Testing
**Priority: High | Estimated: 2-3 days**

### 4.1 User Management
- [ ] Test user listing with pagination
- [ ] Test pending user approval flow
- [ ] Test user creation (pre-SSO)
- [ ] Test user deactivation (with force logout)
- [ ] Test profile assignment
- [ ] Test team assignment
- [ ] Verify audit logging for all actions

### 4.2 Profile Management
- [ ] Test profile listing
- [ ] Verify permission display
- [ ] Test profile assignment to users

### 4.3 Team Management
- [ ] Test team listing
- [ ] Test team hierarchy display
- [ ] Test user assignment to teams

### 4.4 Company Management
- [ ] Test company hierarchy display
- [ ] Test user-company assignments
- [ ] Verify multi-company access

### 4.5 Module Access
- [ ] Test module listing
- [ ] Test module assignment to users
- [ ] Verify feature gating works

### 4.6 Admin Security
- [ ] Verify only system_admin can access
- [ ] Test permission boundary enforcement
- [ ] Verify can't self-deactivate
- [ ] Test audit trail completeness

---

## Phase 5: Local Development & Data Sync
**Priority: Medium | Estimated: 2 days**

### 5.1 Data Sync Verification
- [ ] Test `sync_from_supabase.py` for UI database
- [ ] Test sync for Sales database
- [ ] Test sync for company-specific schemas
- [ ] Add sync support for Asset Management
- [ ] Add sync support for Security Service
- [ ] Test storage bucket sync (proposals, mockups)

### 5.2 Local Service Runner
- [ ] Verify all 4 services start correctly
- [ ] Test WebSocket log streaming
- [ ] Verify logs panel displays correctly
- [ ] Test port cleanup on restart
- [ ] Verify health checks work

### 5.3 Environment Replication
- [ ] Document all required environment variables
- [ ] Create `.env.example` with all variables
- [ ] Test fresh clone → run workflow
- [ ] Verify SQLite fallback works for all services
- [ ] Test Supabase connection validation

### 5.4 Dev Panel Testing
- [ ] Test persona impersonation
- [ ] Test permission toggling
- [ ] Test company access toggling
- [ ] Verify changes reflect in RBAC

---

## Phase 6: RBAC Comprehensive Testing
**Priority: High | Estimated: 3-4 days**

### 6.1 Profile-Based Access
| Scenario | Test |
|----------|------|
| system_admin | Full access to all features |
| sales_manager | Manage proposals, view team data |
| sales_user | Create/edit own proposals only |
| coordinator | Read-only proposal access |
| finance | Access to cost/financial data |
| viewer | Read-only everywhere |

### 6.2 Permission Set Testing
- [ ] Test additive permissions work
- [ ] Test permission expiration
- [ ] Test conflicting permission resolution
- [ ] Test wildcard permissions (`*:*:*`)

### 6.3 Company Access Testing
- [ ] Test single company access
- [ ] Test multi-company access
- [ ] Test parent company → child access inheritance
- [ ] Test cross-company data isolation
- [ ] Test company switching in UI

### 6.4 Team-Based Access
- [ ] Test team member access
- [ ] Test team leader extended access
- [ ] Test team hierarchy inheritance
- [ ] Test sharing rules by team

### 6.5 Record-Level Sharing
- [ ] Test individual record sharing
- [ ] Test shared record expiration
- [ ] Test access level enforcement (view/edit/admin)

### 6.6 Permission Escalation/De-escalation
- [ ] Test upgrading user profile
- [ ] Test downgrading user profile
- [ ] Verify cache invalidation works
- [ ] Test moving users between teams
- [ ] Test removing company access
- [ ] Test adding company access

### 6.7 Edge Cases
- [ ] Test user with no companies assigned
- [ ] Test user with expired permissions
- [ ] Test deactivated user cleanup
- [ ] Test concurrent permission changes

---

## Phase 7: Form-Based Tools Testing
**Priority: Low (Pending Frontend) | Estimated: 3-4 days**

> **Note**: This phase depends on frontend updates from other engineer

### 7.1 Proposal Form
- [ ] Test form validation
- [ ] Test location selection
- [ ] Test pricing calculation preview
- [ ] Test draft saving
- [ ] Test submission flow
- [ ] Test PDF preview

### 7.2 Mockup Generator Form
- [ ] Test location selection
- [ ] Test frame selection
- [ ] Test image upload
- [ ] Test generation preview
- [ ] Test bulk generation

### 7.3 Booking Order Form
- [ ] Test BO creation from proposal
- [ ] Test manual BO creation
- [ ] Test approval workflow triggers
- [ ] Test status updates

---

## Test Environment Checklist

### Required Supabase Projects
- [ ] `unified-ui` (RBAC, users, companies)
- [ ] `sales-module` (proposals, chat, costs)
- [ ] `asset-management` (locations, packages)
- [ ] `security-service` (audit, API keys)

### Required Environment Variables
```bash
# UI Supabase
UI_SUPABASE_URL=
UI_SUPABASE_SERVICE_KEY=

# Sales Supabase
SALESBOT_DEV_SUPABASE_URL=
SALESBOT_DEV_SUPABASE_SERVICE_KEY=

# Asset Management Supabase
ASSETMGMT_SUPABASE_URL=
ASSETMGMT_SUPABASE_SERVICE_KEY=

# Security Service Supabase
SECURITY_SUPABASE_URL=
SECURITY_SUPABASE_SERVICE_KEY=

# AI Providers
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_GENAI_API_KEY=

# Storage
SUPABASE_STORAGE_URL=
```

### Test Data Requirements
- [ ] At least 2 companies with hierarchy
- [ ] Users in each profile type
- [ ] Sample proposals in various states
- [ ] Sample locations with availability
- [ ] Sample packages and rate cards

---

## Progress Tracking

| Phase | Status | Started | Completed | Notes |
|-------|--------|---------|-----------|-------|
| 1. Supabase Schema | Not Started | - | - | |
| 2. Service Integration | Not Started | - | - | |
| 3. AI Chat | Not Started | - | - | |
| 4. Admin Panel | Not Started | - | - | |
| 5. Local Dev | Not Started | - | - | |
| 6. RBAC Testing | Not Started | - | - | |
| 7. Form Tools | Blocked | - | - | Pending frontend |

---

## Known Issues to Fix

### Critical
1. `RATE_LIMIT_DEFAULT` missing in Security Service settings
2. Chat messages not persisted to indexed table
3. Asset Management has no RBAC enforcement

### High
4. Email notifications not implemented (invite flow broken)
5. Location occupancy not tracked
6. Security events not correlated

### Medium
7. Viola locations not in BO parsing
8. Pagination count query incorrect
9. No conversation cleanup job

---

## Success Criteria

### Phase 1-2 Complete When:
- [ ] All Supabase schemas deployed
- [ ] All services can connect to their databases
- [ ] Cross-service calls work end-to-end

### Phase 3 Complete When:
- [ ] User can have full conversation via web chat
- [ ] Proposals can be generated with correct pricing
- [ ] Mockups can be generated and viewed
- [ ] All operations have audit trail

### Phase 4 Complete When:
- [ ] Admin can manage all users
- [ ] RBAC changes take effect immediately
- [ ] All admin actions logged

### Phase 5 Complete When:
- [ ] Fresh dev can clone and run in < 10 minutes
- [ ] All data syncs correctly
- [ ] Local testing matches production behavior

### Phase 6 Complete When:
- [ ] All 6 profile types tested
- [ ] Multi-company scenarios work
- [ ] Permission changes propagate correctly

### Phase 7 Complete When:
- [ ] Forms work equivalent to chat
- [ ] All validation in place
- [ ] Error handling complete

---

## Next Steps

1. **Start Phase 1.1**: Create Asset Management Supabase schema
2. **Fix Critical Bug**: Add `RATE_LIMIT_DEFAULT` to Security Service settings
3. **Parallel**: Begin Phase 2 testing for already-connected services

# Backlog

This document tracks security fixes, infrastructure improvements, and feature work.

---

## ⚠️ IMPORTANT: Context Labels

Each item in this backlog is tagged with its relevance:

| Tag | Meaning |
|-----|---------|
| 🏢 **Enterprise** | Only needed for large-scale deployments (1000+ users, high availability) |
| 🚀 **Growth** | Useful when scaling up (100-1000 users, multiple instances) |
| ✅ **Essential** | Required for production (security, stability, core functionality) |
| 🎯 **Your Setup** | Directly relevant to Sales Proposal Bot on Render + Supabase |

**Your Current Setup:**
- Hosting: Render (single instance)
- Database: Supabase (PostgreSQL)
- Users: <50 internal users
- Scale: Single-tenant, internal tool

**Skip items tagged 🏢 Enterprise unless you're planning significant growth.**

---

## 🔴 HIGH Priority - Security (Fix Immediately)

### 1. Missing Rate Limiting on Auth Endpoints ✅ Essential 🎯 Your Setup ✅ DONE
- **File:** `app_settings/settings.py`
- **Fix Applied:** Changed `rate_limit_enabled` default to `True`

### 2. Secrets with Empty Defaults ✅ Essential 🎯 Your Setup ✅ DONE
- **File:** `app_settings/settings.py`
- **Fix Applied:** Added `validate_production_secrets()` that runs at startup

### 3. Fallback to Dev Auth in Production ✅ Essential 🎯 Your Setup ✅ DONE
- **File:** `integrations/auth/client.py`
- **Fix Applied:** `from_config()` raises `RuntimeError` in production if not set

---

## 🟠 MEDIUM Priority - Security

### 4. JWT Decode Without Verification ✅ Essential
- **File:** `integrations/auth/providers/supabase.py:599-617`
- **Issue:** `decode_token()` uses `verify_signature=False`
- **Risk:** Could be misused for authorization decisions
- **Fix:** Add explicit warnings, require opt-in parameter
- [ ] **TODO**

### 5. Insufficient Email Validation ✅ Essential 🎯 Your Setup ✅ DONE
- **File:** `unified-ui/server.js`
- **Fix Applied:** Added `EMAIL_REGEX` and `isValidEmail()` function

### 6. No Chat Message Length Limit ✅ Essential 🎯 Your Setup ✅ DONE
- **File:** `api/routers/chat.py`
- **Fix Applied:** Added `MAX_MESSAGE_LENGTH = 10_000` with Pydantic validator

### 7. CORS Wide Open in unified-ui ✅ Essential 🎯 Your Setup ✅ DONE
- **File:** `unified-ui/server.js`
- **Fix Applied:** Added `ALLOWED_ORIGINS` with env-specific config, `corsOptions`

### 8. X-Forwarded-For Header Trust 🚀 Growth
- **File:** `unified-ui/server.js:125-129`
- **Issue:** Trusts `X-Forwarded-For` without proxy validation
- **Risk:** IP spoofing for rate limit bypass
- **Fix:** Only trust header from known proxy IPs (Render's IPs)
- [ ] **TODO**

### 9. Generic Exception Handler Disabled ✅ Essential 🎯 Your Setup ✅ DONE
- **File:** `api/exceptions.py`
- **Fix Applied:** Enabled catch-all exception handler

### 10. Outdated Dependencies ✅ Essential 🎯 Your Setup ✅ DONE
- **File:** `requirements.txt`
- **Fix Applied:** Updated `aiohttp>=3.9.5`, `reportlab>=4.0.9`, `psutil>=6.0.0`

### 11. File Download Path Validation ✅ Essential 🎯 Your Setup
- **File:** `api/routers/files.py:22-95`
- **Issue:** Filename from URL not validated against stored metadata
- **Risk:** Potential path traversal if backend doesn't validate
- **Fix:** Validate filename matches stored file metadata
- [ ] **TODO**

### 12. DB Fallback to SQLite Silently ✅ Essential 🎯 Your Setup ✅ DONE
- **File:** `db/database.py`
- **Fix Applied:** Raises `RuntimeError` in production if Supabase credentials missing

### 13. Profile Name Echo in Error Message ✅ Essential ✅ DONE
- **File:** `unified-ui/server.js`
- **Fix Applied:** Changed to generic error message without echoing user input

### 14. Content-Type Validation in File Uploads ✅ Essential 🎯 Your Setup
- **File:** `core/chat_api.py:112-125`
- **Issue:** Uses `.startswith("image/")` for MIME check
- **Risk:** Could match malformed MIME types like `image/jpeg; x-malware`
- **Fix:** Use exact MIME type whitelist
- [ ] **TODO**

### 15. Missing Security Headers (Helmet) ✅ Essential 🎯 Your Setup ✅ DONE
- **File:** `unified-ui/server.js`, `unified-ui/package.json`
- **Fix Applied:** Added `helmet` middleware with CSP configuration

### 16. Excessive Body Size Limit ✅ Essential 🎯 Your Setup ✅ DONE
- **File:** `unified-ui/server.js`
- **Fix Applied:** Reduced to 10MB (file uploads go through proxy, bypassing bodyParser)

---

## 🟢 LOW Priority - Security

### 17. Unprotected Health Endpoints 🚀 Growth
- **File:** `api/routers/health.py:102-120`
- **Issue:** Detailed health endpoints expose internal config
- **Risk:** Information disclosure (LLM provider, DB type, etc.)
- **Fix:** Require auth for detailed endpoints, keep `/health` simple
- [ ] **TODO**

### 18. Temp Files Not Cleaned on Error ✅ Essential 🎯 Your Setup ✅ DONE
- **Files:** `core/file_utils.py`, `generators/mockup.py`
- **Fix Applied:** Added try/finally blocks with `shutil.rmtree` cleanup

### 19. Service URLs in Proxy Logs 🚀 Growth
- **File:** `unified-ui/server.js:113-118`
- **Issue:** Logs expose internal service URLs and architecture
- **Risk:** Information disclosure in logs
- **Fix:** Reduce logging verbosity in production
- [ ] **TODO**

### 20. Error Details Exposed in Proxy ✅ Essential 🎯 Your Setup ✅ DONE
- **File:** `unified-ui/server.js`
- **Fix Applied:** Proxy and generic error handlers now hide details in production

---

## 🔵 Features - Web Chat File Uploads

### 47. File Upload Support for Web Chat ✅ Essential 🎯 Your Setup ✅ DONE
- **Files modified:**
  - `api/routers/files.py` - Added `POST /api/files/upload` and `/upload/multi` endpoints
  - `api/routers/chat.py` - Added `file_ids` field to chat request, resolves to file metadata
  - `core/chat_api.py` - Already handled files param (appends file context to LLM message)
- **Max file size:** 200MB
- **Allowed types:** Images (.jpg, .png, .gif, etc.) and documents (.pdf, .xlsx, .docx, .pptx, etc.)

### 48. File Download Endpoint for Chat Attachments ✅ Essential 🎯 Your Setup ✅ DONE
- **Status:** Already working
- **File:** `api/routers/files.py`
- **Features:**
  - Auth required for all file access
  - Supabase Storage: redirects to signed URLs
  - Local storage: serves via FileResponse
  - Handles both generated files and user uploads

---

## 🔵 Features - Chat Persistence (COMPLETED - Basic)

### 21. Chat History Persistence ✅
- **Status:** COMPLETED (Basic JSON blob approach)
- **Files:** `core/chat_persistence.py`, `db/backends/supabase.py`
- **Current Implementation:**
  - Single JSON blob per user in `chat_sessions` table
  - Full rewrite on each message
  - Works for ~100 messages per user

### 22. Chat History API Endpoint ✅
- **Status:** COMPLETED
- **File:** `api/routers/chat.py`
- **Endpoint:** `GET /api/chat/history`

### 23. WebAdapter Persistence Integration ✅
- **Status:** COMPLETED
- **Files:** `core/chat_api.py`
- **Implementation:** Load on session start, save after each exchange

---

## 🟣 Infrastructure - Redis Integration

### 24. Redis Setup & Configuration 🚀 Growth
- **Priority:** HIGH (when scaling to multiple instances)
- **Files to create:** `integrations/cache/`, `app_settings.py`
- **Why you need it:** Required for horizontal scaling, faster session access
- **Requirements:**
  - Add `redis` to requirements.txt
  - Create Redis client wrapper with connection pooling
  - Environment variables: `REDIS_URL`, `REDIS_PASSWORD`
  - Health check endpoint for Redis
  - Graceful fallback if Redis unavailable
- [ ] **TODO**

### 25. Session Cache in Redis 🚀 Growth
- **Priority:** HIGH (when scaling to multiple instances)
- **Files:** `core/chat_api.py`, `integrations/channels/adapters/web.py`
- **Why you need it:** Current in-memory sessions don't work with multiple instances
- **Requirements:**
  - Store active WebAdapter sessions in Redis
  - TTL-based expiration (e.g., 24 hours of inactivity)
  - Enable horizontal scaling (multiple API instances)
  - Key pattern: `session:{user_id}`
- [ ] **TODO**

### 26. Rate Limiting with Redis 🚀 Growth
- **Priority:** HIGH (when scaling to multiple instances)
- **Files:** `api/middleware/`, `unified-ui/server.js`
- **Why you need it:** In-memory rate limits only work per-instance
- **Requirements:**
  - Replace in-memory rate limit store with Redis
  - Sliding window algorithm for accuracy
  - Per-user and per-IP limits
  - Shared state across instances
- [ ] **TODO**

### 27. LLM Response Caching 🎯 Your Setup (Cost Savings)
- **Priority:** MEDIUM
- **Files:** `integrations/llm/client.py`
- **Why you need it:** Save money on repeated identical LLM calls
- **Requirements:**
  - Cache identical prompts/responses
  - Content-addressable keys (hash of prompt)
  - Short TTL (5-15 minutes) to balance freshness vs cost
  - Cache hit metrics
- [ ] **TODO**

### 28. Distributed Locking 🏢 Enterprise
- **Priority:** LOW (only for multi-instance)
- **Files:** `integrations/cache/locks.py`
- **Why you need it:** Prevent race conditions when running multiple instances
- **Requirements:**
  - Redlock for distributed mutex
  - Use for: BO reference generation, file processing
  - Prevent race conditions across instances
- [ ] **TODO**

---

## 🟣 Infrastructure - Chat Architecture (Enterprise Scale)

### 29. Normalize Chat Schema (Phase 1) 🚀 Growth
- **Priority:** MEDIUM (when conversations get long or need multiple per user)
- **Files:** `db/schema.py`, `db/migrations/`, `db/backends/`
- **Why you need it:** Current JSON blob rewrites entire conversation on each message
- **Current:** Single JSON blob per user
- **Target Schema:**
```sql
-- Conversations (multiple per user)
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    title TEXT,                          -- Auto-generated or user-set
    model TEXT,                          -- LLM model used
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    archived_at TIMESTAMPTZ,             -- Soft delete
    metadata JSONB DEFAULT '{}'          -- Extensible
);
CREATE INDEX idx_conversations_user ON conversations(user_id, updated_at DESC);

-- Individual messages (append-only)
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT,
    tool_calls JSONB,                    -- For assistant tool calls
    tool_call_id TEXT,                   -- For tool responses
    attachments JSONB DEFAULT '[]',      -- Files, images
    tokens_used INTEGER,                 -- For cost tracking
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);
CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at);
CREATE INDEX idx_messages_created ON messages(created_at);
```
- **Migration Strategy:**
  1. Create new tables alongside existing
  2. Dual-write during transition
  3. Backfill existing data
  4. Switch reads to new tables
  5. Drop old table
- [ ] **TODO**

### 30. Message Append-Only Writes 🚀 Growth
- **Priority:** MEDIUM (after schema migration)
- **Files:** `core/chat_persistence.py`, `db/backends/`
- **Why you need it:** Current full-rewrite is slow for long conversations
- **Requirements:**
  - INSERT single message row (not full conversation rewrite)
  - ~10x faster writes
  - Enables real-time sync
- [ ] **TODO**

### 31. Conversation Management API 🚀 Growth
- **Priority:** LOW (nice to have for UX)
- **Files:** `api/routers/chat.py`
- **Why you need it:** Allow users to have multiple chat threads
- **New Endpoints:**
  - `GET /api/conversations` - List user's conversations
  - `POST /api/conversations` - Create new conversation
  - `GET /api/conversations/{id}` - Get conversation with messages
  - `PATCH /api/conversations/{id}` - Update title, archive
  - `DELETE /api/conversations/{id}` - Soft delete
  - `GET /api/conversations/{id}/messages` - Paginated messages
- [ ] **TODO**

### 32. Pagination & Infinite Scroll 🚀 Growth
- **Priority:** LOW (only if conversations get very long)
- **Files:** `api/routers/chat.py`, `core/chat_persistence.py`
- **Why you need it:** Loading 500+ messages at once is slow
- **Requirements:**
  - Cursor-based pagination (not offset)
  - Load latest N messages initially
  - Load more on scroll up
  - Return: `{ messages, next_cursor, has_more }`
- [ ] **TODO**

### 33. Redis + Postgres Hybrid (Write-Behind Cache) 🏢 Enterprise
- **Priority:** LOW (complex, only for high traffic)
- **Files:** `core/chat_persistence.py`, `integrations/cache/`
- **Why you need it:** Sub-millisecond reads for very high traffic
- **Architecture:**
```
┌─────────┐     ┌─────────┐     ┌──────────┐
│ Browser │────▶│  Redis  │────▶│ Postgres │
└─────────┘     │ (cache) │     │ (durable)│
                └─────────┘     └──────────┘
                     │
              Write-behind queue
              (async persist)
```
- **Requirements:**
  - Write to Redis immediately (fast response)
  - Async worker persists to Postgres
  - Read from Redis if available, else Postgres
  - Handle Redis failures gracefully
- [ ] **TODO**

### 34. Message Search (Full-Text) 🏢 Enterprise
- **Priority:** LOW (nice to have)
- **Files:** `db/backends/supabase.py`, `api/routers/chat.py`
- **Why you need it:** Search through past conversations
- **Requirements:**
  - Postgres full-text search on message content
  - `GET /api/conversations/search?q=proposal`
  - GIN index on content column
  - Highlight matching terms in results
- [ ] **TODO**

### 35. Conversation Summarization 🏢 Enterprise
- **Priority:** LOW (nice to have)
- **Files:** `core/chat_api.py`
- **Why you need it:** Auto-title conversations, reduce context window
- **Requirements:**
  - Auto-generate conversation titles using LLM
  - Summarize long conversations for context window
  - Store summary in conversation metadata
- [ ] **TODO**

---

## 🟣 Infrastructure - Observability & Monitoring

### 36. Structured Logging 🚀 Growth
- **Priority:** MEDIUM (helpful for debugging production issues)
- **Files:** `utils/logging.py`, all modules
- **Why you need it:** Better debugging, easier log analysis in Render
- **Requirements:**
  - JSON-formatted logs for production
  - Correlation IDs across requests
  - Log levels: DEBUG (dev), INFO (prod)
  - Include: user_id, request_id, duration, status
- [ ] **TODO**

### 37. Metrics & Dashboards 🏢 Enterprise
- **Priority:** LOW (overkill for small team)
- **Files:** `api/middleware/`, `integrations/`
- **Why you need it:** Proactive monitoring, SLA tracking
- **Metrics to track:**
  - Request latency (p50, p95, p99)
  - LLM response times
  - Cache hit rates (Redis)
  - Error rates by endpoint
  - Active users (DAU/MAU)
  - Token usage per user
- **Tools:** Prometheus + Grafana or Datadog
- [ ] **TODO**

### 38. Distributed Tracing 🏢 Enterprise
- **Priority:** LOW (only for microservices)
- **Files:** `api/middleware/`
- **Why you need it:** Debug complex multi-service requests
- **Requirements:**
  - OpenTelemetry integration
  - Trace requests across services
  - Visualize in Jaeger/Zipkin
- [ ] **TODO**

### 39. Alerting 🚀 Growth
- **Priority:** MEDIUM (when you can't watch logs manually)
- **Why you need it:** Get notified when things break
- **Requirements:**
  - Error rate > 5% → Alert
  - P95 latency > 5s → Alert
  - Redis/DB connection failures → Alert
  - LLM API errors → Alert
- [ ] **TODO**

---

## 🟣 Infrastructure - Scalability

### 40. Horizontal Scaling Readiness 🚀 Growth
- **Priority:** MEDIUM (audit before adding second instance)
- **Why you need it:** Checklist before scaling to multiple instances
- **Requirements:**
  - [ ] No in-memory state (use Redis)
  - [ ] Stateless API servers
  - [ ] Database connection pooling
  - [ ] File storage in Supabase/S3 (not local) ✅ Already done
  - [ ] Session affinity not required
- [ ] **TODO**

### 41. Database Connection Pooling 🎯 Your Setup
- **Priority:** MEDIUM (prevents connection exhaustion)
- **Files:** `db/backends/supabase.py`
- **Why you need it:** Supabase has connection limits, pooling prevents exhaustion
- **Requirements:**
  - Use PgBouncer or Supabase pooler (Supabase provides this)
  - Connection limits per instance
  - Graceful handling of pool exhaustion
- [ ] **TODO**

### 42. Background Job Queue 🚀 Growth
- **Priority:** LOW (when PDF generation blocks requests)
- **Files:** `workers/`, `integrations/queue/`
- **Why you need it:** Don't block HTTP requests with slow operations
- **Requirements:**
  - Redis-based queue (RQ, Celery, or Bull)
  - Offload: PDF generation, email sending, analytics
  - Retry logic with exponential backoff
  - Dead letter queue for failures
- [ ] **TODO**

### 43. CDN for Static Assets 🏢 Enterprise
- **Priority:** LOW (Render handles this adequately)
- **Why you need it:** Faster global asset delivery
- **Requirements:**
  - Serve frontend assets via CDN
  - Cache headers for static files
  - Reduces load on origin servers
- [ ] **TODO**

---

## 🟣 Infrastructure - Data Management

### 44. Message Retention Policy 🚀 Growth
- **Priority:** LOW (when storage becomes a concern)
- **Why you need it:** Prevent unbounded storage growth
- **Requirements:**
  - Auto-archive conversations older than X days
  - Option to export before deletion
  - Configurable per-organization
  - GDPR compliance for deletion requests
- [ ] **TODO**

### 45. Database Backups ✅ Essential 🎯 Your Setup
- **Priority:** HIGH (critical for production)
- **Why you need it:** Recover from data loss
- **Requirements:**
  - Daily automated backups (Supabase handles this ✅)
  - Point-in-time recovery enabled (Supabase Pro plan)
  - Test restore procedure quarterly
  - Backup retention: 30 days
- [ ] **TODO** - Verify Supabase backup settings

### 46. Data Export (GDPR) 🚀 Growth
- **Priority:** LOW (required if you have EU users)
- **Files:** `api/routers/user.py`
- **Why you need it:** Legal compliance for EU users
- **Requirements:**
  - `GET /api/user/export` - Download all user data
  - Include: conversations, messages, files, profile
  - JSON or ZIP format
- [ ] **TODO**

---

## Implementation Phases

### 🎯 Phase 0: Your Setup - Do Now (Security Fixes) ✅ COMPLETED
These are directly relevant to your current Render + Supabase setup:
- [x] #1-3 HIGH Security (Auth, Secrets) ✅
- [x] #5-7, #9-10, #12-13, #15-16 MEDIUM Security (Validation, CORS, Headers) ✅
- [x] #18, #20 LOW Security (Temp files, Error details) ✅
- [ ] #4, #11, #14 Remaining MEDIUM Security items (JWT decode, file validation)
- [ ] #41 Database Connection Pooling (Supabase)
- [ ] #45 Verify Supabase Backups

### 🚀 Phase 1: Growth - When Scaling (Redis + Multi-Instance)
Do these when you need multiple API instances or 100+ users:
- [ ] #24 Redis Setup & Configuration
- [ ] #25 Session Cache in Redis
- [ ] #26 Rate Limiting with Redis
- [ ] #40 Horizontal Scaling Readiness audit

### 🚀 Phase 2: Growth - Chat Improvements
Do these when conversations get long or you want better UX:
- [ ] #29 Normalize Chat Schema
- [ ] #30 Message Append-Only Writes
- [ ] #31 Conversation Management API
- [ ] #32 Pagination & Infinite Scroll

### 🚀 Phase 3: Growth - Observability
Do these when you can't manually monitor:
- [ ] #36 Structured Logging
- [ ] #39 Alerting

### 🏢 Phase 4: Enterprise - Advanced (1000+ users)
Only if you're building a large-scale SaaS:
- [ ] #27 LLM Response Caching
- [ ] #28 Distributed Locking
- [ ] #33 Redis + Postgres Hybrid Cache
- [ ] #34 Message Search
- [ ] #35 Conversation Summarization
- [ ] #37 Metrics & Dashboards
- [ ] #38 Distributed Tracing
- [ ] #42 Background Job Queue
- [ ] #43 CDN for Static Assets
- [ ] #44 Message Retention Policy
- [ ] #46 Data Export (GDPR)

---

## Security Completion Checklist

- [ ] All HIGH priority security items resolved
- [ ] All MEDIUM priority security items resolved
- [ ] All LOW priority security items resolved
- [ ] **Run comprehensive security audit again**
- [ ] Document any accepted risks

---

## Architecture Decision Records

### ADR-001: Chat Storage Strategy
- **Decision:** Migrate from JSON blob to normalized tables
- **Context:** Current approach rewrites entire conversation on each message
- **Consequences:** Better scalability, enables search, requires migration

### ADR-002: Caching Strategy
- **Decision:** Redis for hot data, Postgres for durability
- **Context:** Need fast reads for active conversations
- **Consequences:** Added infrastructure complexity, significant performance gain

### ADR-003: Message Ordering
- **Decision:** Use timestamp-based ordering, not sequence numbers
- **Context:** Distributed systems make sequence numbers complex
- **Consequences:** Possible ordering issues with concurrent writes (acceptable)

---

*Last updated: 2025-12-10*

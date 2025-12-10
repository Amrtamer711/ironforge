# Release Notes

**Sales CRM Platform - Built December 2024**

---

## December 7-10: Authentication & User Management

### JWT Authentication (ES256 + JWKS)
- Migrated from HS256 to ES256 JWKS for enterprise-grade security
- Environment-specific secrets (`UI_DEV_JWT_SECRET` / `UI_PROD_JWT_SECRET`)
- `/health/auth` debug endpoint for diagnosing auth issues
- Token-only validation without metadata dependency

### Chat Persistence
- `chat_sessions` table stores messages per user in database
- `/api/chat/history` endpoint loads previous conversations on login
- Supabase Storage integration for file attachments
- Session create/load/clear operations

### Enterprise RBAC (4-Level)
- **Profiles** - Named permission bundles (sales_user, sales_admin, super_admin)
- **Permission Sets** - Granular resource:action mappings
- **Invite Tokens** - Controlled user onboarding with profile assignment
- **Module-aware navigation** - Dynamic UI based on user permissions

### Invite Token System
- Admin UI to generate and manage invite tokens
- Profile assignment on signup
- Auto-create users in database with correct profile
- Token validation prevents unauthorized signups

### Production Fixes
- Fixed 502 proxy errors (moved middleware before bodyParser)
- Function-based pathRewrite to avoid double `/api/` prefix
- SSE heartbeats prevent proxy timeout during LLM generation
- Comprehensive error handling in Supabase backend

---

## December 6-7: Security & Infrastructure

### Security Overhaul
- JWT Authentication on all sensitive endpoints
- Role-Based Access Control (admin, user, viewer)
- API Key system for external integrations with scoped access
- Security headers (XSS protection, clickjacking prevention, HSTS)

### Architecture Refactor
- Broke 1,400-line `server.py` into 9 modular routers
- Centralized error handling
- Input validation everywhere
- Proper separation of concerns

### Database Layer
- SQLite for local development
- Supabase (PostgreSQL) for production
- Full schema: users, roles, permissions, audit logs, AI cost tracking
- Migration system for safe schema updates

### CI/CD Pipeline
- Linting with Ruff
- Security scanning with Bandit
- Automated tests with pytest
- Docker builds
- GitHub Actions + GitLab CI

---

## December 4-5: Platform Foundation

### Unified Web UI
- React-based web interface replacing Slack-only access
- Channel abstraction layer (Web + Slack adapters)
- Modern dark theme design system
- Responsive layout with sidebar navigation

### Platform-Agnostic Architecture
- Refactored to support multiple channels (Web, Slack)
- Shared LLM infrastructure across all channels
- Microservices architecture with Docker
- Production-ready deployment configuration

---

## December 1-3: Multi-LLM & Cost Optimization

### Google Gemini Integration
- Added Gemini alongside OpenAI
- Unified interface for both providers
- Token-based pricing for Gemini image generation

### Cost Tracking
- Comprehensive AI cost tracking infrastructure
- Per-user and per-workflow cost attribution
- OpenAI prompt caching for 50% cost reduction
- Updated pricing to January 2025 rates

### LLM Abstraction Layer
- Centralized prompts module
- Unified cost tracking architecture
- Model configuration per task type

---

## Key Commits

```
5e21f02 - JWT auth migration to ES256 JWKS
a0948f3 - Chat sessions table for persistent history
fdaa467 - Enterprise 4-level RBAC architecture
8ef06b5 - Token-based invite system
80d38d5 - Auth, RBAC, security middleware, CI
2a54ae7 - Channel abstraction + unified web UI
02396b2 - Platform-agnostic architecture refactor
6614b68 - Google Gemini provider + cost tracking
```

---

## What's Next

See [BACKLOG.md](BACKLOG.md) for prioritized security fixes and infrastructure improvements.

---

*From Slack bot to full CRM platform in 10 days.*

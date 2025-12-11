# Security Issues Tracker

## Status: Architecture is SOUND ✅

The authentication and RBAC architecture is **correctly implemented**:
- Proxy-based trust model with unified-ui as auth gateway
- 4-level enterprise RBAC (profiles, permission sets, teams, record sharing)
- Provider pattern allows swapping auth/RBAC implementations
- Proper async-safe context using `contextvars`
- Clean separation: UI Supabase (auth) vs SalesBot Supabase (data)

---

## Critical Issues (Fix Before Production)

### 1. PROXY_SECRET Not Mandatory in Production
- **Risk**: If not set, backend accepts spoofed `X-Trusted-User-*` headers
- **Location**: `app_settings.py` → `validate_production_secrets()`
- **Fix**: Add `proxy_secret` to required secrets list
- **Status**: ✅ ALREADY DONE (line 480-481 in settings.py)

### 2. Verify Credentials Not Committed
- **Risk**: If `.env` with real keys was committed, they're exposed
- **Action**: Check git history, rotate if needed:
  - OpenAI API key
  - Slack tokens
  - Supabase service keys
- **Status**: ⬜ TODO (verify)

---

## High Priority Issues

### 3. localStorage JWT Storage
- **Risk**: XSS attacks can steal tokens from localStorage
- **Current**: Frontend stores JWT in `localStorage`
- **Better**: HttpOnly cookies (bigger refactor)
- **Status**: ⬜ Deferred (acceptable for internal tool)

### 4. No Backend JWT Validation
- **Risk**: If proxy bypassed, backend has no defense
- **Current**: Backend trusts `X-Trusted-User-*` headers completely
- **Better**: Backend validates JWT signature as defense-in-depth
- **Status**: ⬜ Deferred (proxy secret is primary protection)

### 5. CSP Too Permissive
- **Risk**: `'unsafe-eval'` allows code injection
- **Location**: `unified-ui/server.js` helmet config
- **Fix**: Remove `'unsafe-eval'` from scriptSrc
- **Status**: ✅ FIXED

### 6. No CSRF Protection
- **Risk**: Cross-site POST requests possible
- **Fix**: Add Double-Submit Cookie pattern
- **Status**: ⬜ Deferred (low risk for API-only backend)

### 7. Inconsistent Endpoint Auth
- **Risk**: Some endpoints may be unprotected
- **Action**: Audit all API routes have `Depends(require_auth)`
- **Status**: ✅ AUDITED - All endpoints properly protected

---

## Medium Priority Issues

### 8. Permission Set Expiration Not Enforced
- **Risk**: Expired permissions still work for up to 1 minute (cache TTL)
- **Status**: ⬜ Acceptable for now

### 9. No Audit Logging for RBAC Changes
- **Risk**: Can't track who changed permissions
- **Status**: ⬜ Future enhancement

### 10. Teams & Record Sharing Not Implemented
- **Note**: Levels 3-4 of RBAC return empty lists
- **Status**: ⬜ Future enhancement (not needed yet)

### 11. No Session Revocation
- **Risk**: Logout doesn't invalidate tokens
- **Status**: ⬜ Future enhancement

---

## Architecture Summary

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│   Browser       │       │   unified-ui    │       │  proposal-bot   │
│                 │       │   (Node.js)     │       │   (FastAPI)     │
│  localStorage   │──────▶│                 │──────▶│                 │
│  stores JWT     │ JWT   │  Validates JWT  │Headers│  Trusts proxy   │
│                 │       │  via Supabase   │       │  if secret OK   │
└─────────────────┘       │  Queries RBAC   │       │                 │
                          │  Injects perms  │       │  Checks perms   │
                          │  X-Proxy-Secret │       │  from headers   │
                          └────────┬────────┘       └────────┬────────┘
                                   │                         │
                          ┌────────▼────────┐       ┌────────▼────────┐
                          │  UI Supabase    │       │ SalesBot        │
                          │  (Auth + RBAC)  │       │ Supabase (Data) │
                          └─────────────────┘       └─────────────────┘
```

## What's Working Correctly

| Component | Status | Notes |
|-----------|--------|-------|
| JWT validation at proxy | ✅ | Supabase validates signature |
| RBAC permission checks | ✅ | Wildcard patterns work |
| Proxy secret validation | ✅ | Required in production |
| Role-based tool access | ✅ | Admin tools require admin role |
| User deactivation | ✅ | `is_active` flag checked |
| Rate limiting | ✅ | Implemented with Redis support |
| Security headers | ✅ | HSTS, X-Frame-Options, etc. |
| SQL injection protection | ✅ | Parameterized queries |
| Slack webhook verification | ✅ | Signature validation |
| CSP | ✅ | unsafe-eval removed |
| Endpoint auth | ✅ | All endpoints have auth dependencies |

---

## Pre-Production Checklist

- [x] PROXY_SECRET required in production validation
- [x] Remove `'unsafe-eval'` from CSP
- [x] Audit all endpoints have auth dependencies
- [ ] Set `PROXY_SECRET` in Render env vars
- [ ] Verify `.env` not in git history with real secrets
- [ ] Test permission checks on admin routes

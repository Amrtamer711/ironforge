# Security TODO

This document tracks security vulnerabilities identified in the comprehensive security audit.
After all items are resolved, we will conduct another comprehensive security audit.

---

## 🔴 HIGH Priority (Fix Immediately)

### 1. Missing Rate Limiting on Auth Endpoints
- **File:** `api/server.py`, `app_settings.py`
- **Issue:** Rate limiting disabled by default (`rate_limit_enabled=False`)
- **Risk:** Brute force attacks on authentication endpoints
- **Fix:** Enable rate limiting by default in production
- [ ] **TODO**

### 2. Secrets with Empty Defaults
- **File:** `config.py:69-70, 132-133`
- **Issue:** `SLACK_SIGNING_SECRET`, `OPENAI_API_KEY`, `GOOGLE_API_KEY` default to `""`
- **Risk:** Silent security bypass, application runs without required secrets
- **Fix:** Raise error if required secrets are missing in production
- [ ] **TODO**

### 3. Fallback to Dev Auth in Production
- **File:** `integrations/auth/client.py:74-82`
- **Issue:** `AUTH_PROVIDER` defaults to `local_dev` if not set
- **Risk:** Production could accidentally use insecure dev authentication
- **Fix:** Require explicit `AUTH_PROVIDER` configuration, fail if not set
- [ ] **TODO**

---

## 🟠 MEDIUM Priority

### 4. JWT Decode Without Verification
- **File:** `integrations/auth/providers/supabase.py:482-486`
- **Issue:** `decode_token()` uses `verify_signature=False`
- **Risk:** Could be misused for authorization decisions
- **Fix:** Add explicit warnings, require opt-in parameter
- [ ] **TODO**

### 5. Insufficient Email Validation
- **File:** `unified-ui/server.js:286-290`
- **Issue:** Only checks `email.length < 5`
- **Risk:** Invalid email formats accepted for invite tokens
- **Fix:** Add proper email regex validation
- [ ] **TODO**

### 6. No Chat Message Length Limit
- **File:** `core/chat_api.py:37-44`
- **Issue:** Accepts arbitrary message sizes
- **Risk:** DoS via extremely large messages, high LLM costs
- **Fix:** Add message length validation (e.g., 10,000 char max)
- [ ] **TODO**

### 7. CORS with Credentials Enabled
- **File:** `api/server.py:181-187`
- **Issue:** `allow_credentials=True` with variable origins list
- **Risk:** CSRF attacks if origins list is misconfigured
- **Fix:** Review if credentials are needed; if not, disable
- [ ] **TODO**

### 8. X-Forwarded-For Header Trust
- **File:** `unified-ui/server.js:127-131`
- **Issue:** Trusts `X-Forwarded-For` without proxy validation
- **Risk:** IP spoofing for rate limit bypass
- **Fix:** Only trust header from known proxy IPs (Render's IPs)
- [ ] **TODO**

### 9. Generic Exception Handler Disabled
- **File:** `api/exceptions.py:295-297`
- **Issue:** Catch-all handler is commented out
- **Risk:** Stack traces leaked to clients on unhandled errors
- **Fix:** Enable generic exception handler
- [ ] **TODO**

### 10. Outdated Dependencies
- **File:** `requirements.txt`
- **Issue:** `psutil`, `aiohttp`, `reportlab` have newer versions with security patches
- **Risk:** Known vulnerabilities in outdated packages
- **Fix:** Update: `psutil>=6.0.0`, `aiohttp>=3.9.5`, `reportlab>=4.0.9`
- [ ] **TODO**

### 11. File Download Path Validation
- **File:** `api/routers/files.py:22-95`
- **Issue:** Filename from URL not validated against stored metadata
- **Risk:** Potential path traversal if backend doesn't validate
- **Fix:** Validate filename matches stored file metadata
- [ ] **TODO**

### 12. DB Fallback to SQLite Silently
- **File:** `db/database.py:48-70`
- **Issue:** Falls back to SQLite if Supabase credentials missing
- **Risk:** Production could run with local SQLite unknowingly
- **Fix:** Fail loudly in production if credentials missing
- [ ] **TODO**

### 13. Profile Name Echo in Error Message
- **File:** `unified-ui/server.js:296-300`
- **Issue:** Error message includes user-supplied `profile_name`
- **Risk:** XSS if response rendered as HTML
- **Fix:** Use generic error message without echoing input
- [ ] **TODO**

### 14. JWT Secrets with Legacy Variable Names
- **File:** `integrations/auth/providers/supabase.py:60-78`
- **Issue:** Falls back to legacy `SUPABASE_JWT_SECRET` variable
- **Risk:** Old/rotated keys could be used accidentally
- **Fix:** Remove legacy fallbacks, use explicit variable names only
- [ ] **TODO**

### 15. Content-Type Validation in File Uploads
- **File:** `core/chat_api.py:112-125`
- **Issue:** Uses `.startswith("image/")` for MIME check
- **Risk:** Could match malformed MIME types like `image/jpeg; x-malware`
- **Fix:** Use exact MIME type whitelist
- [ ] **TODO**

---

## 🟢 LOW Priority

### 16. Unprotected Health Endpoints
- **File:** `api/routers/health.py:102-120`
- **Issue:** Detailed health endpoints expose internal config
- **Risk:** Information disclosure (LLM provider, DB type, etc.)
- **Fix:** Require auth for detailed endpoints, keep `/health` simple
- [ ] **TODO**

### 17. Temp Files Not Cleaned on Error
- **File:** `core/file_utils.py:134-147`
- **Issue:** Temp files may not be cleaned if exception occurs
- **Risk:** Disk space exhaustion over time
- **Fix:** Use try/finally for cleanup, or context managers
- [ ] **TODO**

### 18. Service URLs in Proxy Logs
- **File:** `unified-ui/server.js:113-118`
- **Issue:** Logs expose internal service URLs and architecture
- **Risk:** Information disclosure in logs
- **Fix:** Reduce logging verbosity in production
- [ ] **TODO**

---

## Completion Checklist

- [ ] All HIGH priority items resolved
- [ ] All MEDIUM priority items resolved
- [ ] All LOW priority items resolved
- [ ] **Run comprehensive security audit again**
- [ ] Document any accepted risks

---

*Generated from security audit on 2025-12-10*

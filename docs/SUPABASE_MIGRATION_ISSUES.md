# Supabase Production Migration - Issues & Solutions

This document captures all issues encountered during the CRM system migration from development to production Supabase projects.

---

## Table of Contents
1. [Database Schema & Permissions](#1-database-schema--permissions)
2. [Authentication & User Sync](#2-authentication--user-sync)
3. [Trigger & Function Issues](#3-trigger--function-issues)
4. [RLS Policy Issues](#4-rls-policy-issues)
5. [RBAC & Permissions](#5-rbac--permissions)
6. [Service Configuration](#6-service-configuration)

---

## 1. Database Schema & Permissions

### 1.1 Tables Not Accessible by service_role

**Symptom:** Backend services using `service_role` key couldn't query tables.

**Cause:** After `pg_dump`/`psql` migration, table permissions weren't automatically granted to Supabase roles (`anon`, `authenticated`, `service_role`).

**Solution:**
```sql
-- Grant permissions to all roles on all tables
GRANT ALL ON ALL TABLES IN SCHEMA public TO postgres, anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO postgres, anon, authenticated, service_role;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO postgres, anon, authenticated, service_role;
```

**Lesson:** Always run permission grants after schema restoration.

---

### 1.2 Company Schema Permissions (Multi-tenant)

**Symptom:** Asset management service couldn't access company-specific schemas (e.g., `backlite_dubai`, `viola_outdoor`).

**Cause:** Company schemas existed but `service_role` didn't have usage/select permissions.

**Solution:**
```sql
-- For each company schema
GRANT USAGE ON SCHEMA backlite_dubai TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA backlite_dubai TO service_role;
-- Repeat for all company schemas
```

---

### 1.3 Storage Buckets Not Created

**Symptom:** File uploads failed with "bucket not found" errors.

**Cause:** `pg_dump` doesn't capture storage bucket definitions - they're in Supabase's `storage` schema which is managed separately.

**Solution:**
```sql
-- Create required buckets
INSERT INTO storage.buckets (id, name, public) VALUES
  ('proposals', 'proposals', false),
  ('uploads', 'uploads', false),
  ('templates', 'templates', false),
  ('mockups', 'mockups', false);
```

**Lesson:** Storage buckets must be manually created or scripted separately from database migration.

---

## 2. Authentication & User Sync

### 2.1 Users Not Synced to public.users

**Symptom:** Users could authenticate via Google OAuth but weren't appearing in `public.users` table. App showed empty user data.

**Cause:** The `sync_user_from_auth` trigger on `auth.users` wasn't created before users signed in. Users existed in `auth.users` but not in `public.users`.

**Solution:**
```sql
-- Manually sync existing auth users to public.users
INSERT INTO public.users (id, email, name, avatar_url, profile_id, created_at, updated_at)
SELECT
    au.id::TEXT,
    au.email,
    COALESCE(au.raw_user_meta_data->>'name', au.raw_user_meta_data->>'full_name'),
    au.raw_user_meta_data->>'avatar_url',
    (SELECT id FROM profiles WHERE name = 'system_admin'), -- or appropriate profile
    NOW(),
    NOW()
FROM auth.users au
WHERE NOT EXISTS (SELECT 1 FROM public.users pu WHERE pu.id = au.id::TEXT);
```

**Lesson:** Create auth triggers BEFORE any users sign in, or have a manual sync process ready.

---

### 2.2 User Company Assignments Missing

**Symptom:** Users could log in but couldn't see any data (no company context).

**Cause:** `user_companies` junction table wasn't populated for existing users.

**Solution:**
```sql
-- Assign users to their company
INSERT INTO public.user_companies (user_id, company_id, is_primary)
SELECT
    u.id,
    (SELECT id FROM companies WHERE code = 'mmg'),
    true
FROM public.users u
WHERE u.email LIKE '%@mmg.global'
ON CONFLICT (user_id, company_id) DO NOTHING;
```

---

## 3. Trigger & Function Issues

### 3.1 "relation 'user_companies' does not exist" Error

**Symptom:** Users saw error popup: `ERROR: relation "user_companies" does not exist (SQLSTATE 42P01)` when trying to log in.

**Cause:** Cascading triggers on `user_companies` table didn't have explicit `search_path` set. When triggered from auth context, PostgreSQL couldn't find the table.

**Affected Functions:**
- `auto_set_primary_company()` - BEFORE INSERT trigger
- `ensure_single_primary_company()` - AFTER INSERT/UPDATE trigger
- `sync_user_from_auth()` - Trigger on auth.users

**Solution:**
```sql
-- Fix ALL functions that reference tables to include:
-- 1. Explicit schema prefix (public.table_name)
-- 2. SET search_path = public

CREATE OR REPLACE FUNCTION public.auto_set_primary_company()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.user_companies WHERE user_id = NEW.user_id AND id != NEW.id) THEN
        NEW.is_primary := true;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

CREATE OR REPLACE FUNCTION public.ensure_single_primary_company()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.is_primary = true THEN
        UPDATE public.user_companies SET is_primary = false
        WHERE user_id = NEW.user_id AND id != NEW.id AND is_primary = true;
        UPDATE public.users SET primary_company_id = NEW.company_id WHERE id = NEW.user_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;
```

**Lesson:** ALWAYS add `SET search_path = public` to trigger functions, especially those that fire from `auth` schema operations.

---

### 3.2 Trigger Execution Order

**Symptom:** Data inconsistency when multiple triggers fire.

**Cause:** Two triggers on `auth.users`:
- `on_auth_user_created` → `handle_new_user()`
- `on_auth_user_sync` → `sync_user_from_auth()`

Both tried to insert into `public.users`, causing conflicts.

**Solution:** Use `ON CONFLICT DO UPDATE` or `ON CONFLICT DO NOTHING` in all user sync functions to handle race conditions gracefully.

---

## 4. RLS Policy Issues

### 4.1 Authenticated Users Can't Read Own Data

**Symptom:** Logged-in users got permission denied when fetching their profile.

**Cause:** RLS was enabled but only `service_role` had access policies.

**Solution:**
```sql
-- Allow users to read their own data
CREATE POLICY "Users can view own record" ON users
  FOR SELECT TO authenticated
  USING (id = auth.uid()::text);

CREATE POLICY "Users can view own company assignments" ON user_companies
  FOR SELECT TO authenticated
  USING (user_id = auth.uid()::text);

CREATE POLICY "Authenticated users can view companies" ON companies
  FOR SELECT TO authenticated
  USING (true);
```

---

### 4.2 RLS Blocking Service Operations

**Symptom:** Backend services (using service_role) couldn't perform operations.

**Cause:** RLS policies didn't account for service_role access.

**Solution:**
```sql
-- Add service_role full access policy
CREATE POLICY "Service role full access" ON table_name
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);
```

---

## 5. RBAC & Permissions

### 5.1 Wildcard Permission Granting Unintended Access

**Symptom:** `sales_user` profile could access mockup setup features they shouldn't have.

**Cause:** Permission `sales:mockups:*` included `sales:mockups:setup` which should be admin-only.

**Solution:**
```sql
-- Replace wildcard with explicit permissions
DELETE FROM profile_permissions
WHERE profile_id = (SELECT id FROM profiles WHERE name = 'sales_user')
AND permission = 'sales:mockups:*';

INSERT INTO profile_permissions (profile_id, permission)
SELECT p.id, perm FROM profiles p
CROSS JOIN (VALUES
  ('sales:mockups:generate'),
  ('sales:mockups:read'),
  ('sales:mockups:create'),
  ('sales:mockups:update')
) AS perms(perm)
WHERE p.name = 'sales_user';
```

**Lesson:** Avoid wildcard permissions (`*`) when granular control is needed. Be explicit.

---

### 5.2 Permission Format Consistency

**Format:** `{module}:{resource}:{action}`

**Examples:**
- `sales:proposals:create` - Create proposals in sales module
- `assets:locations:read` - Read locations in asset module
- `*:*:*` - Full admin access
- `sales:*:*` - All sales module permissions

**Special Actions:**
- `manage` - Implies all other actions (read, create, update, delete)
- `setup` - Administrative setup/configuration access

---

## 6. Service Configuration

### 6.1 Environment Variable Naming

**Issue:** Confusion between dev and prod Supabase URLs.

**Pattern Used:**
```bash
# Development
UI_DEV_SUPABASE_URL=https://xxx.supabase.co
UI_DEV_SUPABASE_ANON_KEY=xxx
UI_DEV_SUPABASE_SERVICE_ROLE_KEY=xxx

# Production
UI_PROD_SUPABASE_URL=https://yyy.supabase.co
UI_PROD_SUPABASE_ANON_KEY=yyy
UI_PROD_SUPABASE_SERVICE_ROLE_KEY=yyy

# Environment selector
ENVIRONMENT=production  # or 'development'
```

**Lesson:** Use consistent naming convention with environment prefix.

---

### 6.2 Health Check Log Spam

**Symptom:** Logs flooded with health check requests, making debugging difficult.

**Cause:** Load balancers/monitors hitting `/health` endpoint frequently.

**Solution:** Filter health checks in logging middleware:
```python
# Skip logging for health check endpoints
if request.url.path in ['/health', '/api/health']:
    return await call_next(request)
```

---

## Migration Checklist

Based on lessons learned, here's the complete checklist for future migrations:

### Pre-Migration
- [ ] Document all Supabase project refs (dev and prod)
- [ ] Get database connection strings from Supabase dashboard
- [ ] List all storage buckets needed
- [ ] List all edge functions to deploy

### Database Migration
- [ ] Dump schema with `pg_dump --schema-only`
- [ ] Dump reference data (not operational data)
- [ ] Restore to production
- [ ] **Grant permissions to all Supabase roles**
- [ ] **Create storage buckets manually**
- [ ] Verify all tables accessible

### Auth Setup
- [ ] **Create user sync trigger BEFORE any users sign in**
- [ ] Set `search_path = public` on ALL trigger functions
- [ ] Add RLS policies for authenticated users
- [ ] Test login flow end-to-end

### Post-Migration Verification
- [ ] Check table counts match expectations
- [ ] Verify RLS policies working
- [ ] Test each user role/profile
- [ ] Monitor logs for errors

---

## Quick Fixes Reference

### Grant All Permissions
```sql
GRANT ALL ON ALL TABLES IN SCHEMA public TO postgres, anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO postgres, anon, authenticated, service_role;
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
```

### Fix search_path on Function
```sql
ALTER FUNCTION function_name SET search_path = public;
```

### Check Trigger Configuration
```sql
SELECT trigger_name, event_manipulation, action_statement
FROM information_schema.triggers
WHERE event_object_table = 'your_table';
```

### Check Function search_path
```sql
SELECT proname, proconfig
FROM pg_proc
WHERE proname = 'your_function';
```

---

*Document created: 2026-01-14*
*Last updated: 2026-01-14*

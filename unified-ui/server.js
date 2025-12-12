const express = require('express');
const path = require('path');
const cors = require('cors');
const helmet = require('helmet');
const bodyParser = require('body-parser');
const crypto = require('crypto');
const { createProxyMiddleware } = require('http-proxy-middleware');
const { createClient } = require('@supabase/supabase-js');
const { sendInviteEmail, sendWelcomeEmail, EMAIL_PROVIDER } = require('./email-service');

const app = express();
const PORT = process.env.PORT || 3005;

// =============================================================================
// ENVIRONMENT DETECTION
// =============================================================================
const ENVIRONMENT = process.env.ENVIRONMENT || 'development';
const IS_PRODUCTION = ENVIRONMENT === 'production';

console.log(`[UI] Environment: ${ENVIRONMENT} (production: ${IS_PRODUCTION})`);

// =============================================================================
// UI SUPABASE CONFIGURATION (Auth/RBAC - unified-ui owns authentication)
// =============================================================================

// Get credentials based on environment
const supabaseUrl = IS_PRODUCTION
  ? (process.env.UI_PROD_SUPABASE_URL || process.env.SUPABASE_URL)
  : (process.env.UI_DEV_SUPABASE_URL || process.env.SUPABASE_URL);

const supabaseServiceKey = IS_PRODUCTION
  ? (process.env.UI_PROD_SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SERVICE_KEY)
  : (process.env.UI_DEV_SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SERVICE_KEY);

const supabaseAnonKey = IS_PRODUCTION
  ? (process.env.UI_PROD_SUPABASE_ANON_KEY || process.env.SUPABASE_ANON_KEY)
  : (process.env.UI_DEV_SUPABASE_ANON_KEY || process.env.SUPABASE_ANON_KEY);

if (!supabaseUrl || !supabaseServiceKey) {
  console.warn('Warning: UI Supabase credentials not configured.');
  console.warn('Set UI_DEV_SUPABASE_URL and UI_DEV_SUPABASE_SERVICE_ROLE_KEY (or UI_PROD_* for production)');
}

// Service role client for server-side operations
const supabase = supabaseUrl && supabaseServiceKey
  ? createClient(supabaseUrl, supabaseServiceKey)
  : null;

// =============================================================================
// SERVICE REGISTRY
// Sales module routes go to proposal-bot
// =============================================================================
const SERVICES = {
  sales: process.env.SALES_BOT_URL || 'http://localhost:8000',
};

// Shared secret for trusted proxy communication
const PROXY_SECRET = process.env.PROXY_SECRET || null;
if (!PROXY_SECRET) {
  console.warn('[UI] WARNING: PROXY_SECRET not set. Trusted headers may be vulnerable to spoofing.');
  console.warn('[UI] Set PROXY_SECRET environment variable (same value in both unified-ui and proposal-bot)');
}

// =============================================================================
// RATE LIMITING (Simple in-memory rate limiter)
// =============================================================================
const rateLimitStore = new Map();
const RATE_LIMIT_WINDOW_MS = 60 * 1000; // 1 minute
const RATE_LIMIT_MAX_REQUESTS = 10; // max requests per window for auth endpoints

function rateLimiter(maxRequests = RATE_LIMIT_MAX_REQUESTS) {
  return (req, res, next) => {
    const ip = req.ip || req.socket.remoteAddress || 'unknown';
    const key = `${ip}:${req.path}`;
    const now = Date.now();

    let record = rateLimitStore.get(key);
    if (!record || now - record.windowStart > RATE_LIMIT_WINDOW_MS) {
      record = { windowStart: now, count: 0 };
    }

    record.count++;
    rateLimitStore.set(key, record);

    if (record.count > maxRequests) {
      console.warn(`[Rate Limit] Blocked ${ip} on ${req.path}`);
      return res.status(429).json({ error: 'Too many requests, please try again later' });
    }

    next();
  };
}

// Clean up rate limit store periodically
setInterval(() => {
  const now = Date.now();
  for (const [key, record] of rateLimitStore.entries()) {
    if (now - record.windowStart > RATE_LIMIT_WINDOW_MS * 2) {
      rateLimitStore.delete(key);
    }
  }
}, RATE_LIMIT_WINDOW_MS);

// =============================================================================
// CORS CONFIGURATION
// local = localhost only, development/production = Render URL + optional CORS_ORIGINS
// =============================================================================
const IS_LOCAL = ENVIRONMENT === 'local';
const RENDER_EXTERNAL_URL = process.env.RENDER_EXTERNAL_URL; // Auto-set by Render

let ALLOWED_ORIGINS = [];

if (IS_LOCAL) {
  // Local environment - only localhost
  ALLOWED_ORIGINS = ['http://localhost:3000', 'http://localhost:3005', 'http://127.0.0.1:3000', 'http://127.0.0.1:3005'];
} else {
  // Development or Production on Render - allow the Render URL
  if (RENDER_EXTERNAL_URL) {
    ALLOWED_ORIGINS.push(RENDER_EXTERNAL_URL);
  }
  // Also allow any additional origins from CORS_ORIGINS env var
  const extraOrigins = (process.env.CORS_ORIGINS || '').split(',').filter(Boolean).map(s => s.trim());
  ALLOWED_ORIGINS.push(...extraOrigins);
}

// Warn if no origins configured on Render
if (!IS_LOCAL && ALLOWED_ORIGINS.length === 0) {
  console.warn('[UI] WARNING: No CORS origins configured. Ensure RENDER_EXTERNAL_URL is set or add CORS_ORIGINS.');
}

const corsOptions = {
  origin: function (origin, callback) {
    // Allow requests with no origin (like mobile apps, curl, Postman)
    if (!origin) return callback(null, true);

    if (ALLOWED_ORIGINS.length === 0 || ALLOWED_ORIGINS.includes(origin)) {
      callback(null, true);
    } else {
      console.warn(`[CORS] Blocked request from origin: ${origin}`);
      callback(new Error('Not allowed by CORS'));
    }
  },
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization', 'X-API-Key', 'X-Request-ID'],
};

console.log(`[UI] CORS allowed origins: ${ALLOWED_ORIGINS.length > 0 ? ALLOWED_ORIGINS.join(', ') : '(all - development mode)'}`);

// Middleware
// Security headers via Helmet
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"],  // unsafe-inline for inline handlers, CDN for Supabase
      styleSrc: ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
      imgSrc: ["'self'", "data:", "blob:", "https:"],
      connectSrc: ["'self'", ...ALLOWED_ORIGINS, supabaseUrl, "https://*.supabase.co"].filter(Boolean),
      fontSrc: ["'self'", "https:", "data:", "https://fonts.gstatic.com"],
      objectSrc: ["'none'"],
      upgradeInsecureRequests: IS_PRODUCTION ? [] : null,
    },
  },
  crossOriginEmbedderPolicy: false,  // May conflict with some integrations
  crossOriginResourcePolicy: { policy: "cross-origin" },  // Allow cross-origin resources
}));
app.use(cors(corsOptions));

// =============================================================================
// UNIFIED-UI IS THE AUTH/RBAC GATEWAY
// All requests to backend services go through here. We validate the JWT,
// fetch user profile/permissions from UI Supabase, and inject trusted headers.
// Backend services (proposal-bot) trust these headers - no token validation needed.
// =============================================================================

// =============================================================================
// ENTERPRISE RBAC - 4-Level Permission System
// =============================================================================
// Level 1: Profiles (base permissions for job function)
// Level 2: Permission Sets (additive, can be temporary with expiration)
// Level 3: Teams & Hierarchy (team-based access, manager sees subordinates)
// Level 4: Record Sharing (share specific records with users/teams)
// =============================================================================

// Helper: Fetch user's complete RBAC data from UI Supabase
// Returns null if user not found (should be rejected)
async function getUserRBACData(userId) {
  if (!supabase) {
    // Dev mode fallback
    return {
      profile: 'sales_user',
      permissions: ['sales:*:*'],
      teams: [],
      managerId: null,
      subordinateIds: [],
    };
  }

  try {
    // =========================================================================
    // LEVEL 1: Get user with profile
    // =========================================================================
    const { data: userData, error } = await supabase
      .from('users')
      .select('id, email, name, profile_id, is_active, manager_id, profiles(id, name, display_name)')
      .eq('id', userId)
      .single();

    if (error || !userData) {
      console.warn(`[RBAC] User ${userId} not found in users table - ACCESS DENIED`);
      return null; // User doesn't exist - reject access
    }

    // Check if user is active
    if (userData.is_active === false) {
      console.warn(`[RBAC] User ${userId} is deactivated - ACCESS DENIED`);
      return null; // User is deactivated - reject access
    }

    const profile = userData.profiles;
    const profileName = profile?.name || 'sales_user';

    // Get permissions from profile
    let permissions = [];
    if (profile?.id) {
      const { data: perms } = await supabase
        .from('profile_permissions')
        .select('permission')
        .eq('profile_id', profile.id);

      if (perms) {
        permissions = perms.map(p => p.permission);
      }
    }

    // =========================================================================
    // LEVEL 2: Permission Sets (with expiration check)
    // =========================================================================
    const now = new Date().toISOString();
    const { data: userPermSets } = await supabase
      .from('user_permission_sets')
      .select('permission_set_id, expires_at, permission_sets(id, name, is_active)')
      .eq('user_id', userId);

    const activePermissionSets = [];
    if (userPermSets) {
      for (const ups of userPermSets) {
        // Skip if permission set is inactive
        if (!ups.permission_sets?.is_active) continue;

        // Skip if expired
        if (ups.expires_at && new Date(ups.expires_at) < new Date(now)) {
          console.log(`[RBAC] Permission set ${ups.permission_sets?.name} expired for user ${userId}`);
          continue;
        }

        activePermissionSets.push({
          id: ups.permission_sets.id,
          name: ups.permission_sets.name,
          expiresAt: ups.expires_at
        });

        // Get permissions from this permission set
        const { data: psPerms } = await supabase
          .from('permission_set_permissions')
          .select('permission')
          .eq('permission_set_id', ups.permission_sets.id);

        if (psPerms) {
          permissions.push(...psPerms.map(p => p.permission));
        }
      }
    }

    // =========================================================================
    // LEVEL 3: Teams & Hierarchy
    // =========================================================================

    // Get user's teams with their info
    const { data: teamMemberships } = await supabase
      .from('team_members')
      .select('role, teams(id, name, display_name, parent_team_id, is_active)')
      .eq('user_id', userId);

    const teams = [];
    if (teamMemberships) {
      for (const tm of teamMemberships) {
        if (tm.teams?.is_active) {
          teams.push({
            id: tm.teams.id,
            name: tm.teams.name,
            displayName: tm.teams.display_name,
            role: tm.role, // 'member' or 'leader'
            parentTeamId: tm.teams.parent_team_id
          });
        }
      }
    }

    // Get subordinates (users where this user is their manager)
    const { data: subordinates } = await supabase
      .from('users')
      .select('id')
      .eq('manager_id', userId)
      .eq('is_active', true);

    const subordinateIds = subordinates ? subordinates.map(s => s.id) : [];

    // Get team members for teams where user is leader (they can see their team's data)
    const ledTeamIds = teams.filter(t => t.role === 'leader').map(t => t.id);
    let teamMemberIds = [];

    if (ledTeamIds.length > 0) {
      const { data: teamMembers } = await supabase
        .from('team_members')
        .select('user_id')
        .in('team_id', ledTeamIds)
        .neq('user_id', userId); // Exclude self

      if (teamMembers) {
        teamMemberIds = teamMembers.map(tm => tm.user_id);
      }
    }

    // Combine subordinates: direct reports + team members (for team leaders)
    const allSubordinateIds = [...new Set([...subordinateIds, ...teamMemberIds])];

    // =========================================================================
    // Return complete RBAC context
    // =========================================================================
    return {
      profile: profileName,
      permissions: [...new Set(permissions)],
      permissionSets: activePermissionSets,
      teams: teams,
      managerId: userData.manager_id,
      subordinateIds: allSubordinateIds,
    };

  } catch (err) {
    console.error(`[RBAC] Error fetching RBAC for ${userId}:`, err.message);
    return null; // Error fetching - reject access for safety
  }
}

// Helper: Get active sharing rules for an object type
async function getSharingRules(objectType) {
  if (!supabase) return [];

  try {
    const { data: rules } = await supabase
      .from('sharing_rules')
      .select('*')
      .eq('object_type', objectType)
      .eq('is_active', true);

    return rules || [];
  } catch (err) {
    console.error(`[RBAC] Error fetching sharing rules:`, err.message);
    return [];
  }
}

// Helper: Get record shares for a user (records shared with them or their teams)
async function getUserRecordShares(userId, teamIds = []) {
  if (!supabase) return [];

  try {
    const now = new Date().toISOString();

    // Get shares to this user
    const { data: userShares } = await supabase
      .from('record_shares')
      .select('*')
      .eq('shared_with_user_id', userId)
      .or(`expires_at.is.null,expires_at.gt.${now}`);

    // Get shares to user's teams
    let teamShares = [];
    if (teamIds.length > 0) {
      const { data: tShares } = await supabase
        .from('record_shares')
        .select('*')
        .in('shared_with_team_id', teamIds)
        .or(`expires_at.is.null,expires_at.gt.${now}`);

      teamShares = tShares || [];
    }

    return [...(userShares || []), ...teamShares];
  } catch (err) {
    console.error(`[RBAC] Error fetching record shares:`, err.message);
    return [];
  }
}

// RBAC cache (30 second TTL - reduced for faster permission propagation)
const rbacCache = new Map();
const RBAC_CACHE_TTL = 30000;

// Helper to invalidate RBAC cache for a user
function invalidateRBACCache(userId) {
  if (userId) {
    rbacCache.delete(userId);
    console.log(`[RBAC CACHE] Invalidated cache for user ${userId}`);
  }
}

// Helper to invalidate RBAC cache for multiple users
function invalidateRBACCacheForUsers(userIds) {
  for (const userId of userIds || []) {
    rbacCache.delete(userId);
  }
  if (userIds?.length) {
    console.log(`[RBAC CACHE] Invalidated cache for ${userIds.length} users`);
  }
}

// Clear all RBAC cache (use sparingly - for global permission changes)
function clearAllRBACCache() {
  const count = rbacCache.size;
  rbacCache.clear();
  console.log(`[RBAC CACHE] Cleared all ${count} cached entries`);
}

// Auth middleware for proxy - validates JWT, injects trusted headers
async function proxyAuthMiddleware(req, res, next) {
  const authHeader = req.headers.authorization;

  if (!authHeader?.startsWith('Bearer ')) {
    return res.status(401).json({ error: 'Authentication required' });
  }

  if (!supabase) {
    return res.status(500).json({ error: 'Auth service not configured' });
  }

  try {
    const token = authHeader.substring(7);
    const { data: { user }, error } = await supabase.auth.getUser(token);

    if (error || !user) {
      console.warn(`[PROXY AUTH] Invalid token: ${error?.message || 'no user'}`);
      return res.status(401).json({ error: 'Invalid or expired token' });
    }

    // Check cache for RBAC
    const cached = rbacCache.get(user.id);
    let rbac;

    if (cached && Date.now() - cached.ts < RBAC_CACHE_TTL) {
      rbac = cached.data;
    } else {
      rbac = await getUserRBACData(user.id);
      rbacCache.set(user.id, { data: rbac, ts: Date.now() });
    }

    // If RBAC is null, user doesn't exist or is deactivated - reject
    if (!rbac) {
      console.warn(`[PROXY AUTH] User ${user.id} (${user.email}) not authorized - not in users table or deactivated`);
      return res.status(403).json({
        error: 'Account not found or deactivated',
        code: 'USER_NOT_FOUND',
        requiresLogout: true  // Signal frontend to clear session
      });
    }

    // Attach to request for proxy to inject as headers
    // Includes full 4-level RBAC context
    req.trustedUser = {
      id: user.id,
      email: user.email,
      name: user.user_metadata?.name || user.user_metadata?.full_name || '',
      // Level 1: Profile
      profile: rbac.profile,
      // Level 1 + 2: Combined permissions (profile + permission sets)
      permissions: rbac.permissions,
      // Level 2: Active permission sets (for UI display/debugging)
      permissionSets: rbac.permissionSets || [],
      // Level 3: Teams
      teams: rbac.teams || [],
      teamIds: (rbac.teams || []).map(t => t.id),
      // Level 3: Hierarchy
      managerId: rbac.managerId,
      subordinateIds: rbac.subordinateIds || [],
    };

    next();
  } catch (err) {
    console.error(`[PROXY AUTH] Error:`, err.message);
    return res.status(401).json({ error: 'Authentication failed' });
  }
}

// Apply auth middleware before proxy
app.use('/api/sales', proxyAuthMiddleware);

// =============================================================================
// SERVICE PROXY - Forward to proposal-bot with trusted user headers
// proposal-bot trusts X-Trusted-User-* headers (only from this proxy)
// =============================================================================
app.use('/api/sales', createProxyMiddleware({
  target: SERVICES.sales,
  changeOrigin: true,
  pathRewrite: (path) => {
    // When mounted at /api/sales, path comes in ALREADY STRIPPED of the mount point
    // e.g., /api/sales/chat/history -> path = /chat/history
    // We want to forward to /api/chat/history on the target
    const newPath = '/api' + path;
    console.log(`[PROXY] pathRewrite: ${path} -> ${newPath}`);
    return newPath;
  },
  proxyTimeout: 300000,
  timeout: 300000,
  on: {
    proxyReq: (proxyReq, req, res) => {
      const targetPath = '/api' + req.originalUrl.replace('/api/sales', '');
      console.log(`[PROXY] ${req.method} ${req.originalUrl} -> ${SERVICES.sales}${targetPath}`);
      console.log(`[PROXY] User: ${req.trustedUser?.email} | Profile: ${req.trustedUser?.profile}`);

      // INJECT TRUSTED USER HEADERS - proposal-bot reads these instead of validating tokens
      // Full 4-Level RBAC context is injected
      if (req.trustedUser) {
        // Send proxy secret to prove request is from unified-ui
        if (PROXY_SECRET) {
          proxyReq.setHeader('X-Proxy-Secret', PROXY_SECRET);
        }

        // Level 1: User identity & profile
        proxyReq.setHeader('X-Trusted-User-Id', req.trustedUser.id);
        proxyReq.setHeader('X-Trusted-User-Email', req.trustedUser.email);
        proxyReq.setHeader('X-Trusted-User-Name', req.trustedUser.name);
        proxyReq.setHeader('X-Trusted-User-Profile', req.trustedUser.profile);

        // Level 1 + 2: Combined permissions (profile + active permission sets)
        proxyReq.setHeader('X-Trusted-User-Permissions', JSON.stringify(req.trustedUser.permissions));

        // Level 2: Active permission sets (for audit/debugging)
        proxyReq.setHeader('X-Trusted-User-Permission-Sets', JSON.stringify(req.trustedUser.permissionSets));

        // Level 3: Teams (array of {id, name, role})
        proxyReq.setHeader('X-Trusted-User-Teams', JSON.stringify(req.trustedUser.teams));
        proxyReq.setHeader('X-Trusted-User-Team-Ids', JSON.stringify(req.trustedUser.teamIds));

        // Level 3: Hierarchy (manager/subordinates for "see your team's data" patterns)
        if (req.trustedUser.managerId) {
          proxyReq.setHeader('X-Trusted-User-Manager-Id', req.trustedUser.managerId);
        }
        proxyReq.setHeader('X-Trusted-User-Subordinate-Ids', JSON.stringify(req.trustedUser.subordinateIds));
      }

      // Also forward original auth header (backward compat during transition)
      if (req.headers.authorization) {
        proxyReq.setHeader('Authorization', req.headers.authorization);
      }

      // Forward IP
      const ip = req.headers['x-forwarded-for'] || req.socket.remoteAddress;
      if (ip) proxyReq.setHeader('X-Forwarded-For', ip);
    },
    proxyRes: (proxyRes, req, res) => {
      console.log(`[PROXY] Response: ${proxyRes.statusCode} for ${req.method} ${req.originalUrl}`);

      if (req.path.includes('/stream') || proxyRes.headers['content-type']?.includes('text/event-stream')) {
        res.setHeader('X-Accel-Buffering', 'no');
        res.setHeader('Cache-Control', 'no-cache');
        res.setHeader('Connection', 'keep-alive');
      }
    },
    error: (err, req, res) => {
      console.error(`[PROXY] ERROR: ${err.message} for ${req.method} ${req.originalUrl}`);
      if (!res.headersSent) {
        if (IS_PRODUCTION) {
          res.status(502).json({ error: 'Service temporarily unavailable' });
        } else {
          res.status(502).json({ error: 'Service unavailable', details: err.message, target: SERVICES.sales });
        }
      }
    },
  },
}));

// Body parser middleware - AFTER proxy to avoid consuming the body
// Reduced body size limit for security (10MB is enough for most uploads)
app.use(bodyParser.json({ limit: '10mb' }));
app.use(bodyParser.urlencoded({ extended: true, limit: '10mb' }));

// Request logging middleware
app.use((req, res, next) => {
  const start = Date.now();
  res.on('finish', () => {
    const duration = Date.now() - start;
    console.log(`[UI] ${req.method} ${req.path} -> ${res.statusCode} (${duration}ms)`);
  });
  next();
});

// =============================================================================
// AUTH MIDDLEWARE - Validates JWT and attaches user to request
// =============================================================================
async function requireAuth(req, res, next) {
  if (!supabase) {
    return res.status(500).json({ error: 'Supabase not configured' });
  }

  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({ error: 'Unauthorized', requiresAuth: true });
  }

  const token = authHeader.substring(7);

  try {
    const { data: { user }, error } = await supabase.auth.getUser(token);

    if (error || !user) {
      return res.status(401).json({ error: 'Invalid token', requiresAuth: true });
    }

    req.user = user;
    next();
  } catch (err) {
    console.error('[UI Auth] Error:', err.message);
    return res.status(401).json({ error: 'Authentication failed', requiresAuth: true });
  }
}

// =============================================================================
// PROFILE CHECK MIDDLEWARE - Checks if user has required profile
// =============================================================================
function requireProfile(...allowedProfiles) {
  return async (req, res, next) => {
    if (!req.user) {
      return res.status(401).json({ error: 'Not authenticated' });
    }

    try {
      // Get user's profile from users table
      const { data: userData, error } = await supabase
        .from('users')
        .select('profile_id, profiles(name)')
        .eq('id', req.user.id)
        .single();

      if (error || !userData?.profiles?.name) {
        console.warn(`[UI Auth] User ${req.user.email} has no profile assigned`);
        return res.status(403).json({ error: 'No profile assigned' });
      }

      const userProfile = userData.profiles.name;

      if (!allowedProfiles.includes(userProfile)) {
        console.warn(`[UI Auth] User ${req.user.email} with profile ${userProfile} denied access (requires: ${allowedProfiles.join(', ')})`);
        return res.status(403).json({ error: 'Insufficient permissions' });
      }

      req.userProfile = userProfile;
      next();
    } catch (err) {
      console.error('[UI Auth] Profile check error:', err.message);
      return res.status(500).json({ error: 'Failed to check permissions' });
    }
  };
}

app.use(express.static('public'));

// =============================================================================
// LOCAL ROUTES - /api/base/* handled by this server (Auth only)
// =============================================================================

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    service: 'unified-ui',
    supabase: !!supabase,
    sales_bot_url: SERVICES.sales,
    environment: ENVIRONMENT,
  });
});

// Supabase config endpoint - serves public credentials to frontend as JavaScript
// IMPORTANT: Only expose SUPABASE_URL and SUPABASE_ANON_KEY (public), never SERVICE_KEY
app.get('/api/base/config.js', (_req, res) => {
  // Use environment-specific anon key (already resolved above)
  res.type('application/javascript');
  res.send(`// Supabase configuration (auto-generated)
// Environment: ${ENVIRONMENT}
window.SUPABASE_URL = ${JSON.stringify(supabaseUrl || '')};
window.SUPABASE_ANON_KEY = ${JSON.stringify(supabaseAnonKey || '')};
`);
});

// Serve main page
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// =============================================================================
// AUTH ENDPOINTS - Using Supabase Auth
// Note: Most auth is handled client-side with Supabase JS SDK
// These endpoints are for server-side validation
// =============================================================================

// =============================================================================
// INVITE TOKEN ENDPOINTS
// Invite tokens are stored in UI Supabase (auth/RBAC database)
// =============================================================================

// Email validation regex (RFC 5322 simplified)
const EMAIL_REGEX = /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/;

function isValidEmail(email) {
  if (!email || typeof email !== 'string') return false;
  if (email.length < 5 || email.length > 254) return false;
  return EMAIL_REGEX.test(email);
}

// Create invite token (requires system_admin)
app.post('/api/base/auth/invites', rateLimiter(20), requireAuth, requireProfile('system_admin'), async (req, res) => {
  console.log('[UI] Create invite request');

  const { email, profile_name = 'sales_user', expires_in_days = 7, send_email = true } = req.body;

  if (!isValidEmail(email)) {
    return res.status(400).json({ error: 'Valid email address is required' });
  }

  if (expires_in_days < 1 || expires_in_days > 30) {
    return res.status(400).json({ error: 'Expiry must be between 1 and 30 days' });
  }

  // Validate profile exists
  const validProfiles = ['system_admin', 'sales_manager', 'sales_user', 'coordinator', 'finance', 'viewer'];
  if (!validProfiles.includes(profile_name)) {
    // Don't echo user input to prevent XSS
    return res.status(400).json({ error: `Invalid profile. Valid profiles: ${validProfiles.join(', ')}` });
  }

  try {
    const now = new Date();

    // Check if email already has a pending invite
    const { data: existing } = await supabase
      .from('invite_tokens')
      .select('*')
      .eq('email', email.toLowerCase())
      .is('used_at', null)
      .eq('is_revoked', false)
      .gt('expires_at', now.toISOString());

    if (existing && existing.length > 0) {
      return res.status(409).json({ error: `A pending invite already exists for ${email}` });
    }

    // Generate secure token
    const token = crypto.randomBytes(32).toString('base64url');

    // Calculate expiry
    const expiresAt = new Date(now.getTime() + expires_in_days * 24 * 60 * 60 * 1000);

    // Store in UI Supabase
    const { error: insertError } = await supabase
      .from('invite_tokens')
      .insert({
        token,
        email: email.toLowerCase(),
        profile_name,
        created_by: req.user.id,
        created_at: now.toISOString(),
        expires_at: expiresAt.toISOString(),
      });

    if (insertError) {
      console.error('[UI] Failed to create invite:', insertError);
      return res.status(500).json({ error: 'Failed to create invite' });
    }

    console.log(`[UI] Invite token created for ${email} with profile ${profile_name} by ${req.user.email}`);

    // Send invite email if requested
    let emailSent = false;
    let emailError = null;

    if (send_email) {
      try {
        await sendInviteEmail({
          recipientEmail: email.toLowerCase(),
          inviterName: req.user.user_metadata?.name || req.user.email,
          inviterEmail: req.user.email,
          token,
          profileName: profile_name,
          expiresAt: expiresAt.toISOString(),
        });
        emailSent = true;
        console.log(`[UI] Invite email sent to ${email}`);
      } catch (emailErr) {
        console.error(`[UI] Failed to send invite email to ${email}:`, emailErr.message);
        emailError = emailErr.message;
        // Don't fail the request - invite was created, just email failed
      }
    }

    // Return 201 if email sent successfully, 202 if email failed (invite created but with warning)
    const statusCode = (send_email && !emailSent) ? 202 : 201;

    res.status(statusCode).json({
      token,
      email: email.toLowerCase(),
      profile_name,
      expires_at: expiresAt.toISOString(),
      email_sent: emailSent,
      email_error: emailError,
      email_requested: send_email,
      email_provider: EMAIL_PROVIDER,
      warning: (send_email && !emailSent) ? 'Invite created but email delivery failed. Share the invite link manually.' : null,
      message: emailSent
        ? `Invite created and email sent to ${email}.`
        : `Invite token created. ${emailError ? 'Email failed: ' + emailError + '. ' : ''}Share this token with ${email} to allow them to sign up.`,
    });
  } catch (err) {
    console.error('[UI] Error creating invite:', err);
    res.status(500).json({ error: 'Failed to create invite' });
  }
});

// List invite tokens (requires system_admin)
app.get('/api/base/auth/invites', rateLimiter(30), requireAuth, requireProfile('system_admin'), async (req, res) => {
  console.log('[UI] List invites request');

  const includeUsed = req.query.include_used === 'true';

  try {
    let query = supabase
      .from('invite_tokens')
      .select('*')
      .order('created_at', { ascending: false });

    if (!includeUsed) {
      query = query.is('used_at', null).eq('is_revoked', false);
    }

    const { data: tokens, error } = await query;

    if (error) {
      console.error('[UI] Failed to list invites:', error);
      return res.status(500).json({ error: 'Failed to list invites' });
    }

    const result = (tokens || []).map(t => ({
      id: t.id,
      email: t.email,
      profile_name: t.profile_name,
      token: t.token,
      created_by: t.created_by,
      created_at: t.created_at,
      expires_at: t.expires_at,
      is_used: t.used_at !== null,
      is_revoked: !!t.is_revoked,
    }));

    res.json(result);
  } catch (err) {
    console.error('[UI] Error listing invites:', err);
    res.status(500).json({ error: 'Failed to list invites' });
  }
});

// Revoke invite token (requires system_admin)
app.delete('/api/base/auth/invites/:tokenId', rateLimiter(20), requireAuth, requireProfile('system_admin'), async (req, res) => {
  const tokenId = parseInt(req.params.tokenId);
  console.log(`[UI] Revoke invite request for ID: ${tokenId}`);

  if (isNaN(tokenId)) {
    return res.status(400).json({ error: 'Invalid token ID' });
  }

  try {
    // Check token exists
    const { data: existing, error: fetchError } = await supabase
      .from('invite_tokens')
      .select('*')
      .eq('id', tokenId);

    if (fetchError || !existing || existing.length === 0) {
      return res.status(404).json({ error: `Invite token ${tokenId} not found` });
    }

    // Revoke it
    const { error: updateError } = await supabase
      .from('invite_tokens')
      .update({ is_revoked: true })
      .eq('id', tokenId);

    if (updateError) {
      console.error('[UI] Failed to revoke invite:', updateError);
      return res.status(500).json({ error: 'Failed to revoke invite' });
    }

    console.log(`[UI] Invite token ${tokenId} revoked by ${req.user.email}`);
    res.status(204).send();
  } catch (err) {
    console.error('[UI] Error revoking invite:', err);
    res.status(500).json({ error: 'Failed to revoke invite' });
  }
});

// Delete a user from auth.users (requires system_admin)
// This is useful to clean up stuck users from failed signup attempts
app.delete('/api/base/auth/users/:userId', rateLimiter(10), requireAuth, requireProfile('system_admin'), async (req, res) => {
  const userId = req.params.userId;
  console.log(`[UI] Delete auth user request for: ${userId}`);

  if (!userId) {
    return res.status(400).json({ error: 'User ID is required' });
  }

  // Prevent deleting yourself
  if (userId === req.user.id) {
    return res.status(400).json({ error: 'Cannot delete your own account' });
  }

  try {
    // Use Supabase admin API to delete user
    const { error } = await supabase.auth.admin.deleteUser(userId);

    if (error) {
      console.error('[UI] Failed to delete auth user:', error.message);
      return res.status(500).json({ error: error.message });
    }

    // Also delete from users table if exists
    await supabase.from('users').delete().eq('id', userId);

    console.log(`[UI] Auth user ${userId} deleted by ${req.user.email}`);
    res.json({ success: true, message: `User ${userId} deleted from auth.users` });
  } catch (err) {
    console.error('[UI] Error deleting auth user:', err);
    res.status(500).json({ error: 'Failed to delete user' });
  }
});

// Delete a user by email from auth.users (requires system_admin)
// Convenience endpoint when you only have the email
app.delete('/api/base/auth/users-by-email/:email', rateLimiter(10), requireAuth, requireProfile('system_admin'), async (req, res) => {
  const email = decodeURIComponent(req.params.email);
  console.log(`[UI] Delete auth user by email request for: ${email}`);

  if (!email) {
    return res.status(400).json({ error: 'Email is required' });
  }

  // Prevent deleting yourself
  if (email.toLowerCase() === req.user.email.toLowerCase()) {
    return res.status(400).json({ error: 'Cannot delete your own account' });
  }

  try {
    // First find the user in auth.users via admin API
    const { data: { users }, error: listError } = await supabase.auth.admin.listUsers();

    if (listError) {
      console.error('[UI] Failed to list users:', listError.message);
      return res.status(500).json({ error: listError.message });
    }

    const user = users.find(u => u.email?.toLowerCase() === email.toLowerCase());
    if (!user) {
      return res.status(404).json({ error: `No user found with email: ${email}` });
    }

    // Delete the user
    const { error } = await supabase.auth.admin.deleteUser(user.id);

    if (error) {
      console.error('[UI] Failed to delete auth user:', error.message);
      return res.status(500).json({ error: error.message });
    }

    // Also delete from users table if exists
    await supabase.from('users').delete().eq('id', user.id);

    console.log(`[UI] Auth user ${email} (${user.id}) deleted by ${req.user.email}`);
    res.json({ success: true, message: `User ${email} deleted from auth.users`, userId: user.id });
  } catch (err) {
    console.error('[UI] Error deleting auth user by email:', err);
    res.status(500).json({ error: 'Failed to delete user' });
  }
});

// Resend confirmation email for a user stuck in auth.users (requires system_admin)
// This is useful when a user exists in auth.users but never confirmed their email
app.post('/api/base/auth/resend-confirmation', rateLimiter(5), requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { email } = req.body;
  console.log(`[UI] Resend confirmation request for: ${email}`);

  if (!email) {
    return res.status(400).json({ error: 'Email is required' });
  }

  try {
    // Use Supabase's resend method to send a new confirmation email
    const { error } = await supabase.auth.resend({
      type: 'signup',
      email: email.toLowerCase(),
    });

    if (error) {
      console.error('[UI] Failed to resend confirmation:', error.message);
      // Check for common errors
      if (error.message.includes('already confirmed')) {
        return res.status(400).json({ error: 'User has already confirmed their email' });
      }
      if (error.message.includes('not found')) {
        return res.status(404).json({ error: 'No pending signup found for this email' });
      }
      return res.status(500).json({ error: error.message });
    }

    console.log(`[UI] Confirmation email resent to ${email}`);
    res.json({ success: true, message: `Confirmation email resent to ${email}` });
  } catch (err) {
    console.error('[UI] Error resending confirmation:', err);
    res.status(500).json({ error: 'Failed to resend confirmation email' });
  }
});

// Validate invite token (PUBLIC - for signup flow)
// Rate limited heavily to prevent brute force
app.post('/api/base/auth/validate-invite', rateLimiter(5), async (req, res) => {
  const { token, email } = req.body;

  if (!token || !email) {
    // Generic error for security
    return res.status(400).json({ error: 'Invalid or expired invite token' });
  }

  try {
    // Find the token
    const { data: tokens, error: fetchError } = await supabase
      .from('invite_tokens')
      .select('*')
      .eq('token', token);

    if (fetchError || !tokens || tokens.length === 0) {
      console.warn(`[UI] Invalid invite token attempted for: ${email}`);
      // Generic error - don't reveal if token exists
      return res.status(400).json({ error: 'Invalid or expired invite token' });
    }

    const tokenRecord = tokens[0];

    // Check if already used
    if (tokenRecord.used_at) {
      console.warn(`[UI] Token already used for: ${email}`);
      // Generic error
      return res.status(400).json({ error: 'Invalid or expired invite token' });
    }

    // Check if revoked
    if (tokenRecord.is_revoked) {
      console.warn(`[UI] Token revoked for: ${email}`);
      // Generic error
      return res.status(400).json({ error: 'Invalid or expired invite token' });
    }

    // Check expiry
    const now = new Date();
    const expiresAt = new Date(tokenRecord.expires_at);
    if (now > expiresAt) {
      console.warn(`[UI] Token expired for: ${email}, expired at: ${expiresAt}`);
      // Generic error
      return res.status(400).json({ error: 'Invalid or expired invite token' });
    }

    // Check email matches
    if (email.toLowerCase() !== tokenRecord.email.toLowerCase()) {
      console.warn(`[UI] Email mismatch: requested ${email}, token for ${tokenRecord.email}`);
      // Generic error
      return res.status(400).json({ error: 'Invalid or expired invite token' });
    }

    // NOTE: Don't mark token as used yet - wait until signup actually succeeds
    // The /api/base/auth/consume-invite endpoint will mark it as used

    console.log(`[UI] Invite token validated successfully for ${email} with profile ${tokenRecord.profile_name}`);

    res.json({
      valid: true,
      email: tokenRecord.email,
      profile_name: tokenRecord.profile_name,
    });
  } catch (err) {
    console.error('[UI] Error validating invite:', err);
    // Generic error
    res.status(400).json({ error: 'Invalid or expired invite token' });
  }
});

// Consume invite token (called AFTER successful Supabase signup)
// This marks the token as used AND creates the user in the users table with correct profile
app.post('/api/base/auth/consume-invite', rateLimiter(5), async (req, res) => {
  const { token, email, user_id, name } = req.body;

  if (!token || !email) {
    return res.status(400).json({ error: 'Missing token or email' });
  }

  console.log(`[UI] Consuming invite token for email: ${email}, user_id: ${user_id || 'not provided'}`);

  try {
    const now = new Date();

    // Find the token
    const { data: tokens, error: fetchError } = await supabase
      .from('invite_tokens')
      .select('*')
      .eq('token', token)
      .eq('email', email.toLowerCase());

    if (fetchError || !tokens || tokens.length === 0) {
      console.warn(`[UI] Token not found for consume: ${email}`);
      return res.status(400).json({ error: 'Token not found' });
    }

    const tokenRecord = tokens[0];

    // If already used, that's fine - just return success
    if (tokenRecord.used_at) {
      console.log(`[UI] Token already consumed for: ${email}`);
      return res.json({ success: true, already_used: true });
    }

    // Mark token as used
    const { error: updateError } = await supabase
      .from('invite_tokens')
      .update({ used_at: now.toISOString(), used_by_user_id: user_id || null })
      .eq('id', tokenRecord.id);

    if (updateError) {
      console.error('[UI] Failed to mark token as used:', updateError);
      return res.status(500).json({ error: 'Failed to consume token' });
    }

    // If user_id is provided, create user in users table with correct profile
    if (user_id) {
      // Get the profile ID for the invite's profile_name
      const { data: profile, error: profileError } = await supabase
        .from('profiles')
        .select('id')
        .eq('name', tokenRecord.profile_name)
        .single();

      if (profileError || !profile) {
        console.error(`[UI] Profile not found: ${tokenRecord.profile_name}`, profileError);
        // Don't fail the whole request - token is consumed, user can be fixed later
      } else {
        // Create or update user in users table
        const { error: userError } = await supabase
          .from('users')
          .upsert({
            id: user_id,
            email: email.toLowerCase(),
            name: name || email.split('@')[0],
            profile_id: profile.id,
            created_at: now.toISOString(),
          }, { onConflict: 'id' });

        if (userError) {
          console.error('[UI] Failed to create user in users table:', userError);
          // Don't fail - token is consumed, but log the error
        } else {
          console.log(`[UI] Created user ${email} with profile ${tokenRecord.profile_name}`);
        }
      }
    } else {
      console.warn(`[UI] No user_id provided for ${email} - user will need manual profile assignment`);
    }

    // Send welcome email (best effort - don't fail if it doesn't send)
    try {
      await sendWelcomeEmail({
        recipientEmail: email.toLowerCase(),
        recipientName: name || email.split('@')[0],
      });
      console.log(`[UI] Welcome email sent to ${email}`);
    } catch (emailErr) {
      console.error(`[UI] Failed to send welcome email to ${email}:`, emailErr.message);
      // Don't fail the request - user is created, just email failed
    }

    console.log(`[UI] Invite token consumed for ${email}`);
    res.json({ success: true });
  } catch (err) {
    console.error('[UI] Error consuming invite:', err);
    res.status(500).json({ error: 'Failed to consume token' });
  }
});

// =============================================================================
// SESSION ENDPOINT
// =============================================================================

// Verify session endpoint (for checking if user is authenticated)
app.get('/api/base/auth/session', async (req, res) => {
  console.log('[UI] Session check requested');
  if (!supabase) {
    console.error('[UI] Session check failed: Supabase not configured');
    return res.status(500).json({ error: 'Supabase not configured' });
  }

  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    console.log('[UI] Session check: No token provided');
    return res.json({ authenticated: false });
  }

  const token = authHeader.substring(7);

  try {
    const { data: { user }, error } = await supabase.auth.getUser(token);

    if (error || !user) {
      console.log('[UI] Session check: Invalid token');
      return res.json({ authenticated: false });
    }

    console.log('[UI] Session check: Valid session for', user.email);
    res.json({
      authenticated: true,
      user: {
        id: user.id,
        email: user.email,
        role: user.role
      }
    });
  } catch (err) {
    console.error('[UI] Session check error:', err.message);
    res.json({ authenticated: false });
  }
});

// Get current user's profile (for frontend to know user's role)
app.get('/api/base/auth/me', requireAuth, async (req, res) => {
  try {
    // Get user's profile from users table
    const { data: userData, error } = await supabase
      .from('users')
      .select('id, email, name, profile_id, is_active, profiles(name, display_name)')
      .eq('id', req.user.id)
      .single();

    if (error || !userData) {
      console.warn(`[UI] User ${req.user.email} not found in users table - rejecting`);
      return res.status(403).json({
        error: 'Account not found',
        code: 'USER_NOT_FOUND',
        requiresLogout: true
      });
    }

    // Check if user is deactivated
    if (userData.is_active === false) {
      console.warn(`[UI] User ${req.user.email} is deactivated - rejecting`);
      return res.status(403).json({
        error: 'Account deactivated',
        code: 'USER_DEACTIVATED',
        requiresLogout: true
      });
    }

    // Clear RBAC cache for this user to pick up any changes
    rbacCache.delete(req.user.id);

    console.log(`[UI] User profile fetched: ${userData.email} -> ${userData.profiles?.name}`);
    res.json({
      id: userData.id,
      email: userData.email,
      name: userData.name,
      profile_name: userData.profiles?.name || null,
      profile_display_name: userData.profiles?.display_name || null
    });
  } catch (err) {
    console.error('[UI] Error fetching user profile:', err.message);
    res.status(500).json({ error: 'Failed to fetch user profile' });
  }
});

// =============================================================================
// LOGOUT ENDPOINT - Properly invalidate session
// =============================================================================
app.post('/api/base/auth/logout', requireAuth, async (req, res) => {
  const userId = req.user.id;
  const userEmail = req.user.email;

  console.log(`[UI AUTH] Logout requested for user: ${userEmail}`);

  try {
    // 1. Clear RBAC cache for this user
    invalidateRBACCache(userId);

    // 2. Sign out from Supabase (invalidates refresh token)
    const { error } = await supabase.auth.admin.signOut(userId);

    if (error) {
      // Log but don't fail - user is logging out anyway
      console.warn(`[UI AUTH] Supabase signOut warning: ${error.message}`);
    }

    // 3. Audit log the logout
    await supabase.from('audit_log').insert({
      user_id: userId,
      user_email: userEmail,
      action: 'auth.logout',
      action_category: 'auth',
      resource_type: 'session',
      success: true
    });

    console.log(`[UI AUTH] User ${userEmail} logged out successfully`);
    res.json({ success: true, message: 'Logged out successfully' });

  } catch (err) {
    console.error(`[UI AUTH] Logout error: ${err.message}`);
    // Still return success - user wants to log out
    // Clear cache even on error
    invalidateRBACCache(userId);
    res.json({ success: true, message: 'Logged out (with warnings)' });
  }
});

// Force logout endpoint (admin can force logout a user)
app.post('/api/base/auth/force-logout/:userId', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { userId } = req.params;

  console.log(`[UI AUTH] Force logout requested for user: ${userId} by admin: ${req.user.email}`);

  try {
    // 1. Clear RBAC cache for target user
    invalidateRBACCache(userId);

    // 2. Sign out from Supabase
    const { error } = await supabase.auth.admin.signOut(userId);

    if (error) {
      console.warn(`[UI AUTH] Supabase force signOut warning: ${error.message}`);
    }

    // 3. Audit log
    await supabase.from('audit_log').insert({
      user_id: req.user.id,
      user_email: req.user.email,
      action: 'auth.force_logout',
      action_category: 'admin',
      resource_type: 'session',
      target_user_id: userId,
      success: true
    });

    console.log(`[UI AUTH] User ${userId} force logged out by ${req.user.email}`);
    res.json({ success: true });

  } catch (err) {
    console.error(`[UI AUTH] Force logout error: ${err.message}`);
    res.status(500).json({ error: 'Failed to force logout user' });
  }
});

// =============================================================================
// MODULES ENDPOINT - Get accessible modules for current user (RBAC)
// This replaces the proxied /api/sales/modules/accessible endpoint
// =============================================================================
app.get('/api/modules/accessible', requireAuth, async (req, res) => {
  console.log(`[UI RBAC] Getting accessible modules for user: ${req.user.email}`);

  try {
    // Get user's profile from users table
    const { data: userData, error: userError } = await supabase
      .from('users')
      .select('id, email, profile_id, profiles(id, name, display_name)')
      .eq('id', req.user.id)
      .single();

    if (userError) {
      console.warn(`[UI RBAC] Error fetching user: ${userError.message}`);
    }

    const profile = userData?.profiles;
    const profileName = profile?.name || null;

    console.log(`[UI RBAC] User profile: ${profileName || 'none'}`);

    // Get user's permissions from profile_permissions
    let permissions = new Set();
    if (profile?.id) {
      const { data: profilePerms, error: permError } = await supabase
        .from('profile_permissions')
        .select('permission')
        .eq('profile_id', profile.id);

      if (permError) {
        console.warn(`[UI RBAC] Error fetching permissions: ${permError.message}`);
      } else if (profilePerms) {
        profilePerms.forEach(p => permissions.add(p.permission));
      }
    }

    console.log(`[UI RBAC] User permissions: ${Array.from(permissions).join(', ') || 'none'}`);

    // Check if user is admin (has wildcard permission)
    const isAdmin = permissions.has('*:*:*') || profileName === 'system_admin';

    // Get all active modules
    const { data: allModules, error: modulesError } = await supabase
      .from('modules')
      .select('*')
      .eq('is_active', true)
      .order('sort_order');

    if (modulesError) {
      console.error(`[UI RBAC] Error fetching modules: ${modulesError.message}`);
      return res.status(500).json({ error: 'Failed to fetch modules' });
    }

    // Filter modules based on permissions
    const accessibleModules = [];

    for (const module of allModules || []) {
      // Admins can access everything
      if (isAdmin) {
        accessibleModules.push(module);
        continue;
      }

      // Check if user has required permission for this module
      const requiredPerm = module.required_permission;
      if (!requiredPerm) {
        // No permission required, module is accessible
        accessibleModules.push(module);
        continue;
      }

      // Check if user has the required permission (exact match or wildcard)
      const hasAccess = permissions.has(requiredPerm) ||
        permissions.has('*:*:*') ||
        Array.from(permissions).some(p => {
          // Check wildcard patterns like 'sales:*:*' matches 'sales:proposals:read'
          if (p.includes('*')) {
            const pattern = p.replace(/\*/g, '.*');
            return new RegExp(`^${pattern}$`).test(requiredPerm);
          }
          return false;
        });

      if (hasAccess) {
        accessibleModules.push(module);
      }
    }

    console.log(`[UI RBAC] Accessible modules: ${accessibleModules.map(m => m.name).join(', ') || 'none'}`);

    // If no modules found but user is authenticated, give them at least sales module as fallback
    if (accessibleModules.length === 0) {
      console.warn(`[UI RBAC] No modules found for user ${req.user.email}, providing fallback`);
      accessibleModules.push({
        name: 'sales',
        display_name: 'Sales Bot',
        description: 'Sales proposal generation, mockups, and booking orders',
        icon: 'chart-bar',
        is_default: true,
        sort_order: 1,
        tools: ['chat', 'mockup', 'proposals']
      });
    }

    // Format response to match what frontend expects
    const defaultModule = accessibleModules.find(m => m.is_default)?.name || accessibleModules[0]?.name;

    // Check for user-specific default module
    const { data: userModule } = await supabase
      .from('user_modules')
      .select('modules(name)')
      .eq('user_id', req.user.id)
      .eq('is_default', true)
      .single();

    const userDefaultModule = userModule?.modules?.name || null;

    res.json({
      modules: accessibleModules.map(m => ({
        name: m.name,
        display_name: m.display_name,
        description: m.description,
        icon: m.icon,
        is_default: m.is_default,
        sort_order: m.sort_order,
        tools: m.config_json?.tools || (m.name === 'sales' ? ['chat', 'mockup', 'proposals'] : ['admin'])
      })),
      default_module: defaultModule,
      user_default_module: userDefaultModule
    });

  } catch (err) {
    console.error(`[UI RBAC] Error getting modules: ${err.message}`);
    res.status(500).json({ error: 'Failed to get accessible modules' });
  }
});

// =============================================================================
// RBAC API ENDPOINTS - Admin only
// These endpoints expose RBAC data and require system_admin profile
// =============================================================================

// Get user's profile and permissions (admin only)
app.get('/api/rbac/user/:userId', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const userId = req.params.userId;
  console.log(`[UI RBAC API] Getting RBAC info for user: ${userId}`);

  try {
    // Get user's profile
    const { data: userData, error: userError } = await supabase
      .from('users')
      .select('id, email, name, profile_id, profiles(id, name, display_name)')
      .eq('id', userId)
      .single();

    if (userError || !userData) {
      console.warn(`[UI RBAC API] User not found: ${userId}`);
      return res.status(404).json({ error: 'User not found' });
    }

    const profile = userData.profiles;
    const profileName = profile?.name || null;

    // Get user's permissions from profile
    let permissions = [];
    if (profile?.id) {
      const { data: profilePerms } = await supabase
        .from('profile_permissions')
        .select('permission')
        .eq('profile_id', profile.id);

      if (profilePerms) {
        permissions = profilePerms.map(p => p.permission);
      }
    }

    // Get user's permission sets
    const { data: userPermSets } = await supabase
      .from('user_permission_sets')
      .select('permission_sets(id, name, display_name)')
      .eq('user_id', userId);

    const permissionSets = userPermSets?.map(ups => ups.permission_sets) || [];

    // Get permissions from permission sets
    for (const ps of permissionSets) {
      if (ps?.id) {
        const { data: psPerms } = await supabase
          .from('permission_set_permissions')
          .select('permission')
          .eq('permission_set_id', ps.id);

        if (psPerms) {
          permissions.push(...psPerms.map(p => p.permission));
        }
      }
    }

    // Deduplicate permissions
    permissions = [...new Set(permissions)];

    res.json({
      user_id: userId,
      email: userData.email,
      name: userData.name,
      profile: profileName,
      profile_display_name: profile?.display_name || null,
      permissions: permissions,
      permission_sets: permissionSets.map(ps => ps?.name).filter(Boolean),
    });

  } catch (err) {
    console.error(`[UI RBAC API] Error getting user RBAC: ${err.message}`);
    res.status(500).json({ error: 'Failed to get user RBAC info' });
  }
});

// Check if user has a specific permission (admin only)
app.get('/api/rbac/check', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { user_id, permission } = req.query;

  if (!user_id || !permission) {
    return res.status(400).json({ error: 'user_id and permission are required' });
  }

  console.log(`[UI RBAC API] Checking permission ${permission} for user ${user_id}`);

  try {
    // Get user's profile
    const { data: userData } = await supabase
      .from('users')
      .select('profile_id, profiles(id, name)')
      .eq('id', user_id)
      .single();

    const profile = userData?.profiles;

    // Get user's permissions
    let permissions = new Set();
    if (profile?.id) {
      const { data: profilePerms } = await supabase
        .from('profile_permissions')
        .select('permission')
        .eq('profile_id', profile.id);

      if (profilePerms) {
        profilePerms.forEach(p => permissions.add(p.permission));
      }
    }

    // Check permission (exact match or wildcard)
    const hasPermission = permissions.has(permission) ||
      permissions.has('*:*:*') ||
      Array.from(permissions).some(p => {
        if (p.includes('*')) {
          const pattern = p.replace(/\*/g, '.*');
          return new RegExp(`^${pattern}$`).test(permission);
        }
        return false;
      });

    res.json({
      user_id,
      permission,
      has_permission: hasPermission,
      profile: profile?.name || null,
    });

  } catch (err) {
    console.error(`[UI RBAC API] Error checking permission: ${err.message}`);
    res.status(500).json({ error: 'Failed to check permission' });
  }
});

// List all profiles (admin only)
app.get('/api/rbac/profiles', requireAuth, requireProfile('system_admin'), async (req, res) => {
  console.log(`[UI RBAC API] Listing profiles`);

  try {
    const { data: profiles, error } = await supabase
      .from('profiles')
      .select('*')
      .order('name');

    if (error) {
      throw error;
    }

    // Get permissions for each profile
    const result = [];
    for (const profile of profiles || []) {
      const { data: perms } = await supabase
        .from('profile_permissions')
        .select('permission')
        .eq('profile_id', profile.id);

      result.push({
        id: profile.id,
        name: profile.name,
        display_name: profile.display_name,
        description: profile.description,
        is_system: profile.is_system,
        permissions: perms?.map(p => p.permission) || [],
        created_at: profile.created_at,
        updated_at: profile.updated_at,
      });
    }

    res.json(result);

  } catch (err) {
    console.error(`[UI RBAC API] Error listing profiles: ${err.message}`);
    res.status(500).json({ error: 'Failed to list profiles' });
  }
});

// Get single profile by ID (admin only)
app.get('/api/rbac/profiles/:id', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { id } = req.params;
  console.log(`[UI RBAC API] Getting profile: ${id}`);

  try {
    const { data: profile, error } = await supabase
      .from('profiles')
      .select('*')
      .eq('id', id)
      .single();

    if (error) {
      if (error.code === 'PGRST116') {
        return res.status(404).json({ error: 'Profile not found' });
      }
      throw error;
    }

    // Get permissions for profile
    const { data: perms } = await supabase
      .from('profile_permissions')
      .select('permission')
      .eq('profile_id', profile.id);

    res.json({
      ...profile,
      permissions: perms?.map(p => p.permission) || [],
    });

  } catch (err) {
    console.error(`[UI RBAC API] Error getting profile: ${err.message}`);
    res.status(500).json({ error: 'Failed to get profile' });
  }
});

// Create profile (admin only)
app.post('/api/rbac/profiles', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { name, display_name, description, permissions } = req.body;

  if (!name || !display_name) {
    return res.status(400).json({ error: 'name and display_name are required' });
  }

  // Validate name format (lowercase, underscores only)
  if (!/^[a-z][a-z0-9_]*$/.test(name)) {
    return res.status(400).json({ error: 'name must start with lowercase letter and contain only lowercase letters, numbers, and underscores' });
  }

  console.log(`[UI RBAC API] Creating profile: ${name}`);

  try {
    // Check if profile already exists
    const { data: existing } = await supabase
      .from('profiles')
      .select('id')
      .eq('name', name)
      .single();

    if (existing) {
      return res.status(409).json({ error: 'Profile with this name already exists' });
    }

    // Create profile (is_system defaults to false for user-created profiles)
    const { data: profile, error } = await supabase
      .from('profiles')
      .insert({ name, display_name, description, is_system: false })
      .select()
      .single();

    if (error) throw error;

    // Add permissions if provided
    if (permissions?.length > 0) {
      const permInserts = permissions.map(p => ({
        profile_id: profile.id,
        permission: p
      }));

      const { error: permError } = await supabase
        .from('profile_permissions')
        .insert(permInserts);

      if (permError) {
        console.error(`[UI RBAC API] Error adding permissions to profile: ${permError.message}`);
      }
    }

    // Audit log
    await supabase.from('audit_log').insert({
      user_id: req.user.id,
      action: 'profile.create',
      action_category: 'rbac',
      resource_type: 'profile',
      resource_id: profile.id.toString(),
      new_value: { name, display_name, description, permissions: permissions || [] }
    });

    res.status(201).json({ ...profile, permissions: permissions || [] });

  } catch (err) {
    console.error(`[UI RBAC API] Error creating profile: ${err.message}`);
    res.status(500).json({ error: 'Failed to create profile' });
  }
});

// Update profile (admin only)
app.put('/api/rbac/profiles/:id', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { id } = req.params;
  const { display_name, description, permissions } = req.body;

  console.log(`[UI RBAC API] Updating profile: ${id}`);

  try {
    // Get current profile
    const { data: current, error: fetchError } = await supabase
      .from('profiles')
      .select('*')
      .eq('id', id)
      .single();

    if (fetchError) {
      if (fetchError.code === 'PGRST116') {
        return res.status(404).json({ error: 'Profile not found' });
      }
      throw fetchError;
    }

    // Cannot modify system profiles' core settings
    if (current.is_system && (display_name !== undefined || description !== undefined)) {
      console.log(`[UI RBAC API] Warning: Modifying system profile ${current.name}`);
    }

    // Build updates object
    const updates = { updated_at: new Date().toISOString() };
    if (display_name !== undefined) updates.display_name = display_name;
    if (description !== undefined) updates.description = description;

    // Update profile
    const { data: profile, error } = await supabase
      .from('profiles')
      .update(updates)
      .eq('id', id)
      .select()
      .single();

    if (error) throw error;

    // Get old permissions for audit
    const { data: oldPerms } = await supabase
      .from('profile_permissions')
      .select('permission')
      .eq('profile_id', id);

    const oldPermissions = oldPerms?.map(p => p.permission) || [];

    // Update permissions if provided
    if (permissions !== undefined) {
      // Delete existing permissions
      await supabase.from('profile_permissions').delete().eq('profile_id', id);

      // Insert new permissions
      if (permissions.length > 0) {
        const permInserts = permissions.map(p => ({
          profile_id: id,
          permission: p
        }));
        await supabase.from('profile_permissions').insert(permInserts);
      }
    }

    // Clear RBAC cache for all users with this profile
    const { data: usersWithProfile } = await supabase
      .from('users')
      .select('id')
      .eq('profile_id', id);

    for (const user of usersWithProfile || []) {
      rbacCache.delete(user.id);
    }

    // Audit log
    await supabase.from('audit_log').insert({
      user_id: req.user.id,
      action: 'profile.update',
      action_category: 'rbac',
      resource_type: 'profile',
      resource_id: id.toString(),
      old_value: { display_name: current.display_name, description: current.description, permissions: oldPermissions },
      new_value: { display_name: profile.display_name, description: profile.description, permissions: permissions !== undefined ? permissions : oldPermissions }
    });

    res.json({ ...profile, permissions: permissions !== undefined ? permissions : oldPermissions });

  } catch (err) {
    console.error(`[UI RBAC API] Error updating profile: ${err.message}`);
    res.status(500).json({ error: 'Failed to update profile' });
  }
});

// Delete profile (admin only)
app.delete('/api/rbac/profiles/:id', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { id } = req.params;

  console.log(`[UI RBAC API] Deleting profile: ${id}`);

  try {
    // Get profile first
    const { data: profile, error: fetchError } = await supabase
      .from('profiles')
      .select('*')
      .eq('id', id)
      .single();

    if (fetchError) {
      if (fetchError.code === 'PGRST116') {
        return res.status(404).json({ error: 'Profile not found' });
      }
      throw fetchError;
    }

    // Cannot delete system profiles
    if (profile.is_system) {
      return res.status(403).json({ error: 'Cannot delete system profiles' });
    }

    // Check if any users have this profile
    const { data: usersWithProfile, error: userError } = await supabase
      .from('users')
      .select('id, email')
      .eq('profile_id', id);

    if (userError) throw userError;

    if (usersWithProfile?.length > 0) {
      return res.status(409).json({
        error: 'Cannot delete profile with assigned users',
        users_count: usersWithProfile.length,
        hint: 'Reassign users to another profile first'
      });
    }

    // Get permissions for audit log
    const { data: perms } = await supabase
      .from('profile_permissions')
      .select('permission')
      .eq('profile_id', id);

    // Delete profile permissions first (cascade should handle this but being explicit)
    await supabase.from('profile_permissions').delete().eq('profile_id', id);

    // Delete profile
    const { error } = await supabase
      .from('profiles')
      .delete()
      .eq('id', id);

    if (error) throw error;

    // Audit log
    await supabase.from('audit_log').insert({
      user_id: req.user.id,
      action: 'profile.delete',
      action_category: 'rbac',
      resource_type: 'profile',
      resource_id: id.toString(),
      old_value: { ...profile, permissions: perms?.map(p => p.permission) || [] }
    });

    res.json({ success: true, deleted: profile.name });

  } catch (err) {
    console.error(`[UI RBAC API] Error deleting profile: ${err.message}`);
    res.status(500).json({ error: 'Failed to delete profile' });
  }
});

// List all permissions (admin only)
app.get('/api/rbac/permissions', requireAuth, requireProfile('system_admin'), async (req, res) => {
  console.log(`[UI RBAC API] Listing permissions`);

  try {
    const { data: permissions, error } = await supabase
      .from('permissions')
      .select('*')
      .order('module, resource, action');

    if (error) {
      throw error;
    }

    res.json(permissions || []);

  } catch (err) {
    console.error(`[UI RBAC API] Error listing permissions: ${err.message}`);
    res.status(500).json({ error: 'Failed to list permissions' });
  }
});

// Get permissions grouped by resource (admin only)
app.get('/api/rbac/permissions/grouped', requireAuth, requireProfile('system_admin'), async (req, res) => {
  console.log(`[UI RBAC API] Listing permissions grouped`);

  try {
    const { data: permissions, error } = await supabase
      .from('permissions')
      .select('*')
      .order('module, resource, action');

    if (error) {
      throw error;
    }

    // Group by resource (module:resource)
    const grouped = {};
    for (const perm of permissions || []) {
      const key = `${perm.module}:${perm.resource}`;
      if (!grouped[key]) {
        grouped[key] = [];
      }
      grouped[key].push(perm);
    }

    res.json(grouped);

  } catch (err) {
    console.error(`[UI RBAC API] Error listing permissions: ${err.message}`);
    res.status(500).json({ error: 'Failed to list permissions' });
  }
});

// =============================================================================
// LEVEL 2: PERMISSION SET MANAGEMENT APIs
// =============================================================================

// List all permission sets (admin only)
app.get('/api/rbac/permission-sets', requireAuth, requireProfile('system_admin'), async (req, res) => {
  console.log(`[UI RBAC API] Listing permission sets`);

  try {
    const { data: sets, error } = await supabase
      .from('permission_sets')
      .select(`
        *,
        permission_set_permissions(permission)
      `)
      .order('name');

    if (error) throw error;

    // Transform to include permissions array
    const result = (sets || []).map(s => ({
      ...s,
      permissions: (s.permission_set_permissions || []).map(p => p.permission)
    }));

    res.json(result);
  } catch (err) {
    console.error(`[UI RBAC API] Error listing permission sets: ${err.message}`);
    res.status(500).json({ error: 'Failed to list permission sets' });
  }
});

// Create permission set (admin only)
app.post('/api/rbac/permission-sets', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { name, display_name, description, permissions } = req.body;

  if (!name || !display_name) {
    return res.status(400).json({ error: 'name and display_name are required' });
  }

  console.log(`[UI RBAC API] Creating permission set: ${name}`);

  try {
    // Create permission set
    const { data: set, error } = await supabase
      .from('permission_sets')
      .insert({ name, display_name, description })
      .select()
      .single();

    if (error) throw error;

    // Add permissions if provided
    if (permissions?.length > 0) {
      const permInserts = permissions.map(p => ({
        permission_set_id: set.id,
        permission: p
      }));

      await supabase.from('permission_set_permissions').insert(permInserts);
    }

    res.status(201).json({ ...set, permissions: permissions || [] });
  } catch (err) {
    console.error(`[UI RBAC API] Error creating permission set: ${err.message}`);
    res.status(500).json({ error: 'Failed to create permission set' });
  }
});

// Update permission set (admin only)
app.put('/api/rbac/permission-sets/:id', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { id } = req.params;
  const { display_name, description, is_active, permissions } = req.body;

  console.log(`[UI RBAC API] Updating permission set: ${id}`);

  try {
    // Update permission set
    const updates = {};
    if (display_name !== undefined) updates.display_name = display_name;
    if (description !== undefined) updates.description = description;
    if (is_active !== undefined) updates.is_active = is_active;

    const { data: set, error } = await supabase
      .from('permission_sets')
      .update(updates)
      .eq('id', id)
      .select()
      .single();

    if (error) throw error;

    // Update permissions if provided
    if (permissions !== undefined) {
      // Delete existing
      await supabase.from('permission_set_permissions').delete().eq('permission_set_id', id);

      // Insert new
      if (permissions.length > 0) {
        const permInserts = permissions.map(p => ({
          permission_set_id: id,
          permission: p
        }));
        await supabase.from('permission_set_permissions').insert(permInserts);
      }
    }

    res.json({ ...set, permissions: permissions || [] });
  } catch (err) {
    console.error(`[UI RBAC API] Error updating permission set: ${err.message}`);
    res.status(500).json({ error: 'Failed to update permission set' });
  }
});

// Delete permission set (admin only)
app.delete('/api/rbac/permission-sets/:id', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { id } = req.params;

  console.log(`[UI RBAC API] Deleting permission set: ${id}`);

  try {
    // Get permission set first
    const { data: permSet, error: fetchError } = await supabase
      .from('permission_sets')
      .select('*')
      .eq('id', id)
      .single();

    if (fetchError) {
      if (fetchError.code === 'PGRST116') {
        return res.status(404).json({ error: 'Permission set not found' });
      }
      throw fetchError;
    }

    // Check if any users have this permission set assigned
    const { data: usersWithSet, error: userError } = await supabase
      .from('user_permission_sets')
      .select('user_id')
      .eq('permission_set_id', id);

    if (userError) throw userError;

    if (usersWithSet?.length > 0) {
      return res.status(409).json({
        error: 'Cannot delete permission set with assigned users',
        users_count: usersWithSet.length,
        hint: 'Revoke this permission set from all users first'
      });
    }

    // Get permissions for audit log
    const { data: perms } = await supabase
      .from('permission_set_permissions')
      .select('permission')
      .eq('permission_set_id', id);

    // Delete permission set permissions first
    await supabase.from('permission_set_permissions').delete().eq('permission_set_id', id);

    // Delete permission set
    const { error } = await supabase
      .from('permission_sets')
      .delete()
      .eq('id', id);

    if (error) throw error;

    // Audit log
    await supabase.from('audit_log').insert({
      user_id: req.user.id,
      action: 'permission_set.delete',
      action_category: 'rbac',
      resource_type: 'permission_set',
      resource_id: id.toString(),
      old_value: { ...permSet, permissions: perms?.map(p => p.permission) || [] }
    });

    res.json({ success: true, deleted: permSet.name });

  } catch (err) {
    console.error(`[UI RBAC API] Error deleting permission set: ${err.message}`);
    res.status(500).json({ error: 'Failed to delete permission set' });
  }
});

// Assign permission set to user (admin only)
app.post('/api/rbac/users/:userId/permission-sets', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { userId } = req.params;
  const { permission_set_id, expires_at } = req.body;

  if (!permission_set_id) {
    return res.status(400).json({ error: 'permission_set_id is required' });
  }

  console.log(`[UI RBAC API] Assigning permission set ${permission_set_id} to user ${userId}`);

  try {
    const { data, error } = await supabase
      .from('user_permission_sets')
      .insert({
        user_id: userId,
        permission_set_id,
        granted_by: req.user.id,
        expires_at: expires_at || null
      })
      .select()
      .single();

    if (error) throw error;

    // Clear RBAC cache for this user
    rbacCache.delete(userId);

    res.status(201).json(data);
  } catch (err) {
    console.error(`[UI RBAC API] Error assigning permission set: ${err.message}`);
    res.status(500).json({ error: 'Failed to assign permission set' });
  }
});

// Revoke permission set from user (admin only)
app.delete('/api/rbac/users/:userId/permission-sets/:setId', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { userId, setId } = req.params;

  console.log(`[UI RBAC API] Revoking permission set ${setId} from user ${userId}`);

  try {
    const { error } = await supabase
      .from('user_permission_sets')
      .delete()
      .eq('user_id', userId)
      .eq('permission_set_id', setId);

    if (error) throw error;

    // Clear RBAC cache for this user
    rbacCache.delete(userId);

    res.json({ success: true });
  } catch (err) {
    console.error(`[UI RBAC API] Error revoking permission set: ${err.message}`);
    res.status(500).json({ error: 'Failed to revoke permission set' });
  }
});

// Get user's permission sets (admin only)
app.get('/api/rbac/users/:userId/permission-sets', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { userId } = req.params;

  try {
    const { data, error } = await supabase
      .from('user_permission_sets')
      .select(`
        *,
        permission_sets(id, name, display_name, is_active)
      `)
      .eq('user_id', userId);

    if (error) throw error;

    res.json(data || []);
  } catch (err) {
    console.error(`[UI RBAC API] Error getting user permission sets: ${err.message}`);
    res.status(500).json({ error: 'Failed to get user permission sets' });
  }
});

// =============================================================================
// LEVEL 3: TEAM MANAGEMENT APIs
// =============================================================================

// List all teams (admin only)
app.get('/api/rbac/teams', requireAuth, requireProfile('system_admin'), async (req, res) => {
  console.log(`[UI RBAC API] Listing teams`);

  try {
    const { data: teams, error } = await supabase
      .from('teams')
      .select(`
        *,
        parent:parent_team_id(id, name, display_name)
      `)
      .order('name');

    if (error) throw error;

    res.json(teams || []);
  } catch (err) {
    console.error(`[UI RBAC API] Error listing teams: ${err.message}`);
    res.status(500).json({ error: 'Failed to list teams' });
  }
});

// Create team (admin only)
app.post('/api/rbac/teams', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { name, display_name, description, parent_team_id } = req.body;

  if (!name) {
    return res.status(400).json({ error: 'name is required' });
  }

  console.log(`[UI RBAC API] Creating team: ${name}`);

  try {
    const { data: team, error } = await supabase
      .from('teams')
      .insert({ name, display_name: display_name || name, description, parent_team_id })
      .select()
      .single();

    if (error) throw error;

    res.status(201).json(team);
  } catch (err) {
    console.error(`[UI RBAC API] Error creating team: ${err.message}`);
    res.status(500).json({ error: 'Failed to create team' });
  }
});

// Update team (admin only)
app.put('/api/rbac/teams/:id', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { id } = req.params;
  const { name, display_name, description, parent_team_id, is_active } = req.body;

  console.log(`[UI RBAC API] Updating team: ${id}`);

  try {
    const updates = {};
    if (name !== undefined) updates.name = name;
    if (display_name !== undefined) updates.display_name = display_name;
    if (description !== undefined) updates.description = description;
    if (parent_team_id !== undefined) updates.parent_team_id = parent_team_id;
    if (is_active !== undefined) updates.is_active = is_active;

    const { data: team, error } = await supabase
      .from('teams')
      .update(updates)
      .eq('id', id)
      .select()
      .single();

    if (error) throw error;

    res.json(team);
  } catch (err) {
    console.error(`[UI RBAC API] Error updating team: ${err.message}`);
    res.status(500).json({ error: 'Failed to update team' });
  }
});

// Delete team (admin only)
app.delete('/api/rbac/teams/:id', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { id } = req.params;

  console.log(`[UI RBAC API] Deleting team: ${id}`);

  try {
    const { error } = await supabase
      .from('teams')
      .delete()
      .eq('id', id);

    if (error) throw error;

    res.json({ success: true });
  } catch (err) {
    console.error(`[UI RBAC API] Error deleting team: ${err.message}`);
    res.status(500).json({ error: 'Failed to delete team' });
  }
});

// Get team members (admin only)
app.get('/api/rbac/teams/:id/members', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { id } = req.params;

  try {
    const { data: members, error } = await supabase
      .from('team_members')
      .select(`
        *,
        users(id, email, name, is_active)
      `)
      .eq('team_id', id);

    if (error) throw error;

    res.json(members || []);
  } catch (err) {
    console.error(`[UI RBAC API] Error getting team members: ${err.message}`);
    res.status(500).json({ error: 'Failed to get team members' });
  }
});

// Add user to team (admin only)
app.post('/api/rbac/teams/:id/members', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { id } = req.params;
  const { user_id, role } = req.body;

  if (!user_id) {
    return res.status(400).json({ error: 'user_id is required' });
  }

  console.log(`[UI RBAC API] Adding user ${user_id} to team ${id}`);

  try {
    const { data, error } = await supabase
      .from('team_members')
      .insert({
        team_id: parseInt(id),
        user_id,
        role: role || 'member'
      })
      .select()
      .single();

    if (error) throw error;

    // Clear RBAC cache for this user
    rbacCache.delete(user_id);

    res.status(201).json(data);
  } catch (err) {
    console.error(`[UI RBAC API] Error adding team member: ${err.message}`);
    res.status(500).json({ error: 'Failed to add team member' });
  }
});

// Update team member role (admin only)
app.put('/api/rbac/teams/:id/members/:userId', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { id, userId } = req.params;
  const { role } = req.body;

  if (!role || !['member', 'leader'].includes(role)) {
    return res.status(400).json({ error: 'Valid role (member or leader) is required' });
  }

  console.log(`[UI RBAC API] Updating role for user ${userId} in team ${id} to ${role}`);

  try {
    const { data, error } = await supabase
      .from('team_members')
      .update({ role })
      .eq('team_id', id)
      .eq('user_id', userId)
      .select()
      .single();

    if (error) throw error;

    // Clear RBAC cache for this user
    rbacCache.delete(userId);

    res.json(data);
  } catch (err) {
    console.error(`[UI RBAC API] Error updating team member: ${err.message}`);
    res.status(500).json({ error: 'Failed to update team member' });
  }
});

// Remove user from team (admin only)
app.delete('/api/rbac/teams/:id/members/:userId', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { id, userId } = req.params;

  console.log(`[UI RBAC API] Removing user ${userId} from team ${id}`);

  try {
    const { error } = await supabase
      .from('team_members')
      .delete()
      .eq('team_id', id)
      .eq('user_id', userId);

    if (error) throw error;

    // Clear RBAC cache for this user
    rbacCache.delete(userId);

    res.json({ success: true });
  } catch (err) {
    console.error(`[UI RBAC API] Error removing team member: ${err.message}`);
    res.status(500).json({ error: 'Failed to remove team member' });
  }
});

// Set user's manager (admin only)
app.put('/api/rbac/users/:userId/manager', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { userId } = req.params;
  const { manager_id } = req.body;

  console.log(`[UI RBAC API] Setting manager for user ${userId} to ${manager_id || 'none'}`);

  try {
    const { data, error } = await supabase
      .from('users')
      .update({ manager_id: manager_id || null })
      .eq('id', userId)
      .select()
      .single();

    if (error) throw error;

    // Clear RBAC cache for this user and their manager
    rbacCache.delete(userId);
    if (manager_id) rbacCache.delete(manager_id);

    res.json(data);
  } catch (err) {
    console.error(`[UI RBAC API] Error setting manager: ${err.message}`);
    res.status(500).json({ error: 'Failed to set manager' });
  }
});

// =============================================================================
// LEVEL 4: RECORD SHARING APIs
// =============================================================================

// List sharing rules (admin only)
app.get('/api/rbac/sharing-rules', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { object_type } = req.query;

  console.log(`[UI RBAC API] Listing sharing rules`);

  try {
    let query = supabase.from('sharing_rules').select('*').order('object_type, name');

    if (object_type) {
      query = query.eq('object_type', object_type);
    }

    const { data: rules, error } = await query;

    if (error) throw error;

    res.json(rules || []);
  } catch (err) {
    console.error(`[UI RBAC API] Error listing sharing rules: ${err.message}`);
    res.status(500).json({ error: 'Failed to list sharing rules' });
  }
});

// Create sharing rule (admin only)
app.post('/api/rbac/sharing-rules', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { name, description, object_type, share_from_type, share_from_id, share_to_type, share_to_id, access_level } = req.body;

  if (!name || !object_type || !share_from_type || !share_to_type || !access_level) {
    return res.status(400).json({ error: 'name, object_type, share_from_type, share_to_type, and access_level are required' });
  }

  console.log(`[UI RBAC API] Creating sharing rule: ${name}`);

  try {
    const { data: rule, error } = await supabase
      .from('sharing_rules')
      .insert({ name, description, object_type, share_from_type, share_from_id, share_to_type, share_to_id, access_level })
      .select()
      .single();

    if (error) throw error;

    res.status(201).json(rule);
  } catch (err) {
    console.error(`[UI RBAC API] Error creating sharing rule: ${err.message}`);
    res.status(500).json({ error: 'Failed to create sharing rule' });
  }
});

// Update sharing rule (admin only)
app.put('/api/rbac/sharing-rules/:id', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { id } = req.params;
  const { name, description, share_from_type, share_from_id, share_to_type, share_to_id, access_level, is_active } = req.body;

  console.log(`[UI RBAC API] Updating sharing rule: ${id}`);

  try {
    const updates = {};
    if (name !== undefined) updates.name = name;
    if (description !== undefined) updates.description = description;
    if (share_from_type !== undefined) updates.share_from_type = share_from_type;
    if (share_from_id !== undefined) updates.share_from_id = share_from_id;
    if (share_to_type !== undefined) updates.share_to_type = share_to_type;
    if (share_to_id !== undefined) updates.share_to_id = share_to_id;
    if (access_level !== undefined) updates.access_level = access_level;
    if (is_active !== undefined) updates.is_active = is_active;

    const { data: rule, error } = await supabase
      .from('sharing_rules')
      .update(updates)
      .eq('id', id)
      .select()
      .single();

    if (error) throw error;

    res.json(rule);
  } catch (err) {
    console.error(`[UI RBAC API] Error updating sharing rule: ${err.message}`);
    res.status(500).json({ error: 'Failed to update sharing rule' });
  }
});

// Delete sharing rule (admin only)
app.delete('/api/rbac/sharing-rules/:id', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { id } = req.params;

  console.log(`[UI RBAC API] Deleting sharing rule: ${id}`);

  try {
    const { error } = await supabase
      .from('sharing_rules')
      .delete()
      .eq('id', id);

    if (error) throw error;

    res.json({ success: true });
  } catch (err) {
    console.error(`[UI RBAC API] Error deleting sharing rule: ${err.message}`);
    res.status(500).json({ error: 'Failed to delete sharing rule' });
  }
});

// NOTE: Record share creation moved to POST /api/rbac/shares (see LEVEL 4 section below)
// This endpoint is deprecated - use POST /api/rbac/shares instead

// List shares for a record (owner or admin)
app.get('/api/rbac/record-shares/:objectType/:recordId', requireAuth, async (req, res) => {
  const { objectType, recordId } = req.params;

  try {
    const { data: shares, error } = await supabase
      .from('record_shares')
      .select(`
        *,
        shared_with_user:shared_with_user_id(id, email, name),
        shared_with_team:shared_with_team_id(id, name, display_name),
        sharer:shared_by(id, email, name)
      `)
      .eq('object_type', objectType)
      .eq('record_id', recordId);

    if (error) throw error;

    res.json(shares || []);
  } catch (err) {
    console.error(`[UI RBAC API] Error listing record shares: ${err.message}`);
    res.status(500).json({ error: 'Failed to list record shares' });
  }
});

// Revoke a record share (owner, admin, or the person who created the share)
app.delete('/api/rbac/record-shares/:id', requireAuth, async (req, res) => {
  const { id } = req.params;

  console.log(`[UI RBAC API] Revoking record share: ${id}`);

  try {
    // First check if user can delete this share (must be admin or the one who shared it)
    const { data: share, error: fetchError } = await supabase
      .from('record_shares')
      .select('shared_by')
      .eq('id', id)
      .single();

    if (fetchError) throw fetchError;

    // Check permissions
    const isAdmin = req.user.profile === 'system_admin';
    const isOwner = share.shared_by === req.user.id;

    if (!isAdmin && !isOwner) {
      return res.status(403).json({ error: 'Not authorized to revoke this share' });
    }

    const { error } = await supabase
      .from('record_shares')
      .delete()
      .eq('id', id);

    if (error) throw error;

    res.json({ success: true });
  } catch (err) {
    console.error(`[UI RBAC API] Error revoking record share: ${err.message}`);
    res.status(500).json({ error: 'Failed to revoke record share' });
  }
});

// Get current user's RBAC context (any authenticated user)
app.get('/api/rbac/my-context', requireAuth, async (req, res) => {
  try {
    const rbac = await getUserRBACData(req.user.id);

    if (!rbac) {
      return res.status(403).json({ error: 'User not found or deactivated' });
    }

    res.json({
      userId: req.user.id,
      email: req.user.email,
      ...rbac
    });
  } catch (err) {
    console.error(`[UI RBAC API] Error getting user context: ${err.message}`);
    res.status(500).json({ error: 'Failed to get user context' });
  }
});

// =============================================================================
// USER MANAGEMENT APIs (Admin)
// =============================================================================

// List all users (admin only) with pagination and filters
app.get('/api/rbac/users', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { page = 1, limit = 50, search, profile, team, is_active } = req.query;
  const offset = (parseInt(page) - 1) * parseInt(limit);

  console.log(`[UI RBAC API] Listing users (page=${page}, limit=${limit}, search=${search})`);

  try {
    let query = supabase
      .from('users')
      .select(`
        *,
        profiles(id, name, display_name),
        team_members(team_id, role, teams(id, name, display_name))
      `, { count: 'exact' });

    // Apply filters
    if (search) {
      query = query.or(`email.ilike.%${search}%,name.ilike.%${search}%`);
    }

    if (profile) {
      // Get profile ID first
      const { data: profileData } = await supabase
        .from('profiles')
        .select('id')
        .eq('name', profile)
        .single();

      if (profileData) {
        query = query.eq('profile_id', profileData.id);
      }
    }

    if (is_active !== undefined) {
      query = query.eq('is_active', is_active === 'true');
    }

    // Apply pagination
    query = query
      .order('created_at', { ascending: false })
      .range(offset, offset + parseInt(limit) - 1);

    const { data: users, error, count } = await query;

    if (error) throw error;

    // Filter by team if specified (post-query filter due to nested relationship)
    let filteredUsers = users;
    if (team) {
      const teamId = parseInt(team);
      filteredUsers = users.filter(u =>
        u.team_members?.some(tm => tm.team_id === teamId)
      );
    }

    res.json({
      users: filteredUsers || [],
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total: count || 0,
        totalPages: Math.ceil((count || 0) / parseInt(limit))
      }
    });
  } catch (err) {
    console.error(`[UI RBAC API] Error listing users: ${err.message}`);
    res.status(500).json({ error: 'Failed to list users' });
  }
});

// Update user (admin only) - name, avatar, is_active, profile
app.put('/api/rbac/users/:userId', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { userId } = req.params;
  const { name, avatar_url, is_active, profile_id, profile_name } = req.body;

  console.log(`[UI RBAC API] Updating user: ${userId}`);

  try {
    const updates = {};
    if (name !== undefined) updates.name = name;
    if (avatar_url !== undefined) updates.avatar_url = avatar_url;
    if (is_active !== undefined) updates.is_active = is_active;

    // Handle profile assignment by name or ID
    if (profile_name !== undefined) {
      const { data: profileData } = await supabase
        .from('profiles')
        .select('id')
        .eq('name', profile_name)
        .single();

      if (profileData) {
        updates.profile_id = profileData.id;
      } else {
        return res.status(400).json({ error: `Profile '${profile_name}' not found` });
      }
    } else if (profile_id !== undefined) {
      updates.profile_id = profile_id;
    }

    if (Object.keys(updates).length === 0) {
      return res.status(400).json({ error: 'No fields to update' });
    }

    const { data: user, error } = await supabase
      .from('users')
      .update(updates)
      .eq('id', userId)
      .select(`
        *,
        profiles(id, name, display_name)
      `)
      .single();

    if (error) throw error;

    // Clear RBAC cache for this user
    rbacCache.delete(userId);

    res.json(user);
  } catch (err) {
    console.error(`[UI RBAC API] Error updating user: ${err.message}`);
    res.status(500).json({ error: 'Failed to update user' });
  }
});

// Deactivate user (admin only) - soft delete
app.post('/api/rbac/users/:userId/deactivate', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { userId } = req.params;

  console.log(`[UI RBAC API] Deactivating user: ${userId}`);

  try {
    // Prevent self-deactivation
    if (userId === req.user.id) {
      return res.status(403).json({ error: 'Cannot deactivate your own account' });
    }

    // Get the user being deactivated
    const { data: targetUser, error: fetchError } = await supabase
      .from('users')
      .select('id, email, profile_id, profiles(name)')
      .eq('id', userId)
      .single();

    if (fetchError) {
      if (fetchError.code === 'PGRST116') {
        return res.status(404).json({ error: 'User not found' });
      }
      throw fetchError;
    }

    // If target is a system_admin, check if they're the last one
    if (targetUser.profiles?.name === 'system_admin') {
      // Get the system_admin profile ID
      const { data: adminProfile } = await supabase
        .from('profiles')
        .select('id')
        .eq('name', 'system_admin')
        .single();

      if (adminProfile) {
        // Count active system admins
        const { count, error: countError } = await supabase
          .from('users')
          .select('id', { count: 'exact', head: true })
          .eq('profile_id', adminProfile.id)
          .eq('is_active', true);

        if (countError) throw countError;

        if (count <= 1) {
          return res.status(403).json({
            error: 'Cannot deactivate the last system administrator',
            hint: 'Assign another user as system_admin first'
          });
        }
      }
    }

    const { data: user, error } = await supabase
      .from('users')
      .update({ is_active: false })
      .eq('id', userId)
      .select()
      .single();

    if (error) throw error;

    // Clear RBAC cache for this user
    invalidateRBACCache(userId);

    // Audit log
    await supabase.from('audit_log').insert({
      user_id: req.user.id,
      action: 'user.deactivate',
      action_category: 'user_management',
      resource_type: 'user',
      resource_id: userId,
      target_user_id: userId,
      old_value: { is_active: true },
      new_value: { is_active: false }
    });

    res.json({ success: true, user });
  } catch (err) {
    console.error(`[UI RBAC API] Error deactivating user: ${err.message}`);
    res.status(500).json({ error: 'Failed to deactivate user' });
  }
});

// Reactivate user (admin only)
app.post('/api/rbac/users/:userId/reactivate', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const { userId } = req.params;

  console.log(`[UI RBAC API] Reactivating user: ${userId}`);

  try {
    const { data: user, error } = await supabase
      .from('users')
      .update({ is_active: true })
      .eq('id', userId)
      .select()
      .single();

    if (error) throw error;

    // Clear RBAC cache for this user
    rbacCache.delete(userId);

    res.json({ success: true, user });
  } catch (err) {
    console.error(`[UI RBAC API] Error reactivating user: ${err.message}`);
    res.status(500).json({ error: 'Failed to reactivate user' });
  }
});

// Update record share (owner or admin)
app.put('/api/rbac/record-shares/:id', requireAuth, async (req, res) => {
  const { id } = req.params;
  const { access_level, expires_at } = req.body;

  console.log(`[UI RBAC API] Updating record share: ${id}`);

  try {
    // First check if user can update this share (must be admin or the one who shared it)
    const { data: share, error: fetchError } = await supabase
      .from('record_shares')
      .select('shared_by')
      .eq('id', id)
      .single();

    if (fetchError) throw fetchError;

    // Check permissions
    const isAdmin = req.user.profile === 'system_admin';
    const isOwner = share.shared_by === req.user.id;

    if (!isAdmin && !isOwner) {
      return res.status(403).json({ error: 'Not authorized to update this share' });
    }

    const updates = {};
    if (access_level !== undefined) updates.access_level = access_level;
    if (expires_at !== undefined) updates.expires_at = expires_at;

    if (Object.keys(updates).length === 0) {
      return res.status(400).json({ error: 'No fields to update' });
    }

    const { data: updatedShare, error } = await supabase
      .from('record_shares')
      .update(updates)
      .eq('id', id)
      .select()
      .single();

    if (error) throw error;

    res.json(updatedShare);
  } catch (err) {
    console.error(`[UI RBAC API] Error updating record share: ${err.message}`);
    res.status(500).json({ error: 'Failed to update record share' });
  }
});

// Get audit log (admin only) with filters
app.get('/api/rbac/audit-log', requireAuth, requireProfile('system_admin'), async (req, res) => {
  const {
    page = 1,
    limit = 50,
    action,
    action_category,
    user_id,
    target_user_id,
    resource_type,
    from_date,
    to_date
  } = req.query;
  const offset = (parseInt(page) - 1) * parseInt(limit);

  console.log(`[UI RBAC API] Fetching audit log`);

  try {
    let query = supabase
      .from('audit_log')
      .select('*', { count: 'exact' });

    // Apply filters
    if (action) query = query.eq('action', action);
    if (action_category) query = query.eq('action_category', action_category);
    if (user_id) query = query.eq('user_id', user_id);
    if (target_user_id) query = query.eq('target_user_id', target_user_id);
    if (resource_type) query = query.eq('resource_type', resource_type);
    if (from_date) query = query.gte('timestamp', from_date);
    if (to_date) query = query.lte('timestamp', to_date);

    // Apply pagination and ordering
    query = query
      .order('timestamp', { ascending: false })
      .range(offset, offset + parseInt(limit) - 1);

    const { data: logs, error, count } = await query;

    if (error) throw error;

    res.json({
      logs: logs || [],
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total: count || 0,
        totalPages: Math.ceil((count || 0) / parseInt(limit))
      }
    });
  } catch (err) {
    console.error(`[UI RBAC API] Error fetching audit log: ${err.message}`);
    res.status(500).json({ error: 'Failed to fetch audit log' });
  }
});

// =============================================================================
// LEVEL 4: RECORD-LEVEL SHARING APIs
// =============================================================================

// Share a record with a user or team
app.post('/api/rbac/shares', requireAuth, async (req, res) => {
  const { object_type, record_id, shared_with_user_id, shared_with_team_id, access_level, expires_at, reason } = req.body;

  // Validate required fields
  if (!object_type || !record_id) {
    return res.status(400).json({ error: 'object_type and record_id are required' });
  }

  if (!shared_with_user_id && !shared_with_team_id) {
    return res.status(400).json({ error: 'Either shared_with_user_id or shared_with_team_id is required' });
  }

  if (shared_with_user_id && shared_with_team_id) {
    return res.status(400).json({ error: 'Cannot share with both user and team at the same time' });
  }

  const validAccessLevels = ['read', 'read_write', 'full'];
  if (access_level && !validAccessLevels.includes(access_level)) {
    return res.status(400).json({ error: `access_level must be one of: ${validAccessLevels.join(', ')}` });
  }

  console.log(`[UI RBAC API] Creating share: ${object_type}/${record_id} -> ${shared_with_user_id || `team:${shared_with_team_id}`}`);

  try {
    // Check if share already exists
    let existingQuery = supabase
      .from('record_shares')
      .select('id')
      .eq('object_type', object_type)
      .eq('record_id', record_id);

    if (shared_with_user_id) {
      existingQuery = existingQuery.eq('shared_with_user_id', shared_with_user_id);
    } else {
      existingQuery = existingQuery.eq('shared_with_team_id', shared_with_team_id);
    }

    const { data: existing } = await existingQuery.single();

    if (existing) {
      return res.status(409).json({
        error: 'Share already exists',
        existing_share_id: existing.id,
        hint: 'Use PUT /api/rbac/record-shares/:id to update'
      });
    }

    // Create the share
    const { data: share, error } = await supabase
      .from('record_shares')
      .insert({
        object_type,
        record_id,
        shared_with_user_id: shared_with_user_id || null,
        shared_with_team_id: shared_with_team_id || null,
        access_level: access_level || 'read',
        shared_by: req.user.id,
        expires_at: expires_at || null,
        reason: reason || null
      })
      .select()
      .single();

    if (error) throw error;

    // Audit log
    await supabase.from('audit_log').insert({
      user_id: req.user.id,
      action: 'record.share',
      action_category: 'sharing',
      resource_type: object_type,
      resource_id: record_id,
      target_user_id: shared_with_user_id || null,
      new_value: { access_level: share.access_level, shared_with_team_id, expires_at }
    });

    // Clear RBAC cache for affected user
    if (shared_with_user_id) {
      invalidateRBACCache(shared_with_user_id);
    }

    res.status(201).json(share);
  } catch (err) {
    console.error(`[UI RBAC API] Error creating share: ${err.message}`);
    res.status(500).json({ error: 'Failed to create share' });
  }
});

// Get shares for a specific record
app.get('/api/rbac/shares/:objectType/:recordId', requireAuth, async (req, res) => {
  const { objectType, recordId } = req.params;

  console.log(`[UI RBAC API] Getting shares for ${objectType}/${recordId}`);

  try {
    const { data: shares, error } = await supabase
      .from('record_shares')
      .select(`
        *,
        shared_with_user:users!record_shares_shared_with_user_id_fkey(id, email, name),
        shared_with_team:teams!record_shares_shared_with_team_id_fkey(id, name, display_name),
        sharer:users!record_shares_shared_by_fkey(id, email, name)
      `)
      .eq('object_type', objectType)
      .eq('record_id', recordId);

    if (error) throw error;

    // Filter out expired shares
    const now = new Date();
    const activeShares = (shares || []).filter(s => !s.expires_at || new Date(s.expires_at) > now);

    res.json(activeShares);
  } catch (err) {
    console.error(`[UI RBAC API] Error getting shares: ${err.message}`);
    res.status(500).json({ error: 'Failed to get shares' });
  }
});

// Get all shares for the current user (records shared with me)
app.get('/api/rbac/shares/shared-with-me', requireAuth, async (req, res) => {
  const { object_type, page = 1, limit = 50 } = req.query;
  const offset = (parseInt(page) - 1) * parseInt(limit);

  console.log(`[UI RBAC API] Getting shares for user ${req.user.id}`);

  try {
    // Get user's team IDs
    const { data: teamMemberships } = await supabase
      .from('team_members')
      .select('team_id')
      .eq('user_id', req.user.id);

    const teamIds = (teamMemberships || []).map(tm => tm.team_id);

    // Build query for shares where user is directly shared with OR is member of shared team
    let query = supabase
      .from('record_shares')
      .select(`
        *,
        sharer:users!record_shares_shared_by_fkey(id, email, name)
      `, { count: 'exact' });

    // Filter by object type if provided
    if (object_type) {
      query = query.eq('object_type', object_type);
    }

    // User shares OR team shares
    if (teamIds.length > 0) {
      query = query.or(`shared_with_user_id.eq.${req.user.id},shared_with_team_id.in.(${teamIds.join(',')})`);
    } else {
      query = query.eq('shared_with_user_id', req.user.id);
    }

    // Filter out expired
    query = query.or('expires_at.is.null,expires_at.gt.' + new Date().toISOString());

    // Pagination
    query = query
      .order('shared_at', { ascending: false })
      .range(offset, offset + parseInt(limit) - 1);

    const { data: shares, error, count } = await query;

    if (error) throw error;

    res.json({
      shares: shares || [],
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total: count || 0,
        totalPages: Math.ceil((count || 0) / parseInt(limit))
      }
    });
  } catch (err) {
    console.error(`[UI RBAC API] Error getting user shares: ${err.message}`);
    res.status(500).json({ error: 'Failed to get shares' });
  }
});

// Delete a share (revoke access)
app.delete('/api/rbac/shares/:id', requireAuth, async (req, res) => {
  const { id } = req.params;

  console.log(`[UI RBAC API] Deleting share: ${id}`);

  try {
    // Get share first to check permissions and for audit
    const { data: share, error: fetchError } = await supabase
      .from('record_shares')
      .select('*')
      .eq('id', id)
      .single();

    if (fetchError) {
      if (fetchError.code === 'PGRST116') {
        return res.status(404).json({ error: 'Share not found' });
      }
      throw fetchError;
    }

    // Check permissions (must be admin or the one who shared it)
    const isAdmin = req.user.profile === 'system_admin';
    const isOwner = share.shared_by === req.user.id;

    if (!isAdmin && !isOwner) {
      return res.status(403).json({ error: 'Not authorized to delete this share' });
    }

    // Delete the share
    const { error } = await supabase
      .from('record_shares')
      .delete()
      .eq('id', id);

    if (error) throw error;

    // Audit log
    await supabase.from('audit_log').insert({
      user_id: req.user.id,
      action: 'record.unshare',
      action_category: 'sharing',
      resource_type: share.object_type,
      resource_id: share.record_id,
      target_user_id: share.shared_with_user_id,
      old_value: { access_level: share.access_level, shared_with_team_id: share.shared_with_team_id }
    });

    // Clear RBAC cache for affected user
    if (share.shared_with_user_id) {
      invalidateRBACCache(share.shared_with_user_id);
    }

    res.json({ success: true });
  } catch (err) {
    console.error(`[UI RBAC API] Error deleting share: ${err.message}`);
    res.status(500).json({ error: 'Failed to delete share' });
  }
});

// Check if user has access to a specific record
app.get('/api/rbac/check-access/:objectType/:recordId', requireAuth, async (req, res) => {
  const { objectType, recordId } = req.params;
  const { required_level } = req.query;

  console.log(`[UI RBAC API] Checking access: ${objectType}/${recordId} for user ${req.user.id}`);

  try {
    // System admin has full access
    if (req.user.profile === 'system_admin') {
      return res.json({ has_access: true, access_level: 'full', reason: 'system_admin' });
    }

    // Get user's team IDs
    const { data: teamMemberships } = await supabase
      .from('team_members')
      .select('team_id')
      .eq('user_id', req.user.id);

    const teamIds = (teamMemberships || []).map(tm => tm.team_id);

    // Check for direct user share
    const { data: userShare } = await supabase
      .from('record_shares')
      .select('access_level, expires_at')
      .eq('object_type', objectType)
      .eq('record_id', recordId)
      .eq('shared_with_user_id', req.user.id)
      .or('expires_at.is.null,expires_at.gt.' + new Date().toISOString())
      .single();

    if (userShare) {
      const accessLevelRank = { read: 1, read_write: 2, full: 3 };
      const requiredRank = accessLevelRank[required_level] || 1;
      const hasRank = accessLevelRank[userShare.access_level] || 0;

      return res.json({
        has_access: hasRank >= requiredRank,
        access_level: userShare.access_level,
        reason: 'user_share'
      });
    }

    // Check for team share
    if (teamIds.length > 0) {
      const { data: teamShare } = await supabase
        .from('record_shares')
        .select('access_level, expires_at, shared_with_team_id')
        .eq('object_type', objectType)
        .eq('record_id', recordId)
        .in('shared_with_team_id', teamIds)
        .or('expires_at.is.null,expires_at.gt.' + new Date().toISOString())
        .order('access_level', { ascending: false }) // Get highest access level
        .limit(1)
        .single();

      if (teamShare) {
        const accessLevelRank = { read: 1, read_write: 2, full: 3 };
        const requiredRank = accessLevelRank[required_level] || 1;
        const hasRank = accessLevelRank[teamShare.access_level] || 0;

        return res.json({
          has_access: hasRank >= requiredRank,
          access_level: teamShare.access_level,
          reason: 'team_share',
          team_id: teamShare.shared_with_team_id
        });
      }
    }

    // No share found
    return res.json({ has_access: false, access_level: null, reason: 'no_share' });
  } catch (err) {
    console.error(`[UI RBAC API] Error checking access: ${err.message}`);
    res.status(500).json({ error: 'Failed to check access' });
  }
});

// =============================================================================
// SPA CATCH-ALL - Serve index.html for all non-API routes
// This enables client-side routing and handles Supabase auth redirects
// =============================================================================
app.get('*', (req, res) => {
  // Don't catch API routes
  if (req.path.startsWith('/api/')) {
    return res.status(404).json({ error: 'Not found' });
  }
  // Serve index.html for all other routes (SPA)
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Error handling middleware
app.use((err, req, res, next) => {
  console.error('Server error:', err);
  // In production, hide internal error details from client
  if (IS_PRODUCTION) {
    res.status(500).json({ error: 'An internal error occurred' });
  } else {
    res.status(500).json({ error: err.message || 'Internal server error' });
  }
});

// Start server
app.listen(PORT, () => {
  console.log(`Unified UI running on http://localhost:${PORT}`);
  console.log(`Supabase: ${supabase ? 'Connected' : 'Not configured'}`);
  console.log(`Sales Bot: ${SERVICES.sales}`);
});

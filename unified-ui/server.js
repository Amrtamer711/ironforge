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

// Helper: Fetch user's RBAC data from UI Supabase
// Returns null if user not found (should be rejected)
async function getUserRBACData(userId) {
  if (!supabase) {
    // Dev mode fallback
    return { profile: 'sales_user', permissions: ['sales:*:*'] };
  }

  try {
    // Get user with profile
    const { data: userData, error } = await supabase
      .from('users')
      .select('id, email, name, profile_id, is_active, profiles(id, name, display_name)')
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

    // Get permissions from permission sets
    const { data: userPermSets } = await supabase
      .from('user_permission_sets')
      .select('permission_sets(id)')
      .eq('user_id', userId);

    if (userPermSets) {
      for (const ups of userPermSets) {
        if (ups.permission_sets?.id) {
          const { data: psPerms } = await supabase
            .from('permission_set_permissions')
            .select('permission')
            .eq('permission_set_id', ups.permission_sets.id);

          if (psPerms) {
            permissions.push(...psPerms.map(p => p.permission));
          }
        }
      }
    }

    // Dedupe and return
    return {
      profile: profileName,
      permissions: [...new Set(permissions)]
    };

  } catch (err) {
    console.error(`[RBAC] Error fetching RBAC for ${userId}:`, err.message);
    return null; // Error fetching - reject access for safety
  }
}

// RBAC cache (1 minute TTL)
const rbacCache = new Map();
const RBAC_CACHE_TTL = 60000;

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
    req.trustedUser = {
      id: user.id,
      email: user.email,
      name: user.user_metadata?.name || user.user_metadata?.full_name || '',
      profile: rbac.profile,
      permissions: rbac.permissions
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
      if (req.trustedUser) {
        // Send proxy secret to prove request is from unified-ui
        if (PROXY_SECRET) {
          proxyReq.setHeader('X-Proxy-Secret', PROXY_SECRET);
        }
        proxyReq.setHeader('X-Trusted-User-Id', req.trustedUser.id);
        proxyReq.setHeader('X-Trusted-User-Email', req.trustedUser.email);
        proxyReq.setHeader('X-Trusted-User-Name', req.trustedUser.name);
        proxyReq.setHeader('X-Trusted-User-Profile', req.trustedUser.profile);
        proxyReq.setHeader('X-Trusted-User-Permissions', JSON.stringify(req.trustedUser.permissions));
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

    res.status(201).json({
      token,
      email: email.toLowerCase(),
      profile_name,
      expires_at: expiresAt.toISOString(),
      email_sent: emailSent,
      email_error: emailError,
      email_provider: EMAIL_PROVIDER,
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

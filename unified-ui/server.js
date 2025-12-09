const express = require('express');
const path = require('path');
const cors = require('cors');
const bodyParser = require('body-parser');
const crypto = require('crypto');
const { createProxyMiddleware } = require('http-proxy-middleware');
const { createClient } = require('@supabase/supabase-js');

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

// Middleware
app.use(cors());
app.use(bodyParser.json({ limit: '50mb' }));
app.use(bodyParser.urlencoded({ extended: true, limit: '50mb' }));

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
// SERVICE PROXY - Forward /api/sales/* to Sales Bot (proposal-bot)
// Sales module only: chat, mockup, templates, proposals, bo, etc.
// NO auth validation here - just forward headers, let backend handle auth
// =============================================================================
app.use('/api/sales', createProxyMiddleware({
  target: SERVICES.sales,
  changeOrigin: true,
  pathRewrite: {
    '^/api/sales': '/api', // /api/sales/chat -> /api/chat
  },
  // Increase timeout for LLM operations (5 minutes)
  proxyTimeout: 300000,
  timeout: 300000,
  on: {
    proxyReq: (proxyReq, req, res) => {
      // LOG ALL PROXY REQUESTS
      console.log(`[PROXY] ========================================`);
      console.log(`[PROXY] ${req.method} ${req.originalUrl} -> ${SERVICES.sales}${req.path.replace('/api/sales', '/api')}`);
      console.log(`[PROXY] Has Auth Header: ${!!req.headers.authorization}`);
      console.log(`[PROXY] Target: ${SERVICES.sales}`);
      console.log(`[PROXY] ========================================`);

      // Forward Authorization header to backend (backend validates)
      const authHeader = req.headers.authorization;
      if (authHeader) {
        proxyReq.setHeader('Authorization', authHeader);
      }

      // Forward IP for logging/rate limiting
      if (req.headers['x-forwarded-for']) {
        proxyReq.setHeader('X-Forwarded-For', req.headers['x-forwarded-for']);
      } else if (req.socket.remoteAddress) {
        proxyReq.setHeader('X-Forwarded-For', req.socket.remoteAddress);
      }
    },
    proxyRes: (proxyRes, req, res) => {
      console.log(`[PROXY] Response: ${proxyRes.statusCode} for ${req.method} ${req.originalUrl}`);

      // For SSE endpoints, ensure no buffering
      if (req.path.includes('/stream') || proxyRes.headers['content-type']?.includes('text/event-stream')) {
        console.log(`[PROXY] SSE response detected, disabling buffering`);
        res.setHeader('X-Accel-Buffering', 'no');
        res.setHeader('Cache-Control', 'no-cache');
        res.setHeader('Connection', 'keep-alive');
      }
    },
    error: (err, req, res) => {
      console.error(`[PROXY] ERROR: ${err.message}`);
      console.error(`[PROXY] Request was: ${req.method} ${req.originalUrl}`);
      console.error(`[PROXY] Target was: ${SERVICES.sales}`);
      if (!res.headersSent) {
        res.status(502).json({ error: 'Service unavailable', details: err.message, target: SERVICES.sales });
      }
    },
  },
}));

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

// Create invite token (requires system_admin)
app.post('/api/base/auth/invites', rateLimiter(20), requireAuth, requireProfile('system_admin'), async (req, res) => {
  console.log('[UI] Create invite request');

  const { email, profile_name = 'sales_user', expires_in_days = 7 } = req.body;

  if (!email || email.length < 5) {
    return res.status(400).json({ error: 'Valid email is required' });
  }

  if (expires_in_days < 1 || expires_in_days > 30) {
    return res.status(400).json({ error: 'Expiry must be between 1 and 30 days' });
  }

  // Validate profile exists
  const validProfiles = ['system_admin', 'sales_manager', 'sales_user', 'coordinator', 'finance', 'viewer'];
  if (!validProfiles.includes(profile_name)) {
    return res.status(400).json({ error: `Invalid profile: ${profile_name}` });
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

    res.status(201).json({
      token,
      email: email.toLowerCase(),
      profile_name,
      expires_at: expiresAt.toISOString(),
      message: `Invite token created. Share this token with ${email} to allow them to sign up.`,
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

// Validate invite token (PUBLIC - for signup flow)
// Rate limited heavily to prevent brute force
app.post('/api/base/auth/validate-invite', rateLimiter(5), async (req, res) => {
  const { token, email } = req.body;

  if (!token || !email) {
    // Generic error for security
    return res.status(400).json({ error: 'Invalid or expired invite token' });
  }

  console.log(`[UI] Validating invite token for email: ${email}`);

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
      .update({ used_at: now.toISOString() })
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
      .select('id, email, name, profile_id, profiles(name, display_name)')
      .eq('id', req.user.id)
      .single();

    if (error || !userData) {
      console.warn(`[UI] User ${req.user.email} not found in users table`);
      // Return basic info from auth, no profile
      return res.json({
        id: req.user.id,
        email: req.user.email,
        name: req.user.user_metadata?.name || req.user.email?.split('@')[0],
        profile_name: null,
        profile_display_name: null
      });
    }

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
  res.status(500).json({
    error: err.message || 'Internal server error'
  });
});

// Start server
app.listen(PORT, () => {
  console.log(`Unified UI running on http://localhost:${PORT}`);
  console.log(`Supabase: ${supabase ? 'Connected' : 'Not configured'}`);
  console.log(`Sales Bot: ${SERVICES.sales}`);
});

const express = require('express');
const path = require('path');
const cors = require('cors');
const bodyParser = require('body-parser');
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
// UI SUPABASE CONFIGURATION (Auth only - completely separate from Sales Bot)
// UI has its own Supabase project for authentication
// =============================================================================

// Get credentials based on environment (UI's own Supabase project)
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

// Service role client for server-side auth validation
const supabase = supabaseUrl && supabaseServiceKey
  ? createClient(supabaseUrl, supabaseServiceKey)
  : null;

// =============================================================================
// SERVICE REGISTRY
// All business data routes go to Sales Bot
// =============================================================================
const SERVICES = {
  sales: process.env.SALES_BOT_URL || 'http://localhost:8000',
};

// Middleware
app.use(cors());
app.use(bodyParser.json({ limit: '50mb' }));
app.use(bodyParser.urlencoded({ extended: true, limit: '50mb' }));

// =============================================================================
// SUPABASE AUTH MIDDLEWARE
// Verifies JWT tokens from Supabase Auth
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
    console.error('Auth error:', err);
    return res.status(401).json({ error: 'Authentication failed', requiresAuth: true });
  }
}

app.use(express.static('public'));

// =============================================================================
// SERVICE PROXY - Forward ALL /api/sales/* to Sales Bot
// This includes: chat, mockup, templates, proposals, bo, etc.
// IMPORTANT: Forwards Authorization header for backend auth validation
// =============================================================================
app.use('/api/sales', createProxyMiddleware({
  target: SERVICES.sales,
  changeOrigin: true,
  pathRewrite: {
    '^/api/sales': '/api', // /api/sales/chat -> /api/chat
  },
  on: {
    proxyReq: async (proxyReq, req, res) => {
      // Forward Authorization header to backend
      const authHeader = req.headers.authorization;
      if (authHeader) {
        proxyReq.setHeader('Authorization', authHeader);

        // Add X-Request-User-ID for tracing (extract from token if possible)
        if (supabase && authHeader.startsWith('Bearer ')) {
          try {
            const token = authHeader.substring(7);
            const { data: { user } } = await supabase.auth.getUser(token);
            if (user) {
              proxyReq.setHeader('X-Request-User-ID', user.id);
              proxyReq.setHeader('X-Request-User-Email', user.email || '');
            }
          } catch (err) {
            // Token validation failed, still forward to let backend handle
            console.warn('Could not extract user from token:', err.message);
          }
        }
      }

      // Forward other useful headers
      if (req.headers['x-forwarded-for']) {
        proxyReq.setHeader('X-Forwarded-For', req.headers['x-forwarded-for']);
      } else if (req.socket.remoteAddress) {
        proxyReq.setHeader('X-Forwarded-For', req.socket.remoteAddress);
      }
    },
    error: (err, req, res) => {
      console.error(`Proxy error to ${SERVICES.sales}:`, err.message);
      res.status(502).json({ error: 'Service unavailable', service: SERVICES.sales });
    },
  },
}));

// =============================================================================
// LOCAL ROUTES - /api/base/* handled by this server (Auth only)
// =============================================================================

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'unified-ui', supabase: !!supabase });
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

// Verify session endpoint (for checking if user is authenticated)
app.get('/api/base/auth/session', async (req, res) => {
  if (!supabase) {
    return res.status(500).json({ error: 'Supabase not configured' });
  }

  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.json({ authenticated: false });
  }

  const token = authHeader.substring(7);

  try {
    const { data: { user }, error } = await supabase.auth.getUser(token);

    if (error || !user) {
      return res.json({ authenticated: false });
    }

    res.json({
      authenticated: true,
      user: {
        id: user.id,
        email: user.email,
        role: user.role
      }
    });
  } catch (err) {
    res.json({ authenticated: false });
  }
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

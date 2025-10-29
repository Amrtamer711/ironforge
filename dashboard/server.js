const express = require('express');
const axios = require('axios');
const cors = require('cors');
const path = require('path');
const session = require('express-session');
const FileStore = require('session-file-store')(session);
const bcrypt = require('bcrypt');
const cookieParser = require('cookie-parser');

const app = express();
const PORT = process.env.PORT || 3000;

// Configuration from environment
const API_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const SESSION_SECRET = process.env.SESSION_SECRET || 'dev-secret-change-in-production';
const DASHBOARD_PASSWORD = process.env.DASHBOARD_PASSWORD || 'nour';

console.log('🔐 Password-only authentication enabled');

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(cookieParser());

// Session configuration with file store (production-ready)
app.use(session({
  store: new FileStore({
    path: './sessions',
    ttl: 7 * 24 * 60 * 60, // 7 days in seconds
    retries: 0
  }),
  secret: SESSION_SECRET,
  resave: false,
  saveUninitialized: false,
  cookie: {
    secure: process.env.NODE_ENV === 'production',
    httpOnly: true,
    maxAge: 7 * 24 * 60 * 60 * 1000 // 7 days
  }
}));

// Authentication middleware
function requireAuth(req, res, next) {
  if (req.session && req.session.authenticated) {
    return next();
  }
  res.status(401).json({ error: 'Authentication required' });
}

// Authentication endpoints
app.post('/api/login', (req, res) => {
  const { password } = req.body;

  if (!password) {
    return res.status(400).json({ error: 'Password required' });
  }

  // Simple password comparison (upgrade to bcrypt if needed later)
  if (password === DASHBOARD_PASSWORD) {
    req.session.authenticated = true;
    console.log(`✅ Dashboard login successful`);
    res.json({ success: true, message: 'Login successful' });
  } else {
    res.status(401).json({ error: 'Invalid password' });
  }
});

app.post('/api/logout', (req, res) => {
  req.session.destroy((err) => {
    if (err) {
      console.error('[AUTH] Logout error:', err);
      return res.status(500).json({ error: 'Logout failed' });
    }
    res.clearCookie('connect.sid');
    console.log(`👋 Dashboard logged out`);
    res.json({ success: true, message: 'Logout successful' });
  });
});

app.get('/api/auth/check', (req, res) => {
  res.json({
    authenticated: !!(req.session && req.session.authenticated)
  });
});

// Protected endpoints - require authentication
app.get('/api/costs', requireAuth, async (req, res) => {
  try {
    const { start_date, end_date, user_id, call_type, workflow } = req.query;

    const params = new URLSearchParams();
    if (start_date) params.append('start_date', start_date);
    if (end_date) params.append('end_date', end_date);
    if (user_id) params.append('user_id', user_id);
    if (call_type) params.append('call_type', call_type);
    if (workflow) params.append('workflow', workflow);

    const url = `${API_URL}/costs?${params.toString()}`;
    console.log(`[PROXY] Fetching costs from: ${url}`);

    const response = await axios.get(url);
    res.json(response.data);
  } catch (error) {
    console.error('[PROXY] Error fetching costs:', error.message);
    res.status(500).json({
      error: 'Failed to fetch costs data',
      details: error.message
    });
  }
});

// Health check endpoint (no auth required)
app.get('/health', (_req, res) => {
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    backend_url: API_URL
  });
});

// Serve static files from public directory (login page, etc.)
app.use(express.static(path.join(__dirname, 'public')));

// Serve the dashboard on root (will redirect to login if not authenticated)
app.get('/', (_req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'login.html'));
});

app.listen(PORT, () => {
  console.log(`🚀 AI Costs Dashboard running on port ${PORT}`);
  console.log(`📊 Dashboard: http://localhost:${PORT}`);
  console.log(`🔗 API Proxy: http://localhost:${PORT}/api/costs`);
  console.log(`🔌 Backend API: ${API_URL}`);
});

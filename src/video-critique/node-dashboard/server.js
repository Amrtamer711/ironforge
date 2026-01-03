const express = require('express');
const cors = require('cors');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '..', '.env') });

const dashboardRouter = require('./routes/dashboard');
const rolesRouter = require('./routes/roles');

const app = express();
const PORT = process.env.NODE_DASHBOARD_PORT || 3001;

// Password configuration
const PASSWORDS = {
  'juliana': { role: 'head_of_marketing', name: 'Juliana' },
  'deaa': { role: 'head_of_design', name: 'Deaa' }
};

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.static('public'));

// Authentication endpoint
app.post('/api/auth/login', (req, res) => {
  const { password } = req.body;

  if (!password) {
    return res.status(400).json({ error: 'Password is required' });
  }

  const userData = PASSWORDS[password.toLowerCase()];

  if (userData) {
    return res.json({
      success: true,
      role: userData.role,
      name: userData.name
    });
  } else {
    return res.status(401).json({
      success: false,
      error: 'Invalid password'
    });
  }
});

// API Routes
app.use('/api', dashboardRouter);
app.use('/api/roles', rolesRouter);

// Serve the dashboard UI
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'OK', timestamp: new Date().toISOString() });
});

// Error handling middleware
app.use((err, req, res, next) => {
  console.error('Error:', err);
  res.status(500).json({
    error: 'Internal server error',
    message: err.message
  });
});

// Start server
app.listen(PORT, () => {
  console.log(`🚀 Video Critique Dashboard running on http://localhost:${PORT}`);
  console.log(`📊 Dashboard UI: http://localhost:${PORT}`);
  console.log(`🔌 API endpoint: http://localhost:${PORT}/api/dashboard`);
});

module.exports = app;

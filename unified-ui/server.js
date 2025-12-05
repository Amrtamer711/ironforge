const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs').promises;
const cors = require('cors');
const bodyParser = require('body-parser');
const { createProxyMiddleware } = require('http-proxy-middleware');

const app = express();
const PORT = process.env.PORT || 3005;

// =============================================================================
// SERVICE REGISTRY
// Routes: /api/base/* → local, /api/sales/* → Sales Bot, etc.
// =============================================================================
const SERVICES = {
  sales: process.env.SALES_BOT_URL || 'http://localhost:8000',
  // inventory: process.env.INVENTORY_URL || 'http://localhost:8001',
  // analytics: process.env.ANALYTICS_URL || 'http://localhost:8002',
};

// Setup password (change this in production)
const SETUP_PASSWORD = process.env.SETUP_PASSWORD || 'admin123';

// Middleware
app.use(cors());
app.use(bodyParser.json({ limit: '50mb' }));
app.use(bodyParser.urlencoded({ extended: true, limit: '50mb' }));

// Session tracking for authenticated users
const authenticatedSessions = new Set();

// Authentication middleware
function requireAuth(req, res, next) {
  const sessionId = req.headers['x-session-id'];

  if (!sessionId || !authenticatedSessions.has(sessionId)) {
    return res.status(401).json({ error: 'Unauthorized', requiresAuth: true });
  }

  next();
}

app.use(express.static('public'));

// =============================================================================
// SERVICE PROXY - Forward /api/{service}/* to the appropriate backend
// =============================================================================

// Proxy /api/sales/* to Sales Bot
app.use('/api/sales', createProxyMiddleware({
  target: SERVICES.sales,
  changeOrigin: true,
  pathRewrite: {
    '^/api/sales': '/api', // /api/sales/chat -> /api/chat
  },
  on: {
    error: (err, req, res) => {
      console.error(`Proxy error to ${SERVICES.sales}:`, err.message);
      res.status(502).json({ error: 'Service unavailable', service: SERVICES.sales });
    },
  },
}));

// Configure multer for file uploads
const storage = multer.diskStorage({
  destination: async (req, file, cb) => {
    const uploadDir = path.join(__dirname, 'uploads');
    try {
      await fs.mkdir(uploadDir, { recursive: true });
      cb(null, uploadDir);
    } catch (err) {
      cb(err);
    }
  },
  filename: (req, file, cb) => {
    const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
    cb(null, file.fieldname + '-' + uniqueSuffix + path.extname(file.originalname));
  }
});

const upload = multer({
  storage: storage,
  limits: { fileSize: 50 * 1024 * 1024 }, // 50MB limit
  fileFilter: (req, file, cb) => {
    const allowedTypes = /jpeg|jpg|png|gif|webp/;
    const extname = allowedTypes.test(path.extname(file.originalname).toLowerCase());
    const mimetype = allowedTypes.test(file.mimetype);

    if (mimetype && extname) {
      return cb(null, true);
    } else {
      cb(new Error('Only image files are allowed!'));
    }
  }
});

// Data storage paths
const DATA_DIR = path.join(__dirname, 'data');
const TEMPLATES_FILE = path.join(DATA_DIR, 'templates.json');
const LOCATIONS_FILE = path.join(__dirname, '../db.py'); // Reference to existing db

// Initialize data directory and templates file
async function initializeData() {
  try {
    await fs.mkdir(DATA_DIR, { recursive: true });

    try {
      await fs.access(TEMPLATES_FILE);
    } catch {
      await fs.writeFile(TEMPLATES_FILE, JSON.stringify([], null, 2));
    }
  } catch (err) {
    console.error('Error initializing data:', err);
  }
}

// Read templates from file
async function readTemplates() {
  try {
    const data = await fs.readFile(TEMPLATES_FILE, 'utf8');
    return JSON.parse(data);
  } catch (err) {
    console.error('Error reading templates:', err);
    return [];
  }
}

// Write templates to file
async function writeTemplates(templates) {
  try {
    await fs.writeFile(TEMPLATES_FILE, JSON.stringify(templates, null, 2));
  } catch (err) {
    console.error('Error writing templates:', err);
    throw err;
  }
}

// =============================================================================
// LOCAL ROUTES - /api/base/* handled by this server
// =============================================================================

// Login endpoint
app.post('/api/base/login', (req, res) => {
  const { password } = req.body;

  if (password === SETUP_PASSWORD) {
    const sessionId = Math.random().toString(36).substring(2) + Date.now().toString(36);
    authenticatedSessions.add(sessionId);

    res.json({
      success: true,
      sessionId: sessionId
    });
  } else {
    res.status(401).json({
      success: false,
      error: 'Invalid password'
    });
  }
});

// Logout endpoint
app.post('/api/base/logout', (req, res) => {
  const sessionId = req.headers['x-session-id'];
  if (sessionId) {
    authenticatedSessions.delete(sessionId);
  }
  res.json({ success: true });
});

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'unified-ui' });
});

// Serve main page
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Get all templates (public for viewing)
app.get('/api/base/templates', async (req, res) => {
  try {
    const templates = await readTemplates();
    res.json(templates);
  } catch (err) {
    res.status(500).json({ error: 'Failed to load templates' });
  }
});

// Get single template by location key
app.get('/api/base/templates/:locationKey', async (req, res) => {
  try {
    const templates = await readTemplates();
    const template = templates.find(t => t.locationKey === req.params.locationKey);

    if (!template) {
      return res.status(404).json({ error: 'Template not found' });
    }

    res.json(template);
  } catch (err) {
    res.status(500).json({ error: 'Failed to load template' });
  }
});

// Upload billboard image (protected)
app.post('/api/base/upload', requireAuth, upload.single('image'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: 'No file uploaded' });
    }

    const imageUrl = `/uploads/${req.file.filename}`;
    res.json({
      success: true,
      imageUrl: imageUrl,
      filename: req.file.filename
    });
  } catch (err) {
    console.error('Upload error:', err);
    res.status(500).json({ error: 'Failed to upload image' });
  }
});

// Save template (protected)
app.post('/api/base/templates', requireAuth, async (req, res) => {
  try {
    const { locationKey, frames, imageUrl, metadata } = req.body;

    if (!locationKey || !frames || !imageUrl) {
      return res.status(400).json({ error: 'Missing required fields' });
    }

    const templates = await readTemplates();

    // Check if template exists
    const existingIndex = templates.findIndex(t => t.locationKey === locationKey);

    const template = {
      locationKey,
      frames,
      imageUrl,
      metadata: metadata || {},
      updatedAt: new Date().toISOString()
    };

    if (existingIndex >= 0) {
      templates[existingIndex] = template;
    } else {
      template.createdAt = new Date().toISOString();
      templates.push(template);
    }

    await writeTemplates(templates);

    res.json({
      success: true,
      template: template
    });
  } catch (err) {
    console.error('Save error:', err);
    res.status(500).json({ error: 'Failed to save template' });
  }
});

// Delete template (protected)
app.delete('/api/base/templates/:locationKey', requireAuth, async (req, res) => {
  try {
    const templates = await readTemplates();
    const filteredTemplates = templates.filter(t => t.locationKey !== req.params.locationKey);

    if (templates.length === filteredTemplates.length) {
      return res.status(404).json({ error: 'Template not found' });
    }

    await writeTemplates(filteredTemplates);

    res.json({ success: true });
  } catch (err) {
    console.error('Delete error:', err);
    res.status(500).json({ error: 'Failed to delete template' });
  }
});

// Serve uploaded files
app.use('/uploads', express.static(path.join(__dirname, 'uploads')));

// Error handling middleware
app.use((err, req, res, next) => {
  console.error('Server error:', err);
  res.status(500).json({
    error: err.message || 'Internal server error'
  });
});

// Initialize and start server
initializeData().then(() => {
  app.listen(PORT, () => {
    console.log(`🎨 Mockup Studio running on http://localhost:${PORT}`);
    console.log(`📁 Data directory: ${DATA_DIR}`);
  });
});

const express = require('express');
const router = express.Router();

// Get Python API URL from environment
const IS_PRODUCTION = process.env.RENDER === 'true' ||
                     process.env.PORT !== undefined ||
                     process.env.PRODUCTION === 'true';

const PYTHON_API_URL = process.env.PYTHON_API_URL ||
  (IS_PRODUCTION
    ? 'https://videocritique-bot-ob8k.onrender.com'
    : 'http://localhost:8000');

console.log(`🔗 Dashboard will proxy to Python API: ${PYTHON_API_URL}`);

/**
 * GET /api/dashboard
 * Proxy to Python API dashboard endpoint
 * Query params: mode (month|year|range), period (YYYY-MM or YYYY or YYYY-MM-DD,YYYY-MM-DD)
 */
router.get('/dashboard', async (req, res, next) => {
  try {
    const mode = req.query.mode || 'month';
    const period = req.query.period || '';

    // Validate mode
    if (!['month', 'year', 'range'].includes(mode)) {
      return res.status(400).json({
        error: 'Invalid mode',
        message: 'Mode must be either "month", "year", or "range"'
      });
    }

    // Call Python API
    const url = `${PYTHON_API_URL}/api/dashboard?mode=${mode}&period=${encodeURIComponent(period)}`;
    console.log(`📡 Proxying to: ${url}`);

    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`Python API error: ${response.status} ${response.statusText}`);
    }

    const data = await response.json();
    res.json(data);
  } catch (error) {
    console.error('Dashboard API error:', error);
    next(error);
  }
});

/**
 * GET /api/stats
 * Quick stats summary (for homepage widgets)
 */
router.get('/stats', async (req, res, next) => {
  try {
    const url = `${PYTHON_API_URL}/api/dashboard?mode=month`;
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`Python API error: ${response.status}`);
    }

    const data = await response.json();

    // Return simplified stats
    res.json({
      total_tasks: data.summary.total,
      completed: data.pie.completed,
      pending: data.summary.pending,
      accepted_pct: data.summary.accepted_pct,
      avg_response_time: data.reviewer.avg_response_display
    });
  } catch (error) {
    console.error('Stats API error:', error);
    next(error);
  }
});

module.exports = router;

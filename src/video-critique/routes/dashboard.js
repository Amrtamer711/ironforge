const express = require('express');
const router = express.Router();
const dashboardService = require('../services/dashboardService');

/**
 * GET /api/dashboard
 * Main dashboard data endpoint
 * Query params: mode (month|year), period (YYYY-MM or YYYY)
 */
router.get('/dashboard', async (req, res, next) => {
  try {
    const mode = req.query.mode || 'month';
    const period = req.query.period || '';

    // Validate mode
    if (!['month', 'year'].includes(mode)) {
      return res.status(400).json({
        error: 'Invalid mode',
        message: 'Mode must be either "month" or "year"'
      });
    }

    const data = await dashboardService.getDashboardData(mode, period);
    res.json(data);
  } catch (error) {
    next(error);
  }
});

/**
 * GET /api/stats
 * Quick stats summary (for homepage widgets)
 */
router.get('/stats', async (req, res, next) => {
  try {
    const data = await dashboardService.getDashboardData('month', '');

    // Return simplified stats
    res.json({
      total_tasks: data.summary.total,
      completed: data.pie.completed,
      pending: data.summary.pending,
      accepted_pct: data.summary.accepted_pct,
      avg_response_time: data.reviewer.avg_response_display
    });
  } catch (error) {
    next(error);
  }
});

module.exports = router;

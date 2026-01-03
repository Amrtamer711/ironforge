const db = require('../db/database');

/**
 * Parse date from various formats
 */
function parseDate(dateStr) {
  if (!dateStr || dateStr.trim() === '') return null;

  const str = dateStr.trim();

  // Try DD-MM-YYYY format
  let match = str.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
  if (match) {
    const [, day, month, year] = match;
    const date = new Date(year, month - 1, day);
    if (!isNaN(date.getTime())) return date;
  }

  // Try YYYY-MM-DD format
  match = str.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (match) {
    const [, year, month, day] = match;
    const date = new Date(year, month - 1, day);
    if (!isNaN(date.getTime())) return date;
  }

  // Try DD/MM/YYYY format
  match = str.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (match) {
    const [, day, month, year] = match;
    const date = new Date(year, month - 1, day);
    if (!isNaN(date.getTime())) return date;
  }

  // Try MM/DD/YYYY format
  match = str.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (match) {
    const [, month, day, year] = match;
    const date = new Date(year, month - 1, day);
    if (!isNaN(date.getTime())) return date;
  }

  // Fallback to native parsing
  try {
    const date = new Date(dateStr);
    if (!isNaN(date.getTime())) return date;
  } catch (e) {
    return null;
  }

  return null;
}

/**
 * Check if date is in the specified period
 */
function isDateInPeriod(date, mode, period) {
  if (!date) return false;

  try {
    if (mode === 'year') {
      return date.getFullYear() === parseInt(period);
    } else {
      // month mode: period format is "YYYY-MM"
      const [year, month] = period.split('-').map(Number);
      return date.getFullYear() === year && (date.getMonth() + 1) === month;
    }
  } catch (e) {
    return false;
  }
}

/**
 * Safely parse JSON
 */
function safeParseJSON(jsonStr, defaultValue = []) {
  if (!jsonStr || jsonStr.trim() === '' || jsonStr === 'nan' || jsonStr === 'None') {
    return defaultValue;
  }

  try {
    const result = JSON.parse(jsonStr);
    return Array.isArray(result) ? result : defaultValue;
  } catch (e) {
    return defaultValue;
  }
}

/**
 * Calculate percentage safely
 */
function calculatePercentage(numerator, denominator) {
  if (denominator <= 0) return 0.0;
  return Math.round((100.0 * numerator / denominator) * 10) / 10;
}

/**
 * Format duration in hours to human readable string
 */
function formatDuration(hours) {
  if (hours <= 0) return "0 hrs";

  if (hours < 1) {
    return `${Math.round(hours * 60)} mins`;
  } else if (hours < 24) {
    return `${Math.round(hours * 10) / 10} hrs`;
  } else {
    const days = Math.floor(hours / 24);
    const remainingHours = Math.round((hours % 24) * 10) / 10;
    if (remainingHours > 0) {
      return `${days}d ${remainingHours}h`;
    }
    return `${days}d`;
  }
}

/**
 * Get empty dashboard response
 */
function getEmptyDashboardResponse(mode, period) {
  return {
    mode,
    period,
    pie: { completed: 0, not_completed: 0 },
    summary: {
      total: 0,
      assigned: 0,
      pending: 0,
      rejected: 0,
      submitted_to_sales: 0,
      returned: 0,
      uploads: 0,
      accepted_videos: 0,
      accepted_pct: 0.0,
      rejected_pct: 0.0
    },
    reviewer: {
      avg_response_hours: 0,
      avg_response_display: "0 hrs",
      pending_videos: 0,
      handled: 0,
      accepted: 0,
      handled_percent: 0.0
    },
    videographers: {},
    summary_videographers: {}
  };
}

/**
 * Calculate reviewer statistics
 */
function calculateReviewerStats(tasksInPeriod) {
  const responseTimes = [];
  let reviewerHandled = 0;
  let totalAccepted = 0;
  let totalReturned = 0;

  for (const task of tasksInPeriod) {
    const versionHistory = safeParseJSON(task['Version History']);

    const versionStates = {};
    const versionPendingTimes = {};

    for (const event of versionHistory) {
      if (typeof event !== 'object' || !event) continue;

      const folder = String(event.folder || '').toLowerCase();
      const version = event.version;
      const timestampStr = event.at || '';

      if (version === null || version === undefined) continue;

      // Parse timestamp
      let timestamp = null;
      try {
        timestamp = parse(timestampStr, 'dd-MM-yyyy HH:mm:ss', new Date());
      } catch (e) {
        // Invalid timestamp
      }

      // Track pending time
      if (folder === 'pending' && !versionPendingTimes[version] && timestamp) {
        versionPendingTimes[version] = timestamp;
      }

      // Update version state
      if (folder === 'pending') {
        versionStates[version] = 'pending';
      } else if (folder === 'rejected') {
        versionStates[version] = 'rejected';
        // Calculate response time
        if (versionPendingTimes[version] && timestamp) {
          const deltaHours = (timestamp - versionPendingTimes[version]) / (1000 * 60 * 60);
          if (deltaHours > 0) {
            responseTimes.push(deltaHours);
            reviewerHandled++;
          }
        }
      } else if (folder === 'returned') {
        versionStates[version] = 'returned';
      } else if (folder === 'submitted to sales' || folder === 'submitted') {
        versionStates[version] = 'submitted';
        // Calculate response time
        if (versionPendingTimes[version] && timestamp) {
          const deltaHours = (timestamp - versionPendingTimes[version]) / (1000 * 60 * 60);
          if (deltaHours > 0) {
            responseTimes.push(deltaHours);
            reviewerHandled++;
          }
        }
      } else if (folder === 'accepted') {
        versionStates[version] = 'accepted';
      }
    }

    // Count current states
    for (const [version, state] of Object.entries(versionStates)) {
      if (state === 'accepted') totalAccepted++;
      else if (state === 'returned') totalReturned++;
    }
  }

  // Calculate averages
  const avgHours = responseTimes.length > 0 ? responseTimes.reduce((a, b) => a + b, 0) / responseTimes.length : 0;
  const handledPercent = calculatePercentage(totalAccepted, totalAccepted + totalReturned);

  return {
    avg_response_hours: avgHours,
    avg_response_display: formatDuration(avgHours),
    pending_videos: 0, // Will be set by caller
    handled: reviewerHandled,
    accepted: totalAccepted,
    handled_percent: handledPercent,
    total_returned: totalReturned
  };
}

/**
 * Calculate videographer statistics
 */
function calculateVideographerStats(tasksInPeriod) {
  const videographerData = {};
  const videographerSummary = {};

  // Get unique videographers
  const videographers = [...new Set(
    tasksInPeriod
      .filter(t => t.Videographer && t.Videographer.trim() !== '')
      .map(t => t.Videographer)
  )];

  for (const vg of videographers) {
    const vgTasks = tasksInPeriod.filter(t => t.Videographer === vg);

    const vgData = [];
    let vgUploads = 0;
    let vgRejected = 0;
    let vgReturned = 0;
    let vgAccepted = 0;
    let vgSubmitted = 0;
    let vgPending = 0;

    for (const task of vgTasks) {
      const versionHistory = safeParseJSON(task['Version History']);

      const versionStates = {};
      const versionsDict = {};

      let filmingDeadline = task['Filming Date'] || '';
      let uploadedVersion = 'NA';
      let versionNumber = 'NA';
      let submittedAt = 'NA';
      let acceptedAt = 'NA';

      for (const event of versionHistory) {
        if (typeof event !== 'object' || !event) continue;

        const folder = String(event.folder || '').toLowerCase();
        const version = event.version;
        const timestamp = event.at || '';

        if (version === null || version === undefined) continue;

        // Build versions dict
        if (!versionsDict[version]) {
          versionsDict[version] = { version, lifecycle: [] };
        }

        const lifecycleEvent = { stage: folder, at: timestamp };

        if (folder === 'rejected' || folder === 'returned') {
          if (event.rejection_class) lifecycleEvent.rejection_class = event.rejection_class;
          if (event.rejection_comments) lifecycleEvent.rejection_comments = event.rejection_comments;
          if (event.rejected_by) lifecycleEvent.rejected_by = event.rejected_by;
        }

        versionsDict[version].lifecycle.push(lifecycleEvent);

        // Update state
        if (folder === 'pending') {
          versionStates[version] = 'pending';
          uploadedVersion = timestamp;
          versionNumber = `v${version}`;
        } else if (folder === 'rejected') {
          versionStates[version] = 'rejected';
        } else if (folder === 'returned') {
          versionStates[version] = 'returned';
        } else if (folder === 'submitted to sales' || folder === 'submitted') {
          versionStates[version] = 'submitted';
          submittedAt = timestamp;
        } else if (folder === 'accepted') {
          versionStates[version] = 'accepted';
          acceptedAt = timestamp;
        }
      }

      // Count uploads and states
      vgUploads += Object.keys(versionStates).length;

      for (const [version, state] of Object.entries(versionStates)) {
        if (state === 'pending') vgPending++;
        else if (state === 'rejected') vgRejected++;
        else if (state === 'returned') vgReturned++;
        else if (state === 'submitted') vgSubmitted++;
        else if (state === 'accepted') vgAccepted++;
      }

      // Sort versions descending
      const versionsForDisplay = Object.values(versionsDict).sort((a, b) => b.version - a.version);

      vgData.push({
        task_number: String(task['Task #'] || ''),
        brand: task.Brand || '',
        reference: task['Reference Number'] || '',
        status: task.Status || '',
        filming_deadline: filmingDeadline,
        uploaded_version: uploadedVersion,
        version_number: versionNumber,
        submitted_at: submittedAt,
        accepted_at: acceptedAt,
        versions: versionsForDisplay
      });
    }

    videographerData[vg] = vgData;

    // Calculate acceptance rate
    const decidedVideos = vgAccepted + vgSubmitted + vgReturned + vgRejected;
    const positiveOutcomes = vgAccepted + vgSubmitted;
    const acceptanceRate = calculatePercentage(positiveOutcomes, decidedVideos);

    videographerSummary[vg] = {
      total: vgTasks.length,
      uploads: vgUploads,
      pending: vgPending,
      rejected: vgRejected,
      submitted_to_sales: vgSubmitted,
      returned: vgReturned,
      accepted_videos: vgAccepted,
      accepted_pct: acceptanceRate
    };
  }

  return { videographerData, videographerSummary };
}

/**
 * Main dashboard data generation
 */
async function getDashboardData(mode = 'month', period = '') {
  try {
    console.log(`\n=== DASHBOARD REQUEST: mode=${mode}, period=${period} ===`);

    // Default period to current if not provided
    if (!period) {
      const now = new Date();
      period = mode === 'month'
        ? `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
        : String(now.getFullYear());
    }

    // Load all tasks
    const allTasks = await db.getAllTasks();
    console.log(`Loaded ${allTasks.length} total tasks from database`);

    if (allTasks.length === 0) {
      return getEmptyDashboardResponse(mode, period);
    }

    // Parse filming dates and filter by period
    const tasksWithDates = allTasks.map(task => ({
      ...task,
      parsed_filming_date: parseDate(task['Filming Date'])
    }));

    const tasksInPeriod = tasksWithDates.filter(task =>
      isDateInPeriod(task.parsed_filming_date, mode, period)
    );

    console.log(`Tasks in period: ${tasksInPeriod.length}`);

    if (tasksInPeriod.length === 0) {
      return getEmptyDashboardResponse(mode, period);
    }

    // Initialize counters
    const totalTasks = tasksInPeriod.length;
    const assignedTasks = tasksInPeriod.filter(t => t.Videographer && t.Videographer.trim() !== '').length;

    let totalUploads = 0;
    let totalRejected = 0;
    let totalReturned = 0;
    let totalAccepted = 0;
    let currentlyPending = 0;
    let currentlyInSales = 0;
    let completedTasks = 0;

    // Process each task
    for (const task of tasksInPeriod) {
      const versionHistory = safeParseJSON(task['Version History']);
      const versionStates = {};

      for (const event of versionHistory) {
        if (typeof event !== 'object' || !event) continue;

        const folder = String(event.folder || '').toLowerCase();
        const version = event.version;

        if (version === null || version === undefined) continue;

        // Update version state
        if (folder === 'pending') versionStates[version] = 'pending';
        else if (folder === 'rejected') versionStates[version] = 'rejected';
        else if (folder === 'returned') versionStates[version] = 'returned';
        else if (folder === 'submitted to sales' || folder === 'submitted') versionStates[version] = 'submitted';
        else if (folder === 'accepted') versionStates[version] = 'accepted';
      }

      // Count uploads
      totalUploads += Object.keys(versionStates).length;

      for (const [version, state] of Object.entries(versionStates)) {
        if (state === 'pending') currentlyPending++;
        else if (state === 'rejected') totalRejected++;
        else if (state === 'returned') totalReturned++;
        else if (state === 'submitted') currentlyInSales++;
        else if (state === 'accepted') totalAccepted++;
      }

      // Task completed if has at least one accepted version
      if (Object.values(versionStates).includes('accepted')) {
        completedTasks++;
      }
    }

    const totalCompleted = completedTasks;
    const notCompleted = Math.max(totalTasks - totalCompleted, 0);

    // Calculate percentages
    const decidedVersions = totalAccepted + currentlyInSales + totalReturned + totalRejected;
    const positiveOutcomes = totalAccepted + currentlyInSales;
    const acceptedPct = calculatePercentage(positiveOutcomes, decidedVersions);
    const negativeOutcomes = totalRejected + totalReturned;
    const rejectedPct = calculatePercentage(negativeOutcomes, decidedVersions);

    // Calculate reviewer stats
    const reviewerStats = calculateReviewerStats(tasksInPeriod);
    reviewerStats.pending_videos = currentlyPending;

    // Calculate videographer stats
    const { videographerData, videographerSummary } = calculateVideographerStats(tasksInPeriod);

    return {
      mode,
      period,
      pie: {
        completed: totalCompleted,
        not_completed: notCompleted
      },
      summary: {
        total: totalTasks,
        assigned: assignedTasks,
        pending: currentlyPending,
        rejected: totalRejected,
        submitted_to_sales: currentlyInSales,
        returned: totalReturned,
        uploads: totalUploads,
        accepted_videos: totalAccepted,
        accepted_pct: acceptedPct,
        rejected_pct: rejectedPct
      },
      reviewer: reviewerStats,
      videographers: videographerData,
      summary_videographers: videographerSummary
    };

  } catch (error) {
    console.error('Dashboard service error:', error);
    throw error;
  }
}

module.exports = {
  getDashboardData,
  parseDate,
  isDateInPeriod,
  formatDuration,
  calculatePercentage
};

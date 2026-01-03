const sqlite3 = require('sqlite3').verbose();
const path = require('path');

// Determine data directory based on environment
const IS_PRODUCTION = process.env.RENDER === 'true' ||
                     process.env.PORT !== undefined ||
                     process.env.PRODUCTION === 'true';

const DATA_DIR = IS_PRODUCTION ? '/data' : path.join(__dirname, '..', '..', 'data');
const HISTORY_DB_PATH = path.join(DATA_DIR, 'history_logs.db');

console.log(`📁 Using database at: ${HISTORY_DB_PATH}`);

/**
 * Get database connection
 */
function getDatabase() {
  return new Promise((resolve, reject) => {
    const db = new sqlite3.Database(HISTORY_DB_PATH, sqlite3.OPEN_READONLY, (err) => {
      if (err) {
        console.error('Database connection error:', err);
        reject(err);
      } else {
        resolve(db);
      }
    });
  });
}

/**
 * Execute a query and return all rows
 */
async function queryAll(sql, params = []) {
  const db = await getDatabase();

  return new Promise((resolve, reject) => {
    db.all(sql, params, (err, rows) => {
      db.close();
      if (err) {
        reject(err);
      } else {
        resolve(rows);
      }
    });
  });
}

/**
 * Execute a query and return a single row
 */
async function queryOne(sql, params = []) {
  const db = await getDatabase();

  return new Promise((resolve, reject) => {
    db.get(sql, params, (err, row) => {
      db.close();
      if (err) {
        reject(err);
      } else {
        resolve(row);
      }
    });
  });
}

/**
 * Get all live tasks
 */
async function getLiveTasks() {
  const sql = `
    SELECT
      task_number as "Task #",
      Brand,
      "Campaign Start Date",
      "Campaign End Date",
      "Reference Number",
      Location,
      "Sales Person",
      "Submitted By",
      Status,
      "Filming Date",
      Videographer,
      "Task Type",
      "Submission Folder",
      "Current Version",
      "Version History",
      Timestamp,
      "Pending Timestamps",
      "Submitted Timestamps",
      "Returned Timestamps",
      "Rejected Timestamps",
      "Accepted Timestamps"
    FROM live_tasks
    WHERE Status != 'Archived'
  `;

  return await queryAll(sql);
}

/**
 * Get all completed tasks from history
 */
async function getHistoricalTasks() {
  const sql = `
    SELECT
      task_number as "Task #",
      brand as Brand,
      campaign_start_date as "Campaign Start Date",
      campaign_end_date as "Campaign End Date",
      reference_number as "Reference Number",
      location as Location,
      sales_person as "Sales Person",
      submitted_by as "Submitted By",
      COALESCE(status, 'Done') as Status,
      filming_date as "Filming Date",
      videographer as Videographer,
      COALESCE(task_type, 'videography') as "Task Type",
      COALESCE(submission_folder, '') as "Submission Folder",
      current_version as "Current Version",
      COALESCE(version_history, '[]') as "Version History",
      completed_at as Timestamp,
      COALESCE(pending_timestamps, '') as "Pending Timestamps",
      COALESCE(submitted_timestamps, '') as "Submitted Timestamps",
      COALESCE(returned_timestamps, '') as "Returned Timestamps",
      COALESCE(rejected_timestamps, '') as "Rejected Timestamps",
      COALESCE(accepted_timestamps, '') as "Accepted Timestamps"
    FROM completed_tasks
    WHERE status != 'Archived'
  `;

  return await queryAll(sql);
}

/**
 * Get all tasks (live + historical)
 */
async function getAllTasks() {
  try {
    const [liveTasks, historicalTasks] = await Promise.all([
      getLiveTasks(),
      getHistoricalTasks()
    ]);

    return [...liveTasks, ...historicalTasks];
  } catch (error) {
    console.error('Error fetching tasks:', error);
    throw error;
  }
}

module.exports = {
  getDatabase,
  queryAll,
  queryOne,
  getLiveTasks,
  getHistoricalTasks,
  getAllTasks
};

/**
 * Database layer - now uses Python API instead of direct SQLite access
 * This avoids disk mounting issues on Render
 */

const IS_PRODUCTION = process.env.RENDER === 'true' ||
                     process.env.PORT !== undefined ||
                     process.env.PRODUCTION === 'true';

// Python API URL - flexible, can be set via environment variable
const PYTHON_API_URL = process.env.PYTHON_API_URL ||
  (IS_PRODUCTION
    ? 'https://videocritique-bot-ob8k.onrender.com'
    : 'http://localhost:8000');

console.log(`📡 Using Python API at: ${PYTHON_API_URL}`);

/**
 * Fetch data from Python API
 */
async function fetchFromAPI(endpoint) {
  const url = `${PYTHON_API_URL}${endpoint}`;
  console.log(`📡 Fetching: ${url}`);

  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }

  return await response.json();
}

/**
 * Get all tasks from Python API
 * Note: This returns raw task data, not dashboard data
 * The Python /api/get_requests endpoint returns all tasks
 */
async function getAllTasks() {
  try {
    // Call Python API to get all tasks
    const data = await fetchFromAPI('/api/get_requests');

    // The API returns { requests: [...] }
    return data.requests || [];
  } catch (error) {
    console.error('Error fetching tasks from API:', error);
    throw error;
  }
}

/**
 * Get live tasks (filter from all tasks)
 */
async function getLiveTasks() {
  const allTasks = await getAllTasks();
  // Filter for non-archived tasks from live database
  // The API already filters archived tasks
  return allTasks;
}

/**
 * Get historical tasks
 * For now, return empty - the Python API combines both
 */
async function getHistoricalTasks() {
  return [];
}

module.exports = {
  getAllTasks,
  getLiveTasks,
  getHistoricalTasks
};

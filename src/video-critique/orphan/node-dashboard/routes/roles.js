const express = require('express');
const router = express.Router();
const fs = require('fs').promises;
const path = require('path');
const { spawn } = require('child_process');

// Determine config path based on environment
const isProduction = process.env.NODE_ENV === 'production';
const CONFIG_PATH = isProduction
  ? '/data/videographer_config.json'
  : path.join(__dirname, '..', '..', 'data', 'videographer_config.json');

// Path to Python script for role reassignment
const PYTHON_SCRIPT_PATH = path.join(__dirname, '..', '..', 'trigger_role_reassignment.py');
const PYTHON_EXECUTABLE = process.env.PYTHON_PATH || 'python3';

// Helper function to load config
async function loadConfig() {
  try {
    const data = await fs.readFile(CONFIG_PATH, 'utf8');
    return JSON.parse(data);
  } catch (error) {
    console.error('Error loading config:', error);
    throw new Error('Failed to load configuration');
  }
}

// Helper function to save config
async function saveConfig(config) {
  try {
    await fs.writeFile(CONFIG_PATH, JSON.stringify(config, null, 2), 'utf8');
    return true;
  } catch (error) {
    console.error('Error saving config:', error);
    throw new Error('Failed to save configuration');
  }
}

// Validation functions
function validateEmail(email) {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
}

function validateSlackUserId(userId) {
  return userId && userId.startsWith('U') && userId.length > 5;
}

function validateSlackChannelId(channelId) {
  return channelId && channelId.startsWith('D') && channelId.length > 5;
}

// Helper function to trigger Python role reassignment
async function triggerRoleReassignment(roleType, oldData, newData) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify({
      role_type: roleType,
      old_user_id: oldData?.slack_user_id,
      old_channel_id: oldData?.slack_channel_id,
      new_user_id: newData.slack_user_id,
      new_channel_id: newData.slack_channel_id
    });

    const pythonProcess = spawn(PYTHON_EXECUTABLE, [PYTHON_SCRIPT_PATH], {
      cwd: path.join(__dirname, '..', '..')
    });

    let stdout = '';
    let stderr = '';

    pythonProcess.stdin.write(payload);
    pythonProcess.stdin.end();

    pythonProcess.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    pythonProcess.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    pythonProcess.on('close', (code) => {
      if (code === 0) {
        try {
          const result = JSON.parse(stdout);
          resolve(result);
        } catch (e) {
          console.log('Reassignment output:', stdout);
          resolve({ success: true, stdout });
        }
      } else {
        console.error('Reassignment error:', stderr);
        resolve({ success: false, error: stderr });
      }
    });

    pythonProcess.on('error', (error) => {
      console.error('Failed to start reassignment:', error);
      resolve({ success: false, error: error.message });
    });

    // Set timeout
    setTimeout(() => {
      pythonProcess.kill();
      resolve({ success: false, error: 'Reassignment timeout' });
    }, 30000);
  });
}

// GET all configuration
router.get('/config', async (req, res) => {
  try {
    const config = await loadConfig();
    res.json({
      success: true,
      config: config
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// GET all videographers
router.get('/videographers', async (req, res) => {
  try {
    const config = await loadConfig();
    res.json({
      success: true,
      videographers: config.videographers || {}
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// ADD or UPDATE videographer
router.post('/videographers', async (req, res) => {
  try {
    const { name, email, slack_user_id, slack_channel_id, active, oldName } = req.body;

    // Validation
    if (!name || !email || !slack_user_id || !slack_channel_id) {
      return res.status(400).json({
        success: false,
        error: 'All fields are required'
      });
    }

    if (!validateEmail(email)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid email format'
      });
    }

    if (!validateSlackUserId(slack_user_id)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid Slack User ID format (should start with U)'
      });
    }

    if (!validateSlackChannelId(slack_channel_id)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid Slack Channel ID format (should start with D)'
      });
    }

    const config = await loadConfig();

    // If updating and name changed, remove old entry
    if (oldName && oldName !== name && config.videographers[oldName]) {
      delete config.videographers[oldName];

      // Update location mappings
      for (const [location, videographer] of Object.entries(config.location_mappings || {})) {
        if (videographer === oldName) {
          config.location_mappings[location] = name;
        }
      }
    }

    // Add or update videographer
    config.videographers[name] = {
      name,
      email,
      slack_user_id,
      slack_channel_id,
      active: active !== undefined ? active : true
    };

    await saveConfig(config);

    res.json({
      success: true,
      message: oldName ? 'Videographer updated successfully' : 'Videographer added successfully',
      videographer: config.videographers[name]
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// DELETE videographer
router.delete('/videographers/:name', async (req, res) => {
  try {
    const { name } = req.params;
    const config = await loadConfig();

    if (!config.videographers[name]) {
      return res.status(404).json({
        success: false,
        error: 'Videographer not found'
      });
    }

    delete config.videographers[name];

    // Remove from location mappings
    for (const [location, videographer] of Object.entries(config.location_mappings || {})) {
      if (videographer === name) {
        delete config.location_mappings[location];
      }
    }

    await saveConfig(config);

    res.json({
      success: true,
      message: 'Videographer removed successfully'
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// GET all sales people
router.get('/salespeople', async (req, res) => {
  try {
    const config = await loadConfig();
    res.json({
      success: true,
      salespeople: config.sales_people || {}
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// ADD or UPDATE salesperson
router.post('/salespeople', async (req, res) => {
  try {
    const { name, email, slack_user_id, slack_channel_id, active, oldName } = req.body;

    if (!name || !email || !slack_user_id || !slack_channel_id) {
      return res.status(400).json({
        success: false,
        error: 'All fields are required'
      });
    }

    if (!validateEmail(email)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid email format'
      });
    }

    if (!validateSlackUserId(slack_user_id)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid Slack User ID format'
      });
    }

    if (!validateSlackChannelId(slack_channel_id)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid Slack Channel ID format'
      });
    }

    const config = await loadConfig();

    if (oldName && oldName !== name && config.sales_people[oldName]) {
      delete config.sales_people[oldName];
    }

    config.sales_people[name] = {
      name,
      email,
      slack_user_id,
      slack_channel_id,
      active: active !== undefined ? active : true
    };

    await saveConfig(config);

    res.json({
      success: true,
      message: oldName ? 'Salesperson updated successfully' : 'Salesperson added successfully',
      salesperson: config.sales_people[name]
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// DELETE salesperson
router.delete('/salespeople/:name', async (req, res) => {
  try {
    const { name } = req.params;
    const config = await loadConfig();

    if (!config.sales_people[name]) {
      return res.status(404).json({
        success: false,
        error: 'Salesperson not found'
      });
    }

    delete config.sales_people[name];
    await saveConfig(config);

    res.json({
      success: true,
      message: 'Salesperson removed successfully'
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// GET location mappings
router.get('/locations', async (req, res) => {
  try {
    const config = await loadConfig();
    res.json({
      success: true,
      locations: config.location_mappings || {}
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// ADD or UPDATE location mapping
router.post('/locations', async (req, res) => {
  try {
    const { location, videographer, oldLocation } = req.body;

    if (!location || !videographer) {
      return res.status(400).json({
        success: false,
        error: 'Location and videographer are required'
      });
    }

    const config = await loadConfig();

    // Check if videographer exists
    if (!config.videographers[videographer]) {
      return res.status(400).json({
        success: false,
        error: 'Videographer does not exist'
      });
    }

    // If updating location name, remove old entry
    if (oldLocation && oldLocation !== location && config.location_mappings[oldLocation]) {
      delete config.location_mappings[oldLocation];
    }

    config.location_mappings[location] = videographer;
    await saveConfig(config);

    res.json({
      success: true,
      message: oldLocation ? 'Location mapping updated successfully' : 'Location mapping added successfully'
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// DELETE location mapping
router.delete('/locations/:location', async (req, res) => {
  try {
    const { location } = req.params;
    const config = await loadConfig();

    if (!config.location_mappings[location]) {
      return res.status(404).json({
        success: false,
        error: 'Location mapping not found'
      });
    }

    delete config.location_mappings[location];
    await saveConfig(config);

    res.json({
      success: true,
      message: 'Location mapping removed successfully'
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// GET single-person roles (reviewer, hod, head_of_sales)
router.get('/single-roles', async (req, res) => {
  try {
    const config = await loadConfig();
    res.json({
      success: true,
      reviewer: config.reviewer || null,
      hod: config.hod || null,
      head_of_sales: config.head_of_sales || null
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// UPDATE single-person role
router.put('/single-roles/:role', async (req, res) => {
  try {
    const { role } = req.params;
    const { name, email, slack_user_id, slack_channel_id, active } = req.body;

    if (!['reviewer', 'hod', 'head_of_sales'].includes(role)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid role type'
      });
    }

    if (!name || !email || !slack_user_id || !slack_channel_id) {
      return res.status(400).json({
        success: false,
        error: 'All fields are required'
      });
    }

    if (!validateEmail(email)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid email format'
      });
    }

    if (!validateSlackUserId(slack_user_id)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid Slack User ID format'
      });
    }

    if (!validateSlackChannelId(slack_channel_id)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid Slack Channel ID format'
      });
    }

    const config = await loadConfig();

    // Store old role data for reassignment
    const oldRoleData = config[role];

    // Check if user ID or channel ID changed (triggers reassignment)
    const userChanged = oldRoleData &&
      (oldRoleData.slack_user_id !== slack_user_id ||
       oldRoleData.slack_channel_id !== slack_channel_id);

    const newRoleData = {
      name,
      email,
      slack_user_id,
      slack_channel_id,
      active: active !== undefined ? active : true
    };

    config[role] = newRoleData;
    await saveConfig(config);

    // If user changed, trigger reassignment for reviewer or head_of_sales
    let reassignmentResult = null;
    if (userChanged && (role === 'reviewer' || role === 'head_of_sales')) {
      console.log(`Role change detected for ${role}, triggering reassignment...`);
      reassignmentResult = await triggerRoleReassignment(role, oldRoleData, newRoleData);

      if (reassignmentResult.success) {
        console.log(`✅ Reassignment successful for ${role}:`, reassignmentResult);
      } else {
        console.error(`⚠️ Reassignment failed for ${role}:`, reassignmentResult.error);
      }
    }

    res.json({
      success: true,
      message: `${role} updated successfully`,
      [role]: config[role],
      reassignment: reassignmentResult
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// GET admins
router.get('/admins', async (req, res) => {
  try {
    const config = await loadConfig();
    res.json({
      success: true,
      admin: config.admin || {},
      super_admin: config.super_admin || {}
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// ADD or UPDATE admin
router.post('/admins/:type', async (req, res) => {
  try {
    const { type } = req.params; // 'admin' or 'super_admin'
    const { name, email, slack_user_id, slack_channel_id, active, oldName } = req.body;

    if (!['admin', 'super_admin'].includes(type)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid admin type'
      });
    }

    if (!name || !email || !slack_user_id || !slack_channel_id) {
      return res.status(400).json({
        success: false,
        error: 'All fields are required'
      });
    }

    if (!validateEmail(email)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid email format'
      });
    }

    if (!validateSlackUserId(slack_user_id)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid Slack User ID format'
      });
    }

    if (!validateSlackChannelId(slack_channel_id)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid Slack Channel ID format'
      });
    }

    const config = await loadConfig();

    if (oldName && oldName !== name && config[type][oldName]) {
      delete config[type][oldName];
    }

    config[type][name] = {
      name,
      email,
      slack_user_id,
      slack_channel_id,
      active: active !== undefined ? active : true
    };

    await saveConfig(config);

    res.json({
      success: true,
      message: oldName ? `${type} updated successfully` : `${type} added successfully`,
      admin: config[type][name]
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// DELETE admin
router.delete('/admins/:type/:name', async (req, res) => {
  try {
    const { type, name } = req.params;

    if (!['admin', 'super_admin'].includes(type)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid admin type'
      });
    }

    const config = await loadConfig();

    if (!config[type][name]) {
      return res.status(404).json({
        success: false,
        error: `${type} not found`
      });
    }

    delete config[type][name];
    await saveConfig(config);

    res.json({
      success: true,
      message: `${type} removed successfully`
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// GET permissions
router.get('/permissions', async (req, res) => {
  try {
    const config = await loadConfig();
    res.json({
      success: true,
      group_permissions: config.group_permissions || {},
      permissions: config.permissions || {}
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// UPDATE group permissions
router.put('/permissions/groups/:group', async (req, res) => {
  try {
    const { group } = req.params;
    const { permissions } = req.body;

    if (!permissions || !Array.isArray(permissions)) {
      return res.status(400).json({
        success: false,
        error: 'Permissions array is required'
      });
    }

    const config = await loadConfig();

    if (!config.group_permissions) {
      config.group_permissions = {};
    }

    config.group_permissions[group] = permissions;
    await saveConfig(config);

    res.json({
      success: true,
      message: 'Group permissions updated successfully',
      permissions: config.group_permissions[group]
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// UPDATE action permissions
router.put('/permissions/actions/:action', async (req, res) => {
  try {
    const { action } = req.params;
    const { roles } = req.body;

    if (!roles || !Array.isArray(roles)) {
      return res.status(400).json({
        success: false,
        error: 'Roles array is required'
      });
    }

    const config = await loadConfig();

    if (!config.permissions) {
      config.permissions = {};
    }

    config.permissions[action] = roles;
    await saveConfig(config);

    res.json({
      success: true,
      message: 'Action permissions updated successfully',
      roles: config.permissions[action]
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

module.exports = router;

// Global state
let config = null;
let currentTab = 'videographers';

// Check authentication
function checkAuth() {
  const userData = localStorage.getItem('userData');
  if (!userData) {
    window.location.href = '/';
    return null;
  }
  const user = JSON.parse(userData);
  document.getElementById('userName').textContent = user.name;
  return user;
}

// Logout
function logout() {
  localStorage.removeItem('userData');
  window.location.href = '/';
}

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
  checkAuth();
  await loadConfig();
  switchTab('videographers');
});

// Load configuration
async function loadConfig() {
  try {
    const response = await fetch('/api/roles/config');
    const data = await response.json();

    if (data.success) {
      config = data.config;
      renderAll();
      document.getElementById('loadingState').style.display = 'none';
    } else {
      showNotification('Failed to load configuration', 'error');
    }
  } catch (error) {
    console.error('Error loading config:', error);
    showNotification('Error loading configuration', 'error');
  }
}

// Switch tabs
function switchTab(tab) {
  currentTab = tab;

  // Update tab buttons
  document.querySelectorAll('.tab-button').forEach(btn => {
    btn.classList.remove('active');
  });
  event.target.classList.add('active');

  // Hide all sections
  document.querySelectorAll('.tab-content').forEach(section => {
    section.style.display = 'none';
  });

  // Show selected section
  const section = document.getElementById(`${tab}-section`);
  if (section) {
    section.style.display = 'block';
  }
}

// Render all sections
function renderAll() {
  renderVideographers();
  renderSalespeople();
  renderLocations();
  renderSingleRoles();
  renderAdmins();
  renderPermissions();
}

// Render videographers
function renderVideographers() {
  const tbody = document.getElementById('videographersTable');
  tbody.innerHTML = '';

  const videographers = config.videographers || {};
  const entries = Object.entries(videographers);

  if (entries.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center p-8 text-gray-500">No videographers found. Add one to get started.</td></tr>';
    return;
  }

  entries.forEach(([name, data]) => {
    const row = document.createElement('tr');
    row.className = 'table-row border-b border-gray-200';
    row.innerHTML = `
      <td class="p-4 font-medium text-gray-800">${data.name}</td>
      <td class="p-4 text-gray-600">${data.email}</td>
      <td class="p-4 text-gray-600 font-mono text-sm">${data.slack_user_id}</td>
      <td class="p-4 text-gray-600 font-mono text-sm">${data.slack_channel_id}</td>
      <td class="p-4 text-center">
        <span class="badge ${data.active ? 'badge-active' : 'badge-inactive'}">
          ${data.active ? 'Active' : 'Inactive'}
        </span>
      </td>
      <td class="p-4 text-center">
        <button onclick='editVideographer(${JSON.stringify(data)})' class="text-blue-600 hover:text-blue-800 mr-3">
          <i class="fas fa-edit"></i>
        </button>
        <button onclick="deleteVideographer('${name}')" class="text-red-600 hover:text-red-800">
          <i class="fas fa-trash"></i>
        </button>
      </td>
    `;
    tbody.appendChild(row);
  });
}

// Render salespeople
function renderSalespeople() {
  const tbody = document.getElementById('salespeopleTable');
  tbody.innerHTML = '';

  const salespeople = config.sales_people || {};
  const entries = Object.entries(salespeople);

  if (entries.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center p-8 text-gray-500">No sales people found. Add one to get started.</td></tr>';
    return;
  }

  entries.forEach(([name, data]) => {
    const row = document.createElement('tr');
    row.className = 'table-row border-b border-gray-200';
    row.innerHTML = `
      <td class="p-4 font-medium text-gray-800">${data.name}</td>
      <td class="p-4 text-gray-600">${data.email}</td>
      <td class="p-4 text-gray-600 font-mono text-sm">${data.slack_user_id}</td>
      <td class="p-4 text-gray-600 font-mono text-sm">${data.slack_channel_id}</td>
      <td class="p-4 text-center">
        <span class="badge ${data.active ? 'badge-active' : 'badge-inactive'}">
          ${data.active ? 'Active' : 'Inactive'}
        </span>
      </td>
      <td class="p-4 text-center">
        <button onclick='editSalesperson(${JSON.stringify(data)})' class="text-blue-600 hover:text-blue-800 mr-3">
          <i class="fas fa-edit"></i>
        </button>
        <button onclick="deleteSalesperson('${name}')" class="text-red-600 hover:text-red-800">
          <i class="fas fa-trash"></i>
        </button>
      </td>
    `;
    tbody.appendChild(row);
  });
}

// Render locations
function renderLocations() {
  const tbody = document.getElementById('locationsTable');
  tbody.innerHTML = '';

  const locations = config.location_mappings || {};
  const entries = Object.entries(locations);

  if (entries.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3" class="text-center p-8 text-gray-500">No location mappings found. Add one to get started.</td></tr>';
    return;
  }

  entries.forEach(([location, videographer]) => {
    const row = document.createElement('tr');
    row.className = 'table-row border-b border-gray-200';
    row.innerHTML = `
      <td class="p-4 font-medium text-gray-800">${location}</td>
      <td class="p-4 text-gray-600">${videographer}</td>
      <td class="p-4 text-center">
        <button onclick='editLocation("${location}", "${videographer}")' class="text-blue-600 hover:text-blue-800 mr-3">
          <i class="fas fa-edit"></i>
        </button>
        <button onclick="deleteLocation('${location}')" class="text-red-600 hover:text-red-800">
          <i class="fas fa-trash"></i>
        </button>
      </td>
    `;
    tbody.appendChild(row);
  });
}

// Render single roles
function renderSingleRoles() {
  renderSingleRole('reviewer', 'reviewerInfo');
  renderSingleRole('hod', 'hodInfo');
  renderSingleRole('head_of_sales', 'hosInfo');
}

function renderSingleRole(role, containerId) {
  const container = document.getElementById(containerId);
  const data = config[role];

  if (!data) {
    container.innerHTML = '<p class="text-gray-500 col-span-2">Not configured</p>';
    return;
  }

  container.innerHTML = `
    <div>
      <p class="text-sm text-gray-600 font-semibold">Name</p>
      <p class="text-gray-800">${data.name}</p>
    </div>
    <div>
      <p class="text-sm text-gray-600 font-semibold">Email</p>
      <p class="text-gray-800">${data.email}</p>
    </div>
    <div>
      <p class="text-sm text-gray-600 font-semibold">Slack User ID</p>
      <p class="text-gray-800 font-mono text-sm">${data.slack_user_id}</p>
    </div>
    <div>
      <p class="text-sm text-gray-600 font-semibold">Slack Channel ID</p>
      <p class="text-gray-800 font-mono text-sm">${data.slack_channel_id}</p>
    </div>
    <div>
      <p class="text-sm text-gray-600 font-semibold">Status</p>
      <span class="badge ${data.active ? 'badge-active' : 'badge-inactive'}">
        ${data.active ? 'Active' : 'Inactive'}
      </span>
    </div>
  `;
}

// Render admins
function renderAdmins() {
  renderAdminTable('super_admin', 'superAdminsTable');
  renderAdminTable('admin', 'adminsTable');
}

function renderAdminTable(type, tableId) {
  const tbody = document.getElementById(tableId);
  tbody.innerHTML = '';

  const admins = config[type] || {};
  const entries = Object.entries(admins);

  if (entries.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center p-8 text-gray-500">No ${type.replace('_', ' ')}s found. Add one to get started.</td></tr>`;
    return;
  }

  entries.forEach(([name, data]) => {
    const row = document.createElement('tr');
    row.className = 'table-row border-b border-gray-200';
    row.innerHTML = `
      <td class="p-4 font-medium text-gray-800">${data.name}</td>
      <td class="p-4 text-gray-600">${data.email}</td>
      <td class="p-4 text-gray-600 font-mono text-sm">${data.slack_user_id}</td>
      <td class="p-4 text-gray-600 font-mono text-sm">${data.slack_channel_id}</td>
      <td class="p-4 text-center">
        <span class="badge ${data.active ? 'badge-active' : 'badge-inactive'}">
          ${data.active ? 'Active' : 'Inactive'}
        </span>
      </td>
      <td class="p-4 text-center">
        <button onclick='editAdmin("${type}", ${JSON.stringify(data)})' class="text-blue-600 hover:text-blue-800 mr-3">
          <i class="fas fa-edit"></i>
        </button>
        <button onclick="deleteAdmin('${type}', '${name}')" class="text-red-600 hover:text-red-800">
          <i class="fas fa-trash"></i>
        </button>
      </td>
    `;
    tbody.appendChild(row);
  });
}

// Render permissions
function renderPermissions() {
  const container = document.getElementById('permissionsContent');

  const groupPerms = config.group_permissions || {};
  const actionPerms = config.permissions || {};

  let html = '<div class="space-y-6">';

  // Group Permissions
  html += '<div class="border-b border-gray-200 pb-6">';
  html += '<h3 class="text-xl font-bold text-gray-800 mb-4">Group Permissions</h3>';
  html += '<p class="text-sm text-gray-600 mb-4">Permissions assigned to each role group.</p>';
  html += '<div class="space-y-3">';

  Object.entries(groupPerms).forEach(([group, perms]) => {
    html += `
      <div class="bg-gray-50 p-4 rounded-lg">
        <div class="flex justify-between items-start mb-2">
          <h4 class="font-bold text-gray-800">${group}</h4>
          <button onclick='editGroupPermissions("${group}")' class="text-blue-600 hover:text-blue-800 text-sm">
            <i class="fas fa-edit mr-1"></i>Edit
          </button>
        </div>
        <div class="flex flex-wrap gap-2">
          ${perms.map(p => `<span class="badge bg-purple-100 text-purple-800">${p}</span>`).join('')}
        </div>
      </div>
    `;
  });

  html += '</div></div>';

  // Action Permissions
  html += '<div>';
  html += '<h3 class="text-xl font-bold text-gray-800 mb-4">Action Permissions</h3>';
  html += '<p class="text-sm text-gray-600 mb-4">Roles that can perform each action.</p>';
  html += '<div class="space-y-3">';

  Object.entries(actionPerms).forEach(([action, roles]) => {
    html += `
      <div class="bg-gray-50 p-4 rounded-lg">
        <div class="flex justify-between items-start mb-2">
          <h4 class="font-bold text-gray-800">${action}</h4>
          <button onclick='editActionPermissions("${action}")' class="text-blue-600 hover:text-blue-800 text-sm">
            <i class="fas fa-edit mr-1"></i>Edit
          </button>
        </div>
        <div class="flex flex-wrap gap-2">
          ${roles.map(r => `<span class="badge bg-blue-100 text-blue-800">${r}</span>`).join('')}
        </div>
      </div>
    `;
  });

  html += '</div></div></div>';

  container.innerHTML = html;
}

// Modal functions
function openVideographerModal(data = null) {
  document.getElementById('modalTitle').textContent = data ? 'Edit Videographer' : 'Add Videographer';
  document.getElementById('userType').value = 'videographer';

  if (data) {
    document.getElementById('userOldName').value = data.name;
    document.getElementById('userName').value = data.name;
    document.getElementById('userEmail').value = data.email;
    document.getElementById('userSlackUserId').value = data.slack_user_id;
    document.getElementById('userSlackChannelId').value = data.slack_channel_id;
    document.getElementById('userActive').checked = data.active;
  } else {
    document.getElementById('userForm').reset();
    document.getElementById('userOldName').value = '';
    document.getElementById('userActive').checked = true;
  }

  document.getElementById('userModal').classList.add('active');
}

function editVideographer(data) {
  openVideographerModal(data);
}

function openSalespersonModal(data = null) {
  document.getElementById('modalTitle').textContent = data ? 'Edit Salesperson' : 'Add Salesperson';
  document.getElementById('userType').value = 'salesperson';

  if (data) {
    document.getElementById('userOldName').value = data.name;
    document.getElementById('userName').value = data.name;
    document.getElementById('userEmail').value = data.email;
    document.getElementById('userSlackUserId').value = data.slack_user_id;
    document.getElementById('userSlackChannelId').value = data.slack_channel_id;
    document.getElementById('userActive').checked = data.active;
  } else {
    document.getElementById('userForm').reset();
    document.getElementById('userOldName').value = '';
    document.getElementById('userActive').checked = true;
  }

  document.getElementById('userModal').classList.add('active');
}

function editSalesperson(data) {
  openSalespersonModal(data);
}

function openAdminModal(type, data = null) {
  document.getElementById('modalTitle').textContent = data ? `Edit ${type.replace('_', ' ')}` : `Add ${type.replace('_', ' ')}`;
  document.getElementById('userType').value = type;

  if (data) {
    document.getElementById('userOldName').value = data.name;
    document.getElementById('userName').value = data.name;
    document.getElementById('userEmail').value = data.email;
    document.getElementById('userSlackUserId').value = data.slack_user_id;
    document.getElementById('userSlackChannelId').value = data.slack_channel_id;
    document.getElementById('userActive').checked = data.active;
  } else {
    document.getElementById('userForm').reset();
    document.getElementById('userOldName').value = '';
    document.getElementById('userActive').checked = true;
  }

  document.getElementById('userModal').classList.add('active');
}

function editAdmin(type, data) {
  openAdminModal(type, data);
}

function openLocationModal(location = null, videographer = null) {
  document.getElementById('locationModalTitle').textContent = location ? 'Edit Location' : 'Add Location';

  // Populate videographer dropdown
  const select = document.getElementById('locationVideographer');
  select.innerHTML = '<option value="">Select Videographer</option>';

  Object.keys(config.videographers || {}).forEach(name => {
    const option = document.createElement('option');
    option.value = name;
    option.textContent = name;
    if (name === videographer) {
      option.selected = true;
    }
    select.appendChild(option);
  });

  if (location) {
    document.getElementById('locationOldName').value = location;
    document.getElementById('locationName').value = location;
  } else {
    document.getElementById('locationForm').reset();
    document.getElementById('locationOldName').value = '';
  }

  document.getElementById('locationModal').classList.add('active');
}

function editLocation(location, videographer) {
  openLocationModal(location, videographer);
}

function openSingleRoleModal(role) {
  const data = config[role];
  const roleNames = {
    'reviewer': 'Reviewer',
    'hod': 'Head of Department',
    'head_of_sales': 'Head of Sales'
  };

  document.getElementById('modalTitle').textContent = `Edit ${roleNames[role]}`;
  document.getElementById('userType').value = `single_role_${role}`;

  if (data) {
    document.getElementById('userName').value = data.name;
    document.getElementById('userEmail').value = data.email;
    document.getElementById('userSlackUserId').value = data.slack_user_id;
    document.getElementById('userSlackChannelId').value = data.slack_channel_id;
    document.getElementById('userActive').checked = data.active;
  }

  document.getElementById('userModal').classList.add('active');
}

function closeModal(modalId) {
  document.getElementById(modalId).classList.remove('active');
}

// Save functions
async function saveUser(event) {
  event.preventDefault();

  const type = document.getElementById('userType').value;
  const oldName = document.getElementById('userOldName').value;
  const data = {
    name: document.getElementById('userName').value,
    email: document.getElementById('userEmail').value,
    slack_user_id: document.getElementById('userSlackUserId').value,
    slack_channel_id: document.getElementById('userSlackChannelId').value,
    active: document.getElementById('userActive').checked,
    oldName: oldName || undefined
  };

  try {
    let url, method;

    if (type === 'videographer') {
      url = '/api/roles/videographers';
      method = 'POST';
    } else if (type === 'salesperson') {
      url = '/api/roles/salespeople';
      method = 'POST';
    } else if (type.startsWith('single_role_')) {
      const role = type.replace('single_role_', '');
      url = `/api/roles/single-roles/${role}`;
      method = 'PUT';
    } else if (type === 'admin' || type === 'super_admin') {
      url = `/api/roles/admins/${type}`;
      method = 'POST';
    }

    const response = await fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });

    const result = await response.json();

    if (result.success) {
      showNotification(result.message, 'success');
      await loadConfig();
      closeModal('userModal');
    } else {
      showNotification(result.error, 'error');
    }
  } catch (error) {
    console.error('Error saving user:', error);
    showNotification('Error saving user', 'error');
  }
}

async function saveLocation(event) {
  event.preventDefault();

  const oldLocation = document.getElementById('locationOldName').value;
  const data = {
    location: document.getElementById('locationName').value,
    videographer: document.getElementById('locationVideographer').value,
    oldLocation: oldLocation || undefined
  };

  try {
    const response = await fetch('/api/roles/locations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });

    const result = await response.json();

    if (result.success) {
      showNotification(result.message, 'success');
      await loadConfig();
      closeModal('locationModal');
    } else {
      showNotification(result.error, 'error');
    }
  } catch (error) {
    console.error('Error saving location:', error);
    showNotification('Error saving location', 'error');
  }
}

// Delete functions
async function deleteVideographer(name) {
  if (!confirm(`Are you sure you want to delete videographer "${name}"? This will also remove all location mappings.`)) {
    return;
  }

  try {
    const response = await fetch(`/api/roles/videographers/${encodeURIComponent(name)}`, {
      method: 'DELETE'
    });

    const result = await response.json();

    if (result.success) {
      showNotification(result.message, 'success');
      await loadConfig();
    } else {
      showNotification(result.error, 'error');
    }
  } catch (error) {
    console.error('Error deleting videographer:', error);
    showNotification('Error deleting videographer', 'error');
  }
}

async function deleteSalesperson(name) {
  if (!confirm(`Are you sure you want to delete salesperson "${name}"?`)) {
    return;
  }

  try {
    const response = await fetch(`/api/roles/salespeople/${encodeURIComponent(name)}`, {
      method: 'DELETE'
    });

    const result = await response.json();

    if (result.success) {
      showNotification(result.message, 'success');
      await loadConfig();
    } else {
      showNotification(result.error, 'error');
    }
  } catch (error) {
    console.error('Error deleting salesperson:', error);
    showNotification('Error deleting salesperson', 'error');
  }
}

async function deleteLocation(location) {
  if (!confirm(`Are you sure you want to delete location mapping "${location}"?`)) {
    return;
  }

  try {
    const response = await fetch(`/api/roles/locations/${encodeURIComponent(location)}`, {
      method: 'DELETE'
    });

    const result = await response.json();

    if (result.success) {
      showNotification(result.message, 'success');
      await loadConfig();
    } else {
      showNotification(result.error, 'error');
    }
  } catch (error) {
    console.error('Error deleting location:', error);
    showNotification('Error deleting location', 'error');
  }
}

async function deleteAdmin(type, name) {
  if (!confirm(`Are you sure you want to delete ${type.replace('_', ' ')} "${name}"?`)) {
    return;
  }

  try {
    const response = await fetch(`/api/roles/admins/${type}/${encodeURIComponent(name)}`, {
      method: 'DELETE'
    });

    const result = await response.json();

    if (result.success) {
      showNotification(result.message, 'success');
      await loadConfig();
    } else {
      showNotification(result.error, 'error');
    }
  } catch (error) {
    console.error('Error deleting admin:', error);
    showNotification('Error deleting admin', 'error');
  }
}

// Permission editing (simplified for now)
function editGroupPermissions(group) {
  const perms = config.group_permissions[group] || [];
  const newPerms = prompt(`Edit permissions for group "${group}" (comma-separated):`, perms.join(', '));

  if (newPerms !== null) {
    const permArray = newPerms.split(',').map(p => p.trim()).filter(p => p);
    updateGroupPermissions(group, permArray);
  }
}

function editActionPermissions(action) {
  const roles = config.permissions[action] || [];
  const newRoles = prompt(`Edit roles for action "${action}" (comma-separated):`, roles.join(', '));

  if (newRoles !== null) {
    const roleArray = newRoles.split(',').map(r => r.trim()).filter(r => r);
    updateActionPermissions(action, roleArray);
  }
}

async function updateGroupPermissions(group, permissions) {
  try {
    const response = await fetch(`/api/roles/permissions/groups/${encodeURIComponent(group)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ permissions })
    });

    const result = await response.json();

    if (result.success) {
      showNotification(result.message, 'success');
      await loadConfig();
    } else {
      showNotification(result.error, 'error');
    }
  } catch (error) {
    console.error('Error updating permissions:', error);
    showNotification('Error updating permissions', 'error');
  }
}

async function updateActionPermissions(action, roles) {
  try {
    const response = await fetch(`/api/roles/permissions/actions/${encodeURIComponent(action)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roles })
    });

    const result = await response.json();

    if (result.success) {
      showNotification(result.message, 'success');
      await loadConfig();
    } else {
      showNotification(result.error, 'error');
    }
  } catch (error) {
    console.error('Error updating permissions:', error);
    showNotification('Error updating permissions', 'error');
  }
}

// Notification
function showNotification(message, type = 'success') {
  const notification = document.createElement('div');
  notification.className = `notification ${type}`;
  notification.innerHTML = `
    <div class="flex items-center gap-3">
      <i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-circle'} text-xl"></i>
      <span>${message}</span>
    </div>
  `;

  document.body.appendChild(notification);

  setTimeout(() => {
    notification.remove();
  }, 3000);
}

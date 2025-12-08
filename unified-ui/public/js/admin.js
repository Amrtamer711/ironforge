/**
 * Admin Panel JavaScript
 * Handles role and permission management UI
 */

// =============================================================================
// ADMIN STATE
// =============================================================================

const AdminState = {
  roles: [],
  permissions: [],
  permissionsGrouped: {},
  users: [],
  selectedRole: null,
  selectedUser: null,
  isLoading: false,
};

// =============================================================================
// ADMIN API CALLS
// =============================================================================

const AdminAPI = {
  async getDashboard() {
    const response = await API.fetch('/api/sales/admin/dashboard');
    return response;
  },

  async getRoles() {
    const response = await API.fetch('/api/sales/admin/roles');
    return response;
  },

  async getRole(roleName) {
    const response = await API.fetch(`/api/sales/admin/roles/${roleName}`);
    return response;
  },

  async createRole(roleData) {
    const response = await API.fetch('/api/sales/admin/roles', {
      method: 'POST',
      body: JSON.stringify(roleData),
    });
    return response;
  },

  async updateRole(roleName, roleData) {
    const response = await API.fetch(`/api/sales/admin/roles/${roleName}`, {
      method: 'PUT',
      body: JSON.stringify(roleData),
    });
    return response;
  },

  async deleteRole(roleName) {
    await API.fetch(`/api/sales/admin/roles/${roleName}`, {
      method: 'DELETE',
    });
  },

  async getPermissions() {
    const response = await API.fetch('/api/sales/admin/permissions');
    return response;
  },

  async getPermissionsGrouped() {
    const response = await API.fetch('/api/sales/admin/permissions/grouped');
    return response;
  },

  async getUserRoles(userId) {
    const response = await API.fetch(`/api/sales/admin/users/${userId}/roles`);
    return response;
  },

  async assignUserRole(userId, roleName) {
    const response = await API.fetch(`/api/sales/admin/users/${userId}/roles/${roleName}`, {
      method: 'POST',
    });
    return response;
  },

  async revokeUserRole(userId, roleName) {
    await API.fetch(`/api/sales/admin/users/${userId}/roles/${roleName}`, {
      method: 'DELETE',
    });
  },

  async initializeRBAC() {
    const response = await API.fetch('/api/sales/admin/initialize', {
      method: 'POST',
    });
    return response;
  },

  // User Management
  async getUsers(limit = 100, offset = 0) {
    const response = await API.fetch(`/api/sales/admin/users?limit=${limit}&offset=${offset}`);
    return response;
  },

  async getUser(userId) {
    const response = await API.fetch(`/api/sales/admin/users/${userId}`);
    return response;
  },

  async createUser(userData) {
    const response = await API.fetch('/api/sales/admin/users', {
      method: 'POST',
      body: JSON.stringify(userData),
    });
    return response;
  },

  async updateUser(userId, userData) {
    const response = await API.fetch(`/api/sales/admin/users/${userId}`, {
      method: 'PUT',
      body: JSON.stringify(userData),
    });
    return response;
  },

  async deleteUser(userId) {
    await API.fetch(`/api/sales/admin/users/${userId}`, {
      method: 'DELETE',
    });
  },
};

// =============================================================================
// ADMIN UI RENDERING
// =============================================================================

const AdminUI = {
  /**
   * Initialize the admin panel
   */
  async init() {
    console.log('[Admin] Initializing admin panel');

    // Only show admin panel for users with admin role (admin or sales:admin)
    const user = Auth.getUser();
    const hasAdminRole = user?.roles?.some(role =>
      role === 'admin' || role === 'sales:admin'
    );
    if (!user || !hasAdminRole) {
      console.log('[Admin] User does not have admin role');
      return false;
    }

    try {
      AdminState.isLoading = true;

      // Load initial data
      const [roles, permissionsGrouped, users] = await Promise.all([
        AdminAPI.getRoles(),
        AdminAPI.getPermissionsGrouped(),
        AdminAPI.getUsers(),
      ]);

      AdminState.roles = roles;
      AdminState.permissionsGrouped = permissionsGrouped;
      AdminState.users = users;

      console.log('[Admin] Loaded roles:', roles.length);
      console.log('[Admin] Loaded permissions:', Object.keys(permissionsGrouped).length, 'groups');
      console.log('[Admin] Loaded users:', users.length);

      return true;
    } catch (error) {
      console.error('[Admin] Failed to initialize:', error);
      showToast('Failed to load admin data', 'error');
      return false;
    } finally {
      AdminState.isLoading = false;
    }
  },

  /**
   * Render the admin panel content
   */
  render() {
    const container = document.getElementById('adminPanel');
    if (!container) return;

    container.innerHTML = `
      <div class="admin-container">
        <div class="admin-header">
          <h2>Admin Panel</h2>
          <p class="admin-subtitle">Manage roles and permissions</p>
        </div>

        <div class="admin-tabs">
          <button class="admin-tab active" data-tab="users">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
              <circle cx="9" cy="7" r="4"/>
              <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
              <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
            Users
          </button>
          <button class="admin-tab" data-tab="roles">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
            Roles
          </button>
          <button class="admin-tab" data-tab="permissions">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
              <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
            Permissions
          </button>
        </div>

        <div class="admin-content">
          <div class="admin-tab-content active" id="usersTab">
            ${this.renderUsersTab()}
          </div>
          <div class="admin-tab-content" id="rolesTab">
            ${this.renderRolesTab()}
          </div>
          <div class="admin-tab-content" id="permissionsTab">
            ${this.renderPermissionsTab()}
          </div>
        </div>
      </div>
    `;

    this.attachEventListeners();
  },

  /**
   * Render the users tab
   */
  renderUsersTab() {
    return `
      <div class="admin-section">
        <div class="admin-section-header">
          <h3>User Management</h3>
          <span class="admin-badge">${AdminState.users.length}</span>
          <button class="btn btn-primary btn-sm" id="createUserBtn">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            New User
          </button>
        </div>
        <div class="users-table-container">
          <table class="admin-table">
            <thead>
              <tr>
                <th>User</th>
                <th>Email</th>
                <th>Roles</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${AdminState.users.length > 0
                ? AdminState.users.map(user => this.renderUserRow(user)).join('')
                : '<tr><td colspan="5" class="empty-state">No users found. Create one to get started.</td></tr>'
              }
            </tbody>
          </table>
        </div>
      </div>
    `;
  },

  /**
   * Render a single user row
   */
  renderUserRow(user) {
    const statusClass = user.is_active ? 'status-active' : 'status-inactive';
    const statusText = user.is_active ? 'Active' : 'Inactive';

    return `
      <tr class="user-row" data-user-id="${user.id}">
        <td class="user-cell">
          <div class="user-avatar">
            ${user.name ? user.name.charAt(0).toUpperCase() : user.email.charAt(0).toUpperCase()}
          </div>
          <span class="user-name">${user.name || 'No name'}</span>
        </td>
        <td class="user-email">${user.email}</td>
        <td class="user-roles">
          ${user.roles.length > 0
            ? user.roles.map(role => `<span class="role-tag">${role}</span>`).join('')
            : '<span class="no-roles">No roles</span>'
          }
        </td>
        <td>
          <span class="status-badge ${statusClass}">${statusText}</span>
        </td>
        <td class="user-actions">
          <button class="btn-icon edit-user-btn" title="Edit user" data-user-id="${user.id}">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
          </button>
          <button class="btn-icon manage-roles-btn" title="Manage roles" data-user-id="${user.id}">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
          </button>
          <button class="btn-icon delete-user-btn" title="Delete user" data-user-id="${user.id}">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
          </button>
        </td>
      </tr>
    `;
  },

  /**
   * Render the roles tab
   */
  renderRolesTab() {
    const systemRoles = AdminState.roles.filter(r => r.is_system);
    const customRoles = AdminState.roles.filter(r => !r.is_system);

    return `
      <div class="admin-section">
        <div class="admin-section-header">
          <h3>System Roles</h3>
          <span class="admin-badge">${systemRoles.length}</span>
        </div>
        <div class="roles-grid">
          ${systemRoles.map(role => this.renderRoleCard(role)).join('')}
        </div>
      </div>

      <div class="admin-section">
        <div class="admin-section-header">
          <h3>Custom Roles</h3>
          <span class="admin-badge">${customRoles.length}</span>
          <button class="btn btn-primary btn-sm" id="createRoleBtn">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            New Role
          </button>
        </div>
        <div class="roles-grid">
          ${customRoles.length > 0
            ? customRoles.map(role => this.renderRoleCard(role)).join('')
            : '<p class="empty-state">No custom roles yet. Create one to get started.</p>'
          }
        </div>
      </div>
    `;
  },

  /**
   * Render a single role card
   */
  renderRoleCard(role) {
    const permissionCount = role.permissions.length;
    const isSystem = role.is_system;

    return `
      <div class="role-card ${isSystem ? 'role-system' : ''}" data-role="${role.name}">
        <div class="role-card-header">
          <div class="role-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
          </div>
          <div class="role-info">
            <h4 class="role-name">${role.name}</h4>
            ${isSystem ? '<span class="role-badge system">System</span>' : ''}
          </div>
          ${!isSystem ? `
            <div class="role-actions">
              <button class="btn-icon edit-role-btn" title="Edit role" data-role="${role.name}">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
              <button class="btn-icon delete-role-btn" title="Delete role" data-role="${role.name}">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="3 6 5 6 21 6"/>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                </svg>
              </button>
            </div>
          ` : ''}
        </div>
        <p class="role-description">${role.description || 'No description'}</p>
        <div class="role-permissions">
          <span class="permissions-count">${permissionCount} permission${permissionCount !== 1 ? 's' : ''}</span>
          <button class="btn-link view-permissions-btn" data-role="${role.name}">View</button>
        </div>
      </div>
    `;
  },

  /**
   * Render the permissions tab
   */
  renderPermissionsTab() {
    const groups = Object.entries(AdminState.permissionsGrouped);

    return `
      <div class="admin-section">
        <div class="admin-section-header">
          <h3>Available Permissions</h3>
          <span class="admin-badge">${groups.reduce((sum, [_, perms]) => sum + perms.length, 0)}</span>
        </div>
        <div class="permissions-accordion">
          ${groups.map(([resource, permissions]) => this.renderPermissionGroup(resource, permissions)).join('')}
        </div>
      </div>
    `;
  },

  /**
   * Render a permission group
   */
  renderPermissionGroup(resource, permissions) {
    return `
      <div class="permission-group">
        <button class="permission-group-header" data-resource="${resource}">
          <span class="permission-resource">${resource}</span>
          <span class="permission-count">${permissions.length}</span>
          <svg class="chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </button>
        <div class="permission-group-content">
          ${permissions.map(perm => `
            <div class="permission-item">
              <span class="permission-name">${perm.name}</span>
              <span class="permission-action">${perm.action}</span>
              ${perm.description ? `<span class="permission-desc">${perm.description}</span>` : ''}
            </div>
          `).join('')}
        </div>
      </div>
    `;
  },

  /**
   * Show the role editor modal
   */
  showRoleEditor(role = null) {
    const isEdit = role !== null;
    const title = isEdit ? `Edit Role: ${role.name}` : 'Create New Role';

    // Get all available permissions
    const allPermissions = [];
    for (const [resource, perms] of Object.entries(AdminState.permissionsGrouped)) {
      for (const perm of perms) {
        allPermissions.push(perm);
      }
    }

    const selectedPermissions = isEdit ? role.permissions : [];

    const modalHtml = `
      <div class="modal active" id="roleEditorModal">
        <div class="modal-content" style="max-width: 600px;">
          <div class="modal-header">
            <h3>${title}</h3>
            <button class="modal-close" id="closeRoleEditorBtn">&times;</button>
          </div>
          <div class="modal-body">
            <form id="roleEditorForm">
              <div class="form-group">
                <label for="roleName">Role Name</label>
                <input
                  type="text"
                  id="roleName"
                  class="form-control"
                  placeholder="e.g., marketing_manager"
                  pattern="^[a-z_]+$"
                  value="${isEdit ? role.name : ''}"
                  ${isEdit ? 'readonly' : ''}
                  required
                >
                <small class="form-help">Lowercase letters and underscores only</small>
              </div>
              <div class="form-group">
                <label for="roleDescription">Description</label>
                <input
                  type="text"
                  id="roleDescription"
                  class="form-control"
                  placeholder="Brief description of this role"
                  value="${isEdit ? (role.description || '') : ''}"
                  maxlength="200"
                >
              </div>
              <div class="form-group">
                <label>Permissions</label>
                <div class="permissions-selector">
                  ${Object.entries(AdminState.permissionsGrouped).map(([resource, perms]) => `
                    <div class="permission-resource-group">
                      <label class="permission-resource-label">
                        <input type="checkbox" class="resource-checkbox" data-resource="${resource}">
                        ${resource}
                      </label>
                      <div class="permission-checkboxes">
                        ${perms.map(perm => `
                          <label class="permission-checkbox">
                            <input
                              type="checkbox"
                              name="permissions"
                              value="${perm.name}"
                              ${selectedPermissions.includes(perm.name) ? 'checked' : ''}
                            >
                            ${perm.action}
                          </label>
                        `).join('')}
                      </div>
                    </div>
                  `).join('')}
                </div>
              </div>
              <div class="form-actions">
                <button type="button" class="btn btn-secondary" id="cancelRoleEditorBtn">Cancel</button>
                <button type="submit" class="btn btn-primary">
                  ${isEdit ? 'Update Role' : 'Create Role'}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);
    this.attachRoleEditorListeners(isEdit, role?.name);
  },

  /**
   * Show role permissions modal
   */
  showRolePermissions(roleName) {
    const role = AdminState.roles.find(r => r.name === roleName);
    if (!role) return;

    const modalHtml = `
      <div class="modal active" id="rolePermissionsModal">
        <div class="modal-content" style="max-width: 500px;">
          <div class="modal-header">
            <h3>Permissions for: ${role.name}</h3>
            <button class="modal-close" id="closePermissionsModalBtn">&times;</button>
          </div>
          <div class="modal-body">
            ${role.description ? `<p class="role-modal-desc">${role.description}</p>` : ''}
            <div class="permissions-list">
              ${role.permissions.length > 0
                ? role.permissions.map(perm => `
                    <div class="permission-list-item">
                      <span class="permission-name">${perm}</span>
                    </div>
                  `).join('')
                : '<p class="empty-state">No permissions assigned</p>'
              }
            </div>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);

    // Close handlers
    document.getElementById('closePermissionsModalBtn').onclick = () => {
      document.getElementById('rolePermissionsModal').remove();
    };
    document.getElementById('rolePermissionsModal').onclick = (e) => {
      if (e.target.id === 'rolePermissionsModal') {
        document.getElementById('rolePermissionsModal').remove();
      }
    };
  },

  /**
   * Show the user editor modal (create or edit)
   */
  showUserEditor(user = null) {
    const isEdit = user !== null;
    const title = isEdit ? `Edit User: ${user.email}` : 'Create New User';

    const modalHtml = `
      <div class="modal active" id="userEditorModal">
        <div class="modal-content" style="max-width: 500px;">
          <div class="modal-header">
            <h3>${title}</h3>
            <button class="modal-close" id="closeUserEditorBtn">&times;</button>
          </div>
          <div class="modal-body">
            <form id="userEditorForm">
              <div class="form-group">
                <label for="userEmail">Email</label>
                <input
                  type="email"
                  id="userEmail"
                  class="form-control"
                  placeholder="user@example.com"
                  value="${isEdit ? user.email : ''}"
                  ${isEdit ? 'readonly' : ''}
                  required
                >
              </div>
              <div class="form-group">
                <label for="userName">Name</label>
                <input
                  type="text"
                  id="userName"
                  class="form-control"
                  placeholder="Full name"
                  value="${isEdit ? (user.name || '') : ''}"
                  maxlength="100"
                >
              </div>
              ${!isEdit ? `
                <div class="form-group">
                  <label for="userPassword">Password</label>
                  <input
                    type="password"
                    id="userPassword"
                    class="form-control"
                    placeholder="Minimum 6 characters"
                    minlength="6"
                    required
                  >
                </div>
                <div class="form-group">
                  <label>Initial Roles</label>
                  <div class="roles-checkboxes">
                    ${AdminState.roles.map(role => `
                      <label class="role-checkbox">
                        <input
                          type="checkbox"
                          name="roles"
                          value="${role.name}"
                          ${role.name === 'sales:sales_person' ? 'checked' : ''}
                        >
                        ${role.name}
                      </label>
                    `).join('')}
                  </div>
                </div>
              ` : `
                <div class="form-group">
                  <label for="userActive">Status</label>
                  <select id="userActive" class="form-control">
                    <option value="true" ${user.is_active ? 'selected' : ''}>Active</option>
                    <option value="false" ${!user.is_active ? 'selected' : ''}>Inactive</option>
                  </select>
                </div>
              `}
              <div class="form-actions">
                <button type="button" class="btn btn-secondary" id="cancelUserEditorBtn">Cancel</button>
                <button type="submit" class="btn btn-primary">
                  ${isEdit ? 'Update User' : 'Create User'}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);
    this.attachUserEditorListeners(isEdit, user?.id);
  },

  /**
   * Attach event listeners to the user editor modal
   */
  attachUserEditorListeners(isEdit, userId) {
    const modal = document.getElementById('userEditorModal');
    const form = document.getElementById('userEditorForm');
    const closeBtn = document.getElementById('closeUserEditorBtn');
    const cancelBtn = document.getElementById('cancelUserEditorBtn');

    const closeModal = () => modal.remove();

    closeBtn.onclick = closeModal;
    cancelBtn.onclick = closeModal;
    modal.onclick = (e) => {
      if (e.target === modal) closeModal();
    };

    form.onsubmit = async (e) => {
      e.preventDefault();

      const email = document.getElementById('userEmail').value.trim();
      const name = document.getElementById('userName').value.trim();

      try {
        if (isEdit) {
          const isActive = document.getElementById('userActive').value === 'true';
          const updatedUser = await AdminAPI.updateUser(userId, {
            name: name || null,
            is_active: isActive,
          });
          const idx = AdminState.users.findIndex(u => u.id === userId);
          if (idx !== -1) {
            AdminState.users[idx] = updatedUser;
          }
          showToast(`User "${email}" updated`, 'success');
        } else {
          const password = document.getElementById('userPassword').value;
          const roles = Array.from(
            document.querySelectorAll('input[name="roles"]:checked')
          ).map(cb => cb.value);

          const newUser = await AdminAPI.createUser({
            email,
            name: name || null,
            password,
            roles,
          });
          AdminState.users.push(newUser);
          showToast(`User "${email}" created`, 'success');
        }

        closeModal();
        this.render();
      } catch (error) {
        showToast(error.message || 'Failed to save user', 'error');
      }
    };
  },

  /**
   * Show the role management modal for a user
   */
  showUserRolesManager(userId) {
    const user = AdminState.users.find(u => u.id === userId);
    if (!user) return;

    const modalHtml = `
      <div class="modal active" id="userRolesModal">
        <div class="modal-content" style="max-width: 500px;">
          <div class="modal-header">
            <h3>Manage Roles: ${user.email}</h3>
            <button class="modal-close" id="closeUserRolesBtn">&times;</button>
          </div>
          <div class="modal-body">
            <p class="modal-description">Select roles to assign to this user:</p>
            <div class="roles-manager">
              ${AdminState.roles.map(role => `
                <label class="role-manager-item">
                  <input
                    type="checkbox"
                    class="role-toggle"
                    data-role="${role.name}"
                    ${user.roles.includes(role.name) ? 'checked' : ''}
                  >
                  <div class="role-manager-info">
                    <span class="role-manager-name">${role.name}</span>
                    <span class="role-manager-desc">${role.description || ''}</span>
                  </div>
                </label>
              `).join('')}
            </div>
            <div class="form-actions">
              <button type="button" class="btn btn-secondary" id="closeUserRolesModalBtn">Close</button>
            </div>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);

    const modal = document.getElementById('userRolesModal');
    const closeBtn = document.getElementById('closeUserRolesBtn');
    const closeModalBtn = document.getElementById('closeUserRolesModalBtn');

    const closeModal = () => modal.remove();

    closeBtn.onclick = closeModal;
    closeModalBtn.onclick = closeModal;
    modal.onclick = (e) => {
      if (e.target === modal) closeModal();
    };

    // Handle role toggle
    document.querySelectorAll('.role-toggle').forEach(checkbox => {
      checkbox.onchange = async () => {
        const roleName = checkbox.dataset.role;
        const isChecked = checkbox.checked;

        try {
          if (isChecked) {
            await AdminAPI.assignUserRole(userId, roleName);
            user.roles.push(roleName);
            showToast(`Role "${roleName}" assigned`, 'success');
          } else {
            await AdminAPI.revokeUserRole(userId, roleName);
            user.roles = user.roles.filter(r => r !== roleName);
            showToast(`Role "${roleName}" revoked`, 'success');
          }
          // Update the main users table
          this.render();
        } catch (error) {
          // Revert checkbox state
          checkbox.checked = !isChecked;
          showToast(error.message || 'Failed to update role', 'error');
        }
      };
    });
  },

  /**
   * Attach event listeners to the admin panel
   */
  attachEventListeners() {
    // Tab switching
    document.querySelectorAll('.admin-tab').forEach(tab => {
      tab.onclick = () => {
        document.querySelectorAll('.admin-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.admin-tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById(tab.dataset.tab + 'Tab').classList.add('active');
      };
    });

    // Create user button
    const createUserBtn = document.getElementById('createUserBtn');
    if (createUserBtn) {
      createUserBtn.onclick = () => this.showUserEditor();
    }

    // Edit user buttons
    document.querySelectorAll('.edit-user-btn').forEach(btn => {
      btn.onclick = (e) => {
        e.stopPropagation();
        const userId = btn.dataset.userId;
        const user = AdminState.users.find(u => u.id === userId);
        if (user) {
          this.showUserEditor(user);
        }
      };
    });

    // Manage user roles buttons
    document.querySelectorAll('.manage-roles-btn').forEach(btn => {
      btn.onclick = (e) => {
        e.stopPropagation();
        const userId = btn.dataset.userId;
        this.showUserRolesManager(userId);
      };
    });

    // Delete user buttons
    document.querySelectorAll('.delete-user-btn').forEach(btn => {
      btn.onclick = async (e) => {
        e.stopPropagation();
        const userId = btn.dataset.userId;
        const user = AdminState.users.find(u => u.id === userId);
        if (user && confirm(`Are you sure you want to delete user "${user.email}"?`)) {
          try {
            await AdminAPI.deleteUser(userId);
            showToast(`User "${user.email}" deleted`, 'success');
            AdminState.users = AdminState.users.filter(u => u.id !== userId);
            this.render();
          } catch (error) {
            showToast(error.message || 'Failed to delete user', 'error');
          }
        }
      };
    });

    // Create role button
    const createRoleBtn = document.getElementById('createRoleBtn');
    if (createRoleBtn) {
      createRoleBtn.onclick = () => this.showRoleEditor();
    }

    // Edit role buttons
    document.querySelectorAll('.edit-role-btn').forEach(btn => {
      btn.onclick = async (e) => {
        e.stopPropagation();
        const roleName = btn.dataset.role;
        const role = AdminState.roles.find(r => r.name === roleName);
        if (role) {
          this.showRoleEditor(role);
        }
      };
    });

    // Delete role buttons
    document.querySelectorAll('.delete-role-btn').forEach(btn => {
      btn.onclick = async (e) => {
        e.stopPropagation();
        const roleName = btn.dataset.role;
        if (confirm(`Are you sure you want to delete the role "${roleName}"?`)) {
          try {
            await AdminAPI.deleteRole(roleName);
            showToast(`Role "${roleName}" deleted`, 'success');
            AdminState.roles = AdminState.roles.filter(r => r.name !== roleName);
            this.render();
          } catch (error) {
            showToast('Failed to delete role', 'error');
          }
        }
      };
    });

    // View permissions buttons
    document.querySelectorAll('.view-permissions-btn').forEach(btn => {
      btn.onclick = (e) => {
        e.stopPropagation();
        this.showRolePermissions(btn.dataset.role);
      };
    });

    // Permission group accordion
    document.querySelectorAll('.permission-group-header').forEach(header => {
      header.onclick = () => {
        const group = header.closest('.permission-group');
        group.classList.toggle('expanded');
      };
    });
  },

  /**
   * Attach event listeners to the role editor modal
   */
  attachRoleEditorListeners(isEdit, originalName) {
    const modal = document.getElementById('roleEditorModal');
    const form = document.getElementById('roleEditorForm');
    const closeBtn = document.getElementById('closeRoleEditorBtn');
    const cancelBtn = document.getElementById('cancelRoleEditorBtn');

    const closeModal = () => modal.remove();

    closeBtn.onclick = closeModal;
    cancelBtn.onclick = closeModal;
    modal.onclick = (e) => {
      if (e.target === modal) closeModal();
    };

    // Resource checkbox (select all permissions for a resource)
    document.querySelectorAll('.resource-checkbox').forEach(checkbox => {
      checkbox.onclick = () => {
        const resource = checkbox.dataset.resource;
        const perms = document.querySelectorAll(`input[name="permissions"][value^="${resource}:"]`);
        perms.forEach(perm => perm.checked = checkbox.checked);
      };
    });

    // Form submission
    form.onsubmit = async (e) => {
      e.preventDefault();

      const name = document.getElementById('roleName').value.trim();
      const description = document.getElementById('roleDescription').value.trim();
      const permissions = Array.from(
        document.querySelectorAll('input[name="permissions"]:checked')
      ).map(cb => cb.value);

      try {
        if (isEdit) {
          const updatedRole = await AdminAPI.updateRole(originalName, {
            description,
            permissions,
          });
          const idx = AdminState.roles.findIndex(r => r.name === originalName);
          if (idx !== -1) {
            AdminState.roles[idx] = updatedRole;
          }
          showToast(`Role "${name}" updated`, 'success');
        } else {
          const newRole = await AdminAPI.createRole({
            name,
            description,
            permissions,
          });
          AdminState.roles.push(newRole);
          showToast(`Role "${name}" created`, 'success');
        }

        closeModal();
        this.render();
      } catch (error) {
        showToast(error.message || 'Failed to save role', 'error');
      }
    };
  },
};

// =============================================================================
// EXPORT FOR USE IN APP.JS
// =============================================================================

window.AdminUI = AdminUI;
window.AdminAPI = AdminAPI;
window.AdminState = AdminState;

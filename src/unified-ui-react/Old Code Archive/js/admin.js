/**
 * Enterprise RBAC Admin Panel
 *
 * 4-Level Enterprise RBAC:
 * - Level 1: Profiles (base permission templates)
 * - Level 2: Permission Sets (additive permissions)
 * - Level 3: Teams & Hierarchy
 * - Level 4: Record-Level Sharing
 */

// =============================================================================
// ADMIN STATE
// =============================================================================

const AdminState = {
  // Data
  users: [],
  profiles: [],
  permissionSets: [],
  teams: [],
  sharingRules: [],
  permissions: [],
  permissionsGrouped: {},
  invites: [],
  apiKeys: [],

  // Selection state
  selectedUser: null,
  selectedProfile: null,
  selectedPermissionSet: null,
  selectedTeam: null,

  // Loading state
  isLoading: false,
};

// =============================================================================
// ADMIN API CALLS
// =============================================================================

const AdminAPI = {
  // Dashboard
  async getDashboard() {
    return await API.fetch('/api/admin/dashboard');
  },

  // =================== USERS ===================
  async getUsers(limit = 100, offset = 0) {
    return await API.fetch(`/api/admin/users?limit=${limit}&offset=${offset}`);
  },

  async getUser(userId) {
    return await API.fetch(`/api/admin/users/${userId}`);
  },

  async getUserPermissions(userId) {
    return await API.fetch(`/api/admin/users/${userId}/permissions`);
  },

  async createUser(userData) {
    return await API.fetch('/api/admin/users', {
      method: 'POST',
      body: JSON.stringify(userData),
    });
  },

  async updateUser(userId, userData) {
    return await API.fetch(`/api/admin/users/${userId}`, {
      method: 'PUT',
      body: JSON.stringify(userData),
    });
  },

  async deleteUser(userId) {
    await API.fetch(`/api/admin/users/${userId}`, { method: 'DELETE' });
  },

  async assignUserProfile(userId, profileName) {
    return await API.fetch(`/api/admin/users/${userId}/profile?profile_name=${profileName}`, {
      method: 'PUT',
    });
  },

  async setUserManager(userId, managerId) {
    const params = managerId ? `?manager_id=${managerId}` : '';
    return await API.fetch(`/api/admin/users/${userId}/manager${params}`, {
      method: 'PUT',
    });
  },

  // =================== PROFILES ===================
  async getProfiles() {
    return await API.fetch('/api/admin/profiles');
  },

  async getProfile(profileName) {
    return await API.fetch(`/api/admin/profiles/${profileName}`);
  },

  async createProfile(profileData) {
    return await API.fetch('/api/admin/profiles', {
      method: 'POST',
      body: JSON.stringify(profileData),
    });
  },

  async updateProfile(profileName, profileData) {
    return await API.fetch(`/api/admin/profiles/${profileName}`, {
      method: 'PUT',
      body: JSON.stringify(profileData),
    });
  },

  async deleteProfile(profileName) {
    await API.fetch(`/api/admin/profiles/${profileName}`, { method: 'DELETE' });
  },

  // =================== PERMISSION SETS ===================
  async getPermissionSets() {
    return await API.fetch('/api/admin/permission-sets');
  },

  async getPermissionSet(psName) {
    return await API.fetch(`/api/admin/permission-sets/${psName}`);
  },

  async createPermissionSet(psData) {
    return await API.fetch('/api/admin/permission-sets', {
      method: 'POST',
      body: JSON.stringify(psData),
    });
  },

  async updatePermissionSet(psName, psData) {
    return await API.fetch(`/api/admin/permission-sets/${psName}`, {
      method: 'PUT',
      body: JSON.stringify(psData),
    });
  },

  async deletePermissionSet(psName) {
    await API.fetch(`/api/admin/permission-sets/${psName}`, { method: 'DELETE' });
  },

  async assignUserPermissionSet(userId, psName, expiresAt = null) {
    return await API.fetch(`/api/admin/users/${userId}/permission-sets/${psName}`, {
      method: 'POST',
      body: JSON.stringify({ expires_at: expiresAt }),
    });
  },

  async revokeUserPermissionSet(userId, psName) {
    await API.fetch(`/api/admin/users/${userId}/permission-sets/${psName}`, {
      method: 'DELETE',
    });
  },

  // =================== TEAMS ===================
  async getTeams() {
    return await API.fetch('/api/admin/teams');
  },

  async getTeam(teamId) {
    return await API.fetch(`/api/admin/teams/${teamId}`);
  },

  async createTeam(teamData) {
    return await API.fetch('/api/admin/teams', {
      method: 'POST',
      body: JSON.stringify(teamData),
    });
  },

  async updateTeam(teamId, teamData) {
    return await API.fetch(`/api/admin/teams/${teamId}`, {
      method: 'PUT',
      body: JSON.stringify(teamData),
    });
  },

  async deleteTeam(teamId) {
    await API.fetch(`/api/admin/teams/${teamId}`, { method: 'DELETE' });
  },

  async getTeamMembers(teamId) {
    return await API.fetch(`/api/admin/teams/${teamId}/members`);
  },

  async addTeamMember(teamId, userId, role = 'member') {
    return await API.fetch(`/api/admin/teams/${teamId}/members`, {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, role }),
    });
  },

  async removeTeamMember(teamId, userId) {
    await API.fetch(`/api/admin/teams/${teamId}/members/${userId}`, {
      method: 'DELETE',
    });
  },

  // =================== SHARING RULES ===================
  async getSharingRules(objectType = null) {
    const params = objectType ? `?object_type=${objectType}` : '';
    return await API.fetch(`/api/admin/sharing-rules${params}`);
  },

  async createSharingRule(ruleData) {
    return await API.fetch('/api/admin/sharing-rules', {
      method: 'POST',
      body: JSON.stringify(ruleData),
    });
  },

  async deleteSharingRule(ruleId) {
    await API.fetch(`/api/admin/sharing-rules/${ruleId}`, { method: 'DELETE' });
  },

  // =================== PERMISSIONS ===================
  async getPermissions() {
    return await API.fetch('/api/admin/permissions');
  },

  async getPermissionsGrouped() {
    return await API.fetch('/api/admin/permissions/grouped');
  },

  // =================== INVITES ===================
  async getInvites(includeUsed = false) {
    return await API.fetch(`/api/base/auth/invites?include_used=${includeUsed}`);
  },

  async createInvite(inviteData) {
    return await API.fetch('/api/base/auth/invites', {
      method: 'POST',
      body: JSON.stringify(inviteData),
    });
  },

  async revokeInvite(tokenId) {
    await API.fetch(`/api/base/auth/invites/${tokenId}`, { method: 'DELETE' });
  },

  // =================== API KEYS ===================
  async getApiKeys(includeInactive = false) {
    return await API.fetch(`/api/admin/api-keys?include_inactive=${includeInactive}`);
  },

  async createApiKey(keyData) {
    return await API.fetch('/api/admin/api-keys', {
      method: 'POST',
      body: JSON.stringify(keyData),
    });
  },

  async rotateApiKey(keyId) {
    return await API.fetch(`/api/admin/api-keys/${keyId}/rotate`, { method: 'POST' });
  },

  async deleteApiKey(keyId) {
    await API.fetch(`/api/admin/api-keys/${keyId}`, { method: 'DELETE' });
  },

  async deactivateApiKey(keyId) {
    return await API.fetch(`/api/admin/api-keys/${keyId}/deactivate`, { method: 'POST' });
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
    console.log('[Admin] Initializing enterprise RBAC admin panel');

    // Check admin permission
    const hasAdmin = Auth?.hasPermission?.('core:system:admin') || Auth?.hasPermission?.('core:*:*');
    if (!hasAdmin) {
      console.log('[Admin] User does not have admin permissions');
      return false;
    }

    try {
      AdminState.isLoading = true;

      // Load initial data in parallel
      const [users, profiles, permissionSets, teams, sharingRules, permissionsGrouped, invites] = await Promise.all([
        AdminAPI.getUsers().catch(() => []),
        AdminAPI.getProfiles().catch(() => []),
        [],//AdminAPI.getPermissionSets().catch(() => []),
        AdminAPI.getTeams().catch(() => []),
        [],//AdminAPI.getSharingRules().catch(() => []),
        [],//AdminAPI.getPermissionsGrouped().catch(() => ({})),
        [],//AdminAPI.getInvites().catch(() => []),
      ]);

      AdminState.users = users.users;
      AdminState.profiles = profiles.profiles;
      AdminState.permissionSets = permissionSets;
      AdminState.teams = teams.teams;
      AdminState.sharingRules = sharingRules;
      AdminState.permissionsGrouped = permissionsGrouped;
      AdminState.invites = invites;

      console.log('[Admin] Loaded:', {
        users: users.users.length,
        profiles: profiles.profiles.length,
        permissionSets: permissionSets.length,
        teams: teams.teams.length,
        sharingRules: sharingRules.length,
      });

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
   * Render the admin panel
   */
  render() {
    const container = document.getElementById('adminPanel');
    if (!container) return;

    container.innerHTML = `
      <div class="admin-container">
        <div class="admin-header">
          <h2>Enterprise RBAC Admin</h2>
          <p class="admin-subtitle">Manage profiles, permissions, teams, and access control</p>
        </div>

        <div class="admin-tabs">
          <button class="admin-tab active" data-tab="users">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
              <circle cx="9" cy="7" r="4"/>
              <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
              <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
            <span class="label">Users</span>
          </button>
          <button class="admin-tab" data-tab="profiles">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
            <span class="label">Profiles</span>
          </button>
          <button class="admin-tab" data-tab="permissionSets">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
            <span class="label">Permission Sets</span>
          </button>
          <button class="admin-tab" data-tab="teams">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
              <circle cx="9" cy="7" r="4"/>
              <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
              <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
            <span class="label">Teams</span>
          </button>
          <button class="admin-tab" data-tab="sharingRules">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="18" cy="5" r="3"/>
              <circle cx="6" cy="12" r="3"/>
              <circle cx="18" cy="19" r="3"/>
              <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>
              <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
            </svg>
            <span class="label">Sharing Rules</span>
          </button>
          <button class="admin-tab" data-tab="invites">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M22 2L11 13"/>
              <path d="M22 2L15 22L11 13L2 9L22 2Z"/>
            </svg>
            <span class="label">Invites</span>
          </button>
        </div>

        <div class="admin-content">
          <div class="admin-tab-content active" id="usersTab">
            ${this.renderUsersTab()}
          </div>
          <div class="admin-tab-content" id="profilesTab">
            ${this.renderProfilesTab()}
          </div>
          <div class="admin-tab-content" id="permissionSetsTab">
            ${this.renderPermissionSetsTab()}
          </div>
          <div class="admin-tab-content" id="teamsTab">
            ${this.renderTeamsTab()}
          </div>
          <div class="admin-tab-content" id="sharingRulesTab">
            ${this.renderSharingRulesTab()}
          </div>
          <div class="admin-tab-content" id="invitesTab">
            ${this.renderInvitesTab()}
          </div>
        </div>
      </div>
    `;

    this.attachEventListeners();
  },

  // ===========================================
  // USERS TAB
  // ===========================================
  renderUsersTab() {
    return `
      <div class="admin-section">
        <div class="admin-section-header">
          <h3>User Management</h3>
          <span class="admin-badge">${AdminState.users.length}</span>
        </div>
        <p class="section-description">Manage user profiles and permission sets. Each user has one profile (base permissions) and can have multiple permission sets (additive permissions).</p>
        <div class="users-table-container">
          <table class="admin-table">
            <thead>
              <tr>
                <th>User</th>
                <th>Email</th>
                <th>Profile</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${AdminState.users.length > 0
                ? AdminState.users.map(user => this.renderUserRow(user)).join('')
                : '<tr><td colspan="5" class="empty-state">No users found. Use the Invites tab to invite new users.</td></tr>'
              }
            </tbody>
          </table>
        </div>
      </div>
    `;
  },

  renderUserRow(user) {
    const statusClass = user.is_active ? 'status-active' : 'status-inactive';
    const statusText = user.is_active ? 'Active' : 'Inactive';
    const profile = user.profile || 'No profile';
    /*
    <div class="user-avatar">
            ${user.name ? user.name.charAt(0).toUpperCase() : user.email.charAt(0).toUpperCase()}
          </div>
    */
    return `
      <tr class="user-row" data-user-id="${user.id}">
        <td class="user-cell user-name" data-label="User">${user.name || 'No name'}
        </td>
        <td class="user-email" data-label="Email">${user.email}</td>
        <td data-label="Profile">
          <span class="profile-tag ${user.profile === 'system_admin' ? 'profile-admin' : ''}">${profile}</span>
        </td>
        <td data-label="Status">
          <span class="status-badge ${statusClass}">${statusText}</span>
        </td>
        <td class="user-actions" data-label="Actions">
          <button class="btn-icon view-user-perms-btn" title="View permissions" data-user-id="${user.id}">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
              <circle cx="12" cy="12" r="3"/>
            </svg>
          </button>
          <button class="btn-icon edit-user-btn" title="Edit user" data-user-id="${user.id}">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
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

  // ===========================================
  // PROFILES TAB
  // ===========================================
  renderProfilesTab() {
    const systemProfiles = AdminState.profiles.filter(p => p.is_system);
    const customProfiles = AdminState.profiles.filter(p => !p.is_system);

    return `
      <div class="admin-section">
        <div class="admin-section-header">
          <h3>System Profiles</h3>
          <span class="admin-badge">${systemProfiles.length}</span>
        </div>
        <p class="section-description">System profiles are built-in and cannot be modified. Each user is assigned exactly one profile.</p>
        <div class="profiles-grid">
          ${systemProfiles.map(profile => this.renderProfileCard(profile)).join('')}
        </div>
      </div>

      <div class="admin-section">
        <div class="admin-section-header">
          <h3>Custom Profiles</h3>
          <span class="admin-badge">${customProfiles.length}</span>
          <button class="btn btn-primary btn-sm" id="createProfileBtn">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            New Profile
          </button>
        </div>
        <div class="profiles-grid">
          ${customProfiles.length > 0
            ? customProfiles.map(profile => this.renderProfileCard(profile)).join('')
            : '<p class="empty-state">No custom profiles yet. Create one to define custom permission sets.</p>'
          }
        </div>
      </div>
    `;
  },

  renderProfileCard(profile) {
    //const permissionCount = profile.permissions.length;
    const isSystem = profile.is_system;

    return `
      <div class="profile-card ${isSystem ? 'profile-system' : ''}" data-profile="${profile.name}">
        <div class="profile-card-header">
          <div class="profile-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
          </div>
          <div class="profile-info">
            <h4 class="profile-name">${profile.display_name || profile.name}</h4>
            ${isSystem ? '<span class="profile-badge system">System</span>' : ''}
          </div>
          ${!isSystem ? `
            <div class="profile-actions">
              <button class="btn-icon edit-profile-btn" title="Edit profile" data-profile="${profile.name}">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
              <button class="btn-icon delete-profile-btn" title="Delete profile" data-profile="${profile.name}">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="3 6 5 6 21 6"/>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                </svg>
              </button>
            </div>
          ` : ''}
        </div>
        <p class="profile-description">${profile.description || 'No description'}</p>
        
      </div>
    `;
  },
/*
<div class="profile-permissions">
          <span class="permissions-count">${permissionCount} permission${permissionCount !== 1 ? 's' : ''}</span>
          <button class="btn-link view-profile-perms-btn" data-profile="${profile.name}">View</button>
        </div>
*/
  // ===========================================
  // PERMISSION SETS TAB
  // ===========================================
  renderPermissionSetsTab() {
    return `
      <div class="admin-section">
        <div class="admin-section-header">
          <h3>Permission Sets</h3>
          <span class="admin-badge">${AdminState.permissionSets.length}</span>
          <button class="btn btn-primary btn-sm" id="createPermissionSetBtn">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            New Permission Set
          </button>
        </div>
        <p class="section-description">Permission sets grant additional permissions on top of a user's profile. Users can have multiple permission sets.</p>
        <div class="permission-sets-grid">
          ${AdminState.permissionSets.length > 0
            ? AdminState.permissionSets.map(ps => this.renderPermissionSetCard(ps)).join('')
            : '<p class="empty-state">No permission sets yet. Create one to define reusable permission bundles.</p>'
          }
        </div>
      </div>
    `;
  },

  renderPermissionSetCard(ps) {
    const permissionCount = ps.permissions.length;
    const statusClass = ps.is_active ? 'status-active' : 'status-inactive';

    return `
      <div class="permission-set-card ${!ps.is_active ? 'inactive' : ''}" data-ps="${ps.name}">
        <div class="ps-card-header">
          <div class="ps-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
          </div>
          <div class="ps-info">
            <h4 class="ps-name">${ps.display_name || ps.name}</h4>
            <span class="status-badge ${statusClass}">${ps.is_active ? 'Active' : 'Inactive'}</span>
          </div>
          <div class="ps-actions">
            <button class="btn-icon assign-ps-btn" title="Assign to user" data-ps="${ps.name}">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                <circle cx="8.5" cy="7" r="4"/>
                <line x1="20" y1="8" x2="20" y2="14"/>
                <line x1="23" y1="11" x2="17" y2="11"/>
              </svg>
            </button>
            <button class="btn-icon edit-ps-btn" title="Edit" data-ps="${ps.name}">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
              </svg>
            </button>
            <button class="btn-icon delete-ps-btn" title="Delete" data-ps="${ps.name}">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              </svg>
            </button>
          </div>
        </div>
        <p class="ps-description">${ps.description || 'No description'}</p>
        <div class="ps-permissions">
          <span class="permissions-count">${permissionCount} permission${permissionCount !== 1 ? 's' : ''}</span>
          <button class="btn-link view-ps-perms-btn" data-ps="${ps.name}">View</button>
        </div>
      </div>
    `;
  },

  // ===========================================
  // TEAMS TAB
  // ===========================================
  renderTeamsTab() {
    return `
      <div class="admin-section">
        <div class="admin-section-header">
          <h3>Teams</h3>
          <span class="admin-badge">${AdminState.teams.length}</span>
          <button class="btn btn-primary btn-sm" id="createTeamBtn">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            New Team
          </button>
        </div>
        <p class="section-description">Teams allow grouping users for shared access and hierarchy. Team members can be designated as leaders or members.</p>
        <div class="teams-grid">
          ${AdminState.teams.length > 0
            ? AdminState.teams.map(team => this.renderTeamCard(team)).join('')
            : '<p class="empty-state">No teams yet. Create one to group users together.</p>'
          }
        </div>
      </div>
    `;
  },

  renderTeamCard(team) {
    const statusClass = team.is_active ? 'status-active' : 'status-inactive';
    const parentTeam = team.parent_team_id
      ? AdminState.teams.find(t => t.id === team.parent_team_id)?.name
      : null;

    return `
      <div class="team-card ${!team.is_active ? 'inactive' : ''}" data-team-id="${team.id}">
        <div class="team-card-header">
          <div class="team-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
              <circle cx="9" cy="7" r="4"/>
              <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
              <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
          </div>
          <div class="team-info">
            <h4 class="team-name">${team.display_name || team.name}</h4>
            <span class="status-badge ${statusClass}">${team.is_active ? 'Active' : 'Inactive'}</span>
          </div>
          <div class="team-actions">
            <button class="btn-icon view-team-members-btn" title="View members" data-team-id="${team.id}">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                <circle cx="9" cy="7" r="4"/>
              </svg>
            </button>
            <button class="btn-icon edit-team-btn" title="Edit" data-team-id="${team.id}">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
              </svg>
            </button>
            <button class="btn-icon delete-team-btn" title="Delete" data-team-id="${team.id}">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              </svg>
            </button>
          </div>
        </div>
        <p class="team-description">${team.description || 'No description'}</p>
        ${parentTeam ? `<p class="team-parent">Parent: ${parentTeam}</p>` : ''}
      </div>
    `;
  },

  // ===========================================
  // SHARING RULES TAB
  // ===========================================
  renderSharingRulesTab() {
    return `
      <div class="admin-section">
        <div class="admin-section-header">
          <h3>Sharing Rules</h3>
          <span class="admin-badge">${AdminState.sharingRules.length}</span>
          <button class="btn btn-primary btn-sm" id="createSharingRuleBtn">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            New Sharing Rule
          </button>
        </div>
        <p class="section-description">Sharing rules define automatic record-level access based on profiles, teams, or ownership.</p>
        <div class="sharing-rules-table-container">
          <table class="admin-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Object</th>
                <th>From</th>
                <th>To</th>
                <th>Access</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${AdminState.sharingRules.length > 0
                ? AdminState.sharingRules.map(rule => this.renderSharingRuleRow(rule)).join('')
                : '<tr><td colspan="6" class="empty-state">No sharing rules yet. Create one to define automatic record sharing.</td></tr>'
              }
            </tbody>
          </table>
        </div>
      </div>
    `;
  },

  renderSharingRuleRow(rule) {
    const accessColors = {
      'read': 'access-read',
      'read_write': 'access-write',
      'full': 'access-full',
    };

    return `
      <tr class="sharing-rule-row" data-rule-id="${rule.id}">
        <td>
          <strong>${rule.name}</strong>
          ${rule.description ? `<br><small>${rule.description}</small>` : ''}
        </td>
        <td><span class="object-tag">${rule.object_type}</span></td>
        <td>${rule.share_from_type}${rule.share_from_id ? `: ${rule.share_from_id}` : ''}</td>
        <td>${rule.share_to_type}${rule.share_to_id ? `: ${rule.share_to_id}` : ''}</td>
        <td><span class="access-badge ${accessColors[rule.access_level] || ''}">${rule.access_level}</span></td>
        <td class="rule-actions">
          <button class="btn-icon delete-rule-btn" title="Delete" data-rule-id="${rule.id}">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
          </button>
        </td>
      </tr>
    `;
  },

  // ===========================================
  // INVITES TAB
  // ===========================================
  renderInvitesTab() {
    const pendingInvites = AdminState.invites.filter(i => !i.is_used && !i.is_revoked);
    const usedInvites = AdminState.invites.filter(i => i.is_used);

    return `
      <div class="admin-section">
        <div class="admin-section-header">
          <h3>Invite Tokens</h3>
          <span class="admin-badge">${pendingInvites.length} pending</span>
          <button class="btn btn-primary btn-sm" id="createInviteBtn">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            New Invite
          </button>
        </div>
        <p class="section-description">Create invite tokens for new users. Each token is tied to an email and profile.</p>
        <div class="invites-table-container">
          <table class="admin-table">
            <thead>
              <tr>
                <th>Email</th>
                <th>Profile</th>
                <th>Token</th>
                <th>Expires</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${pendingInvites.length > 0
                ? pendingInvites.map(invite => this.renderInviteRow(invite)).join('')
                : '<tr><td colspan="6" class="empty-state">No pending invites. Create one to invite a new user.</td></tr>'
              }
            </tbody>
          </table>
        </div>
      </div>
      ${usedInvites.length > 0 ? `
        <div class="admin-section">
          <div class="admin-section-header">
            <h3>Used Invites</h3>
            <span class="admin-badge secondary">${usedInvites.length}</span>
          </div>
          <div class="invites-table-container">
            <table class="admin-table">
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Profile</th>
                  <th>Used</th>
                </tr>
              </thead>
              <tbody>
                ${usedInvites.map(invite => `
                  <tr class="invite-row used">
                    <td>${invite.email}</td>
                    <td><span class="profile-tag">${invite.profile_name}</span></td>
                    <td>${new Date(invite.created_at).toLocaleDateString()}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      ` : ''}
    `;
  },

  renderInviteRow(invite) {
    const expiresAt = new Date(invite.expires_at);
    const isExpired = expiresAt < new Date();
    const statusClass = invite.is_revoked ? 'status-revoked' : (isExpired ? 'status-expired' : 'status-pending');
    const statusText = invite.is_revoked ? 'Revoked' : (isExpired ? 'Expired' : 'Pending');

    return `
      <tr class="invite-row" data-invite-id="${invite.id}">
        <td class="invite-email">${invite.email}</td>
        <td><span class="profile-tag">${invite.profile_name}</span></td>
        <td class="invite-token">
          <code class="token-display">${invite.token || '--------'}</code>
          ${invite.token ? `
            <button class="btn-icon copy-token-btn" title="Copy token" data-token="${invite.token}">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
              </svg>
            </button>
          ` : ''}
        </td>
        <td class="invite-expires">${expiresAt.toLocaleDateString()}</td>
        <td>
          <span class="status-badge ${statusClass}">${statusText}</span>
        </td>
        <td class="invite-actions">
          ${!invite.is_revoked && !isExpired ? `
            <button class="btn-icon revoke-invite-btn" title="Revoke invite" data-invite-id="${invite.id}">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="15" y1="9" x2="9" y2="15"/>
                <line x1="9" y1="9" x2="15" y2="15"/>
              </svg>
            </button>
          ` : ''}
        </td>
      </tr>
    `;
  },

  // ===========================================
  // MODALS
  // ===========================================

  /**
   * Show user permissions modal
   */
  async showUserPermissions(userId) {
    try {
      const permInfo = await AdminAPI.getUserPermissions(userId);
      const user = AdminState.users.find(u => u.id === userId);

      const modalHtml = `
        <div class="modal active" id="userPermissionsModal">
          <div class="modal-content" style="max-width: 600px;">
            <div class="modal-header">
              <h3>Permissions: ${user?.email || userId}</h3>
              <button class="modal-close" id="closeUserPermissionsBtn">&times;</button>
            </div>
            <div class="modal-body">
              <div class="user-perm-section">
                <h4>Profile</h4>
                <span class="profile-tag large">${permInfo.profile || 'No profile assigned'}</span>
              </div>
              <div class="user-perm-section">
                <h4>Permission Sets</h4>
                ${permInfo.permission_sets.length > 0
                  ? permInfo.permission_sets.map(ps => `<span class="ps-tag">${ps}</span>`).join(' ')
                  : '<span class="no-data">No permission sets assigned</span>'
                }
              </div>
              <div class="user-perm-section">
                <h4>Effective Permissions (${permInfo.permissions.length})</h4>
                <div class="permissions-list">
                  ${permInfo.permissions.length > 0
                    ? permInfo.permissions.map(p => `<div class="permission-item"><code>${p}</code></div>`).join('')
                    : '<span class="no-data">No permissions</span>'
                  }
                </div>
              </div>
            </div>
          </div>
        </div>
      `;

      document.body.insertAdjacentHTML('beforeend', modalHtml);
      document.getElementById('closeUserPermissionsBtn').onclick = () => {
        document.getElementById('userPermissionsModal').remove();
      };
      document.getElementById('userPermissionsModal').onclick = (e) => {
        if (e.target.id === 'userPermissionsModal') {
          document.getElementById('userPermissionsModal').remove();
        }
      };
    } catch (error) {
      showToast('Failed to load user permissions', 'error');
    }
  },

  /**
   * Show user editor modal
   */
  showUserEditor(user) {
    const profileOptions = AdminState.profiles.map(p =>
      `<option value="${p.name}" ${user.profile === p.name ? 'selected' : ''}>${p.display_name || p.name}</option>`
    ).join('');

    const modalHtml = `
      <div class="modal active" id="userEditorModal">
        <div class="modal-content" style="max-width: 500px;">
          <div class="modal-header">
            <h3>Edit User: ${user.email}</h3>
            <button class="modal-close" id="closeUserEditorBtn">&times;</button>
          </div>
          <div class="modal-body">
            <form id="userEditorForm">
              <div class="form-group">
                <label for="userName">Name</label>
                <input type="text" id="userName" class="form-control" value="${user.name || ''}" maxlength="100">
              </div>
              <div class="form-group">
                <label for="userProfile">Profile</label>
                <select id="userProfile" class="form-control">
                  ${profileOptions}
                </select>
                <small class="form-help">The user's base permission template</small>
              </div>
              <div class="form-group">
                <label for="userActive">Status</label>
                <select id="userActive" class="form-control">
                  <option value="true" ${user.is_active ? 'selected' : ''}>Active</option>
                  <option value="false" ${!user.is_active ? 'selected' : ''}>Inactive</option>
                </select>
              </div>
              <div class="form-actions">
                <button type="button" class="btn btn-secondary" id="cancelUserEditorBtn">Cancel</button>
                <button type="submit" class="btn btn-primary">Save Changes</button>
              </div>
            </form>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);

    const modal = document.getElementById('userEditorModal');
    const closeModal = () => modal.remove();

    document.getElementById('closeUserEditorBtn').onclick = closeModal;
    document.getElementById('cancelUserEditorBtn').onclick = closeModal;
    modal.onclick = (e) => { if (e.target === modal) closeModal(); };

    document.getElementById('userEditorForm').onsubmit = async (e) => {
      e.preventDefault();
      const name = document.getElementById('userName').value.trim();
      const profile = document.getElementById('userProfile').value;
      const isActive = document.getElementById('userActive').value === 'true';

      try {
        // Update user info
        await AdminAPI.updateUser(user.id, { name: name || null, is_active: isActive });

        // Update profile if changed
        if (profile !== user.profile) {
          await AdminAPI.assignUserProfile(user.id, profile);
        }

        showToast('User updated successfully', 'success');
        closeModal();

        // Refresh users
        AdminState.users = await AdminAPI.getUsers();
        this.render();
      } catch (error) {
        showToast(error.message || 'Failed to update user', 'error');
      }
    };
  },

  /**
   * Show profile permissions
   */
  showProfilePermissions(profileName) {
    const profile = AdminState.profiles.find(p => p.name === profileName);
    if (!profile) return;

    const modalHtml = `
      <div class="modal active" id="profilePermsModal">
        <div class="modal-content" style="max-width: 500px;">
          <div class="modal-header">
            <h3>Permissions: ${profile.display_name || profile.name}</h3>
            <button class="modal-close" id="closeProfilePermsBtn">&times;</button>
          </div>
          <div class="modal-body">
            ${profile.description ? `<p class="modal-description">${profile.description}</p>` : ''}
            <div class="permissions-list">
              ${profile.permissions.length > 0
                ? profile.permissions.map(p => `<div class="permission-item"><code>${p}</code></div>`).join('')
                : '<p class="empty-state">No permissions assigned</p>'
              }
            </div>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);
    document.getElementById('closeProfilePermsBtn').onclick = () => {
      document.getElementById('profilePermsModal').remove();
    };
    document.getElementById('profilePermsModal').onclick = (e) => {
      if (e.target.id === 'profilePermsModal') {
        document.getElementById('profilePermsModal').remove();
      }
    };
  },

  /**
   * Show permission set permissions
   */
  showPermissionSetPermissions(ps) {
    const modalHtml = `
      <div class="modal active" id="psPermsModal">
        <div class="modal-content" style="max-width: 500px;">
          <div class="modal-header">
            <h3>Permissions: ${ps.display_name || ps.name}</h3>
            <button class="modal-close" id="closePsPermsBtn">&times;</button>
          </div>
          <div class="modal-body">
            ${ps.description ? `<p class="modal-description">${ps.description}</p>` : ''}
            <div class="permissions-list">
              ${ps.permissions.length > 0
                ? ps.permissions.map(p => `<div class="permission-item"><code>${p}</code></div>`).join('')
                : '<p class="empty-state">No permissions assigned</p>'
              }
            </div>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);
    document.getElementById('closePsPermsBtn').onclick = () => {
      document.getElementById('psPermsModal').remove();
    };
    document.getElementById('psPermsModal').onclick = (e) => {
      if (e.target.id === 'psPermsModal') {
        document.getElementById('psPermsModal').remove();
      }
    };
  },

  /**
   * Show profile editor modal
   */
  showProfileEditor(profile = null) {
    const isEdit = profile !== null;
    const title = isEdit ? `Edit Profile: ${profile.name}` : 'Create New Profile';
    const selectedPermissions = isEdit ? profile.permissions : [];

    const modalHtml = `
      <div class="modal active" id="profileEditorModal">
        <div class="modal-content" style="max-width: 700px;">
          <div class="modal-header">
            <h3>${title}</h3>
            <button class="modal-close" id="closeProfileEditorBtn">&times;</button>
          </div>
          <div class="modal-body">
            <form id="profileEditorForm">
              <div class="form-row">
                <div class="form-group">
                  <label for="profileName">Name</label>
                  <input type="text" id="profileName" class="form-control"
                    placeholder="e.g., marketing_manager" pattern="^[a-z_]+$"
                    value="${isEdit ? profile.name : ''}" ${isEdit ? 'readonly' : ''} required>
                  <small class="form-help">Lowercase letters and underscores only</small>
                </div>
                <div class="form-group">
                  <label for="profileDisplayName">Display Name</label>
                  <input type="text" id="profileDisplayName" class="form-control"
                    placeholder="e.g., Marketing Manager"
                    value="${isEdit ? (profile.display_name || '') : ''}" required>
                </div>
              </div>
              <div class="form-group">
                <label for="profileDescription">Description</label>
                <input type="text" id="profileDescription" class="form-control"
                  placeholder="Brief description of this profile"
                  value="${isEdit ? (profile.description || '') : ''}" maxlength="500">
              </div>
              <div class="form-group">
                <label>Permissions</label>
                <div class="permissions-selector">
                  ${Object.entries(AdminState.permissionsGrouped).map(([resource, perms]) => `
                    <div class="permission-resource-group">
                      <label class="permission-resource-label">
                        <input type="checkbox" class="resource-checkbox" data-resource="${resource}">
                        <strong>${resource}</strong>
                      </label>
                      <div class="permission-checkboxes">
                        ${perms.map(perm => `
                          <label class="permission-checkbox">
                            <input type="checkbox" name="permissions" value="${perm.name}"
                              ${selectedPermissions.includes(perm.name) ? 'checked' : ''}>
                            ${perm.action}
                          </label>
                        `).join('')}
                      </div>
                    </div>
                  `).join('')}
                </div>
              </div>
              <div class="form-actions">
                <button type="button" class="btn btn-secondary" id="cancelProfileEditorBtn">Cancel</button>
                <button type="submit" class="btn btn-primary">${isEdit ? 'Update Profile' : 'Create Profile'}</button>
              </div>
            </form>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);

    const modal = document.getElementById('profileEditorModal');
    const closeModal = () => modal.remove();

    document.getElementById('closeProfileEditorBtn').onclick = closeModal;
    document.getElementById('cancelProfileEditorBtn').onclick = closeModal;
    modal.onclick = (e) => { if (e.target === modal) closeModal(); };

    // Resource checkbox toggles all permissions in group
    document.querySelectorAll('.resource-checkbox').forEach(cb => {
      cb.onclick = () => {
        const resource = cb.dataset.resource;
        const perms = document.querySelectorAll(`input[name="permissions"][value^="${resource}:"]`);
        perms.forEach(p => p.checked = cb.checked);
      };
    });

    document.getElementById('profileEditorForm').onsubmit = async (e) => {
      e.preventDefault();
      const name = document.getElementById('profileName').value.trim();
      const displayName = document.getElementById('profileDisplayName').value.trim();
      const description = document.getElementById('profileDescription').value.trim();
      const permissions = Array.from(document.querySelectorAll('input[name="permissions"]:checked')).map(cb => cb.value);

      try {
        if (isEdit) {
          await AdminAPI.updateProfile(profile.name, { display_name: displayName, description, permissions });
          showToast('Profile updated successfully', 'success');
        } else {
          await AdminAPI.createProfile({ name, display_name: displayName, description, permissions });
          showToast('Profile created successfully', 'success');
        }
        closeModal();
        AdminState.profiles = await AdminAPI.getProfiles();
        this.render();
      } catch (error) {
        showToast(error.message || 'Failed to save profile', 'error');
      }
    };
  },

  /**
   * Show permission set editor modal
   */
  showPermissionSetEditor(ps = null) {
    const isEdit = ps !== null;
    const title = isEdit ? `Edit Permission Set: ${ps.name}` : 'Create New Permission Set';
    const selectedPermissions = isEdit ? ps.permissions : [];

    const modalHtml = `
      <div class="modal active" id="psEditorModal">
        <div class="modal-content" style="max-width: 700px;">
          <div class="modal-header">
            <h3>${title}</h3>
            <button class="modal-close" id="closePsEditorBtn">&times;</button>
          </div>
          <div class="modal-body">
            <form id="psEditorForm">
              <div class="form-row">
                <div class="form-group">
                  <label for="psName">Name</label>
                  <input type="text" id="psName" class="form-control"
                    placeholder="e.g., export_data" pattern="^[a-z_]+$"
                    value="${isEdit ? ps.name : ''}" ${isEdit ? 'readonly' : ''} required>
                </div>
                <div class="form-group">
                  <label for="psDisplayName">Display Name</label>
                  <input type="text" id="psDisplayName" class="form-control"
                    placeholder="e.g., Export Data"
                    value="${isEdit ? (ps.display_name || '') : ''}" required>
                </div>
              </div>
              <div class="form-group">
                <label for="psDescription">Description</label>
                <input type="text" id="psDescription" class="form-control"
                  placeholder="Brief description"
                  value="${isEdit ? (ps.description || '') : ''}" maxlength="500">
              </div>
              ${isEdit ? `
                <div class="form-group">
                  <label for="psActive">Status</label>
                  <select id="psActive" class="form-control">
                    <option value="true" ${ps.is_active ? 'selected' : ''}>Active</option>
                    <option value="false" ${!ps.is_active ? 'selected' : ''}>Inactive</option>
                  </select>
                </div>
              ` : ''}
              <div class="form-group">
                <label>Permissions</label>
                <div class="permissions-selector">
                  ${Object.entries(AdminState.permissionsGrouped).map(([resource, perms]) => `
                    <div class="permission-resource-group">
                      <label class="permission-resource-label">
                        <input type="checkbox" class="resource-checkbox" data-resource="${resource}">
                        <strong>${resource}</strong>
                      </label>
                      <div class="permission-checkboxes">
                        ${perms.map(perm => `
                          <label class="permission-checkbox">
                            <input type="checkbox" name="permissions" value="${perm.name}"
                              ${selectedPermissions.includes(perm.name) ? 'checked' : ''}>
                            ${perm.action}
                          </label>
                        `).join('')}
                      </div>
                    </div>
                  `).join('')}
                </div>
              </div>
              <div class="form-actions">
                <button type="button" class="btn btn-secondary" id="cancelPsEditorBtn">Cancel</button>
                <button type="submit" class="btn btn-primary">${isEdit ? 'Update' : 'Create'}</button>
              </div>
            </form>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);

    const modal = document.getElementById('psEditorModal');
    const closeModal = () => modal.remove();

    document.getElementById('closePsEditorBtn').onclick = closeModal;
    document.getElementById('cancelPsEditorBtn').onclick = closeModal;
    modal.onclick = (e) => { if (e.target === modal) closeModal(); };

    document.querySelectorAll('.resource-checkbox').forEach(cb => {
      cb.onclick = () => {
        const resource = cb.dataset.resource;
        const perms = document.querySelectorAll(`input[name="permissions"][value^="${resource}:"]`);
        perms.forEach(p => p.checked = cb.checked);
      };
    });

    document.getElementById('psEditorForm').onsubmit = async (e) => {
      e.preventDefault();
      const name = document.getElementById('psName').value.trim();
      const displayName = document.getElementById('psDisplayName').value.trim();
      const description = document.getElementById('psDescription').value.trim();
      const permissions = Array.from(document.querySelectorAll('input[name="permissions"]:checked')).map(cb => cb.value);
      const isActive = isEdit ? document.getElementById('psActive').value === 'true' : true;

      try {
        if (isEdit) {
          await AdminAPI.updatePermissionSet(ps.name, { display_name: displayName, description, permissions, is_active: isActive });
          showToast('Permission set updated', 'success');
        } else {
          await AdminAPI.createPermissionSet({ name, display_name: displayName, description, permissions });
          showToast('Permission set created', 'success');
        }
        closeModal();
        AdminState.permissionSets = await AdminAPI.getPermissionSets();
        this.render();
      } catch (error) {
        showToast(error.message || 'Failed to save permission set', 'error');
      }
    };
  },

  /**
   * Show permission set assignment modal
   */
  showAssignPermissionSet(psName) {
    const modalHtml = `
      <div class="modal active" id="assignPsModal">
        <div class="modal-content" style="max-width: 500px;">
          <div class="modal-header">
            <h3>Assign Permission Set: ${psName}</h3>
            <button class="modal-close" id="closeAssignPsBtn">&times;</button>
          </div>
          <div class="modal-body">
            <form id="assignPsForm">
              <div class="form-group">
                <label for="assignPsUser">Select User</label>
                <select id="assignPsUser" class="form-control" required>
                  <option value="">Choose a user...</option>
                  ${AdminState.users.map(u => `<option value="${u.id}">${u.email} (${u.name || 'No name'})</option>`).join('')}
                </select>
              </div>
              <div class="form-group">
                <label for="assignPsExpiry">Expires (optional)</label>
                <input type="datetime-local" id="assignPsExpiry" class="form-control">
                <small class="form-help">Leave empty for permanent assignment</small>
              </div>
              <div class="form-actions">
                <button type="button" class="btn btn-secondary" id="cancelAssignPsBtn">Cancel</button>
                <button type="submit" class="btn btn-primary">Assign</button>
              </div>
            </form>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);

    const modal = document.getElementById('assignPsModal');
    const closeModal = () => modal.remove();

    document.getElementById('closeAssignPsBtn').onclick = closeModal;
    document.getElementById('cancelAssignPsBtn').onclick = closeModal;
    modal.onclick = (e) => { if (e.target === modal) closeModal(); };

    document.getElementById('assignPsForm').onsubmit = async (e) => {
      e.preventDefault();
      const userId = document.getElementById('assignPsUser').value;
      const expiresAt = document.getElementById('assignPsExpiry').value || null;

      try {
        await AdminAPI.assignUserPermissionSet(userId, psName, expiresAt);
        showToast(`Permission set assigned`, 'success');
        closeModal();
      } catch (error) {
        showToast(error.message || 'Failed to assign permission set', 'error');
      }
    };
  },

  /**
   * Show team editor modal
   */
  showTeamEditor(team = null) {
    const isEdit = team !== null;
    const title = isEdit ? `Edit Team: ${team.name}` : 'Create New Team';
    const parentOptions = AdminState.teams
      .filter(t => !isEdit || t.id !== team.id)
      .map(t => `<option value="${t.id}" ${isEdit && team.parent_team_id === t.id ? 'selected' : ''}>${t.name}</option>`)
      .join('');

    const modalHtml = `
      <div class="modal active" id="teamEditorModal">
        <div class="modal-content" style="max-width: 500px;">
          <div class="modal-header">
            <h3>${title}</h3>
            <button class="modal-close" id="closeTeamEditorBtn">&times;</button>
          </div>
          <div class="modal-body">
            <form id="teamEditorForm">
              <div class="form-group">
                <label for="teamName">Name</label>
                <input type="text" id="teamName" class="form-control" placeholder="e.g., Sales Team"
                  value="${isEdit ? team.name : ''}" required>
              </div>
              <div class="form-group">
                <label for="teamDisplayName">Display Name</label>
                <input type="text" id="teamDisplayName" class="form-control" placeholder="e.g., Sales Team"
                  value="${isEdit ? (team.display_name || '') : ''}">
              </div>
              <div class="form-group">
                <label for="teamDescription">Description</label>
                <input type="text" id="teamDescription" class="form-control" placeholder="Brief description"
                  value="${isEdit ? (team.description || '') : ''}" maxlength="500">
              </div>
              <div class="form-group">
                <label for="teamParent">Parent Team (optional)</label>
                <select id="teamParent" class="form-control">
                  <option value="">No parent (top-level team)</option>
                  ${parentOptions}
                </select>
              </div>
              ${isEdit ? `
                <div class="form-group">
                  <label for="teamActive">Status</label>
                  <select id="teamActive" class="form-control">
                    <option value="true" ${team.is_active ? 'selected' : ''}>Active</option>
                    <option value="false" ${!team.is_active ? 'selected' : ''}>Inactive</option>
                  </select>
                </div>
              ` : ''}
              <div class="form-actions">
                <button type="button" class="btn btn-secondary" id="cancelTeamEditorBtn">Cancel</button>
                <button type="submit" class="btn btn-primary">${isEdit ? 'Update' : 'Create'}</button>
              </div>
            </form>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);

    const modal = document.getElementById('teamEditorModal');
    const closeModal = () => modal.remove();

    document.getElementById('closeTeamEditorBtn').onclick = closeModal;
    document.getElementById('cancelTeamEditorBtn').onclick = closeModal;
    modal.onclick = (e) => { if (e.target === modal) closeModal(); };

    document.getElementById('teamEditorForm').onsubmit = async (e) => {
      e.preventDefault();
      const name = document.getElementById('teamName').value.trim();
      const displayName = document.getElementById('teamDisplayName').value.trim() || null;
      const description = document.getElementById('teamDescription').value.trim() || null;
      const parentTeamId = document.getElementById('teamParent').value || null;
      const isActive = isEdit ? document.getElementById('teamActive').value === 'true' : true;

      try {
        if (isEdit) {
          await AdminAPI.updateTeam(team.id, { name, display_name: displayName, description, parent_team_id: parentTeamId ? parseInt(parentTeamId) : null, is_active: isActive });
          showToast('Team updated', 'success');
        } else {
          await AdminAPI.createTeam({ name, display_name: displayName, description, parent_team_id: parentTeamId ? parseInt(parentTeamId) : null });
          showToast('Team created', 'success');
        }
        closeModal();
        AdminState.teams = await AdminAPI.getTeams();
        this.render();
      } catch (error) {
        showToast(error.message || 'Failed to save team', 'error');
      }
    };
  },

  /**
   * Show team members modal
   */
  async showTeamMembers(teamId) {
    try {
      const members = await AdminAPI.getTeamMembers(teamId);
      const team = AdminState.teams.find(t => t.id === teamId);

      const modalHtml = `
        <div class="modal active" id="teamMembersModal">
          <div class="modal-content" style="max-width: 600px;">
            <div class="modal-header">
              <h3>Members: ${team?.name || teamId}</h3>
              <button class="modal-close" id="closeTeamMembersBtn">&times;</button>
            </div>
            <div class="modal-body">
              <div class="team-member-add">
                <select id="addMemberUser" class="form-control">
                  <option value="">Add member...</option>
                  ${AdminState.users.filter(u => !members.find(m => m.user_id === u.id)).map(u =>
                    `<option value="${u.id}">${u.email}</option>`
                  ).join('')}
                </select>
                <select id="addMemberRole" class="form-control">
                  <option value="member">Member</option>
                  <option value="leader">Leader</option>
                </select>
                <button class="btn btn-primary" id="addMemberBtn">Add</button>
              </div>
              <div class="team-members-list">
                ${members.length > 0
                  ? members.map(m => {
                      const user = AdminState.users.find(u => u.id === m.user_id);
                      return `
                        <div class="team-member-item" data-user-id="${m.user_id}">
                          <div class="member-info">
                            <span class="member-email">${user?.email || m.user_id}</span>
                            <span class="member-role ${m.role === 'leader' ? 'role-leader' : ''}">${m.role}</span>
                          </div>
                          <button class="btn-icon remove-member-btn" data-user-id="${m.user_id}" title="Remove">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                              <line x1="18" y1="6" x2="6" y2="18"/>
                              <line x1="6" y1="6" x2="18" y2="18"/>
                            </svg>
                          </button>
                        </div>
                      `;
                    }).join('')
                  : '<p class="empty-state">No members in this team</p>'
                }
              </div>
            </div>
          </div>
        </div>
      `;

      document.body.insertAdjacentHTML('beforeend', modalHtml);

      const modal = document.getElementById('teamMembersModal');
      const closeModal = () => modal.remove();

      document.getElementById('closeTeamMembersBtn').onclick = closeModal;
      modal.onclick = (e) => { if (e.target === modal) closeModal(); };

      // Add member
      document.getElementById('addMemberBtn').onclick = async () => {
        const userId = document.getElementById('addMemberUser').value;
        const role = document.getElementById('addMemberRole').value;
        if (!userId) return;

        try {
          await AdminAPI.addTeamMember(teamId, userId, role);
          showToast('Member added', 'success');
          closeModal();
          this.showTeamMembers(teamId);
        } catch (error) {
          showToast(error.message || 'Failed to add member', 'error');
        }
      };

      // Remove members
      document.querySelectorAll('.remove-member-btn').forEach(btn => {
        btn.onclick = async () => {
          const userId = btn.dataset.userId;
          if (confirm('Remove this member from the team?')) {
            try {
              await AdminAPI.removeTeamMember(teamId, userId);
              showToast('Member removed', 'success');
              closeModal();
              this.showTeamMembers(teamId);
            } catch (error) {
              showToast(error.message || 'Failed to remove member', 'error');
            }
          }
        };
      });
    } catch (error) {
      showToast('Failed to load team members', 'error');
    }
  },

  /**
   * Show sharing rule creator modal
   */
  showSharingRuleCreator() {
    const objectTypes = ['proposals', 'booking_orders', 'mockups', 'templates'];

    const modalHtml = `
      <div class="modal active" id="sharingRuleModal">
        <div class="modal-content" style="max-width: 600px;">
          <div class="modal-header">
            <h3>Create Sharing Rule</h3>
            <button class="modal-close" id="closeSharingRuleBtn">&times;</button>
          </div>
          <div class="modal-body">
            <form id="sharingRuleForm">
              <div class="form-group">
                <label for="ruleName">Name</label>
                <input type="text" id="ruleName" class="form-control" placeholder="e.g., Share proposals with sales team" required>
              </div>
              <div class="form-group">
                <label for="ruleDescription">Description</label>
                <input type="text" id="ruleDescription" class="form-control" placeholder="Brief description" maxlength="500">
              </div>
              <div class="form-group">
                <label for="ruleObjectType">Object Type</label>
                <select id="ruleObjectType" class="form-control" required>
                  ${objectTypes.map(t => `<option value="${t}">${t}</option>`).join('')}
                </select>
              </div>
              <div class="form-row">
                <div class="form-group">
                  <label for="ruleFromType">Share From</label>
                  <select id="ruleFromType" class="form-control" required>
                    <option value="owner">Owner (record creator)</option>
                    <option value="profile">Profile</option>
                    <option value="team">Team</option>
                  </select>
                </div>
                <div class="form-group">
                  <label for="ruleFromId">From ID (optional)</label>
                  <input type="text" id="ruleFromId" class="form-control" placeholder="Profile name or Team ID">
                </div>
              </div>
              <div class="form-row">
                <div class="form-group">
                  <label for="ruleToType">Share To</label>
                  <select id="ruleToType" class="form-control" required>
                    <option value="profile">Profile</option>
                    <option value="team">Team</option>
                    <option value="all">All Users</option>
                  </select>
                </div>
                <div class="form-group">
                  <label for="ruleToId">To ID (optional)</label>
                  <input type="text" id="ruleToId" class="form-control" placeholder="Profile name or Team ID">
                </div>
              </div>
              <div class="form-group">
                <label for="ruleAccessLevel">Access Level</label>
                <select id="ruleAccessLevel" class="form-control" required>
                  <option value="read">Read Only</option>
                  <option value="read_write">Read & Write</option>
                  <option value="full">Full Access</option>
                </select>
              </div>
              <div class="form-actions">
                <button type="button" class="btn btn-secondary" id="cancelSharingRuleBtn">Cancel</button>
                <button type="submit" class="btn btn-primary">Create Rule</button>
              </div>
            </form>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);

    const modal = document.getElementById('sharingRuleModal');
    const closeModal = () => modal.remove();

    document.getElementById('closeSharingRuleBtn').onclick = closeModal;
    document.getElementById('cancelSharingRuleBtn').onclick = closeModal;
    modal.onclick = (e) => { if (e.target === modal) closeModal(); };

    document.getElementById('sharingRuleForm').onsubmit = async (e) => {
      e.preventDefault();
      const data = {
        name: document.getElementById('ruleName').value.trim(),
        description: document.getElementById('ruleDescription').value.trim() || null,
        object_type: document.getElementById('ruleObjectType').value,
        share_from_type: document.getElementById('ruleFromType').value,
        share_from_id: document.getElementById('ruleFromId').value.trim() || null,
        share_to_type: document.getElementById('ruleToType').value,
        share_to_id: document.getElementById('ruleToId').value.trim() || null,
        access_level: document.getElementById('ruleAccessLevel').value,
      };

      try {
        await AdminAPI.createSharingRule(data);
        showToast('Sharing rule created', 'success');
        closeModal();
        AdminState.sharingRules = await AdminAPI.getSharingRules();
        this.render();
      } catch (error) {
        showToast(error.message || 'Failed to create sharing rule', 'error');
      }
    };
  },

  /**
   * Show invite creator modal
   */
  showInviteCreator() {
    const profileOptions = AdminState.profiles.map(p =>
      `<option value="${p.name}" ${p.name === 'sales_user' ? 'selected' : ''}>${p.display_name || p.name}</option>`
    ).join('');

    const modalHtml = `
      <div class="modal active" id="inviteCreatorModal">
        <div class="modal-content" style="max-width: 500px;">
          <div class="modal-header">
            <h3>Create Invite Token</h3>
            <button class="modal-close" id="closeInviteCreatorBtn">&times;</button>
          </div>
          <div class="modal-body">
            <form id="inviteCreatorForm">
              <div class="form-group">
                <label for="inviteEmail">Email Address</label>
                <input type="email" id="inviteEmail" class="form-control" placeholder="user@example.com" required>
                <small class="form-help">The user must sign up with this exact email</small>
              </div>
              <div class="form-group">
                <label for="inviteProfile">Profile</label>
                <select id="inviteProfile" class="form-control" required>
                  ${profileOptions}
                </select>
              </div>
              <div class="form-group">
                <label for="inviteExpiry">Expires In</label>
                <select id="inviteExpiry" class="form-control">
                  <option value="1">1 day</option>
                  <option value="3">3 days</option>
                  <option value="7" selected>7 days</option>
                  <option value="14">14 days</option>
                  <option value="30">30 days</option>
                </select>
              </div>
              <div class="form-actions">
                <button type="button" class="btn btn-secondary" id="cancelInviteCreatorBtn">Cancel</button>
                <button type="submit" class="btn btn-primary">Create Invite</button>
              </div>
            </form>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);

    const modal = document.getElementById('inviteCreatorModal');
    const closeModal = () => modal.remove();

    document.getElementById('closeInviteCreatorBtn').onclick = closeModal;
    document.getElementById('cancelInviteCreatorBtn').onclick = closeModal;
    modal.onclick = (e) => { if (e.target === modal) closeModal(); };

    document.getElementById('inviteCreatorForm').onsubmit = async (e) => {
      e.preventDefault();
      const email = document.getElementById('inviteEmail').value.trim();
      const profileName = document.getElementById('inviteProfile').value;
      const expiresInDays = parseInt(document.getElementById('inviteExpiry').value);

      try {
        const result = await AdminAPI.createInvite({ email, profile_name: profileName, expires_in_days: expiresInDays });
        closeModal();
        this.showInviteSuccess(result);
        AdminState.invites = await AdminAPI.getInvites();
        this.render();
      } catch (error) {
        showToast(error.message || 'Failed to create invite', 'error');
      }
    };
  },

  /**
   * Show invite success modal
   */
  showInviteSuccess(invite) {
    const modalHtml = `
      <div class="modal active" id="inviteSuccessModal">
        <div class="modal-content" style="max-width: 500px;">
          <div class="modal-header">
            <h3>Invite Created!</h3>
            <button class="modal-close" id="closeInviteSuccessBtn">&times;</button>
          </div>
          <div class="modal-body">
            <div class="invite-success-content">
              <p>Share these details with <strong>${invite.email}</strong>:</p>
              <div class="invite-details">
                <div class="invite-detail-row">
                  <label>Token:</label>
                  <div class="token-copy-container">
                    <code id="inviteTokenValue">${invite.token}</code>
                    <button class="btn btn-sm btn-secondary" id="copyInviteTokenBtn">Copy</button>
                  </div>
                </div>
                <div class="invite-detail-row">
                  <label>Profile:</label>
                  <span>${invite.profile_name}</span>
                </div>
                <div class="invite-detail-row">
                  <label>Expires:</label>
                  <span>${new Date(invite.expires_at).toLocaleDateString()}</span>
                </div>
              </div>
              <p class="invite-warning">This token will only be shown once. Make sure to copy it!</p>
            </div>
            <div class="form-actions">
              <button type="button" class="btn btn-primary" id="doneInviteSuccessBtn">Done</button>
            </div>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);

    const modal = document.getElementById('inviteSuccessModal');
    const closeModal = () => modal.remove();

    document.getElementById('closeInviteSuccessBtn').onclick = closeModal;
    document.getElementById('doneInviteSuccessBtn').onclick = closeModal;
    modal.onclick = (e) => { if (e.target === modal) closeModal(); };

    document.getElementById('copyInviteTokenBtn').onclick = () => {
      const token = document.getElementById('inviteTokenValue').textContent;
      navigator.clipboard.writeText(token).then(() => {
        document.getElementById('copyInviteTokenBtn').textContent = 'Copied!';
        setTimeout(() => { document.getElementById('copyInviteTokenBtn').textContent = 'Copy'; }, 2000);
      });
    };
  },

  // ===========================================
  // EVENT LISTENERS
  // ===========================================
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

    // USER ACTIONS
    document.querySelectorAll('.view-user-perms-btn').forEach(btn => {
      btn.onclick = () => this.showUserPermissions(btn.dataset.userId);
    });
    document.querySelectorAll('.edit-user-btn').forEach(btn => {
      btn.onclick = () => {
        const user = AdminState.users.find(u => u.id === btn.dataset.userId);
        if (user) this.showUserEditor(user);
      };
    });
    document.querySelectorAll('.delete-user-btn').forEach(btn => {
      btn.onclick = async () => {
        const user = AdminState.users.find(u => u.id === btn.dataset.userId);
        if (user && confirm(`Delete user "${user.email}"?`)) {
          try {
            await AdminAPI.deleteUser(user.id);
            showToast('User deleted', 'success');
            AdminState.users = await AdminAPI.getUsers();
            this.render();
          } catch (error) {
            showToast(error.message || 'Failed to delete user', 'error');
          }
        }
      };
    });

    // PROFILE ACTIONS
    const createProfileBtn = document.getElementById('createProfileBtn');
    if (createProfileBtn) createProfileBtn.onclick = () => this.showProfileEditor();

    document.querySelectorAll('.view-profile-perms-btn').forEach(btn => {
      btn.onclick = () => this.showProfilePermissions(btn.dataset.profile);
    });
    document.querySelectorAll('.edit-profile-btn').forEach(btn => {
      btn.onclick = () => {
        const profile = AdminState.profiles.find(p => p.name === btn.dataset.profile);
        if (profile) this.showProfileEditor(profile);
      };
    });
    document.querySelectorAll('.delete-profile-btn').forEach(btn => {
      btn.onclick = async () => {
        if (confirm(`Delete profile "${btn.dataset.profile}"?`)) {
          try {
            await AdminAPI.deleteProfile(btn.dataset.profile);
            showToast('Profile deleted', 'success');
            AdminState.profiles = await AdminAPI.getProfiles();
            this.render();
          } catch (error) {
            showToast(error.message || 'Failed to delete profile', 'error');
          }
        }
      };
    });

    // PERMISSION SET ACTIONS
    const createPsBtn = document.getElementById('createPermissionSetBtn');
    if (createPsBtn) createPsBtn.onclick = () => this.showPermissionSetEditor();

    document.querySelectorAll('.view-ps-perms-btn').forEach(btn => {
      btn.onclick = () => {
        const ps = AdminState.permissionSets.find(p => p.name === btn.dataset.ps);
        if (ps) this.showPermissionSetPermissions(ps);
      };
    });
    document.querySelectorAll('.assign-ps-btn').forEach(btn => {
      btn.onclick = () => this.showAssignPermissionSet(btn.dataset.ps);
    });
    document.querySelectorAll('.edit-ps-btn').forEach(btn => {
      btn.onclick = () => {
        const ps = AdminState.permissionSets.find(p => p.name === btn.dataset.ps);
        if (ps) this.showPermissionSetEditor(ps);
      };
    });
    document.querySelectorAll('.delete-ps-btn').forEach(btn => {
      btn.onclick = async () => {
        if (confirm(`Delete permission set "${btn.dataset.ps}"?`)) {
          try {
            await AdminAPI.deletePermissionSet(btn.dataset.ps);
            showToast('Permission set deleted', 'success');
            AdminState.permissionSets = await AdminAPI.getPermissionSets();
            this.render();
          } catch (error) {
            showToast(error.message || 'Failed to delete permission set', 'error');
          }
        }
      };
    });

    // TEAM ACTIONS
    const createTeamBtn = document.getElementById('createTeamBtn');
    if (createTeamBtn) createTeamBtn.onclick = () => this.showTeamEditor();

    document.querySelectorAll('.view-team-members-btn').forEach(btn => {
      btn.onclick = () => this.showTeamMembers(parseInt(btn.dataset.teamId));
    });
    document.querySelectorAll('.edit-team-btn').forEach(btn => {
      btn.onclick = () => {
        const team = AdminState.teams.find(t => t.id === parseInt(btn.dataset.teamId));
        if (team) this.showTeamEditor(team);
      };
    });
    document.querySelectorAll('.delete-team-btn').forEach(btn => {
      btn.onclick = async () => {
        if (confirm('Delete this team?')) {
          try {
            await AdminAPI.deleteTeam(parseInt(btn.dataset.teamId));
            showToast('Team deleted', 'success');
            AdminState.teams = await AdminAPI.getTeams();
            this.render();
          } catch (error) {
            showToast(error.message || 'Failed to delete team', 'error');
          }
        }
      };
    });

    // SHARING RULE ACTIONS
    const createRuleBtn = document.getElementById('createSharingRuleBtn');
    if (createRuleBtn) createRuleBtn.onclick = () => this.showSharingRuleCreator();

    document.querySelectorAll('.delete-rule-btn').forEach(btn => {
      btn.onclick = async () => {
        if (confirm('Delete this sharing rule?')) {
          try {
            await AdminAPI.deleteSharingRule(parseInt(btn.dataset.ruleId));
            showToast('Sharing rule deleted', 'success');
            AdminState.sharingRules = await AdminAPI.getSharingRules();
            this.render();
          } catch (error) {
            showToast(error.message || 'Failed to delete sharing rule', 'error');
          }
        }
      };
    });

    // INVITE ACTIONS
    const createInviteBtn = document.getElementById('createInviteBtn');
    if (createInviteBtn) createInviteBtn.onclick = () => this.showInviteCreator();

    document.querySelectorAll('.copy-token-btn').forEach(btn => {
      btn.onclick = () => {
        navigator.clipboard.writeText(btn.dataset.token).then(() => {
          showToast('Token copied', 'success');
        });
      };
    });
    document.querySelectorAll('.revoke-invite-btn').forEach(btn => {
      btn.onclick = async () => {
        if (confirm('Revoke this invite?')) {
          try {
            await AdminAPI.revokeInvite(btn.dataset.inviteId);
            showToast('Invite revoked', 'success');
            AdminState.invites = await AdminAPI.getInvites();
            this.render();
          } catch (error) {
            showToast(error.message || 'Failed to revoke invite', 'error');
          }
        }
      };
    });
  },
};

// =============================================================================
// EXPORT
// =============================================================================

window.AdminUI = AdminUI;
window.AdminAPI = AdminAPI;
window.AdminState = AdminState;

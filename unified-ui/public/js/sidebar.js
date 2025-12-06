/**
 * Sidebar Module - Tool navigation and settings
 */

const Sidebar = {
  currentTool: 'chat',
  isCollapsed: false,

  init() {
    this.setupNavigation();
    this.setupSettings();
    this.setupCollapse();
    this.showTool('chat');
  },

  setupNavigation() {
    const navItems = document.querySelectorAll('.sidebar-nav-item');

    navItems.forEach(item => {
      item.addEventListener('click', () => {
        const tool = item.dataset.tool;
        this.showTool(tool);
      });
    });
  },

  showTool(tool) {
    this.currentTool = tool;

    // Update nav items
    const navItems = document.querySelectorAll('.sidebar-nav-item');
    navItems.forEach(item => {
      item.classList.toggle('active', item.dataset.tool === tool);
    });

    // Update tool panels
    const panels = document.querySelectorAll('.tool-panel');
    panels.forEach(panel => {
      panel.classList.toggle('active', panel.id === `${tool}Panel`);
    });

    // Update settings panels
    this.showSettings(tool);

    // Initialize tool-specific content
    this.initTool(tool);
  },

  showSettings(tool) {
    const settingsPanels = document.querySelectorAll('.tool-settings-panel');
    settingsPanels.forEach(panel => {
      panel.style.display = panel.id === `${tool}Settings` ? 'block' : 'none';
    });
  },

  initTool(tool) {
    switch (tool) {
      case 'chat':
        if (window.Chat) {
          Chat.init();
        }
        break;
      case 'mockup':
        this.initMockup();
        break;
      case 'proposals':
        this.initProposals();
        break;
      case 'admin':
        this.initAdmin();
        break;
    }
  },

  initMockup() {
    // Load mockup studio content into the panel
    const mockupPanel = document.getElementById('mockupPanel');
    if (!mockupPanel) return;

    // Check if already initialized
    if (mockupPanel.dataset.initialized) return;
    mockupPanel.dataset.initialized = 'true';

    // Load locations for settings dropdown
    this.loadMockupLocations();

    // Mode toggle
    const modeToggleBtns = document.querySelectorAll('.mode-toggle-btn');
    modeToggleBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        modeToggleBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        // Mode change logic here
      });
    });
  },

  async loadMockupLocations() {
    const locationSelect = document.getElementById('mockupLocation');
    if (!locationSelect) return;

    try {
      // Try to load from API
      const locations = await API.mockup.getLocations();
      locationSelect.innerHTML = '<option value="">Select location...</option>' +
        locations.map(loc => `<option value="${loc}">${loc}</option>`).join('');
    } catch (e) {
      // Fallback to hardcoded locations
      const defaultLocations = [
        'Burj Khalifa',
        'Dubai Mall',
        'The Landmark',
        'Business Bay'
      ];
      locationSelect.innerHTML = '<option value="">Select location...</option>' +
        defaultLocations.map(loc => `<option value="${loc}">${loc}</option>`).join('');
    }
  },

  initProposals() {
    const proposalsPanel = document.getElementById('proposalsPanel');
    if (!proposalsPanel) return;

    // Check if already initialized
    if (proposalsPanel.dataset.initialized) return;
    proposalsPanel.dataset.initialized = 'true';

    // Load proposal history
    this.loadProposals();

    // New proposal button
    const newProposalBtn = document.getElementById('newProposalBtn');
    if (newProposalBtn) {
      newProposalBtn.addEventListener('click', () => {
        // Switch to chat and suggest proposal
        this.showTool('chat');
        const chatInput = document.getElementById('chatInput');
        if (chatInput) {
          chatInput.value = 'Generate a sales proposal for ';
          chatInput.focus();
        }
      });
    }
  },

  async loadProposals() {
    const proposalsList = document.getElementById('proposalsList');
    if (!proposalsList) return;

    try {
      const proposals = await API.proposals.getHistory();

      if (proposals && proposals.length > 0) {
        proposalsList.innerHTML = proposals.map(p => `
          <div class="proposal-item">
            <div class="proposal-info">
              <h4>${p.client || 'Unknown Client'}</h4>
              <p>${p.location || ''} - ${new Date(p.created_at).toLocaleDateString()}</p>
            </div>
            <a href="${p.file_url}" target="_blank" class="btn btn-secondary btn-sm">Download</a>
          </div>
        `).join('');
      } else {
        proposalsList.innerHTML = '<p class="empty-state">No proposals yet. Create your first one!</p>';
      }
    } catch (e) {
      proposalsList.innerHTML = '<p class="empty-state">No proposals yet. Create your first one!</p>';
    }
  },

  async initAdmin() {
    const adminPanel = document.getElementById('adminPanel');
    if (!adminPanel) return;

    // Check if already initialized
    if (adminPanel.dataset.initialized) {
      // Just re-render if already initialized
      if (window.AdminUI) {
        AdminUI.render();
      }
      return;
    }

    // Initialize admin module
    if (window.AdminUI) {
      const success = await AdminUI.init();
      if (success) {
        adminPanel.dataset.initialized = 'true';
        AdminUI.render();
      } else {
        adminPanel.innerHTML = '<p class="empty-state">Admin panel not available.</p>';
      }
    }
  },

  /**
   * Show/hide admin nav item based on user roles
   */
  updateAdminVisibility(user) {
    const adminNavItem = document.getElementById('adminNavItem');
    if (!adminNavItem) return;

    const isAdmin = user && user.roles && user.roles.includes('admin');
    adminNavItem.style.display = isAdmin ? 'flex' : 'none';
  },

  setupSettings() {
    // Chat temperature slider
    const tempSlider = document.getElementById('chatTemperature');
    const tempValue = document.getElementById('chatTempValue');

    if (tempSlider && tempValue) {
      tempSlider.addEventListener('input', () => {
        tempValue.textContent = (tempSlider.value / 100).toFixed(1);
      });
    }
  },

  setupCollapse() {
    const collapseBtn = document.getElementById('sidebarCollapseBtn');
    const sidebar = document.getElementById('appSidebar');

    if (collapseBtn && sidebar) {
      collapseBtn.addEventListener('click', () => {
        this.isCollapsed = !this.isCollapsed;
        sidebar.classList.toggle('collapsed', this.isCollapsed);
      });
    }
  },

  collapse() {
    const sidebar = document.getElementById('appSidebar');
    if (sidebar) {
      this.isCollapsed = true;
      sidebar.classList.add('collapsed');
    }
  },

  expand() {
    const sidebar = document.getElementById('appSidebar');
    if (sidebar) {
      this.isCollapsed = false;
      sidebar.classList.remove('collapsed');
    }
  }
};

// Make Sidebar globally available
window.Sidebar = Sidebar;

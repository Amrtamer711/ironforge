/**
 * Sidebar Module - Tool navigation and settings
 */

const Sidebar = {
  currentTool: 'chat',
  isCollapsed: false,

  init() {
    console.log('[Sidebar] Initializing...');
    this.setupNavigation();
    this.setupSettings();
    this.setupCollapse();
    this.showTool('chat');
    console.log('[Sidebar] Initialized');
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
    console.log('[Sidebar] Switching to tool:', tool);
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
    // Initialize mockup generator module
    const mockupPanel = document.getElementById('mockupPanel');
    if (!mockupPanel) return;

    // Check if already initialized
    if (mockupPanel.dataset.initialized) return;
    mockupPanel.dataset.initialized = 'true';

    // Initialize the MockupGenerator module
    if (window.MockupGenerator) {
      MockupGenerator.init();
    } else {
      console.warn('[Sidebar] MockupGenerator module not loaded');
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
    console.log('[Sidebar] Initializing admin panel...');
    const adminPanel = document.getElementById('adminPanel');
    if (!adminPanel) return;

    // Check if already initialized
    if (adminPanel.dataset.initialized) {
      console.log('[Sidebar] Admin panel already initialized, re-rendering');
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
        console.log('[Sidebar] Admin panel initialized successfully');
        adminPanel.dataset.initialized = 'true';
        AdminUI.render();
      } else {
        console.warn('[Sidebar] Admin panel initialization failed');
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

/**
 * Module Registry - Manages application modules and navigation
 *
 * Handles:
 * - Fetching accessible modules from backend
 * - Rendering dynamic navigation
 * - Module switching
 * - Tool management within modules
 */

const ModuleRegistry = {
  // State
  modules: [],
  currentModule: null,
  currentTool: null,
  defaultModule: null,
  userDefaultModule: null,
  isLoading: false,
  initialized: false,

  /**
   * Initialize the module registry
   * Fetches accessible modules and sets up navigation
   */
  async init() {
    if (this.initialized) {
      console.log('[ModuleRegistry] Already initialized');
      return true;
    }

    console.log('[ModuleRegistry] Initializing...');
    this.isLoading = true;

    try {
      // Fetch accessible modules from backend
      const modules = await this.fetchModules();

      if (!modules || modules.length === 0) {
        console.warn('[ModuleRegistry] No modules accessible to user');
        this.isLoading = false;
        return false;
      }

      this.modules = modules.modules;
      this.defaultModule = modules.default_module;
      this.userDefaultModule = modules.user_default_module;

      console.log('[ModuleRegistry] Loaded modules:', this.modules.map(m => m.name));

      // Render the navigation
      this.renderNavigation();

      // Render the module switcher
      this.renderModuleSwitcher();

      // Determine and activate default module
      const targetModule = this.userDefaultModule || this.defaultModule || this.modules[0]?.name;
      if (targetModule) {
        await this.switchModule(targetModule);
      }

      this.initialized = true;
      this.isLoading = false;
      console.log('[ModuleRegistry] Initialized successfully');
      return true;

    } catch (error) {
      console.error('[ModuleRegistry] Initialization failed:', error);
      this.isLoading = false;
      return false;
    }
  },

  /**
   * Fetch accessible modules from the backend
   */
  async fetchModules() {
    try {
      const token = await Auth.getAccessToken();
      if (!token) {
        console.warn('[ModuleRegistry] No auth token available');
        return null;
      }

      const response = await fetch('/api/sales/modules/accessible', {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch modules: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('[ModuleRegistry] Error fetching modules:', error);
      // Return fallback modules for development
      return this.getFallbackModules();
    }
  },

  /**
   * Fallback modules for when backend is unavailable (dev mode)
   */
  getFallbackModules() {
    console.log('[ModuleRegistry] Using fallback modules');

    const user = Auth.getUser();
    const isAdmin = user && user.roles && user.roles.includes('admin');

    const modules = [
      {
        name: 'sales',
        display_name: 'Sales Bot',
        description: 'Sales proposal generation, mockups, and booking orders',
        icon: 'chart-bar',
        is_default: true,
        sort_order: 1,
        tools: ['chat', 'mockup', 'proposals']
      }
    ];

    if (isAdmin) {
      modules.push({
        name: 'core',
        display_name: 'Administration',
        description: 'System administration and user management',
        icon: 'shield',
        is_default: false,
        sort_order: 100,
        tools: ['admin']
      });
    }

    return {
      modules: modules,
      default_module: 'sales',
      user_default_module: null
    };
  },

  /**
   * Render the sidebar navigation based on current module
   */
  renderNavigation() {
    const navContainer = document.querySelector('.sidebar-nav');
    if (!navContainer) {
      console.warn('[ModuleRegistry] Navigation container not found');
      return;
    }

    // Get current module config
    const moduleConfig = this.getModuleConfig(this.currentModule || this.defaultModule || 'sales');
    if (!moduleConfig) {
      console.warn('[ModuleRegistry] No module config found');
      return;
    }

    // Get tool configurations
    const tools = this.getToolConfigs(moduleConfig.name);

    // Build navigation HTML
    let navHTML = '';
    tools.forEach((tool, index) => {
      const isActive = index === 0; // First tool is active by default
      navHTML += `
        <button class="sidebar-nav-item ${isActive ? 'active' : ''}" data-tool="${tool.name}" data-module="${moduleConfig.name}">
          ${this.getToolIcon(tool.name)}
          <span>${tool.display_name}</span>
        </button>
      `;
    });

    navContainer.innerHTML = navHTML;

    // Add click handlers
    navContainer.querySelectorAll('.sidebar-nav-item').forEach(item => {
      item.addEventListener('click', () => {
        const toolName = item.dataset.tool;
        this.switchTool(toolName);
      });
    });

    console.log('[ModuleRegistry] Navigation rendered for module:', moduleConfig.name);
  },

  /**
   * Render the module switcher dropdown in header
   */
  renderModuleSwitcher() {
    const switcherContainer = document.getElementById('moduleSwitcher');
    if (!switcherContainer) {
      console.log('[ModuleRegistry] Module switcher container not found, creating...');
      this.createModuleSwitcher();
      return;
    }

    this.updateModuleSwitcher();
  },

  /**
   * Create the module switcher dropdown in the header
   */
  createModuleSwitcher() {
    // Find the header actions area
    const headerActions = document.querySelector('.header-actions');
    if (!headerActions) return;

    // Only show switcher if user has access to multiple modules
    if (this.modules.length <= 1) {
      console.log('[ModuleRegistry] Single module, no switcher needed');
      return;
    }

    // Create switcher element
    const switcherHTML = `
      <div class="module-switcher" id="moduleSwitcher">
        <button class="module-switcher-btn" id="moduleSwitcherBtn">
          <span class="module-switcher-icon" id="moduleSwitcherIcon"></span>
          <span class="module-switcher-name" id="moduleSwitcherName">Loading...</span>
          <svg class="module-switcher-arrow" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M6 9l6 6 6-6"/>
          </svg>
        </button>
        <div class="module-switcher-dropdown" id="moduleSwitcherDropdown">
          ${this.modules.map(m => `
            <button class="module-switcher-option ${m.name === this.currentModule ? 'active' : ''}" data-module="${m.name}">
              ${this.getModuleIcon(m.icon)}
              <span>${m.display_name}</span>
            </button>
          `).join('')}
        </div>
      </div>
    `;

    // Insert before user menu
    const userMenu = headerActions.querySelector('.user-menu');
    if (userMenu) {
      userMenu.insertAdjacentHTML('beforebegin', switcherHTML);
    } else {
      headerActions.insertAdjacentHTML('afterbegin', switcherHTML);
    }

    // Add event listeners
    this.setupModuleSwitcherEvents();
  },

  /**
   * Setup module switcher event handlers
   */
  setupModuleSwitcherEvents() {
    const btn = document.getElementById('moduleSwitcherBtn');
    const dropdown = document.getElementById('moduleSwitcherDropdown');

    if (btn && dropdown) {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        dropdown.classList.toggle('open');
      });

      // Close on outside click
      document.addEventListener('click', () => {
        dropdown.classList.remove('open');
      });

      // Module selection
      dropdown.querySelectorAll('.module-switcher-option').forEach(option => {
        option.addEventListener('click', (e) => {
          e.stopPropagation();
          const moduleName = option.dataset.module;
          this.switchModule(moduleName);
          dropdown.classList.remove('open');
        });
      });
    }
  },

  /**
   * Update the module switcher display
   */
  updateModuleSwitcher() {
    const nameEl = document.getElementById('moduleSwitcherName');
    const iconEl = document.getElementById('moduleSwitcherIcon');
    const dropdown = document.getElementById('moduleSwitcherDropdown');

    const currentConfig = this.getModuleConfig(this.currentModule);
    if (currentConfig) {
      if (nameEl) nameEl.textContent = currentConfig.display_name;
      if (iconEl) iconEl.innerHTML = this.getModuleIcon(currentConfig.icon);
    }

    // Update active state in dropdown
    if (dropdown) {
      dropdown.querySelectorAll('.module-switcher-option').forEach(option => {
        option.classList.toggle('active', option.dataset.module === this.currentModule);
      });
    }
  },

  /**
   * Switch to a different module
   */
  async switchModule(moduleName) {
    console.log('[ModuleRegistry] Switching to module:', moduleName);

    const moduleConfig = this.getModuleConfig(moduleName);
    if (!moduleConfig) {
      console.error('[ModuleRegistry] Module not found:', moduleName);
      return false;
    }

    // Update state
    this.currentModule = moduleName;

    // Re-render navigation for this module
    this.renderNavigation();

    // Update module switcher
    this.updateModuleSwitcher();

    // Switch to default tool in this module
    const tools = this.getToolConfigs(moduleName);
    const defaultTool = tools.find(t => t.is_default) || tools[0];
    if (defaultTool) {
      await this.switchTool(defaultTool.name);
    }

    console.log('[ModuleRegistry] Switched to module:', moduleName);
    return true;
  },

  /**
   * Switch to a different tool within the current module
   */
  async switchTool(toolName) {
    console.log('[ModuleRegistry] Switching to tool:', toolName);

    this.currentTool = toolName;

    // Update nav items
    const navItems = document.querySelectorAll('.sidebar-nav-item');
    navItems.forEach(item => {
      item.classList.toggle('active', item.dataset.tool === toolName);
    });

    // Update tool panels
    const panels = document.querySelectorAll('.tool-panel');
    panels.forEach(panel => {
      panel.classList.toggle('active', panel.id === `${toolName}Panel`);
    });

    // Update settings panels
    const settingsPanels = document.querySelectorAll('.tool-settings-panel');
    settingsPanels.forEach(panel => {
      panel.style.display = panel.id === `${toolName}Settings` ? 'block' : 'none';
    });

    // Initialize tool-specific content
    await this.initTool(toolName);

    console.log('[ModuleRegistry] Switched to tool:', toolName);
  },

  /**
   * Initialize a tool when it becomes active
   */
  async initTool(toolName) {
    switch (toolName) {
      case 'chat':
        if (window.Chat) {
          Chat.init();
        }
        break;
      case 'mockup':
        if (window.Sidebar) {
          Sidebar.initMockup();
        }
        break;
      case 'proposals':
        if (window.Sidebar) {
          Sidebar.initProposals();
        }
        break;
      case 'admin':
        if (window.AdminUI) {
          await AdminUI.init();
          AdminUI.render();
        }
        break;
    }
  },

  /**
   * Get module configuration by name
   */
  getModuleConfig(moduleName) {
    return this.modules.find(m => m.name === moduleName);
  },

  /**
   * Get tool configurations for a module
   */
  getToolConfigs(moduleName) {
    // Tool definitions - these could come from backend in the future
    const toolDefs = {
      sales: [
        { name: 'chat', display_name: 'AI Chat', icon: 'chat', is_default: true },
        { name: 'mockup', display_name: 'Mockup Generator', icon: 'mockup' },
        { name: 'proposals', display_name: 'Proposals', icon: 'document' },
      ],
      core: [
        { name: 'admin', display_name: 'Admin Panel', icon: 'shield', is_default: true },
      ],
    };

    return toolDefs[moduleName] || [];
  },

  /**
   * Get SVG icon for a tool
   */
  getToolIcon(toolName) {
    const icons = {
      chat: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
      </svg>`,
      mockup: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="3" y="3" width="18" height="18" rx="2"/>
        <path d="M3 9h18M9 21V9"/>
      </svg>`,
      proposals: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>
      </svg>`,
      admin: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
      </svg>`,
    };
    return icons[toolName] || icons.chat;
  },

  /**
   * Get SVG icon for a module
   */
  getModuleIcon(iconName) {
    const icons = {
      'chart-bar': `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M12 20V10M6 20V14M18 20V4"/>
      </svg>`,
      'shield': `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
      </svg>`,
      'users': `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
        <circle cx="9" cy="7" r="4"/>
        <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>
      </svg>`,
    };
    return icons[iconName] || icons['chart-bar'];
  },

  /**
   * Check if user has access to a specific module
   */
  hasModuleAccess(moduleName) {
    return this.modules.some(m => m.name === moduleName);
  },

  /**
   * Get list of accessible module names
   */
  getAccessibleModuleNames() {
    return this.modules.map(m => m.name);
  },

  /**
   * Reset the module registry (for logout)
   */
  reset() {
    this.modules = [];
    this.currentModule = null;
    this.currentTool = null;
    this.defaultModule = null;
    this.userDefaultModule = null;
    this.isLoading = false;
    this.initialized = false;
    console.log('[ModuleRegistry] Reset');
  }
};

// Make globally available
window.ModuleRegistry = ModuleRegistry;

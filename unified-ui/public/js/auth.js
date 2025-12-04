/**
 * Auth Module - Handles authentication
 * Supports: Local dev (simple auth) and Supabase (production)
 */

const Auth = {
  user: null,
  isLocalDev: window.location.hostname === 'localhost',

  // Dev users for local testing
  devUsers: {
    'admin@mmg.com': {
      password: 'admin123',
      id: 'dev-admin-1',
      name: 'Sales Admin',
      email: 'admin@mmg.com',
      roles: ['admin', 'hos', 'sales_person']
    },
    'hos@mmg.com': {
      password: 'hos123',
      id: 'dev-hos-1',
      name: 'Head of Sales',
      email: 'hos@mmg.com',
      roles: ['hos', 'sales_person']
    },
    'sales@mmg.com': {
      password: 'sales123',
      id: 'dev-sales-1',
      name: 'Sales Person',
      email: 'sales@mmg.com',
      roles: ['sales_person']
    }
  },

  init() {
    // Check for existing session
    const token = localStorage.getItem('authToken');
    const userData = localStorage.getItem('userData');

    if (token && userData) {
      try {
        this.user = JSON.parse(userData);
        this.showApp();
        return true;
      } catch (e) {
        this.logout();
      }
    }

    this.showLanding();
    return false;
  },

  async login(email, password) {
    if (this.isLocalDev) {
      return this.localLogin(email, password);
    }
    return this.apiLogin(email, password);
  },

  localLogin(email, password) {
    const user = this.devUsers[email.toLowerCase()];

    if (!user || user.password !== password) {
      throw new Error('Invalid email or password');
    }

    // Create mock token and user data
    const token = 'dev-token-' + Date.now();
    const userData = {
      id: user.id,
      name: user.name,
      email: user.email,
      roles: user.roles
    };

    // Store in localStorage
    localStorage.setItem('authToken', token);
    localStorage.setItem('userData', JSON.stringify(userData));

    this.user = userData;
    return userData;
  },

  async apiLogin(email, password) {
    try {
      const response = await API.auth.login(email, password);

      if (response && response.token) {
        localStorage.setItem('authToken', response.token);
        localStorage.setItem('userData', JSON.stringify(response.user));
        this.user = response.user;
        return response.user;
      }

      throw new Error('Login failed');
    } catch (error) {
      throw error;
    }
  },

  logout() {
    localStorage.removeItem('authToken');
    localStorage.removeItem('userData');
    this.user = null;

    // Try to call logout endpoint (non-blocking)
    if (!this.isLocalDev) {
      API.auth.logout().catch(() => {});
    }

    this.showLanding();
  },

  showLanding() {
    document.getElementById('landingPage').style.display = 'flex';
    document.getElementById('app').style.display = 'none';
    document.getElementById('loginModal').classList.remove('active');
  },

  showLogin() {
    document.getElementById('loginModal').classList.add('active');
  },

  hideLogin() {
    document.getElementById('loginModal').classList.remove('active');
  },

  showApp() {
    document.getElementById('landingPage').style.display = 'none';
    document.getElementById('loginModal').classList.remove('active');
    document.getElementById('app').style.display = 'flex';

    // Update UI with user info
    this.updateUserUI();

    // Initialize sidebar and tools
    if (window.Sidebar) {
      Sidebar.init();
    }
  },

  updateUserUI() {
    if (!this.user) return;

    // Update user name
    const userNameEl = document.getElementById('userName');
    if (userNameEl) {
      userNameEl.textContent = this.user.name || 'User';
    }

    // Update initials
    const initialsEl = document.getElementById('userInitials');
    if (initialsEl) {
      const names = (this.user.name || 'U').split(' ');
      initialsEl.textContent = names.map(n => n[0]).join('').toUpperCase().slice(0, 2);
    }

    // Update email
    const emailEl = document.getElementById('userEmail');
    if (emailEl) {
      emailEl.textContent = this.user.email || '';
    }

    // Update roles
    const rolesEl = document.getElementById('userRoles');
    if (rolesEl && this.user.roles) {
      rolesEl.innerHTML = this.user.roles.map(role => {
        const roleClass = role === 'admin' ? 'role-admin' :
                          role === 'hos' ? 'role-hos' : 'role-sales';
        const roleLabel = role === 'admin' ? 'Admin' :
                          role === 'hos' ? 'HoS' :
                          role === 'sales_person' ? 'Sales' : role;
        return `<span class="role-badge ${roleClass}">${roleLabel}</span>`;
      }).join('');
    }
  },

  hasRole(role) {
    return this.user && this.user.roles && this.user.roles.includes(role);
  },

  isAdmin() {
    return this.hasRole('admin');
  },

  isHos() {
    return this.hasRole('hos');
  }
};

// Initialize auth event listeners
document.addEventListener('DOMContentLoaded', () => {
  // Landing page login buttons
  const landingLoginBtn = document.getElementById('landingLoginBtn');
  const heroGetStartedBtn = document.getElementById('heroGetStartedBtn');

  if (landingLoginBtn) {
    landingLoginBtn.addEventListener('click', () => Auth.showLogin());
  }

  if (heroGetStartedBtn) {
    heroGetStartedBtn.addEventListener('click', () => Auth.showLogin());
  }

  // Close login modal
  const closeLoginModal = document.getElementById('closeLoginModal');
  if (closeLoginModal) {
    closeLoginModal.addEventListener('click', () => Auth.hideLogin());
  }

  // Login form submission
  const loginForm = document.getElementById('loginForm');
  if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();

      const email = document.getElementById('emailInput').value;
      const password = document.getElementById('passwordInput').value;
      const submitBtn = loginForm.querySelector('button[type="submit"]');

      try {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Signing in...';

        await Auth.login(email, password);
        Auth.showApp();

        Toast.success('Welcome back!');
      } catch (error) {
        Toast.error(error.message || 'Login failed');
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Sign In';
      }
    });
  }

  // Logout button
  const logoutBtn = document.getElementById('logoutBtn');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', () => {
      Auth.logout();
      Toast.success('Logged out successfully');
    });
  }

  // User menu toggle
  const userMenuBtn = document.getElementById('userMenuBtn');
  const userMenu = document.getElementById('userMenu');

  if (userMenuBtn && userMenu) {
    userMenuBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      userMenu.classList.toggle('open');
    });

    // Close menu when clicking outside
    document.addEventListener('click', (e) => {
      if (!userMenu.contains(e.target)) {
        userMenu.classList.remove('open');
      }
    });
  }

  // Initialize auth state
  Auth.init();
});

// Make Auth globally available
window.Auth = Auth;

/**
 * Auth Module - Handles authentication via Supabase
 * Supports: Local dev (simple auth) and Supabase (production)
 */

const Auth = {
  user: null,
  supabaseClient: null,
  isLocalDev: window.location.hostname === 'localhost' && !window.SUPABASE_URL,

  // Dev users for local testing (when Supabase is not configured)
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

  async init() {
    // Initialize Supabase client if configured
    if (window.SUPABASE_URL && window.SUPABASE_ANON_KEY && typeof supabase !== 'undefined') {
      this.supabaseClient = supabase.createClient(window.SUPABASE_URL, window.SUPABASE_ANON_KEY);
      this.isLocalDev = false;

      // Listen for auth state changes
      this.supabaseClient.auth.onAuthStateChange((event, session) => {
        if (event === 'SIGNED_IN' && session) {
          this.handleSession(session);
        } else if (event === 'SIGNED_OUT') {
          this.user = null;
          this.showLanding();
        }
      });

      // Check for existing session
      const { data: { session } } = await this.supabaseClient.auth.getSession();
      if (session) {
        this.handleSession(session);
        return true;
      }
    } else {
      // Local dev mode - check localStorage
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
    }

    this.showLanding();
    return false;
  },

  handleSession(session) {
    const user = session.user;

    // Build user object from Supabase user
    this.user = {
      id: user.id,
      email: user.email,
      name: user.user_metadata?.name || user.email?.split('@')[0] || 'User',
      roles: user.user_metadata?.roles || ['sales_person']
    };

    // Store for API requests
    localStorage.setItem('authToken', session.access_token);
    localStorage.setItem('userData', JSON.stringify(this.user));

    this.showApp();
  },

  async login(email, password) {
    if (this.isLocalDev) {
      return this.localLogin(email, password);
    }
    return this.supabaseLogin(email, password);
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

  async supabaseLogin(email, password) {
    if (!this.supabaseClient) {
      throw new Error('Supabase not configured');
    }

    const { data, error } = await this.supabaseClient.auth.signInWithPassword({
      email,
      password
    });

    if (error) {
      throw new Error(error.message);
    }

    // Session will be handled by onAuthStateChange
    return this.user;
  },

  async signUp(email, password, name) {
    if (this.isLocalDev) {
      throw new Error('Sign up not available in dev mode');
    }

    if (!this.supabaseClient) {
      throw new Error('Supabase not configured');
    }

    const { data, error } = await this.supabaseClient.auth.signUp({
      email,
      password,
      options: {
        data: {
          name: name,
          roles: ['sales_person'] // Default role
        }
      }
    });

    if (error) {
      throw new Error(error.message);
    }

    return data;
  },

  async logout() {
    if (this.supabaseClient) {
      await this.supabaseClient.auth.signOut();
    }

    localStorage.removeItem('authToken');
    localStorage.removeItem('userData');
    this.user = null;

    this.showLanding();
  },

  async getAccessToken() {
    if (this.isLocalDev) {
      return localStorage.getItem('authToken');
    }

    if (this.supabaseClient) {
      const { data: { session } } = await this.supabaseClient.auth.getSession();
      return session?.access_token || null;
    }

    return null;
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
      // Update admin visibility based on user roles
      Sidebar.updateAdminVisibility(this.user);
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
  },

  getUser() {
    return this.user;
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
    logoutBtn.addEventListener('click', async () => {
      await Auth.logout();
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

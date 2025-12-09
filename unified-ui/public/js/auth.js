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
    console.log('[Auth] Initializing...');
    console.log('[Auth] SUPABASE_URL:', window.SUPABASE_URL ? 'configured' : 'not set');
    console.log('[Auth] SUPABASE_ANON_KEY:', window.SUPABASE_ANON_KEY ? 'configured' : 'not set');

    // Initialize Supabase client if configured
    if (window.SUPABASE_URL && window.SUPABASE_ANON_KEY && typeof supabase !== 'undefined') {
      console.log('[Auth] Creating Supabase client...');
      this.supabaseClient = supabase.createClient(window.SUPABASE_URL, window.SUPABASE_ANON_KEY);
      this.isLocalDev = false;

      // Listen for auth state changes
      this.supabaseClient.auth.onAuthStateChange((event, session) => {
        console.log('[Auth] Auth state changed:', event);
        if (event === 'SIGNED_IN' && session) {
          this.handleSession(session);
        } else if (event === 'SIGNED_OUT') {
          this.user = null;
          this.showLanding();
        }
      });

      // Check for existing session
      console.log('[Auth] Checking for existing session...');
      const { data: { session } } = await this.supabaseClient.auth.getSession();
      if (session) {
        console.log('[Auth] Found existing session');
        this.handleSession(session);
        return true;
      }
      console.log('[Auth] No existing session found');
    } else {
      console.log('[Auth] Running in local dev mode');
      // Local dev mode - check localStorage
      const token = localStorage.getItem('authToken');
      const userData = localStorage.getItem('userData');

      if (token && userData) {
        try {
          this.user = JSON.parse(userData);
          console.log('[Auth] Restored dev session for:', this.user.email);
          this.showApp();
          return true;
        } catch (e) {
          console.error('[Auth] Failed to parse stored user data');
          this.logout();
        }
      }
    }

    console.log('[Auth] Showing landing page');
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
    console.log('[Auth] Attempting Supabase login for:', email);

    if (!this.supabaseClient) {
      console.error('[Auth] Supabase client not configured');
      throw new Error('Supabase not configured');
    }

    const { data, error } = await this.supabaseClient.auth.signInWithPassword({
      email,
      password
    });

    if (error) {
      console.error('[Auth] Login failed:', error.message);
      throw new Error(error.message);
    }

    console.log('[Auth] Login successful for:', email);
    // Session will be handled by onAuthStateChange
    return this.user;
  },

  async signUpWithToken(token, email, password, name) {
    console.log('[Auth] Starting signup with token for:', email);

    if (this.isLocalDev) {
      console.error('[Auth] Sign up not available in dev mode');
      throw new Error('Sign up not available in dev mode');
    }

    if (!this.supabaseClient) {
      console.error('[Auth] Supabase client not configured');
      throw new Error('Supabase not configured');
    }

    // Step 1: Validate the invite token with the backend (via /api/sales proxy)
    console.log('[Auth] Validating invite token with backend...');

    const validateResponse = await fetch('/api/sales/auth/validate-invite', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, email })
    });

    if (!validateResponse.ok) {
      const errorData = await validateResponse.json();
      console.error('[Auth] Token validation failed:', errorData.detail || 'Unknown error');
      throw new Error(errorData.detail || 'Invalid or expired invite token');
    }

    const tokenData = await validateResponse.json();
    console.log('[Auth] Token validated, role:', tokenData.role_name);

    // Step 2: Create the user in Supabase Auth
    console.log('[Auth] Creating Supabase user...');
    const { data, error } = await this.supabaseClient.auth.signUp({
      email,
      password,
      options: {
        data: {
          name: name,
          roles: [tokenData.role_name || 'user']
        }
      }
    });

    if (error) {
      console.error('[Auth] Supabase signup failed:', error.message);
      throw new Error(error.message);
    }

    console.log('[Auth] Signup successful for:', email);
    // Step 3: Mark token as used (backend will handle this on first API call with user sync)
    // The token will be consumed when the user makes their first authenticated request

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
    document.body.classList.remove('modal-open');
  },

  showLogin() {
    document.getElementById('loginModal').classList.add('active');
    document.body.classList.add('modal-open');
  },

  hideLogin() {
    document.getElementById('loginModal').classList.remove('active');
    document.body.classList.remove('modal-open');
  },

  showApp() {
    document.getElementById('landingPage').style.display = 'none';
    document.getElementById('loginModal').classList.remove('active');
    document.body.classList.remove('modal-open');
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

  // Close modal when clicking outside (on the modal backdrop)
  const loginModal = document.getElementById('loginModal');
  if (loginModal) {
    loginModal.addEventListener('click', (e) => {
      // Only close if clicking directly on the modal backdrop, not on the content
      if (e.target === loginModal) {
        Auth.hideLogin();
      }
    });
  }

  // Auth tab switching
  const signInTab = document.getElementById('signInTab');
  const signUpTab = document.getElementById('signUpTab');
  const loginForm = document.getElementById('loginForm');
  const signupForm = document.getElementById('signupForm');
  const authSubtitle = document.getElementById('authSubtitle');
  const devModeHint = document.getElementById('devModeHint');

  function switchToSignIn() {
    signInTab.classList.add('active');
    signInTab.style.background = 'var(--neural-800)';
    signInTab.style.color = 'var(--neural-100)';
    signUpTab.classList.remove('active');
    signUpTab.style.background = 'var(--neural-900)';
    signUpTab.style.color = 'var(--neural-500)';
    loginForm.style.display = 'block';
    signupForm.style.display = 'none';
    authSubtitle.textContent = 'Sign in to continue to your workspace';
    if (devModeHint) devModeHint.style.display = 'block';
  }

  function switchToSignUp() {
    signUpTab.classList.add('active');
    signUpTab.style.background = 'var(--neural-800)';
    signUpTab.style.color = 'var(--neural-100)';
    signInTab.classList.remove('active');
    signInTab.style.background = 'var(--neural-900)';
    signInTab.style.color = 'var(--neural-500)';
    signupForm.style.display = 'block';
    loginForm.style.display = 'none';
    authSubtitle.textContent = 'Create your account with an invite token';
    if (devModeHint) devModeHint.style.display = 'none';
  }

  if (signInTab) {
    signInTab.addEventListener('click', switchToSignIn);
  }
  if (signUpTab) {
    signUpTab.addEventListener('click', switchToSignUp);
  }

  // Login form submission
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

  // Sign up form submission
  if (signupForm) {
    signupForm.addEventListener('submit', async (e) => {
      e.preventDefault();

      const token = document.getElementById('signupTokenInput').value.trim();
      const email = document.getElementById('signupEmailInput').value.trim();
      const name = document.getElementById('signupNameInput').value.trim();
      const password = document.getElementById('signupPasswordInput').value;
      const confirmPassword = document.getElementById('signupConfirmPasswordInput').value;
      const submitBtn = signupForm.querySelector('button[type="submit"]');

      // Validate passwords match
      if (password !== confirmPassword) {
        Toast.error('Passwords do not match');
        return;
      }

      // Validate password length
      if (password.length < 8) {
        Toast.error('Password must be at least 8 characters');
        return;
      }

      try {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Creating account...';

        await Auth.signUpWithToken(token, email, password, name);

        Toast.success('Account created! Please check your email to verify, then sign in.');

        // Switch to sign in tab
        switchToSignIn();
        document.getElementById('emailInput').value = email;
      } catch (error) {
        Toast.error(error.message || 'Sign up failed');
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Create Account';
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

// Password visibility toggle function
function togglePasswordVisibility(inputId, button) {
  const input = document.getElementById(inputId);
  const eyeOpen = button.querySelector('.eye-open');
  const eyeClosed = button.querySelector('.eye-closed');

  if (input.type === 'password') {
    input.type = 'text';
    eyeOpen.style.display = 'none';
    eyeClosed.style.display = 'block';
  } else {
    input.type = 'password';
    eyeOpen.style.display = 'block';
    eyeClosed.style.display = 'none';
  }
}

// Make it globally available
window.togglePasswordVisibility = togglePasswordVisibility;

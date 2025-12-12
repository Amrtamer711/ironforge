/**
 * Auth Module - Handles authentication via Microsoft SSO (Supabase)
 * Production: Microsoft SSO only
 * Local Dev: Simple email/password for testing
 */

const Auth = {
  user: null,
  supabaseClient: null,
  isLocalDev: window.location.hostname === 'localhost' && !window.SUPABASE_URL,

  // Dev users for local testing only (when Supabase is not configured)
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

    // Check for auth errors in URL hash (e.g., from OAuth redirects)
    this.handleAuthHashError();

    // Initialize Supabase client if configured
    if (window.SUPABASE_URL && window.SUPABASE_ANON_KEY && typeof supabase !== 'undefined') {
      console.log('[Auth] Creating Supabase client...');
      this.supabaseClient = supabase.createClient(window.SUPABASE_URL, window.SUPABASE_ANON_KEY);
      this.isLocalDev = false;

      // Listen for auth state changes (handles OAuth redirect callback)
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
      console.log('[Auth] Running in local dev mode (no Supabase)');
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

  async handleSession(session) {
    const user = session.user;

    // Store token first for API requests
    localStorage.setItem('authToken', session.access_token);

    // Fetch user's profile from the users table (the source of truth for RBAC)
    let profileName = 'sales_user'; // Default fallback
    try {
      const response = await fetch('/api/base/auth/me', {
        headers: {
          'Authorization': `Bearer ${session.access_token}`
        }
      });

      // Check if user was deleted/deactivated/pending approval
      if (response.status === 403) {
        const errorData = await response.json();
        if (errorData.requiresLogout) {
          console.error('[Auth] User account issue:', errorData.code);

          // Handle pending approval specially - show the pending screen instead of logout
          if (errorData.code === 'USER_PENDING_APPROVAL') {
            this.showAccessPending(user.email, errorData.error);
            return;
          }

          await this.logout();
          if (window.Toast) {
            Toast.error(errorData.error || 'Your account has been removed or deactivated');
          }
          return;
        }
      }

      if (response.ok) {
        const data = await response.json();
        profileName = data.profile_name || data.profile || 'sales_user';
        console.log('[Auth] User profile from server:', profileName);
      }
    } catch (err) {
      console.warn('[Auth] Could not fetch user profile, using default:', err.message);
      // Fallback to user_metadata if server call fails
      profileName = user.user_metadata?.profile || 'sales_user';
    }

    // Map profile to roles for backward compatibility
    const profileToRoles = {
      'system_admin': ['admin', 'hos', 'sales_person'],
      'sales_manager': ['hos', 'sales_person'],
      'sales_user': ['sales_person'],
      'coordinator': ['coordinator'],
      'finance': ['finance'],
      'viewer': ['viewer']
    };

    // Build user object from Supabase user
    // Microsoft Azure sends name in full_name field
    const userName = user.user_metadata?.full_name
      || user.user_metadata?.name
      || user.identities?.[0]?.identity_data?.full_name
      || user.identities?.[0]?.identity_data?.name
      || user.email?.split('@')[0]
      || 'User';

    this.user = {
      id: user.id,
      email: user.email,
      name: userName,
      profile: profileName,
      roles: profileToRoles[profileName] || ['sales_person']
    };

    localStorage.setItem('userData', JSON.stringify(this.user));
    console.log('[Auth] Session established for:', this.user.email, 'with profile:', profileName);

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

  /**
   * Sign in with Microsoft SSO via Supabase OAuth
   */
  async loginWithMicrosoft() {
    console.log('[Auth] Initiating Microsoft SSO login...');

    if (!this.supabaseClient) {
      console.error('[Auth] Supabase client not configured');
      throw new Error('Supabase not configured. Please contact your administrator.');
    }

    const { data, error } = await this.supabaseClient.auth.signInWithOAuth({
      provider: 'azure',
      options: {
        scopes: 'email profile openid',
        redirectTo: window.location.origin  // Redirect back to this origin after SSO
      }
    });

    if (error) {
      console.error('[Auth] Microsoft SSO failed:', error.message);
      throw new Error(error.message);
    }

    // User will be redirected to Microsoft, then back to our app
    // onAuthStateChange will handle the session when they return
    console.log('[Auth] Redirecting to Microsoft for authentication...');
    return data;
  },

  /**
   * Show the access pending screen for unapproved users
   */
  showAccessPending(email, message) {
    console.log('[Auth] Showing access pending screen for:', email);

    // Hide loading screen
    const loadingScreen = document.getElementById('loadingScreen');
    if (loadingScreen) loadingScreen.classList.add('hidden');

    // Hide landing, login modal, and app
    document.getElementById('landingPage').style.display = 'none';
    document.getElementById('loginModal').classList.remove('active');
    document.body.classList.remove('modal-open');
    document.getElementById('app').style.display = 'none';

    // Show access pending screen (create it if it doesn't exist)
    let pendingScreen = document.getElementById('accessPendingScreen');
    if (!pendingScreen) {
      pendingScreen = document.createElement('div');
      pendingScreen.id = 'accessPendingScreen';
      pendingScreen.innerHTML = `
        <div class="pending-container">
          <div class="pending-icon">
            <svg width="80" height="80" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </svg>
          </div>
          <h1>Access Pending</h1>
          <p class="pending-message">${message || 'Your account is pending administrator approval.'}</p>
          <p class="pending-email">Signed in as: <strong>${email}</strong></p>
          <p class="pending-instructions">
            Please contact your administrator to request access to the platform.
            Once approved, you'll be able to sign in and use the system.
          </p>
          <button class="btn btn-secondary" onclick="Auth.logout()">
            Sign Out
          </button>
        </div>
      `;
      pendingScreen.style.cssText = `
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 100vh;
        background: var(--neural-950);
        color: var(--neural-100);
      `;
      const style = document.createElement('style');
      style.textContent = `
        #accessPendingScreen .pending-container {
          text-align: center;
          max-width: 480px;
          padding: 3rem;
        }
        #accessPendingScreen .pending-icon {
          color: var(--accent-amber);
          margin-bottom: 1.5rem;
        }
        #accessPendingScreen h1 {
          font-size: 2rem;
          font-weight: 700;
          margin-bottom: 1rem;
        }
        #accessPendingScreen .pending-message {
          color: var(--neural-300);
          font-size: 1.1rem;
          margin-bottom: 1rem;
        }
        #accessPendingScreen .pending-email {
          color: var(--neural-400);
          margin-bottom: 1.5rem;
        }
        #accessPendingScreen .pending-instructions {
          color: var(--neural-500);
          font-size: 0.9rem;
          margin-bottom: 2rem;
          line-height: 1.6;
        }
      `;
      document.head.appendChild(style);
      document.body.appendChild(pendingScreen);
    } else {
      // Update existing screen
      pendingScreen.querySelector('.pending-message').textContent = message || 'Your account is pending administrator approval.';
      pendingScreen.querySelector('.pending-email strong').textContent = email;
    }

    pendingScreen.style.display = 'flex';
  },

  /**
   * Hide the access pending screen
   */
  hideAccessPending() {
    const pendingScreen = document.getElementById('accessPendingScreen');
    if (pendingScreen) {
      pendingScreen.style.display = 'none';
    }
  },

  /**
   * DEPRECATED: Sign up with invite token
   * This method is deprecated in favor of Microsoft SSO authentication.
   * New users should sign in via Microsoft SSO. If pre-approved by admin,
   * they get immediate access. If not, they see the "Access Pending" screen.
   */
  async signUpWithToken(token, email, password, name) {
    console.warn('[Auth] signUpWithToken is DEPRECATED - use Microsoft SSO instead');
    console.log('[Auth] Starting signup with token for:', email);

    if (this.isLocalDev) {
      console.error('[Auth] Sign up not available in dev mode');
      throw new Error('Sign up not available in dev mode');
    }

    if (!this.supabaseClient) {
      console.error('[Auth] Supabase client not configured');
      throw new Error('Supabase not configured');
    }

    // Step 1: Validate the invite token with unified-ui backend (handles auth/RBAC)
    // NOTE: This does NOT mark the token as used - only validates it
    console.log('[Auth] Validating invite token with backend...');

    const validateResponse = await fetch('/api/base/auth/validate-invite', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, email })
    });

    if (!validateResponse.ok) {
      const errorData = await validateResponse.json();
      console.error('[Auth] Token validation failed:', errorData.error || 'Unknown error');
      throw new Error(errorData.error || 'Invalid or expired invite token');
    }

    const tokenData = await validateResponse.json();
    console.log('[Auth] Token validated, profile:', tokenData.profile_name);

    // Step 2: Create the user in Supabase Auth
    console.log('[Auth] Creating Supabase user...');
    const { data, error } = await this.supabaseClient.auth.signUp({
      email,
      password,
      options: {
        data: {
          name: name,
          profile: tokenData.profile_name || 'sales_user'
        }
      }
    });

    if (error) {
      console.error('[Auth] Supabase signup failed:', error.message);
      throw new Error(error.message);
    }

    // Check if user already exists (Supabase returns user with identities: [] for existing users)
    // This happens when email exists in auth.users but hasn't confirmed yet
    if (data.user && data.user.identities && data.user.identities.length === 0) {
      console.warn('[Auth] User already exists in auth.users - may need to resend confirmation');
      throw new Error('An account with this email already exists. Please check your email for the confirmation link, or contact an administrator to resend it.');
    }

    console.log('[Auth] Signup successful for:', email);
    console.log('[Auth] Signup response data:', JSON.stringify(data, null, 2));
    console.log('[Auth] User ID from signup:', data.user?.id);

    // Step 3: Mark token as used NOW that signup succeeded
    // Also pass user_id so backend can create user in users table with correct profile
    const userId = data.user?.id || data.session?.user?.id;
    console.log('[Auth] Consuming invite token with user_id:', userId);
    try {
      const consumeResponse = await fetch('/api/base/auth/consume-invite', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          token,
          email,
          user_id: userId,  // Pass the Supabase Auth user ID
          name: name        // Pass the user's name
        })
      });

      if (!consumeResponse.ok) {
        // Don't fail the signup if consume fails - user was created successfully
        console.warn('[Auth] Failed to consume token, but signup succeeded');
      } else {
        console.log('[Auth] Invite token consumed successfully');
      }
    } catch (consumeErr) {
      // Don't fail the signup if consume fails
      console.warn('[Auth] Error consuming token:', consumeErr.message);
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

    // Reset module registry
    if (window.ModuleRegistry) {
      ModuleRegistry.reset();
    }

    // Hide access pending screen if shown
    this.hideAccessPending();

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
    // Hide loading screen
    const loadingScreen = document.getElementById('loadingScreen');
    if (loadingScreen) loadingScreen.classList.add('hidden');

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

  async showApp() {
    // Hide loading screen
    const loadingScreen = document.getElementById('loadingScreen');
    if (loadingScreen) loadingScreen.classList.add('hidden');

    document.getElementById('landingPage').style.display = 'none';
    document.getElementById('loginModal').classList.remove('active');
    document.body.classList.remove('modal-open');
    document.getElementById('app').style.display = 'flex';

    // Update UI with user info
    this.updateUserUI();

    // Initialize module registry (handles navigation and tools)
    if (window.ModuleRegistry) {
      await ModuleRegistry.init();
    } else if (window.Sidebar) {
      // Fallback to legacy sidebar if ModuleRegistry not loaded
      Sidebar.init();
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
  },

  handleAuthHashError() {
    // Check URL hash for auth errors from Supabase redirects
    const hash = window.location.hash;
    if (!hash || !hash.includes('error=')) return;

    // Parse hash parameters
    const params = new URLSearchParams(hash.substring(1));
    const error = params.get('error');
    const errorCode = params.get('error_code');
    const errorDescription = params.get('error_description');

    if (error) {
      console.error('[Auth] Auth error in URL:', { error, errorCode, errorDescription });

      // Clear the hash from URL to prevent showing error again on refresh
      history.replaceState(null, '', window.location.pathname);

      // Map error codes to user-friendly messages
      let userMessage = errorDescription ? decodeURIComponent(errorDescription.replace(/\+/g, ' ')) : 'Authentication failed';

      if (errorCode === 'otp_expired') {
        userMessage = 'Email link has expired. Please sign up again to receive a new confirmation email.';
      } else if (errorCode === 'access_denied') {
        userMessage = 'Access denied. The link may have expired or already been used.';
      }

      // Show error after a short delay to ensure Toast is initialized
      setTimeout(() => {
        if (window.Toast) {
          Toast.error(userMessage);
        } else {
          alert(userMessage);
        }
      }, 500);
    }
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

  // Determine which login section to show based on environment
  const ssoLoginSection = document.getElementById('ssoLoginSection');
  const devLoginSection = document.getElementById('devLoginSection');
  const authSubtitle = document.getElementById('authSubtitle');
  const isDevMode = window.location.hostname === 'localhost' && !window.SUPABASE_URL;

  if (isDevMode) {
    // Show dev login form, hide SSO button
    if (ssoLoginSection) ssoLoginSection.style.display = 'none';
    if (devLoginSection) devLoginSection.style.display = 'block';
    if (authSubtitle) authSubtitle.textContent = 'Sign in to continue (Dev Mode)';
  } else {
    // Show SSO button, hide dev login form
    if (ssoLoginSection) ssoLoginSection.style.display = 'block';
    if (devLoginSection) devLoginSection.style.display = 'none';
  }

  // Microsoft SSO button click handler
  const microsoftSsoBtn = document.getElementById('microsoftSsoBtn');
  if (microsoftSsoBtn) {
    microsoftSsoBtn.addEventListener('click', async () => {
      try {
        microsoftSsoBtn.disabled = true;
        microsoftSsoBtn.innerHTML = `
          <svg class="spinner" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation: spin 1s linear infinite;">
            <circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-dashoffset="32"/>
          </svg>
          Connecting to Microsoft...
        `;

        await Auth.loginWithMicrosoft();
        // User will be redirected to Microsoft, so we don't need to do anything else here
      } catch (error) {
        if (window.Toast) {
          Toast.error(error.message || 'Microsoft sign-in failed');
        }
        microsoftSsoBtn.disabled = false;
        microsoftSsoBtn.innerHTML = `
          <svg width="21" height="21" viewBox="0 0 21 21" fill="none">
            <rect width="10" height="10" fill="#f25022"/>
            <rect x="11" width="10" height="10" fill="#7fba00"/>
            <rect y="11" width="10" height="10" fill="#00a4ef"/>
            <rect x="11" y="11" width="10" height="10" fill="#ffb900"/>
          </svg>
          Sign in with Microsoft
        `;
      }
    });
  }

  // Dev mode login form submission
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

        if (window.Toast) Toast.success('Welcome back!');
      } catch (error) {
        if (window.Toast) Toast.error(error.message || 'Login failed');
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
      if (window.Toast) Toast.success('Logged out successfully');
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

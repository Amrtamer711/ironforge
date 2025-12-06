/**
 * API Client - All communication with backend services
 *
 * Endpoint Namespacing:
 * - /api/base/*  → Unified UI's own backend (auth, templates, uploads)
 * - /api/sales/* → Sales Bot service (chat, mockup, proposals, bo)
 * - /api/inventory/* → Future inventory service
 * - /api/analytics/* → Future analytics service
 *
 * Authentication:
 * - Uses Supabase Auth for authentication
 * - Supabase client handles tokens automatically
 * - Backend validates tokens via Supabase Admin SDK
 */

// =============================================================================
// SUPABASE CONFIGURATION
// These will be set from environment or config
// =============================================================================
const SUPABASE_URL = window.SUPABASE_URL || '';
const SUPABASE_ANON_KEY = window.SUPABASE_ANON_KEY || '';

// Initialize Supabase client (if available)
let supabaseClient = null;

// Check if Supabase JS library is loaded
if (typeof supabase !== 'undefined' && SUPABASE_URL && SUPABASE_ANON_KEY) {
  supabaseClient = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
}

const API = {
  // Always use same origin - the unified-ui server proxies to services
  baseUrl: '',

  // Get current auth token from Supabase
  async getAuthToken() {
    if (!supabaseClient) return null;

    const { data: { session } } = await supabaseClient.auth.getSession();
    return session?.access_token || null;
  },

  // Helper for making requests
  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const token = await this.getAuthToken();

    const headers = {
      'Content-Type': 'application/json',
      ...options.headers
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers
      });

      if (response.status === 401) {
        // Token expired or invalid - trigger logout
        if (supabaseClient) {
          await supabaseClient.auth.signOut();
        }
        window.dispatchEvent(new CustomEvent('auth:logout'));
        return null;
      }

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(error.detail || error.error || 'Request failed');
      }

      return response.json();
    } catch (error) {
      console.error(`API Error [${endpoint}]:`, error);
      throw error;
    }
  },

  // ============================================
  // SUPABASE AUTH (Client-side)
  // ============================================
  supabase: {
    getClient() {
      return supabaseClient;
    },

    async signUp(email, password) {
      if (!supabaseClient) throw new Error('Supabase not configured');

      const { data, error } = await supabaseClient.auth.signUp({
        email,
        password
      });

      if (error) throw error;
      return data;
    },

    async signIn(email, password) {
      if (!supabaseClient) throw new Error('Supabase not configured');

      const { data, error } = await supabaseClient.auth.signInWithPassword({
        email,
        password
      });

      if (error) throw error;
      window.dispatchEvent(new CustomEvent('auth:login', { detail: data.user }));
      return data;
    },

    async signOut() {
      if (!supabaseClient) throw new Error('Supabase not configured');

      const { error } = await supabaseClient.auth.signOut();
      if (error) throw error;

      window.dispatchEvent(new CustomEvent('auth:logout'));
      return true;
    },

    async getSession() {
      if (!supabaseClient) return null;

      const { data: { session } } = await supabaseClient.auth.getSession();
      return session;
    },

    async getUser() {
      if (!supabaseClient) return null;

      const { data: { user } } = await supabaseClient.auth.getUser();
      return user;
    },

    // Listen for auth state changes
    onAuthStateChange(callback) {
      if (!supabaseClient) return null;

      return supabaseClient.auth.onAuthStateChange((event, session) => {
        callback(event, session);
      });
    }
  },

  // ============================================
  // BASE ENDPOINTS (Unified UI - Auth only)
  // ============================================
  base: {
    // Check session with backend
    async checkSession() {
      return API.request('/api/base/auth/session');
    }
  },

  // ============================================
  // TEMPLATES (Sales Bot service)
  // ============================================
  templates: {
    async getAll() {
      return API.request('/api/sales/templates');
    },

    async get(locationKey) {
      return API.request(`/api/sales/templates/${locationKey}`);
    },

    async save(data) {
      return API.request('/api/sales/templates', {
        method: 'POST',
        body: JSON.stringify(data)
      });
    },

    async delete(locationKey) {
      return API.request(`/api/sales/templates/${locationKey}`, {
        method: 'DELETE'
      });
    },

    async uploadImage(formData) {
      const token = await API.getAuthToken();
      const response = await fetch(`${API.baseUrl}/api/sales/templates/upload`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });
      return response.json();
    }
  },

  // ============================================
  // SALES ENDPOINTS (Sales Bot service)
  // ============================================
  auth: {
    async login(email, password) {
      return API.request('/api/sales/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password })
      });
    },

    async logout() {
      return API.request('/api/sales/auth/logout', {
        method: 'POST'
      });
    },

    async me() {
      return API.request('/api/sales/auth/me');
    }
  },

  chat: {
    async sendMessage(conversationId, message) {
      return API.request('/api/sales/chat/message', {
        method: 'POST',
        body: JSON.stringify({ conversation_id: conversationId, message })
      });
    },

    async getConversations() {
      return API.request('/api/sales/chat/conversations');
    },

    async getConversation(id) {
      return API.request(`/api/sales/chat/conversation/${id}`);
    },

    async createConversation() {
      return API.request('/api/sales/chat/conversation', {
        method: 'POST'
      });
    },

    async deleteConversation(id) {
      return API.request(`/api/sales/chat/conversation/${id}`, {
        method: 'DELETE'
      });
    },

    // SSE for streaming responses
    async streamMessage(conversationId, message, onChunk, onDone, onError) {
      const token = await API.getAuthToken();
      const url = `${API.baseUrl}/api/sales/chat/stream`;

      fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ conversation_id: conversationId, message })
      }).then(response => {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        function read() {
          reader.read().then(({ done, value }) => {
            if (done) {
              onDone();
              return;
            }

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const data = line.slice(6);
                if (data === '[DONE]') {
                  onDone();
                  return;
                }
                try {
                  const parsed = JSON.parse(data);
                  onChunk(parsed);
                } catch (e) {
                  onChunk({ content: data });
                }
              }
            }

            read();
          }).catch(onError);
        }

        read();
      }).catch(onError);
    }
  },

  mockup: {
    async getLocations() {
      return API.request('/api/sales/mockup/locations');
    },

    async getTemplates(location, timeOfDay, finish) {
      const params = new URLSearchParams();
      if (location) params.append('location', location);
      if (timeOfDay) params.append('time_of_day', timeOfDay);
      if (finish) params.append('finish', finish);
      return API.request(`/api/sales/mockup/templates?${params}`);
    },

    async generate(formData) {
      const token = await API.getAuthToken();
      const response = await fetch(`${API.baseUrl}/api/sales/mockup/generate`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });
      return response.json();
    }
  },

  proposals: {
    async generate(data) {
      return API.request('/api/sales/proposals/generate', {
        method: 'POST',
        body: JSON.stringify(data)
      });
    },

    async getHistory() {
      return API.request('/api/sales/proposals/history');
    }
  },

  bo: {
    async getPending() {
      return API.request('/api/sales/bo/pending');
    },

    async approve(id) {
      return API.request(`/api/sales/bo/${id}/approve`, {
        method: 'POST'
      });
    },

    async reject(id, reason) {
      return API.request(`/api/sales/bo/${id}/reject`, {
        method: 'POST',
        body: JSON.stringify({ reason })
      });
    }
  }
};

// Make API globally available
window.API = API;

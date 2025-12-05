/**
 * API Client - All communication with backend services
 *
 * Endpoint Namespacing:
 * - /api/base/*  → Unified UI's own backend (auth, templates, uploads)
 * - /api/sales/* → Sales Bot service (chat, mockup, proposals, bo)
 * - /api/inventory/* → Future inventory service
 * - /api/analytics/* → Future analytics service
 */

const API = {
  // Always use same origin - the unified-ui server proxies to services
  baseUrl: '',

  // Helper for making requests
  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const token = localStorage.getItem('authToken');

    const headers = {
      'Content-Type': 'application/json',
      ...options.headers
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    // Add session ID for base API auth
    const sessionId = localStorage.getItem('sessionId');
    if (sessionId) {
      headers['x-session-id'] = sessionId;
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers
      });

      if (response.status === 401) {
        // Token expired or invalid
        Auth.logout();
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
  // BASE ENDPOINTS (Unified UI's own backend)
  // ============================================
  base: {
    async login(password) {
      const result = await API.request('/api/base/login', {
        method: 'POST',
        body: JSON.stringify({ password })
      });
      if (result && result.sessionId) {
        localStorage.setItem('sessionId', result.sessionId);
      }
      return result;
    },

    async logout() {
      const result = await API.request('/api/base/logout', {
        method: 'POST'
      });
      localStorage.removeItem('sessionId');
      return result;
    },

    async getTemplates() {
      return API.request('/api/base/templates');
    },

    async getTemplate(locationKey) {
      return API.request(`/api/base/templates/${locationKey}`);
    },

    async saveTemplate(data) {
      return API.request('/api/base/templates', {
        method: 'POST',
        body: JSON.stringify(data)
      });
    },

    async deleteTemplate(locationKey) {
      return API.request(`/api/base/templates/${locationKey}`, {
        method: 'DELETE'
      });
    },

    async uploadImage(formData) {
      const sessionId = localStorage.getItem('sessionId');
      const response = await fetch(`${API.baseUrl}/api/base/upload`, {
        method: 'POST',
        headers: {
          'x-session-id': sessionId
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
    streamMessage(conversationId, message, onChunk, onDone, onError) {
      const token = localStorage.getItem('authToken');
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
      const token = localStorage.getItem('authToken');
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

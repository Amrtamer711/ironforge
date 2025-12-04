/**
 * API Client - All communication with FastAPI backend
 * The unified UI ONLY communicates through these endpoints
 */

const API = {
  baseUrl: window.location.hostname === 'localhost' ? 'http://localhost:8000' : '',

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
        throw new Error(error.detail || 'Request failed');
      }

      return response.json();
    } catch (error) {
      console.error(`API Error [${endpoint}]:`, error);
      throw error;
    }
  },

  // ============================================
  // AUTH ENDPOINTS
  // ============================================
  auth: {
    async login(email, password) {
      return API.request('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password })
      });
    },

    async logout() {
      return API.request('/api/auth/logout', {
        method: 'POST'
      });
    },

    async me() {
      return API.request('/api/auth/me');
    }
  },

  // ============================================
  // CHAT ENDPOINTS
  // ============================================
  chat: {
    async sendMessage(conversationId, message) {
      return API.request('/api/chat/message', {
        method: 'POST',
        body: JSON.stringify({ conversation_id: conversationId, message })
      });
    },

    async getConversations() {
      return API.request('/api/chat/conversations');
    },

    async getConversation(id) {
      return API.request(`/api/chat/conversation/${id}`);
    },

    async createConversation() {
      return API.request('/api/chat/conversation', {
        method: 'POST'
      });
    },

    async deleteConversation(id) {
      return API.request(`/api/chat/conversation/${id}`, {
        method: 'DELETE'
      });
    },

    // SSE for streaming responses
    streamMessage(conversationId, message, onChunk, onDone, onError) {
      const token = localStorage.getItem('authToken');
      const url = `${API.baseUrl}/api/chat/stream`;

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

  // ============================================
  // MOCKUP ENDPOINTS (existing)
  // ============================================
  mockup: {
    async getLocations() {
      return API.request('/api/mockup/locations');
    },

    async getTemplates(location, timeOfDay, finish) {
      const params = new URLSearchParams();
      if (location) params.append('location', location);
      if (timeOfDay) params.append('time_of_day', timeOfDay);
      if (finish) params.append('finish', finish);
      return API.request(`/api/mockup/templates?${params}`);
    },

    async generate(formData) {
      const token = localStorage.getItem('authToken');
      const response = await fetch(`${API.baseUrl}/api/mockup/generate`, {
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
  // PROPOSAL ENDPOINTS
  // ============================================
  proposals: {
    async generate(data) {
      return API.request('/api/proposals/generate', {
        method: 'POST',
        body: JSON.stringify(data)
      });
    },

    async getHistory() {
      return API.request('/api/proposals/history');
    }
  },

  // ============================================
  // BO ENDPOINTS
  // ============================================
  bo: {
    async getPending() {
      return API.request('/api/bo/pending');
    },

    async approve(id) {
      return API.request(`/api/bo/${id}/approve`, {
        method: 'POST'
      });
    },

    async reject(id, reason) {
      return API.request(`/api/bo/${id}/reject`, {
        method: 'POST',
        body: JSON.stringify({ reason })
      });
    }
  }
};

// Make API globally available
window.API = API;

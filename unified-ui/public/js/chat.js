/**
 * Chat Module - ChatGPT-style interface
 * Connected to FastAPI backend for real LLM responses
 */

const Chat = {
  conversationId: null,
  messages: [],
  isStreaming: false,
  pendingFile: null,

  init() {
    console.log('[Chat] Initializing...');
    this.setupInput();
    this.setupSuggestions();
    this.setupFileUpload();
    this.updateTimeGreeting();
    console.log('[Chat] Initialized');
  },

  updateTimeGreeting() {
    const greetingEl = document.getElementById('timeGreeting');
    if (!greetingEl) return;
    
    const hour = new Date().getHours();
    let greeting = 'day';
    
    if (hour >= 5 && hour < 12) {
      greeting = 'morning';
    } else if (hour >= 12 && hour < 17) {
      greeting = 'afternoon';
    } else if (hour >= 17 && hour < 21) {
      greeting = 'evening';
    } else {
      greeting = 'night';
    }
    
    greetingEl.textContent = greeting;
  },

  setupInput() {
    const chatInput = document.getElementById('chatInput');
    const sendBtn = document.getElementById('chatSendBtn');

    if (!chatInput || !sendBtn) return;

    // Auto-resize textarea
    chatInput.addEventListener('input', () => {
      chatInput.style.height = 'auto';
      chatInput.style.height = Math.min(chatInput.scrollHeight, 150) + 'px';

      // Enable/disable send button
      sendBtn.disabled = !chatInput.value.trim() || this.isStreaming;
    });

    // Send on Enter (without Shift)
    chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!sendBtn.disabled) {
          this.sendMessage();
        }
      }
    });

    // Send button click
    sendBtn.addEventListener('click', () => {
      this.sendMessage();
    });
  },

  setupSuggestions() {
    const suggestions = document.querySelectorAll('.suggestion-btn');

    suggestions.forEach(btn => {
      btn.addEventListener('click', () => {
        const chatInput = document.getElementById('chatInput');
        if (chatInput) {
          // Use data-prompt attribute if available, fallback to title text
          const prompt = btn.dataset.prompt || btn.querySelector('.suggestion-title')?.textContent || btn.textContent;
          chatInput.value = prompt;
          chatInput.focus();
          chatInput.dispatchEvent(new Event('input'));
        }
      });
    });
  },

  setupFileUpload() {
    const attachBtn = document.getElementById('chatAttachBtn');
    const fileInput = document.getElementById('chatFileInput');
    const filePreview = document.getElementById('chatFilePreview');
    const filePreviewName = document.getElementById('filePreviewName');
    const removeFileBtn = document.getElementById('removeFileBtn');

    if (!attachBtn || !fileInput) return;

    // Click attach button to open file picker
    attachBtn.addEventListener('click', () => {
      fileInput.click();
    });

    // Handle file selection
    fileInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (file) {
        this.pendingFile = file;
        filePreviewName.textContent = file.name;
        filePreview.style.display = 'block';

        // Update send button state
        const sendBtn = document.getElementById('chatSendBtn');
        const chatInput = document.getElementById('chatInput');
        if (sendBtn) {
          sendBtn.disabled = !chatInput.value.trim() && !this.pendingFile;
        }
      }
    });

    // Remove file
    if (removeFileBtn) {
      removeFileBtn.addEventListener('click', () => {
        this.pendingFile = null;
        fileInput.value = '';
        filePreview.style.display = 'none';

        // Update send button state
        const sendBtn = document.getElementById('chatSendBtn');
        const chatInput = document.getElementById('chatInput');
        if (sendBtn) {
          sendBtn.disabled = !chatInput.value.trim();
        }
      });
    }
  },

  async sendMessage() {
    const chatInput = document.getElementById('chatInput');
    const sendBtn = document.getElementById('chatSendBtn');
    const filePreview = document.getElementById('chatFilePreview');
    const fileInput = document.getElementById('chatFileInput');

    const message = chatInput?.value.trim() || '';
    const hasFile = this.pendingFile !== null;

    // Must have message or file
    if (!message && !hasFile) return;

    console.log('[Chat] Sending message:', message.substring(0, 50) + (message.length > 50 ? '...' : ''));
    if (hasFile) {
      console.log('[Chat] With file attachment:', this.pendingFile.name);
    }

    // Capture file before clearing
    const fileToSend = this.pendingFile;

    // Clear input and file
    if (chatInput) {
      chatInput.value = '';
      chatInput.style.height = 'auto';
    }
    if (filePreview) filePreview.style.display = 'none';
    if (fileInput) fileInput.value = '';
    this.pendingFile = null;

    sendBtn.disabled = true;
    this.isStreaming = true;

    // Hide welcome screen
    this.hideWelcome();

    // Add user message (with file indicator if applicable)
    let displayMessage = message;
    if (fileToSend) {
      const fileIndicator = `[Attached: ${fileToSend.name}]`;
      displayMessage = message ? `${message}\n${fileIndicator}` : fileIndicator;
    }
    this.addMessage('user', displayMessage);

    // Add assistant message placeholder
    const assistantMsgId = this.addMessage('assistant', '', true);

    try {
      console.log('[Chat] Calling API stream...');
      // Always try to use the real API first
      await this.apiStreamResponse(assistantMsgId, message, fileToSend);
      console.log('[Chat] Stream completed successfully');
    } catch (error) {
      console.error('[Chat] API error:', error.message);
      // Fallback to mock if API fails
      if (error.message && error.message.includes('Failed to fetch')) {
        this.updateMessage(assistantMsgId, 'Unable to connect to the server. Please make sure the FastAPI backend is running on port 8000.');
      } else {
        this.updateMessage(assistantMsgId, 'Sorry, there was an error processing your request. Please try again.');
      }
      Toast.error('Failed to get response');
    } finally {
      this.isStreaming = false;
      sendBtn.disabled = !(chatInput?.value.trim() || this.pendingFile);
    }
  },

  async apiStreamResponse(msgId, userMessage, file = null) {
    // Get user info from Auth
    const user = Auth.user || {};
    const userId = user.id || 'web-user-default';
    const userName = user.name || 'Web User';
    const roles = user.roles || ['sales_person'];

    console.log('[Chat] Stream request - User:', userId, 'Roles:', roles);

    // Use streaming endpoint (via /api/sales proxy)
    const url = `${API.baseUrl}/api/sales/chat/stream`;
    const token = localStorage.getItem('authToken');
    console.log('[Chat] Streaming to:', url, 'Token:', token ? 'present' : 'missing');

    // Build request body
    const requestBody = {
      message: userMessage || (file ? `Please process this file: ${file.name}` : ''),
      conversation_id: this.conversationId,
      user_id: userId,
      user_name: userName,
      roles: roles
    };

    // If there's a file, add file info (actual upload handled separately)
    if (file) {
      requestBody.files = [{
        filename: file.name,
        mimetype: file.type,
        size: file.size
      }];
    }

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(requestBody)
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let fullContent = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split('\n');

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') {
            continue;
          }
          try {
            const parsed = JSON.parse(data);

            if (parsed.error) {
              this.updateMessage(msgId, `Error: ${parsed.error}`);
              return;
            }

            if (parsed.type === 'chunk' && parsed.content) {
              fullContent += parsed.content;
              this.updateMessage(msgId, fullContent);
            } else if (parsed.type === 'content' && parsed.content) {
              fullContent = parsed.content;
              this.updateMessage(msgId, fullContent);
            } else if (parsed.type === 'tool_call') {
              // Handle tool calls - show processing message
              const toolName = parsed.tool?.name || 'processing';
              this.updateMessage(msgId, `_Processing ${toolName}..._`);
            }
          } catch (e) {
            // If not valid JSON, treat as plain text chunk
            if (data.trim()) {
              fullContent += data;
              this.updateMessage(msgId, fullContent);
            }
          }
        }
      }
    }

    // If we got no content, show a default message
    if (!fullContent) {
      this.updateMessage(msgId, 'I\'m ready to help. What would you like to do?');
    }
  },

  async nonStreamingResponse(msgId, userMessage) {
    // Fallback non-streaming version
    const user = Auth.user || {};
    const userId = user.id || 'web-user-default';
    const userName = user.name || 'Web User';
    const roles = user.roles || ['sales_person'];

    try {
      const response = await API.chat.sendMessage(this.conversationId, userMessage);

      if (response && response.content) {
        this.updateMessage(msgId, response.content);
      } else if (response && response.error) {
        this.updateMessage(msgId, `Error: ${response.error}`);
      } else {
        this.updateMessage(msgId, 'I\'m ready to help. What would you like to do?');
      }
    } catch (error) {
      throw error;
    }
  },

  hideWelcome() {
    const welcome = document.querySelector('.chat-welcome');
    if (welcome) {
      welcome.style.display = 'none';
    }
  },

  addMessage(role, content, isStreaming = false) {
    const messagesContainer = document.getElementById('chatMessages');
    if (!messagesContainer) return null;

    const msgId = 'msg-' + Date.now();
    const isUser = role === 'user';

    const avatar = isUser
      ? `<span>${Auth.user?.name?.charAt(0) || 'U'}</span>`
      : 'AI';

    const msgHtml = `
      <div class="chat-msg ${role}" id="${msgId}">
        <div class="chat-msg-avatar">${avatar}</div>
        <div class="chat-msg-content">
          <div class="chat-msg-bubble">${content}${isStreaming && !content ? '<span class="typing-indicator">...</span>' : ''}</div>
        </div>
      </div>
    `;

    messagesContainer.insertAdjacentHTML('beforeend', msgHtml);

    // Scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    // Store message
    this.messages.push({ id: msgId, role, content });

    return msgId;
  },

  updateMessage(msgId, content) {
    const msgEl = document.getElementById(msgId);
    if (msgEl) {
      const bubble = msgEl.querySelector('.chat-msg-bubble');
      if (bubble) {
        // Convert markdown-like formatting
        let formatted = content
          .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
          .replace(/`([^`]+)`/g, '<code>$1</code>')
          .replace(/_(.*?)_/g, '<em>$1</em>')
          .replace(/\n/g, '<br>');
        bubble.innerHTML = formatted;
      }
    }

    // Update stored message
    const msg = this.messages.find(m => m.id === msgId);
    if (msg) {
      msg.content = content;
    }

    // Scroll to bottom
    const messagesContainer = document.getElementById('chatMessages');
    if (messagesContainer) {
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
  },

  clearChat() {
    const messagesContainer = document.getElementById('chatMessages');
    if (messagesContainer) {
      // Get time-based greeting
      const hour = new Date().getHours();
      let greeting = 'day';
      if (hour >= 5 && hour < 12) greeting = 'morning';
      else if (hour >= 12 && hour < 17) greeting = 'afternoon';
      else if (hour >= 17 && hour < 21) greeting = 'evening';
      else greeting = 'night';

      messagesContainer.innerHTML = `
        <div class="chat-welcome">
          <!-- Animated orbs background -->
          <div class="welcome-orbs">
            <div class="welcome-orb orb-1"></div>
            <div class="welcome-orb orb-2"></div>
            <div class="welcome-orb orb-3"></div>
          </div>
          
          <!-- Main logo animation -->
          <div class="welcome-logo-container">
            <div class="welcome-logo-ring ring-outer"></div>
            <div class="welcome-logo-ring ring-middle"></div>
            <div class="welcome-logo-ring ring-inner"></div>
            <div class="welcome-logo-core">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                <path d="M2 17l10 5 10-5"/>
                <path d="M2 12l10 5 10-5"/>
              </svg>
            </div>
          </div>
          
          <div class="welcome-text-container">
            <h2 class="welcome-title">
              <span class="welcome-greeting">Good <span id="timeGreeting">${greeting}</span>,</span>
              <span class="welcome-question">How can I help?</span>
            </h2>
            <p class="welcome-subtitle">Your AI assistant for proposals, mockups & business intelligence</p>
          </div>
          
          <div class="welcome-suggestions">
            <button class="suggestion-btn" data-prompt="Generate a sales proposal">
              <div class="suggestion-icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                  <line x1="16" y1="13" x2="8" y2="13"/>
                  <line x1="16" y1="17" x2="8" y2="17"/>
                </svg>
              </div>
              <div class="suggestion-content">
                <span class="suggestion-title">Sales Proposal</span>
                <span class="suggestion-desc">Generate professional proposals</span>
              </div>
              <div class="suggestion-arrow">→</div>
            </button>
            
            <button class="suggestion-btn" data-prompt="Create a billboard mockup">
              <div class="suggestion-icon icon-cyan">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="3" y="3" width="18" height="18" rx="2"/>
                  <circle cx="8.5" cy="8.5" r="1.5"/>
                  <path d="M21 15l-5-5L5 21"/>
                </svg>
              </div>
              <div class="suggestion-content">
                <span class="suggestion-title">Billboard Mockup</span>
                <span class="suggestion-desc">Create stunning visuals</span>
              </div>
              <div class="suggestion-arrow">→</div>
            </button>
            
            <button class="suggestion-btn" data-prompt="Check booking orders">
              <div class="suggestion-icon icon-purple">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/>
                  <rect x="9" y="3" width="6" height="4" rx="1"/>
                  <path d="M9 14l2 2 4-4"/>
                </svg>
              </div>
              <div class="suggestion-content">
                <span class="suggestion-title">Booking Orders</span>
                <span class="suggestion-desc">Review & manage BOs</span>
              </div>
              <div class="suggestion-arrow">→</div>
            </button>
            
            <button class="suggestion-btn" data-prompt="List available locations">
              <div class="suggestion-icon icon-green">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
                  <circle cx="12" cy="10" r="3"/>
                </svg>
              </div>
              <div class="suggestion-content">
                <span class="suggestion-title">Locations</span>
                <span class="suggestion-desc">Browse available spots</span>
              </div>
              <div class="suggestion-arrow">→</div>
            </button>
          </div>
          
          <div class="welcome-footer">
            <div class="welcome-tip">
              <span class="tip-icon">💡</span>
              <span>Pro tip: Upload files by clicking the paperclip or drag & drop</span>
            </div>
          </div>
        </div>
      `;

      // Re-setup suggestions
      this.setupSuggestions();
    }

    this.messages = [];
    this.conversationId = null;

    // Clear on server too
    if (Auth.user) {
      API.chat.deleteConversation(this.conversationId).catch(() => {});
    }
  }
};

// Make Chat globally available
window.Chat = Chat;

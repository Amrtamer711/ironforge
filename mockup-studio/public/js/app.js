// Mockup Studio - Main Application
class MockupStudio {
  constructor() {
    this.sessionId = localStorage.getItem('mockup_studio_session');
    this.canvas = null;
    this.ctx = null;
    this.image = null;
    this.frames = [];
    this.currentFrame = null;
    this.isDrawing = false;
    this.startX = 0;
    this.startY = 0;
    this.zoom = 1;
    this.panX = 0;
    this.panY = 0;
    this.isPanning = false;
    this.lastPanX = 0;
    this.lastPanY = 0;
    this.pixelUpscale = false;
    this.edgeBlur = 8;
    this.mode = 'create'; // 'create' or 'edit'
    this.editTemplate = null;
    this.currentFrameIndex = 0;

    this.init();
  }

  init() {
    this.setupLoginForm();

    if (this.sessionId) {
      this.showApp();
    }
  }

  setupLoginForm() {
    const loginForm = document.getElementById('loginForm');
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      await this.handleLogin();
    });
  }

  async handleLogin() {
    const password = document.getElementById('passwordInput').value;

    try {
      const response = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password })
      });

      const data = await response.json();

      if (data.success) {
        this.sessionId = data.sessionId;
        localStorage.setItem('mockup_studio_session', this.sessionId);
        this.showApp();
        this.showToast('Login successful!', 'success');
      } else {
        this.showToast('Invalid password', 'error');
      }
    } catch (err) {
      this.showToast('Login failed', 'error');
      console.error(err);
    }
  }

  showApp() {
    document.getElementById('loginModal').classList.remove('active');
    document.getElementById('app').style.display = 'block';

    // Initialize canvas and event listeners
    this.canvas = document.getElementById('canvas');
    this.ctx = this.canvas.getContext('2d');
    this.setupEventListeners();
    this.loadLocations();
  }

  getAuthHeaders() {
    return {
      'Content-Type': 'application/json',
      'X-Session-Id': this.sessionId
    };
  }

  handleUnauthorized() {
    localStorage.removeItem('mockup_studio_session');
    this.sessionId = null;
    this.showToast('Session expired. Please login again.', 'error');
    setTimeout(() => {
      window.location.reload();
    }, 1500);
  }

  setupEventListeners() {
    // Mode switching
    document.querySelectorAll('.mode-btn').forEach(btn => {
      btn.addEventListener('click', (e) => this.switchMode(e.target.dataset.mode));
    });

    // Upload
    const uploadZone = document.getElementById('uploadZone');
    const imageUpload = document.getElementById('imageUpload');

    uploadZone.addEventListener('click', () => imageUpload.click());
    imageUpload.addEventListener('change', (e) => this.handleImageUpload(e));

    // Drag and drop
    uploadZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      uploadZone.classList.add('drag-over');
    });

    uploadZone.addEventListener('dragleave', () => {
      uploadZone.classList.remove('drag-over');
    });

    uploadZone.addEventListener('drop', (e) => {
      e.preventDefault();
      uploadZone.classList.remove('drag-over');
      const files = e.dataTransfer.files;
      if (files.length > 0) {
        this.loadImageFile(files[0]);
      }
    });

    // Location select
    document.getElementById('locationSelect').addEventListener('change', (e) => {
      if (e.target.value) {
        this.startFrameSetup();
      }
    });

    // Zoom controls
    document.getElementById('zoomIn').addEventListener('click', () => this.changeZoom(0.1));
    document.getElementById('zoomOut').addEventListener('click', () => this.changeZoom(-0.1));
    document.getElementById('zoomFit').addEventListener('click', () => this.fitToScreen());
    document.getElementById('pixelUpscale').addEventListener('change', (e) => {
      this.pixelUpscale = e.target.checked;
      this.canvas.classList.toggle('pixel-upscale', this.pixelUpscale);
      this.redraw();
    });

    // Edge blur slider
    document.getElementById('edgeBlur').addEventListener('input', (e) => {
      this.edgeBlur = parseInt(e.target.value);
      document.getElementById('blurValue').textContent = this.edgeBlur;
    });

    // Canvas interaction
    this.canvas.addEventListener('mousedown', (e) => this.handleMouseDown(e));
    this.canvas.addEventListener('mousemove', (e) => this.handleMouseMove(e));
    this.canvas.addEventListener('mouseup', (e) => this.handleMouseUp(e));
    this.canvas.addEventListener('wheel', (e) => this.handleWheel(e));

    // Control buttons
    document.getElementById('undoBtn').addEventListener('click', () => this.undo());
    document.getElementById('nextFrameBtn').addEventListener('click', () => this.nextFrame());
    document.getElementById('finishBtn').addEventListener('click', () => this.finish());

    // Modal
    document.getElementById('viewTemplatesBtn').addEventListener('click', () => this.showTemplatesModal());
    document.getElementById('closeModal').addEventListener('click', () => this.hideTemplatesModal());

    // Click outside modal to close
    document.getElementById('templatesModal').addEventListener('click', (e) => {
      if (e.target.id === 'templatesModal') {
        this.hideTemplatesModal();
      }
    });
  }

  switchMode(mode) {
    this.mode = mode;
    document.querySelectorAll('.mode-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === mode);
    });

    document.querySelectorAll('.mode-content').forEach(content => {
      content.classList.toggle('active', content.id === `${mode}Mode`);
    });

    if (mode === 'edit') {
      this.loadTemplatesForEdit();
    }
  }

  async loadLocations() {
    // For now, use dummy locations. In production, fetch from API
    const select = document.getElementById('locationSelect');
    const locations = [
      'dubai_gateway',
      'dubai_jawhara',
      'triple_crown',
      'the_landmark',
      'oryx_billboard'
    ];

    locations.forEach(loc => {
      const option = document.createElement('option');
      option.value = loc;
      option.textContent = loc.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
      select.appendChild(option);
    });
  }

  async handleImageUpload(e) {
    const file = e.target.files[0];
    if (file) {
      await this.loadImageFile(file);
    }
  }

  async loadImageFile(file) {
    const formData = new FormData();
    formData.append('image', file);

    try {
      const response = await fetch('/api/upload', {
        method: 'POST',
        headers: {
          'X-Session-Id': this.sessionId
        },
        body: formData
      });

      if (response.status === 401) {
        this.handleUnauthorized();
        return;
      }

      const data = await response.json();

      if (data.success) {
        this.loadImage(data.imageUrl);
        document.getElementById('locationSelectGroup').style.display = 'block';
        this.showToast('Image uploaded successfully!', 'success');
      }
    } catch (err) {
      this.showToast('Failed to upload image', 'error');
      console.error(err);
    }
  }

  loadImage(url) {
    this.image = new Image();
    this.image.onload = () => {
      this.canvas.width = this.image.width;
      this.canvas.height = this.image.height;
      this.fitToScreen();
      this.redraw();
    };
    this.image.src = url;
  }

  startFrameSetup() {
    const locationKey = document.getElementById('locationSelect').value;
    if (!locationKey) return;

    // Show editor
    document.getElementById('editorSection').style.display = 'block';
    document.getElementById('editorSection').scrollIntoView({ behavior: 'smooth' });

    // For demo, assume 3 frames. In production, get from location metadata
    this.totalFrames = 3;
    this.currentFrameIndex = 0;
    this.frames = [];
    this.updateProgress();

    this.showToast('Click and drag to define the first frame', 'success');
  }

  startFrameEdit(template) {
    this.editTemplate = template;
    this.frames = [...template.frames]; // Clone frames
    this.currentFrameIndex = 0;
    this.totalFrames = this.frames.length;

    // Load image
    this.loadImage(template.imageUrl);

    // Show editor
    this.switchMode('create'); // Use create mode UI
    document.getElementById('editorSection').style.display = 'block';
    document.getElementById('locationSelectGroup').style.display = 'none';

    // Update progress
    document.getElementById('frameName').textContent = `Editing frame ${this.currentFrameIndex + 1}`;
    this.updateProgress();

    // Show current frame overlay
    this.showCurrentFrameOverlay();

    this.showToast(`Editing frame ${this.currentFrameIndex + 1} of ${this.totalFrames}`, 'success');
  }

  showCurrentFrameOverlay() {
    const overlay = document.getElementById('frameOverlay');
    overlay.innerHTML = '';

    if (this.currentFrameIndex < this.frames.length) {
      const frame = this.frames[this.currentFrameIndex];
      const rect = this.canvas.getBoundingClientRect();

      const box = document.createElement('div');
      box.className = 'frame-box';
      box.style.left = (frame.points[0][0] * this.zoom + rect.left) + 'px';
      box.style.top = (frame.points[0][1] * this.zoom + rect.top) + 'px';
      box.style.width = ((frame.points[1][0] - frame.points[0][0]) * this.zoom) + 'px';
      box.style.height = ((frame.points[2][1] - frame.points[0][1]) * this.zoom) + 'px';

      const label = document.createElement('div');
      label.className = 'frame-label';
      label.textContent = `Frame ${this.currentFrameIndex + 1} (Click to re-define)`;
      box.appendChild(label);

      overlay.appendChild(box);
    }
  }

  handleMouseDown(e) {
    const rect = this.canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left) / this.zoom;
    const y = (e.clientY - rect.top) / this.zoom;

    if (e.button === 1 || e.shiftKey) {
      // Middle mouse or shift+click for panning
      this.isPanning = true;
      this.lastPanX = e.clientX;
      this.lastPanY = e.clientY;
      this.canvas.style.cursor = 'grabbing';
    } else {
      // Start drawing frame
      this.isDrawing = true;
      this.startX = x;
      this.startY = y;
      this.currentFrame = null;
    }
  }

  handleMouseMove(e) {
    if (this.isPanning) {
      const dx = e.clientX - this.lastPanX;
      const dy = e.clientY - this.lastPanY;
      this.panX += dx;
      this.panY += dy;
      this.lastPanX = e.clientX;
      this.lastPanY = e.clientY;
      this.redraw();
      return;
    }

    if (!this.isDrawing) return;

    const rect = this.canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left) / this.zoom;
    const y = (e.clientY - rect.top) / this.zoom;

    this.currentFrame = {
      x: Math.min(this.startX, x),
      y: Math.min(this.startY, y),
      width: Math.abs(x - this.startX),
      height: Math.abs(y - this.startY)
    };

    this.redraw();
  }

  handleMouseUp(e) {
    if (this.isPanning) {
      this.isPanning = false;
      this.canvas.style.cursor = 'crosshair';
      return;
    }

    if (!this.isDrawing) return;

    this.isDrawing = false;

    if (this.currentFrame && this.currentFrame.width > 10 && this.currentFrame.height > 10) {
      // Convert to frame format
      const frame = {
        points: [
          [this.currentFrame.x, this.currentFrame.y],
          [this.currentFrame.x + this.currentFrame.width, this.currentFrame.y],
          [this.currentFrame.x + this.currentFrame.width, this.currentFrame.y + this.currentFrame.height],
          [this.currentFrame.x, this.currentFrame.y + this.currentFrame.height]
        ],
        config: {
          blurStrength: this.edgeBlur
        }
      };

      if (this.editTemplate && this.currentFrameIndex < this.frames.length) {
        // Replace existing frame
        this.frames[this.currentFrameIndex] = frame;
      } else {
        // Add new frame
        this.frames.push(frame);
      }

      this.currentFrame = null;
      this.updateProgress();
      document.getElementById('undoBtn').disabled = false;

      if (this.frames.length < this.totalFrames) {
        document.getElementById('nextFrameBtn').disabled = false;
        this.showToast(`Frame ${this.frames.length} defined. Click Next or define another frame.`, 'success');
      } else {
        document.getElementById('finishBtn').style.display = 'inline-flex';
        this.showToast('All frames defined! Click Finish to save.', 'success');
      }
    }

    this.redraw();
  }

  handleWheel(e) {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.1 : 0.1;
    this.changeZoom(delta);
  }

  changeZoom(delta) {
    this.zoom = Math.max(0.1, Math.min(5, this.zoom + delta));
    document.getElementById('zoomLevel').textContent = Math.round(this.zoom * 100) + '%';
    this.redraw();
  }

  fitToScreen() {
    const wrapper = document.getElementById('canvasWrapper');
    const wrapperWidth = wrapper.clientWidth - 40;
    const wrapperHeight = wrapper.clientHeight - 40;

    const scaleX = wrapperWidth / this.canvas.width;
    const scaleY = wrapperHeight / this.canvas.height;

    this.zoom = Math.min(scaleX, scaleY, 1);
    this.panX = 0;
    this.panY = 0;
    document.getElementById('zoomLevel').textContent = Math.round(this.zoom * 100) + '%';
    this.redraw();
  }

  redraw() {
    if (!this.image) return;

    // Clear canvas
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    // Draw image
    this.ctx.drawImage(this.image, 0, 0);

    // Draw existing frames
    this.frames.forEach((frame, index) => {
      this.ctx.strokeStyle = '#667eea';
      this.ctx.lineWidth = 3 / this.zoom;
      this.ctx.beginPath();
      this.ctx.rect(
        frame.points[0][0],
        frame.points[0][1],
        frame.points[1][0] - frame.points[0][0],
        frame.points[2][1] - frame.points[0][1]
      );
      this.ctx.stroke();

      // Draw label
      this.ctx.fillStyle = '#667eea';
      this.ctx.font = `${14 / this.zoom}px sans-serif`;
      this.ctx.fillText(`Frame ${index + 1}`, frame.points[0][0] + 5, frame.points[0][1] - 5);
    });

    // Draw current frame being drawn
    if (this.currentFrame) {
      this.ctx.strokeStyle = '#10b981';
      this.ctx.lineWidth = 3 / this.zoom;
      this.ctx.setLineDash([10 / this.zoom, 5 / this.zoom]);
      this.ctx.strokeRect(
        this.currentFrame.x,
        this.currentFrame.y,
        this.currentFrame.width,
        this.currentFrame.height
      );
      this.ctx.setLineDash([]);
    }

    // Apply zoom transform
    this.canvas.style.transform = `scale(${this.zoom})`;
    this.canvas.style.transformOrigin = 'top left';
  }

  updateProgress() {
    const current = this.editTemplate ? this.currentFrameIndex + 1 : this.frames.length;
    document.getElementById('currentFrame').textContent = current;
    document.getElementById('totalFrames').textContent = this.totalFrames;

    const progress = (current / this.totalFrames) * 100;
    document.getElementById('progressFill').style.width = progress + '%';

    if (!this.editTemplate) {
      document.getElementById('frameName').textContent =
        current < this.totalFrames ? `Defining frame ${current + 1}...` : 'All frames defined!';
    }
  }

  undo() {
    if (this.frames.length > 0) {
      this.frames.pop();
      this.updateProgress();
      this.redraw();

      if (this.frames.length === 0) {
        document.getElementById('undoBtn').disabled = true;
      }

      if (this.frames.length < this.totalFrames) {
        document.getElementById('nextFrameBtn').disabled = this.frames.length === 0;
        document.getElementById('finishBtn').style.display = 'none';
      }

      this.showToast('Frame removed', 'success');
    }
  }

  nextFrame() {
    if (this.editTemplate) {
      // Move to next frame in edit mode
      this.currentFrameIndex++;
      if (this.currentFrameIndex >= this.totalFrames) {
        // All frames edited
        this.finish();
      } else {
        document.getElementById('frameName').textContent = `Editing frame ${this.currentFrameIndex + 1}`;
        this.updateProgress();
        this.showCurrentFrameOverlay();
        this.showToast(`Now editing frame ${this.currentFrameIndex + 1}`, 'success');
      }
    } else {
      // Create mode - just acknowledge
      this.showToast(`Ready for frame ${this.frames.length + 1}`, 'success');
    }
  }

  async finish() {
    const locationKey = this.editTemplate ?
      this.editTemplate.locationKey :
      document.getElementById('locationSelect').value;

    if (!locationKey) {
      this.showToast('Please select a location', 'error');
      return;
    }

    const templateData = {
      locationKey,
      frames: this.frames,
      imageUrl: this.image.src,
      metadata: {
        imageWidth: this.image.width,
        imageHeight: this.image.height,
        totalFrames: this.frames.length
      }
    };

    try {
      const response = await fetch('/api/templates', {
        method: 'POST',
        headers: this.getAuthHeaders(),
        body: JSON.stringify(templateData)
      });

      if (response.status === 401) {
        this.handleUnauthorized();
        return;
      }

      const data = await response.json();

      if (data.success) {
        this.showToast(
          this.editTemplate ? 'Template updated successfully!' : 'Template saved successfully!',
          'success'
        );

        // Reset
        setTimeout(() => {
          window.location.reload();
        }, 1500);
      }
    } catch (err) {
      this.showToast('Failed to save template', 'error');
      console.error(err);
    }
  }

  async loadTemplatesForEdit() {
    const container = document.getElementById('templateList');
    container.innerHTML = '<div class="loading">Loading templates...</div>';

    try {
      const response = await fetch('/api/templates');
      const templates = await response.json();

      if (templates.length === 0) {
        container.innerHTML = '<div class="loading">No templates found</div>';
        return;
      }

      container.innerHTML = '';

      templates.forEach(template => {
        const card = document.createElement('div');
        card.className = 'template-card';
        card.innerHTML = `
          <img src="${template.imageUrl}" class="template-card-image" alt="${template.locationKey}">
          <div class="template-card-body">
            <div class="template-card-title">${template.locationKey.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</div>
            <div class="template-card-meta">
              <span>${template.frames.length} frames</span>
              <span>${new Date(template.updatedAt).toLocaleDateString()}</span>
            </div>
            <div class="template-card-actions">
              <button class="btn btn-primary btn-sm edit-template-btn">Edit</button>
              <button class="btn btn-danger btn-sm delete-template-btn">Delete</button>
            </div>
          </div>
        `;

        card.querySelector('.edit-template-btn').addEventListener('click', () => {
          this.startFrameEdit(template);
        });

        card.querySelector('.delete-template-btn').addEventListener('click', () => {
          this.deleteTemplate(template.locationKey);
        });

        container.appendChild(card);
      });
    } catch (err) {
      container.innerHTML = '<div class="loading">Failed to load templates</div>';
      console.error(err);
    }
  }

  async deleteTemplate(locationKey) {
    if (!confirm('Are you sure you want to delete this template?')) return;

    try {
      const response = await fetch(`/api/templates/${locationKey}`, {
        method: 'DELETE',
        headers: {
          'X-Session-Id': this.sessionId
        }
      });

      if (response.status === 401) {
        this.handleUnauthorized();
        return;
      }

      const data = await response.json();

      if (data.success) {
        this.showToast('Template deleted', 'success');
        this.loadTemplatesForEdit();
      }
    } catch (err) {
      this.showToast('Failed to delete template', 'error');
      console.error(err);
    }
  }

  async showTemplatesModal() {
    document.getElementById('templatesModal').classList.add('active');
    const grid = document.getElementById('templatesGrid');
    grid.innerHTML = '<div class="loading">Loading templates...</div>';

    try {
      const response = await fetch('/api/templates');
      const templates = await response.json();

      if (templates.length === 0) {
        grid.innerHTML = '<div class="loading">No templates found</div>';
        return;
      }

      grid.innerHTML = '';

      templates.forEach(template => {
        const card = document.createElement('div');
        card.className = 'template-card';
        card.innerHTML = `
          <img src="${template.imageUrl}" class="template-card-image" alt="${template.locationKey}">
          <div class="template-card-body">
            <div class="template-card-title">${template.locationKey.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</div>
            <div class="template-card-meta">
              <span>${template.frames.length} frames</span>
              <span>${new Date(template.updatedAt).toLocaleDateString()}</span>
            </div>
          </div>
        `;

        grid.appendChild(card);
      });
    } catch (err) {
      grid.innerHTML = '<div class="loading">Failed to load templates</div>';
      console.error(err);
    }
  }

  hideTemplatesModal() {
    document.getElementById('templatesModal').classList.remove('active');
  }

  showToast(message, type = 'success') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    const icons = {
      success: '<svg width="24" height="24" viewBox="0 0 24 24" fill="#10b981"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"/></svg>',
      error: '<svg width="24" height="24" viewBox="0 0 24 24" fill="#ef4444"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12 19 6.41z"/></svg>',
      warning: '<svg width="24" height="24" viewBox="0 0 24 24" fill="#f59e0b"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>'
    };

    toast.innerHTML = `
      <div class="toast-icon">${icons[type]}</div>
      <div class="toast-message">${message}</div>
    `;

    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  new MockupStudio();
});

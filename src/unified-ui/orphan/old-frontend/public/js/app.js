// Unified UI - Main Application
// MMG Platform - Sales Department Module

// ========================================
// TOAST NOTIFICATIONS (Global Utility)
// ========================================
const Toast = {
  container: null,

  init() {
    this.container = document.getElementById('toastContainer');
    if (!this.container) {
      this.container = document.createElement('div');
      this.container.id = 'toastContainer';
      this.container.className = 'toast-container';
      document.body.appendChild(this.container);
    }
  },

  show(message, type = 'success') {
    if (!this.container) this.init();

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    const icons = {
      success: '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"/></svg>',
      error: '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12 19 6.41z"/></svg>',
      warning: '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>',
      info: '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>'
    };

    toast.innerHTML = `
      <div class="toast-icon">${icons[type] || icons.info}</div>
      <div class="toast-message">${message}</div>
    `;

    this.container.appendChild(toast);

    // Auto remove after 3 seconds
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(100%)';
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  },

  success(message) { this.show(message, 'success'); },
  error(message) { this.show(message, 'error'); },
  warning(message) { this.show(message, 'warning'); },
  info(message) { this.show(message, 'info'); }
};

// Make Toast globally available
window.Toast = Toast;

// ========================================
// MOCKUP STUDIO CLASS (Tool within Unified UI)
// ========================================
class MockupStudio {
  constructor() {
    // Authentication
    this.sessionId = localStorage.getItem('mockup_studio_session');

    // Canvas state
    this.canvas = null;
    this.ctx = null;
    this.previewImg = null;
    this.currentPhoto = null;

    // Frame state
    this.currentPoints = [];
    this.allFrames = [];
    this.selectedFrameIndex = -1;

    // Canvas drawing state
    this.imgNaturalW = 0;
    this.imgNaturalH = 0;
    this.drawX = 0;
    this.drawY = 0;
    this.drawW = 0;
    this.drawH = 0;
    this.scale = 1;

    // Interaction state
    this.isDrawing = false;
    this.isDraggingCorner = false;
    this.isDraggingFrame = false;
    this.dragFrameIndex = -1;
    this.dragPointIndex = -1;
    this.startX = 0;
    this.startY = 0;

    // Zoom/pan
    this.zoom = 1;
    this.panX = 0;
    this.panY = 0;
    this.isPanning = false;
    this.lastPanX = 0;
    this.lastPanY = 0;
    this.pixelUpscale = false;

    // Mode
    this.mode = 'setup';

    // Test preview
    this.testPreviewMode = false;
    this.testCreativeFile = null;
    this.testPreviewImage = null;
    this.isGeneratingPreview = false;
    this.livePreviewEnabled = false;
    this.previewDebounceTimer = null;
    this.lastPreviewConfig = null;

    // Generate mode
    this.selectedTemplateConfig = null;

    // Locations
    this.locations = [];

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

    this.canvas = document.getElementById('canvas');
    this.ctx = this.canvas.getContext('2d');

    this.setupEventListeners();
    this.loadLocations();
    this.initializeSliders();
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
    setTimeout(() => window.location.reload(), 1500);
  }

  // ========================================
  // EVENT LISTENERS SETUP
  // ========================================

  setupEventListeners() {
    // Mode switching
    document.querySelectorAll('.mode-btn').forEach(btn => {
      btn.addEventListener('click', (e) => this.switchMode(e.currentTarget.dataset.mode));
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
    uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('drag-over'));
    uploadZone.addEventListener('drop', (e) => {
      e.preventDefault();
      uploadZone.classList.remove('drag-over');
      if (e.dataTransfer.files.length > 0) {
        this.loadImageFile(e.dataTransfer.files[0]);
      }
    });

    // Location select
    document.getElementById('locationSelect').addEventListener('change', () => this.onLocationChange());

    // Zoom controls
    document.getElementById('zoomIn').addEventListener('click', () => this.changeZoom(0.1));
    document.getElementById('zoomOut').addEventListener('click', () => this.changeZoom(-0.1));
    document.getElementById('zoomFit').addEventListener('click', () => this.fitToScreen());
    document.getElementById('pixelUpscale').addEventListener('change', (e) => {
      this.pixelUpscale = e.target.checked;
      this.canvas.classList.toggle('pixel-upscale', this.pixelUpscale);
      this.redraw();
    });

    // Canvas interaction
    this.canvas.addEventListener('mousedown', (e) => this.handleMouseDown(e));
    this.canvas.addEventListener('mousemove', (e) => this.handleMouseMove(e));
    this.canvas.addEventListener('mouseup', (e) => this.handleMouseUp(e));
    this.canvas.addEventListener('wheel', (e) => this.handleWheel(e));

    // Keyboard shortcuts for precise corner adjustment
    document.addEventListener('keydown', (e) => this.handleKeyDown(e));

    // Control buttons
    document.getElementById('addFrameBtn').addEventListener('click', () => this.addFrame());
    document.getElementById('resetFrameBtn').addEventListener('click', () => this.resetCurrentFrame());
    document.getElementById('saveAllBtn').addEventListener('click', () => this.saveAllFrames());
    document.getElementById('clearAllBtn').addEventListener('click', () => this.clearAllFrames());

    // Green screen
    document.getElementById('greenscreenToggle').addEventListener('change', (e) => {
      document.getElementById('colorPickerSection').style.display = e.target.checked ? 'block' : 'none';
      document.getElementById('detectGreenscreenBtn').disabled = !e.target.checked || !this.previewImg;
    });

    document.getElementById('greenscreenColor').addEventListener('input', (e) => {
      document.getElementById('greenscreenColorHex').value = e.target.value.toUpperCase();
    });

    document.getElementById('greenscreenColorHex').addEventListener('input', (e) => {
      const hex = e.target.value;
      if (/^#[0-9A-F]{6}$/i.test(hex)) {
        document.getElementById('greenscreenColor').value = hex;
      }
    });

    document.getElementById('colorTolerance').addEventListener('input', (e) => {
      document.getElementById('toleranceValue').textContent = e.target.value;
      this.updateSliderFill(e.target);
    });

    document.getElementById('detectGreenscreenBtn').addEventListener('click', () => this.detectGreenScreen());

    // Test preview
    document.getElementById('testPreviewToggle').addEventListener('change', (e) => {
      this.testPreviewMode = e.target.checked;
      this.livePreviewEnabled = e.target.checked;
      document.getElementById('testPreviewUpload').style.display = this.testPreviewMode ? 'block' : 'none';
      if (!this.testPreviewMode) {
        this.testCreativeFile = null;
        this.testPreviewImage = null;
        this.livePreviewEnabled = false;
        this.lastPreviewConfig = null;
        if (this.previewDebounceTimer) {
          clearTimeout(this.previewDebounceTimer);
        }
        this.redraw();
      }
    });

    document.getElementById('testCreativeUpload').addEventListener('change', (e) => {
      const file = e.target.files[0];
      this.testCreativeFile = file || null;
      document.getElementById('generatePreviewBtn').disabled = !file || this.currentPoints.length !== 4;
      // Reset last config so first preview triggers
      this.lastPreviewConfig = null;
      // Auto-trigger first preview when creative is uploaded
      if (file && this.currentPoints.length === 4 && this.livePreviewEnabled) {
        this.scheduleLivePreview();
      }
    });

    document.getElementById('generatePreviewBtn').addEventListener('click', () => this.generateBackendPreview());

    // Light direction buttons
    document.querySelectorAll('.light-dir-btn').forEach(btn => {
      btn.addEventListener('click', (e) => this.setLightDirection(e.currentTarget, 'frame'));
    });

    document.querySelectorAll('.gen-light-dir-btn').forEach(btn => {
      btn.addEventListener('click', (e) => this.setLightDirection(e.currentTarget, 'gen'));
    });

    // Modal
    document.getElementById('viewTemplatesBtn').addEventListener('click', () => this.showTemplatesModal());
    document.getElementById('closeModal').addEventListener('click', () => this.hideTemplatesModal());
    document.getElementById('templatesModal').addEventListener('click', (e) => {
      if (e.target.id === 'templatesModal') this.hideTemplatesModal();
    });

    // Generate mode
    document.getElementById('generateLocationSelect').addEventListener('change', () => this.loadTemplatesForGenerate());
    document.getElementById('generateTimeOfDay').addEventListener('change', () => this.loadTemplatesForGenerate());
    document.getElementById('generateFinish').addEventListener('change', () => this.loadTemplatesForGenerate());
    document.getElementById('generateTemplate').addEventListener('change', () => this.loadTemplateConfig());
    document.getElementById('generateConfigToggle').addEventListener('change', (e) => {
      document.getElementById('generateConfigSection').style.display = e.target.checked ? 'block' : 'none';
    });
    document.getElementById('creativeUpload').addEventListener('change', () => this.updateGenerateButtonState());
    document.getElementById('aiCreativePrompt').addEventListener('input', () => this.updateGenerateButtonState());
    document.getElementById('generateBtn').addEventListener('click', () => this.generateMockup());
  }

  initializeSliders() {
    // Setup mode sliders
    const setupSliders = [
      { id: 'frameBrightness', valueId: 'brightnessValue' },
      { id: 'frameContrast', valueId: 'contrastValue' },
      { id: 'frameSaturation', valueId: 'saturationValue' },
      { id: 'frameImageBlur', valueId: 'imageBlurValue' },
      { id: 'frameEdgeBlur', valueId: 'edgeBlurValue' },
      { id: 'frameOverlayOpacity', valueId: 'overlayValue' },
      { id: 'frameShadowIntensity', valueId: 'shadowValue' },
      { id: 'frameLightingAdjustment', valueId: 'lightingValue' },
      { id: 'frameColorTemperature', valueId: 'temperatureValue' },
      { id: 'frameVignette', valueId: 'vignetteValue' },
      { id: 'frameEdgeSmoother', valueId: 'edgeSmootherValue' },
      { id: 'frameSharpening', valueId: 'sharpeningValue' },
      { id: 'frameDepthMultiplier', valueId: 'depthValue' }
    ];

    setupSliders.forEach(({ id, valueId }) => {
      const slider = document.getElementById(id);
      const valueEl = document.getElementById(valueId);
      if (slider && valueEl) {
        // Update value display on input (while dragging)
        slider.addEventListener('input', (e) => {
          valueEl.textContent = e.target.value;
          this.updateSliderFill(e.target);
        });
        // Trigger live preview on mouseup/touchend (after releasing slider)
        slider.addEventListener('mouseup', () => this.scheduleLivePreview());
        slider.addEventListener('touchend', () => this.scheduleLivePreview());
        this.updateSliderFill(slider);
      }
    });

    // Generate mode sliders
    const genSliders = [
      { id: 'genFrameBrightness', valueId: 'genBrightnessValue' },
      { id: 'genFrameContrast', valueId: 'genContrastValue' },
      { id: 'genFrameSaturation', valueId: 'genSaturationValue' },
      { id: 'genFrameImageBlur', valueId: 'genImageBlurValue' },
      { id: 'genFrameEdgeBlur', valueId: 'genEdgeBlurValue' },
      { id: 'genFrameOverlayOpacity', valueId: 'genOverlayValue' },
      { id: 'genFrameShadowIntensity', valueId: 'genShadowValue' },
      { id: 'genFrameLightingAdjustment', valueId: 'genLightingValue' },
      { id: 'genFrameColorTemperature', valueId: 'genTemperatureValue' },
      { id: 'genFrameVignette', valueId: 'genVignetteValue' },
      { id: 'genFrameEdgeSmoother', valueId: 'genEdgeSmootherValue' },
      { id: 'genFrameSharpening', valueId: 'genSharpeningValue' },
      { id: 'genFrameDepthMultiplier', valueId: 'genDepthValue' }
    ];

    genSliders.forEach(({ id, valueId }) => {
      const slider = document.getElementById(id);
      const valueEl = document.getElementById(valueId);
      if (slider && valueEl) {
        slider.addEventListener('input', (e) => {
          valueEl.textContent = e.target.value;
          this.updateSliderFill(e.target);
        });
        this.updateSliderFill(slider);
      }
    });
  }

  updateSliderFill(slider) {
    const min = parseFloat(slider.min) || 0;
    const max = parseFloat(slider.max) || 100;
    const value = parseFloat(slider.value);
    const percent = ((value - min) / (max - min)) * 100;
    slider.style.background = `linear-gradient(to right, var(--primary) ${percent}%, var(--gray-200) ${percent}%)`;
  }

  setLightDirection(btn, prefix) {
    const selector = prefix === 'gen' ? '.gen-light-dir-btn' : '.light-dir-btn';
    const inputId = prefix === 'gen' ? 'genFrameLightDirection' : 'frameLightDirection';
    const labelId = prefix === 'gen' ? 'genLightDirectionLabel' : 'lightDirectionLabel';

    document.querySelectorAll(selector).forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    const direction = btn.dataset.direction;
    document.getElementById(inputId).value = direction;

    const labelMap = {
      'top-left': 'Top Left', 'top': 'Top', 'top-right': 'Top Right',
      'left': 'Left', 'center': 'Center', 'right': 'Right',
      'bottom-left': 'Bottom Left', 'bottom': 'Bottom', 'bottom-right': 'Bottom Right'
    };
    document.getElementById(labelId).textContent = labelMap[direction] || 'Top';

    // Trigger live preview when light direction changes (only for setup mode)
    if (prefix === 'frame') {
      this.scheduleLivePreview();
    }
  }

  // ========================================
  // LIVE PREVIEW
  // ========================================

  scheduleLivePreview() {
    // Only run if live preview is enabled and conditions are met
    if (!this.livePreviewEnabled) return;
    if (!this.testCreativeFile || !this.currentPhoto || this.currentPoints.length !== 4) return;

    // Clear any pending preview request
    if (this.previewDebounceTimer) {
      clearTimeout(this.previewDebounceTimer);
    }

    // Check if config actually changed
    const currentConfig = JSON.stringify(this.getFrameConfig());
    if (currentConfig === this.lastPreviewConfig) return;

    // Schedule new preview after 400ms delay
    this.previewDebounceTimer = setTimeout(() => {
      this.lastPreviewConfig = currentConfig;
      this.generateLivePreview();
    }, 400);
  }

  async generateLivePreview() {
    if (this.isGeneratingPreview) return;
    if (!this.testCreativeFile || !this.currentPhoto || this.currentPoints.length !== 4) return;

    this.isGeneratingPreview = true;

    // Show loading indicator
    const indicator = document.getElementById('livePreviewIndicator');
    if (indicator) indicator.style.display = 'flex';

    try {
      const frameConfig = this.getFrameConfig();
      const formData = new FormData();
      formData.append('billboard_photo', this.currentPhoto);
      formData.append('creative', this.testCreativeFile);
      formData.append('frame_points', JSON.stringify(this.currentPoints));
      formData.append('config', JSON.stringify(frameConfig));
      formData.append('time_of_day', document.getElementById('timeOfDaySelect').value || 'day');

      const response = await fetch('/api/mockup/test-preview', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        throw new Error(`Preview failed: ${response.statusText}`);
      }

      const blob = await response.blob();
      const imageUrl = URL.createObjectURL(blob);

      const img = new Image();
      img.onload = () => {
        this.testPreviewImage = img;
        this.redraw();
      };
      img.src = imageUrl;

    } catch (error) {
      console.error('[Live Preview] Error:', error);
    } finally {
      this.isGeneratingPreview = false;
      if (indicator) indicator.style.display = 'none';
    }
  }

  // ========================================
  // MODE SWITCHING
  // ========================================

  switchMode(mode) {
    this.mode = mode;

    document.querySelectorAll('.mode-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === mode);
    });

    document.querySelectorAll('.mode-content').forEach(content => {
      content.classList.toggle('active', content.id === `${mode}Mode`);
    });

    if (mode === 'generate') {
      this.populateGenerateLocations();
    }
  }

  // ========================================
  // LOCATIONS
  // ========================================

  async loadLocations() {
    try {
      const response = await fetch('/api/mockup/locations');
      const data = await response.json();
      this.locations = data.locations || [];

      const setupSelect = document.getElementById('locationSelect');
      const generateSelect = document.getElementById('generateLocationSelect');

      setupSelect.innerHTML = '<option value="">Choose a location...</option>';
      generateSelect.innerHTML = '<option value="">Choose a location...</option>';

      this.locations.forEach(loc => {
        setupSelect.innerHTML += `<option value="${loc.key}">${loc.name}</option>`;
        generateSelect.innerHTML += `<option value="${loc.key}">${loc.name}</option>`;
      });
    } catch (err) {
      console.error('Failed to load locations:', err);
      this.showToast('Failed to load locations', 'error');
    }
  }

  populateGenerateLocations() {
    const generateSelect = document.getElementById('generateLocationSelect');
    generateSelect.innerHTML = '<option value="">Choose a location...</option>';
    this.locations.forEach(loc => {
      generateSelect.innerHTML += `<option value="${loc.key}">${loc.name}</option>`;
    });
  }

  onLocationChange() {
    const locationKey = document.getElementById('locationSelect').value;
    if (locationKey) {
      this.loadPhotoList();
      document.getElementById('existingPhotosSection').style.display = 'block';
    } else {
      document.getElementById('existingPhotosSection').style.display = 'none';
    }
  }

  // ========================================
  // IMAGE UPLOAD
  // ========================================

  async handleImageUpload(e) {
    const file = e.target.files[0];
    if (file) {
      await this.loadImageFile(file);
    }
  }

  async loadImageFile(file) {
    this.currentPhoto = file;

    const reader = new FileReader();
    reader.onload = (event) => {
      const img = new Image();
      img.onload = () => {
        this.previewImg = img;
        this.imgNaturalW = img.width;
        this.imgNaturalH = img.height;

        // Set canvas size to match image
        this.canvas.width = 1200;
        this.canvas.height = 800;

        const fit = this.fitImageIntoCanvas(this.imgNaturalW, this.imgNaturalH);
        this.drawX = fit.x;
        this.drawY = fit.y;
        this.drawW = fit.w;
        this.drawH = fit.h;
        this.scale = fit.s;

        this.currentPoints = [];
        this.allFrames = [];

        // Hide upload zone and show settings/editor
        document.getElementById('uploadZone').style.display = 'none';
        document.getElementById('settingsRow').style.display = 'grid';
        document.getElementById('greenscreenSection').style.display = 'block';
        document.getElementById('editorSection').style.display = 'block';

        // Enable green screen button if toggle is on
        if (document.getElementById('greenscreenToggle').checked) {
          document.getElementById('detectGreenscreenBtn').disabled = false;
        }

        document.getElementById('setupHint').innerHTML = 'Click and drag to draw a box around the billboard screen';
        this.updateProgress();
        this.redraw();

        this.showToast('Image loaded successfully!', 'success');
      };
      img.src = event.target.result;
    };
    reader.readAsDataURL(file);
  }

  fitImageIntoCanvas(imgW, imgH) {
    const s = Math.min(this.canvas.width / imgW, this.canvas.height / imgH);
    const w = Math.round(imgW * s);
    const h = Math.round(imgH * s);
    const x = Math.round((this.canvas.width - w) / 2);
    const y = Math.round((this.canvas.height - h) / 2);
    return { x, y, w, h, s };
  }

  // ========================================
  // CANVAS DRAWING
  // ========================================

  redraw() {
    this.clearCanvas();
    if (!this.previewImg) return;

    // If test preview mode is active and we have a backend-generated preview, show it
    if (this.testPreviewMode && this.testPreviewImage) {
      this.ctx.drawImage(this.testPreviewImage, this.drawX, this.drawY, this.drawW, this.drawH);
      return;
    }

    // Normal mode: draw billboard
    this.ctx.drawImage(this.previewImg, this.drawX, this.drawY, this.drawW, this.drawH);

    // Draw all completed frames with grey fill and dashed edges
    this.allFrames.forEach((frameData, frameIndex) => {
      const isSelected = this.selectedFrameIndex === frameIndex;
      this.drawFrame(frameData.points, isSelected, frameIndex);
    });

    // Draw current frame being edited
    if (this.currentPoints.length > 0) {
      this.drawFrame(this.currentPoints, true, -1);
    }

    // Draw alignment guides if dragging a corner
    if (this.isDraggingCorner) {
      this.drawAlignmentGuides();
    }

    // Apply zoom transform
    this.canvas.style.transform = `scale(${this.zoom})`;
    this.canvas.style.transformOrigin = 'top left';
  }

  drawFrame(framePoints, isSelected, frameIndex) {
    const isCurrent = frameIndex === -1;

    // Draw frame fill and outline
    this.ctx.fillStyle = 'rgba(102, 126, 234, 0.15)';
    this.ctx.strokeStyle = isSelected ? '#667eea' : '#555';
    this.ctx.lineWidth = isSelected ? 3 : 2;
    this.ctx.setLineDash([6, 3]);
    this.ctx.lineCap = 'round';
    this.ctx.lineJoin = 'round';

    this.ctx.beginPath();
    for (let i = 0; i < framePoints.length; i++) {
      const cx = this.drawX + framePoints[i][0] * this.scale;
      const cy = this.drawY + framePoints[i][1] * this.scale;
      if (i === 0) this.ctx.moveTo(cx, cy);
      else this.ctx.lineTo(cx, cy);
    }
    if (framePoints.length === 4) {
      this.ctx.closePath();
      this.ctx.fill();
    }
    this.ctx.stroke();
    this.ctx.setLineDash([]);

    // Draw edge length labels (for current/selected frame)
    if (isSelected && framePoints.length === 4) {
      this.drawEdgeLengths(framePoints);
    }

    // Draw corner handles with better visibility
    framePoints.forEach((pt, idx) => {
      const cx = this.drawX + pt[0] * this.scale;
      const cy = this.drawY + pt[1] * this.scale;

      // Outer circle (white border for visibility)
      const handleSize = isSelected ? 12 : 8;
      this.ctx.beginPath();
      this.ctx.arc(cx, cy, handleSize / 2 + 2, 0, Math.PI * 2);
      this.ctx.fillStyle = 'white';
      this.ctx.fill();

      // Inner circle (colored)
      this.ctx.beginPath();
      this.ctx.arc(cx, cy, handleSize / 2, 0, Math.PI * 2);
      this.ctx.fillStyle = isSelected ? '#667eea' : '#555';
      this.ctx.fill();

      // Crosshair inside for precision
      if (isSelected) {
        this.ctx.strokeStyle = 'white';
        this.ctx.lineWidth = 1.5;
        this.ctx.beginPath();
        this.ctx.moveTo(cx - 3, cy);
        this.ctx.lineTo(cx + 3, cy);
        this.ctx.moveTo(cx, cy - 3);
        this.ctx.lineTo(cx, cy + 3);
        this.ctx.stroke();
      }

      // Show coordinates when dragging this corner
      if (this.isDraggingCorner && this.dragPointIndex === idx &&
          ((isCurrent && this.dragFrameIndex === -1) || this.dragFrameIndex === frameIndex)) {
        this.drawCoordinateLabel(cx, cy, pt[0], pt[1]);
      }
    });
  }

  drawEdgeLengths(framePoints) {
    this.ctx.font = '11px -apple-system, sans-serif';
    this.ctx.textAlign = 'center';
    this.ctx.textBaseline = 'middle';

    for (let i = 0; i < 4; i++) {
      const p1 = framePoints[i];
      const p2 = framePoints[(i + 1) % 4];
      const length = Math.round(Math.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2));

      // Midpoint of edge
      const mx = this.drawX + ((p1[0] + p2[0]) / 2) * this.scale;
      const my = this.drawY + ((p1[1] + p2[1]) / 2) * this.scale;

      // Background pill
      const text = `${length}px`;
      const textWidth = this.ctx.measureText(text).width;
      this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
      this.roundRect(mx - textWidth / 2 - 4, my - 8, textWidth + 8, 16, 4);
      this.ctx.fill();

      // Text
      this.ctx.fillStyle = 'white';
      this.ctx.fillText(text, mx, my);
    }
  }

  drawCoordinateLabel(cx, cy, imgX, imgY) {
    const text = `(${Math.round(imgX)}, ${Math.round(imgY)})`;
    this.ctx.font = 'bold 12px -apple-system, sans-serif';
    const textWidth = this.ctx.measureText(text).width;

    // Position label offset from corner
    const labelX = cx + 15;
    const labelY = cy - 15;

    // Background
    this.ctx.fillStyle = '#667eea';
    this.roundRect(labelX - 4, labelY - 10, textWidth + 8, 20, 4);
    this.ctx.fill();

    // Text
    this.ctx.fillStyle = 'white';
    this.ctx.textAlign = 'left';
    this.ctx.textBaseline = 'middle';
    this.ctx.fillText(text, labelX, labelY);
  }

  drawAlignmentGuides() {
    // Get the point being dragged
    let draggedPoint;
    if (this.dragFrameIndex === -1) {
      draggedPoint = this.currentPoints[this.dragPointIndex];
    } else {
      draggedPoint = this.allFrames[this.dragFrameIndex].points[this.dragPointIndex];
    }

    if (!draggedPoint) return;

    const cx = this.drawX + draggedPoint[0] * this.scale;
    const cy = this.drawY + draggedPoint[1] * this.scale;

    // Draw crosshair lines across entire canvas
    this.ctx.strokeStyle = 'rgba(102, 126, 234, 0.5)';
    this.ctx.lineWidth = 1;
    this.ctx.setLineDash([4, 4]);

    // Vertical line
    this.ctx.beginPath();
    this.ctx.moveTo(cx, 0);
    this.ctx.lineTo(cx, this.canvas.height);
    this.ctx.stroke();

    // Horizontal line
    this.ctx.beginPath();
    this.ctx.moveTo(0, cy);
    this.ctx.lineTo(this.canvas.width, cy);
    this.ctx.stroke();

    this.ctx.setLineDash([]);
  }

  roundRect(x, y, width, height, radius) {
    this.ctx.beginPath();
    this.ctx.moveTo(x + radius, y);
    this.ctx.lineTo(x + width - radius, y);
    this.ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
    this.ctx.lineTo(x + width, y + height - radius);
    this.ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    this.ctx.lineTo(x + radius, y + height);
    this.ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
    this.ctx.lineTo(x, y + radius);
    this.ctx.quadraticCurveTo(x, y, x + radius, y);
    this.ctx.closePath();
  }

  clearCanvas() {
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    this.ctx.fillStyle = '#f8f9fa';
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
  }

  // ========================================
  // MOUSE INTERACTIONS
  // ========================================

  handleMouseDown(e) {
    if (!this.previewImg) return;

    const rect = this.canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left) / this.zoom;
    const y = (e.clientY - rect.top) / this.zoom;

    // Shift+Click to detect color
    if (e.shiftKey) {
      if (x < this.drawX || y < this.drawY || x > this.drawX + this.drawW || y > this.drawY + this.drawH) return;

      const ix = Math.floor((x - this.drawX) / this.scale);
      const iy = Math.floor((y - this.drawY) / this.scale);

      const tempCanvas = document.createElement('canvas');
      tempCanvas.width = this.previewImg.width;
      tempCanvas.height = this.previewImg.height;
      const tempCtx = tempCanvas.getContext('2d');
      tempCtx.drawImage(this.previewImg, 0, 0);
      const imageData = tempCtx.getImageData(ix, iy, 1, 1);
      const r = imageData.data[0];
      const g = imageData.data[1];
      const b = imageData.data[2];
      const hex = '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('').toUpperCase();

      document.getElementById('greenscreenColor').value = hex;
      document.getElementById('greenscreenColorHex').value = hex;
      this.showToast(`Color detected: ${hex}`, 'success');
      return;
    }

    // Middle mouse or Ctrl+click for panning
    if (e.button === 1 || e.ctrlKey) {
      this.isPanning = true;
      this.lastPanX = e.clientX;
      this.lastPanY = e.clientY;
      this.canvas.style.cursor = 'grabbing';
      return;
    }

    // Check if clicking on a corner
    const corner = this.getClickedCorner(x, y);
    if (corner) {
      this.isDraggingCorner = true;
      this.dragFrameIndex = corner.frame;
      this.dragPointIndex = corner.point;
      if (this.dragFrameIndex >= 0) {
        this.selectedFrameIndex = this.dragFrameIndex;
      }
      this.redraw();
      return;
    }

    // Check if clicking inside a frame
    const hoveredFrame = this.getHoveredFrame(x, y);
    if (hoveredFrame !== null) {
      this.isDraggingFrame = true;
      this.dragFrameIndex = hoveredFrame;
      this.selectedFrameIndex = hoveredFrame;
      this.startX = x;
      this.startY = y;
      this.canvas.style.cursor = 'move';
      this.redraw();
      return;
    }

    // Check if click is inside image
    if (x < this.drawX || y < this.drawY || x > this.drawX + this.drawW || y > this.drawY + this.drawH) return;

    // Start drawing new box
    this.isDrawing = true;
    this.startX = x;
    this.startY = y;
    this.selectedFrameIndex = -1;
  }

  handleMouseMove(e) {
    if (!this.previewImg) return;

    const rect = this.canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left) / this.zoom;
    const y = (e.clientY - rect.top) / this.zoom;

    // Panning
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

    // Dragging a corner
    if (this.isDraggingCorner) {
      const ix = (x - this.drawX) / this.scale;
      const iy = (y - this.drawY) / this.scale;

      if (this.dragFrameIndex === -1) {
        this.currentPoints[this.dragPointIndex] = [Math.round(ix), Math.round(iy)];
      } else {
        this.allFrames[this.dragFrameIndex].points[this.dragPointIndex] = [Math.round(ix), Math.round(iy)];
      }
      this.redraw();
      return;
    }

    // Dragging entire frame
    if (this.isDraggingFrame) {
      const deltaX = (x - this.startX) / this.scale;
      const deltaY = (y - this.startY) / this.scale;

      if (this.dragFrameIndex === -1) {
        this.currentPoints = this.currentPoints.map(pt => [
          Math.round(pt[0] + deltaX),
          Math.round(pt[1] + deltaY)
        ]);
      } else {
        this.allFrames[this.dragFrameIndex].points = this.allFrames[this.dragFrameIndex].points.map(pt => [
          Math.round(pt[0] + deltaX),
          Math.round(pt[1] + deltaY)
        ]);
      }

      this.startX = x;
      this.startY = y;
      this.redraw();
      return;
    }

    // Drawing new box
    if (this.isDrawing) {
      this.redraw();

      // Draw preview rectangle
      this.ctx.fillStyle = 'rgba(128, 128, 128, 0.3)';
      const width = x - this.startX;
      const height = y - this.startY;
      this.ctx.fillRect(this.startX, this.startY, width, height);

      this.ctx.strokeStyle = '#667eea';
      this.ctx.lineWidth = 4;
      this.ctx.setLineDash([8, 4]);
      this.ctx.lineCap = 'butt';
      this.ctx.lineJoin = 'miter';
      this.ctx.strokeRect(this.startX, this.startY, width, height);
      this.ctx.setLineDash([]);
      return;
    }

    // Update cursor based on what's being hovered
    const hoveredCorner = this.getClickedCorner(x, y);
    const hoveredFrame = this.getHoveredFrame(x, y);

    if (hoveredCorner) {
      // Use resize cursors based on corner position
      const cursorMap = {
        0: 'nwse-resize', // top-left
        1: 'nesw-resize', // top-right
        2: 'nwse-resize', // bottom-right
        3: 'nesw-resize'  // bottom-left
      };
      this.canvas.style.cursor = cursorMap[hoveredCorner.point] || 'pointer';
    } else if (hoveredFrame !== null) {
      this.canvas.style.cursor = 'move';
    } else {
      this.canvas.style.cursor = 'crosshair';
    }
  }

  handleMouseUp(e) {
    if (!this.previewImg) return;

    if (this.isPanning) {
      this.isPanning = false;
      this.canvas.style.cursor = 'crosshair';
      return;
    }

    if (this.isDraggingCorner) {
      this.isDraggingCorner = false;
      this.dragFrameIndex = -1;
      this.dragPointIndex = -1;
      this.canvas.style.cursor = 'crosshair';
      this.redraw();
      return;
    }

    if (this.isDraggingFrame) {
      this.isDraggingFrame = false;
      this.dragFrameIndex = -1;
      this.canvas.style.cursor = 'crosshair';
      this.redraw();
      return;
    }

    if (!this.isDrawing) return;

    const rect = this.canvas.getBoundingClientRect();
    const endX = (e.clientX - rect.left) / this.zoom;
    const endY = (e.clientY - rect.top) / this.zoom;

    const topLeftX = (Math.min(this.startX, endX) - this.drawX) / this.scale;
    const topLeftY = (Math.min(this.startY, endY) - this.drawY) / this.scale;
    const bottomRightX = (Math.max(this.startX, endX) - this.drawX) / this.scale;
    const bottomRightY = (Math.max(this.startY, endY) - this.drawY) / this.scale;

    // Minimum size check
    if (Math.abs(bottomRightX - topLeftX) > 10 && Math.abs(bottomRightY - topLeftY) > 10) {
      this.currentPoints = [
        [Math.round(topLeftX), Math.round(topLeftY)],
        [Math.round(bottomRightX), Math.round(topLeftY)],
        [Math.round(bottomRightX), Math.round(bottomRightY)],
        [Math.round(topLeftX), Math.round(bottomRightY)]
      ];

      document.getElementById('addFrameBtn').disabled = false;
      document.getElementById('setupHint').innerHTML = 'Frame drawn! Drag corners to adjust. Use arrow keys for 1px nudge (Shift+arrows for 10px). Click "Add Frame" to save.';

      // Show frame settings and test preview
      document.getElementById('frameSettingsPanel').style.display = 'block';
      document.getElementById('testPreviewSection').style.display = 'block';

      // Update test preview button state
      if (this.testCreativeFile && this.currentPoints.length === 4) {
        document.getElementById('generatePreviewBtn').disabled = false;
      }
    }

    this.isDrawing = false;
    this.redraw();
  }

  handleWheel(e) {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.1 : 0.1;
    this.changeZoom(delta);
  }

  handleKeyDown(e) {
    // Only handle if we have a selected frame or current points
    if (this.currentPoints.length !== 4 && this.selectedFrameIndex < 0) return;

    // Arrow keys for precise movement
    const arrowKeys = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'];
    if (!arrowKeys.includes(e.key)) return;

    e.preventDefault();

    // Shift = 10px, normal = 1px
    const step = e.shiftKey ? 10 : 1;
    let dx = 0, dy = 0;

    switch (e.key) {
      case 'ArrowUp': dy = -step; break;
      case 'ArrowDown': dy = step; break;
      case 'ArrowLeft': dx = -step; break;
      case 'ArrowRight': dx = step; break;
    }

    // Move all corners of current/selected frame
    if (this.currentPoints.length === 4) {
      this.currentPoints = this.currentPoints.map(pt => [pt[0] + dx, pt[1] + dy]);
    } else if (this.selectedFrameIndex >= 0) {
      this.allFrames[this.selectedFrameIndex].points = this.allFrames[this.selectedFrameIndex].points.map(pt => [pt[0] + dx, pt[1] + dy]);
    }

    this.redraw();
  }

  getClickedCorner(x, y) {
    // Zoom-aware hit radius - larger when zoomed out for easier grabbing
    const baseRadius = 12;
    const hitRadius = Math.max(baseRadius, baseRadius / this.zoom);

    // Check current frame first (higher priority)
    if (this.currentPoints.length > 0) {
      for (let i = 0; i < this.currentPoints.length; i++) {
        const cx = this.drawX + this.currentPoints[i][0] * this.scale;
        const cy = this.drawY + this.currentPoints[i][1] * this.scale;
        const dist = Math.sqrt((x - cx) ** 2 + (y - cy) ** 2);
        if (dist < hitRadius) {
          return { frame: -1, point: i };
        }
      }
    }

    // Check all saved frames
    for (let fi = 0; fi < this.allFrames.length; fi++) {
      const framePoints = this.allFrames[fi].points;
      for (let pi = 0; pi < framePoints.length; pi++) {
        const cx = this.drawX + framePoints[pi][0] * this.scale;
        const cy = this.drawY + framePoints[pi][1] * this.scale;
        const dist = Math.sqrt((x - cx) ** 2 + (y - cy) ** 2);
        if (dist < hitRadius) {
          return { frame: fi, point: pi };
        }
      }
    }
    return null;
  }

  getHoveredFrame(x, y) {
    // Check current frame first
    if (this.currentPoints.length === 4 && this.isPointInFrame(x, y, this.currentPoints)) {
      return -1;
    }

    // Check all saved frames
    for (let fi = this.allFrames.length - 1; fi >= 0; fi--) {
      if (this.isPointInFrame(x, y, this.allFrames[fi].points)) {
        return fi;
      }
    }
    return null;
  }

  isPointInFrame(x, y, framePoints) {
    const imgX = (x - this.drawX) / this.scale;
    const imgY = (y - this.drawY) / this.scale;

    let inside = false;
    for (let i = 0, j = framePoints.length - 1; i < framePoints.length; j = i++) {
      const xi = framePoints[i][0], yi = framePoints[i][1];
      const xj = framePoints[j][0], yj = framePoints[j][1];

      const intersect = ((yi > imgY) !== (yj > imgY))
          && (imgX < (xj - xi) * (imgY - yi) / (yj - yi) + xi);
      if (intersect) inside = !inside;
    }
    return inside;
  }

  // ========================================
  // ZOOM CONTROLS
  // ========================================

  changeZoom(delta) {
    // Minimum zoom is 100% (1.0), maximum is 500%
    this.zoom = Math.max(1, Math.min(5, this.zoom + delta));
    document.getElementById('zoomLevel').textContent = Math.round(this.zoom * 100) + '%';
    this.redraw();
  }

  fitToScreen() {
    this.zoom = 1;
    this.panX = 0;
    this.panY = 0;
    document.getElementById('zoomLevel').textContent = '100%';
    this.redraw();
  }

  // ========================================
  // FRAME MANAGEMENT
  // ========================================

  getFrameConfig() {
    return {
      brightness: parseInt(document.getElementById('frameBrightness').value),
      contrast: parseInt(document.getElementById('frameContrast').value),
      saturation: parseInt(document.getElementById('frameSaturation').value),
      depthMultiplier: parseInt(document.getElementById('frameDepthMultiplier').value),
      lightDirection: document.getElementById('frameLightDirection').value,
      imageBlur: parseInt(document.getElementById('frameImageBlur').value),
      edgeBlur: parseInt(document.getElementById('frameEdgeBlur').value),
      overlayOpacity: parseInt(document.getElementById('frameOverlayOpacity').value),
      shadowIntensity: parseInt(document.getElementById('frameShadowIntensity').value),
      lightingAdjustment: parseInt(document.getElementById('frameLightingAdjustment').value),
      colorTemperature: parseInt(document.getElementById('frameColorTemperature').value),
      vignette: parseInt(document.getElementById('frameVignette').value),
      edgeSmoother: parseInt(document.getElementById('frameEdgeSmoother').value),
      sharpening: parseInt(document.getElementById('frameSharpening').value)
    };
  }

  resetFrameConfig() {
    document.getElementById('frameBrightness').value = 100;
    document.getElementById('brightnessValue').textContent = '100';
    document.getElementById('frameContrast').value = 100;
    document.getElementById('contrastValue').textContent = '100';
    document.getElementById('frameSaturation').value = 100;
    document.getElementById('saturationValue').textContent = '100';
    document.getElementById('frameDepthMultiplier').value = 15;
    document.getElementById('depthValue').textContent = '15';
    document.getElementById('frameLightDirection').value = 'top';
    document.getElementById('lightDirectionLabel').textContent = 'Top';
    document.getElementById('frameImageBlur').value = 0;
    document.getElementById('imageBlurValue').textContent = '0';
    document.getElementById('frameEdgeBlur').value = 1;
    document.getElementById('edgeBlurValue').textContent = '1';
    document.getElementById('frameOverlayOpacity').value = 0;
    document.getElementById('overlayValue').textContent = '0';
    document.getElementById('frameShadowIntensity').value = 0;
    document.getElementById('shadowValue').textContent = '0';
    document.getElementById('frameLightingAdjustment').value = 0;
    document.getElementById('lightingValue').textContent = '0';
    document.getElementById('frameColorTemperature').value = 0;
    document.getElementById('temperatureValue').textContent = '0';
    document.getElementById('frameVignette').value = 0;
    document.getElementById('vignetteValue').textContent = '0';
    document.getElementById('frameEdgeSmoother').value = 3;
    document.getElementById('edgeSmootherValue').textContent = '3';
    document.getElementById('frameSharpening').value = 0;
    document.getElementById('sharpeningValue').textContent = '0';

    // Reset light direction buttons
    document.querySelectorAll('.light-dir-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('.light-dir-btn[data-direction="top"]').classList.add('active');

    // Update slider fills
    document.querySelectorAll('#frameSettingsPanel input[type="range"]').forEach(slider => {
      this.updateSliderFill(slider);
    });
  }

  addFrame() {
    if (this.currentPoints.length !== 4) {
      this.showToast('Please select 4 corner points', 'error');
      return;
    }

    const frameConfig = this.getFrameConfig();

    this.allFrames.push({
      points: [...this.currentPoints],
      config: frameConfig
    });

    this.currentPoints = [];
    document.getElementById('addFrameBtn').disabled = true;
    document.getElementById('saveAllBtn').disabled = false;
    document.getElementById('framesInfo').style.display = 'block';
    document.getElementById('frameCount').textContent = this.allFrames.length;

    document.getElementById('setupHint').innerHTML =
      `Frame ${this.allFrames.length} added! Draw another box for more frames, or "Save All Frames" when done.`;

    // Hide frame config and test preview
    document.getElementById('frameSettingsPanel').style.display = 'none';
    document.getElementById('testPreviewSection').style.display = 'none';
    document.getElementById('testPreviewToggle').checked = false;
    this.testPreviewMode = false;
    this.testCreativeFile = null;
    this.testPreviewImage = null;
    document.getElementById('testPreviewUpload').style.display = 'none';
    document.getElementById('testCreativeUpload').value = '';

    // Reset config for next frame
    this.resetFrameConfig();
    this.updateProgress();
    this.redraw();

    this.showToast(`Frame ${this.allFrames.length} added!`, 'success');
  }

  resetCurrentFrame() {
    this.currentPoints = [];

    document.getElementById('frameSettingsPanel').style.display = 'none';
    document.getElementById('testPreviewSection').style.display = 'none';
    document.getElementById('testPreviewToggle').checked = false;
    this.testPreviewMode = false;
    this.testCreativeFile = null;
    this.testPreviewImage = null;
    document.getElementById('testPreviewUpload').style.display = 'none';
    document.getElementById('testCreativeUpload').value = '';

    this.redraw();
    document.getElementById('addFrameBtn').disabled = true;

    if (this.previewImg) {
      if (this.allFrames.length > 0) {
        document.getElementById('setupHint').innerHTML =
          `${this.allFrames.length} frame(s) saved. Draw another box for another frame, or "Save All Frames" when done.`;
      } else {
        document.getElementById('setupHint').innerHTML = 'Click and drag to draw a box around the billboard screen';
      }
    }
  }

  clearAllFrames() {
    if (!this.previewImg && this.allFrames.length === 0 && this.currentPoints.length === 0) return;
    if (!confirm('Clear all and start over? This will reset your work.')) return;

    // Reset all state
    this.allFrames = [];
    this.currentPoints = [];
    this.previewImg = null;
    this.currentPhoto = null;
    this.testPreviewImage = null;
    this.testCreativeFile = null;

    // Reset UI elements
    document.getElementById('addFrameBtn').disabled = true;
    document.getElementById('saveAllBtn').disabled = true;
    document.getElementById('framesInfo').style.display = 'none';
    document.getElementById('frameCount').textContent = '0';
    document.getElementById('frameSettingsPanel').style.display = 'none';
    document.getElementById('testPreviewSection').style.display = 'none';

    // Show upload zone, hide editor
    document.getElementById('uploadZone').style.display = 'flex';
    document.getElementById('settingsRow').style.display = 'none';
    document.getElementById('greenscreenSection').style.display = 'none';
    document.getElementById('editorSection').style.display = 'none';

    // Reset file input
    document.getElementById('imageUpload').value = '';

    this.updateProgress();
    this.clearCanvas();

    this.showToast('All cleared - upload a new image', 'success');
  }

  updateProgress() {
    const count = this.allFrames.length + (this.currentPoints.length === 4 ? 1 : 0);
    document.getElementById('currentFrame').textContent = count;
    document.getElementById('totalFrames').textContent = '?';
    document.getElementById('frameName').textContent = count > 0 ? `${count} frame(s) configured` : 'Draw frames on the image...';
    document.getElementById('progressFill').style.width = count > 0 ? '100%' : '0%';
  }

  async saveAllFrames() {
    const locationKey = document.getElementById('locationSelect').value;
    const timeOfDay = document.getElementById('timeOfDaySelect').value;
    const finish = document.getElementById('finishSelect').value;

    // Validate required fields
    if (!locationKey) {
      this.showToast('Please select a location', 'error');
      return;
    }

    if (!timeOfDay) {
      this.showToast('Please select time of day (Day or Night)', 'error');
      return;
    }

    if (!finish) {
      this.showToast('Please select billboard finish (Gold or Silver)', 'error');
      return;
    }

    // Add current frame if it has 4 points
    if (this.currentPoints.length === 4) {
      const frameConfig = this.getFrameConfig();
      this.allFrames.push({
        points: [...this.currentPoints],
        config: frameConfig
      });
      this.currentPoints = [];
    }

    if (this.allFrames.length === 0) {
      this.showToast('Please add at least one frame', 'error');
      return;
    }

    if (!this.currentPhoto) {
      this.showToast('Please upload a photo', 'error');
      return;
    }

    const formData = new FormData();
    formData.append('location_key', locationKey);
    formData.append('time_of_day', timeOfDay);
    formData.append('finish', finish);
    formData.append('photo', this.currentPhoto);
    formData.append('frames_data', JSON.stringify(this.allFrames));

    try {
      const response = await fetch('/api/mockup/save-frame', {
        method: 'POST',
        headers: { 'X-Session-Id': this.sessionId },
        body: formData
      });

      const result = await response.json();

      if (response.ok) {
        this.showToast(`Saved ${this.allFrames.length} frame(s) successfully!`, 'success');
        this.clearAllFrames();
        document.getElementById('imageUpload').value = '';
        this.previewImg = null;
        this.currentPhoto = null;
        this.loadPhotoList();
      } else {
        this.showToast(result.error || 'Failed to save frames', 'error');
      }
    } catch (err) {
      this.showToast('Network error: ' + err.message, 'error');
    }
  }

  // ========================================
  // GREEN SCREEN DETECTION
  // ========================================

  detectGreenScreen() {
    if (!this.previewImg) return;

    // Draw image to a temp canvas for pixel analysis
    const tempCanvas = document.createElement('canvas');
    tempCanvas.width = this.previewImg.width;
    tempCanvas.height = this.previewImg.height;
    const tempCtx = tempCanvas.getContext('2d');
    tempCtx.drawImage(this.previewImg, 0, 0);
    const imageData = tempCtx.getImageData(0, 0, this.previewImg.width, this.previewImg.height);

    const detectedFrame = this.detectGreenScreenFromImageData(imageData);

    if (detectedFrame) {
      this.currentPoints = detectedFrame;
      document.getElementById('addFrameBtn').disabled = false;
      document.getElementById('setupHint').innerHTML =
        'Green screen detected! Frame auto-configured. Drag corners to adjust or click "Add Frame" to save.';
      document.getElementById('frameSettingsPanel').style.display = 'block';
      document.getElementById('testPreviewSection').style.display = 'block';

      this.showToast('Green screen detected successfully!', 'success');
    } else {
      document.getElementById('setupHint').innerHTML =
        'No green screen detected. Try adjusting tolerance or draw frame manually.';
      this.showToast('No green screen detected', 'error');
    }

    this.redraw();
  }

  detectGreenScreenFromImageData(imageData) {
    const data = imageData.data;
    const width = imageData.width;
    const height = imageData.height;

    const targetHex = document.getElementById('greenscreenColor').value;
    const targetR = parseInt(targetHex.slice(1, 3), 16);
    const targetG = parseInt(targetHex.slice(3, 5), 16);
    const targetB = parseInt(targetHex.slice(5, 7), 16);
    const colorTolerance = parseInt(document.getElementById('colorTolerance').value);

    // Create exclusion mask for already-marked frames
    const exclusionMask = new Uint8Array(width * height);
    this.allFrames.forEach(frameData => {
      const pts = frameData.points;
      for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
          if (this.isPointInPolygon(x, y, pts)) {
            exclusionMask[y * width + x] = 1;
          }
        }
      }
    });

    // Create binary mask of matching pixels
    const mask = new Uint8Array(width * height);
    let matchedPixelCount = 0;

    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const pixelIdx = y * width + x;

        if (exclusionMask[pixelIdx] === 1) {
          mask[pixelIdx] = 0;
          continue;
        }

        const i = pixelIdx * 4;
        const r = data[i];
        const g = data[i + 1];
        const b = data[i + 2];

        const distance = Math.sqrt(
          Math.pow(r - targetR, 2) +
          Math.pow(g - targetG, 2) +
          Math.pow(b - targetB, 2)
        );

        if (distance <= colorTolerance) {
          mask[pixelIdx] = 255;
          matchedPixelCount++;
        }
      }
    }

    if (matchedPixelCount < 1000) {
      console.log('[Green Screen] Not enough pixels matched');
      return null;
    }

    // Dilate the mask
    const dilatedMask = new Uint8Array(width * height);
    const expandPixels = 3;

    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const idx = y * width + x;
        let hasGreenNearby = false;

        for (let dy = -expandPixels; dy <= expandPixels && !hasGreenNearby; dy++) {
          for (let dx = -expandPixels; dx <= expandPixels && !hasGreenNearby; dx++) {
            const ny = y + dy;
            const nx = x + dx;
            if (ny >= 0 && ny < height && nx >= 0 && nx < width) {
              if (mask[ny * width + nx] === 255) {
                hasGreenNearby = true;
              }
            }
          }
        }

        dilatedMask[idx] = hasGreenNearby ? 255 : 0;
      }
    }

    // Find contour points
    const contourPoints = [];
    for (let y = 1; y < height - 1; y++) {
      for (let x = 1; x < width - 1; x++) {
        const idx = y * width + x;
        if (dilatedMask[idx] === 0) {
          const hasDilatedNeighbor =
            dilatedMask[idx - 1] === 255 ||
            dilatedMask[idx + 1] === 255 ||
            dilatedMask[idx - width] === 255 ||
            dilatedMask[idx + width] === 255;

          if (hasDilatedNeighbor) {
            contourPoints.push([x, y]);
          }
        }
      }
    }

    if (contourPoints.length < 4) {
      console.log('[Green Screen] Not enough contour points');
      return null;
    }

    // Find the 4 extreme corner points
    let topLeft = contourPoints[0];
    let topRight = contourPoints[0];
    let bottomRight = contourPoints[0];
    let bottomLeft = contourPoints[0];

    for (const pt of contourPoints) {
      const [x, y] = pt;
      if (x + y < topLeft[0] + topLeft[1]) topLeft = pt;
      if (x - y > topRight[0] - topRight[1]) topRight = pt;
      if (x + y > bottomRight[0] + bottomRight[1]) bottomRight = pt;
      if (x - y < bottomLeft[0] - bottomLeft[1]) bottomLeft = pt;
    }

    // Apply perspective-aware adaptive padding
    const depthMultiplier = parseInt(document.getElementById('frameDepthMultiplier').value);
    const topWidth = Math.abs(topRight[0] - topLeft[0]);
    const bottomWidth = Math.abs(bottomRight[0] - bottomLeft[0]);
    const widthRatio = topWidth / bottomWidth;

    if (widthRatio > 1.1) {
      const extra = Math.floor((widthRatio - 1) * depthMultiplier);
      bottomLeft[1] = Math.min(height - 1, bottomLeft[1] + extra);
      bottomRight[1] = Math.min(height - 1, bottomRight[1] + extra);
    } else if (widthRatio < 0.9) {
      const extra = Math.floor((1 / widthRatio - 1) * depthMultiplier);
      topLeft[1] = Math.max(0, topLeft[1] - extra);
      topRight[1] = Math.max(0, topRight[1] - extra);
    }

    return [topLeft, topRight, bottomRight, bottomLeft];
  }

  isPointInPolygon(x, y, points) {
    let inside = false;
    for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
      const xi = points[i][0], yi = points[i][1];
      const xj = points[j][0], yj = points[j][1];

      const intersect = ((yi > y) !== (yj > y))
          && (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
      if (intersect) inside = !inside;
    }
    return inside;
  }

  // ========================================
  // TEST PREVIEW
  // ========================================

  async generateBackendPreview() {
    if (!this.testCreativeFile || !this.currentPhoto || this.currentPoints.length !== 4) {
      this.showToast('Please upload a billboard photo, draw a frame, and upload a test creative', 'error');
      return;
    }

    if (this.isGeneratingPreview) return;
    this.isGeneratingPreview = true;

    const btn = document.getElementById('generatePreviewBtn');
    const btnText = document.getElementById('previewBtnText');
    const loading = document.getElementById('previewLoading');
    btn.disabled = true;
    btnText.style.display = 'none';
    loading.style.display = 'inline';

    try {
      const frameConfig = this.getFrameConfig();
      const formData = new FormData();
      formData.append('billboard_photo', this.currentPhoto);
      formData.append('creative', this.testCreativeFile);
      formData.append('frame_points', JSON.stringify(this.currentPoints));
      formData.append('config', JSON.stringify(frameConfig));
      formData.append('time_of_day', document.getElementById('timeOfDaySelect').value || 'day');

      const response = await fetch('/api/mockup/test-preview', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        throw new Error(`Preview failed: ${response.statusText}`);
      }

      const blob = await response.blob();
      const imageUrl = URL.createObjectURL(blob);

      const img = new Image();
      img.onload = () => {
        this.testPreviewImage = img;
        this.redraw();
        this.showToast('Preview generated!', 'success');
      };
      img.src = imageUrl;

    } catch (error) {
      console.error('[Test Preview] Error:', error);
      this.showToast('Error generating preview: ' + error.message, 'error');
    } finally {
      this.isGeneratingPreview = false;
      btn.disabled = false;
      btnText.style.display = 'inline';
      loading.style.display = 'none';
    }
  }

  // ========================================
  // PHOTO LIST
  // ========================================

  async loadPhotoList() {
    const locationKey = document.getElementById('locationSelect').value;
    const photoGrid = document.getElementById('photoGrid');

    if (!locationKey) {
      photoGrid.innerHTML = '<p class="no-photos">Select a location to view existing photos.</p>';
      return;
    }

    try {
      const response = await fetch(`/api/mockup/photos/${locationKey}`);
      const data = await response.json();

      if (!data.photos || data.photos.length === 0) {
        photoGrid.innerHTML = '<p class="no-photos">No photos configured for this location yet.</p>';
        return;
      }

      photoGrid.innerHTML = data.photos.map(photo => `
        <div class="photo-card">
          <img src="/api/mockup/photo/${locationKey}/${photo}" alt="${photo}">
          <div class="photo-card-info">
            <h4>${photo}</h4>
            <button class="btn btn-danger btn-sm" onclick="app.deletePhoto('${locationKey}', '${photo}')">Delete</button>
          </div>
        </div>
      `).join('');
    } catch (err) {
      this.showToast('Failed to load photos', 'error');
    }
  }

  async deletePhoto(locationKey, photoFilename) {
    if (!confirm(`Delete ${photoFilename}?`)) return;

    try {
      const response = await fetch(`/api/mockup/photo/${locationKey}/${photoFilename}`, {
        method: 'DELETE',
        headers: { 'X-Session-Id': this.sessionId }
      });

      if (response.ok) {
        this.showToast('Photo deleted successfully', 'success');
        this.loadPhotoList();
      } else {
        const result = await response.json();
        this.showToast(result.error || 'Failed to delete photo', 'error');
      }
    } catch (err) {
      this.showToast('Network error: ' + err.message, 'error');
    }
  }

  // ========================================
  // GENERATE MODE
  // ========================================

  async loadTemplatesForGenerate() {
    const locationKey = document.getElementById('generateLocationSelect').value;
    const timeOfDay = document.getElementById('generateTimeOfDay').value;
    const finish = document.getElementById('generateFinish').value;

    if (!locationKey) {
      document.getElementById('templateSelectionGroup').style.display = 'none';
      document.getElementById('generateConfigSection').style.display = 'none';
      this.selectedTemplateConfig = null;
      this.updateGenerateButtonState();
      return;
    }

    try {
      const response = await fetch(`/api/mockup/templates/${locationKey}?time_of_day=${timeOfDay}&finish=${finish}`);
      const data = await response.json();

      const templateSelect = document.getElementById('generateTemplate');
      templateSelect.innerHTML = '<option value="">-- Select a template --</option>';
      this.selectedTemplateConfig = null;

      if (data.templates && data.templates.length > 0) {
        data.templates.forEach(template => {
          const displayName = `${template.photo} (${template.time_of_day}/${template.finish}, ${template.frame_count} frame${template.frame_count > 1 ? 's' : ''})`;
          const option = document.createElement('option');
          option.value = JSON.stringify({
            photo: template.photo,
            time_of_day: template.time_of_day,
            finish: template.finish,
            config: template.config
          });
          option.textContent = displayName;
          templateSelect.appendChild(option);
        });

        document.getElementById('templateSelectionGroup').style.display = 'block';
      } else {
        document.getElementById('templateSelectionGroup').style.display = 'none';
        document.getElementById('generateConfigToggleSection').style.display = 'none';
        document.getElementById('generateConfigSection').style.display = 'none';
      }

      this.updateGenerateButtonState();
    } catch (err) {
      console.error('Error loading templates:', err);
      this.showToast('Failed to load templates', 'error');
    }
  }

  loadTemplateConfig() {
    const templateSelect = document.getElementById('generateTemplate');
    const selectedValue = templateSelect.value;

    if (!selectedValue) {
      document.getElementById('generateConfigToggleSection').style.display = 'none';
      document.getElementById('generateConfigSection').style.display = 'none';
      document.getElementById('generateConfigToggle').checked = false;
      this.selectedTemplateConfig = null;
      return;
    }

    try {
      const templateData = JSON.parse(selectedValue);
      this.selectedTemplateConfig = templateData;
      const config = templateData.config || {};

      // Populate all config controls
      document.getElementById('genFrameBrightness').value = config.brightness || 100;
      document.getElementById('genBrightnessValue').textContent = config.brightness || 100;
      document.getElementById('genFrameContrast').value = config.contrast || 100;
      document.getElementById('genContrastValue').textContent = config.contrast || 100;
      document.getElementById('genFrameSaturation').value = config.saturation || 100;
      document.getElementById('genSaturationValue').textContent = config.saturation || 100;
      document.getElementById('genFrameDepthMultiplier').value = config.depthMultiplier || 15;
      document.getElementById('genDepthValue').textContent = config.depthMultiplier || 15;
      document.getElementById('genFrameLightDirection').value = config.lightDirection || 'top';
      document.getElementById('genFrameImageBlur').value = config.imageBlur || 0;
      document.getElementById('genImageBlurValue').textContent = config.imageBlur || 0;
      document.getElementById('genFrameEdgeBlur').value = config.edgeBlur || 1;
      document.getElementById('genEdgeBlurValue').textContent = config.edgeBlur || 1;
      document.getElementById('genFrameOverlayOpacity').value = config.overlayOpacity || 0;
      document.getElementById('genOverlayValue').textContent = config.overlayOpacity || 0;
      document.getElementById('genFrameShadowIntensity').value = config.shadowIntensity || 0;
      document.getElementById('genShadowValue').textContent = config.shadowIntensity || 0;
      document.getElementById('genFrameLightingAdjustment').value = config.lightingAdjustment || 0;
      document.getElementById('genLightingValue').textContent = config.lightingAdjustment || 0;
      document.getElementById('genFrameColorTemperature').value = config.colorTemperature || 0;
      document.getElementById('genTemperatureValue').textContent = config.colorTemperature || 0;
      document.getElementById('genFrameVignette').value = config.vignette || 0;
      document.getElementById('genVignetteValue').textContent = config.vignette || 0;
      document.getElementById('genFrameEdgeSmoother').value = config.edgeSmoother || 3;
      document.getElementById('genEdgeSmootherValue').textContent = config.edgeSmoother || 3;
      document.getElementById('genFrameSharpening').value = config.sharpening || 0;
      document.getElementById('genSharpeningValue').textContent = config.sharpening || 0;

      // Update light direction buttons
      const lightDirection = config.lightDirection || 'top';
      document.querySelectorAll('.gen-light-dir-btn').forEach(btn => btn.classList.remove('active'));
      const activeBtn = document.querySelector(`.gen-light-dir-btn[data-direction="${lightDirection}"]`);
      if (activeBtn) activeBtn.classList.add('active');

      const labelMap = {
        'top-left': 'Top Left', 'top': 'Top', 'top-right': 'Top Right',
        'left': 'Left', 'center': 'Center', 'right': 'Right',
        'bottom-left': 'Bottom Left', 'bottom': 'Bottom', 'bottom-right': 'Bottom Right'
      };
      document.getElementById('genLightDirectionLabel').textContent = labelMap[lightDirection] || 'Top';

      // Update slider fills
      document.querySelectorAll('#generateConfigSection input[type="range"]').forEach(slider => {
        this.updateSliderFill(slider);
      });

      document.getElementById('generateConfigToggleSection').style.display = 'block';

      if (document.getElementById('generateConfigToggle').checked) {
        document.getElementById('generateConfigSection').style.display = 'block';
      }
    } catch (err) {
      console.error('Error loading template config:', err);
      this.showToast('Error loading template configuration', 'error');
    }
  }

  updateGenerateButtonState() {
    const hasFile = document.getElementById('creativeUpload').files.length > 0;
    const hasPrompt = document.getElementById('aiCreativePrompt').value.trim().length > 0;
    const hasLocation = document.getElementById('generateLocationSelect').value !== '';
    document.getElementById('generateBtn').disabled = !hasLocation || (!hasFile && !hasPrompt);
  }

  async generateMockup() {
    const locationKey = document.getElementById('generateLocationSelect').value;
    const timeOfDay = document.getElementById('generateTimeOfDay').value;
    const finish = document.getElementById('generateFinish').value;
    const creativeFile = document.getElementById('creativeUpload').files[0];
    const aiPrompt = document.getElementById('aiCreativePrompt').value.trim();

    if (!locationKey) {
      this.showToast('Please select a location', 'error');
      return;
    }

    if (!creativeFile && !aiPrompt) {
      this.showToast('Please either upload a creative image OR provide an AI prompt', 'error');
      return;
    }

    const formData = new FormData();
    formData.append('location_key', locationKey);

    if (this.selectedTemplateConfig) {
      formData.append('time_of_day', this.selectedTemplateConfig.time_of_day);
      formData.append('finish', this.selectedTemplateConfig.finish);
      formData.append('specific_photo', this.selectedTemplateConfig.photo);

      const frameConfig = {
        brightness: parseInt(document.getElementById('genFrameBrightness').value),
        contrast: parseInt(document.getElementById('genFrameContrast').value),
        saturation: parseInt(document.getElementById('genFrameSaturation').value),
        depthMultiplier: parseInt(document.getElementById('genFrameDepthMultiplier').value),
        lightDirection: document.getElementById('genFrameLightDirection').value,
        imageBlur: parseInt(document.getElementById('genFrameImageBlur').value),
        edgeBlur: parseInt(document.getElementById('genFrameEdgeBlur').value),
        overlayOpacity: parseInt(document.getElementById('genFrameOverlayOpacity').value),
        shadowIntensity: parseInt(document.getElementById('genFrameShadowIntensity').value),
        lightingAdjustment: parseInt(document.getElementById('genFrameLightingAdjustment').value),
        colorTemperature: parseInt(document.getElementById('genFrameColorTemperature').value),
        vignette: parseInt(document.getElementById('genFrameVignette').value),
        edgeSmoother: parseInt(document.getElementById('genFrameEdgeSmoother').value),
        sharpening: parseInt(document.getElementById('genFrameSharpening').value)
      };

      formData.append('frame_config', JSON.stringify(frameConfig));
    } else {
      formData.append('time_of_day', timeOfDay);
      formData.append('finish', finish);
    }

    if (aiPrompt) {
      formData.append('ai_prompt', aiPrompt);
    } else {
      formData.append('creative', creativeFile);
    }

    document.getElementById('generateLoading').style.display = 'block';
    document.getElementById('generateBtn').disabled = true;
    document.getElementById('mockupResult').innerHTML = '';

    try {
      const response = await fetch('/api/mockup/generate', {
        method: 'POST',
        body: formData
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);

        document.getElementById('mockupResult').innerHTML = `
          <h3>Generated Mockup</h3>
          <img src="${url}" alt="Generated Mockup" style="max-width: 100%; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">
          <div style="margin-top: 1rem;">
            <a href="${url}" download="mockup.jpg" class="btn btn-primary">Download Mockup</a>
          </div>
        `;
        this.showToast('Mockup generated successfully!', 'success');
      } else {
        const result = await response.json();
        this.showToast(result.error || 'Failed to generate mockup', 'error');
      }
    } catch (err) {
      this.showToast('Network error: ' + err.message, 'error');
    } finally {
      document.getElementById('generateLoading').style.display = 'none';
      document.getElementById('generateBtn').disabled = false;
    }
  }

  // ========================================
  // TEMPLATES MODAL
  // ========================================

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
              <span>${template.frames ? template.frames.length : 0} frames</span>
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

  // ========================================
  // TOAST NOTIFICATIONS
  // ========================================

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

// Make MockupStudio globally available
window.MockupStudio = MockupStudio;

// ========================================
// APP INITIALIZATION
// ========================================
let app;

document.addEventListener('DOMContentLoaded', () => {
  // Initialize Toast first
  Toast.init();

  // Initialize Auth (handles landing/login/app state)
  // Auth.init() is called from auth.js

  // MockupStudio will be initialized when the mockup tool is selected
  // via Sidebar.initMockup()
});

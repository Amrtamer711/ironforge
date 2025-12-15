/**
 * Mockup Studio Module
 * Handles mockup setup (admin/hos only) and generation (all users)
 */

const MockupGenerator = {
  // State
  currentMode: 'generate', // 'setup' or 'generate'
  selectedFile: null,
  locations: [],
  templates: [],
  isGenerating: false,
  initialized: false,
  canAccessSetup: false,

  // Setup mode state
  setup: {
    canvas: null,
    ctx: null,
    previewImg: null,
    currentPhoto: null,
    currentPoints: [],
    allFrames: [],
    imgNaturalW: 0,
    imgNaturalH: 0,
    drawX: 0,
    drawY: 0,
    drawW: 0,
    drawH: 0,
    scale: 1
  },

  /**
   * Initialize the mockup generator
   */
  init() {
    if (this.initialized) {
      console.log('[MockupGenerator] Already initialized');
      return;
    }

    console.log('[MockupGenerator] Initializing...');

    // Check user permissions for setup mode
    this.checkPermissions();

    // Setup event listeners
    this.setupEventListeners();

    // Load locations for both modes
    this.loadLocations();

    // Initialize setup canvas if user has access
    if (this.canAccessSetup) {
      this.initSetupCanvas();
    }

    this.initialized = true;
    console.log('[MockupGenerator] Initialized');
  },

  /**
   * Check if user has permission to access setup mode
   */
  checkPermissions() {
    const user = Auth?.getUser?.();
    const roles = user?.roles || [];

    // Admin or HoS can access setup
    this.canAccessSetup = roles.includes('admin') || roles.includes('hos');

    console.log('[MockupGenerator] User roles:', roles, 'Can access setup:', this.canAccessSetup);

    // Show/hide setup mode button based on permissions
    const setupBtn = document.getElementById('mockupSetupModeBtn');
    if (setupBtn) {
      setupBtn.style.display = this.canAccessSetup ? 'flex' : 'none';
    }
  },

  /**
   * Setup all event listeners
   */
  setupEventListeners() {
    // Mode toggle buttons
    const setupModeBtn = document.getElementById('mockupSetupModeBtn');
    const generateModeBtn = document.getElementById('mockupGenerateModeBtn');

    if (setupModeBtn) {
      setupModeBtn.addEventListener('click', () => this.switchMode('setup'));
    }
    if (generateModeBtn) {
      generateModeBtn.addEventListener('click', () => this.switchMode('generate'));
    }

    // === GENERATE MODE LISTENERS ===
    this.setupGenerateModeListeners();

    // === SETUP MODE LISTENERS ===
    if (this.canAccessSetup) {
      this.setupSetupModeListeners();
    }
  },

  /**
   * Setup generate mode event listeners
   */
  setupGenerateModeListeners() {
    // Location select
    const locationSelect = document.getElementById('mockupLocationSelect');
    if (locationSelect) {
      locationSelect.addEventListener('change', () => this.onLocationChange());
    }

    // Time of day and finish selects
    const timeOfDaySelect = document.getElementById('mockupTimeOfDay');
    const finishSelect = document.getElementById('mockupFinish');
    if (timeOfDaySelect) {
      timeOfDaySelect.addEventListener('change', () => this.onFilterChange());
    }
    if (finishSelect) {
      finishSelect.addEventListener('change', () => this.onFilterChange());
    }

    // File upload
    const uploadZone = document.getElementById('mockupUploadZone');
    const fileInput = document.getElementById('mockupCreativeUpload');
    const clearBtn = document.getElementById('mockupClearFile');

    if (uploadZone && fileInput) {
      uploadZone.addEventListener('click', () => fileInput.click());
      fileInput.addEventListener('change', (e) => this.handleFileSelect(e));

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
        if (e.dataTransfer.files.length > 0) {
          this.handleFile(e.dataTransfer.files[0]);
        }
      });
    }

    if (clearBtn) {
      clearBtn.addEventListener('click', () => this.clearFile());
    }

    // AI prompt textarea
    const aiPrompt = document.getElementById('mockupAiPrompt');
    if (aiPrompt) {
      aiPrompt.addEventListener('input', () => this.updateGenerateButton());
    }

    // Generate button
    const generateBtn = document.getElementById('mockupGenerateBtn');
    if (generateBtn) {
      generateBtn.addEventListener('click', () => this.generateMockup());
    }

    // Regenerate button
    const regenerateBtn = document.getElementById('mockupRegenerateBtn');
    if (regenerateBtn) {
      regenerateBtn.addEventListener('click', () => this.generateMockup());
    }
  },

  /**
   * Setup setup mode event listeners
   */
  setupSetupModeListeners() {
    // Setup location select
    const setupLocationSelect = document.getElementById('setupLocationSelect');
    if (setupLocationSelect) {
      setupLocationSelect.addEventListener('change', () => this.onSetupLocationChange());
    }

    // Setup photo upload
    const setupUploadZone = document.getElementById('setupUploadZone');
    const setupPhotoInput = document.getElementById('setupPhotoUpload');

    if (setupUploadZone && setupPhotoInput) {
      setupUploadZone.addEventListener('click', () => setupPhotoInput.click());
      setupPhotoInput.addEventListener('change', (e) => this.handleSetupPhotoSelect(e));

      // Drag and drop
      setupUploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        setupUploadZone.classList.add('drag-over');
      });
      setupUploadZone.addEventListener('dragleave', () => {
        setupUploadZone.classList.remove('drag-over');
      });
      setupUploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        setupUploadZone.classList.remove('drag-over');
        if (e.dataTransfer.files.length > 0) {
          this.handleSetupPhoto(e.dataTransfer.files[0]);
        }
      });
    }

    // Green screen toggle
    const greenscreenToggle = document.getElementById('setupGreenscreenToggle');
    if (greenscreenToggle) {
      greenscreenToggle.addEventListener('change', (e) => {
        const options = document.getElementById('setupGreenscreenOptions');
        if (options) {
          options.style.display = e.target.checked ? 'block' : 'none';
        }
      });
    }

    // Color picker sync
    const colorPicker = document.getElementById('setupGreenscreenColor');
    const colorHex = document.getElementById('setupGreenscreenHex');
    if (colorPicker && colorHex) {
      colorPicker.addEventListener('input', (e) => {
        colorHex.value = e.target.value.toUpperCase();
      });
      colorHex.addEventListener('input', (e) => {
        if (/^#[0-9A-F]{6}$/i.test(e.target.value)) {
          colorPicker.value = e.target.value;
        }
      });
    }

    // Tolerance slider
    const toleranceSlider = document.getElementById('setupColorTolerance');
    const toleranceValue = document.getElementById('setupToleranceValue');
    if (toleranceSlider && toleranceValue) {
      toleranceSlider.addEventListener('input', (e) => {
        toleranceValue.textContent = e.target.value;
      });
    }

    // Frame config sliders
    this.setupFrameConfigSliders();

    // Action buttons
    const addFrameBtn = document.getElementById('setupAddFrameBtn');
    const resetFrameBtn = document.getElementById('setupResetFrameBtn');
    const saveAllBtn = document.getElementById('setupSaveAllBtn');
    const clearAllBtn = document.getElementById('setupClearAllBtn');
    const detectBtn = document.getElementById('setupDetectBtn');

    if (addFrameBtn) {
      addFrameBtn.addEventListener('click', () => this.addFrame());
    }
    if (resetFrameBtn) {
      resetFrameBtn.addEventListener('click', () => this.resetCurrentFrame());
    }
    if (saveAllBtn) {
      saveAllBtn.addEventListener('click', () => this.saveAllFrames());
    }
    if (clearAllBtn) {
      clearAllBtn.addEventListener('click', () => this.clearAllFrames());
    }
    if (detectBtn) {
      detectBtn.addEventListener('click', () => this.detectGreenScreen());
    }
  },

  /**
   * Setup frame configuration sliders
   */
  setupFrameConfigSliders() {
    const sliders = [
      { id: 'setupBrightness', valueId: 'setupBrightnessValue', suffix: '%' },
      { id: 'setupContrast', valueId: 'setupContrastValue', suffix: '%' },
      { id: 'setupSaturation', valueId: 'setupSaturationValue', suffix: '%' },
      { id: 'setupEdgeBlur', valueId: 'setupEdgeBlurValue', suffix: 'px' },
      { id: 'setupOverlayOpacity', valueId: 'setupOverlayValue', suffix: '%' },
      { id: 'setupEdgeSmoother', valueId: 'setupEdgeSmootherValue', suffix: 'x' }
    ];

    sliders.forEach(({ id, valueId, suffix }) => {
      const slider = document.getElementById(id);
      const valueEl = document.getElementById(valueId);
      if (slider && valueEl) {
        slider.addEventListener('input', (e) => {
          valueEl.textContent = e.target.value + (suffix === '%' || suffix === 'x' ? '' : '');
        });
      }
    });
  },

  /**
   * Switch between setup and generate modes
   */
  switchMode(mode) {
    if (mode === 'setup' && !this.canAccessSetup) {
      this.showToast('You do not have permission to access Setup mode', 'error');
      return;
    }

    this.currentMode = mode;

    // Update button states
    const setupBtn = document.getElementById('mockupSetupModeBtn');
    const generateBtn = document.getElementById('mockupGenerateModeBtn');

    if (setupBtn) setupBtn.classList.toggle('active', mode === 'setup');
    if (generateBtn) generateBtn.classList.toggle('active', mode === 'generate');

    // Show/hide mode content
    const setupMode = document.getElementById('mockupSetupMode');
    const generateMode = document.getElementById('mockupGenerateMode');

    if (setupMode) setupMode.style.display = mode === 'setup' ? 'block' : 'none';
    if (generateMode) generateMode.style.display = mode === 'generate' ? 'block' : 'none';

    console.log('[MockupGenerator] Switched to', mode, 'mode');
  },

  /**
   * Initialize setup canvas
   */
  initSetupCanvas() {
    const canvas = document.getElementById('setupCanvas');
    if (!canvas) return;

    this.setup.canvas = canvas;
    this.setup.ctx = canvas.getContext('2d');

    // Canvas click handler for selecting points
    canvas.addEventListener('click', (e) => this.onCanvasClick(e));
    canvas.addEventListener('mousemove', (e) => this.onCanvasMouseMove(e));

    // Shift+click for color picking
    canvas.addEventListener('click', (e) => {
      if (e.shiftKey && this.setup.previewImg) {
        this.pickColorFromCanvas(e);
      }
    });
  },

  /**
   * Handle canvas click for point selection
   */
  onCanvasClick(e) {
    if (e.shiftKey) return; // Color picking mode

    const canvas = this.setup.canvas;
    if (!canvas || !this.setup.previewImg) return;

    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;

    const canvasX = (e.clientX - rect.left) * scaleX;
    const canvasY = (e.clientY - rect.top) * scaleY;

    // Convert to image coordinates
    const imgX = (canvasX - this.setup.drawX) / this.setup.scale;
    const imgY = (canvasY - this.setup.drawY) / this.setup.scale;

    // Only add point if within image bounds
    if (imgX >= 0 && imgX <= this.setup.imgNaturalW &&
        imgY >= 0 && imgY <= this.setup.imgNaturalH) {
      this.setup.currentPoints.push({ x: imgX, y: imgY });
      this.redrawCanvas();
      this.updateSetupButtons();

      // Show frame config when 4 points selected
      if (this.setup.currentPoints.length === 4) {
        const frameConfig = document.getElementById('setupFrameConfig');
        if (frameConfig) frameConfig.style.display = 'block';
      }
    }
  },

  /**
   * Handle canvas mouse move for crosshair
   */
  onCanvasMouseMove(e) {
    // Could add crosshair cursor or hover effects here
  },

  /**
   * Pick color from canvas for green screen detection
   */
  pickColorFromCanvas(e) {
    const canvas = this.setup.canvas;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;

    const canvasX = (e.clientX - rect.left) * scaleX;
    const canvasY = (e.clientY - rect.top) * scaleY;

    const pixel = this.setup.ctx.getImageData(canvasX, canvasY, 1, 1).data;
    const hex = '#' + [pixel[0], pixel[1], pixel[2]].map(x => x.toString(16).padStart(2, '0')).join('').toUpperCase();

    const colorPicker = document.getElementById('setupGreenscreenColor');
    const colorHex = document.getElementById('setupGreenscreenHex');

    if (colorPicker) colorPicker.value = hex;
    if (colorHex) colorHex.value = hex;

    this.showToast(`Color picked: ${hex}`, 'success');
  },

  /**
   * Redraw the setup canvas
   */
  redrawCanvas() {
    const { canvas, ctx, previewImg, drawX, drawY, drawW, drawH, scale, currentPoints, allFrames } = this.setup;
    if (!canvas || !ctx) return;

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw background
    ctx.fillStyle = '#f8f9fa';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Draw image if loaded
    if (previewImg) {
      ctx.drawImage(previewImg, drawX, drawY, drawW, drawH);
    }

    // Draw existing frames
    allFrames.forEach((frame, idx) => {
      this.drawFrame(ctx, frame, scale, drawX, drawY, `Frame ${idx + 1}`, '#28a745');
    });

    // Draw current points
    if (currentPoints.length > 0) {
      ctx.fillStyle = '#667eea';
      ctx.strokeStyle = '#667eea';
      ctx.lineWidth = 2;

      currentPoints.forEach((pt, idx) => {
        const x = pt.x * scale + drawX;
        const y = pt.y * scale + drawY;

        // Draw point
        ctx.beginPath();
        ctx.arc(x, y, 6, 0, Math.PI * 2);
        ctx.fill();

        // Draw label
        ctx.fillStyle = 'white';
        ctx.font = 'bold 12px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(idx + 1, x, y);
        ctx.fillStyle = '#667eea';

        // Draw line to previous point
        if (idx > 0) {
          const prevPt = currentPoints[idx - 1];
          ctx.beginPath();
          ctx.moveTo(prevPt.x * scale + drawX, prevPt.y * scale + drawY);
          ctx.lineTo(x, y);
          ctx.stroke();
        }
      });

      // Close the shape if 4 points
      if (currentPoints.length === 4) {
        ctx.beginPath();
        ctx.moveTo(currentPoints[3].x * scale + drawX, currentPoints[3].y * scale + drawY);
        ctx.lineTo(currentPoints[0].x * scale + drawX, currentPoints[0].y * scale + drawY);
        ctx.stroke();
      }
    }
  },

  /**
   * Draw a saved frame on canvas
   */
  drawFrame(ctx, frame, scale, offsetX, offsetY, label, color) {
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.fillStyle = color + '33'; // Semi-transparent fill

    ctx.beginPath();
    ctx.moveTo(frame[0].x * scale + offsetX, frame[0].y * scale + offsetY);
    for (let i = 1; i < frame.length; i++) {
      ctx.lineTo(frame[i].x * scale + offsetX, frame[i].y * scale + offsetY);
    }
    ctx.closePath();
    ctx.fill();
    ctx.stroke();

    // Draw label
    const centerX = frame.reduce((sum, pt) => sum + pt.x, 0) / frame.length * scale + offsetX;
    const centerY = frame.reduce((sum, pt) => sum + pt.y, 0) / frame.length * scale + offsetY;

    ctx.fillStyle = color;
    ctx.font = 'bold 14px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(label, centerX, centerY);
  },

  /**
   * Update setup button states
   */
  updateSetupButtons() {
    const addFrameBtn = document.getElementById('setupAddFrameBtn');
    const saveAllBtn = document.getElementById('setupSaveAllBtn');
    const detectBtn = document.getElementById('setupDetectBtn');
    const greenscreenToggle = document.getElementById('setupGreenscreenToggle');

    if (addFrameBtn) {
      addFrameBtn.disabled = this.setup.currentPoints.length !== 4;
    }
    if (saveAllBtn) {
      saveAllBtn.disabled = this.setup.allFrames.length === 0;
    }
    if (detectBtn) {
      detectBtn.disabled = !greenscreenToggle?.checked || !this.setup.previewImg;
    }

    // Update frame count display
    const framesInfo = document.getElementById('setupFramesInfo');
    const frameCount = document.getElementById('setupFrameCount');
    if (framesInfo && frameCount) {
      framesInfo.style.display = this.setup.allFrames.length > 0 ? 'block' : 'none';
      frameCount.textContent = this.setup.allFrames.length;
    }
  },

  /**
   * Add current frame to list
   */
  addFrame() {
    if (this.setup.currentPoints.length !== 4) return;

    // Get frame config values
    const config = {
      brightness: parseInt(document.getElementById('setupBrightness')?.value || 100),
      contrast: parseInt(document.getElementById('setupContrast')?.value || 100),
      saturation: parseInt(document.getElementById('setupSaturation')?.value || 100),
      edge_blur: parseInt(document.getElementById('setupEdgeBlur')?.value || 1),
      overlay_opacity: parseInt(document.getElementById('setupOverlayOpacity')?.value || 0),
      edge_smoother: parseInt(document.getElementById('setupEdgeSmoother')?.value || 3)
    };

    // Save frame with config
    this.setup.allFrames.push({
      points: [...this.setup.currentPoints],
      config: config
    });

    // Reset current points
    this.setup.currentPoints = [];

    // Hide frame config
    const frameConfig = document.getElementById('setupFrameConfig');
    if (frameConfig) frameConfig.style.display = 'none';

    this.redrawCanvas();
    this.updateSetupButtons();
    this.showToast(`Frame ${this.setup.allFrames.length} added`, 'success');
  },

  /**
   * Reset current frame points
   */
  resetCurrentFrame() {
    this.setup.currentPoints = [];

    // Hide frame config
    const frameConfig = document.getElementById('setupFrameConfig');
    if (frameConfig) frameConfig.style.display = 'none';

    this.redrawCanvas();
    this.updateSetupButtons();
  },

  /**
   * Clear all frames
   */
  clearAllFrames() {
    if (!confirm('Clear all configured frames?')) return;

    this.setup.allFrames = [];
    this.setup.currentPoints = [];

    // Hide frame config
    const frameConfig = document.getElementById('setupFrameConfig');
    if (frameConfig) frameConfig.style.display = 'none';

    this.redrawCanvas();
    this.updateSetupButtons();
    this.showToast('All frames cleared', 'info');
  },

  /**
   * Save all frames to server
   */
  async saveAllFrames() {
    if (this.setup.allFrames.length === 0) {
      this.showToast('No frames to save', 'error');
      return;
    }

    const locationSelect = document.getElementById('setupLocationSelect');
    const location = locationSelect?.value;

    if (!location) {
      this.showToast('Please select a location', 'error');
      return;
    }

    const timeOfDay = document.getElementById('setupTimeOfDay')?.value || 'all';
    const finish = document.getElementById('setupFinish')?.value || 'all';

    try {
      // Build form data
      const formData = new FormData();
      formData.append('location_key', location);
      formData.append('time_of_day', timeOfDay);
      formData.append('finish', finish);

      // Convert frames to flat array format expected by API
      const framesData = this.setup.allFrames.map(frame => ({
        points: frame.points.flatMap(pt => [pt.x, pt.y]),
        config: frame.config
      }));
      formData.append('frames', JSON.stringify(framesData));

      // Add the photo if we have one
      if (this.setup.currentPhoto) {
        formData.append('photo', this.setup.currentPhoto);
      }

      const token = await API.getAuthToken();
      const response = await fetch('/api/sales/mockup/setup/save', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'Failed to save frames');
      }

      this.showToast('Frames saved successfully!', 'success');

      // Clear after successful save
      this.setup.allFrames = [];
      this.setup.currentPoints = [];
      this.updateSetupButtons();
      this.redrawCanvas();

      // Reload photos for this location
      this.loadSetupPhotos(location);

    } catch (error) {
      console.error('[MockupGenerator] Error saving frames:', error);
      this.showToast(error.message || 'Failed to save frames', 'error');
    }
  },

  /**
   * Detect green screen automatically
   */
  detectGreenScreen() {
    this.showToast('Green screen detection - Coming soon', 'info');
    // TODO: Implement green screen detection
  },

  /**
   * Handle setup location change
   */
  async onSetupLocationChange() {
    const locationSelect = document.getElementById('setupLocationSelect');
    const location = locationSelect?.value;

    if (location) {
      await this.loadSetupPhotos(location);
    }
  },

  /**
   * Load existing photos for a location in setup mode
   */
  async loadSetupPhotos(location) {
    const photosSection = document.getElementById('setupPhotosSection');
    const photosGrid = document.getElementById('setupPhotosGrid');

    if (!photosSection || !photosGrid) return;

    try {
      const timeOfDay = document.getElementById('setupTimeOfDay')?.value || 'all';
      const finish = document.getElementById('setupFinish')?.value || 'all';

      const params = new URLSearchParams();
      params.append('time_of_day', timeOfDay);
      params.append('finish', finish);

      const response = await API.request(`/api/sales/mockup/templates/${location}?${params}`);

      if (response && response.templates && response.templates.length > 0) {
        photosSection.style.display = 'block';
        photosGrid.innerHTML = response.templates.map(t => `
          <div class="setup-photo-card" data-photo="${t.photo}">
            <div class="setup-photo-thumb">
              <img src="/api/sales/mockup/photo/${location}/${t.photo}" alt="${t.photo}" loading="lazy">
            </div>
            <div class="setup-photo-info">
              <span class="photo-name">${t.photo}</span>
              <span class="photo-meta">${t.time_of_day}/${t.finish} - ${t.frame_count} frames</span>
            </div>
            <button class="btn btn-sm btn-danger setup-delete-photo" data-photo="${t.photo}">Delete</button>
          </div>
        `).join('');

        // Add click handlers for delete buttons
        photosGrid.querySelectorAll('.setup-delete-photo').forEach(btn => {
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.deleteSetupPhoto(location, btn.dataset.photo);
          });
        });
      } else {
        photosSection.style.display = 'none';
      }
    } catch (error) {
      console.error('[MockupGenerator] Error loading setup photos:', error);
    }
  },

  /**
   * Delete a setup photo
   */
  async deleteSetupPhoto(location, photo) {
    if (!confirm(`Delete photo "${photo}" and all its frames?`)) return;

    try {
      const token = await API.getAuthToken();
      const response = await fetch(`/api/sales/mockup/setup/delete/${location}/${photo}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (!response.ok) {
        throw new Error('Failed to delete photo');
      }

      this.showToast('Photo deleted', 'success');
      this.loadSetupPhotos(location);

    } catch (error) {
      console.error('[MockupGenerator] Error deleting photo:', error);
      this.showToast('Failed to delete photo', 'error');
    }
  },

  /**
   * Handle setup photo selection
   */
  handleSetupPhotoSelect(event) {
    const file = event.target.files?.[0];
    if (file) {
      this.handleSetupPhoto(file);
    }
  },

  /**
   * Handle setup photo upload
   */
  handleSetupPhoto(file) {
    const validTypes = ['image/jpeg', 'image/png', 'image/webp'];
    if (!validTypes.includes(file.type)) {
      this.showToast('Please upload a valid image file (JPG, PNG, WEBP)', 'error');
      return;
    }

    if (file.size > 20 * 1024 * 1024) {
      this.showToast('File size must be less than 20MB', 'error');
      return;
    }

    this.setup.currentPhoto = file;

    // Load image for canvas
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => {
        this.setup.previewImg = img;
        this.setup.imgNaturalW = img.naturalWidth;
        this.setup.imgNaturalH = img.naturalHeight;

        // Calculate draw dimensions to fit canvas
        const canvas = this.setup.canvas;
        const canvasRatio = canvas.width / canvas.height;
        const imgRatio = img.naturalWidth / img.naturalHeight;

        if (imgRatio > canvasRatio) {
          this.setup.drawW = canvas.width;
          this.setup.drawH = canvas.width / imgRatio;
          this.setup.drawX = 0;
          this.setup.drawY = (canvas.height - this.setup.drawH) / 2;
        } else {
          this.setup.drawH = canvas.height;
          this.setup.drawW = canvas.height * imgRatio;
          this.setup.drawX = (canvas.width - this.setup.drawW) / 2;
          this.setup.drawY = 0;
        }

        this.setup.scale = this.setup.drawW / img.naturalWidth;

        // Clear points when loading new image
        this.setup.currentPoints = [];
        this.setup.allFrames = [];

        // Hide hint, show canvas
        const hint = document.getElementById('setupHint');
        if (hint) hint.style.display = 'none';

        this.redrawCanvas();
        this.updateSetupButtons();
      };
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  },

  /**
   * Load available locations from API
   */
  async loadLocations() {
    try {
      console.log('[MockupGenerator] Loading locations...');
      const response = await API.request('/api/sales/mockup/locations');

      if (response && response.locations) {
        this.locations = response.locations;

        // Update generate mode location select
        const locationSelect = document.getElementById('mockupLocationSelect');
        if (locationSelect) {
          locationSelect.innerHTML = '<option value="">Select a location...</option>' +
            this.locations.map(loc =>
              `<option value="${loc.key}">${loc.name}</option>`
            ).join('');
        }

        // Update setup mode location select
        const setupLocationSelect = document.getElementById('setupLocationSelect');
        if (setupLocationSelect) {
          setupLocationSelect.innerHTML = '<option value="">Select a location...</option>' +
            this.locations.map(loc =>
              `<option value="${loc.key}">${loc.name}</option>`
            ).join('');
        }

        console.log('[MockupGenerator] Loaded', this.locations.length, 'locations');
      }
    } catch (error) {
      console.error('[MockupGenerator] Failed to load locations:', error);
    }
  },

  // ==================== GENERATE MODE METHODS ====================

  /**
   * Handle location selection change
   */
  async onLocationChange() {
    const locationSelect = document.getElementById('mockupLocationSelect');
    const templateGroup = document.getElementById('templateSelectGroup');
    const location = locationSelect?.value;

    if (!location) {
      if (templateGroup) templateGroup.style.display = 'none';
      this.templates = [];
      this.updateGenerateButton();
      return;
    }

    // Show template selection
    if (templateGroup) templateGroup.style.display = 'block';

    // Load templates for this location
    await this.loadTemplates(location);
    this.updateGenerateButton();
  },

  /**
   * Handle filter (time of day / finish) change
   */
  async onFilterChange() {
    const locationSelect = document.getElementById('mockupLocationSelect');
    const location = locationSelect?.value;

    if (location) {
      await this.loadTemplates(location);
    }
    this.updateGenerateButton();
  },

  /**
   * Load templates for a location with current filters
   */
  async loadTemplates(location) {
    const templateSelect = document.getElementById('mockupTemplate');
    const timeOfDay = document.getElementById('mockupTimeOfDay')?.value || 'all';
    const finish = document.getElementById('mockupFinish')?.value || 'all';

    if (!templateSelect) return;

    try {
      console.log('[MockupGenerator] Loading templates for', location);
      const params = new URLSearchParams();
      params.append('time_of_day', timeOfDay || 'all');
      params.append('finish', finish || 'all');

      const response = await API.request(`/api/sales/mockup/templates/${location}?${params}`);

      if (response && response.templates) {
        this.templates = response.templates;
        templateSelect.innerHTML = '<option value="">Random template</option>' +
          this.templates.map(t =>
            `<option value="${t.photo}">${t.photo} (${t.time_of_day}/${t.finish}, ${t.frame_count} frame${t.frame_count > 1 ? 's' : ''})</option>`
          ).join('');
        console.log('[MockupGenerator] Loaded', this.templates.length, 'templates');
      }
    } catch (error) {
      console.error('[MockupGenerator] Failed to load templates:', error);
      templateSelect.innerHTML = '<option value="">No templates available</option>';
    }
  },

  /**
   * Handle file input change
   */
  handleFileSelect(event) {
    const file = event.target.files?.[0];
    if (file) {
      this.handleFile(file);
    }
  },

  /**
   * Handle file (from input or drop)
   */
  handleFile(file) {
    // Validate file type
    const validTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
    if (!validTypes.includes(file.type)) {
      this.showToast('Please upload a valid image file (JPG, PNG, GIF, WEBP)', 'error');
      return;
    }

    // Validate file size (10MB max)
    if (file.size > 10 * 1024 * 1024) {
      this.showToast('File size must be less than 10MB', 'error');
      return;
    }

    this.selectedFile = file;

    // Show preview
    const uploadZone = document.getElementById('mockupUploadZone');
    const filePreview = document.getElementById('mockupFilePreview');
    const previewImg = document.getElementById('mockupPreviewImg');

    if (uploadZone) uploadZone.style.display = 'none';
    if (filePreview) filePreview.style.display = 'block';

    if (previewImg) {
      const reader = new FileReader();
      reader.onload = (e) => {
        previewImg.src = e.target.result;
      };
      reader.readAsDataURL(file);
    }

    // Clear AI prompt when file is selected
    const aiPrompt = document.getElementById('mockupAiPrompt');
    if (aiPrompt) aiPrompt.value = '';

    this.updateGenerateButton();
  },

  /**
   * Clear selected file
   */
  clearFile() {
    this.selectedFile = null;

    const uploadZone = document.getElementById('mockupUploadZone');
    const filePreview = document.getElementById('mockupFilePreview');
    const fileInput = document.getElementById('mockupCreativeUpload');
    const previewImg = document.getElementById('mockupPreviewImg');

    if (uploadZone) uploadZone.style.display = 'flex';
    if (filePreview) filePreview.style.display = 'none';
    if (fileInput) fileInput.value = '';
    if (previewImg) previewImg.src = '';

    this.updateGenerateButton();
  },

  /**
   * Update generate button state
   */
  updateGenerateButton() {
    const generateBtn = document.getElementById('mockupGenerateBtn');
    const locationSelect = document.getElementById('mockupLocationSelect');
    const aiPrompt = document.getElementById('mockupAiPrompt');

    if (!generateBtn) return;

    const hasLocation = locationSelect?.value;
    const hasFile = this.selectedFile !== null;
    const hasPrompt = aiPrompt?.value?.trim().length > 0;

    // Enable if we have location AND (file OR prompt)
    const canGenerate = hasLocation && (hasFile || hasPrompt) && !this.isGenerating;
    generateBtn.disabled = !canGenerate;
  },

  /**
   * Generate the mockup
   */
  async generateMockup() {
    if (this.isGenerating) return;

    const locationSelect = document.getElementById('mockupLocationSelect');
    const timeOfDay = document.getElementById('mockupTimeOfDay')?.value || 'all';
    const finish = document.getElementById('mockupFinish')?.value || 'all';
    const templateSelect = document.getElementById('mockupTemplate');
    const aiPrompt = document.getElementById('mockupAiPrompt');

    const location = locationSelect?.value;
    if (!location) {
      this.showToast('Please select a location', 'error');
      return;
    }

    if (!this.selectedFile && !aiPrompt?.value?.trim()) {
      this.showToast('Please upload a creative or enter an AI prompt', 'error');
      return;
    }

    // Show loading state
    this.isGenerating = true;
    this.showLoading(true);
    this.updateGenerateButton();

    try {
      // Build form data
      const formData = new FormData();
      formData.append('location_key', location);
      formData.append('time_of_day', timeOfDay);
      formData.append('finish', finish);

      if (templateSelect?.value) {
        formData.append('specific_photo', templateSelect.value);
      }

      if (this.selectedFile) {
        formData.append('creative', this.selectedFile);
      } else if (aiPrompt?.value?.trim()) {
        formData.append('ai_prompt', aiPrompt.value.trim());
      }

      console.log('[MockupGenerator] Generating mockup for', location);

      // Make API request
      const token = await API.getAuthToken();
      const response = await fetch('/api/sales/mockup/generate', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'Failed to generate mockup');
      }

      // Get the image blob
      const blob = await response.blob();
      const imageUrl = URL.createObjectURL(blob);

      // Show result
      this.showResult(imageUrl, location, timeOfDay, finish);
      this.showToast('Mockup generated successfully!', 'success');

    } catch (error) {
      console.error('[MockupGenerator] Error generating mockup:', error);
      this.showToast(error.message || 'Failed to generate mockup', 'error');
      this.showLoading(false);
    } finally {
      this.isGenerating = false;
      this.updateGenerateButton();
    }
  },

  /**
   * Show/hide loading state
   */
  showLoading(show) {
    const loading = document.getElementById('mockupLoading');
    const empty = document.getElementById('mockupEmpty');
    const result = document.getElementById('mockupResultDisplay');

    if (show) {
      if (loading) loading.style.display = 'flex';
      if (empty) empty.style.display = 'none';
      if (result) result.style.display = 'none';
    } else {
      if (loading) loading.style.display = 'none';
    }
  },

  /**
   * Show the result
   */
  showResult(imageUrl, location, timeOfDay, finish) {
    const loading = document.getElementById('mockupLoading');
    const empty = document.getElementById('mockupEmpty');
    const result = document.getElementById('mockupResultDisplay');
    const resultImage = document.getElementById('mockupResultImage');
    const downloadBtn = document.getElementById('mockupDownloadBtn');

    if (loading) loading.style.display = 'none';
    if (empty) empty.style.display = 'none';
    if (result) result.style.display = 'flex';

    if (resultImage) {
      resultImage.src = imageUrl;
    }

    if (downloadBtn) {
      downloadBtn.href = imageUrl;
      downloadBtn.download = `mockup_${location}_${timeOfDay}_${finish}.jpg`;
    }
  },

  /**
   * Show toast notification
   */
  showToast(message, type = 'info') {
    // Try to use the global toast function if available
    if (typeof showToast === 'function') {
      showToast(message, type);
      return;
    }

    // Fallback: create a simple toast
    const container = document.getElementById('toastContainer');
    if (!container) {
      console.log(`[Toast] ${type}: ${message}`);
      return;
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    // Remove after 3 seconds
    setTimeout(() => {
      toast.classList.add('fade-out');
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }
};

// Make globally available
window.MockupGenerator = MockupGenerator;

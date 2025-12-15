/**
 * Mockup Generator Module
 * Handles mockup generation with uploaded or AI-generated creatives
 */

const MockupGenerator = {
  // State
  selectedFile: null,
  locations: [],
  templates: [],
  isGenerating: false,
  initialized: false,

  /**
   * Initialize the mockup generator
   */
  init() {
    if (this.initialized) {
      console.log('[MockupGenerator] Already initialized');
      return;
    }

    console.log('[MockupGenerator] Initializing...');

    // Setup event listeners
    this.setupEventListeners();

    // Load locations
    this.loadLocations();

    this.initialized = true;
    console.log('[MockupGenerator] Initialized');
  },

  /**
   * Setup all event listeners
   */
  setupEventListeners() {
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
   * Load available locations from API
   */
  async loadLocations() {
    const locationSelect = document.getElementById('mockupLocationSelect');
    if (!locationSelect) return;

    try {
      console.log('[MockupGenerator] Loading locations...');
      const response = await API.request('/api/sales/mockup/locations');

      if (response && response.locations) {
        this.locations = response.locations;
        locationSelect.innerHTML = '<option value="">Select a location...</option>' +
          this.locations.map(loc =>
            `<option value="${loc.key}">${loc.name}</option>`
          ).join('');
        console.log('[MockupGenerator] Loaded', this.locations.length, 'locations');
      }
    } catch (error) {
      console.error('[MockupGenerator] Failed to load locations:', error);
      // Use fallback
      locationSelect.innerHTML = '<option value="">Failed to load locations</option>';
    }
  },

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

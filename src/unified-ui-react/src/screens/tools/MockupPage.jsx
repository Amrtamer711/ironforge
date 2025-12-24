import React, { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { FormField } from "../../components/ui/form-field";
import { SoftCard } from "../../components/ui/soft-card";
import * as mockupApi from "../../api/mockup";
import { useAuth, hasPermission } from "../../state/auth";
import { cn } from "../../lib/utils";

const TIME_OF_DAY = [
  { value: "all", label: "All (Default)" },
  { value: "day", label: "Day" },
  { value: "night", label: "Night" },
];

const FINISHES = [
  { value: "all", label: "All (Default)" },
  { value: "gold", label: "Gold" },
  { value: "silver", label: "Silver" },
];

const CANVAS_WIDTH = 1200;
const CANVAS_HEIGHT = 800;
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 4;
const ZOOM_STEP = 0.1;
const PAN_THRESHOLD = 4;

const DEFAULT_FRAME_CONFIG = {
  brightness: 100,
  contrast: 100,
  saturation: 100,
  depthMultiplier: 15,
  lightDirection: "top",
  imageBlur: 0,
  edgeBlur: 1,
  overlayOpacity: 0,
  shadowIntensity: 0,
  lightingAdjustment: 0,
  colorTemperature: 0,
  vignette: 0,
  edgeSmoother: 3,
  sharpening: 0,
};

const LIGHT_DIRECTIONS = [
  { value: "top-left", label: "Top Left", glyph: "↖" },
  { value: "top", label: "Top", glyph: "↑" },
  { value: "top-right", label: "Top Right", glyph: "↗" },
  { value: "left", label: "Left", glyph: "←" },
  { value: "center", label: "Center", glyph: "●" },
  { value: "right", label: "Right", glyph: "→" },
  { value: "bottom-left", label: "Bottom Left", glyph: "↙" },
  { value: "bottom", label: "Bottom", glyph: "↓" },
  { value: "bottom-right", label: "Bottom Right", glyph: "↘" },
];

const LIGHT_LABELS = LIGHT_DIRECTIONS.reduce((acc, item) => {
  acc[item.value] = item.label;
  return acc;
}, {});

function normalizeFrameConfig(config) {
  return { ...DEFAULT_FRAME_CONFIG, ...(config || {}) };
}

function getRangeBackground(value, min, max) {
  const percent = ((value - min) / (max - min)) * 100;
  return `linear-gradient(to right, rgb(var(--brand-accent, 102 126 234)) ${percent}%, rgba(0, 0, 0, 0.1) ${percent}%)`;
}

export function MockupPage() {
  const { user } = useAuth();
  const canSetup = hasPermission(user, "sales:mockups:setup");

  const [mode, setMode] = useState("generate");
  const [location, setLocation] = useState("");
  const [timeOfDay, setTimeOfDay] = useState("all");
  const [finish, setFinish] = useState("all");

  const [templateKey, setTemplateKey] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [generateConfigEnabled, setGenerateConfigEnabled] = useState(false);
  const [genFrameConfig, setGenFrameConfig] = useState(DEFAULT_FRAME_CONFIG);

  const [aiPrompt, setAiPrompt] = useState("");
  const [creativeFile, setCreativeFile] = useState(null);
  const [resultUrl, setResultUrl] = useState("");
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState("");

  const [setupPhoto, setSetupPhoto] = useState(null);
  const [setupSaving, setSetupSaving] = useState(false);
  const [setupMessage, setSetupMessage] = useState("");
  const [setupError, setSetupError] = useState("");
  const [framesJson, setFramesJson] = useState("[]");
  const [framesJsonDirty, setFramesJsonDirty] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState(null);
  const [editingTemplateLoading, setEditingTemplateLoading] = useState(false);
  const [setupDragActive, setSetupDragActive] = useState(false);
  const [creativeDragActive, setCreativeDragActive] = useState(false);
  const [setupHint, setSetupHint] = useState(
    "Select a location, upload a billboard photo, then click four corners to define the frame."
  );
  const [setupFrameConfig, setSetupFrameConfig] = useState(DEFAULT_FRAME_CONFIG);
  const [greenscreenColor, setGreenscreenColor] = useState("#1CFF1C");
  const [colorTolerance, setColorTolerance] = useState(40);
  const [currentPoints, setCurrentPoints] = useState([]);
  const [frameCount, setFrameCount] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [pixelUpscale, setPixelUpscale] = useState(false);
  const [activeFrameIndex, setActiveFrameIndex] = useState(-1);
  const [setupImageReady, setSetupImageReady] = useState(false);
  const [templatesOpen, setTemplatesOpen] = useState(true);
  const [greenscreenOpen, setGreenscreenOpen] = useState(true);
  const [frameSettingsOpen, setFrameSettingsOpen] = useState(true);
  const [previewOpen, setPreviewOpen] = useState(true);

  const [testPreviewMode, setTestPreviewMode] = useState(false);
  const [testCreativeFiles, setTestCreativeFiles] = useState({});
  const [testPreviewing, setTestPreviewing] = useState(false);

  const canvasRef = useRef(null);
  const previewImgRef = useRef(null);
  const testPreviewImgRef = useRef(null);
  const testPreviewUrlRef = useRef("");
  const testPreviewCacheRef = useRef(new Map());
  const testCreativeFilesRef = useRef({});
  const greenscreenFrameRef = useRef(false);

  const currentPointsRef = useRef([]);
  const allFramesRef = useRef([]);
  const selectedFrameRef = useRef(-1);
  const viewRef = useRef({ zoom: 1, panX: 0, panY: 0 });
  const dragStateRef = useRef({
    isDrawing: false,
    isDraggingCorner: false,
    isDraggingFrame: false,
    dragFrameIndex: -1,
    dragPointIndex: -1,
    startX: 0,
    startY: 0,
    isPanning: false,
    shiftPanPending: false,
    hasPanned: false,
    panStartX: 0,
    panStartY: 0,
    panOriginX: 0,
    panOriginY: 0,
  });
  const touchStateRef = useRef({
    pointers: new Map(),
    isPinching: false,
    startDistance: 0,
    startZoom: 1,
    startPanX: 0,
    startPanY: 0,
    startCenterX: 0,
    startCenterY: 0,
  });
  const canvasMetricsRef = useRef({
    drawX: 0,
    drawY: 0,
    drawW: 0,
    drawH: 0,
    scale: 1,
    imgNaturalW: 0,
    imgNaturalH: 0,
  });

  const locationsQuery = useQuery({
    queryKey: ["mockup", "locations"],
    queryFn: mockupApi.getLocations,
  });

  const templatesQuery = useQuery({
    queryKey: ["mockup", "templates", location, timeOfDay, finish],
    queryFn: () => mockupApi.getTemplates(location, { timeOfDay, finish }),
    enabled: !!location,
  });

  useEffect(() => {
    return () => {
      if (resultUrl) URL.revokeObjectURL(resultUrl);
      testPreviewCacheRef.current.forEach((entry) => {
        if (entry?.url) URL.revokeObjectURL(entry.url);
      });
      testPreviewCacheRef.current.clear();
      if (testPreviewUrlRef.current) URL.revokeObjectURL(testPreviewUrlRef.current);
    };
  }, [resultUrl]);

  useEffect(() => {
    testCreativeFilesRef.current = testCreativeFiles;
  }, [testCreativeFiles]);

  const locationOptions = useMemo(() => {
    const data = locationsQuery.data;
    if (Array.isArray(data)) return data;
    return data?.locations || [];
  }, [locationsQuery.data]);

  const templateOptions = useMemo(() => {
    const data = templatesQuery.data;
    if (Array.isArray(data)) return data;
    return data?.templates || [];
  }, [templatesQuery.data]);

  const templateMap = useMemo(() => {
    const map = new Map();
    templateOptions.forEach((t) => {
      map.set(getTemplateKey(t), t);
    });
    return map;
  }, [templateOptions]);

  const canGenerate = location && (creativeFile || aiPrompt.trim()) && !generating;
  const canDetectGreenscreen = Boolean(previewImgRef.current);
  const hasActiveFrame = currentPoints.length === 4 || activeFrameIndex >= 0;
  const activeFrameKey =
    activeFrameIndex >= 0 ? `frame-${activeFrameIndex}` : currentPoints.length === 4 ? "current" : null;
  const activeTestCreativeFile = activeFrameKey ? testCreativeFiles[activeFrameKey] : null;
  const zoomPercent = Math.round(zoom * 100);

  useEffect(() => {
    if (!templateKey) {
      setSelectedTemplate(null);
      setGenerateConfigEnabled(false);
      setGenFrameConfig(DEFAULT_FRAME_CONFIG);
      return;
    }

    const template = templateMap.get(templateKey);
    if (!template) {
      setSelectedTemplate(null);
      setGenerateConfigEnabled(false);
      setGenFrameConfig(DEFAULT_FRAME_CONFIG);
      return;
    }

    setSelectedTemplate(template);
    setGenFrameConfig(normalizeFrameConfig(template.config));
  }, [templateKey, templateMap]);

  useEffect(() => {
    if (!activeFrameKey) {
      testPreviewImgRef.current = null;
      testPreviewUrlRef.current = "";
      return;
    }
    const cachedPreview = testPreviewCacheRef.current.get(activeFrameKey);
    testPreviewImgRef.current = cachedPreview?.img || null;
    testPreviewUrlRef.current = cachedPreview?.url || "";
    if (testPreviewMode) {
      drawPreview();
    }
  }, [activeFrameKey, testCreativeFiles, testPreviewMode]);

  useEffect(() => {
    if (previewImgRef.current) updateHintForPhoto();
    drawPreview();
  }, [testPreviewMode]);

  useEffect(() => {
    drawPreview();
  }, [pixelUpscale]);

  useEffect(() => {
    if (setupImageReady && previewImgRef.current) {
      drawPreview();
    }
  }, [setupImageReady]);

  useEffect(() => {
    if (framesJsonDirty) return;
    const payload = buildFramesPayload();
    setFramesJson(payload.length ? JSON.stringify(payload, null, 2) : "[]");
  }, [currentPoints, frameCount, setupFrameConfig, framesJsonDirty]);

  useEffect(() => {
    if (templateKey) setTemplateKey("");
  }, [timeOfDay, finish]);

  async function onGenerate() {
    if (!canGenerate) return;
    setGenerateError("");
    setResultUrl("");

    try {
      setGenerating(true);
      const formData = new FormData();
      formData.append("location_key", location);

      if (selectedTemplate) {
        formData.append("time_of_day", selectedTemplate.time_of_day || timeOfDay || "all");
        formData.append("finish", selectedTemplate.finish || finish || "all");
        formData.append("specific_photo", selectedTemplate.photo);
        formData.append("frame_config", JSON.stringify(genFrameConfig));
      } else {
        formData.append("time_of_day", timeOfDay || "all");
        formData.append("finish", finish || "all");
      }

      if (aiPrompt.trim()) {
        formData.append("ai_prompt", aiPrompt.trim());
      } else if (creativeFile) {
        formData.append("creative", creativeFile);
      }

      const blob = await mockupApi.generateMockup(formData);
      const url = URL.createObjectURL(blob);
      if (resultUrl) URL.revokeObjectURL(resultUrl);
      setResultUrl(url);
    } catch (err) {
      setGenerateError(err?.message || "Failed to generate mockup");
    } finally {
      setGenerating(false);
    }
  }

  async function saveSetup() {
    setSetupMessage("");
    setSetupError("");

    if (!location) {
      setSetupError("Select a location first");
      return;
    }

    if (!setupPhoto) {
      setSetupError("Upload a billboard photo first");
      return;
    }

    let framesPayload = buildFramesPayload();
    if (framesJson.trim()) {
      try {
        framesPayload = JSON.parse(framesJson);
      } catch (err) {
        setSetupError(err?.message || "Frames JSON is invalid");
        return;
      }
    }

    if (!Array.isArray(framesPayload) || !framesPayload.length) {
      setSetupError("Add at least one frame before saving");
      return;
    }

    try {
      setSetupSaving(true);
      const formData = new FormData();
      formData.append("location_key", location);
      formData.append("time_of_day", timeOfDay || "all");
      formData.append("finish", finish || "all");
      formData.append("frames", JSON.stringify(framesPayload));
      formData.append("photo", setupPhoto);

      await mockupApi.saveSetupPhoto(formData);
      setSetupMessage("Saved frames successfully");
      clearAllFrames(true);
      setEditingTemplate(null);
      setEditingTemplateLoading(false);
      setSetupPhoto(null);
      previewImgRef.current = null;
      setSetupImageReady(false);
      templatesQuery.refetch();
      drawPreview();
    } catch (err) {
      setSetupError(err?.message || "Failed to save template");
    } finally {
      setSetupSaving(false);
    }
  }

  async function deleteTemplate(photo) {
    if (!location) return;
    try {
      await mockupApi.deleteSetupPhoto(location, photo);
      templatesQuery.refetch();
    } catch (err) {
      setSetupError(err?.message || "Failed to delete template");
    }
  }

  function applyImageToCanvas(img, { resetFrames = true } = {}) {
    previewImgRef.current = img;
    setSetupImageReady(true);
    const fit = fitImageIntoCanvas(img.naturalWidth, img.naturalHeight);
    canvasMetricsRef.current = {
      drawX: fit.x,
      drawY: fit.y,
      drawW: fit.w,
      drawH: fit.h,
      scale: fit.scale,
      imgNaturalW: img.naturalWidth,
      imgNaturalH: img.naturalHeight,
    };
    resetView(false);
    if (resetFrames) {
      currentPointsRef.current = [];
      allFramesRef.current = [];
      clearActiveSelection();
      greenscreenFrameRef.current = false;
      resetSetupConfig();
      clearTestPreviewState();
      syncCurrentPoints();
      syncFrameCount();
      setFramesJson("[]");
      setFramesJsonDirty(false);
    }
    updateHintForPhoto();
    drawPreview();
  }

  function loadImageFromUrl(url, options) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        applyImageToCanvas(img, options);
        resolve();
      };
      img.onerror = () => reject(new Error("Failed to load image"));
      img.src = url;
    });
  }

  function loadImageFromFile(file, options) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (event) => {
        const img = new Image();
        img.onload = () => {
          applyImageToCanvas(img, options);
          resolve();
        };
        img.onerror = () => reject(new Error("Failed to load image"));
        img.src = event.target.result;
      };
      reader.onerror = () => reject(new Error("Failed to read image"));
      reader.readAsDataURL(file);
    });
  }

  function normalizeFramePoints(points) {
    if (!points) return null;
    if (Array.isArray(points) && points.length === 4 && Array.isArray(points[0])) {
      return points;
    }
    if (Array.isArray(points) && points.length >= 8 && typeof points[0] === "number") {
      return [
        [points[0], points[1]],
        [points[2], points[3]],
        [points[4], points[5]],
        [points[6], points[7]],
      ];
    }
    return null;
  }

  function extractFramesFromTemplate(template) {
    if (!template) return [];
    // Changedis
    let raw = template.frames || template.frames_data || template.framesData || template.frame_data || template.frame_points;
    if (typeof raw === "string") {
      try {
        raw = JSON.parse(raw);
      } catch {
        raw = [];
      }
    }
    if (!Array.isArray(raw)) return [];

    return raw
      .map((frame) => {
        const points =
          normalizeFramePoints(frame?.points || frame?.frame_points || frame) || normalizeFramePoints(frame?.points);
        if (!points) return null;
        let rawConfig = frame?.config || template?.config;
        if (typeof rawConfig === "string") {
          try {
            rawConfig = JSON.parse(rawConfig);
          } catch {
            rawConfig = null;
          }
        }
        const config = normalizeFrameConfig(rawConfig);
        return { points, config, source: "existing" };
      })
      .filter(Boolean);
  }

  async function startEditTemplate(template) {
    if (!location || !template?.photo) return;
    setEditingTemplate(template);
    setEditingTemplateLoading(true);
    setSetupError("");
    setSetupMessage("");
    setSetupPhoto(null);

    try {
      if (template.time_of_day) setTimeOfDay(template.time_of_day);
      if (template.finish) setFinish(template.finish);

      const photoUrl = mockupApi.getTemplatePhotoUrl(location, template.photo);
      await loadImageFromUrl(photoUrl, { resetFrames: false });

      const frames = extractFramesFromTemplate(template);
      allFramesRef.current = frames;
      currentPointsRef.current = [];
      clearActiveSelection();
      greenscreenFrameRef.current = false;
      syncCurrentPoints();
      syncFrameCount();
      setFramesJson(frames.length ? JSON.stringify(buildFramesPayload(), null, 2) : "[]");
      setFramesJsonDirty(false);
      drawPreview();

      const response = await fetch(photoUrl);
      const blob = await response.blob();
      const file = new File([blob], template.photo, { type: blob.type || "image/jpeg" });
      setSetupPhoto(file);
    } catch (err) {
      setSetupError(err?.message || "Failed to load template for editing");
    } finally {
      setEditingTemplateLoading(false);
    }
  }

  function stopEditTemplate() {
    setEditingTemplate(null);
    setEditingTemplateLoading(false);
    setSetupMessage("");
    setSetupError("");
    currentPointsRef.current = [];
    allFramesRef.current = [];
    clearActiveSelection();
    greenscreenFrameRef.current = false;
    syncCurrentPoints();
    syncFrameCount();
    setFramesJson("[]");
    setFramesJsonDirty(false);
    updateHintForPhoto();
    drawPreview();
  }

  function getCanvasPoint(event) {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    return {
      x: (event.clientX - rect.left) * scaleX,
      y: (event.clientY - rect.top) * scaleY,
    };
  }

  function clampZoom(value) {
    return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value));
  }

  function getViewMetrics() {
    const { drawX, drawY, drawW, drawH, scale } = canvasMetricsRef.current;
    const { zoom: currentZoom, panX, panY } = viewRef.current;
    return {
      drawX: drawX + panX,
      drawY: drawY + panY,
      drawW: drawW * currentZoom,
      drawH: drawH * currentZoom,
      scale: scale * currentZoom,
    };
  }

  function resetView(shouldDraw = true) {
    viewRef.current = { zoom: 1, panX: 0, panY: 0 };
    setZoom(1);
    if (shouldDraw) drawPreview();
  }

  function getCanvasCenter() {
    const canvas = canvasRef.current;
    if (!canvas) return { x: CANVAS_WIDTH / 2, y: CANVAS_HEIGHT / 2 };
    return { x: canvas.width / 2, y: canvas.height / 2 };
  }

  function setZoomAtPoint(nextZoom, anchorX, anchorY) {
    const { drawX, drawY, scale } = canvasMetricsRef.current;
    const { zoom: currentZoom, panX, panY } = viewRef.current;
    const clamped = clampZoom(nextZoom);
    const currentScale = scale * currentZoom;
    const targetScale = scale * clamped;

    if (!currentScale || !targetScale) return;

    const imgX = (anchorX - (drawX + panX)) / currentScale;
    const imgY = (anchorY - (drawY + panY)) / currentScale;
    const nextPanX = anchorX - drawX - imgX * targetScale;
    const nextPanY = anchorY - drawY - imgY * targetScale;

    viewRef.current = { zoom: clamped, panX: nextPanX, panY: nextPanY };
    setZoom(clamped);
    drawPreview();
  }

  function pickGreenscreenColor(x, y) {
    if (!previewImgRef.current) return;
    const { drawX, drawY, drawW, drawH, scale } = getViewMetrics();
    if (x < drawX || y < drawY || x > drawX + drawW || y > drawY + drawH) return;
    const ix = Math.floor((x - drawX) / scale);
    const iy = Math.floor((y - drawY) / scale);
    const tempCanvas = document.createElement("canvas");
    tempCanvas.width = previewImgRef.current.naturalWidth;
    tempCanvas.height = previewImgRef.current.naturalHeight;
    const tempCtx = tempCanvas.getContext("2d");
    tempCtx.drawImage(previewImgRef.current, 0, 0);
    const imageData = tempCtx.getImageData(ix, iy, 1, 1);
    const [r, g, b] = imageData.data;
    const hex = `#${[r, g, b]
      .map((val) => val.toString(16).padStart(2, "0"))
      .join("")
      .toUpperCase()}`;
    setGreenscreenColor(hex);
  }

  function handleCanvasWheel(event) {
    // Mouse wheel zoom disabled for now.
    void event;
    /*
    if (!previewImgRef.current) return;
    event.preventDefault();
    const canvasPoint = getCanvasPoint(event);
    if (!canvasPoint) return;
    const step = event.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP;
    setZoomAtPoint(viewRef.current.zoom + step, canvasPoint.x, canvasPoint.y);
    */
  }

  function handleZoomIn() {
    if (!previewImgRef.current) return;
    const center = getCanvasCenter();
    setZoomAtPoint(viewRef.current.zoom + ZOOM_STEP, center.x, center.y);
  }

  function handleZoomOut() {
    if (!previewImgRef.current) return;
    const center = getCanvasCenter();
    setZoomAtPoint(viewRef.current.zoom - ZOOM_STEP, center.x, center.y);
  }

  function handleFitToScreen() {
    if (!previewImgRef.current) return;
    resetView();
  }

  function fitImageIntoCanvas(imgW, imgH) {
    const scale = Math.min(CANVAS_WIDTH / imgW, CANVAS_HEIGHT / imgH);
    const w = Math.round(imgW * scale);
    const h = Math.round(imgH * scale);
    const x = Math.round((CANVAS_WIDTH - w) / 2);
    const y = Math.round((CANVAS_HEIGHT - h) / 2);
    return { x, y, w, h, scale };
  }

  function clearCanvas() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#f8f9fa";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }

  function drawPreview() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    clearCanvas();

    const previewImg = previewImgRef.current;
    if (!previewImg) return;

    const { drawX, drawY, drawW, drawH, scale } = getViewMetrics();
    ctx.imageSmoothingEnabled = !pixelUpscale;
    if (!pixelUpscale) {
      ctx.imageSmoothingQuality = "high";
    }

    if (testPreviewMode && testPreviewImgRef.current) {
      ctx.drawImage(testPreviewImgRef.current, drawX, drawY, drawW, drawH);
      return;
    }

    ctx.drawImage(previewImg, drawX, drawY, drawW, drawH);

    const frames = allFramesRef.current;
    frames.forEach((frame, frameIndex) => {
      const framePoints = frame.points;
      const isSelected = selectedFrameRef.current === frameIndex;
      const baseWidth = 1;

      ctx.fillStyle = "rgba(128, 128, 128, 0.3)";
      ctx.strokeStyle = isSelected ? "#667eea" : "#333";
      ctx.lineWidth = baseWidth;
      ctx.setLineDash([8, 4]);
      ctx.lineCap = "butt";
      ctx.lineJoin = "miter";

      ctx.beginPath();
      framePoints.forEach((pt, index) => {
        const cx = drawX + pt[0] * scale;
        const cy = drawY + pt[1] * scale;
        if (index === 0) ctx.moveTo(cx, cy);
        else ctx.lineTo(cx, cy);
      });
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
      ctx.setLineDash([]);

      framePoints.forEach((pt) => {
        const cx = drawX + pt[0] * scale;
        const cy = drawY + pt[1] * scale;
        const markerSize = 4;
        ctx.fillStyle = isSelected ? "#667eea" : "#333";
        ctx.fillRect(cx - markerSize / 2, cy - markerSize / 2, markerSize, markerSize);
      });
    });

    const activePoints = currentPointsRef.current;
    if (activePoints.length > 0) {
      const activeMarkerSize = 4;
      ctx.fillStyle = "rgba(128, 128, 128, 0.3)";
      ctx.strokeStyle = "#667eea";
      ctx.lineWidth = 1;
      ctx.setLineDash([8, 4]);
      ctx.lineCap = "butt";
      ctx.lineJoin = "miter";

      ctx.beginPath();
      activePoints.forEach((pt, index) => {
        const cx = drawX + pt[0] * scale;
        const cy = drawY + pt[1] * scale;
        if (index === 0) ctx.moveTo(cx, cy);
        else ctx.lineTo(cx, cy);
      });
      if (activePoints.length === 4) {
        ctx.closePath();
        ctx.fill();
      }
      ctx.stroke();
      ctx.setLineDash([]);

      activePoints.forEach((pt) => {
        const cx = drawX + pt[0] * scale;
        const cy = drawY + pt[1] * scale;
        ctx.fillStyle = "#667eea";
        ctx.fillRect(cx - activeMarkerSize / 2, cy - activeMarkerSize / 2, activeMarkerSize, activeMarkerSize);
      });
    }
  }

  function syncCurrentPoints() {
    setCurrentPoints([...currentPointsRef.current]);
  }

  function syncFrameCount() {
    setFrameCount(allFramesRef.current.length);
  }

  function clearActiveSelection() {
    selectedFrameRef.current = -1;
    setActiveFrameIndex(-1);
  }

  function getActiveFrameData() {
    if (activeFrameIndex >= 0) {
      const frame = allFramesRef.current[activeFrameIndex];
      if (!frame) return null;
      return {
        key: `frame-${activeFrameIndex}`,
        points: frame.points,
        config: frame.config,
      };
    }
    if (currentPointsRef.current.length === 4) {
      return {
        key: "current",
        points: currentPointsRef.current,
        config: setupFrameConfig,
      };
    }
    return null;
  }

  function revokeTestPreviewUrls() {
    testPreviewCacheRef.current.forEach((entry) => {
      if (entry?.url) URL.revokeObjectURL(entry.url);
    });
    testPreviewCacheRef.current.clear();
    if (testPreviewUrlRef.current) URL.revokeObjectURL(testPreviewUrlRef.current);
    testPreviewUrlRef.current = "";
    testPreviewImgRef.current = null;
  }

  function clearTestPreviewState() {
    revokeTestPreviewUrls();
    setTestPreviewMode(false);
    setTestCreativeFiles({});
  }

  function updateTestCreativeForActive(file) {
    if (!activeFrameKey) return;
    setTestCreativeFiles((prev) => {
      const next = { ...prev };
      if (file) {
        next[activeFrameKey] = file;
      } else {
        delete next[activeFrameKey];
      }
      return next;
    });
  }

  function selectExistingFrame(index) {
    currentPointsRef.current = [];
    syncCurrentPoints();
    selectedFrameRef.current = index;
    setActiveFrameIndex(index);
    const frame = allFramesRef.current[index];
    if (frame?.config) {
      setSetupFrameConfig(normalizeFrameConfig(frame.config));
    }
    setFrameSettingsOpen(true);
    setFramesJsonDirty(false);
    const payload = buildFramesPayload();
    setFramesJson(payload.length ? JSON.stringify(payload, null, 2) : "[]");
  }

  function handleSetupFrameConfigChange(key, value) {
    setSetupFrameConfig((prev) => {
      const next = { ...prev, [key]: value };
      const selectedIndex = selectedFrameRef.current;
      if (selectedIndex >= 0 && allFramesRef.current[selectedIndex]) {
        allFramesRef.current[selectedIndex].config = next;
      }
      return next;
    });
  }

  function isPointInFrame(x, y, framePoints) {
    const { drawX, drawY, scale } = getViewMetrics();
    const imgX = (x - drawX) / scale;
    const imgY = (y - drawY) / scale;
    let inside = false;
    for (let i = 0, j = framePoints.length - 1; i < framePoints.length; j = i++) {
      const xi = framePoints[i][0];
      const yi = framePoints[i][1];
      const xj = framePoints[j][0];
      const yj = framePoints[j][1];
      const intersect = (yi > imgY) !== (yj > imgY) && imgX < ((xj - xi) * (imgY - yi)) / (yj - yi) + xi;
      if (intersect) inside = !inside;
    }
    return inside;
  }

  function getHoveredFrame(x, y) {
    if (currentPointsRef.current.length === 4 && isPointInFrame(x, y, currentPointsRef.current)) {
      return -1;
    }
    for (let fi = allFramesRef.current.length - 1; fi >= 0; fi -= 1) {
      if (isPointInFrame(x, y, allFramesRef.current[fi].points)) {
        return fi;
      }
    }
    return null;
  }

  function getClickedCorner(x, y) {
    const hitRadius = 15;
    const { drawX, drawY, scale } = getViewMetrics();

    if (currentPointsRef.current.length > 0) {
      for (let i = 0; i < currentPointsRef.current.length; i += 1) {
        const cx = drawX + currentPointsRef.current[i][0] * scale;
        const cy = drawY + currentPointsRef.current[i][1] * scale;
        const dist = Math.hypot(x - cx, y - cy);
        if (dist < hitRadius) return { frame: -1, point: i };
      }
    }

    for (let fi = 0; fi < allFramesRef.current.length; fi += 1) {
      const framePoints = allFramesRef.current[fi].points;
      for (let pi = 0; pi < framePoints.length; pi += 1) {
        const cx = drawX + framePoints[pi][0] * scale;
        const cy = drawY + framePoints[pi][1] * scale;
        const dist = Math.hypot(x - cx, y - cy);
        if (dist < hitRadius) return { frame: fi, point: pi };
      }
    }

    return null;
  }

  function updateHintForPhoto() {
    if (!previewImgRef.current) {
      setSetupHint("Select a location, upload a billboard photo, then click four corners to define the frame.");
      return;
    }
    setSetupHint("Click and drag to draw a box. Use +/Fit to zoom; Shift+drag or middle mouse pans; pinch to zoom.");
  }

  function handleSetupPhoto(file) {
    if (!file) return;
    loadImageFromFile(file, { resetFrames: true }).catch((err) => {
      setSetupError(err?.message || "Failed to load image");
    });
  }

  function handleCanvasPointerDown(event) {
    if (mode !== "setup" || !previewImgRef.current) return;
    const canvasPoint = getCanvasPoint(event);
    if (!canvasPoint) return;

    const { x, y } = canvasPoint;
    const dragState = dragStateRef.current;

    if (event.pointerType === "touch") {
      const touchState = touchStateRef.current;
      touchState.pointers.set(event.pointerId, { x, y });
      if (touchState.pointers.size === 2) {
        const [p1, p2] = Array.from(touchState.pointers.values());
        const centerX = (p1.x + p2.x) / 2;
        const centerY = (p1.y + p2.y) / 2;
        touchState.isPinching = true;
        touchState.startDistance = Math.hypot(p1.x - p2.x, p1.y - p2.y);
        touchState.startZoom = viewRef.current.zoom;
        touchState.startPanX = viewRef.current.panX;
        touchState.startPanY = viewRef.current.panY;
        touchState.startCenterX = centerX;
        touchState.startCenterY = centerY;
        dragState.isDrawing = false;
        dragState.isDraggingCorner = false;
        dragState.isDraggingFrame = false;
        dragState.isPanning = false;
        if (canvasRef.current) canvasRef.current.style.cursor = "grabbing";
        return;
      }
    }

    const isMiddleButton = event.button === 1;
    if (isMiddleButton || event.shiftKey) {
      event.preventDefault();
      dragState.isPanning = true;
      dragState.shiftPanPending = event.shiftKey && event.button === 0;
      dragState.hasPanned = false;
      dragState.panStartX = x;
      dragState.panStartY = y;
      dragState.panOriginX = viewRef.current.panX;
      dragState.panOriginY = viewRef.current.panY;
      if (canvasRef.current) canvasRef.current.style.cursor = "grabbing";
      return;
    }

    dragState.shiftPanPending = false;
    dragState.hasPanned = false;

    const { drawX, drawY, drawW, drawH } = getViewMetrics();

    const corner = getClickedCorner(x, y);
    if (corner) {
      dragStateRef.current.isDraggingCorner = true;
      dragStateRef.current.dragFrameIndex = corner.frame;
      dragStateRef.current.dragPointIndex = corner.point;
      if (corner.frame >= 0) {
        selectExistingFrame(corner.frame);
      } else {
        clearActiveSelection();
        setFrameSettingsOpen(true);
      }
      drawPreview();
      return;
    }

    const hoveredFrame = getHoveredFrame(x, y);
    if (hoveredFrame !== null) {
      dragStateRef.current.isDraggingFrame = true;
      dragStateRef.current.dragFrameIndex = hoveredFrame;
      dragStateRef.current.startX = x;
      dragStateRef.current.startY = y;
      if (hoveredFrame >= 0) {
        selectExistingFrame(hoveredFrame);
      } else {
        clearActiveSelection();
        setFrameSettingsOpen(true);
      }
      if (canvasRef.current) canvasRef.current.style.cursor = "move";
      drawPreview();
      return;
    }

    if (x < drawX || y < drawY || x > drawX + drawW || y > drawY + drawH) return;

    greenscreenFrameRef.current = false;
    dragStateRef.current.isDrawing = true;
    dragStateRef.current.startX = x;
    dragStateRef.current.startY = y;
    clearActiveSelection();
  }

  function handleCanvasPointerMove(event) {
    if (mode !== "setup" || !previewImgRef.current) return;
    const canvasPoint = getCanvasPoint(event);
    if (!canvasPoint) return;

    const { x, y } = canvasPoint;
    const dragState = dragStateRef.current;

    if (event.pointerType === "touch") {
      const touchState = touchStateRef.current;
      if (touchState.pointers.has(event.pointerId)) {
        touchState.pointers.set(event.pointerId, { x, y });
      }
      if (touchState.isPinching && touchState.pointers.size >= 2) {
        const [p1, p2] = Array.from(touchState.pointers.values());
        const centerX = (p1.x + p2.x) / 2;
        const centerY = (p1.y + p2.y) / 2;
        const dist = Math.hypot(p1.x - p2.x, p1.y - p2.y);
        const { drawX, drawY, scale } = canvasMetricsRef.current;
        const startZoom = touchState.startZoom;
        if (touchState.startDistance > 0 && scale) {
          const nextZoom = clampZoom(startZoom * (dist / touchState.startDistance));
          const anchorImgX =
            (touchState.startCenterX - (drawX + touchState.startPanX)) / (scale * startZoom);
          const anchorImgY =
            (touchState.startCenterY - (drawY + touchState.startPanY)) / (scale * startZoom);
          const nextPanX = centerX - drawX - anchorImgX * scale * nextZoom;
          const nextPanY = centerY - drawY - anchorImgY * scale * nextZoom;
          viewRef.current = { zoom: nextZoom, panX: nextPanX, panY: nextPanY };
          setZoom(nextZoom);
          drawPreview();
        }
        return;
      }
    }

    if (dragState.isPanning) {
      event.preventDefault();
      const deltaX = x - dragState.panStartX;
      const deltaY = y - dragState.panStartY;
      if (dragState.shiftPanPending && !dragState.hasPanned) {
        if (Math.hypot(deltaX, deltaY) < PAN_THRESHOLD) return;
        dragState.hasPanned = true;
      }
      viewRef.current.panX = dragState.panOriginX + deltaX;
      viewRef.current.panY = dragState.panOriginY + deltaY;
      drawPreview();
      return;
    }

    const { drawX, drawY, scale } = getViewMetrics();

    if (dragState.isDraggingCorner) {
      const ix = (x - drawX) / scale;
      const iy = (y - drawY) / scale;
      if (dragState.dragFrameIndex === -1) {
        currentPointsRef.current[dragState.dragPointIndex] = [Math.round(ix), Math.round(iy)];
      } else {
        allFramesRef.current[dragState.dragFrameIndex].points[dragState.dragPointIndex] = [
          Math.round(ix),
          Math.round(iy),
        ];
      }
      drawPreview();
      return;
    }

    if (dragState.isDraggingFrame) {
      const deltaX = (x - dragState.startX) / scale;
      const deltaY = (y - dragState.startY) / scale;

      if (dragState.dragFrameIndex === -1) {
        currentPointsRef.current = currentPointsRef.current.map((pt) => [
          Math.round(pt[0] + deltaX),
          Math.round(pt[1] + deltaY),
        ]);
      } else {
        allFramesRef.current[dragState.dragFrameIndex].points =
          allFramesRef.current[dragState.dragFrameIndex].points.map((pt) => [
            Math.round(pt[0] + deltaX),
            Math.round(pt[1] + deltaY),
          ]);
      }

      dragState.startX = x;
      dragState.startY = y;
      drawPreview();
      return;
    }

    if (dragState.isDrawing) {
      drawPreview();
      const ctx = canvasRef.current.getContext("2d");
      ctx.fillStyle = "rgba(128, 128, 128, 0.3)";
      const width = x - dragState.startX;
      const height = y - dragState.startY;
      ctx.fillRect(dragState.startX, dragState.startY, width, height);
      ctx.strokeStyle = "#667eea";
      ctx.lineWidth = 1;
      ctx.setLineDash([8, 4]);
      ctx.lineCap = "butt";
      ctx.lineJoin = "miter";
      ctx.strokeRect(dragState.startX, dragState.startY, width, height);
      ctx.setLineDash([]);
      return;
    }

    const hoveredCorner = getClickedCorner(x, y);
    const hoveredFrame = getHoveredFrame(x, y);
    if (canvasRef.current) {
      if (hoveredCorner) {
        canvasRef.current.style.cursor = "pointer";
      } else if (hoveredFrame !== null) {
        canvasRef.current.style.cursor = "move";
      } else {
        canvasRef.current.style.cursor = "crosshair";
      }
    }
  }

  function handleCanvasPointerUp(event) {
    if (mode !== "setup" || !previewImgRef.current) return;
    const canvasPoint = getCanvasPoint(event);
    const dragState = dragStateRef.current;

    if (event.pointerType === "touch") {
      const touchState = touchStateRef.current;
      if (touchState.pointers.has(event.pointerId)) {
        touchState.pointers.delete(event.pointerId);
      }
      if (touchState.isPinching && touchState.pointers.size < 2) {
        touchState.isPinching = false;
      }
      if (touchState.isPinching) return;
    }

    if (dragState.isPanning) {
      dragState.isPanning = false;
      if (canvasRef.current) canvasRef.current.style.cursor = "crosshair";
      if (dragState.shiftPanPending && !dragState.hasPanned && greenscreenOpen && canvasPoint) {
        pickGreenscreenColor(canvasPoint.x, canvasPoint.y);
      }
      dragState.shiftPanPending = false;
      dragState.hasPanned = false;
      return;
    }

    if (dragState.isDraggingCorner) {
      dragState.isDraggingCorner = false;
      dragState.dragFrameIndex = -1;
      dragState.dragPointIndex = -1;
      if (canvasRef.current) canvasRef.current.style.cursor = "crosshair";
      syncCurrentPoints();
      drawPreview();
      return;
    }

    if (dragState.isDraggingFrame) {
      dragState.isDraggingFrame = false;
      dragState.dragFrameIndex = -1;
      if (canvasRef.current) canvasRef.current.style.cursor = "crosshair";
      syncCurrentPoints();
      drawPreview();
      return;
    }

    if (!dragState.isDrawing || !canvasPoint) return;

    const { x, y } = canvasPoint;
    const { drawX, drawY, scale } = getViewMetrics();
    const startX = dragState.startX;
    const startY = dragState.startY;

    const topLeftX = (Math.min(startX, x) - drawX) / scale;
    const topLeftY = (Math.min(startY, y) - drawY) / scale;
    const bottomRightX = (Math.max(startX, x) - drawX) / scale;
    const bottomRightY = (Math.max(startY, y) - drawY) / scale;

    currentPointsRef.current = [
      [Math.round(topLeftX), Math.round(topLeftY)],
      [Math.round(bottomRightX), Math.round(topLeftY)],
      [Math.round(bottomRightX), Math.round(bottomRightY)],
      [Math.round(topLeftX), Math.round(bottomRightY)],
    ];
    dragState.isDrawing = false;

    syncCurrentPoints();
    clearActiveSelection();
    setFrameSettingsOpen(true);
    setSetupHint("Frame drawn. Drag corners to adjust, or drag inside to move. Click Add Frame to save.");
    drawPreview();
  }

  function resetSetupConfig() {
    setSetupFrameConfig(DEFAULT_FRAME_CONFIG);
  }

  function addFrame() {
    if (currentPointsRef.current.length !== 4) {
      setSetupError("Select 4 corner points first");
      return;
    }

    const frameConfig = { ...setupFrameConfig };
    const source = greenscreenFrameRef.current ? "greenscreen" : "manual";
    allFramesRef.current.push({
      points: [...currentPointsRef.current],
      config: frameConfig,
      source,
    });

    const currentKey = "current";
    currentPointsRef.current = [];
    const newIndex = allFramesRef.current.length - 1;
    selectExistingFrame(newIndex);
    greenscreenFrameRef.current = false;
    syncCurrentPoints();
    syncFrameCount();
    setSetupHint(`Frame ${allFramesRef.current.length} added. Draw another box or save when done.`);
    const movedPreview = testPreviewCacheRef.current.get(currentKey);
    if (movedPreview) {
      testPreviewCacheRef.current.set(`frame-${newIndex}`, movedPreview);
      testPreviewCacheRef.current.delete(currentKey);
    }
    const currentFile = testCreativeFilesRef.current[currentKey];
    if (currentFile) {
      setTestCreativeFiles((prev) => {
        const next = { ...prev };
        next[`frame-${newIndex}`] = currentFile;
        delete next[currentKey];
        return next;
      });
    }
    setTestPreviewMode(false);
    testPreviewImgRef.current = null;
    drawPreview();
  }

  function resetCurrentFrame() {
    currentPointsRef.current = [];
    clearActiveSelection();
    greenscreenFrameRef.current = false;
    syncCurrentPoints();
    testPreviewCacheRef.current.delete("current");
    setTestCreativeFiles((prev) => {
      if (!prev.current) return prev;
      const next = { ...prev };
      delete next.current;
      return next;
    });
    setTestPreviewMode(false);
    testPreviewImgRef.current = null;
    if (allFramesRef.current.length) {
      setSetupHint(`Frames saved: ${allFramesRef.current.length}. Draw another box or save all frames.`);
    } else {
      updateHintForPhoto();
    }
    drawPreview();
  }

  function clearAllFrames(skipConfirm = false) {
    if (!skipConfirm && !window.confirm("Clear all frames? This will reset your work.")) return;
    allFramesRef.current = [];
    currentPointsRef.current = [];
    clearActiveSelection();
    greenscreenFrameRef.current = false;
    clearTestPreviewState();
    syncCurrentPoints();
    syncFrameCount();
    setFramesJson("[]");
    setFramesJsonDirty(false);
    updateHintForPhoto();
    drawPreview();
  }

  function buildFramesPayload() {
    const frames = [...allFramesRef.current];
    if (currentPointsRef.current.length === 4) {
      frames.push({
        points: [...currentPointsRef.current],
        config: { ...setupFrameConfig },
      });
    }
    return frames.map((frame) => ({
      points: frame.points.flatMap((pt) => [pt[0], pt[1]]),
      config: frame.config,
    }));
  }

  function parseFramesJson(value) {
    if (!value.trim()) return [];
    let data = [];
    try {
      data = JSON.parse(value);
    } catch (err) {
      throw new Error(err?.message || "Frames JSON is invalid");
    }
    if (!Array.isArray(data)) {
      throw new Error("Frames JSON must be an array of frames.");
    }

    return data.map((frame, index) => {
      const points = normalizeFramePoints(frame?.points || frame?.frame_points || frame);
      if (!points || points.length !== 4) {
        throw new Error(`Frame ${index + 1} must include 4 points.`);
      }
      const normalizedPoints = points.map((pt) => {
        const x = Number(pt[0]);
        const y = Number(pt[1]);
        if (!Number.isFinite(x) || !Number.isFinite(y)) {
          throw new Error(`Frame ${index + 1} has invalid point values.`);
        }
        return [x, y];
      });
      let config = frame?.config;
      if (typeof config === "string") {
        try {
          config = JSON.parse(config);
        } catch {
          config = null;
        }
      }
      return {
        points: normalizedPoints,
        config: normalizeFrameConfig(config),
        source: "json",
      };
    });
  }

  function applyFramesJsonToCanvas() {
    setSetupError("");
    try {
      const frames = parseFramesJson(framesJson);
      allFramesRef.current = frames;
      currentPointsRef.current = [];
      greenscreenFrameRef.current = false;
      clearTestPreviewState();
      if (frames.length) {
        selectExistingFrame(0);
      } else {
        clearActiveSelection();
      }
      syncCurrentPoints();
      syncFrameCount();
      setFramesJsonDirty(false);
      setFramesJson(frames.length ? JSON.stringify(buildFramesPayload(), null, 2) : "[]");
      drawPreview();
    } catch (err) {
      setSetupError(err?.message || "Frames JSON is invalid");
    }
  }

  function handleGreenscreenDetect() {
    if (!previewImgRef.current) return;

    const tempCanvas = document.createElement("canvas");
    tempCanvas.width = previewImgRef.current.width;
    tempCanvas.height = previewImgRef.current.height;
    const tempCtx = tempCanvas.getContext("2d");
    tempCtx.drawImage(previewImgRef.current, 0, 0);
    const imageData = tempCtx.getImageData(0, 0, previewImgRef.current.width, previewImgRef.current.height);

    const detected = detectGreenScreen(imageData, {
      color: greenscreenColor,
      tolerance: colorTolerance,
      depthMultiplier: setupFrameConfig.depthMultiplier,
      existingFrames: allFramesRef.current,
    });

    if (detected) {
      currentPointsRef.current = detected;
      clearActiveSelection();
      greenscreenFrameRef.current = true;
      syncCurrentPoints();
      setFrameSettingsOpen(true);
      setSetupHint("Green screen detected. Adjust points or click Add Frame to save.");
      drawPreview();
    } else {
      setSetupHint("No green screen detected. Adjust tolerance or draw frame manually.");
    }
  }

  async function generateTestPreview() {
    const activeFrame = getActiveFrameData();
    if (!setupPhoto || !activeFrame || !activeFrameKey) {
      setSetupError("Upload a photo and select or draw a frame first.");
      return;
    }
    const creativeFile = activeTestCreativeFile;
    if (!creativeFile) {
      setSetupError("Upload a test creative for the active frame first.");
      return;
    }

    if (testPreviewing) return;
    setSetupError("");
    setTestPreviewing(true);

    try {
      const formData = new FormData();
      formData.append("billboard_photo", setupPhoto);
      formData.append("creative", creativeFile);
      formData.append("frame_points", JSON.stringify(activeFrame.points));
      formData.append("config", JSON.stringify(activeFrame.config));
      formData.append("time_of_day", timeOfDay || "day");

      const blob = await mockupApi.testPreview(formData);
      const existing = testPreviewCacheRef.current.get(activeFrameKey);
      if (existing?.url) {
        URL.revokeObjectURL(existing.url);
      }
      const url = URL.createObjectURL(blob);
      const img = new Image();
      img.onload = () => {
        testPreviewCacheRef.current.set(activeFrameKey, { url, img });
        testPreviewUrlRef.current = url;
        testPreviewImgRef.current = img;
        drawPreview();
      };
      img.src = url;
    } catch (err) {
      setSetupError(err?.message || "Failed to generate preview");
    } finally {
      setTestPreviewing(false);
    }
  }

  function handleSetupPhotoClear() {
    setSetupPhoto(null);
    previewImgRef.current = null;
    currentPointsRef.current = [];
    allFramesRef.current = [];
    clearActiveSelection();
    greenscreenFrameRef.current = false;
    setSetupImageReady(false);
    clearTestPreviewState();
    resetView(false);
    syncCurrentPoints();
    syncFrameCount();
    setFramesJson("[]");
    setFramesJsonDirty(false);
    setSetupHint("Select a location, upload a billboard photo, then click four corners to define the frame.");
    drawPreview();
  }

  function handleSetupDragOver(event) {
    event.preventDefault();
    setSetupDragActive(true);
  }

  function handleSetupDragLeave(event) {
    event.preventDefault();
    setSetupDragActive(false);
  }

  function handleSetupDrop(event) {
    event.preventDefault();
    setSetupDragActive(false);
    const file = event.dataTransfer?.files?.[0];
    if (file) {
      setSetupPhoto(file);
      handleSetupPhoto(file);
    }
  }

  function handleCreativeDragOver(event) {
    event.preventDefault();
    setCreativeDragActive(true);
  }

  function handleCreativeDragLeave(event) {
    event.preventDefault();
    setCreativeDragActive(false);
  }

  function handleCreativeDrop(event) {
    event.preventDefault();
    setCreativeDragActive(false);
    const file = event.dataTransfer?.files?.[0];
    if (file) {
      setCreativeFile(file);
    }
  }

  return (
    <div className="h-full min-h-0 flex flex-col">
      <div className="flex-1 min-h-0 overflow-y-auto space-y-4 px-2 py-1">
        <div className="flex items-center gap-3">
          <Button
            variant={mode === "generate" ? "default" : "ghost"}
            onClick={() => setMode("generate")}
            className="rounded-2xl"
          >
            Generate
          </Button>
          {canSetup ? (
            <Button
              variant={mode === "setup" ? "default" : "ghost"}
              onClick={() => setMode("setup")}
              className="rounded-2xl"
            >
              Setup
            </Button>
          ) : null}
        </div>

        {mode === "generate" ? (
          <Card>
            <CardHeader>
              <CardTitle>Mockup Generator</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <FormField label="Location">
                  <select
                    className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                    value={location}
                    onChange={(e) => {
                      setLocation(e.target.value);
                      setTemplateKey("");
                    }}
                  >
                    <option value="">Select a location...</option>
                    {locationOptions.map((loc) => (
                      <option key={loc.key} value={loc.key}>
                        {loc.name}
                      </option>
                    ))}
                  </select>
                </FormField>

                <FormField label="Time of Day">
                  <select
                    className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                    value={timeOfDay}
                    onChange={(e) => setTimeOfDay(e.target.value)}
                  >
                    {TIME_OF_DAY.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </FormField>

                <FormField label="Billboard Finish">
                  <select
                    className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                    value={finish}
                    onChange={(e) => setFinish(e.target.value)}
                  >
                    {FINISHES.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </FormField>
              </div>

              {location ? (
                <FormField label="Template (optional)">
                  <select
                    className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                    value={templateKey}
                    onChange={(e) => setTemplateKey(e.target.value)}
                    disabled={templatesQuery.isLoading}
                  >
                    <option value="">Random template</option>
                    {templateOptions.map((t) => (
                      <option key={getTemplateKey(t)} value={getTemplateKey(t)}>
                        {t.photo} ({t.time_of_day}/{t.finish}, {t.frame_count} frame{t.frame_count > 1 ? "s" : ""})
                      </option>
                    ))}
                  </select>
                  <div className="text-[11px] text-black/50 dark:text-white/60">
                    {templatesQuery.isLoading ? "Loading templates..." : ""}
                  </div>
                </FormField>
              ) : null}

              {selectedTemplate ? (
                <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-white/40 dark:bg-white/5 p-4 space-y-3">
                  <label className="flex items-start gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={generateConfigEnabled}
                      onChange={(e) => setGenerateConfigEnabled(e.target.checked)}
                    />
                    <span>
                      <span className="font-semibold">Customize Frame Configuration</span>
                      <span className="block text-xs text-black/55 dark:text-white/60">
                        Enable to tweak lighting, blur, and other settings.
                      </span>
                    </span>
                  </label>

                  {generateConfigEnabled ? (
                    <FrameConfigControls
                      config={genFrameConfig}
                      onChange={(key, value) =>
                        setGenFrameConfig((prev) => ({
                          ...prev,
                          [key]: value,
                        }))
                      }
                    />
                  ) : null}
                </div>
              ) : null}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <FormField label="Upload Creative/Ad Image">
                  {creativeFile ? (
                    <div
                      className={`flex items-center justify-between rounded-xl bg-black/5 dark:bg-white/10 px-3 py-2 text-sm ${creativeDragActive ? "ring-2 ring-black/20 dark:ring-white/30" : ""}`}
                      onDragOver={handleCreativeDragOver}
                      onDragLeave={handleCreativeDragLeave}
                      onDrop={handleCreativeDrop}
                    >
                      <div className="truncate">{creativeFile.name}</div>
                      <button className="opacity-70 hover:opacity-100" onClick={() => setCreativeFile(null)}>
                        x
                      </button>
                    </div>
                  ) : (
                    <label
                      className={`block cursor-pointer rounded-xl border border-dashed border-black/10 dark:border-white/15 px-4 py-5 text-center text-sm bg-white/50 dark:bg-white/5 ${creativeDragActive ? "ring-2 ring-black/20 dark:ring-white/30" : ""}`}
                      onDragOver={handleCreativeDragOver}
                      onDragLeave={handleCreativeDragLeave}
                      onDrop={handleCreativeDrop}
                    >
                      <input
                        type="file"
                        className="hidden"
                        accept="image/jpeg,image/png,image/webp,image/gif"
                        onChange={(e) => setCreativeFile(e.target.files?.[0] || null)}
                      />
                      <div className="font-semibold mb-1">Click to upload/ Drag and Drop an Image</div>
                      <div className="text-xs text-black/55 dark:text-white/60">JPG, PNG, WEBP, GIF up to 10MB</div>
                    </label>
                  )}
                </FormField>

                <FormField label="Or use AI prompt">
                  <textarea
                  className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/10 dark:focus:ring-white/15 min-h-[80px]"
                    value={aiPrompt}
                    onChange={(e) => setAiPrompt(e.target.value)}
                    placeholder="Describe what you want to generate..."
                  />
                </FormField>
              </div>

              {generateError ? (
                <div className="rounded-xl bg-red-50/70 text-red-700 px-4 py-2 text-sm dark:bg-red-500/10 dark:text-red-300">
                  {generateError}
                </div>
              ) : null}

              <div className="flex items-center gap-3">
                <Button className="rounded-2xl" onClick={onGenerate} disabled={!canGenerate}>
                  {generating ? "Generating..." : "Generate"}
                </Button>
                <div className="text-xs text-black/55 dark:text-white/60">Location + (creative or prompt) required</div>
              </div>

              <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-white/40 dark:bg-white/5 p-4">
                {!resultUrl && !generating ? (
                  <div className="text-sm text-black/60 dark:text-white/65">Result will appear here</div>
                ) : null}
                {generating ? (
                  <div className="text-sm text-black/60 dark:text-white/65">Processing mockup...</div>
                ) : null}
                {resultUrl ? (
                  <div className="space-y-3">
                    <img
                      src={resultUrl}
                      alt="Generated mockup"
                      className="w-full rounded-xl border border-black/5 dark:border-white/10"
                    />
                    <div className="flex gap-2">
                      <a
                        href={resultUrl}
                        download={`mockup_${location || "result"}.jpg`}
                        className="inline-flex items-center justify-center rounded-2xl bg-black text-white px-4 py-2 text-sm dark:bg-white dark:text-black"
                      >
                        Download
                      </a>
                    </div>
                  </div>
                ) : null}
              </div>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>Mockup Setup</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-4">
                    <div className="space-y-4">
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <FormField label="Location">
                          <select
                            className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                            value={location}
                            onChange={(e) => {
                              setLocation(e.target.value);
                              setTemplateKey("");
                            }}
                          >
                            <option value="">Select a location...</option>
                            {locationOptions.map((loc) => (
                              <option key={loc.key} value={loc.key}>
                                {loc.name}
                              </option>
                            ))}
                          </select>
                        </FormField>

                        <FormField label="Time of Day">
                          <select
                            className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                            value={timeOfDay}
                            onChange={(e) => setTimeOfDay(e.target.value)}
                          >
                            {TIME_OF_DAY.map((opt) => (
                              <option key={opt.value} value={opt.value}>
                                {opt.label}
                              </option>
                            ))}
                          </select>
                        </FormField>

                        <FormField label="Billboard Finish">
                          <select
                            className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                            value={finish}
                            onChange={(e) => setFinish(e.target.value)}
                          >
                            {FINISHES.map((opt) => (
                              <option key={opt.value} value={opt.value}>
                                {opt.label}
                              </option>
                            ))}
                          </select>
                        </FormField>
                      </div>

                      {editingTemplate ? (
                        <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-white/50 dark:bg-white/5 px-4 py-3 flex flex-wrap items-center justify-between gap-2">
                          <div className="text-sm">
                            <span className="font-semibold">Editing template:</span>{" "}
                            {editingTemplate.photo} ({editingTemplate.time_of_day}/{editingTemplate.finish})
                          </div>
                          <div className="flex items-center gap-2">
                            {editingTemplateLoading ? (
                              <span className="text-xs text-black/50 dark:text-white/60">Loading...</span>
                            ) : null}
                            <Button variant="ghost" size="sm" className="rounded-xl" onClick={stopEditTemplate}>
                              Stop editing
                            </Button>
                          </div>
                        </div>
                      ) : null}
                      <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-white/40 dark:bg-white/5 p-4 shadow-soft">
                        <button
                          type="button"
                          className="flex w-full items-center justify-between gap-3 text-left"
                          onClick={() => setTemplatesOpen((prev) => !prev)}
                          aria-expanded={templatesOpen}
                        >
                          <div>
                            <div className="text-sm font-semibold text-black/80 dark:text-white/85">
                              Existing templates
                            </div>
                            <div className="text-xs text-black/55 dark:text-white/60">
                              {location
                                ? `${templateOptions.length} template${templateOptions.length === 1 ? "" : "s"}`
                                : "Select a location to load templates."}
                            </div>
                          </div>
                          <div className="flex items-center gap-2 text-xs text-black/50 dark:text-white/55">
                            <span>{templatesOpen ? "Hide" : "Show"}</span>
                            <ChevronDown
                              size={16}
                              className={cn("transition-transform", templatesOpen && "rotate-180")}
                            />
                          </div>
                        </button>
                        {templatesOpen ? (
                          <div className="mt-3 space-y-2">
                            {templatesQuery.isLoading ? (
                              <div className="text-sm text-black/60 dark:text-white/65">Loading templates...</div>
                            ) : null}
                            {!templatesQuery.isLoading && (!templateOptions.length || !location) ? (
                              <div className="text-sm text-black/60 dark:text-white/65">
                                No templates for this selection.
                              </div>
                            ) : null}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                              {templateOptions.map((t) => {
                                const isEditing =
                                  editingTemplate?.photo === t.photo &&
                                  editingTemplate?.time_of_day === t.time_of_day &&
                                  editingTemplate?.finish === t.finish;
                                return (
                                  <div
                                    key={`${t.photo}-${t.time_of_day}-${t.finish}`}
                                    className={`rounded-xl border border-black/5 dark:border-white/10 bg-white/60 dark:bg-white/5 p-3 text-sm space-y-2 ${isEditing ? "ring-2 ring-black/20 dark:ring-white/30" : ""}`}
                                  >
                                    <div className="overflow-hidden rounded-lg border border-black/5 dark:border-white/10 bg-black/5">
                                      <img
                                        src={mockupApi.getTemplatePhotoUrl(location, t.photo)}
                                        alt={t.photo}
                                        className="w-full h-32 object-cover"
                                        loading="lazy"
                                      />
                                    </div>
                                    <div className="font-semibold truncate">{t.photo}</div>
                                    <div className="text-xs text-black/55 dark:text-white/60">
                                      {t.time_of_day}/{t.finish} - {t.frame_count} frame
                                      {t.frame_count > 1 ? "s" : ""}
                                    </div>
                                    <div className="flex gap-2">
                                      <Button
                                        variant="secondary"
                                        size="sm"
                                        className="rounded-xl"
                                        onClick={() => startEditTemplate(t)}
                                        disabled={editingTemplateLoading}
                                      >
                                        Edit
                                      </Button>
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        className="rounded-xl"
                                        onClick={() => deleteTemplate(t.photo)}
                                      >
                                        Delete
                                      </Button>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        ) : null}
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <FormField label="Upload Billboard Photo">
                          {setupPhoto ? (
                            <div
                              className={`flex items-center justify-between rounded-xl bg-black/5 dark:bg-white/10 px-3 py-2 text-sm ${setupDragActive ? "ring-2 ring-black/20 dark:ring-white/30" : ""}`}
                              onDragOver={handleSetupDragOver}
                              onDragLeave={handleSetupDragLeave}
                              onDrop={handleSetupDrop}
                            >
                              <div className="truncate">{setupPhoto.name}</div>
                              <button className="opacity-70 hover:opacity-100" onClick={handleSetupPhotoClear}>
                                x
                              </button>
                            </div>
                          ) : (
                            <label
                              className={`block cursor-pointer rounded-xl border border-dashed border-black/10 dark:border-white/15 px-4 py-5 text-center text-sm bg-white/50 dark:bg-white/5 ${setupDragActive ? "ring-2 ring-black/20 dark:ring-white/30" : ""}`}
                              onDragOver={handleSetupDragOver}
                              onDragLeave={handleSetupDragLeave}
                              onDrop={handleSetupDrop}
                            >
                              <input
                                type="file"
                                className="hidden"
                                accept="image/jpeg,image/png,image/webp"
                                onChange={(e) => {
                                  const file = e.target.files?.[0];
                                  if (file) {
                                    setSetupPhoto(file);
                                    handleSetupPhoto(file);
                                  }
                                }}
                              />
                              <div className="font-semibold mb-1">Click to upload/ Drag and Drop an Image</div>
                              <div className="text-xs text-black/55 dark:text-white/60">JPG, PNG, WEBP up to 20MB</div>
                            </label>
                          )}
                        </FormField>
                        <FormField label="Frames JSON">
                          <textarea
                            className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/10 dark:focus:ring-white/15 min-h-[80px] font-mono"
                            value={framesJson}
                            onChange={(e) => {
                              setFramesJson(e.target.value);
                              setFramesJsonDirty(true);
                            }}
                            placeholder='[{"points":[0,0,0,0],"config":{"brightness":100}}]'
                          />
                          <div className="flex items-center justify-between text-[11px] text-black/50 dark:text-white/60">
                            <span>Auto-filled from canvas. Edit to override.</span>
                            <div className="flex items-center gap-3">
                              <button type="button" className="text-xs underline" onClick={applyFramesJsonToCanvas}>
                                Apply to canvas
                              </button>
                              <button
                                type="button"
                                className="text-xs underline"
                                onClick={() => {
                                  setFramesJsonDirty(false);
                                  const payload = buildFramesPayload();
                                  setFramesJson(payload.length ? JSON.stringify(payload, null, 2) : "[]");
                                }}
                              >
                                Sync from canvas
                              </button>
                            </div>
                          </div>
                        </FormField>
                      </div>

                      {setupImageReady ? (
                        <>
                          <SoftCard className="bg-white/50 dark:bg-white/5 p-4">
                            <button
                              type="button"
                              className="flex w-full items-center justify-between gap-3 text-left"
                              onClick={() => setGreenscreenOpen((prev) => !prev)}
                              aria-expanded={greenscreenOpen}
                            >
                              <div>
                                <div className="text-sm font-semibold text-black/80 dark:text-white/85">
                                  Green Screen Detection
                                </div>
                                <div className="text-xs text-black/55 dark:text-white/60">
                                  Detect billboard frame using chroma key.
                                </div>
                              </div>
                              <div className="flex items-center gap-2 text-xs text-black/50 dark:text-white/55">
                                <span>{greenscreenOpen ? "Hide" : "Edit"}</span>
                                <ChevronDown
                                  size={16}
                                  className={cn("transition-transform", greenscreenOpen && "rotate-180")}
                                />
                              </div>
                            </button>

                            {greenscreenOpen ? (
                              <div className="mt-3 space-y-3">
                                <div className="flex items-center gap-3">
                                  <input
                                    type="color"
                                    value={greenscreenColor}
                                    onChange={(e) => setGreenscreenColor(e.target.value.toUpperCase())}
                                    className="h-10 w-16 rounded-lg border border-black/10 dark:border-white/20"
                                  />
                                  <input
                                    type="text"
                                    value={greenscreenColor}
                                    onChange={(e) => setGreenscreenColor(e.target.value.toUpperCase())}
                                    className="flex-1 rounded-xl bg-white/70 dark:bg-white/10 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none font-mono"
                                  />
                                </div>
                                <div className="text-xs text-black/55 dark:text-white/60">
                                  Tip: Shift+click to pick a color. Shift+drag or middle mouse pans.
                                </div>
                                <RangeField
                                  label="Color Tolerance"
                                  value={colorTolerance}
                                  min={10}
                                  max={100}
                                  onChange={(val) => setColorTolerance(val)}
                                  helper="Lower is stricter, higher is more forgiving."
                                />
                                <Button
                                  className="rounded-2xl w-full"
                                  onClick={handleGreenscreenDetect}
                                  disabled={!canDetectGreenscreen}
                                >
                                  Detect Green Screen Now
                                </Button>
                              </div>
                            ) : null}
                          </SoftCard>

                          {hasActiveFrame ? (
                            <div className="rounded-2xl bg-blue-50/70 dark:bg-blue-500/10 ring-1 ring-blue-500/20 p-4 shadow-soft">
                              <button
                                type="button"
                                className="flex w-full items-center justify-between gap-3 text-left"
                                onClick={() => setFrameSettingsOpen((prev) => !prev)}
                                aria-expanded={frameSettingsOpen}
                              >
                                <div>
                                  <div className="text-sm font-semibold text-blue-900 dark:text-blue-100">
                                    Current Frame Settings
                                  </div>
                                  <div className="text-xs text-blue-800 dark:text-blue-200">
                                    Adjust the current frame appearance.
                                  </div>
                                </div>
                                <div className="flex items-center gap-2 text-xs text-blue-800 dark:text-blue-200">
                                  <span>{frameSettingsOpen ? "Hide" : "Edit"}</span>
                                  <ChevronDown
                                    size={16}
                                    className={cn("transition-transform", frameSettingsOpen && "rotate-180")}
                                  />
                                </div>
                              </button>
                              {frameSettingsOpen ? (
                                <div className="mt-3 space-y-3">
                                  <FrameConfigControls
                                    config={setupFrameConfig}
                                    onChange={handleSetupFrameConfigChange}
                                  />
                                  <div className="text-xs text-blue-800 dark:text-blue-200">
                                    Settings apply to the current frame only.
                                  </div>
                                </div>
                              ) : null}
                            </div>
                          ) : null}

                          {hasActiveFrame ? (
                            <div className="rounded-2xl bg-blue-50/70 dark:bg-blue-500/10 ring-1 ring-blue-500/20 p-4 shadow-soft">
                              <button
                                type="button"
                                className="flex w-full items-center justify-between gap-3 text-left"
                                onClick={() => setPreviewOpen((prev) => !prev)}
                                aria-expanded={previewOpen}
                              >
                                <div>
                                  <div className="text-sm font-semibold text-blue-900 dark:text-blue-100">
                                    Test Preview Mode
                                  </div>
                                  <div className="text-xs text-blue-800 dark:text-blue-200">
                                    Preview creative on the current frame before saving.
                                  </div>
                                </div>
                                <div className="flex items-center gap-2 text-xs text-blue-800 dark:text-blue-200">
                                  <span>{previewOpen ? "Hide" : "Edit"}</span>
                                  <ChevronDown
                                    size={16}
                                    className={cn("transition-transform", previewOpen && "rotate-180")}
                                  />
                                </div>
                              </button>
                              {previewOpen ? (
                                <div className="mt-3 space-y-2">
                                  <label className="flex items-center gap-3 text-sm">
                                    <input
                                      type="checkbox"
                                      checked={testPreviewMode}
                                      onChange={(e) => {
                                    setTestPreviewMode(e.target.checked);
                                    if (!e.target.checked) {
                                      testPreviewImgRef.current = null;
                                      testPreviewUrlRef.current = "";
                                      drawPreview();
                                    }
                                  }}
                                />
                                    <span className="font-semibold text-blue-900 dark:text-blue-100">
                                      Enable preview
                                    </span>
                                  </label>
                                  {testPreviewMode ? (
                                    <div className="space-y-2">
                                      <label className="block text-xs font-semibold text-blue-900 dark:text-blue-100">
                                        Upload Test Creative
                                      </label>
                                  <input
                                    type="file"
                                    accept="image/*"
                                    onChange={(e) => updateTestCreativeForActive(e.target.files?.[0] || null)}
                                    className="w-full text-sm"
                                  />
                                  {activeTestCreativeFile ? (
                                    <div className="text-[11px] text-blue-800 dark:text-blue-200">
                                      Selected: {activeTestCreativeFile.name}
                                    </div>
                                  ) : null}
                                  <Button
                                    className="rounded-2xl w-full"
                                    onClick={generateTestPreview}
                                    disabled={
                                      !activeTestCreativeFile || !setupPhoto || !hasActiveFrame || testPreviewing
                                    }
                                  >
                                    {testPreviewing ? "Generating..." : "Generate Test Preview"}
                                  </Button>
                                  {activeFrameIndex >= 0 ? (
                                    <div className="text-[11px] text-blue-800 dark:text-blue-200">
                                      Preview applies to frame {activeFrameIndex + 1}.
                                    </div>
                                  ) : null}
                                </div>
                              ) : null}
                            </div>
                          ) : null}
                            </div>
                          ) : null}
                        </>
                      ) : null}
                    </div>
                    {setupImageReady ? (
                      <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-white/40 dark:bg-white/5 p-3 space-y-2">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <Button
                              variant="secondary"
                              size="sm"
                              className="h-8 px-3"
                              onClick={handleZoomOut}
                              disabled={!previewImgRef.current}
                            >
                              -
                            </Button>
                            <Button
                              variant="secondary"
                              size="sm"
                              className="h-8 px-3"
                              onClick={handleZoomIn}
                              disabled={!previewImgRef.current}
                            >
                              +
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={handleFitToScreen}
                              disabled={!previewImgRef.current}
                            >
                              Fit
                            </Button>
                            <span className="text-xs text-black/60 dark:text-white/60">{zoomPercent}%</span>
                          </div>
                          <label className="flex items-center gap-2 text-xs text-black/70 dark:text-white/70">
                            <input
                              type="checkbox"
                              checked={pixelUpscale}
                              onChange={(e) => setPixelUpscale(e.target.checked)}
                            />
                            Pixel Upscale
                          </label>
                        </div>
                        <canvas
                          ref={canvasRef}
                          width={CANVAS_WIDTH}
                          height={CANVAS_HEIGHT}
                          className="w-full h-auto rounded-xl border border-black/10 dark:border-white/10 bg-white"
                          onPointerDown={handleCanvasPointerDown}
                          onPointerMove={handleCanvasPointerMove}
                          onPointerUp={handleCanvasPointerUp}
                          onPointerLeave={handleCanvasPointerUp}
                          onWheel={handleCanvasWheel}
                          style={{ touchAction: "none" }}
                        />
                        <div className="text-xs text-black/60 dark:text-white/60">{setupHint}</div>
                      </div>
                    ) : (
                      <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-black/5 dark:bg-white/10 px-4 py-3 text-sm text-black/60 dark:text-white/65">
                        Upload a billboard photo or pick an existing template to enable the canvas tools.
                      </div>
                    )}
                  </div>

                  {setupError ? (
                    <div className="rounded-xl bg-red-50/70 text-red-700 px-4 py-2 text-sm dark:bg-red-500/10 dark:text-red-300">
                      {setupError}
                    </div>
                  ) : null}
                  {setupMessage ? (
                    <div className="rounded-xl bg-green-50/70 text-green-700 px-4 py-2 text-sm dark:bg-green-500/10 dark:text-green-200">
                      {setupMessage}
                    </div>
                  ) : null}

                  <div className="flex flex-wrap gap-2">
                    <Button className="rounded-2xl" onClick={addFrame} disabled={currentPoints.length !== 4}>
                      Add Frame
                    </Button>
                    <Button variant="secondary" className="rounded-2xl" onClick={resetCurrentFrame}>
                      Reset Current Frame
                    </Button>
                    <Button
                      className="rounded-2xl"
                      onClick={saveSetup}
                      disabled={setupSaving || !location || !setupPhoto}
                    >
                      {setupSaving ? "Saving..." : editingTemplate ? "Save Changes" : "Save All Frames"}
                    </Button>
                    <Button variant="ghost" className="rounded-2xl" onClick={() => clearAllFrames(false)}>
                      Clear All Frames
                    </Button>
                  </div>

                  {frameCount ? (
                    <div className="rounded-xl bg-blue-50/70 text-blue-900 px-3 py-2 text-sm dark:bg-blue-500/10 dark:text-blue-100">
                      Frames configured: {frameCount}
                    </div>
                  ) : null}

                  
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

function FrameConfigControls({ config, onChange }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <RangeField
        label="Brightness"
        value={config.brightness}
        min={50}
        max={200}
        suffix="%"
        onChange={(val) => onChange("brightness", val)}
      />
      <RangeField
        label="Contrast"
        value={config.contrast}
        min={50}
        max={200}
        suffix="%"
        onChange={(val) => onChange("contrast", val)}
      />
      <RangeField
        label="Saturation"
        value={config.saturation}
        min={0}
        max={200}
        suffix="%"
        onChange={(val) => onChange("saturation", val)}
      />
      <RangeField
        label="Image Blur"
        value={config.imageBlur}
        min={0}
        max={20}
        onChange={(val) => onChange("imageBlur", val)}
        helper="Blur entire creative (0 = off)."
      />
      <RangeField
        label="Edge Blur"
        value={config.edgeBlur}
        min={1}
        max={20}
        suffix="px"
        onChange={(val) => onChange("edgeBlur", val)}
        helper="Edge blur amount (1 = off)."
      />
      <RangeField
        label="Overlay Opacity"
        value={config.overlayOpacity}
        min={0}
        max={50}
        suffix="%"
        onChange={(val) => onChange("overlayOpacity", val)}
        helper="Billboard overlay strength."
      />

      <div className="md:col-span-2 grid grid-cols-1 sm:grid-cols-2 gap-3">
        <LightDirectionPicker
          value={config.lightDirection}
          onChange={(val) => onChange("lightDirection", val)}
        />
        <RangeField
          label="Depth Perception"
          value={config.depthMultiplier}
          min={5}
          max={30}
          suffix="x"
          onChange={(val) => onChange("depthMultiplier", val)}
          helper="Perspective compensation."
        />
      </div>

      <RangeField
        label="Shadow Intensity"
        value={config.shadowIntensity}
        min={0}
        max={100}
        suffix="%"
        onChange={(val) => onChange("shadowIntensity", val)}
        helper="Edge darkening."
      />
      <RangeField
        label="Lighting Match"
        value={config.lightingAdjustment}
        min={-50}
        max={50}
        suffix="%"
        onChange={(val) => onChange("lightingAdjustment", val)}
        helper="Brightness matching."
      />
      <RangeField
        label="Color Temperature"
        value={config.colorTemperature}
        min={-50}
        max={50}
        onChange={(val) => onChange("colorTemperature", val)}
        helper="Warm/cool shift."
      />
      <RangeField
        label="Vignette"
        value={config.vignette}
        min={0}
        max={100}
        suffix="%"
        onChange={(val) => onChange("vignette", val)}
        helper="Corner darkening."
      />
      <RangeField
        label="Edge Smoother"
        value={config.edgeSmoother}
        min={1}
        max={20}
        suffix="x"
        onChange={(val) => onChange("edgeSmoother", val)}
        helper="Higher = softer edges."
      />
      <RangeField
        label="Sharpening"
        value={config.sharpening}
        min={0}
        max={100}
        suffix="%"
        onChange={(val) => onChange("sharpening", val)}
        helper="Unsharp mask strength (0 = off)."
      />
    </div>
  );
}

function LightDirectionPicker({ value, onChange }) {
  return (
    <div className="space-y-2">
      <div className="text-xs font-semibold text-black/70 dark:text-white/70">
        Light Direction: {LIGHT_LABELS[value] || "Top"}
      </div>
      <div className="grid grid-cols-3 gap-2 w-[150px]">
        {LIGHT_DIRECTIONS.map((dir) => (
          <button
            key={dir.value}
            type="button"
            onClick={() => onChange(dir.value)}
            className={`rounded-lg border px-2 py-2 text-sm font-semibold ${
              value === dir.value
                ? "border-black/40 dark:border-white/50 bg-black/5 dark:bg-white/15 text-black dark:text-white"
                : "border-black/10 dark:border-white/20 bg-white/80 dark:bg-black/40 text-black/70 dark:text-white/80"
            }`}
            title={dir.label}
          >
            {dir.glyph}
          </button>
        ))}
      </div>
    </div>
  );
}

function RangeField({ label, value, min, max, step = 1, suffix = "", helper, onChange }) {
  return (
    <div className="space-y-1">
      <div className="text-xs font-semibold text-black/70 dark:text-white/70">
        {label}: {value}
        {suffix}
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ background: getRangeBackground(value, min, max) }}
        className="w-full accent-black"
      />
      {helper ? <div className="text-[11px] text-black/55 dark:text-white/60">{helper}</div> : null}
    </div>
  );
}

function getTemplateKey(template) {
  return `${template.photo}::${template.time_of_day || "all"}::${template.finish || "all"}`;
}

function detectGreenScreen(imageData, { color, tolerance, depthMultiplier, existingFrames }) {
  const data = imageData.data;
  const width = imageData.width;
  const height = imageData.height;
  const targetR = parseInt(color.slice(1, 3), 16);
  const targetG = parseInt(color.slice(3, 5), 16);
  const targetB = parseInt(color.slice(5, 7), 16);
  const colorTolerance = tolerance;

  const exclusionMask = new Uint8Array(width * height);
  existingFrames.forEach((frame) => {
    const pts = frame.points;
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        if (isPointInPolygon(x, y, pts)) {
          exclusionMask[y * width + x] = 1;
        }
      }
    }
  });

  const mask = new Uint8Array(width * height);
  let matchedPixelCount = 0;

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const pixelIdx = y * width + x;
      if (exclusionMask[pixelIdx] === 1) continue;
      const i = pixelIdx * 4;
      const r = data[i];
      const g = data[i + 1];
      const b = data[i + 2];
      const distance = Math.sqrt((r - targetR) ** 2 + (g - targetG) ** 2 + (b - targetB) ** 2);
      if (distance <= colorTolerance) {
        mask[pixelIdx] = 255;
        matchedPixelCount += 1;
      }
    }
  }

  if (matchedPixelCount < 1000) return null;

  const dilatedMask = new Uint8Array(width * height);
  const expandPixels = 3;

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const idx = y * width + x;
      let hasGreenNearby = false;
      for (let dy = -expandPixels; dy <= expandPixels; dy += 1) {
        for (let dx = -expandPixels; dx <= expandPixels; dx += 1) {
          const ny = y + dy;
          const nx = x + dx;
          if (ny >= 0 && ny < height && nx >= 0 && nx < width) {
            if (mask[ny * width + nx] === 255) {
              hasGreenNearby = true;
              break;
            }
          }
        }
        if (hasGreenNearby) break;
      }
      dilatedMask[idx] = hasGreenNearby ? 255 : 0;
    }
  }

  const contourPoints = [];
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const idx = y * width + x;
      if (dilatedMask[idx] === 0) {
        const hasNeighbor =
          dilatedMask[idx - 1] === 255 ||
          dilatedMask[idx + 1] === 255 ||
          dilatedMask[idx - width] === 255 ||
          dilatedMask[idx + width] === 255 ||
          dilatedMask[idx - width - 1] === 255 ||
          dilatedMask[idx - width + 1] === 255 ||
          dilatedMask[idx + width - 1] === 255 ||
          dilatedMask[idx + width + 1] === 255;

        if (hasNeighbor) contourPoints.push([x, y]);
      }
    }
  }

  if (contourPoints.length < 4) return null;

  let topLeft = contourPoints[0];
  let topRight = contourPoints[0];
  let bottomRight = contourPoints[0];
  let bottomLeft = contourPoints[0];

  contourPoints.forEach((pt) => {
    const [x, y] = pt;
    if (x + y < topLeft[0] + topLeft[1]) topLeft = pt;
    if (x - y > topRight[0] - topRight[1]) topRight = pt;
    if (x + y > bottomRight[0] + bottomRight[1]) bottomRight = pt;
    if (x - y < bottomLeft[0] - bottomLeft[1]) bottomLeft = pt;
  });

  const topWidth = Math.abs(topRight[0] - topLeft[0]);
  const bottomWidth = Math.abs(bottomRight[0] - bottomLeft[0]);
  const leftHeight = Math.abs(bottomLeft[1] - topLeft[1]);
  const rightHeight = Math.abs(bottomRight[1] - topRight[1]);
  const widthRatio = topWidth / bottomWidth;
  const heightRatio = leftHeight / rightHeight;
  const depth = depthMultiplier || DEFAULT_FRAME_CONFIG.depthMultiplier;

  if (widthRatio > 1.1) {
    const extra = Math.floor((widthRatio - 1) * depth);
    bottomLeft = [bottomLeft[0], Math.min(height - 1, bottomLeft[1] + extra)];
    bottomRight = [bottomRight[0], Math.min(height - 1, bottomRight[1] + extra)];
  } else if (widthRatio < 0.9) {
    const extra = Math.floor((1 / widthRatio - 1) * depth);
    topLeft = [topLeft[0], Math.max(0, topLeft[1] - extra)];
    topRight = [topRight[0], Math.max(0, topRight[1] - extra)];
  }

  if (heightRatio > 1.1) {
    const extra = Math.floor((heightRatio - 1) * depth);
    topRight = [Math.min(width - 1, topRight[0] + extra), topRight[1]];
    bottomRight = [Math.min(width - 1, bottomRight[0] + extra), bottomRight[1]];
  } else if (heightRatio < 0.9) {
    const extra = Math.floor((1 / heightRatio - 1) * depth);
    topLeft = [Math.max(0, topLeft[0] - extra), topLeft[1]];
    bottomLeft = [Math.max(0, bottomLeft[0] - extra), bottomLeft[1]];
  }

  return [topLeft, topRight, bottomRight, bottomLeft];
}

function isPointInPolygon(x, y, points) {
  let inside = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const xi = points[i][0];
    const yi = points[i][1];
    const xj = points[j][0];
    const yj = points[j][1];

    const intersect = yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

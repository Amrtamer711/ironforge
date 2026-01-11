import React, { useState } from "react";
import { ChevronDown } from "lucide-react";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { FormField } from "../../../components/ui/form-field";
import { MultiSelect } from "../../../components/ui/multi-select";
import { ConfirmModal } from "../../../components/ui/modal";
import { SoftCard } from "../../../components/ui/soft-card";
import { LoadingEllipsis } from "../../../components/ui/loading-ellipsis";
import { SelectDropdown } from "../../../components/ui/select-dropdown";
import { cn } from "../../../lib/utils";

export function SetupTab({
  locations,
  setLocations,
  venueType,
  setVenueType,
  assetType,
  setAssetType,
  setTemplateKey,
  locationOptions,
  locationsQuery,
  assetTypeOptions,
  assetTypesQuery,
  timeOfDay,
  setTimeOfDay,
  timeOfDayDisabled,
  sideDisabled,
  side,
  setSide,
  timeOfDayOptions,
  sideOptions,
  venueTypeOptions,
  editingTemplate,
  editingTemplateLoading,
  stopEditTemplate,
  templatesOpen,
  setTemplatesOpen,
  templateOptions,
  templatesQuery,
  templateThumbs,
  getTemplateKey,
  startEditTemplate,
  deleteTemplate,
  setupPhoto,
  setSetupPhoto,
  handleSetupPhoto,
  handleSetupDragOver,
  handleSetupDragLeave,
  handleSetupDrop,
  setupDragActive,
  handleSetupPhotoClear,
  framesJson,
  setFramesJson,
  setFramesJsonDirty,
  applyFramesJsonToCanvas,
  buildFramesPayload,
  setupImageReady,
  greenscreenOpen,
  setGreenscreenOpen,
  greenscreenColor,
  setGreenscreenColor,
  greenscreenDetecting,
  colorTolerance,
  setColorTolerance,
  RangeField,
  handleGreenscreenDetect,
  canDetectGreenscreen,
  hasActiveFrame,
  frameSettingsOpen,
  setFrameSettingsOpen,
  setupFrameConfig,
  handleSetupFrameConfigChange,
  FrameConfigControls,
  previewOpen,
  setPreviewOpen,
  testPreviewMode,
  setTestPreviewMode,
  testPreviewImgRef,
  testPreviewUrlRef,
  previewImgRef,
  drawPreview,
  activeTestCreativeFile,
  updateTestCreativeForActive,
  generateTestPreview,
  testPreviewing,
  activeFrameIndex,
  canvasRef,
  canvasWidth,
  canvasHeight,
  handleCanvasPointerDown,
  handleCanvasPointerMove,
  handleCanvasPointerUp,
  handleCanvasWheel,
  setupHint,
  handleZoomOut,
  handleZoomIn,
  handleFitToScreen,
  zoomPercent,
  pixelUpscale,
  setPixelUpscale,
  setupError,
  setupMessage,
  addFrame,
  resetCurrentFrame,
  saveSetup,
  setupSaving,
  clearAllFrames,
  currentPoints,
  frameCount,
  useNativeSelects,
}) {
  const [confirmDelete, setConfirmDelete] = useState({ open: false, template: null });
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);

  const deleteTimeOfDay = confirmDelete.template?.time_of_day || "all";
  const deleteSide = confirmDelete.template?.side || "all";
  const deleteLocation = confirmDelete.template?.storage_key || "";
  const deleteLocationLabel = deleteLocation ? ` for ${deleteLocation}` : "";
  const deleteMessage = confirmDelete.template
    ? `Delete "${confirmDelete.template.photo}" (${deleteTimeOfDay}/${deleteSide})${deleteLocationLabel}? This removes the photo and its frames.`
    : "Delete this template? This removes the photo and its frames.";

  async function handleConfirmDelete() {
    if (!confirmDelete.template || deleteSubmitting) return;
    setDeleteSubmitting(true);
    try {
      await deleteTemplate(confirmDelete.template);
    } finally {
      setDeleteSubmitting(false);
      setConfirmDelete({ open: false, template: null });
    }
  }

  function handleCloseDelete() {
    if (deleteSubmitting) return;
    setConfirmDelete({ open: false, template: null });
  }

  return (
    <>
      <Card className="h-full flex flex-col">
        <CardHeader>
          <CardTitle>Mockup Setup</CardTitle>
        </CardHeader>
        <CardContent className="flex-1 min-h-0 overflow-y-auto space-y-4">
        <div className="space-y-4">
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
              <FormField label="Location">
                <MultiSelect
                  value={locations}
                  onChange={(next) => {
                    setLocations(next);
                    setTemplateKey("");
                  }}
                  options={locationOptions.map((loc) => {
                    const value = loc?.key ?? loc?.id ?? loc?.value ?? loc;
                    const label = loc?.name ?? loc?.label ?? value;
                    return { value, label };
                  })}
                  placeholder="Select locations"
                />
                {locationsQuery.isLoading ? (
                  <div className="mt-1 text-xs text-black/50 dark:text-white/60">
                    <LoadingEllipsis text="Loading locations" />
                  </div>
                ) : null}
              </FormField>

              <FormField label="Asset Type">
                <SelectDropdown
                  value={assetType}
                  options={[
                    { value: "", label: "All asset types" },
                    ...assetTypeOptions.map((type) => {
                      if (typeof type === "string") {
                        return { value: type, label: type };
                      }
                      return {
                        value: type?.type_key ?? type?.key ?? type?.id ?? type?.value ?? "",
                        label: type?.name ?? type?.label ?? type?.type_key ?? "Unknown",
                      };
                    }),
                  ]}
                  placeholder="Select asset type"
                  onChange={(nextValue) => setAssetType(nextValue)}
                  useNativeSelect={useNativeSelects}
                />
                {assetTypesQuery?.isLoading ? (
                  <div className="mt-1 text-xs text-black/50 dark:text-white/60">
                    <LoadingEllipsis text="Loading asset types" />
                  </div>
                ) : null}
              </FormField>

              <FormField label="Venue Type">
                <SelectDropdown
                  value={venueType}
                  options={venueTypeOptions}
                  placeholder="Select venue type"
                  onChange={(nextValue) => setVenueType(nextValue)}
                  useNativeSelect={useNativeSelects}
                />
              </FormField>

              {!timeOfDayDisabled && (
                <FormField label="Time of Day">
                  <SelectDropdown
                    value={timeOfDay}
                    options={timeOfDayOptions}
                    placeholder="Select time of day"
                    onChange={(nextValue) => setTimeOfDay(nextValue)}
                    useNativeSelect={useNativeSelects}
                  />
                </FormField>
              )}

              {!sideDisabled && (
                <FormField label="Billboard Side">
                  <SelectDropdown
                    value={side}
                    options={sideOptions}
                    placeholder="Select side"
                    onChange={(nextValue) => setSide(nextValue)}
                    useNativeSelect={useNativeSelects}
                  />
                </FormField>
              )}
            </div>

            {editingTemplate ? (
              <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-white/50 dark:bg-white/5 px-4 py-3 flex flex-wrap items-center justify-between gap-2">
                <div className="text-sm">
                  <span className="font-semibold">Editing template:</span> {editingTemplate.photo} (
                  {editingTemplate.time_of_day}/{editingTemplate.side})
                </div>
                <div className="flex items-center gap-2">
                  {editingTemplateLoading ? (
                    <LoadingEllipsis text="Loading" className="text-xs text-black/50 dark:text-white/60" />
                  ) : null}
                  <Button variant="ghost" size="sm" className="rounded-xl" onClick={stopEditTemplate}>
                    Stop editing
                  </Button>
                </div>
              </div>
            ) : null}
            {!editingTemplate ? (
              <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-white/40 dark:bg-white/5 p-4 shadow-soft">
                <button
                  type="button"
                  className="flex w-full items-center justify-between gap-3 text-left"
                  onClick={() => setTemplatesOpen((prev) => !prev)}
                  aria-expanded={templatesOpen}
                >
                  <div>
                    <div className="text-sm font-semibold text-black/80 dark:text-white/85">Existing templates</div>
                    <div className="text-xs text-black/55 dark:text-white/60">
                      {locations.length
                        ? `${templateOptions.length} template${templateOptions.length === 1 ? "" : "s"}`
                        : "Select at least one location to load templates."}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-black/50 dark:text-white/55">
                    <span>{templatesOpen ? "Hide" : "Show"}</span>
                    <ChevronDown size={16} className={cn("transition-transform", templatesOpen && "rotate-180")} />
                  </div>
                </button>
                {templatesOpen ? (
                  <div className="mt-3 space-y-2">
                    {templatesQuery.isLoading ? (
                      <LoadingEllipsis text="Loading templates" className="text-sm text-black/60 dark:text-white/65" />
                    ) : null}
                    {!templatesQuery.isLoading && (!templateOptions.length || !locations.length) ? (
                      <div className="text-sm text-black/60 dark:text-white/65">No templates for this selection.</div>
                    ) : null}
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-2">
                      {templateOptions.map((t) => {
                        const templateKey = getTemplateKey(t);
                        return (
                          <div
                            key={templateKey}
                            className="rounded-xl border border-black/5 dark:border-white/10 bg-white/60 dark:bg-white/5 p-3 text-sm transition flex flex-col"
                          >
                            <div className="overflow-hidden rounded-lg border border-black/5 dark:border-white/10 bg-black/5">
                              {templateThumbs[templateKey] ? (
                                <img
                                  src={templateThumbs[templateKey]}
                                  alt={t.photo}
                                  className="w-full h-40 object-cover"
                                  loading="lazy"
                                />
                              ) : (
                                <div className="h-40 grid place-items-center text-xs text-black/50 dark:text-white/60">
                                  <LoadingEllipsis text="Loading" className="text-xs text-black/50 dark:text-white/60" />
                                </div>
                              )}
                            </div>
                            <div className="mt-auto pt-2 space-y-2">
                              <div className="font-semibold truncate">{t.photo}</div>
                              <div className="text-xs text-black/55 dark:text-white/60">
                                {t.time_of_day}/{t.side} - {t.frame_count} frame
                                {t.frame_count > 1 ? "s" : ""}
                              </div>
                              <div className="flex gap-2">
                                <Button
                                  variant="secondary"
                                  size="sm"
                                  className="rounded-xl"
                                  onClick={() => startEditTemplate(t)}
                                  disabled={editingTemplateLoading || deleteSubmitting}
                                >
                                  Edit
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="rounded-xl"
                                  onClick={() => setConfirmDelete({ open: true, template: t })}
                                  disabled={deleteSubmitting}
                                >
                                  Delete
                                </Button>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <FormField label="Upload Billboard Photo">
                {setupPhoto ? (
                  <div
                    className={`flex items-center justify-between rounded-xl bg-black/5 dark:bg-white/10 px-3 py-2 text-sm min-h-[120px] ${setupDragActive ? "ring-2 ring-black/20 dark:ring-white/30" : ""}`}
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
                    className={`block cursor-pointer rounded-xl border border-dashed border-black/10 dark:border-white/15 px-4 py-5 text-center text-sm bg-white/50 dark:bg-white/5 min-h-[120px] ${setupDragActive ? "ring-2 ring-black/20 dark:ring-white/30" : ""}`}
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
              <FormField label="Frames Data">
                <textarea
                  className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/10 dark:focus:ring-white/15 min-h-[120px] font-mono"
                  value={framesJson}
                  onChange={(e) => {
                    setFramesJson(e.target.value);
                    setFramesJsonDirty(true);
                  }}
                  placeholder='[{"points":[0,0,0,0],"config":{"brightness":100}}]'
                />
                <div className="flex items-center justify-between text-xs text-black/50 dark:text-white/60">
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
                      <ChevronDown size={16} className={cn("transition-transform", greenscreenOpen && "rotate-180")} />
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
                        disabled={!canDetectGreenscreen || greenscreenDetecting}
                      >
                        {greenscreenDetecting ? <LoadingEllipsis text="Detecting" /> : "Detect Green Screen Now"}
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
                        <ChevronDown size={16} className={cn("transition-transform", frameSettingsOpen && "rotate-180")} />
                      </div>
                    </button>
                    {frameSettingsOpen ? (
                      <div className="mt-3 space-y-3">
                        <FrameConfigControls config={setupFrameConfig} onChange={handleSetupFrameConfigChange} />
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
                        <div className="text-sm font-semibold text-blue-900 dark:text-blue-100">Test Preview Mode</div>
                        <div className="text-xs text-blue-800 dark:text-blue-200">
                          Preview creative on the current frame before saving.
                        </div>
                      </div>
                      <div className="flex items-center gap-2 text-xs text-blue-800 dark:text-blue-200">
                        <span>{previewOpen ? "Hide" : "Edit"}</span>
                        <ChevronDown size={16} className={cn("transition-transform", previewOpen && "rotate-180")} />
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
                          <span className="font-semibold text-blue-900 dark:text-blue-100">Enable preview</span>
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
                              <div className="text-xs text-blue-800 dark:text-blue-200">
                                Selected: {activeTestCreativeFile.name}
                              </div>
                            ) : null}
                            <Button
                              className="rounded-2xl w-full"
                              onClick={generateTestPreview}
                              disabled={!activeTestCreativeFile || !setupPhoto || !hasActiveFrame || testPreviewing}
                            >
                              {testPreviewing ? <LoadingEllipsis text="Generating" /> : "Generate Test Preview"}
                            </Button>
                            {activeFrameIndex >= 0 ? (
                              <div className="text-xs text-blue-800 dark:text-blue-200">
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
                  <Button variant="ghost" size="sm" onClick={handleFitToScreen} disabled={!previewImgRef.current}>
                    Fit
                  </Button>
                  <span className="text-xs text-black/60 dark:text-white/60">{zoomPercent}%</span>
                </div>
                <label className="flex items-center gap-2 text-xs text-black/70 dark:text-white/70">
                  <input type="checkbox" checked={pixelUpscale} onChange={(e) => setPixelUpscale(e.target.checked)} />
                  Pixel Upscale
                </label>
              </div>
              <canvas
                ref={canvasRef}
                width={canvasWidth}
                height={canvasHeight}
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
          <Button className="rounded-2xl" onClick={saveSetup} disabled={setupSaving || !locations.length || !setupPhoto}>
            {setupSaving ? (
              <LoadingEllipsis text="Saving" />
            ) : editingTemplate ? (
              "Save Changes"
            ) : (
              "Save All Frames"
            )}
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

      <ConfirmModal
        open={confirmDelete.open}
        message={deleteMessage}
        onClose={handleCloseDelete}
        onConfirm={handleConfirmDelete}
      />
    </>
  );
}

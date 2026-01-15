import React, { useEffect, useMemo, useRef, useState } from "react";
import { Download, ExternalLink } from "lucide-react";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { FormField } from "../../components/ui/form-field";
import { LoadingEllipsis } from "../../components/ui/loading-ellipsis";
import { SelectDropdown } from "../../components/ui/select-dropdown";
import * as mockupApi from "../../api/mockup";
import { cn, normalizeFrameConfig } from "../../lib/utils";

function useGenerateActions({
  locations,
  timeOfDay,
  side,
  templateOptions,
  getTemplateKey,
  defaultFrameConfig,
  templateKey: externalTemplateKey,
  setTemplateKey: externalSetTemplateKey,
  venueType,
  timeOfDayDisabled,
  locationOptions,
}) {
  const [internalTemplateKey, setInternalTemplateKey] = useState("");
  const templateKey = externalTemplateKey ?? internalTemplateKey;
  const setTemplateKey = externalSetTemplateKey ?? setInternalTemplateKey;
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [genFrameConfig, setGenFrameConfig] = useState(defaultFrameConfig);
  const [aiPrompt, setAiPrompt] = useState("");
  const [creativeFiles, setCreativeFiles] = useState([]);
  const [creativeDragActive, setCreativeDragActive] = useState(false);
  const [lastResults, setLastResults] = useState([]);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState("");
  const resultsRef = React.useRef([]);

  const templateMap = useMemo(() => {
    const map = new Map();
    templateOptions.forEach((t) => {
      map.set(getTemplateKey(t), t);
    });
    return map;
  }, [getTemplateKey, templateOptions]);

  const locationNameMap = useMemo(() => {
    const map = new Map();
    (locationOptions || []).forEach((loc) => {
      const key = loc?.location_key ?? loc?.key ?? loc?.id ?? loc?.value ?? loc;
      if (!key) return;
      const label = loc?.display_name ?? loc?.name ?? loc?.label ?? key;
      map.set(String(key), label);
    });
    return map;
  }, [locationOptions]);

  const locationLabel = useMemo(() => {
    if (!locations.length) return "";
    return locations
      .map((loc) => locationNameMap.get(String(loc)) || loc)
      .filter(Boolean)
      .join(", ");
  }, [locationNameMap, locations]);

  const templateFrameCount = selectedTemplate?.frame_count || 0;
  const multiCreativeCount = creativeFiles.length > 1;
  const requiresTemplate = multiCreativeCount && !selectedTemplate;
  const creativeCountMismatch =
    multiCreativeCount && templateFrameCount && creativeFiles.length !== templateFrameCount;
  const multiCreativeError = requiresTemplate
    ? "Select a template to map multiple creatives to frames."
    : creativeCountMismatch
      ? `Upload exactly ${templateFrameCount} creatives to match the template frames.`
      : "";

  const canGenerate =
    locations.length && (creativeFiles.length || aiPrompt.trim()) && !generating && !multiCreativeError;

  useEffect(() => {
    if (!templateKey) {
      setSelectedTemplate(null);
      setGenFrameConfig(defaultFrameConfig);
      return;
    }

    const template = templateMap.get(templateKey);
    if (!template) {
      setSelectedTemplate(null);
      setGenFrameConfig(defaultFrameConfig);
      return;
    }

    setSelectedTemplate(template);
    setGenFrameConfig(normalizeFrameConfig(template.config, defaultFrameConfig));
  }, [defaultFrameConfig, templateKey, templateMap]);

  useEffect(() => {
    if (templateKey) setTemplateKey("");
  }, [side, timeOfDay, locations, venueType, timeOfDayDisabled]);

  useEffect(() => {
    resultsRef.current = lastResults;
  }, [lastResults]);

  useEffect(() => {
    return () => {
      revokeResultUrls(resultsRef.current);
    };
  }, []);

  async function onGenerate() {
    if (!canGenerate) return;
    setGenerateError("");
    try {
      setGenerating(true);
      const formData = new FormData();
      const resolvedTimeOfDay = timeOfDayDisabled ? "all" : timeOfDay;
      formData.append("location_key", locations[0] || "");
      formData.append("location_keys", JSON.stringify(locations));
      formData.append("venue_type", venueType);

      if (selectedTemplate) {
        formData.append("time_of_day", selectedTemplate.time_of_day || resolvedTimeOfDay || "all");
        formData.append("side", selectedTemplate.side || side || "all");
        formData.append("specific_photo", selectedTemplate.photo);
        formData.append("frame_config", JSON.stringify(genFrameConfig));
      } else {
        formData.append("time_of_day", resolvedTimeOfDay || "all");
        formData.append("side", side || "all");
      }

      if (aiPrompt.trim()) {
        formData.append("ai_prompt", aiPrompt.trim());
      } else if (creativeFiles.length) {
        creativeFiles.forEach((entry) => formData.append("creative", entry.file));
      }

      const response = await mockupApi.generateMockup(formData);
      const images = await normalizeGeneratedImages(response, locationLabel);
      const run = {
        id: crypto.randomUUID(),
        location: locationLabel,
        images,
      };
      setLastResults((prev) => {
        return [run, ...prev];
      });
    } catch (error) {
      setGenerateError(error?.message || "Unable to generate mockup.");
    } finally {
      setGenerating(false);
    }
  }

  return {
    templateKey,
    setTemplateKey,
    aiPrompt,
    setAiPrompt,
    creativeFiles,
    setCreativeFiles,
    creativeDragActive,
    setCreativeDragActive,
    multiCreativeError,
    selectedTemplate,
    lastResults,
    generating,
    generateError,
    setGenerateError,
    onGenerate,
    canGenerate,
  };
}

export function GeneratePanel(props) {
  const state = useGenerateActions(props);
  return <GenerateTab {...props} {...state} />;
}

export function GenerateTab({
  locations,
  setLocations,
  venueType,
  setVenueType,
  setTemplateKey,
  locationOptions,
  locationsQuery,
  timeOfDay,
  setTimeOfDay,
  timeOfDayDisabled,
  sideDisabled,
  side,
  setSide,
  timeOfDayOptions,
  sideOptions,
  venueTypeOptions,
  templateKey,
  templateOptions,
  templatesQuery,
  templateThumbs,
  getTemplateKey,
  setCreativeFiles,
  creativeFiles,
  creativeDragActive,
  setCreativeDragActive,
  multiCreativeError,
  selectedTemplate,
  aiPrompt,
  setAiPrompt,
  generateError,
  setGenerateError,
  generating,
  onGenerate,
  canGenerate,
  lastResults,
  useNativeSelects,
}) {
  const locationSelectOptions = useMemo(
    () =>
      locationOptions.map((loc) => {
        const value = loc?.key ?? loc?.id ?? loc?.value ?? loc;
        const label = loc?.name ?? loc?.label ?? value;
        return { value, label };
      }),
    [locationOptions]
  );

  const frameCountHint = selectedTemplate?.frame_count;
  const sessionImages = useMemo(
    () =>
      lastResults.flatMap((entry) =>
        (entry.images || []).map((image, idx) => ({
          entryId: entry.id,
          location: entry.location,
          image,
          index: idx,
        }))
      ),
    [lastResults]
  );

  function handleCreativeFiles(files) {
    const list = Array.from(files || []).filter(Boolean);
    if (!list.length) return;
    setCreativeFiles((prev) => {
      const next = [...prev];
      list.forEach((file) => {
        const exists = next.some(
          (existing) =>
            existing.file.name === file.name &&
            existing.file.size === file.size &&
            existing.file.lastModified === file.lastModified
        );
        if (!exists) {
          next.push({
            id: crypto.randomUUID(),
            file,
          });
        }
      });
      return next;
    });
    setAiPrompt("");
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
    handleCreativeFiles(event.dataTransfer?.files);
  }

  function removeCreativeFile(id) {
    setCreativeFiles((prev) => prev.filter((entry) => entry.id !== id));
  }

  function clearCreativeFiles() {
    setCreativeFiles([]);
  }

  function handleAiPromptChange(value) {
    setAiPrompt(value);
    if (value.trim()) {
      setCreativeFiles([]);
    }
  }

  function resetForm() {
    setLocations([]);
    setVenueType("all");
    setTimeOfDay("all");
    setSide("all");
    setTemplateKey("");
    setCreativeFiles([]);
    setAiPrompt("");
    setGenerateError("");
  }

  const creativeInputRef = useRef(null);

  return (
    <Card className="h-full flex flex-col">
          <CardHeader>
            <CardTitle>Mockup Generator</CardTitle>
          </CardHeader>
          <CardContent className="flex-1 min-h-0 overflow-y-auto space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <FormField label="Location">
            <SelectDropdown
              value={locations[0] || ""}
              options={locationSelectOptions}
              placeholder="Select a location"
              onChange={(nextValue) => {
                setLocations(nextValue ? [nextValue] : []);
                setVenueType("all");
                setTimeOfDay("all");
                setSide("all");
                setTemplateKey("");
              }}
              useNativeSelect={useNativeSelects}
            />
            {locationsQuery.isLoading ? (
              <div className="mt-1 text-xs text-black/50 dark:text-white/60">
                <LoadingEllipsis text="Loading locations" />
              </div>
            ) : null}
          </FormField>

          <FormField label="Venue Type">
            <SelectDropdown
              value={venueType}
              options={venueTypeOptions}
              onChange={(nextValue) => setVenueType(nextValue)}
              useNativeSelect={useNativeSelects}
            />
          </FormField>

          {!timeOfDayDisabled && (
            <FormField label="Time of Day">
              <SelectDropdown
                value={timeOfDay}
                options={timeOfDayOptions}
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
                onChange={(nextValue) => setSide(nextValue)}
                useNativeSelect={useNativeSelects}
              />
            </FormField>
          )}
        </div>

        {locations.length ? (
          <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-white/40 dark:bg-white/5 p-4 shadow-soft space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-sm font-semibold text-black/80 dark:text-white/85">Templates (optional)</div>
                <div className="text-xs text-black/55 dark:text-white/60">Select a template or keep random.</div>
              </div>
              {templateKey ? (
                <Button variant="ghost" size="sm" className="rounded-xl" onClick={() => setTemplateKey("")}>
                  Use random
                </Button>
              ) : null}
            </div>
            {templatesQuery.isLoading ? (
              <LoadingEllipsis text="Loading templates" className="text-sm text-black/60 dark:text-white/65" />
            ) : null}
            {!templatesQuery.isLoading && !templateOptions.length ? (
              <div className="text-sm text-black/60 dark:text-white/65">No templates for this selection.</div>
            ) : null}
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-2">
              {templateOptions.map((t) => {
                const key = getTemplateKey(t);
                const isSelected = key === templateKey;
                const thumb = templateThumbs[key];
                return (
                  <div
                    key={key}
                    className={cn(
                      "rounded-xl border border-black/5 dark:border-white/10 bg-white/60 dark:bg-white/5 p-3 text-left text-sm transition flex flex-col",
                      isSelected ? "border-2" : "hover:bg-black/5 dark:hover:bg-white/10"
                    )}
                    style={
                      isSelected
                        ? {
                            borderColor: "rgb(var(--brand-accent) / 0.6)",
                            boxShadow: "0 0 0 1px rgb(var(--brand-accent) / 0.25)",
                          }
                        : undefined
                    }
                  >
                    <button type="button" onClick={() => setTemplateKey(key)} className="text-left flex flex-col flex-1">
                      <div className="overflow-hidden rounded-lg border border-black/5 dark:border-white/10 bg-black/5">
                        {thumb ? (
                          <img src={thumb} alt={t.photo} className="w-full h-40 object-cover" loading="lazy" />
                        ) : (
                          <div className="h-40 grid place-items-center text-xs text-black/50 dark:text-white/60">
                            <LoadingEllipsis text="Loading" className="text-xs text-black/50 dark:text-white/60" />
                          </div>
                        )}
                      </div>
                    </button>
                    <div className="pt-2">
                      {thumb ? (
                        <Button variant="secondary" size="sm" className="w-full rounded-xl" asChild>
                          <a href={thumb} target="_blank" rel="noreferrer">
                            <ExternalLink size={16} className="mr-2" />
                            Open
                          </a>
                        </Button>
                      ) : (
                        <Button variant="secondary" size="sm" className="w-full rounded-xl" disabled>
                          Open
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <FormField label="Upload Creative/Ad Image">
            {creativeFiles.length ? (
              <div
                className={`flex items-center justify-between rounded-xl bg-black/5 dark:bg-white/10 px-3 py-2 text-sm min-h-[120px] ${creativeDragActive ? "ring-2 ring-black/20 dark:ring-white/30" : ""}`}
                onDragOver={handleCreativeDragOver}
                onDragLeave={handleCreativeDragLeave}
                onDrop={handleCreativeDrop}
              >
                <div className="w-full space-y-2">
                  {creativeFiles.map((entry) => (
                    <div key={entry.id} className="flex items-center justify-between gap-2">
                      <div className="truncate">{entry.file.name}</div>
                      <button
                        type="button"
                        className="opacity-70 hover:opacity-100"
                        onClick={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          removeCreativeFile(entry.id);
                        }}
                      >
                        x
                      </button>
                    </div>
                  ))}
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-black/50 dark:text-white/60">
                    <span>{creativeFiles.length} file{creativeFiles.length > 1 ? "s" : ""} selected</span>
                    <div className="flex items-center gap-3">
                      <button type="button" className="underline" onClick={() => creativeInputRef.current?.click()}>
                        Add more
                      </button>
                      <button type="button" className="underline" onClick={clearCreativeFiles}>
                        Clear all
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <label
                className={`block cursor-pointer rounded-xl border border-dashed border-black/10 dark:border-white/15 px-4 py-5 text-center text-sm bg-white/50 dark:bg-white/5 min-h-[120px] ${creativeDragActive ? "ring-2 ring-black/20 dark:ring-white/30" : ""}`}
                onDragOver={handleCreativeDragOver}
                onDragLeave={handleCreativeDragLeave}
                onDrop={handleCreativeDrop}
              >
                <input
                  type="file"
                  className="hidden"
                  multiple
                  accept="image/jpeg,image/png,image/webp,image/gif"
                  onChange={(e) => {
                    handleCreativeFiles(e.target.files);
                    e.target.value = "";
                  }}
                />
                <div className="font-semibold mb-1">Click to upload/ Drag and Drop an Image</div>
                <div className="text-xs text-black/55 dark:text-white/60">
                  JPG, PNG, WEBP, GIF up to 10MB each
                </div>
              </label>
            )}
            <input
              ref={creativeInputRef}
              type="file"
              multiple
              accept="image/jpeg,image/png,image/webp,image/gif"
              className="hidden"
              onChange={(e) => {
                handleCreativeFiles(e.target.files);
                e.target.value = "";
              }}
            />
            <div className="mt-2 text-xs text-black/55 dark:text-white/60">
              {frameCountHint && frameCountHint > 1
                ? `Upload 1 image to reuse across ${frameCountHint} frames, or upload exactly ${frameCountHint} images (one per frame).`
                : frameCountHint === 1
                  ? "Upload 1 image."
                  : "Upload 1 image to reuse across frames, or select a template to upload multiple images."}
            </div>
            {multiCreativeError ? (
              <div className="mt-2 text-xs text-red-600 dark:text-red-300">{multiCreativeError}</div>
            ) : null}
          </FormField>

          <FormField label="Or use AI prompt">
            <textarea
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/10 dark:focus:ring-white/15 min-h-[120px]"
              value={aiPrompt}
              onChange={(e) => handleAiPromptChange(e.target.value)}
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
            {generating ? <LoadingEllipsis text="Generating Mockup" /> : "Generate Mockup"}
          </Button>
          <Button variant="secondary" className="rounded-2xl" onClick={resetForm} disabled={generating}>
            Reset
          </Button>
        </div>

        <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-white/40 dark:bg-white/5 p-4">
          {!lastResults.length && !generating ? (
            <div className="text-sm text-black/60 dark:text-white/65">Result will appear here</div>
          ) : null}
          {generating ? (
            <LoadingEllipsis text="Processing mockup" className="text-sm text-black/60 dark:text-white/65" />
          ) : null}
          {lastResults.length ? (
            <div className="space-y-4">
              <div className="text-sm font-semibold text-black/80 dark:text-white/85">
                Mockups generated this session
              </div>
              {sessionImages.length ? (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-2">
                  {sessionImages.map((entry) => (
                    <div
                      key={`${entry.entryId}-img-${entry.index}`}
                      className="rounded-xl border border-black/5 dark:border-white/10 bg-white/60 dark:bg-white/5 p-3 text-sm transition flex flex-col"
                    >
                      <a
                        href={entry.image.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="overflow-hidden rounded-lg border border-black/5 dark:border-white/10 bg-black/5"
                      >
                        <img
                          src={entry.image.url}
                          alt={entry.image.label || "Generated mockup"}
                          className="w-full h-40 object-cover"
                          loading="lazy"
                        />
                      </a>
                      <div className="mt-2 space-y-2">
                        {entry.location ? (
                          <div className="text-xs text-black/55 dark:text-white/60 truncate">
                            {entry.location}
                          </div>
                        ) : null}
                        <div className="flex items-center gap-2">
                          <Button asChild size="sm" variant="ghost" className="rounded-xl">
                            <a href={entry.image.url} target="_blank" rel="noopener noreferrer">
                              <ExternalLink size={14} className="mr-1" />
                              Open
                            </a>
                          </Button>
                          <Button size="sm" variant="secondary" className="rounded-xl">
                            <span
                              role="link"
                              tabIndex={0}
                              onClick={(event) => {
                                event.preventDefault();
                                downloadFile(entry.image.url, entry.image.filename);
                              }}
                              onKeyDown={(event) => {
                                if (event.key === "Enter" || event.key === " ") {
                                  event.preventDefault();
                                  downloadFile(entry.image.url, entry.image.filename);
                                }
                              }}
                              className="inline-flex items-center"
                            >
                              <Download size={14} className="mr-1" />
                              Download
                            </span>
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-xs text-black/55 dark:text-white/60">No images returned yet.</div>
              )}
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function isBlob(value) {
  return typeof Blob !== "undefined" && value instanceof Blob;
}

async function normalizeGeneratedImages(response, locationLabel) {
  if (!response) return [];
  if (response instanceof Response) {
    const blob = await response.blob();
    return blob ? [buildImageEntry(blob, locationLabel, 1)] : [];
  }
  if (isBlob(response)) {
    return [buildImageEntry(response, locationLabel, 1)];
  }

  const payload = response;
  const list =
    payload?.images ||
    payload?.image_urls ||
    payload?.urls ||
    payload?.results ||
    payload?.files ||
    payload?.data ||
    null;
  const images = Array.isArray(list) ? list : payload?.url ? [payload.url] : [];
  if (!images.length) return [];

  return images.map((entry, index) => {
    if (typeof entry === "string") {
      return buildUrlEntry(entry, locationLabel, index + 1);
    }
    if (isBlob(entry)) {
      return buildImageEntry(entry, locationLabel, index + 1);
    }
    const url = entry?.url || entry?.image_url || entry?.file_url || "";
    return buildUrlEntry(url, locationLabel, index + 1);
  });
}

function buildImageEntry(blob, locationLabel, index) {
  const url = URL.createObjectURL(blob);
  const filename = buildDownloadName(url, locationLabel, index);
  return { url, filename };
}

function buildUrlEntry(url, locationLabel, index) {
  if (!url) return { url: "", filename: buildDownloadName("", locationLabel, index) };
  return { url, filename: buildDownloadName(url, locationLabel, index) };
}

function buildDownloadName(url, locationLabel, index) {
  const fromUrl = getNameFromUrl(url);
  if (fromUrl) return fromUrl;
  const safeLocation = (locationLabel || "result")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  const suffix = index ? `_${index}` : "";
  return `mockup_${safeLocation || "result"}${suffix}.jpg`;
}

function getNameFromUrl(url) {
  if (!url) return "";
  try {
    const resolved = new URL(url, window.location.href);
    const parts = resolved.pathname.split("/").filter(Boolean);
    return parts.length ? decodeURIComponent(parts[parts.length - 1]) : "";
  } catch {
    const fallback = url.split("?")[0].split("#")[0];
    const parts = fallback.split("/").filter(Boolean);
    return parts.length ? decodeURIComponent(parts[parts.length - 1]) : "";
  }
}

function revokeResultUrls(results) {
  const list = Array.isArray(results) ? results : [];
  list.forEach((result) => {
    (result?.images || []).forEach((image) => {
      if (image?.url?.startsWith("blob:")) {
        URL.revokeObjectURL(image.url);
      }
    });
  });
}

async function downloadFile(url, filename) {
  const res = await fetch(url);
  const blob = await res.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename || "download";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

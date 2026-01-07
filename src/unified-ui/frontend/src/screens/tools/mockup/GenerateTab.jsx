import React, { useEffect, useMemo, useState } from "react";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { FormField } from "../../../components/ui/form-field";
import { LoadingEllipsis } from "../../../components/ui/loading-ellipsis";
import * as mockupApi from "../../../api/mockup";
import { cn, normalizeFrameConfig } from "../../../lib/utils";

function useGenerateActions({
  location,
  timeOfDay,
  finish,
  templateOptions,
  getTemplateKey,
  defaultFrameConfig,
  templateKey: externalTemplateKey,
  setTemplateKey: externalSetTemplateKey,
}) {
  const [internalTemplateKey, setInternalTemplateKey] = useState("");
  const templateKey = externalTemplateKey ?? internalTemplateKey;
  const setTemplateKey = externalSetTemplateKey ?? setInternalTemplateKey;
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [genFrameConfig, setGenFrameConfig] = useState(defaultFrameConfig);
  const [aiPrompt, setAiPrompt] = useState("");
  const [creativeFile, setCreativeFile] = useState(null);
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

  const canGenerate = location && (creativeFile || aiPrompt.trim()) && !generating;

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
  }, [finish, timeOfDay]);

  useEffect(() => {
    resultsRef.current = lastResults;
  }, [lastResults]);

  useEffect(() => {
    return () => {
      resultsRef.current.forEach((entry) => {
        if (entry?.url) URL.revokeObjectURL(entry.url);
      });
    };
  }, []);

  async function onGenerate() {
    if (!canGenerate) return;
    setGenerateError("");
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
      setLastResults((prev) => {
        const next = [{ url, location }, ...prev];
        if (next.length > 3) {
          const removed = next.pop();
          if (removed?.url) URL.revokeObjectURL(removed.url);
        }
        return next;
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
    creativeFile,
    setCreativeFile,
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
  location,
  setLocation,
  setTemplateKey,
  locationOptions,
  locationsQuery,
  timeOfDay,
  setTimeOfDay,
  finish,
  setFinish,
  timeOfDayOptions,
  finishOptions,
  templateKey,
  templateOptions,
  templatesQuery,
  templateThumbs,
  getTemplateKey,
  creativeFile,
  setCreativeFile,
  creativeDragActive,
  handleCreativeDragOver,
  handleCreativeDragLeave,
  handleCreativeDrop,
  aiPrompt,
  setAiPrompt,
  generateError,
  setGenerateError,
  generating,
  onGenerate,
  canGenerate,
  lastResults,
}) {
  function resetForm() {
    setLocation("");
    setTimeOfDay("all");
    setFinish("all");
    setTemplateKey("");
    setCreativeFile(null);
    setAiPrompt("");
    setGenerateError("");
  }

  return (
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
              <option value="">Select a location</option>
              {locationOptions.map((loc) => (
                <option key={loc.key} value={loc.key}>
                  {loc.name}
                </option>
              ))}
            </select>
            {locationsQuery.isLoading ? (
              <div className="mt-1 text-xs text-black/50 dark:text-white/60">
                <LoadingEllipsis text="Loading locations" />
              </div>
            ) : null}
          </FormField>

          <FormField label="Time of Day">
            <select
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={timeOfDay}
              onChange={(e) => setTimeOfDay(e.target.value)}
            >
              {timeOfDayOptions.map((opt) => (
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
              {finishOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </FormField>
        </div>

        {location ? (
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
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setTemplateKey(key)}
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
                    <div className="overflow-hidden rounded-lg border border-black/5 dark:border-white/10 bg-black/5">
                      {templateThumbs[key] ? (
                        <img
                          src={templateThumbs[key]}
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
                    <div className="mt-auto pt-2 space-y-1">
                      <div className="font-semibold truncate">{t.photo}</div>
                      <div className="text-xs text-black/55 dark:text-white/60">
                        {t.time_of_day}/{t.finish} - {t.frame_count} frame
                        {t.frame_count > 1 ? "s" : ""}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <FormField label="Upload Creative/Ad Image">
            {creativeFile ? (
              <div
                className={`flex items-center justify-between rounded-xl bg-black/5 dark:bg-white/10 px-3 py-2 text-sm min-h-[120px] ${creativeDragActive ? "ring-2 ring-black/20 dark:ring-white/30" : ""}`}
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
                className={`block cursor-pointer rounded-xl border border-dashed border-black/10 dark:border-white/15 px-4 py-5 text-center text-sm bg-white/50 dark:bg-white/5 min-h-[120px] ${creativeDragActive ? "ring-2 ring-black/20 dark:ring-white/30" : ""}`}
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
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/10 dark:focus:ring-white/15 min-h-[120px]"
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
            <div className="space-y-3">
              <div className="text-sm font-semibold text-black/80 dark:text-white/85">
                Last 3 Generated Mockups
              </div>
              {lastResults.map((entry, index) => (
                <div key={`mockup-result-${index}`} className="space-y-3">
                  <img
                    src={entry.url}
                    alt="Generated mockup"
                    className="w-full rounded-xl border border-black/5 dark:border-white/10"
                  />
                  <div className="flex gap-2">
                    <a
                      href={entry.url}
                      download={`mockup_${entry.location || "result"}.jpg`}
                      className="inline-flex items-center justify-center rounded-2xl bg-black text-white px-4 py-2 text-sm dark:bg-white dark:text-black"
                    >
                      Download
                    </a>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

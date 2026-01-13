import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";

// Service toggle definitions
const SERVICE_TOGGLES = [
  { key: "chat", label: "AI Chat", description: "Chat assistant for general queries" },
  { key: "video_critique", label: "Video Critique", description: "AI-powered video analysis tool" },
  { key: "proposals", label: "Proposals", description: "Proposal generation and management" },
  { key: "asset_management", label: "Asset Management", description: "Digital asset management system" },
];

const MOCKUP_TOGGLES = [
  { key: "mockup_setup", label: "Mockup Setup", description: "Configure and upload mockup templates" },
  { key: "mockup_generate", label: "Mockup Generate", description: "Generate mockups from templates" },
];

export function ServicesTab({ isInitializing, isDevMode, serviceVisibility, isUpdating, onToggleService }) {
  return (
    <Card className="h-full min-h-0 flex flex-col">
      <CardHeader className="pb-2">
        <CardTitle className="text-lg">Service Visibility</CardTitle>
        <p className="text-sm text-black/60 dark:text-white/65">
          Toggle which services are visible to users in the sidebar. Admin and Settings are always visible.
        </p>
      </CardHeader>
      <CardContent className="flex-1 min-h-0 overflow-y-auto space-y-6">
        {isInitializing ? (
          <div className="space-y-6 animate-pulse">
            {/* Skeleton for General Services */}
            <div className="space-y-3">
              <div className="h-4 w-28 bg-black/10 dark:bg-white/10 rounded" />
              <div className="grid gap-3">
                {[1, 2, 3, 4].map((i) => (
                  <div
                    key={i}
                    className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between rounded-xl bg-black/[0.02] dark:bg-white/[0.03] p-3 ring-1 ring-black/5 dark:ring-white/10"
                  >
                    <div className="space-y-2">
                      <div className="h-4 w-24 bg-black/10 dark:bg-white/10 rounded" />
                      <div className="h-3 w-40 bg-black/5 dark:bg-white/5 rounded" />
                    </div>
                    <div className="h-6 w-11 bg-black/10 dark:bg-white/10 rounded-full" />
                  </div>
                ))}
              </div>
            </div>
            {/* Skeleton for Mockup Services */}
            <div className="space-y-3">
              <div className="h-4 w-28 bg-black/10 dark:bg-white/10 rounded" />
              <div className="grid gap-3">
                {[1, 2].map((i) => (
                  <div
                    key={i}
                    className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between rounded-xl bg-black/[0.02] dark:bg-white/[0.03] p-3 ring-1 ring-black/5 dark:ring-white/10"
                  >
                    <div className="space-y-2">
                      <div className="h-4 w-24 bg-black/10 dark:bg-white/10 rounded" />
                      <div className="h-3 w-40 bg-black/5 dark:bg-white/5 rounded" />
                    </div>
                    <div className="h-6 w-11 bg-black/10 dark:bg-white/10 rounded-full" />
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <>
            {/* Dev Mode Banner */}
            {isDevMode && (
              <div className="rounded-xl bg-amber-500/10 border border-amber-500/30 p-3 mb-4">
                <div className="flex items-center gap-2">
                  <span className="text-amber-600 dark:text-amber-400 font-medium text-sm">Dev Mode Active</span>
                </div>
                <p className="text-xs text-amber-600/80 dark:text-amber-400/80 mt-1">
                  All services are forced visible. Running with{" "}
                  <code className="bg-amber-500/20 px-1 rounded">--dev-all-services</code> flag. Toggles are disabled in
                  this mode.
                </p>
              </div>
            )}

            {/* General Services */}
            <div className="space-y-3">
              <h3 className="text-sm font-medium text-black/70 dark:text-white/75">General Services</h3>
              <div className="grid gap-3">
                {SERVICE_TOGGLES.map((service) => (
                  <ServiceToggle
                    key={service.key}
                    label={service.label}
                    description={service.description}
                    enabled={serviceVisibility[service.key] === true}
                    onChange={() => onToggleService(service.key, serviceVisibility[service.key])}
                    disabled={isDevMode || isUpdating}
                  />
                ))}
              </div>
            </div>

            {/* Mockup Services */}
            <div className="space-y-3">
              <h3 className="text-sm font-medium text-black/70 dark:text-white/75">Mockup Services</h3>
              <p className="text-xs text-black/50 dark:text-white/50">
                If both are disabled, the Mockup service will be hidden entirely.
              </p>
              <div className="grid gap-3">
                {MOCKUP_TOGGLES.map((service) => (
                  <ServiceToggle
                    key={service.key}
                    label={service.label}
                    description={service.description}
                    enabled={serviceVisibility[service.key] === true}
                    onChange={() => onToggleService(service.key, serviceVisibility[service.key])}
                    disabled={isDevMode || isUpdating}
                  />
                ))}
              </div>
            </div>

            {/* Always Visible Notice */}
            <div className="pt-4 border-t border-black/10 dark:border-white/10">
              <p className="text-xs text-black/50 dark:text-white/50">
                <strong>Always visible:</strong> Admin (for admins only), Settings
              </p>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function ServiceToggle({ label, description, enabled, onChange, disabled }) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between rounded-xl bg-black/[0.02] dark:bg-white/[0.03] p-3 ring-1 ring-black/5 dark:ring-white/10">
      <div className="flex-1 min-w-0 sm:mr-4">
        <div className="text-sm font-medium">{label}</div>
        <div className="text-xs text-black/50 dark:text-white/50 break-words sm:truncate">{description}</div>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        disabled={disabled}
        onClick={onChange}
        className={[
          "relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent self-start sm:self-auto",
          "transition-all duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-black/20",
          enabled ? "bg-green-500" : "bg-black/20 dark:bg-white/20",
          disabled ? "opacity-50 cursor-not-allowed" : "",
        ].join(" ")}
      >
        <span
          className={[
            "pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-lg ring-0",
            "transition-transform duration-200 ease-in-out",
            enabled ? "translate-x-5" : "translate-x-0",
          ].join(" ")}
        />
      </button>
    </div>
  );
}

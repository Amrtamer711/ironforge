import React, { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { ThemeToggle } from "../components/ThemeToggle";
import { SoftCard } from "../components/ui/soft-card";

export function SettingsPage() {
  const BRAND_KEY = "mmg-brand-theme";
  const [brandTheme, setBrandTheme] = useState("none");

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(BRAND_KEY);
    const initial = stored || "none";
    setBrandTheme(initial);
    if (initial === "none") {
      document.body.removeAttribute("data-brand-theme");
    } else {
      document.body.setAttribute("data-brand-theme", initial);
    }
  }, []);

  const handleBrandChange = (value) => {
    setBrandTheme(value);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(BRAND_KEY, value);
    }
    if (value === "none") {
      document.body.removeAttribute("data-brand-theme");
    } else {
      document.body.setAttribute("data-brand-theme", value);
    }
  };

  return (
    <div className="h-full min-h-0">
      <Card className="h-full min-h-0 flex flex-col">
        <CardHeader>
          <CardTitle>Settings</CardTitle>
        </CardHeader>
        <CardContent className="flex-1 min-h-0 overflow-y-auto pt-1 text-sm text-black/60 dark:text-white/65 space-y-4">
          <SoftCard className="flex items-center justify-between p-4">
            <div>
              <div className="font-semibold text-black/80 dark:text-white/85">Theme</div>
              <div className="text-sm text-black/60 dark:text-white/65">Toggle dark / light mode</div>
            </div>
            <ThemeToggle />
          </SoftCard>

          <SoftCard className="space-y-3 p-4">
            <div className="flex items-center justify-between gap-4">
              <div>
                <div className="font-semibold text-black/80 dark:text-white/85">
                  Color theme
                </div>
                <div className="text-sm text-black/60 dark:text-white/65">
                  Choose a color palette that layers on top of light / dark mode.
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-2">
              <button
                type="button"
                onClick={() => handleBrandChange("none")}
                className={`flex items-center justify-between rounded-2xl border px-3 py-2 text-left text-sm transition-colors ${
                  brandTheme === "none"
                    ? "border-black/60 dark:border-white/80 bg-black/5 dark:bg-white/10"
                    : "border-black/10 dark:border-white/15 hover:bg-black/3 dark:hover:bg-white/5"
                }`}
              >
                <span className="font-medium">System default</span>
              </button>

              <button
                type="button"
                onClick={() => handleBrandChange("blue")}
                className={`flex items-center justify-between rounded-2xl border px-3 py-2 text-left text-sm transition-colors ${
                  brandTheme === "blue"
                    ? "border-blue-500/80 bg-blue-500/5"
                    : "border-black/10 dark:border-white/15 hover:bg-black/3 dark:hover:bg-white/5"
                }`}
              >
                <span className="font-medium">Blue</span>
                <span className="flex h-5 w-5 rounded-full bg-[#007AFF]" />
              </button>

              <button
                type="button"
                onClick={() => handleBrandChange("green")}
                className={`flex items-center justify-between rounded-2xl border px-3 py-2 text-left text-sm transition-colors ${
                  brandTheme === "green"
                    ? "border-emerald-500/80 bg-emerald-500/5"
                    : "border-black/10 dark:border-white/15 hover:bg-black/3 dark:hover:bg-white/5"
                }`}
              >
                <span className="font-medium">Green</span>
                <span className="flex h-5 w-5 rounded-full bg-[#0F806B]" />
              </button>

              <button
                type="button"
                onClick={() => handleBrandChange("orange")}
                className={`flex items-center justify-between rounded-2xl border px-3 py-2 text-left text-sm transition-colors ${
                  brandTheme === "orange"
                    ? "border-orange-500/80 bg-orange-500/5"
                    : "border-black/10 dark:border-white/15 hover:bg-black/3 dark:hover:bg-white/5"
                }`}
              >
                <span className="font-medium">Orange</span>
                <span className="flex h-5 w-5 rounded-full bg-[#FF7900]" />
              </button>

              <button
                type="button"
                onClick={() => handleBrandChange("gold")}
                className={`flex items-center justify-between rounded-2xl border px-3 py-2 text-left text-sm transition-colors ${
                  brandTheme === "gold"
                    ? "border-amber-500/80 bg-amber-500/5"
                    : "border-black/10 dark:border-white/15 hover:bg-black/3 dark:hover:bg-white/5"
                }`}
              >
                <span className="font-medium">Gold</span>
                <span className="flex h-5 w-5 rounded-full bg-[#CA9E2C]" />
              </button>

              <button
                type="button"
                onClick={() => handleBrandChange("brand")}
                className={`flex items-center justify-between rounded-2xl border px-3 py-2 text-left text-sm transition-colors ${
                  brandTheme === "brand"
                    ? "border-black/70 dark:border-white/80 bg-black/5 dark:bg-white/10"
                    : "border-black/10 dark:border-white/15 hover:bg-black/3 dark:hover:bg-white/5"
                }`}
              >
                <span className="font-medium">Brand Theme</span>
                <span className="flex items-center gap-1">
                  <span className="h-4 w-4 rounded-full bg-[#000000]" />
                  <span className="h-4 w-4 rounded-full bg-[#007AFF]" />
                  <span className="h-4 w-4 rounded-full bg-[#CA9E2C]" />
                </span>
              </button>
            </div>
          </SoftCard>
        </CardContent>
      </Card>
    </div>
  );
}

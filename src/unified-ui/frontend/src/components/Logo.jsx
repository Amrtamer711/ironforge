import React from "react";

export function Logo({ size = 128 }) {
  return (
    <div className="flex items-center gap-2">
      {/* Uses /public/logo.svg; we invert in light mode so white SVG appears black, and keep it white in dark mode */}
      <img
        src="/logo.svg"
        width={size}
        height={size}
        alt="Unified UI"
        className="shrink-0 filter invert dark:invert-0"
      />
      <span className="font-semibold align-text-bottom tracking-tight hidden sm:inline-flex">
        Unified UI
      </span>
    </div>
  );
}


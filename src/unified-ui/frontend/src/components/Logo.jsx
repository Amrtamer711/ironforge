import React from "react";

export function Logo({ size = 128 }) {
  return (
    <div className="flex items-end gap-2">
      {/* Uses /public/logo.svg; we invert in light mode so white SVG appears black, and keep it white in dark mode */}
      <img
        src="/logo.svg"
        width={size}
        height={size}
        alt=""
        className="shrink-0 filter invert dark:invert-0"
      />
      <span className="mmg-brand-gold font-semibold text-lg leading-none tracking-tight hidden sm:inline-flex">
        Nova
      </span>
    </div>
  );
}

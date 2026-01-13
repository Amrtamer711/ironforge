import React from "react";

export function Logo({ size = 128 }) {
  return (
    <div className="flex items-end gap-2">
      <img
        src="/MMG_Logo_Blk.png"
        width={size}
        height={size}
        alt="MMG"
        className="shrink-0 dark:hidden"
      />
      <img
        src="/MMG_Logo.png"
        width={size}
        height={size}
        alt="MMG"
        className="shrink-0 hidden dark:block"
      />
      <span className="mmg-brand-gold font-semibold text-lg leading-none tracking-tight hidden sm:inline-flex">
        Nova
      </span>
    </div>
  );
}

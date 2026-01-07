import React from "react";
import { cn } from "../../lib/utils";

export function SearchInput({ className, placeholder = "Search...", ...props }) {
  return (
    <input
      type="text"
      placeholder={placeholder}
      className={cn(
        "rounded-2xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none",
        className
      )}
      {...props}
    />
  );
}

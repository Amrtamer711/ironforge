import React from "react";
import { cn } from "../../lib/utils";

export function SoftCard({ className, ...props }) {
  return (
    <div
      className={cn(
        "rounded-2xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 shadow-soft",
        className
      )}
      {...props}
    />
  );
}

export const SurfaceCard = SoftCard;

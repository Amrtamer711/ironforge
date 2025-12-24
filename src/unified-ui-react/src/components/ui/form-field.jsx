import React from "react";
import { cn } from "../../lib/utils";

export function FormField({ label, children, className, labelClassName, withGap = true }) {
  return (
    <label className={cn("block", withGap && "space-y-1", className)}>
      <div className={cn("text-xs font-semibold text-black/60 dark:text-white/65", labelClassName)}>
        {label}
      </div>
      {children}
    </label>
  );
}

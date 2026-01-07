import React, { useMemo } from "react";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "../../lib/utils";
import { DropdownMenuItem } from "./dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "./popover";

function formatSelection(labels, placeholder, maxLabelCount) {
  if (!labels.length) return placeholder;
  if (labels.length <= maxLabelCount) return labels.join(", ");
  return `${labels.slice(0, maxLabelCount).join(", ")} +${labels.length - maxLabelCount}`;
}

export function MultiSelect({
  value = [],
  options = [],
  onChange,
  placeholder = "Select...",
  disabled = false,
  maxLabelCount = 2,
  className,
  contentClassName,
}) {
  const selectedSet = useMemo(() => new Set(value), [value]);
  const selectedLabels = useMemo(
    () => options.filter((opt) => selectedSet.has(opt.value)).map((opt) => opt.label),
    [options, selectedSet]
  );

  function toggleValue(nextValue) {
    if (disabled) return;
    if (!onChange) return;
    if (selectedSet.has(nextValue)) {
      onChange(value.filter((val) => val !== nextValue));
    } else {
      onChange([...value, nextValue]);
    }
  }

  const displayText = formatSelection(selectedLabels, placeholder, maxLabelCount);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          className={cn(
            "w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none",
            "flex items-center justify-between gap-2 text-left",
            "disabled:opacity-60 disabled:cursor-not-allowed",
            className
          )}
        >
          <span className={cn("truncate", !selectedLabels.length && "text-black/50 dark:text-white/55")}>
            {displayText}
          </span>
          <ChevronDown size={16} className="text-black/50 dark:text-white/60" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className={cn("min-w-[220px]", contentClassName)}>
        <div className="max-h-[240px] overflow-y-auto">
          {options.length ? (
            options.map((opt) => {
              const isSelected = selectedSet.has(opt.value);
              return (
                <DropdownMenuItem
                  key={opt.value}
                  onSelect={(event) => {
                    event.preventDefault();
                    toggleValue(opt.value);
                  }}
                  className="cursor-pointer"
                >
                  <span
                    className={cn(
                      "h-4 w-4 rounded-full flex items-center justify-center transition-colors",
                      isSelected
                        ? "bg-black text-white dark:bg-white dark:text-black shadow-soft"
                        : "bg-black/5 dark:bg-white/10 text-black/40 dark:text-white/40"
                    )}
                  >
                    <Check size={10} className={isSelected ? "opacity-100" : "opacity-0"} />
                  </span>
                  <span className="min-w-0 truncate">{opt.label}</span>
                </DropdownMenuItem>
              );
            })
          ) : (
            <div className="px-3 py-2 text-sm text-black/60 dark:text-white/65">No options available.</div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

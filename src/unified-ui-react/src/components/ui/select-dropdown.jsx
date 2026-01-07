import React, { useMemo } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "../../lib/utils";
import { DropdownMenuItem } from "./dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "./popover";

export function SelectDropdown({
  value = "",
  options = [],
  onChange,
  placeholder = "Select...",
  disabled = false,
  className,
  contentClassName,
  useNativeSelect = false,
}) {
  const selectedOption = useMemo(
    () => options.find((opt) => opt.value === value),
    [options, value]
  );

  if (useNativeSelect) {
    return (
      <select
        className={cn(
          "w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none",
          "disabled:opacity-60 disabled:cursor-not-allowed",
          className
        )}
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        disabled={disabled}
      >
        {placeholder ? (
          <option value="" disabled>
            {placeholder}
          </option>
        ) : null}
        {options.map((opt) => (
          <option key={opt.value} value={opt.value} disabled={opt.disabled}>
            {opt.label}
          </option>
        ))}
      </select>
    );
  }

  if (disabled) {
    return (
      <button
        type="button"
        disabled
        className={cn(
          "w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none",
          "flex items-center justify-between gap-2 text-left",
          "disabled:opacity-60 disabled:cursor-not-allowed",
          className
        )}
      >
        <span className={cn("truncate", !selectedOption && "text-black/50 dark:text-white/55")}>
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <ChevronDown size={16} className="text-black/50 dark:text-white/60" />
      </button>
    );
  }

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
          <span className={cn("truncate", !selectedOption && "text-black/50 dark:text-white/55")}>
            {selectedOption ? selectedOption.label : placeholder}
          </span>
          <ChevronDown size={16} className="text-black/50 dark:text-white/60" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className={cn("min-w-[220px]", contentClassName)}>
        <div className="max-h-[240px] overflow-y-auto space-y-1">
          {options.length ? (
            options.map((opt) => {
              const isSelected = opt.value === value;
              return (
                <DropdownMenuItem
                  key={opt.value}
                  disabled={opt.disabled}
                  onSelect={() => {
                    if (opt.disabled) return;
                    onChange?.(opt.value);
                  }}
                  className={cn(
                    "cursor-pointer gap-0 py-1",
                    isSelected && "bg-black/5 dark:bg-white/10 font-semibold"
                  )}
                >
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

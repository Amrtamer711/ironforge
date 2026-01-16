import React, { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "../../lib/utils";
import { DropdownMenuItem } from "./dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "./popover";

function flattenTree(options, depth = 0, acc = []) {
  options.forEach((opt) => {
    acc.push({ ...opt, depth });
    if (opt.children?.length) {
      flattenTree(opt.children, depth + 1, acc);
    }
  });
  return acc;
}

function findTreeOption(options, value) {
  for (const opt of options) {
    if (opt.value === value) return opt;
    if (opt.children?.length) {
      const found = findTreeOption(opt.children, value);
      if (found) return found;
    }
  }
  return null;
}

export function SelectDropdown({
  value = "",
  options = [],
  treeOptions = [],
  onChange,
  placeholder = "Select...",
  disabled = false,
  className,
  contentClassName,
  useNativeSelect = false,
}) {
  const hasTree = Boolean(treeOptions?.length);
  const ignoreSelectRef = useRef(false);
  const [expandedNodes, setExpandedNodes] = useState(() => new Set());

  const flattenedTreeOptions = useMemo(
    () => (hasTree ? flattenTree(treeOptions) : []),
    [hasTree, treeOptions]
  );

  const selectedOption = useMemo(() => {
    if (hasTree) return findTreeOption(treeOptions, value);
    return options.find((opt) => opt.value === value);
  }, [hasTree, options, treeOptions, value]);

  useEffect(() => {
    if (!hasTree) return;
    const next = new Set();
    const walk = (nodes) => {
      nodes.forEach((opt) => {
        if (opt.children?.length) next.add(opt.value);
        if (opt.children?.length) walk(opt.children);
      });
    };
    walk(treeOptions);
    setExpandedNodes(next);
  }, [hasTree, treeOptions]);

  if (useNativeSelect) {
    const nativeOptions = hasTree ? flattenedTreeOptions : options;
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
        {nativeOptions.map((opt) => {
          const prefix = hasTree && opt.depth ? `${"-".repeat(opt.depth)} ` : "";
          return (
            <option key={opt.value} value={opt.value} disabled={opt.disabled}>
              {prefix}{opt.label}
            </option>
          );
        })}
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
          {hasTree ? (
            treeOptions.length ? (
              treeOptions.map((opt) => {
                const renderTree = (node, depth = 0) => {
                  const isSelected = node.value === value;
                  const hasChildren = Boolean(node.children?.length);
                  const isExpanded = expandedNodes.has(node.value);
                  return (
                    <React.Fragment key={`${node.value}-${depth}`}>
                      <DropdownMenuItem
                        disabled={node.disabled}
                        onSelect={(event) => {
                          if (node.disabled) return;
                          if (ignoreSelectRef.current) {
                            event.preventDefault();
                            ignoreSelectRef.current = false;
                            return;
                          }
                          onChange?.(node.value);
                        }}
                        className={cn(
                          "cursor-pointer gap-0 py-1",
                          isSelected && "bg-black/5 dark:bg-white/10 font-semibold"
                        )}
                      >
                        <div className="flex items-center gap-2 w-full" style={{ paddingLeft: depth * 12 }}>
                          {hasChildren ? (
                            <button
                              type="button"
                              className="text-black/50 dark:text-white/60 hover:text-black/80 dark:hover:text-white/80"
                              onMouseDown={(event) => {
                                event.preventDefault();
                                event.stopPropagation();
                                ignoreSelectRef.current = true;
                              }}
                              onClick={(event) => {
                                event.preventDefault();
                                event.stopPropagation();
                                setExpandedNodes((prev) => {
                                  const next = new Set(prev);
                                  if (next.has(node.value)) {
                                    next.delete(node.value);
                                  } else {
                                    next.add(node.value);
                                  }
                                  return next;
                                });
                              }}
                              aria-label={isExpanded ? "Collapse" : "Expand"}
                            >
                              {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                            </button>
                          ) : (
                            <span className="inline-block w-4" />
                          )}
                          <span className="min-w-0 truncate">{node.label}</span>
                        </div>
                      </DropdownMenuItem>
                      {hasChildren && isExpanded
                        ? node.children.map((child) => renderTree(child, depth + 1))
                        : null}
                    </React.Fragment>
                  );
                };
                return renderTree(opt, 0);
              })
            ) : (
              <div className="px-3 py-2 text-sm text-black/60 dark:text-white/65">No options available.</div>
            )
          ) : options.length ? (
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

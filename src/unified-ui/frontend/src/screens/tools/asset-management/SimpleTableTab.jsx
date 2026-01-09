import React, { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { LoadingEllipsis } from "../../../components/ui/loading-ellipsis";
import { SearchInput } from "../../../components/ui/search-input";

function buildSearchHaystack(item) {
  if (!item) return "";
  return Object.values(item)
    .map((value) => {
      if (value === null || value === undefined) return "";
      if (typeof value === "string") return value;
      if (typeof value === "number" || typeof value === "boolean") return String(value);
      return "";
    })
    .join(" ")
    .toLowerCase();
}

function formatKeyLabel(key) {
  if (!key) return "—";
  if (key === "display_name") return "NAME";
  return String(key)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "—";
  if (Array.isArray(value)) return value.length ? JSON.stringify(value) : "—";
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return "—";
    }
  }
  return String(value);
}

export function SimpleTableTab({
  title,
  items,
  itemsQuery,
  itemLabel = "item",
  searchPlaceholder = "Search...",
  emptyMessage = "No items found.",
  preferredColumns = [],
  stringKey = "value",
}) {
  const [searchTerm, setSearchTerm] = useState("");

  const normalizedItems = useMemo(() => {
    const list = Array.isArray(items) ? items : [];
    return list.map((item) => {
      if (item === null || item === undefined) return { [stringKey]: "—" };
      if (typeof item === "string" || typeof item === "number" || typeof item === "boolean") {
        return { [stringKey]: item };
      }
      return item;
    });
  }, [items, stringKey]);

  const columns = useMemo(() => {
    const keySet = new Set();
    normalizedItems.forEach((item) => {
      Object.keys(item || {}).forEach((key) => keySet.add(key));
    });
    const remaining = Array.from(keySet).filter((key) => !preferredColumns.includes(key)).sort();
    return [...preferredColumns.filter((key) => keySet.has(key)), ...remaining];
  }, [normalizedItems, preferredColumns]);

  const rows = useMemo(() => {
    const needle = searchTerm.trim().toLowerCase();
    const filtered = normalizedItems.filter((item) => {
      if (!needle) return true;
      return buildSearchHaystack(item).includes(needle);
    });
    return filtered.map((item, index) => ({
      id: item?.id ?? item?.[stringKey] ?? `row-${index}`,
      raw: item,
    }));
  }, [normalizedItems, searchTerm, stringKey]);

  const loading = itemsQuery?.isLoading;
  const hasError = itemsQuery?.isError;
  const errorMessage = itemsQuery?.error?.message || "Failed to load data.";

  return (
    <Card className="h-full min-h-0 flex flex-col">
      <CardHeader className="space-y-1">
        <CardTitle>{title}</CardTitle>
        <div className="text-xs text-black/55 dark:text-white/60">
          {rows.length} {itemLabel}
          {rows.length === 1 ? "" : "s"}
        </div>
      </CardHeader>
      <CardContent className="flex-1 min-h-0 overflow-y-auto space-y-3 pt-1 md:flex md:flex-col md:overflow-hidden">
        <SearchInput
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full md:shrink-0"
          placeholder={searchPlaceholder}
        />
        {loading ? (
          <LoadingEllipsis text="Loading" className="text-sm text-black/60 dark:text-white/65" />
        ) : hasError ? (
          <div className="text-sm text-red-700 dark:text-red-300">{errorMessage}</div>
        ) : !rows.length ? (
          <div className="text-sm text-black/60 dark:text-white/65">{emptyMessage}</div>
        ) : (
          <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-white/40 dark:bg-white/5 w-full max-w-full overflow-hidden md:flex-1 md:min-h-0">
            <div className="w-full max-w-full min-w-0 overflow-x-auto md:h-full md:overflow-auto">
              <div className="min-w-max">
                <table className="w-full text-sm">
                  <thead className="bg-white dark:bg-neutral-900 text-xs uppercase tracking-wide text-black/45 dark:text-white/50">
                    <tr>
                      {columns.map((key) => (
                        <th
                          key={key}
                          className="sticky top-0 z-10 px-4 py-3 text-left font-semibold whitespace-nowrap bg-white dark:bg-neutral-900"
                        >
                          {formatKeyLabel(key)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-black/5 dark:divide-white/10">
                    {rows.map((row) => (
                      <tr key={row.id} className="text-black/80 dark:text-white/85">
                        {columns.map((key) => (
                          <td key={`${row.id}-${key}`} className="px-4 py-3 whitespace-nowrap">
                            {formatValue(row.raw?.[key])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

import React, { useMemo, useState } from "react";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { FormField } from "../../../components/ui/form-field";
import { LoadingEllipsis } from "../../../components/ui/loading-ellipsis";
import { Modal } from "../../../components/ui/modal";
import { SearchInput } from "../../../components/ui/search-input";
import { SelectDropdown } from "../../../components/ui/select-dropdown";

function buildSearchHaystack(location) {
  if (!location) return "";
  return Object.values(location)
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

export function LocationsTab({ locations, locationsQuery }) {
  const [editingLocation, setEditingLocation] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [displayTypeFilter, setDisplayTypeFilter] = useState("");
  const [companyFilter, setCompanyFilter] = useState("");
  const [seriesFilter, setSeriesFilter] = useState("");

  const displayTypeOptions = useMemo(() => {
    const list = Array.isArray(locations) ? locations : [];
    const values = new Set();
    list.forEach((location) => {
      const value = location?.display_type || "";
      if (value) values.add(value);
    });
    return [
      { value: "", label: "All display types" },
      ...Array.from(values).sort().map((value) => ({ value, label: value })),
    ];
  }, [locations]);

  const companyOptions = useMemo(() => {
    const list = Array.isArray(locations) ? locations : [];
    const values = new Set();
    list.forEach((location) => {
      const value = location?.company_schema || "";
      if (value) values.add(value);
    });
    return [
      { value: "", label: "All companies" },
      ...Array.from(values).sort().map((value) => ({ value, label: value })),
    ];
  }, [locations]);

  const seriesOptions = useMemo(() => {
    const list = Array.isArray(locations) ? locations : [];
    const values = new Set();
    list.forEach((location) => {
      const value = location?.series || "";
      if (value) values.add(value);
    });
    return [{ value: "", label: "All series" }, ...Array.from(values).sort().map((value) => ({ value, label: value }))];
  }, [locations]);

  const rows = useMemo(() => {
    const list = Array.isArray(locations) ? locations : [];
    const needle = searchTerm.trim().toLowerCase();
    const filtered = list.filter((location) => {
      if (displayTypeFilter) {
        const value = location?.display_type || "";
        if (value !== displayTypeFilter) return false;
      }
      if (companyFilter) {
        const value = location?.company_schema || "";
        if (value !== companyFilter) return false;
      }
      if (seriesFilter) {
        const value = location?.series || "";
        if (value !== seriesFilter) return false;
      }
      if (needle) {
        const haystack = buildSearchHaystack(location);
        if (!haystack.includes(needle)) return false;
      }
      return true;
    });
    return filtered.map((location, index) => ({
      id: location?.location_key || `location-${index}`,
      raw: location,
    }));
  }, [locations, displayTypeFilter, companyFilter, seriesFilter, searchTerm]);

  const columns = useMemo(() => {
    const list = Array.isArray(locations) ? locations : [];
    const keySet = new Set();
    list.forEach((location) => {
      Object.keys(location || {}).forEach((key) => keySet.add(key));
    });
    const preferred = [
      "display_name",
      "location_key",
      "display_type",
      "company_schema",
      "series",
      "city",
      "area",
      "upload_fee",
      "height",
      "width",
      "number_of_faces",
      "spot_duration",
      "loop_duration",
      "sov_percent",
      "eligible_for_proposals",
      "eligible_for_mockups",
    ];
    const remaining = Array.from(keySet).filter((key) => !preferred.includes(key)).sort();
    return [...preferred.filter((key) => keySet.has(key)), ...remaining];
  }, [locations]);

  const activeEntries = useMemo(() => {
    if (!editingLocation) return [];
    return Object.entries(editingLocation);
  }, [editingLocation]);

  const activeLocation = editingLocation || null;

  return (
    <>
      <Card className="h-full min-h-0 flex flex-col">
        <CardHeader className="space-y-1">
          <CardTitle>Locations</CardTitle>
          <div className="text-xs text-black/55 dark:text-white/60">
            {rows.length} location{rows.length === 1 ? "" : "s"}
          </div>
        </CardHeader>
        <CardContent className="flex-1 min-h-0 overflow-y-auto space-y-3 pt-1">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-4">
            <SearchInput
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full"
              placeholder="Search locations..."
            />
            <SelectDropdown
              value={displayTypeFilter}
              options={displayTypeOptions}
              onChange={setDisplayTypeFilter}
              className="w-full"
            />
            <SelectDropdown
              value={companyFilter}
              options={companyOptions}
              onChange={setCompanyFilter}
              className="w-full"
            />
            <SelectDropdown
              value={seriesFilter}
              options={seriesOptions}
              onChange={setSeriesFilter}
              className="w-full"
            />
          </div>
          {locationsQuery.isLoading ? (
            <LoadingEllipsis text="Loading locations" className="text-sm text-black/60 dark:text-white/65" />
          ) : locationsQuery.isError ? (
            <div className="text-sm text-red-700 dark:text-red-300">
              {locationsQuery.error?.message || "Failed to load locations."}
            </div>
          ) : !rows.length ? (
            <div className="text-sm text-black/60 dark:text-white/65">No locations found.</div>
          ) : (
            <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-white/40 dark:bg-white/5 w-full max-w-full overflow-hidden">
              <div className="w-full max-w-full min-w-0 overflow-x-auto">
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
                        <th className="sticky top-0 right-0 z-20 px-4 py-3 text-left font-semibold bg-white dark:bg-neutral-900">
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-black/5 dark:divide-white/10">
                      {rows.map((row) => (
                        <tr key={row.id} className="text-black/80 dark:text-white/85">
                          {columns.map((key) => {
                            const value = formatValue(row.raw?.[key]);
                            return (
                              <td key={`${row.id}-${key}`} className="px-4 py-3 whitespace-nowrap">
                                {value}
                              </td>
                            );
                          })}
                          <td className="sticky right-0 z-10 px-4 py-3 bg-white/90 dark:bg-neutral-900/95">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="rounded-xl"
                              onClick={() => setEditingLocation(row.raw)}
                            >
                              Edit
                            </Button>
                          </td>
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

      <Modal
        open={Boolean(editingLocation)}
        onClose={() => setEditingLocation(null)}
        title="Edit location"
        maxWidth="560px"
      >
        {activeLocation ? (
          <div className="space-y-3">
            <FormField label="Location Key">
              <input
                className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                value={activeLocation.location_key || "—"}
                disabled
                readOnly
              />
            </FormField>
            <FormField label="Display Name">
              <input
                className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                value={activeLocation.display_name || "—"}
                disabled
                readOnly
              />
            </FormField>
            <FormField label="Display Type">
              <input
                className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                value={activeLocation.display_type || "—"}
                disabled
                readOnly
              />
            </FormField>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <FormField label="Company">
                <input
                  className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                  value={activeLocation.company_schema || "—"}
                  disabled
                  readOnly
                />
              </FormField>
              <FormField label="Series">
                <input
                  className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                  value={activeLocation.series || "—"}
                  disabled
                  readOnly
                />
              </FormField>
              <FormField label="City">
                <input
                  className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                  value={activeLocation.city || "—"}
                  disabled
                  readOnly
                />
              </FormField>
              <FormField label="Area">
                <input
                  className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                  value={activeLocation.area || "—"}
                  disabled
                  readOnly
                />
              </FormField>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" className="rounded-2xl" onClick={() => setEditingLocation(null)}>
                Close
              </Button>
              <Button className="rounded-2xl" disabled>
                Save
              </Button>
            </div>
            <div className="pt-2">
              <div className="text-xs uppercase tracking-wide text-black/50 dark:text-white/60 mb-2">
                All fields
              </div>
              <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-white/40 dark:bg-white/5 divide-y divide-black/5 dark:divide-white/10">
                {activeEntries.map(([key, value]) => (
                  <div key={key} className="flex flex-col md:flex-row md:items-center gap-2 px-3 py-2 text-sm">
                    <div className="text-xs uppercase tracking-wide text-black/45 dark:text-white/55 md:w-56">
                      {formatKeyLabel(key)}
                    </div>
                    <div className="text-black/80 dark:text-white/85 break-all">{formatValue(value)}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : null}
      </Modal>
    </>
  );
}

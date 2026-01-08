import React, { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, ExternalLink, FileText, Plus, Trash2 } from "lucide-react";

import * as proposalsApi from "../../../api/proposals";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { Button } from "../../../components/ui/button";
import { FormField } from "../../../components/ui/form-field";
import { LoadingEllipsis } from "../../../components/ui/loading-ellipsis";
import { SelectDropdown } from "../../../components/ui/select-dropdown";
import { runtimeConfig } from "../../../lib/runtimeConfig";

function formatDateForApi(value) {
  if (!value) return "";
  const trimmed = String(value).trim();
  if (!trimmed) return "";
  if (trimmed.includes("/")) return trimmed;
  const parts = trimmed.split("-");
  if (parts.length === 3) {
    const [year, month, day] = parts;
    if (year && month && day) return `${day}/${month}/${year}`;
  }
  return trimmed;
}

function formatWeeks(value) {
  const parsed = Number.parseInt(value, 10);
  const normalized = Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
  return `${normalized} ${normalized === 1 ? "Week" : "Weeks"}`;
}

function formatAmount(value, currencyCode) {
  const code = currencyCode || "AED";
  if (value === null || value === undefined || value === "") return `${code} 0`;
  const raw = typeof value === "string" ? value.trim() : value;
  if (typeof raw === "string" && raw.toUpperCase().startsWith(code)) return raw;
  const numeric = typeof raw === "number" ? raw : Number.parseFloat(String(raw).replace(/,/g, ""));
  if (!Number.isFinite(numeric)) return `${code} 0`;
  return `${code} ${numeric.toLocaleString()}`;
}

function parseAmount(value) {
  if (value === null || value === undefined) return 0;
  const numeric = Number.parseFloat(String(value).replace(/[^\d.-]/g, ""));
  return Number.isFinite(numeric) ? numeric : 0;
}

function useProposalsGenerate() {
  const qc = useQueryClient();
  const [client, setClient] = useState("");
  const createPeriod = () => ({
    id: crypto.randomUUID(),
    startDate: "",
    duration: "",
    netRate: "",
  });
  const createItem = () => ({
    id: crypto.randomUUID(),
    location: "",
    spots: "1",
    productionFee: "",
    periods: [createPeriod()],
  });
  const [items, setItems] = useState(() => [createItem()]);
  const [packageType, setPackageType] = useState("separate");
  const [combinedNetRate, setCombinedNetRate] = useState("");
  const [currency, setCurrency] = useState("AED");
  const [paymentTerms, setPaymentTerms] = useState("100% upfront");
  const [lastResults, setLastResults] = useState([]);
  const [locationDetailsByKey, setLocationDetailsByKey] = useState({});

  const locationsQuery = useQuery({
    queryKey: ["locations", "proposals"],
    queryFn: () => proposalsApi.getLocations({ service: "proposals" }),
  });

  const locationOptions = useMemo(() => {
    const data = locationsQuery.data;
    if (Array.isArray(data)) return data;
    return data?.locations || data?.data || [];
  }, [locationsQuery.data]);

  const locationKeys = useMemo(
    () => Array.from(new Set(items.map((item) => item.location).filter(Boolean))),
    [items]
  );

  useEffect(() => {
    if (!locationKeys.length) return;
    const missing = locationKeys.filter((key) => !locationDetailsByKey[key]);
    if (!missing.length) return;
    let active = true;
    (async () => {
      const entries = await Promise.all(
        missing.map(async (key) => {
          try {
            const data = await proposalsApi.getLocationByKey(key);
            return [key, data];
          } catch {
            return [key, null];
          }
        })
      );
      if (!active) return;
      setLocationDetailsByKey((prev) => {
        const next = { ...prev };
        entries.forEach(([key, data]) => {
          if (data) next[key] = data;
        });
        return next;
      });
    })();
    return () => {
      active = false;
    };
  }, [locationKeys, locationDetailsByKey]);

  const generateMutation = useMutation({
    mutationFn: (payload) => proposalsApi.generate(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["proposals", "history"] });
    },
  });

  function updateItem(id, field, value) {
    setItems((prev) => prev.map((item) => (item.id === id ? { ...item, [field]: value } : item)));
  }

  function updatePeriod(itemId, periodId, field, value) {
    setItems((prev) =>
      prev.map((item) => {
        if (item.id !== itemId) return item;
        return {
          ...item,
          periods: item.periods.map((period) =>
            period.id === periodId ? { ...period, [field]: value } : period
          ),
        };
      })
    );
  }

  function addItem() {
    setItems((prev) => [...prev, createItem()]);
  }

  function removeItem(id) {
    setItems((prev) => (prev.length > 1 ? prev.filter((item) => item.id !== id) : prev));
  }

  function addPeriod(itemId) {
    setItems((prev) =>
      prev.map((item) => (item.id === itemId ? { ...item, periods: [...item.periods, createPeriod()] } : item))
    );
  }

  function removePeriod(itemId, periodId) {
    setItems((prev) =>
      prev.map((item) => {
        if (item.id !== itemId) return item;
        if (item.periods.length <= 1) return item;
        return { ...item, periods: item.periods.filter((period) => period.id !== periodId) };
      })
    );
  }

  function handleGenerate() {
    const currencyCode = currency || "AED";
    const combinedRate = formatAmount(combinedNetRate, currencyCode);
    const proposalItems = items.filter((item) => item.location);
    const proposals = proposalItems.map((item) => {
      const filledPeriods = item.periods.filter(
        (period) => period.startDate || period.duration || period.netRate
      );
      const periods = packageType === "combined"
        ? [filledPeriods[0] || item.periods[0]]
        : filledPeriods;
      const startDates = periods.map((period) => formatDateForApi(period?.startDate || ""));
      const durations = periods.map((period) => formatWeeks(period?.duration));
      const netRates = periods.map((period) => formatAmount(period?.netRate, currencyCode));
      const spotValue = Number.parseInt(item.spots, 10);
      const spots = Number.isFinite(spotValue) && spotValue > 0 ? spotValue : 1;
      const detailsRaw = locationDetailsByKey[item.location] || {};
      const details = detailsRaw.location || detailsRaw;
      const isStatic = (details.display_type || details.displayType || "").toLowerCase() === "static";
      const uploadFeeValue = details.upload_fee ?? details.uploadFee ?? 0;
      const productionFeeValue = details.production_fee ?? details.productionFee ?? 0;
      const overrideProductionFee = item.productionFee;
      const proposal = {
        location: item.location || "",
        upload_fee: formatAmount(uploadFeeValue, currencyCode),
        spots,
      };
      if (isStatic) {
        proposal.production_fee = formatAmount(
          overrideProductionFee !== "" && overrideProductionFee !== null && overrideProductionFee !== undefined
            ? overrideProductionFee
            : productionFeeValue,
          currencyCode
        );
      }
      if (packageType === "combined") {
        proposal.start_date = startDates[0] || "";
        proposal.duration = durations[0] || formatWeeks(1);
      } else {
        proposal.start_dates = startDates;
        proposal.durations = durations;
        proposal.net_rates = netRates;
      }
      return proposal;
    });
    const locationLabels = proposalItems
      .map((item) => {
        const loc = locationOptions.find((opt) => (opt.location_key || opt.key || opt.id) === item.location);
        return loc?.display_name || loc?.name || loc?.label || item.location;
      })
      .filter(Boolean)
      .join(", ");

    const payload = {
      proposals,
      client_name: client,
      proposal_type: packageType,
      payment_terms: paymentTerms || "100% upfront",
      currency: currencyCode,
    };
    if (packageType === "combined") {
      payload.combined_net_rate = combinedRate;
    }
    const meta = {
      client,
      packageType,
      items: proposals.map((item) => ({
        location: item.location,
        netRatesValue: Array.isArray(item.net_rates) ? item.net_rates.map(parseAmount) : [],
      })),
      combinedNetRateValue: packageType === "combined" ? parseAmount(combinedRate) : 0,
      locationsLabel: locationLabels,
      currency: currencyCode,
      paymentTerms: paymentTerms || "100% upfront",
    };
    generateMutation.mutate(payload, {
      onSuccess: (data) => {
        setLastResults((prev) => [{ data, meta }, ...prev].slice(0, 3));
      },
    });
  }

  function resetForm() {
    setClient("");
    setItems([createItem()]);
    setPackageType("separate");
    setCombinedNetRate("");
    setCurrency("AED");
    setPaymentTerms("100% upfront");
  }

  return {
    client,
    setClient,
    items,
    updateItem,
    addItem,
    removeItem,
    addPeriod,
    removePeriod,
    updatePeriod,
    packageType,
    setPackageType,
    combinedNetRate,
    setCombinedNetRate,
    currency,
    setCurrency,
    paymentTerms,
    setPaymentTerms,
    lastResults,
    locationsQuery,
    locationOptions,
    generateMutation,
    handleGenerate,
    resetForm,
  };
}

export function GeneratePanel() {
  const state = useProposalsGenerate();
  return <GenerateTab {...state} />;
}

export function GenerateTab({
  client,
  setClient,
  items,
  updateItem,
  addItem,
  removeItem,
  addPeriod,
  removePeriod,
  updatePeriod,
  packageType,
  setPackageType,
  combinedNetRate,
  setCombinedNetRate,
  currency,
  setCurrency,
  paymentTerms,
  setPaymentTerms,
  lastResults,
  locationsQuery,
  locationOptions,
  generateMutation,
  handleGenerate,
  resetForm,
}) {
  const results = Array.isArray(lastResults) ? lastResults : [];
  const isGenerating = generateMutation.isPending;
  const locationSelectOptions = useMemo(() => {
    const options = locationOptions
      .map((loc) => {
        const value = loc.location_key || loc.key || loc.id || "";
        const label = loc.display_name || loc.name || loc.label || value || "—";
        return { value, label };
      })
      .filter((opt) => opt.value);
    return [{ value: "", label: "Select a location" }, ...options];
  }, [locationOptions]);
  const packageTypeOptions = useMemo(
    () => [
      { value: "separate", label: "Separate" },
      { value: "combined", label: "Combined" },
    ],
    []
  );
  const currencyOptions = useMemo(
    () => [
      { value: "AED", label: "AED" },
      { value: "EUR", label: "EUR" },
      { value: "USD", label: "USD" },
      { value: "GBP", label: "GBP" },
    ],
    []
  );

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Generate Proposal</CardTitle>
      </CardHeader>
      <CardContent className="flex-1 min-h-0 overflow-y-auto space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <FormField label="Client">
            <input
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={client}
              onChange={(e) => setClient(e.target.value)}
              placeholder="Client name"
            />
          </FormField>
          <FormField label="Package Type">
            <SelectDropdown value={packageType} options={packageTypeOptions} onChange={setPackageType} />
          </FormField>
        </div>
        {packageType === "combined" ? (
          <FormField label="Combined Net Rate">
            <input
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={combinedNetRate}
              onChange={(e) => setCombinedNetRate(e.target.value)}
              type="number"
              min="0"
              step="0.01"
              placeholder="0"
            />
          </FormField>
        ) : null}
        <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-white/40 dark:bg-white/5 p-3 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-sm font-semibold text-black/80 dark:text-white/85">Locations</div>
              {locationsQuery.isLoading ? (
                <div className="mt-1 text-xs text-black/50 dark:text-white/60">
                  <LoadingEllipsis text="Loading locations" />
                </div>
              ) : null}
            </div>
            <Button variant="secondary" size="sm" className="rounded-xl" onClick={addItem}>
              Add Location
            </Button>
          </div>
          <div className="space-y-3">
            {items.map((item) => {
              const selectedLocation = locationOptions.find(
                (loc) => (loc.location_key || loc.key || loc.id) === item.location
              );
              const isStatic = (selectedLocation?.display_type || "").toLowerCase() === "static";
              return (
                <div
                  key={item.id}
                  className="rounded-xl border border-black/5 dark:border-white/10 bg-white/60 dark:bg-white/5 p-3 space-y-3"
                >
                  {packageType === "combined" ? (
                    <div className="grid grid-cols-1 md:grid-cols-[1.4fr_0.6fr_0.9fr_0.7fr_auto] gap-2 items-end">
                      <FormField label="Location">
                        <SelectDropdown
                          value={item.location}
                          options={locationSelectOptions}
                          onChange={(nextValue) => updateItem(item.id, "location", nextValue)}
                        />
                      </FormField>
                      <FormField label="Spots">
                        <input
                          className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                          value={item.spots}
                          onChange={(e) => updateItem(item.id, "spots", e.target.value)}
                          type="number"
                          min="1"
                          step="1"
                          placeholder="1"
                        />
                      </FormField>
                      <FormField label="Start Date">
                        <input
                          className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                          value={item.periods[0]?.startDate || ""}
                          onChange={(e) => updatePeriod(item.id, item.periods[0]?.id, "startDate", e.target.value)}
                          type="date"
                        />
                      </FormField>
                      <FormField label="Duration (weeks)">
                        <input
                          className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                          value={item.periods[0]?.duration || ""}
                          onChange={(e) => updatePeriod(item.id, item.periods[0]?.id, "duration", e.target.value)}
                          type="number"
                          min="1"
                          step="1"
                          placeholder="1"
                        />
                      </FormField>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="rounded-xl h-10 w-10"
                        onClick={() => removeItem(item.id)}
                        disabled={items.length === 1}
                        title="Remove location"
                      >
                        <Trash2 size={16} />
                      </Button>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 items-end">
                      <FormField label="Location">
                        <SelectDropdown
                          value={item.location}
                          options={locationSelectOptions}
                          onChange={(nextValue) => updateItem(item.id, "location", nextValue)}
                        />
                      </FormField>
                      <div className="flex items-end justify-between gap-2">
                        <FormField label="Spots" className="flex-1">
                          <input
                            className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                            value={item.spots}
                            onChange={(e) => updateItem(item.id, "spots", e.target.value)}
                            type="number"
                            min="1"
                            step="1"
                            placeholder="1"
                          />
                        </FormField>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="rounded-xl h-10 w-10"
                          onClick={() => removeItem(item.id)}
                          disabled={items.length === 1}
                          title="Remove location"
                        >
                          <Trash2 size={16} />
                        </Button>
                      </div>
                    </div>
                  )}

                  {isStatic ? (
                    <FormField label="Production Fee">
                      <input
                        className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                        value={item.productionFee}
                        onChange={(e) => updateItem(item.id, "productionFee", e.target.value)}
                        type="number"
                        min="0"
                        step="0.01"
                        placeholder="0"
                      />
                    </FormField>
                  ) : null}

                {packageType !== "combined" ? (
                  <>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="text-xs font-semibold text-black/60 dark:text-white/60">Line Items</div>
                      <Button variant="secondary" size="sm" className="rounded-xl" onClick={() => addPeriod(item.id)}>
                        Add Line Item
                      </Button>
                    </div>
                    <div className="space-y-2">
                      {item.periods.map((period) => (
                        <div
                          key={period.id}
                          className="grid grid-cols-1 md:grid-cols-[1fr_1fr_1fr_1fr_auto] gap-2 items-end"
                        >
                          <FormField label="Start Date">
                            <input
                              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                              value={period.startDate}
                              onChange={(e) => updatePeriod(item.id, period.id, "startDate", e.target.value)}
                              type="date"
                            />
                          </FormField>
                          <FormField label="Duration (weeks)">
                            <input
                              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                              value={period.duration}
                              onChange={(e) => updatePeriod(item.id, period.id, "duration", e.target.value)}
                              type="number"
                              min="1"
                              step="1"
                              placeholder="1"
                            />
                          </FormField>
                          <FormField label="Net Rate">
                            <input
                              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                              value={period.netRate}
                              onChange={(e) => updatePeriod(item.id, period.id, "netRate", e.target.value)}
                              type="number"
                              min="0"
                              step="0.01"
                              placeholder="0"
                            />
                          </FormField>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="rounded-xl h-10 w-10"
                            onClick={() => removePeriod(item.id, period.id)}
                            disabled={item.periods.length === 1}
                            title="Remove dates"
                          >
                            <Trash2 size={16} />
                          </Button>
                        </div>
                      ))}
                    </div>
                  </>
                ) : null}
              </div>
            );
            })}
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <FormField label="Currency">
            <SelectDropdown value={currency} options={currencyOptions} onChange={setCurrency} />
          </FormField>
          <FormField label="Payment Terms">
            <input
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={paymentTerms}
              onChange={(e) => setPaymentTerms(e.target.value)}
              placeholder="Payment terms"
            />
          </FormField>
        </div>

        {generateMutation.isError ? (
          <div className="rounded-xl bg-red-50/70 text-red-700 px-4 py-2 text-sm dark:bg-red-500/10 dark:text-red-300">
            {generateMutation.error?.message || "Generation failed"}
          </div>
        ) : null}

        <div className="flex items-center gap-3">
          <Button
            className="rounded-2xl"
            onClick={handleGenerate}
            disabled={isGenerating}
          >
            {isGenerating ? <LoadingEllipsis text="Generating Proposal" /> : "Generate Proposal"}
          </Button>
          <Button
            variant="secondary"
            className="rounded-2xl"
            onClick={resetForm}
            disabled={isGenerating}
          >
            Reset
          </Button>
        </div>

        <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-white/40 dark:bg-white/5 p-4 space-y-3">
          {!results.length && !isGenerating ? (
            <div className="text-sm text-black/60 dark:text-white/65">Result will appear here</div>
          ) : null}
          {isGenerating ? (
            <LoadingEllipsis text="Processing proposal" className="text-sm text-black/60 dark:text-white/65" />
          ) : null}
          {results.length ? (
            <>
              <div className="text-sm font-semibold text-black/80 dark:text-white/85">
                Last 3 Generated Proposals
              </div>
              <div className="space-y-4">
                {results.map((result, index) => {
                  const resultData = result?.data || null;
                  const resultMeta = result?.meta || null;
                  const fileEntries = [];
                  if (resultData?.pptx_url) fileEntries.push({ url: resultData.pptx_url, type: "pptx" });
                  if (resultData?.pdf_url) fileEntries.push({ url: resultData.pdf_url, type: "pdf" });
                  const resultLocation = resultData?.locations || resultMeta?.locationsLabel || "—";
                  const totalAmountValue =
                    resultMeta?.packageType === "combined"
                      ? resultMeta?.combinedNetRateValue
                      : (resultMeta?.items || []).reduce((sum, item) => {
                          const rates = Array.isArray(item.netRatesValue) ? item.netRatesValue : [];
                          return sum + rates.reduce((inner, rate) => inner + (rate || 0), 0);
                        }, 0);
                  const totalAmountLabel =
                    Number.isFinite(totalAmountValue)
                      ? `${resultMeta?.currency || "AED"} ${Number(totalAmountValue).toLocaleString()}`
                      : "—";
                  return (
                    <div
                      key={`proposal-output-${index}`}
                      className="rounded-xl border border-black/5 dark:border-white/10 bg-white/60 dark:bg-white/5 p-3 space-y-3"
                    >
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-xs text-black/65 dark:text-white/65">
                        <div className="flex flex-wrap items-baseline gap-1">
                          <span className="uppercase tracking-wide text-black/45 dark:text-white/50">Client</span>
                          <span className="font-semibold text-black/80 dark:text-white/85">
                            {resultMeta?.client || "—"}
                          </span>
                        </div>
                        <div className="flex flex-wrap items-baseline gap-1">
                          <span className="uppercase tracking-wide text-black/45 dark:text-white/50">Package</span>
                          <span className="font-semibold text-black/80 dark:text-white/85">
                            {resultMeta?.packageType || "—"}
                          </span>
                        </div>
                        <div className="flex flex-wrap items-baseline gap-1 sm:col-span-2">
                          <span className="uppercase tracking-wide text-black/45 dark:text-white/50">Locations</span>
                          <span className="font-semibold text-black/80 dark:text-white/85">{resultLocation}</span>
                        </div>
                        <div className="flex flex-wrap items-baseline gap-1">
                          <span className="uppercase tracking-wide text-black/45 dark:text-white/50">Total Amount</span>
                          <span className="font-semibold text-black/80 dark:text-white/85">{totalAmountLabel}</span>
                        </div>
                      </div>

                      {fileEntries.length ? (
                        <div className="space-y-2">
                          {fileEntries.map((file) => {
                            const resolvedUrl = resolveProposalUrl(file.url);
                            const nameFromUrl = getNameFromUrl(resolvedUrl);
                            const fallbackName = file.type === "pdf" ? "proposal.pdf" : "proposal.pptx";
                            const displayName = nameFromUrl || fallbackName;
                            const isPdf = file.type === "pdf";
                            return (
                              <div
                                key={`${file.type}-${file.url}`}
                                className="rounded-xl border border-black/5 dark:border-white/10 bg-white/70 dark:bg-white/5 p-3"
                              >
                                <div className="flex flex-wrap items-start justify-between gap-3">
                                  <div className="min-w-0">
                                    <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-black/50 dark:text-white/60">
                                      {isPdf ? (
                                        <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 text-red-700 dark:text-red-300 px-2 py-0.5">
                                          <FileText size={12} />
                                          PDF
                                        </span>
                                      ) : (
                                        <span className="inline-flex items-center gap-1 rounded-full bg-black/5 dark:bg-white/10 px-2 py-0.5">
                                          PPTX
                                        </span>
                                      )}
                                    </div>
                                    <div className="mt-1 text-xs font-semibold text-black/80 dark:text-white/85 truncate">
                                      {displayName}
                                    </div>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <Button asChild size="sm" variant="ghost" className="rounded-xl">
                                      <a href={resolvedUrl} target="_blank" rel="noopener noreferrer">
                                        <ExternalLink size={14} className="mr-1" />
                                        Open
                                      </a>
                                    </Button>
                                    <Button size="sm" variant="secondary" className="rounded-xl">
                                      <span
                                        role="link"
                                        tabIndex={0}
                                        onClick={(e) => {
                                          e.preventDefault();
                                          downloadFile(resolvedUrl, displayName);
                                        }}
                                        onKeyDown={(e) => {
                                          if (e.key === "Enter" || e.key === " ") {
                                            e.preventDefault();
                                            downloadFile(resolvedUrl, displayName);
                                          }
                                        }}
                                        className="inline-flex items-center"
                                      >
                                        <Download size={14} className="mr-1" />
                                        Download
                                      </span>
                                    </Button>
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <div className="text-xs text-black/55 dark:text-white/60">No files returned yet.</div>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function resolveProposalUrl(url) {
  if (!url) return "";
  if (url.startsWith("http")) return url;
  return `${runtimeConfig.API_BASE_URL}${url}`;
}

function getNameFromUrl(url) {
  if (!url) return "";
  try {
    const resolved = new URL(url, window.location.href);
    const parts = resolved.pathname.split("/").filter(Boolean);
    return parts.length ? decodeURIComponent(parts[parts.length - 1]) : "";
  } catch {
    const fallback = url.split("?")[0].split("#")[0];
    const parts = fallback.split("/").filter(Boolean);
    return parts.length ? decodeURIComponent(parts[parts.length - 1]) : "";
  }
}

async function downloadFile(url, filename) {
  const res = await fetch(url);
  const blob = await res.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename || "download";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

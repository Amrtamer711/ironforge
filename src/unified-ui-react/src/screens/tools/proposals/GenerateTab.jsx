import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";

import * as proposalsApi from "../../../api/proposals";
import * as mockupApi from "../../../api/mockup";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { Button } from "../../../components/ui/button";
import { FormField } from "../../../components/ui/form-field";
import { LoadingEllipsis } from "../../../components/ui/loading-ellipsis";

function useProposalsGenerate() {
  const qc = useQueryClient();
  const [client, setClient] = useState("");
  const [location, setLocation] = useState("");
  const [notes, setNotes] = useState("");

  const locationsQuery = useQuery({
    queryKey: ["mockup", "locations"],
    queryFn: mockupApi.getLocations,
  });

  const locationOptions = useMemo(() => {
    const data = locationsQuery.data;
    if (Array.isArray(data)) return data;
    return data?.locations || [];
  }, [locationsQuery.data]);

  const generateMutation = useMutation({
    mutationFn: (payload) => proposalsApi.generate(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["proposals", "history"] });
      setClient("");
      setLocation("");
      setNotes("");
    },
  });

  function handleGenerate() {
    generateMutation.mutate({ client, location, notes });
  }

  return {
    client,
    setClient,
    location,
    setLocation,
    notes,
    setNotes,
    locationsQuery,
    locationOptions,
    generateMutation,
    handleGenerate,
  };
}

export function GeneratePanel() {
  const state = useProposalsGenerate();
  return <GenerateTab {...state} />;
}

export function GenerateTab({
  client,
  setClient,
  location,
  setLocation,
  notes,
  setNotes,
  locationsQuery,
  locationOptions,
  generateMutation,
  handleGenerate,
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Generate Proposal</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <FormField label="Client">
            <input
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={client}
              onChange={(e) => setClient(e.target.value)}
              placeholder="Client name"
            />
          </FormField>
          <FormField label="Location">
            <select
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
            >
              <option value="">Select a location</option>
              {locationOptions.map((loc) => (
                <option key={loc.key || loc.id} value={loc.key || loc.id}>
                  {loc.name || loc.label || loc.key || loc.id}
                </option>
              ))}
            </select>
            {locationsQuery.isLoading ? (
              <div className="mt-1 text-xs text-black/50 dark:text-white/60">
                <LoadingEllipsis text="Loading locations" />
              </div>
            ) : null}
          </FormField>
        </div>

        <FormField label="Notes / Requirements">
          <textarea
            className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/10 dark:focus:ring-white/15 min-h-[120px]"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Key specs, deadlines..."
          />
        </FormField>

        {generateMutation.isError ? (
          <div className="rounded-xl bg-red-50/70 text-red-700 px-4 py-2 text-sm dark:bg-red-500/10 dark:text-red-300">
            {generateMutation.error?.message || "Generation failed"}
          </div>
        ) : null}

        <div className="flex items-center gap-3">
          <Button
            variant="secondary"
            className="gap-2 rounded-2xl"
            onClick={handleGenerate}
            disabled={generateMutation.isLoading}
          >
            <Plus size={18} />
            {generateMutation.isLoading ? <LoadingEllipsis text="Generating" /> : "Generate Proposal"}
          </Button>
          <div className="text-xs text-black/55 dark:text-white/60">Files will appear in history once ready.</div>
        </div>
      </CardContent>
    </Card>
  );
}

import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";

import * as proposalsApi from "../../api/proposals";
import * as mockupApi from "../../api/mockup";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";

export function ProposalsPage() {
  const qc = useQueryClient();

  const historyQuery = useQuery({
    queryKey: ["proposals", "history"],
    queryFn: proposalsApi.getHistory,
  });

  const locationsQuery = useQuery({
    queryKey: ["mockup", "locations"],
    queryFn: mockupApi.getLocations,
  });

  const [client, setClient] = useState("");
  const [location, setLocation] = useState("");
  const [notes, setNotes] = useState("");

  const generateMutation = useMutation({
    mutationFn: (payload) => proposalsApi.generate(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["proposals", "history"] });
      setClient("");
      setLocation("");
      setNotes("");
    },
  });

  const proposals = useMemo(() => {
    if (Array.isArray(historyQuery.data)) return historyQuery.data;
    if (historyQuery.data?.proposals) return historyQuery.data.proposals;
    return historyQuery.data || [];
  }, [historyQuery.data]);

  const locationOptions = useMemo(() => {
    const data = locationsQuery.data;
    if (Array.isArray(data)) return data;
    return data?.locations || [];
  }, [locationsQuery.data]);

  return (
    <div className="h-full min-h-0 flex flex-col">
      <div className="flex-1 min-h-0 overflow-y-auto space-y-4 px-2 py-1">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Generate Proposal</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field label="Client">
                <input
                  className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                  value={client}
                  onChange={(e) => setClient(e.target.value)}
                  placeholder="Client name"
                />
              </Field>
              <Field label="Location">
                <select
                  className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                >
                  <option value="">Select a location...</option>
                  {locationOptions.map((loc) => (
                    <option key={loc.key || loc.id} value={loc.key || loc.id}>
                      {loc.name || loc.label || loc.key || loc.id}
                    </option>
                  ))}
                </select>
              </Field>
            </div>

            <Field label="Notes / Requirements">
              <textarea
                className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/10 dark:focus:ring-white/15 min-h-[120px]"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Key specs, deadlines..."
              />
            </Field>

            {generateMutation.isError ? (
              <div className="rounded-xl bg-red-50/70 text-red-700 px-4 py-2 text-sm dark:bg-red-500/10 dark:text-red-300">
                {generateMutation.error?.message || "Generation failed"}
              </div>
            ) : null}

            <div className="flex items-center gap-3">
              <Button
                variant="secondary"
                className="gap-2 rounded-2xl"
                onClick={() => generateMutation.mutate({ client, location, notes })}
                disabled={generateMutation.isLoading}
              >
                <Plus size={18} />
                {generateMutation.isLoading ? "Generating..." : "Generate Proposal"}
              </Button>
              <div className="text-xs text-black/55 dark:text-white/60">Files will appear in history once ready.</div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>History</CardTitle>
          </CardHeader>
          <CardContent>
            {historyQuery.isLoading ? (
              <div className="text-sm text-black/60 dark:text-white/65">Loading…</div>
            ) : (
              <div className="space-y-2">
                {(proposals || []).map((p, idx) => (
                  <div
                    key={p.id || p.file_url || idx}
                    className="rounded-2xl p-4 bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 shadow-soft"
                  >
                    <div className="text-sm font-semibold">{p.client || "Proposal"}</div>
                    <div className="text-xs text-black/55 dark:text-white/60 mt-1">
                      {(p.location || "").toString()} {p.created_at ? `• ${new Date(p.created_at).toLocaleString()}` : ""}
                    </div>
                    {p.file_url ? (
                      <a
                        href={p.file_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex mt-2 text-xs underline opacity-80 hover:opacity-100"
                      >
                        Download
                      </a>
                    ) : null}
                  </div>
                ))}
                {!proposals?.length ? (
                  <div className="text-sm text-black/60 dark:text-white/65">No proposals yet.</div>
                ) : null}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block space-y-1">
      <div className="text-xs font-semibold text-black/60 dark:text-white/65">{label}</div>
      {children}
    </label>
  );
}

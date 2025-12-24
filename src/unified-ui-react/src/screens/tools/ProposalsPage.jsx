import React, { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";

import * as proposalsApi from "../../api/proposals";
import * as mockupApi from "../../api/mockup";
import * as adminApi from "../../api/admin";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { FormField } from "../../components/ui/form-field";
import { SoftCard } from "../../components/ui/soft-card";
import { LoadingEllipsis } from "../../components/ui/loading-ellipsis";

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
  const [userNameById, setUserNameById] = useState({});

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

  const userIds = useMemo(() => {
    const ids = new Set();
    (proposals || []).forEach((p) => {
      const id = p.submitted_by || p.user_id;
      if (id) ids.add(id);
    });
    return Array.from(ids);
  }, [proposals]);

  const missingUserIds = useMemo(
    () => userIds.filter((id) => !userNameById[id]),
    [userIds, userNameById]
  );

  useEffect(() => {
    if (!missingUserIds.length) return;
    let active = true;
    (async () => {
      const entries = await Promise.all(
        missingUserIds.map(async (id) => {
          try {
            const data = await adminApi.getrbacUser(id);
            const name = data?.name || data?.user?.name || data?.profile?.name || id;
            return [id, name];
          } catch {
            return [id, id];
          }
        })
      );
      if (!active) return;
      setUserNameById((prev) => {
        const next = { ...prev };
        entries.forEach(([id, name]) => {
          if (!next[id]) next[id] = name;
        });
        return next;
      });
    })();
    return () => {
      active = false;
    };
  }, [missingUserIds]);

  return (
    <div className="h-full min-h-0 flex flex-col">
      <div className="flex-1 min-h-0 overflow-y-auto space-y-4 px-2 py-1">
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
                  <option value="">Select a location...</option>
                  {locationOptions.map((loc) => (
                    <option key={loc.key || loc.id} value={loc.key || loc.id}>
                      {loc.name || loc.label || loc.key || loc.id}
                    </option>
                  ))}
                </select>
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
              <LoadingEllipsis text="Loading" className="text-sm text-black/60 dark:text-white/65" />
            ) : (
              <div className="space-y-2">
                {(proposals || []).map((p, idx) => {
                  const clientName = p.client_name || p.client || "Proposal";
                  const userId = p.submitted_by || p.user_id || "";
                  const userName = userId ? userNameById[userId] || userId : "—";
                  const generatedAt = p.date_generated || p.created_at;
                  const packageType = p.package_type || "—";
                  const locationText =
                    p.locations || p.proposal_data?.locations_text || p.location || "—";
                  const totalAmount =
                    p.total_amount ||
                    (p.total_amount_value != null
                      ? `${p.currency || ""} ${Number(p.total_amount_value).toLocaleString()}`
                      : "—");

                  return (
                    <SoftCard
                      key={p.id || p.file_url || idx}
                      className="p-3"
                    >
                      <div className="text-sm font-semibold">{clientName}</div>
                      <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-[11px] text-black/65 dark:text-white/65">
                        <div className="flex flex-wrap items-baseline gap-1">
                          <span className="uppercase tracking-wide text-[10px] text-black/45 dark:text-white/50">User</span>
                          <span className="font-semibold text-black/80 dark:text-white/85">{userName}</span>
                        </div>
                        <div className="flex flex-wrap items-baseline gap-1">
                          <span className="uppercase tracking-wide text-[10px] text-black/45 dark:text-white/50">Generated</span>
                          <span className="font-semibold text-black/80 dark:text-white/85">
                            {generatedAt ? new Date(generatedAt).toLocaleString() : "—"}
                          </span>
                        </div>
                        <div className="flex flex-wrap items-baseline gap-1">
                          <span className="uppercase tracking-wide text-[10px] text-black/45 dark:text-white/50">Package Type</span>
                          <span className="font-semibold text-black/80 dark:text-white/85">{packageType}</span>
                        </div>
                        <div className="flex flex-wrap items-baseline gap-1">
                          <span className="uppercase tracking-wide text-[10px] text-black/45 dark:text-white/50">Total Amount</span>
                          <span className="font-semibold text-black/80 dark:text-white/85">{totalAmount}</span>
                        </div>
                        <div className="flex flex-wrap items-baseline gap-1 sm:col-span-2">
                          <span className="uppercase tracking-wide text-[10px] text-black/45 dark:text-white/50">Locations</span>
                          <span className="font-semibold text-black/80 dark:text-white/85">{locationText}</span>
                        </div>
                      </div>
                      {p.file_url ? (
                        <a
                          href={p.file_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex mt-2 text-[11px] underline opacity-80 hover:opacity-100"
                        >
                          Download
                        </a>
                      ) : null}
                    </SoftCard>
                  );
                })}
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

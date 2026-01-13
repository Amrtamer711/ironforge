import React, { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import * as proposalsApi from "../../api/proposals";
import * as adminApi from "../../api/admin";
import { Download, ExternalLink } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { SearchInput } from "../../components/ui/search-input";
import { LoadingEllipsis } from "../../components/ui/loading-ellipsis";
import { SelectDropdown } from "../../components/ui/select-dropdown";
import { useAuth, canAccessAdmin } from "../../state/auth";
import { runtimeConfig } from "../../lib/runtimeConfig";

function useProposalsHistory() {
  const { user } = useAuth();
  const [userNameById, setUserNameById] = useState({});
  const [userNamesLoading, setUserNamesLoading] = useState(false);

  const historyQuery = useQuery({
    queryKey: ["proposals", "history"],
    queryFn: proposalsApi.getHistory,
  });

  const proposals = useMemo(() => {
    if (Array.isArray(historyQuery.data)) return historyQuery.data;
    if (historyQuery.data?.proposals) return historyQuery.data.proposals;
    return historyQuery.data || [];
  }, [historyQuery.data]);

  const canViewAll = useMemo(() => canAccessAdmin(user), [user]);

  const visibleProposals = useMemo(() => {
    const list = proposals || [];
    if (canViewAll) return list;
    const userId = user?.id || user?.user_id || user?.email || "";
    if (!userId) return list;
    return list.filter((p) => {
      const owner = p.submitted_by || p.user_id || "";
      return owner === userId;
    });
  }, [proposals, canViewAll, user?.id, user?.user_id, user?.email]);

  const userIds = useMemo(() => {
    const ids = new Set();
    (visibleProposals || []).forEach((p) => {
      const id = p.submitted_by || p.user_id;
      if (id) ids.add(id);
    });
    return Array.from(ids);
  }, [visibleProposals]);

  const missingUserIds = useMemo(
    () => userIds.filter((id) => !userNameById[id]),
    [userIds, userNameById]
  );

  useEffect(() => {
    if (!missingUserIds.length) return;
    setUserNamesLoading(true);
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
      setUserNamesLoading(false);
    })();
    return () => {
      active = false;
    };
  }, [missingUserIds]);

  useEffect(() => {
    if (!missingUserIds.length) setUserNamesLoading(false);
  }, [missingUserIds.length]);

  return {
    historyQuery,
    userNamesLoading,
    visibleProposals,
    userNameById,
  };
}

export function HistoryPanel() {
  const state = useProposalsHistory();
  return <HistoryTab {...state} />;
}

export function HistoryTab({ historyQuery, userNamesLoading, visibleProposals, userNameById }) {
  const [packageFilter, setPackageFilter] = useState("");
  const [locationFilter, setLocationFilter] = useState("");
  const [searchTerm, setSearchTerm] = useState("");

  const proposals = useMemo(
    () =>
      (visibleProposals || []).map((p, idx) => {
        const clientName = p.client_name || p.client || "Proposal";
        const userId = p.submitted_by || p.user_id || "";
        const userName = userId ? userNameById[userId] || userId : "—";
        const generatedAt = p.date_generated || p.created_at;
        const packageType = p.package_type || "—";
        const locationText = p.locations || p.proposal_data?.locations_text || p.location || "—";
        const totalAmount =
          p.total_amount ||
          (p.total_amount_value != null
            ? `${p.currency || ""} ${Number(p.total_amount_value).toLocaleString()}`
            : "—");
        const fileEntries = [];
        if (p.pptx_url) fileEntries.push({ url: p.pptx_url, type: "pptx" });
        if (p.pdf_url) fileEntries.push({ url: p.pdf_url, type: "pdf" });
        if (!fileEntries.length && p.file_url) fileEntries.push({ url: p.file_url, type: "pdf" });
        return {
          id: p.id || p.file_url || idx,
          clientName,
          userName,
          generatedAt,
          packageType,
          locationText,
          totalAmount,
          fileEntries,
        };
      }),
    [visibleProposals, userNameById]
  );

  const packageOptions = useMemo(() => {
    const set = new Set();
    proposals.forEach((p) => {
      if (p.packageType && p.packageType !== "—") set.add(p.packageType);
    });
    return Array.from(set);
  }, [proposals]);

  const locationOptions = useMemo(() => {
    const set = new Set();
    proposals.forEach((p) => {
      if (!p.locationText || p.locationText === "—") return;
      p.locationText.split(",").forEach((part) => {
        const value = part.trim();
        if (value) set.add(value);
      });
    });
    return Array.from(set);
  }, [proposals]);
  const packageSelectOptions = useMemo(
    () => [{ value: "", label: "All packages" }, ...packageOptions.map((value) => ({ value, label: value }))],
    [packageOptions]
  );
  const locationSelectOptions = useMemo(
    () => [{ value: "", label: "All locations" }, ...locationOptions.map((value) => ({ value, label: value }))],
    [locationOptions]
  );

  const filteredProposals = useMemo(() => {
    const needle = searchTerm.trim().toLowerCase();
    return proposals.filter((p) => {
      if (packageFilter && p.packageType !== packageFilter) return false;
      if (locationFilter) {
        const locations = (p.locationText || "")
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean);
        if (!locations.includes(locationFilter)) return false;
      }
      if (needle) {
        const haystack = `${p.clientName} ${p.locationText}`.toLowerCase();
        if (!haystack.includes(needle)) return false;
      }
      return true;
    });
  }, [proposals, packageFilter, locationFilter, searchTerm]);

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="space-y-2">
        <CardTitle>History</CardTitle>
      </CardHeader>
      <CardContent className="flex-1 min-h-0 flex flex-col">
        {historyQuery.isLoading || userNamesLoading ? (
          <LoadingEllipsis text="Loading" className="text-sm text-black/60 dark:text-white/65" />
        ) : visibleProposals?.length ? (
          <div className="flex-1 min-h-0 flex flex-col gap-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <SearchInput
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full sm:w-[260px]"
                placeholder="Search..."
              />
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-end">
                <SelectDropdown
                  value={packageFilter}
                  options={packageSelectOptions}
                  onChange={setPackageFilter}
                  className="sm:w-[200px]"
                />
                <SelectDropdown
                  value={locationFilter}
                  options={locationSelectOptions}
                  onChange={setLocationFilter}
                  className="sm:w-[220px]"
                />
              </div>
            </div>
            <div className="flex-1 min-h-0 rounded-2xl border border-black/5 dark:border-white/10 bg-white/40 dark:bg-white/5 w-full min-w-0 overflow-hidden">
              <div className="h-full w-full min-w-0 overflow-auto">
                <table className="min-w-[760px] w-full text-sm">
                  <thead className="bg-white dark:bg-neutral-900 text-xs uppercase tracking-wide text-black/45 dark:text-white/50 sticky top-0 z-10">
                    <tr>
                      <th className="sticky top-0 z-10 px-4 py-3 text-left font-semibold bg-white dark:bg-neutral-900">Client</th>
                      <th className="sticky top-0 z-10 px-4 py-3 text-left font-semibold bg-white dark:bg-neutral-900">Locations</th>
                      <th className="sticky top-0 z-10 px-4 py-3 text-left font-semibold bg-white dark:bg-neutral-900">Amount</th>
                      <th className="sticky top-0 z-10 px-4 py-3 text-left font-semibold bg-white dark:bg-neutral-900">User</th>
                      <th className="sticky top-0 z-10 px-4 py-3 text-left font-semibold bg-white dark:bg-neutral-900">Generated</th>
                      <th className="sticky top-0 right-0 z-20 px-4 py-3 text-left font-semibold bg-white dark:bg-neutral-900">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-black/5 dark:divide-white/10">
                    {(filteredProposals || []).map((p) => {
                      return (
                        <tr key={p.id} className="text-black/80 dark:text-white/85">
                          <td className="px-4 py-3 font-semibold">{p.clientName}</td>
                          <td className="px-4 py-3">{p.locationText}</td>
                          <td className="px-4 py-3">{p.totalAmount}</td>
                          <td className="px-4 py-3">{p.userName}</td>
                          <td className="px-4 py-3">
                            {p.generatedAt ? new Date(p.generatedAt).toLocaleString() : "—"}
                          </td>
                          <td className="sticky right-0 z-10 px-4 py-3 bg-white/90 dark:bg-neutral-900/95">
                            {p.fileEntries.length ? (
                              <div className="flex flex-col gap-2">
                                {p.fileEntries.map((file) => {
                                  const resolvedUrl = resolveProposalUrl(file.url);
                                  const nameFromUrl = getNameFromUrl(resolvedUrl);
                                  const fallbackName = file.type === "pdf" ? "proposal.pdf" : "proposal.pptx";
                                  const displayName = nameFromUrl || fallbackName;
                                  return (
                                    <div key={`${file.type}-${file.url}`} className="flex flex-wrap items-center gap-2">
                                      <span className="text-[11px] uppercase tracking-wide text-black/50 dark:text-white/60">
                                        {file.type}
                                      </span>
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
                                  );
                                })}
                              </div>
                            ) : (
                              <span className="text-xs text-black/50 dark:text-white/55">—</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
            {!filteredProposals.length ? (
              <div className="text-sm text-black/60 dark:text-white/65">No matching proposals.</div>
            ) : null}
          </div>
        ) : (
          <div className="text-sm text-black/60 dark:text-white/65">No proposals yet.</div>
        )}
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

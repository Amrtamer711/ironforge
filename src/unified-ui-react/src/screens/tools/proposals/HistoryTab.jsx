import React, { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import * as proposalsApi from "../../../api/proposals";
import * as adminApi from "../../../api/admin";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { SoftCard } from "../../../components/ui/soft-card";
import { LoadingEllipsis } from "../../../components/ui/loading-ellipsis";
import { useAuth } from "../../../state/auth";

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

  const visibleProposals = useMemo(() => {
    const list = proposals || [];
    const userId = user?.id || user?.user_id || user?.email || "";
    if (!userId) return list;
    return list.filter((p) => {
      const owner = p.submitted_by || p.user_id || "";
      return owner === userId;
    });
  }, [proposals, user?.id, user?.user_id, user?.email]);

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
  return (
    <Card>
      <CardHeader>
        <CardTitle>History</CardTitle>
      </CardHeader>
      <CardContent>
        {historyQuery.isLoading || userNamesLoading ? (
          <LoadingEllipsis text="Loading" className="text-sm text-black/60 dark:text-white/65" />
        ) : (
          <div className="space-y-2">
            {(visibleProposals || []).map((p, idx) => {
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

              return (
                <SoftCard key={p.id || p.file_url || idx} className="p-3">
                  <div className="text-base font-semibold">{clientName}</div>
                  <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-xs text-black/65 dark:text-white/65">
                    <div className="flex flex-wrap items-baseline gap-1">
                      <span className="uppercase tracking-wide text-xs text-black/45 dark:text-white/50">User</span>
                      <span className="font-semibold text-black/80 dark:text-white/85">{userName}</span>
                    </div>
                    <div className="flex flex-wrap items-baseline gap-1">
                      <span className="uppercase tracking-wide text-xs text-black/45 dark:text-white/50">
                        Generated
                      </span>
                      <span className="font-semibold text-black/80 dark:text-white/85">
                        {generatedAt ? new Date(generatedAt).toLocaleString() : "—"}
                      </span>
                    </div>
                    <div className="flex flex-wrap items-baseline gap-1">
                      <span className="uppercase tracking-wide text-xs text-black/45 dark:text-white/50">
                        Package Type
                      </span>
                      <span className="font-semibold text-black/80 dark:text-white/85">{packageType}</span>
                    </div>
                    <div className="flex flex-wrap items-baseline gap-1">
                      <span className="uppercase tracking-wide text-xs text-black/45 dark:text-white/50">
                        Total Amount
                      </span>
                      <span className="font-semibold text-black/80 dark:text-white/85">{totalAmount}</span>
                    </div>
                    <div className="flex flex-wrap items-baseline gap-1 sm:col-span-2">
                      <span className="uppercase tracking-wide text-xs text-black/45 dark:text-white/50">
                        Locations
                      </span>
                      <span className="font-semibold text-black/80 dark:text-white/85">{locationText}</span>
                    </div>
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
                </SoftCard>
              );
            })}
            {!visibleProposals?.length ? (
              <div className="text-sm text-black/60 dark:text-white/65">No proposals yet.</div>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

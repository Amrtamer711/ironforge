import React, { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import * as mockupApi from "../../../api/mockup";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { SoftCard } from "../../../components/ui/soft-card";
import { LoadingEllipsis } from "../../../components/ui/loading-ellipsis";

function useHistoryActions({ enabled }) {
  const historyQuery = useQuery({
    queryKey: ["mockup", "history"],
    queryFn: mockupApi.getHistory,
    enabled,
  });

  const historyItems = useMemo(() => {
    if (Array.isArray(historyQuery.data)) return historyQuery.data;
    if (historyQuery.data?.history) return historyQuery.data.history;
    if (historyQuery.data?.mockups) return historyQuery.data.mockups;
    if (historyQuery.data?.items) return historyQuery.data.items;
    return historyQuery.data || [];
  }, [historyQuery.data]);

  return { historyQuery, historyItems };
}

export function HistoryPanel(props) {
  const state = useHistoryActions(props);
  return <HistoryTab {...state} />;
}

export function HistoryTab({ historyQuery, historyItems }) {
  return (
    <Card className="h-full flex flex-col">
          <CardHeader>
            <CardTitle>History</CardTitle>
          </CardHeader>
          <CardContent className="flex-1 min-h-0 overflow-y-auto">
        {historyQuery.isLoading ? (
          <LoadingEllipsis text="Loading" className="text-sm text-black/60 dark:text-white/65" />
        ) : historyQuery.isError ? (
          <div className="text-sm text-black/60 dark:text-white/65">Unable to load history right now.</div>
        ) : (
          <div className="space-y-2">
            {(historyItems || []).map((item, idx) => {
              const imageUrl =
                item.image_url ||
                item.mockup_url ||
                item.result_url ||
                item.file_url ||
                item.url ||
                item.image ||
                "";
              const locationLabel =
                item.location_name ||
                item.location ||
                item.location_key ||
                item.location_id ||
                "Mockup";
              const timeLabel = item.time_of_day || item.timeOfDay || "";
              const sideLabel = item.side || item.billboard_side || "";
              const createdAt = item.created_at || item.generated_at || item.date_generated || "";
              const downloadName = ["mockup", locationLabel || "result", timeLabel || "all", sideLabel || "all"]
                .filter(Boolean)
                .join("_");

              return (
                <SoftCard key={item.id || item.file_id || imageUrl || idx} className="p-3 space-y-2">
                  {imageUrl ? (
                    <div className="overflow-hidden rounded-xl border border-black/5 dark:border-white/10 bg-black/5">
                      <img src={imageUrl} alt={locationLabel} className="w-full h-40 object-cover" loading="lazy" />
                    </div>
                  ) : (
                    <div className="rounded-xl border border-dashed border-black/10 dark:border-white/15 px-3 py-6 text-sm text-black/60 dark:text-white/65 text-center">
                      Preview not available
                    </div>
                  )}
                  <div className="text-base font-semibold">{locationLabel}</div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-xs text-black/65 dark:text-white/65">
                    {createdAt ? (
                      <div className="flex flex-wrap items-baseline gap-1">
                        <span className="uppercase tracking-wide text-xs text-black/45 dark:text-white/50">
                          Generated
                        </span>
                        <span className="font-semibold text-black/80 dark:text-white/85">
                          {new Date(createdAt).toLocaleString()}
                        </span>
                      </div>
                    ) : null}
                    {timeLabel ? (
                      <div className="flex flex-wrap items-baseline gap-1">
                        <span className="uppercase tracking-wide text-xs text-black/45 dark:text-white/50">
                          Time of Day
                        </span>
                        <span className="font-semibold text-black/80 dark:text-white/85">{timeLabel}</span>
                      </div>
                    ) : null}
                    {sideLabel ? (
                      <div className="flex flex-wrap items-baseline gap-1">
                        <span className="uppercase tracking-wide text-xs text-black/45 dark:text-white/50">Side</span>
                        <span className="font-semibold text-black/80 dark:text-white/85">{sideLabel}</span>
                      </div>
                    ) : null}
                  </div>
                  {imageUrl ? (
                    <div className="flex flex-wrap gap-2">
                      <Button asChild size="sm" variant="ghost" className="rounded-xl">
                        <a href={imageUrl} target="_blank" rel="noopener noreferrer">
                          Open
                        </a>
                      </Button>
                      <Button asChild size="sm" variant="secondary" className="rounded-xl">
                        <a href={imageUrl} download={downloadName}>
                          Download
                        </a>
                      </Button>
                    </div>
                  ) : null}
                </SoftCard>
              );
            })}
            {!historyItems?.length ? (
              <div className="text-sm text-black/60 dark:text-white/65">No mockups yet.</div>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

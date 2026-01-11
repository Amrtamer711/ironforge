import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as chatApi from "../api/chat";

const PREFETCH_SIZE = 50;  // Align with pagination (50 messages/page)
const URL_REFRESH_INTERVAL = 5 * 60 * 1000;  // Check every 5 minutes
const URL_REFRESH_BUFFER = 2 * 3600 * 1000;  // Refresh 2 hours before expiry

/**
 * Hook for lazy-loading attachment URLs with pre-fetching and TTL management.
 *
 * Features:
 * - Lazy loads attachment URLs when they become visible
 * - Prefetches next 50 attachments (aligned with pagination)
 * - Tracks URL expiry and auto-refreshes before expiration
 * - Supports thumbnail + full image URLs with dimensions
 *
 * @param {string[]} allFileIds - All attachment file_ids from history (for pre-fetch calculation)
 * @returns {{ urls: Record<string, object>, loadAttachments: (fileIds: string[]) => Promise<void>, isLoading: boolean }}
 */
export function useAttachmentLoader(allFileIds = []) {
  const [urls, setUrls] = useState({});
  // urls structure: {
  //   file_id: {
  //     thumbnail: "https://...",
  //     full: "https://...",
  //     width: 1920,
  //     height: 1080,
  //     fetchedAt: 1704067200000,
  //     expiresAt: 1704153600000  // fetchedAt + 24h
  //   }
  // }

  const [isLoading, setIsLoading] = useState(false);
  const loadedRef = useRef(new Set());
  const pendingRef = useRef(new Set());

  // O(1) index lookup map instead of O(n) indexOf calls
  const fileIdIndexMap = useMemo(() => {
    const map = new Map();
    allFileIds.forEach((id, idx) => map.set(id, idx));
    return map;
  }, [allFileIds]);

  const loadAttachments = useCallback(
    async (visibleFileIds) => {
      // Filter out already loaded or pending
      const needLoad = visibleFileIds.filter(
        (id) => !loadedRef.current.has(id) && !pendingRef.current.has(id)
      );

      if (needLoad.length === 0) return;

      // Mark as pending
      needLoad.forEach((id) => pendingRef.current.add(id));

      // Calculate prefetch (align with pagination: next 50 messages)
      let maxVisibleIdx = -1;
      for (const id of visibleFileIds) {
        const idx = fileIdIndexMap.get(id);
        if (idx !== undefined && idx > maxVisibleIdx) {
          maxVisibleIdx = idx;
        }
      }

      const currentPage = Math.floor(maxVisibleIdx / PREFETCH_SIZE);
      const nextPageStart = (currentPage + 1) * PREFETCH_SIZE;
      const nextPageEnd = nextPageStart + PREFETCH_SIZE;

      const prefetchIds = allFileIds
        .slice(nextPageStart, nextPageEnd)
        .filter((id) => !loadedRef.current.has(id) && !pendingRef.current.has(id));

      try {
        setIsLoading(true);
        const result = await chatApi.refreshAttachmentUrls(needLoad, prefetchIds);

        if (result?.urls) {
          const now = Date.now();
          const enrichedUrls = {};

          // Add TTL tracking to each URL
          Object.entries(result.urls).forEach(([id, urlData]) => {
            enrichedUrls[id] = {
              ...urlData,
              fetchedAt: now,
              expiresAt: now + 24 * 3600 * 1000  // 24h expiry
            };
          });

          // Update state with new URLs
          setUrls((prev) => ({ ...prev, ...enrichedUrls }));

          // Mark as loaded
          Object.keys(enrichedUrls).forEach((id) => {
            loadedRef.current.add(id);
            pendingRef.current.delete(id);
          });
        }
      } catch (err) {
        console.error("[AttachmentLoader] Failed to refresh URLs:", err);
        // Remove from pending on error so retry is possible
        needLoad.forEach((id) => pendingRef.current.delete(id));
      } finally {
        setIsLoading(false);
      }
    },
    [allFileIds, fileIdIndexMap]
  );

  // Background URL refresh for expiring URLs
  useEffect(() => {
    const refreshInterval = setInterval(() => {
      const now = Date.now();

      // Find URLs that will expire soon (within 2 hours)
      const expiringSoon = Object.entries(urls)
        .filter(([_, data]) => data.expiresAt && (data.expiresAt - now) < URL_REFRESH_BUFFER)
        .map(([fileId]) => fileId);

      if (expiringSoon.length > 0) {
        console.log(`[AttachmentLoader] Refreshing ${expiringSoon.length} expiring URLs`);
        loadAttachments(expiringSoon);
      }
    }, URL_REFRESH_INTERVAL);

    return () => clearInterval(refreshInterval);
  }, [urls, loadAttachments]);

  return { urls, loadAttachments, isLoading };
}

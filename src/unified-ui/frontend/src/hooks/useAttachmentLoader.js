import { useCallback, useRef, useState } from "react";
import * as chatApi from "../api/chat";

const PREFETCH_SIZE = 20;

/**
 * Hook for lazy-loading attachment URLs with pre-fetching.
 * When attachments become visible, call loadAttachments() with their file_ids.
 * The hook will automatically pre-fetch the next batch.
 *
 * @param {string[]} allFileIds - All attachment file_ids from history (for pre-fetch calculation)
 * @returns {{ urls: Record<string, string>, loadAttachments: (fileIds: string[]) => Promise<void>, isLoading: boolean }}
 */
export function useAttachmentLoader(allFileIds = []) {
  const [urls, setUrls] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const loadedRef = useRef(new Set());
  const pendingRef = useRef(new Set());

  const loadAttachments = useCallback(
    async (visibleFileIds) => {
      // Filter out already loaded or pending
      const needLoad = visibleFileIds.filter(
        (id) => !loadedRef.current.has(id) && !pendingRef.current.has(id)
      );

      if (needLoad.length === 0) return;

      // Mark as pending
      needLoad.forEach((id) => pendingRef.current.add(id));

      // Calculate prefetch IDs (next batch not yet loaded)
      const lastVisibleIndex = Math.max(
        ...visibleFileIds.map((id) => allFileIds.indexOf(id)).filter((i) => i >= 0),
        -1
      );
      const prefetchIds =
        lastVisibleIndex >= 0
          ? allFileIds
              .slice(lastVisibleIndex + 1, lastVisibleIndex + 1 + PREFETCH_SIZE)
              .filter((id) => !loadedRef.current.has(id) && !pendingRef.current.has(id))
          : [];

      try {
        setIsLoading(true);
        const result = await chatApi.refreshAttachmentUrls(needLoad, prefetchIds);

        if (result?.urls) {
          // Update state with new URLs
          setUrls((prev) => ({ ...prev, ...result.urls }));

          // Mark as loaded
          Object.keys(result.urls).forEach((id) => {
            loadedRef.current.add(id);
            pendingRef.current.delete(id);
          });
        }
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error("[AttachmentLoader] Failed to refresh URLs:", err);
        // Remove from pending on error so retry is possible
        needLoad.forEach((id) => pendingRef.current.delete(id));
      } finally {
        setIsLoading(false);
      }
    },
    [allFileIds]
  );

  return { urls, loadAttachments, isLoading };
}

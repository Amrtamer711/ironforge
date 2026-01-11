import { useEffect, useRef } from 'react';

/**
 * Hook for prefetching images into browser cache.
 *
 * Downloads actual image bytes (not just URLs) for instant rendering
 * when they become visible. Implements queue management with throttling.
 *
 * Features:
 * - Batch processing (3 images in parallel)
 * - Throttling (3 images per second to avoid network congestion)
 * - Thumbnail priority (load thumbnails first, full images delayed)
 * - Deduplication (doesn't re-fetch already prefetched images)
 *
 * @param {Array<{fileId: string, thumbnailUrl: string, fullUrl: string}>} urlsToPreload
 */
export function useImagePrefetch(urlsToPreload = []) {
  const prefetchedRef = useRef(new Set());
  const queueRef = useRef([]);
  const isProcessingRef = useRef(false);

  useEffect(() => {
    // Filter out already prefetched
    const newUrls = urlsToPreload.filter(
      ({ fileId }) => !prefetchedRef.current.has(fileId)
    );

    if (newUrls.length === 0) return;

    // Add to queue
    queueRef.current.push(...newUrls);

    // Start processing if not already running
    if (!isProcessingRef.current) {
      processQueue();
    }

    async function processQueue() {
      isProcessingRef.current = true;

      while (queueRef.current.length > 0) {
        // Process 3 images in parallel (batch processing)
        const batch = queueRef.current.splice(0, 3);

        await Promise.all(
          batch.map(async ({ fileId, thumbnailUrl, fullUrl }) => {
            try {
              // Phase 1: Prefetch thumbnail (high priority)
              if (thumbnailUrl) {
                const thumbResp = await fetch(thumbnailUrl);
                await thumbResp.blob();  // Force download into browser cache
                console.log(`[Prefetch] Downloaded thumbnail for ${fileId}`);
              }

              // Phase 2: Prefetch full image (lower priority, delayed)
              if (fullUrl) {
                setTimeout(async () => {
                  try {
                    const fullResp = await fetch(fullUrl);
                    await fullResp.blob();  // Force download into browser cache
                    console.log(`[Prefetch] Downloaded full image for ${fileId}`);
                  } catch (err) {
                    console.warn(`[Prefetch] Failed to download full image for ${fileId}:`, err);
                  }
                }, 2000);  // 2 second delay for full images
              }

              // Mark as prefetched
              prefetchedRef.current.add(fileId);
            } catch (err) {
              console.warn(`[Prefetch] Failed to download thumbnail for ${fileId}:`, err);
            }
          })
        );

        // Throttle: Wait 1 second between batches (3 images per second max)
        if (queueRef.current.length > 0) {
          await new Promise(resolve => setTimeout(resolve, 1000));
        }
      }

      isProcessingRef.current = false;
    }
  }, [urlsToPreload]);
}

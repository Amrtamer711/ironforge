import React from "react";
import { X } from "lucide-react";
import { useNotifications } from "../../hooks/useNotifications";
import { SoftCard } from "./soft-card";

export function NotificationsToastStack() {
  const { toasts, dismissToast, formatTime } = useNotifications();

  if (!toasts.length) return null;

  return (
    <div className="fixed right-6 top-24 z-50 flex w-[320px] flex-col gap-2">
      {toasts.map((toast) => {
        const item = toast.notification;
        return (
          <SoftCard
            key={toast.id}
            className="p-3 bg-white dark:bg-neutral-900 shadow-soft ring-1 ring-black/10 dark:ring-white/10"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="text-sm font-semibold text-black/85 dark:text-white/85 truncate">
                  {item.title || "Notification"}
                </div>
                {item.message ? (
                  <div className="mt-1 text-xs text-black/60 dark:text-white/65 leading-4 mmg-line-clamp-2">
                    {item.message}
                  </div>
                ) : null}
                {item.created_at ? (
                  <div className="mt-1 text-[11px] text-black/45 dark:text-white/45">
                    {formatTime(item.created_at)}
                  </div>
                ) : null}
              </div>
              <button
                type="button"
                className="rounded-full p-1 text-black/50 hover:text-black/80 dark:text-white/50 dark:hover:text-white/80"
                onClick={() => dismissToast(toast.id)}
                aria-label="Dismiss notification"
              >
                <X size={14} />
              </button>
            </div>
          </SoftCard>
        );
      })}
    </div>
  );
}

import React, { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, Eye, X } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./dropdown-menu";
import { Button } from "./button";
import { IconActionButton } from "./icon-action-button";
import { Modal } from "./modal";
import { useNotifications } from "../../hooks/useNotifications";
import { cn } from "../../lib/utils";

function NotificationDetails({ notification }) {
  if (!notification) return null;
  return (
    <div className="space-y-3 text-sm text-black/70 dark:text-white/70">
      {notification.message ? <div>{notification.message}</div> : <div>No additional details.</div>}
      {notification.meta?.details ? (
        <div className="rounded-xl bg-black/5 dark:bg-white/10 p-3 text-xs whitespace-pre-wrap">
          {notification.meta.details}
        </div>
      ) : null}
    </div>
  );
}

export function NotificationsBell() {
  const nav = useNavigate();
  const {
    notifications,
    unreadCount,
    clearAll,
    dismissNotification,
    markRead,
    formatTime,
  } = useNotifications();
  const [activeNotification, setActiveNotification] = useState(null);

  const recent = useMemo(() => notifications.slice(0, 6), [notifications]);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            className="relative flex h-9 w-9 items-center justify-center rounded-2xl bg-black/5 dark:bg-white/10 text-black/80 dark:text-white/80 shadow-soft"
            aria-label="Notifications"
          >
            <Bell size={18} />
            {unreadCount ? (
              <span className="absolute -right-1 -top-1 min-w-[18px] rounded-full bg-rose-500 px-1 text-[11px] font-semibold leading-4 text-white">
                {unreadCount > 99 ? "99+" : unreadCount}
              </span>
            ) : null}
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="end"
          className="w-[320px] p-0 bg-white/90 dark:bg-neutral-900/85"
        >
          <div className="flex items-center justify-between px-3 py-2">
            <div>
              <div className="text-sm font-semibold">Notifications</div>
              <div className="text-xs text-black/50 dark:text-white/55">
                {notifications.length ? `${notifications.length} total` : "No alerts"}
              </div>
            </div>
            <Button
              variant="secondary"
              size="sm"
              className="rounded-xl"
              onClick={clearAll}
              disabled={!notifications.length}
            >
              Clear all
            </Button>
          </div>
          <DropdownMenuSeparator />
          <div className="max-h-[320px] overflow-y-auto p-2 space-y-2">
            {!recent.length ? (
              <div className="rounded-xl border border-dashed border-black/10 dark:border-white/15 p-4 text-xs text-black/50 dark:text-white/60 text-center">
                You're all caught up.
              </div>
            ) : (
              recent.map((notification) => (
                <div
                  key={notification.id}
                  className={cn(
                    "rounded-xl px-3 py-2 ring-1 transition-colors",
                    notification.read
                      ? "bg-white/50 dark:bg-white/5 ring-black/5 dark:ring-white/10"
                      : "bg-black/5 dark:bg-white/10 ring-black/10 dark:ring-white/20"
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-black/85 dark:text-white/85 truncate">
                        {notification.title || "Notification"}
                      </div>
                      {notification.message ? (
                        <div className="mt-0.5 text-xs text-black/60 dark:text-white/65 leading-4 mmg-line-clamp-2">
                          {notification.message}
                        </div>
                      ) : null}
                      {notification.created_at ? (
                        <div className="mt-1 text-[11px] text-black/45 dark:text-white/45">
                          {formatTime(notification.created_at)}
                        </div>
                      ) : null}
                    </div>
                    <div className="flex flex-col items-center gap-2">
                      <IconActionButton
                        variant="ghost"
                        className="h-7 w-7"
                        onClick={() => dismissNotification(notification.id)}
                        aria-label="Dismiss notification"
                      >
                        <X size={14} />
                      </IconActionButton>
                      <IconActionButton
                        variant="ghost"
                        className="h-7 w-7"
                        onClick={() => {
                          markRead(notification.id);
                          setActiveNotification(notification);
                        }}
                        aria-label="View notification"
                      >
                        <Eye size={14} />
                      </IconActionButton>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
          <DropdownMenuSeparator />
          <div className="px-3 py-2">
            <Button
              variant="secondary"
              className="w-full rounded-2xl"
              onClick={() => nav("/app/notifications")}
            >
              View all notifications
            </Button>
          </div>
        </DropdownMenuContent>
      </DropdownMenu>

      <Modal
        open={Boolean(activeNotification)}
        onClose={() => setActiveNotification(null)}
        title={activeNotification?.title || "Notification"}
        maxWidth="520px"
      >
        <NotificationDetails notification={activeNotification} />
      </Modal>
    </>
  );
}

import React, { useMemo, useState } from "react";
import { Eye, X } from "lucide-react";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { IconActionButton } from "../../components/ui/icon-action-button";
import { Modal } from "../../components/ui/modal";
import { SoftCard } from "../../components/ui/soft-card";
import { LoadingEllipsis } from "../../components/ui/loading-ellipsis";
import { useNotifications } from "../../hooks/useNotifications";

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

export function NotificationsPage() {
  const {
    notifications,
    loading,
    clearAll,
    dismissNotification,
    markRead,
    formatTime,
  } = useNotifications();
  const [activeNotification, setActiveNotification] = useState(null);

  const items = useMemo(() => notifications, [notifications]);

  return (
    <div className="h-full min-h-0">
      <Card className="h-full flex flex-col">
        <CardHeader className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle>Notifications</CardTitle>
            <div className="text-xs text-black/50 dark:text-white/55">
              {items.length ? `${items.length} total` : "No alerts yet"}
            </div>
          </div>
          <Button variant="secondary" className="rounded-2xl" onClick={clearAll} disabled={!items.length}>
            Clear all
          </Button>
        </CardHeader>
        <CardContent className="flex-1 min-h-0 overflow-y-auto pt-2">
          {loading ? (
            <LoadingEllipsis text="Loading" className="text-sm text-black/60 dark:text-white/65" />
          ) : items.length ? (
            <div className="space-y-2">
              {items.map((notification) => (
                <SoftCard key={notification.id} className="p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-base font-semibold text-black/85 dark:text-white/85 truncate">
                        {notification.title || "Notification"}
                      </div>
                      {notification.message ? (
                        <div className="mt-1 text-sm text-black/60 dark:text-white/65 leading-5 mmg-line-clamp-2">
                          {notification.message}
                        </div>
                      ) : null}
                      {notification.created_at ? (
                        <div className="mt-1 text-xs text-black/45 dark:text-white/45">
                          {formatTime(notification.created_at)}
                        </div>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-2">
                      <IconActionButton
                        variant="ghost"
                        className="h-8 w-8"
                        onClick={() => {
                          markRead(notification.id);
                          setActiveNotification(notification);
                        }}
                        aria-label="View notification"
                      >
                        <Eye size={14} />
                      </IconActionButton>
                      <IconActionButton
                        variant="ghost"
                        className="h-8 w-8"
                        onClick={() => dismissNotification(notification.id)}
                        aria-label="Close notification"
                      >
                        <X size={14} />
                      </IconActionButton>
                    </div>
                  </div>
                </SoftCard>
              ))}
            </div>
          ) : (
            <SoftCard className="p-6 text-center text-sm text-black/60 dark:text-white/65">
              You're all caught up.
            </SoftCard>
          )}
        </CardContent>
      </Card>

      <Modal
        open={Boolean(activeNotification)}
        onClose={() => setActiveNotification(null)}
        title={activeNotification?.title || "Notification"}
        maxWidth="520px"
      >
        <NotificationDetails notification={activeNotification} />
      </Modal>
    </div>
  );
}

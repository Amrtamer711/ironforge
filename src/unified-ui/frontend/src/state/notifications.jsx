import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { notificationsApi } from "../api";
import { NotificationsContext } from "./notifications-context";

function playNotificationSound() {
  if (typeof window === "undefined") return;
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 740;
    gain.gain.value = 0.15;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
    osc.stop(ctx.currentTime + 0.3);
    osc.onended = () => {
      ctx.close();
    };
  } catch {
    // ignore audio errors
  }
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
}

export function NotificationsProvider({ children }) {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [toasts, setToasts] = useState([]);
  const seenIdsRef = useRef(new Set());
  const didInitRef = useRef(false);
  const toastTimers = useRef(new Map());

  const loadNotifications = useCallback(async () => {
    setLoading(true);
    const list = await notificationsApi.getNotifications();
    setNotifications(Array.isArray(list) ? list : []);
    setLoading(false);
  }, []);

  const clearAll = useCallback(async () => {
    await notificationsApi.clearNotifications();
    setNotifications([]);
  }, []);

  const dismissNotification = useCallback(async (id) => {
    if (!id) return;
    await notificationsApi.dismissNotification(id);
    setNotifications((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const markRead = useCallback(async (id) => {
    if (!id) return;
    await notificationsApi.markNotificationRead(id);
    setNotifications((prev) => prev.map((item) => (item.id === id ? { ...item, read: true } : item)));
  }, []);

  const addNotification = useCallback(async (payload) => {
    const notification = await notificationsApi.addNotification(payload);
    setNotifications((prev) => [notification, ...prev]);
    return notification;
  }, []);

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
    const timer = toastTimers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      toastTimers.current.delete(id);
    }
  }, []);

  const pushToast = useCallback(
    (notification) => {
      if (!notification?.id) return;
      setToasts((prev) => [...prev, { id: notification.id, notification }]);
      const timer = setTimeout(() => dismissToast(notification.id), 4200);
      toastTimers.current.set(notification.id, timer);
    },
    [dismissToast]
  );

  useEffect(() => {
    loadNotifications();
  }, [loadNotifications]);

  useEffect(() => {
    if (!didInitRef.current) {
      notifications.forEach((item) => seenIdsRef.current.add(item.id));
      didInitRef.current = true;
      return;
    }
    const nextItems = notifications.filter((item) => item.id && !seenIdsRef.current.has(item.id));
    if (nextItems.length) {
      playNotificationSound();
      nextItems.forEach((item) => {
        seenIdsRef.current.add(item.id);
        pushToast(item);
      });
    }
  }, [notifications, pushToast]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const handleStorage = (event) => {
      if (event.key !== notificationsApi.NOTIFICATIONS_STORAGE_KEY) return;
      loadNotifications();
    };
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, [loadNotifications]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.mmgNotify = (payload) => addNotification(payload);
    window.mmgNotifications = {
      add: (payload) => addNotification(payload),
      clear: clearAll,
      dismiss: dismissNotification,
      markRead,
    };
    return () => {
      delete window.mmgNotify;
      delete window.mmgNotifications;
    };
  }, [addNotification, clearAll, dismissNotification, markRead]);

  const unreadCount = useMemo(
    () => notifications.filter((item) => !item.read).length,
    [notifications]
  );

  const value = useMemo(
    () => ({
      notifications,
      loading,
      unreadCount,
      toasts,
      addNotification,
      clearAll,
      dismissNotification,
      markRead,
      dismissToast,
      formatTime,
    }),
    [
      notifications,
      loading,
      unreadCount,
      toasts,
      addNotification,
      clearAll,
      dismissNotification,
      markRead,
      dismissToast,
    ]
  );

  return <NotificationsContext.Provider value={value}>{children}</NotificationsContext.Provider>;
}

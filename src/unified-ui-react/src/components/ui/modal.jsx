import React from "react";
import { Button } from "./button";

export function Modal({ open, onClose, title, children, maxWidth = "520px" }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start sm:items-center justify-center bg-black/40 backdrop-blur-sm px-4 py-6 overflow-y-auto">
      <div className="w-full" style={{ maxWidth }}>
        <div className="rounded-2xl bg-white/90 dark:bg-neutral-900/95 shadow-2xl ring-1 ring-black/10 dark:ring-white/10 max-h-[85vh] flex flex-col">
          <div className="flex items-center justify-between px-4 py-2 border-b border-black/5 dark:border-white/10">
            <div className="text-sm font-semibold">{title}</div>
            <button className="text-black/60 dark:text-white/60 hover:opacity-100 opacity-70" onClick={onClose}>
              ✕
            </button>
          </div>
          <div className="p-4 overflow-y-auto">{children}</div>
        </div>
      </div>
    </div>
  );
}

export function ConfirmModal({ open, onClose, onConfirm, message }) {
  if (!open) return null;
  return (
    <Modal open={open} onClose={onClose} title="Confirm" maxWidth="420px">
      <div className="space-y-4">
        <div className="text-sm text-black/70 dark:text-white/70">{message || "Are you sure?"}</div>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" className="rounded-2xl" onClick={onClose}>
            Cancel
          </Button>
          <Button className="rounded-2xl" onClick={onConfirm}>
            Confirm
          </Button>
        </div>
      </div>
    </Modal>
  );
}

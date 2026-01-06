import React from "react";
import { createPortal } from "react-dom";
import { Button } from "./button";

export function Modal({ open, onClose, title, children, maxWidth = "520px" }) {
  if (!open) return null;
  const content = (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 backdrop-blur-sm px-4 py-6 overflow-y-auto">
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
  if (typeof document === "undefined") return content;
  return createPortal(content, document.body);
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

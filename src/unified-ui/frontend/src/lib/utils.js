import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export function parsePermissions(text) {
  return text
    .split(/\n|,/)
    .map((p) => p.trim())
    .filter(Boolean);
}

export function parsePermissionParts(value) {
  if (!value) return { module: "", service: "", action: "" };
  const [module, service, action] = value.split(":");
  return {
    module: module?.trim() || "",
    service: service?.trim() || "",
    action: action?.trim() || "",
  };
}

export function buildPermissionValue({ module, service, action }) {
  if (!module || !service || !action) return "";
  return `${module}:${service}:${action}`;
}

export function selectionLabel(count, singular, plural = `${singular}s`) {
  if (!count) return `No ${plural} selected`;
  return `${count} ${count === 1 ? singular : plural} selected`;
}

export function normalizeFrameConfig(config, defaults = {}) {
  return { ...defaults, ...(config || {}) };
}

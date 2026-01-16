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

export function buildCompanyTreeOptions(companyList, { excludeValues = [] } = {}) {
  const exclude = new Set((excludeValues || []).map((value) => String(value)).filter(Boolean));
  const byCode = new Map();
  const byId = new Map();
  const childCodes = new Set();

  companyList.forEach((company) => {
    const code = company.code || String(company.id || "");
    if (!code || exclude.has(String(code))) return;
    byCode.set(code, company);
    if (company.id != null) byId.set(company.id, company);
    (company.children || []).forEach((child) => childCodes.add(child));
  });

  const getChildren = (company) => {
    if (Array.isArray(company.children) && company.children.length) {
      return company.children
        .map((code) => byCode.get(code))
        .filter(Boolean);
    }
    if (company.id == null) return [];
    return companyList.filter((child) => {
      const childCode = child.code || String(child.id || "");
      if (exclude.has(String(childCode))) return false;
      return child.parent_id === company.id;
    });
  };

  const roots = companyList.filter((company) => {
    const code = company.code || String(company.id || "");
    if (!code || exclude.has(String(code))) return false;
    if (company.parent_id == null) return true;
    if (byId.has(company.parent_id)) return false;
    if (company.code && childCodes.has(company.code)) return false;
    return true;
  });

  const buildNode = (company) => {
    const value = company.code || company.id || "";
    if (!value || exclude.has(String(value))) return null;
    const children = getChildren(company)
      .map((child) => buildNode(child))
      .filter(Boolean);
    return {
      value,
      label: company.name || company.code || String(company.id || ""),
      children,
    };
  };

  return roots.map((root) => buildNode(root)).filter(Boolean);
}

import React, { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { Button } from "../../../components/ui/button";
import { FormField } from "../../../components/ui/form-field";
import { SearchInput } from "../../../components/ui/search-input";
import { SoftCard } from "../../../components/ui/soft-card";
import { IconActionButton } from "../../../components/ui/icon-action-button";
import { LoadingEllipsis } from "../../../components/ui/loading-ellipsis";
import { ConfirmModal, Modal } from "../../../components/ui/modal";
import { SelectDropdown } from "../../../components/ui/select-dropdown";
import { adminApi } from "../../../api";
import { buildPermissionValue, parsePermissionParts } from "../../../lib/utils";

export function PermissionsTab({
  permissionSearch,
  setPermissionSearch,
  openPermissionModal,
  permissionModuleFilter,
  setPermissionModuleFilter,
  permissionServiceFilter,
  setPermissionServiceFilter,
  permissionActionFilter,
  setPermissionActionFilter,
  permissionModuleOptions,
  permissionFilterServiceOptions,
  permissionFilterActionOptions,
  permissionsQuery,
  filteredPermissionList,
  parsePermissionParts,
  mergedPermissionDescriptions,
  setConfirmDelete,
}) {
  const moduleSelectOptions = [
    { value: "", label: "All modules" },
    ...permissionModuleOptions.map((opt) => ({ value: opt, label: opt })),
  ];
  const serviceSelectOptions = [
    { value: "", label: "All services" },
    ...permissionFilterServiceOptions.map((opt) => ({ value: opt, label: opt })),
  ];
  const actionSelectOptions = [
    { value: "", label: "All permissions" },
    ...permissionFilterActionOptions.map((opt) => ({ value: opt, label: opt })),
  ];

  return (
    <Card className="h-full min-h-0 flex flex-col">
      <CardHeader className="space-y-2">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>Permissions</CardTitle>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-end">
            <SearchInput
              value={permissionSearch}
              onChange={(e) => setPermissionSearch(e.target.value)}
              className="w-full sm:w-[220px]"
            />
            <Button
              className="rounded-2xl self-start sm:self-auto"
              variant="secondary"
              onClick={() => openPermissionModal("add", "")}
            >
              Add permission
            </Button>
          </div>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          <SelectDropdown
            value={permissionModuleFilter}
            options={moduleSelectOptions}
            onChange={setPermissionModuleFilter}
          />
          <SelectDropdown
            value={permissionServiceFilter}
            options={serviceSelectOptions}
            onChange={setPermissionServiceFilter}
          />
          <SelectDropdown
            value={permissionActionFilter}
            options={actionSelectOptions}
            onChange={setPermissionActionFilter}
            className="col-span-2 sm:col-span-1"
          />
        </div>
      </CardHeader>
      <CardContent className="flex-1 min-h-0 overflow-y-auto space-y-3 pt-2">
        {permissionsQuery.isLoading ? (
          <LoadingEllipsis text="Loading" className="text-sm text-black/60 dark:text-white/65" />
        ) : filteredPermissionList.length ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {filteredPermissionList.map((p) => {
              const parts = parsePermissionParts(p);
              const description = mergedPermissionDescriptions[p];
              return (
                <SoftCard key={p} className="p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="grid grid-cols-1 gap-1 text-sm">
                      <div className="flex flex-wrap items-baseline gap-1">
                        <span className="text-xs uppercase tracking-wide text-black/50 dark:text-white/60">Module</span>
                        <span className="font-semibold text-black/85 dark:text-white/85">{parts.module}</span>
                      </div>
                      <div className="flex flex-wrap items-baseline gap-1">
                        <span className="text-xs uppercase tracking-wide text-black/50 dark:text-white/60">
                          Service
                        </span>
                        <span className="font-semibold text-black/85 dark:text-white/85">{parts.service}</span>
                      </div>
                      <div className="flex flex-wrap items-baseline gap-1">
                        <span className="text-xs uppercase tracking-wide text-black/50 dark:text-white/60">
                          Permission
                        </span>
                        <span className="font-semibold text-black/85 dark:text-white/85">{parts.action}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <IconActionButton
                        onClick={() => openPermissionModal("edit", p)}
                        title="Edit permission"
                        aria-label="Edit permission"
                      >
                        <Pencil size={16} />
                      </IconActionButton>
                      <IconActionButton
                        variant="ghost"
                        onClick={() =>
                          setConfirmDelete({
                            open: true,
                            type: "permission",
                            payload: p,
                            label: `Delete permission "${p}"?`,
                          })
                        }
                        title="Delete permission"
                        aria-label="Delete permission"
                      >
                        <Trash2 size={16} />
                      </IconActionButton>
                    </div>
                  </div>
                  {description ? (
                    <div className="mt-2 flex items-baseline gap-1 text-sm min-w-0">
                      <span className="text-xs uppercase tracking-wide text-black/50 dark:text-white/60">
                        Description
                      </span>
                      <span className="text-black/60 dark:text-white/65 truncate">{description}</span>
                    </div>
                  ) : null}
                </SoftCard>
              );
            })}
          </div>
        ) : (
          <div className="text-sm text-black/60 dark:text-white/65">
            {permissionSearch.trim() ? "No matching permissions." : "No permissions available."}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function PermissionsPanel({
  permissionSearch,
  setPermissionSearch,
  openPermissionModal: externalOpenPermissionModal,
  permissionModuleFilter,
  setPermissionModuleFilter,
  permissionServiceFilter,
  setPermissionServiceFilter,
  permissionActionFilter,
  setPermissionActionFilter,
  permissionModuleOptions,
  permissionFilterServiceOptions,
  permissionFilterActionOptions,
  permissionsQuery,
  filteredPermissionList,
  parsePermissionParts,
  mergedPermissionDescriptions,
  permissionTree,
  updateLocalPermissionDescription,
}) {
  const {
    permissionModal,
    setPermissionModal,
    permissionModalError,
    savingPermission,
    openPermissionModal,
    updatePermissionModalField,
    savePermissionModal,
    deletePermissionFromModal,
    setPermissionModalError,
  } = usePermissionModalActions({ mergedPermissionDescriptions, updateLocalPermissionDescription });
  const [confirmDelete, setConfirmDelete] = useState({ open: false, type: "", payload: null, label: "" });

  const permissionServiceOptions = permissionModal.module
    ? permissionTree.servicesByModule[permissionModal.module] || []
    : permissionTree.allServices;
  const permissionActionOptions =
    permissionModal.module && permissionModal.service
      ? permissionTree.actionsByService[`${permissionModal.module}:${permissionModal.service}`] || []
      : permissionTree.allActions;

  async function handleConfirmDelete() {
    if (!confirmDelete.open || !confirmDelete.payload) return;
    try {
      await deletePermissionFromModal(confirmDelete.payload);
    } finally {
      setConfirmDelete({ open: false, type: "", payload: null, label: "" });
    }
  }

  return (
    <>
      <PermissionsTab
        permissionSearch={permissionSearch}
        setPermissionSearch={setPermissionSearch}
        openPermissionModal={externalOpenPermissionModal || openPermissionModal}
        permissionModuleFilter={permissionModuleFilter}
        setPermissionModuleFilter={setPermissionModuleFilter}
        permissionServiceFilter={permissionServiceFilter}
        setPermissionServiceFilter={setPermissionServiceFilter}
        permissionActionFilter={permissionActionFilter}
        setPermissionActionFilter={setPermissionActionFilter}
        permissionModuleOptions={permissionModuleOptions}
        permissionFilterServiceOptions={permissionFilterServiceOptions}
        permissionFilterActionOptions={permissionFilterActionOptions}
        permissionsQuery={permissionsQuery}
        filteredPermissionList={filteredPermissionList}
        parsePermissionParts={parsePermissionParts}
        mergedPermissionDescriptions={mergedPermissionDescriptions}
        setConfirmDelete={setConfirmDelete}
      />

      <PermissionsModal
        open={permissionModal.open}
        onClose={() => {
          setPermissionModal({
            open: false,
            mode: "add",
            value: "",
            original: "",
            module: "",
            service: "",
            action: "",
            description: "",
            originalDescription: "",
          });
          setPermissionModalError("");
        }}
        permissionModal={permissionModal}
        permissionModuleOptions={permissionModuleOptions}
        permissionServiceOptions={permissionServiceOptions}
        permissionActionOptions={permissionActionOptions}
        updatePermissionModalField={updatePermissionModalField}
        permissionModalError={permissionModalError}
        savePermissionModal={savePermissionModal}
        savingPermission={savingPermission}
      />

      <ConfirmModal
        open={confirmDelete.open}
        message={confirmDelete.label}
        onClose={() => setConfirmDelete({ open: false, type: "", payload: null, label: "" })}
        onConfirm={handleConfirmDelete}
      />
    </>
  );
}

const EMPTY_PERMISSION_MODAL = {
  open: false,
  mode: "add",
  value: "",
  original: "",
  module: "",
  service: "",
  action: "",
  description: "",
  originalDescription: "",
};

function usePermissionModalActions({ mergedPermissionDescriptions, updateLocalPermissionDescription }) {
  const qc = useQueryClient();
  const [permissionModal, setPermissionModal] = useState(EMPTY_PERMISSION_MODAL);
  const [permissionModalError, setPermissionModalError] = useState("");
  const [savingPermission, setSavingPermission] = useState(false);

  function openPermissionModal(mode = "add", value = "") {
    const parts = parsePermissionParts(value);
    const desc = value ? mergedPermissionDescriptions[value] || "" : "";
    setPermissionModalError("");
    setPermissionModal({
      open: true,
      mode,
      value,
      original: value,
      module: parts.module,
      service: parts.service,
      action: parts.action,
      description: desc,
      originalDescription: desc,
    });
  }

  function updatePermissionModalField(field, nextValue) {
    setPermissionModal((prev) => {
      const updated = { ...prev, [field]: nextValue };
      return { ...updated, value: buildPermissionValue(updated) };
    });
    setPermissionModalError("");
  }

  async function savePermissionModal() {
    const value = buildPermissionValue(permissionModal);
    if (!value) {
      setPermissionModalError("Select module, service, and permission.");
      return;
    }
    setSavingPermission(true);
    try {
      const desc = permissionModal.description?.trim() || "";
      if (permissionModal.mode === "add") {
        await adminApi.addPermission(value, desc);
        updateLocalPermissionDescription(value, desc);
      } else if (value !== permissionModal.original) {
        await adminApi.addPermission(value, desc);
        await adminApi.deletePermission(permissionModal.original);
        updateLocalPermissionDescription(permissionModal.original, "");
        updateLocalPermissionDescription(value, desc);
      } else if (desc !== permissionModal.originalDescription) {
        await adminApi.addPermission(value, desc);
        updateLocalPermissionDescription(value, desc);
      } else {
        setPermissionModal({ ...EMPTY_PERMISSION_MODAL });
        return;
      }
      qc.invalidateQueries({ queryKey: ["admin", "permissions"] });
      setPermissionModal({ ...EMPTY_PERMISSION_MODAL });
    } catch {
      // ignore
    } finally {
      setSavingPermission(false);
    }
  }

  async function deletePermissionFromModal(value) {
    const target = value || permissionModal.original || permissionModal.value;
    if (!target) return;
    setSavingPermission(true);
    try {
      await adminApi.deletePermission(target);
      updateLocalPermissionDescription(target, "");
      qc.invalidateQueries({ queryKey: ["admin", "permissions"] });
      setPermissionModal({ ...EMPTY_PERMISSION_MODAL });
    } catch {
      // ignore
    } finally {
      setSavingPermission(false);
    }
  }

  return {
    permissionModal,
    setPermissionModal,
    permissionModalError,
    savingPermission,
    openPermissionModal,
    updatePermissionModalField,
    savePermissionModal,
    deletePermissionFromModal,
    setPermissionModalError,
  };
}

export function PermissionsModal({
  open,
  onClose,
  permissionModal,
  permissionModuleOptions,
  permissionServiceOptions,
  permissionActionOptions,
  updatePermissionModalField,
  permissionModalError,
  savePermissionModal,
  savingPermission,
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={permissionModal.mode === "edit" ? "Edit permission" : "Add permission"}
      maxWidth="520px"
    >
      <div className="space-y-3">
        <FormField label="Permission">
          <div className="grid grid-cols-[1fr_auto_1fr_auto_1fr] items-center gap-2">
            <div>
              <input
                list="permission-module-options"
                className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                value={permissionModal.module}
                onChange={(e) => updatePermissionModalField("module", e.target.value)}
                placeholder="module"
              />
              <datalist id="permission-module-options">
                {permissionModuleOptions.map((opt, idx) => (
                  <option key={`${opt}-${idx}`} value={opt} />
                ))}
              </datalist>
            </div>
            <span className="text-sm text-black/40 dark:text-white/40">:</span>
            <div>
              <input
                list="permission-service-options"
                className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                value={permissionModal.service}
                onChange={(e) => updatePermissionModalField("service", e.target.value)}
                placeholder="service"
              />
              <datalist id="permission-service-options">
                {permissionServiceOptions.map((opt, idx) => (
                  <option key={`${opt}-${idx}`} value={opt} />
                ))}
              </datalist>
            </div>
            <span className="text-sm text-black/40 dark:text-white/40">:</span>
            <div>
              <input
                list="permission-action-options"
                className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                value={permissionModal.action}
                onChange={(e) => updatePermissionModalField("action", e.target.value)}
                placeholder="permission"
              />
              <datalist id="permission-action-options">
                {permissionActionOptions.map((opt, idx) => (
                  <option key={`${opt}-${idx}`} value={opt} />
                ))}
              </datalist>
            </div>
          </div>
        </FormField>
        <FormField label="Description">
          <input
            className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
            value={permissionModal.description}
            onChange={(e) => updatePermissionModalField("description", e.target.value)}
            placeholder="Short description"
          />
        </FormField>
        {permissionModalError ? (
          <div className="text-xs text-red-600 dark:text-red-300">{permissionModalError}</div>
        ) : null}
        <div className="flex justify-end">
          <Button className="rounded-2xl" onClick={savePermissionModal} disabled={savingPermission}>
            {savingPermission ? (
              <LoadingEllipsis text="Saving" />
            ) : permissionModal.mode === "edit" ? (
              "Update Permission"
            ) : (
              "Add Permission"
            )}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

import React, { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, Copy, Pencil, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { Button } from "../../../components/ui/button";
import { FormField } from "../../../components/ui/form-field";
import { SearchInput } from "../../../components/ui/search-input";
import { SoftCard } from "../../../components/ui/soft-card";
import { IconActionButton } from "../../../components/ui/icon-action-button";
import { LoadingEllipsis } from "../../../components/ui/loading-ellipsis";
import { ConfirmModal, Modal } from "../../../components/ui/modal";
import { adminApi } from "../../../api";
import { cn, parsePermissions, selectionLabel } from "../../../lib/utils";

export function PermissionSetsTab({
  permissionSetSearch,
  setPermissionSetSearch,
  openPermissionSetModal,
  permissionSetsQuery,
  filteredPermissionSetList,
  duplicatePermissionSet,
  setConfirmDelete,
}) {
  return (
    <Card className="h-full min-h-0 flex flex-col">
      <CardHeader className="space-y-2">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>Permission Sets</CardTitle>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-end">
            <SearchInput
              value={permissionSetSearch}
              onChange={(e) => setPermissionSetSearch(e.target.value)}
              className="w-full sm:w-[220px]"
            />
            <Button
              variant="secondary"
              className="rounded-2xl self-start sm:self-auto"
              onClick={() => openPermissionSetModal(null)}
            >
              Add permission set
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex-1 min-h-0 overflow-y-auto space-y-4 pt-2">
        {permissionSetsQuery.isLoading ? (
          <LoadingEllipsis text="Loading" className="text-sm text-black/60 dark:text-white/65" />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {filteredPermissionSetList.map((set) => (
              <SoftCard key={set.name} className="p-4 space-y-1">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-base font-semibold">{set.display_name || set.name}</div>
                    <div className="text-sm text-black/55 dark:text-white/60">{set.name}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <IconActionButton
                      onClick={() => duplicatePermissionSet(set)}
                      title="Duplicate permission set"
                      aria-label="Duplicate permission set"
                    >
                      <Copy size={16} />
                    </IconActionButton>
                    <IconActionButton
                      onClick={() => openPermissionSetModal(set)}
                      title="Edit permission set"
                      aria-label="Edit permission set"
                    >
                      <Pencil size={16} />
                    </IconActionButton>
                    <IconActionButton
                      variant="ghost"
                      onClick={() =>
                        setConfirmDelete({
                          open: true,
                          type: "permission-set",
                          payload: set.name,
                          label: `Delete permission set "${set.display_name || set.name}"?`,
                        })
                      }
                      title="Delete permission set"
                      aria-label="Delete permission set"
                    >
                      <Trash2 size={16} />
                    </IconActionButton>
                  </div>
                </div>
                <div className="text-sm text-black/55 dark:text-white/60">
                  {(set.permissions || []).length} permission{(set.permissions || []).length === 1 ? "" : "s"}
                </div>
                {set.description ? (
                  <div className="text-sm text-black/60 dark:text-white/65 truncate">{set.description}</div>
                ) : null}
              </SoftCard>
            ))}
            {!filteredPermissionSetList.length ? (
              <div className="text-sm text-black/60 dark:text-white/65">
                {permissionSetSearch.trim() ? "No matching permission sets." : "No permission sets available."}
              </div>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function PermissionSetsPanel({
  permissionSetSearch,
  setPermissionSetSearch,
  permissionSetsQuery,
  filteredPermissionSetList,
  permissionList,
  permissionsQuery,
}) {
  const {
    permissionSetForm,
    setPermissionSetForm,
    editingPermissionSet,
    setEditingPermissionSet,
    permissionSetModalOpen,
    setPermissionSetModalOpen,
    savingPermissionSet,
    permissionSetPermissionsOpen,
    setPermissionSetPermissionsOpen,
    openPermissionSetModal,
    duplicatePermissionSet,
    savePermissionSet,
    deletePermissionSet,
    selectedPermissionSetPermissions,
    selectedPermissionSetPermissionSet,
    customPermissionSetPermissions,
    togglePermissionSetPermission,
    selectAllPermissionSetPermissions,
    clearPermissionSetPermissions,
  } = usePermissionSetActions({ permissionList });
  const [confirmDelete, setConfirmDelete] = useState({ open: false, type: "", payload: null, label: "" });

  async function handleConfirmDelete() {
    if (!confirmDelete.open || !confirmDelete.payload) return;
    try {
      await deletePermissionSet(confirmDelete.payload);
    } finally {
      setConfirmDelete({ open: false, type: "", payload: null, label: "" });
    }
  }

  return (
    <>
      <PermissionSetsTab
        permissionSetSearch={permissionSetSearch}
        setPermissionSetSearch={setPermissionSetSearch}
        openPermissionSetModal={openPermissionSetModal}
        permissionSetsQuery={permissionSetsQuery}
        filteredPermissionSetList={filteredPermissionSetList}
        duplicatePermissionSet={duplicatePermissionSet}
        setConfirmDelete={setConfirmDelete}
      />

      <PermissionSetsModal
        open={permissionSetModalOpen}
        onClose={() => {
          setPermissionSetModalOpen(false);
          setEditingPermissionSet(null);
          setPermissionSetForm({ name: "", display_name: "", description: "", permissionsText: "" });
          setPermissionSetPermissionsOpen(false);
        }}
        editingPermissionSet={editingPermissionSet}
        permissionSetForm={permissionSetForm}
        setPermissionSetForm={setPermissionSetForm}
        permissionSetPermissionsOpen={permissionSetPermissionsOpen}
        setPermissionSetPermissionsOpen={setPermissionSetPermissionsOpen}
        selectedPermissionSetPermissions={selectedPermissionSetPermissions}
        permissionList={permissionList}
        permissionsQuery={permissionsQuery}
        selectedPermissionSetPermissionSet={selectedPermissionSetPermissionSet}
        togglePermissionSetPermission={togglePermissionSetPermission}
        selectAllPermissionSetPermissions={selectAllPermissionSetPermissions}
        clearPermissionSetPermissions={clearPermissionSetPermissions}
        customPermissionSetPermissions={customPermissionSetPermissions}
        setConfirmDelete={setConfirmDelete}
        savePermissionSet={savePermissionSet}
        savingPermissionSet={savingPermissionSet}
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

function usePermissionSetActions({ permissionList }) {
  const qc = useQueryClient();
  const [permissionSetForm, setPermissionSetForm] = useState({
    name: "",
    display_name: "",
    description: "",
    permissionsText: "",
  });
  const [editingPermissionSet, setEditingPermissionSet] = useState(null);
  const [permissionSetModalOpen, setPermissionSetModalOpen] = useState(false);
  const [savingPermissionSet, setSavingPermissionSet] = useState(false);
  const [permissionSetPermissionsOpen, setPermissionSetPermissionsOpen] = useState(false);

  const selectedPermissionSetPermissions = useMemo(
    () => parsePermissions(permissionSetForm.permissionsText),
    [permissionSetForm.permissionsText]
  );
  const selectedPermissionSetPermissionSet = useMemo(
    () => new Set(selectedPermissionSetPermissions),
    [selectedPermissionSetPermissions]
  );
  const customPermissionSetPermissions = useMemo(() => {
    if (!permissionList.length) return selectedPermissionSetPermissions;
    const known = new Set(permissionList);
    return selectedPermissionSetPermissions.filter((perm) => !known.has(perm));
  }, [permissionList, selectedPermissionSetPermissions]);

  function openPermissionSetModal(set) {
    setPermissionSetPermissionsOpen(false);
    if (set) {
      setEditingPermissionSet(set.name);
      setPermissionSetForm({
        name: set.name || "",
        display_name: set.display_name || set.name || "",
        description: set.description || "",
        permissionsText: (set.permissions || [])
          .map((perm) => (typeof perm === "string" ? perm : perm?.name))
          .filter(Boolean)
          .join("\n"),
      });
    } else {
      setEditingPermissionSet(null);
      setPermissionSetForm({ name: "", display_name: "", description: "", permissionsText: "" });
    }
    setPermissionSetModalOpen(true);
  }

  function duplicatePermissionSet(set) {
    if (!set) return;
    const baseName = set.name || set.display_name || "permission_set";
    const baseDisplay = set.display_name || set.name || baseName;
    setEditingPermissionSet(null);
    setPermissionSetPermissionsOpen(false);
    setPermissionSetForm({
      name: `${baseName}_new`,
      display_name: `${baseDisplay}_new`,
      description: set.description || "",
      permissionsText: (set.permissions || [])
        .map((perm) => (typeof perm === "string" ? perm : perm?.name))
        .filter(Boolean)
        .join("\n"),
    });
    setPermissionSetModalOpen(true);
  }

  async function savePermissionSet() {
    if (!permissionSetForm.name.trim()) return;
    setSavingPermissionSet(true);
    const payload = {
      name: permissionSetForm.name.trim(),
      display_name: permissionSetForm.display_name || permissionSetForm.name.trim(),
      description: permissionSetForm.description,
      permissions: parsePermissions(permissionSetForm.permissionsText),
    };
    try {
      if (editingPermissionSet) {
        await adminApi.updatePermissionSet(editingPermissionSet, payload);
      } else {
        await adminApi.createPermissionSet(payload);
      }
      qc.invalidateQueries({ queryKey: ["admin", "permission-sets"] });
      setPermissionSetModalOpen(false);
      setEditingPermissionSet(null);
    } catch {
      // ignore
    } finally {
      setSavingPermissionSet(false);
    }
  }

  async function deletePermissionSet(name) {
    if (!name) return;
    try {
      await adminApi.deletePermissionSet(name);
      qc.invalidateQueries({ queryKey: ["admin", "permission-sets"] });
      setPermissionSetModalOpen(false);
      setEditingPermissionSet(null);
    } catch {
      // ignore
    }
  }

  function togglePermissionSetPermission(value) {
    setPermissionSetForm((f) => {
      const current = new Set(parsePermissions(f.permissionsText));
      if (current.has(value)) current.delete(value);
      else current.add(value);
      return { ...f, permissionsText: Array.from(current).join("\n") };
    });
  }

  function selectAllPermissionSetPermissions() {
    const combined = new Set([...selectedPermissionSetPermissions, ...permissionList]);
    setPermissionSetForm((f) => ({ ...f, permissionsText: Array.from(combined).join("\n") }));
  }

  function clearPermissionSetPermissions() {
    setPermissionSetForm((f) => ({ ...f, permissionsText: "" }));
  }

  return {
    permissionSetForm,
    setPermissionSetForm,
    editingPermissionSet,
    setEditingPermissionSet,
    permissionSetModalOpen,
    setPermissionSetModalOpen,
    savingPermissionSet,
    permissionSetPermissionsOpen,
    setPermissionSetPermissionsOpen,
    openPermissionSetModal,
    duplicatePermissionSet,
    savePermissionSet,
    deletePermissionSet,
    selectedPermissionSetPermissions,
    selectedPermissionSetPermissionSet,
    customPermissionSetPermissions,
    togglePermissionSetPermission,
    selectAllPermissionSetPermissions,
    clearPermissionSetPermissions,
  };
}

export function PermissionSetsModal({
  open,
  onClose,
  editingPermissionSet,
  permissionSetForm,
  setPermissionSetForm,
  permissionSetPermissionsOpen,
  setPermissionSetPermissionsOpen,
  selectedPermissionSetPermissions,
  permissionList,
  permissionsQuery,
  selectedPermissionSetPermissionSet,
  togglePermissionSetPermission,
  selectAllPermissionSetPermissions,
  clearPermissionSetPermissions,
  customPermissionSetPermissions,
  setConfirmDelete,
  savePermissionSet,
  savingPermissionSet,
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editingPermissionSet ? `Edit permission set: ${editingPermissionSet}` : "Add permission set"}
      maxWidth="640px"
    >
      <div className="space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <FormField label="Name">
            <input
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={permissionSetForm.name}
              onChange={(e) => setPermissionSetForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="sales_ops"
              disabled={Boolean(editingPermissionSet)}
            />
          </FormField>
          <FormField label="Display Name">
            <input
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={permissionSetForm.display_name}
              onChange={(e) => setPermissionSetForm((f) => ({ ...f, display_name: e.target.value }))}
              placeholder="Sales Ops"
            />
          </FormField>
        </div>
        <FormField label="Description">
          <input
            className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
            value={permissionSetForm.description}
            onChange={(e) => setPermissionSetForm((f) => ({ ...f, description: e.target.value }))}
            placeholder="What this permission set grants"
          />
        </FormField>
        <FormField label="Permissions">
          <SoftCard className="p-4">
            <button
              type="button"
              className="flex w-full items-center justify-between gap-3 text-left"
              onClick={() => setPermissionSetPermissionsOpen((openValue) => !openValue)}
              aria-expanded={permissionSetPermissionsOpen}
            >
              <div>
                <div className="text-sm font-semibold text-black/80 dark:text-white/85">Permissions</div>
                <div className="text-xs text-black/55 dark:text-white/60">
                  {selectionLabel(selectedPermissionSetPermissions.length, "permission")}
                </div>
              </div>
              <div className="flex items-center gap-2 text-xs text-black/50 dark:text-white/55">
                <span>{permissionSetPermissionsOpen ? "Hide" : "Edit"}</span>
                <ChevronDown
                  size={16}
                  className={cn("transition-transform", permissionSetPermissionsOpen && "rotate-180")}
                />
              </div>
            </button>

            {permissionSetPermissionsOpen ? (
              <div className="mt-0 space-y-0">
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <div className="flex gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="rounded-xl"
                      onClick={selectAllPermissionSetPermissions}
                      disabled={!permissionList.length}
                    >
                      Select all
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="rounded-xl"
                      onClick={clearPermissionSetPermissions}
                      disabled={!selectedPermissionSetPermissions.length}
                    >
                      Clear
                    </Button>
                  </div>
                </div>

                {permissionsQuery.isLoading ? (
                  <LoadingEllipsis text="Loading permissions" className="text-sm text-black/60 dark:text-white/65" />
                ) : permissionList.length ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-[168px] overflow-y-auto p-1">
                    {permissionList.map((perm) => {
                      const active = selectedPermissionSetPermissionSet.has(perm);
                      return (
                        <button
                          key={perm}
                          type="button"
                          onClick={() => togglePermissionSetPermission(perm)}
                          className={cn(
                            "flex items-center justify-between gap-3 rounded-xl px-3 py-2 text-sm ring-1 transition-colors",
                            active
                              ? "bg-black/5 dark:bg-white/10 ring-black/20 dark:ring-white/20 text-black dark:text-white"
                              : "bg-white/60 dark:bg-white/5 ring-black/5 dark:ring-white/10 text-black/70 dark:text-white/70 hover:bg-black/5 dark:hover:bg-white/10"
                          )}
                        >
                          <span className="min-w-0 truncate">{perm}</span>
                          <span
                            className={cn(
                              "h-6 w-6 rounded-full flex items-center justify-center transition-colors",
                              active
                                ? "bg-black text-white dark:bg-white dark:text-black shadow-soft"
                                : "bg-black/5 dark:bg-white/10 text-black/40 dark:text-white/40"
                            )}
                          >
                            <Check size={14} className={active ? "opacity-100" : "opacity-0"} />
                          </span>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="text-sm text-black/60 dark:text-white/65">No permissions available.</div>
                )}

                {customPermissionSetPermissions.length ? (
                  <div className="rounded-2xl bg-white/50 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 p-3">
                    <div className="text-xs font-semibold text-black/60 dark:text-white/65">
                      Custom permissions
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {customPermissionSetPermissions.map((perm) => (
                        <button
                          key={perm}
                          type="button"
                          onClick={() => togglePermissionSetPermission(perm)}
                          className="flex items-center gap-2 rounded-full bg-black/5 dark:bg-white/10 px-3 py-1 text-xs text-black/70 dark:text-white/70 hover:bg-black/8 dark:hover:bg-white/15"
                          title="Remove permission"
                        >
                          <span className="max-w-[220px] truncate">{perm}</span>
                          <span className="text-black/40 dark:text-white/40">x</span>
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </SoftCard>
        </FormField>
        <div className="flex items-center justify-between gap-2 pt-1">
          {editingPermissionSet ? (
            <Button
              variant="ghost"
              className="rounded-2xl text-red-600 hover:text-red-700 dark:text-red-300"
              onClick={() =>
                setConfirmDelete({
                  open: true,
                  type: "permission-set",
                  payload: editingPermissionSet,
                  label: `Delete permission set "${permissionSetForm.display_name || permissionSetForm.name}"?`,
                })
              }
            >
              Delete
            </Button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <Button variant="ghost" className="rounded-2xl" onClick={onClose}>
              Cancel
            </Button>
            <Button className="rounded-2xl" onClick={savePermissionSet} disabled={savingPermissionSet}>
              {savingPermissionSet ? <LoadingEllipsis text="Saving" /> : "Save"}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

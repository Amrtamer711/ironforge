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

export function ProfilesTab({
  profileSearch,
  setProfileSearch,
  openProfileModal,
  filteredProfileOptions,
  duplicateProfile,
  setConfirmDelete,
}) {
  return (
    <Card className="h-full min-h-0 flex flex-col">
      <CardHeader className="space-y-2">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>Profiles</CardTitle>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-end">
            <SearchInput
              value={profileSearch}
              onChange={(e) => setProfileSearch(e.target.value)}
              className="w-full sm:w-[220px]"
            />
            <Button variant="secondary" className="rounded-2xl self-start sm:self-auto" onClick={() => openProfileModal(null)}>
              Add profile
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex-1 min-h-0 overflow-y-auto space-y-4 pt-2">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {filteredProfileOptions.map((p) => (
            <SoftCard key={p.id || p.name} className="p-4 space-y-1">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-base font-semibold">{p.display_name || p.name}</div>
                  <div className="text-sm text-black/55 dark:text-white/60">{p.name}</div>
                </div>
                <div className="flex items-center gap-2">
                  <IconActionButton
                    onClick={() => duplicateProfile(p)}
                    title="Duplicate profile"
                    aria-label="Duplicate profile"
                  >
                    <Copy size={16} />
                  </IconActionButton>
                  {!p.is_system ? (
                    <>
                      <IconActionButton
                        onClick={() => openProfileModal(p)}
                        title="Edit profile"
                        aria-label="Edit profile"
                      >
                        <Pencil size={16} />
                      </IconActionButton>
                      <IconActionButton
                        variant="ghost"
                        onClick={() =>
                          setConfirmDelete({
                            open: true,
                            type: "profile",
                        payload: p.id || p.name,
                        label: `Delete profile "${p.display_name || p.name}"?`,
                          })
                        }
                        title="Delete profile"
                        aria-label="Delete profile"
                      >
                        <Trash2 size={16} />
                      </IconActionButton>
                    </>
                  ) : (
                    <span className="text-xs rounded-full px-2 py-0.5 bg-black/5 dark:bg-white/10">System</span>
                  )}
                </div>
              </div>
              <div className="text-sm text-black/55 dark:text-white/60">
                {(p.permissions || []).length} permission{(p.permissions || []).length === 1 ? "" : "s"}
              </div>
              {p.description ? (
                <div className="text-sm text-black/60 dark:text-white/65 truncate">{p.description}</div>
              ) : null}
            </SoftCard>
          ))}
        </div>
        {!filteredProfileOptions.length ? (
          <div className="text-sm text-black/60 dark:text-white/65">
            {profileSearch.trim() ? "No matching profiles." : "No profiles available."}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function ProfilesPanel({
  profileSearch,
  setProfileSearch,
  filteredProfileOptions,
  permissionList,
  permissionSetValues,
  permissionSetList,
  permissionSetsQuery,
  permissionsQuery,
}) {
  const {
    profileForm,
    setProfileForm,
    editingProfile,
    setEditingProfile,
    profileModalOpen,
    setProfileModalOpen,
    profileIsSystem,
    setProfileIsSystem,
    profilePermissionSetsOpen,
    setProfilePermissionSetsOpen,
    profilePermissionsOpen,
    setProfilePermissionsOpen,
    savingProfile,
    openProfileModal,
    duplicateProfile,
    saveProfile,
    deleteProfile,
    selectedProfilePermissions,
    selectedProfilePermissionSet,
    selectedProfilePermissionSets,
    customProfilePermissions,
    toggleProfilePermission,
    selectAllProfilePermissions,
    clearProfilePermissions,
    toggleProfilePermissionSet,
    selectAllProfilePermissionSets,
    clearProfilePermissionSets,
  } = useProfileActions({ permissionList, permissionSetValues, permissionSetList });
  const [confirmDelete, setConfirmDelete] = useState({ open: false, type: "", payload: null, label: "" });

  async function handleConfirmDelete() {
    if (!confirmDelete.open || !confirmDelete.payload) return;
    try {
      await deleteProfile(confirmDelete.payload);
    } finally {
      setConfirmDelete({ open: false, type: "", payload: null, label: "" });
    }
  }

  return (
    <>
      <ProfilesTab
        profileSearch={profileSearch}
        setProfileSearch={setProfileSearch}
        openProfileModal={openProfileModal}
        filteredProfileOptions={filteredProfileOptions}
        duplicateProfile={duplicateProfile}
        setConfirmDelete={setConfirmDelete}
      />

      <ProfilesModal
        open={profileModalOpen}
        onClose={() => {
          setProfileModalOpen(false);
          setEditingProfile(null);
          setProfileForm({ name: "", display_name: "", description: "", permissionsText: "", permissionSets: [] });
          setProfileIsSystem(false);
          setProfilePermissionSetsOpen(false);
          setProfilePermissionsOpen(false);
        }}
        editingProfile={editingProfile}
        profileForm={profileForm}
        setProfileForm={setProfileForm}
        profileIsSystem={profileIsSystem}
        profilePermissionSetsOpen={profilePermissionSetsOpen}
        setProfilePermissionSetsOpen={setProfilePermissionSetsOpen}
        profilePermissionsOpen={profilePermissionsOpen}
        setProfilePermissionsOpen={setProfilePermissionsOpen}
        permissionSetValues={permissionSetValues}
        permissionSetsQuery={permissionSetsQuery}
        permissionSetList={permissionSetList}
        selectedProfilePermissionSets={selectedProfilePermissionSets}
        toggleProfilePermissionSet={toggleProfilePermissionSet}
        selectAllProfilePermissionSets={selectAllProfilePermissionSets}
        clearProfilePermissionSets={clearProfilePermissionSets}
        selectedProfilePermissions={selectedProfilePermissions}
        permissionList={permissionList}
        permissionsQuery={permissionsQuery}
        selectedProfilePermissionSet={selectedProfilePermissionSet}
        toggleProfilePermission={toggleProfilePermission}
        selectAllProfilePermissions={selectAllProfilePermissions}
        clearProfilePermissions={clearProfilePermissions}
        customProfilePermissions={customProfilePermissions}
        setConfirmDelete={setConfirmDelete}
        saveProfile={saveProfile}
        savingProfile={savingProfile}
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

function useProfileActions({ permissionList, permissionSetValues, permissionSetList }) {
  const qc = useQueryClient();
  const [profileForm, setProfileForm] = useState({
    name: "",
    display_name: "",
    description: "",
    permissionsText: "",
    permissionSets: [],
  });
  const [editingProfile, setEditingProfile] = useState(null);
  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [profileIsSystem, setProfileIsSystem] = useState(false);
  const [profilePermissionSetsOpen, setProfilePermissionSetsOpen] = useState(false);
  const [profilePermissionsOpen, setProfilePermissionsOpen] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);

  const selectedProfilePermissions = useMemo(
    () => parsePermissions(profileForm.permissionsText),
    [profileForm.permissionsText]
  );
  const selectedProfilePermissionSet = useMemo(
    () => new Set(selectedProfilePermissions),
    [selectedProfilePermissions]
  );
  const selectedProfilePermissionSets = useMemo(
    () => new Set(profileForm.permissionSets || []),
    [profileForm.permissionSets]
  );
  const customProfilePermissions = useMemo(() => {
    if (!permissionList.length) return selectedProfilePermissions;
    const known = new Set(permissionList);
    return selectedProfilePermissions.filter((perm) => !known.has(perm));
  }, [permissionList, selectedProfilePermissions]);

  const permissionSetPermissionsMap = useMemo(() => {
    const map = new Map();
    (permissionSetList || []).forEach((set) => {
      const key = set.name || set.id;
      if (!key) return;
      const perms = (set.permissions || set.permission_list || set.permissionList || [])
        .map((entry) => (typeof entry === "string" ? entry : entry?.name || entry?.value || entry?.permission))
        .filter(Boolean);
      map.set(key, new Set(perms));
    });
    return map;
  }, [permissionSetList]);

  function filterPermissionSetsByPermissions(permissionSetValuesList, permissionsSet) {
    return (permissionSetValuesList || []).filter((setName) => {
      const required = permissionSetPermissionsMap.get(setName);
      if (!required) return true;
      for (const value of required) {
        if (!permissionsSet.has(value)) return false;
      }
      return true;
    });
  }

  function openProfileModal(profile) {
    setProfileIsSystem(Boolean(profile?.is_system));
    if (profile?.is_system) return;
    setProfilePermissionSetsOpen(false);
    setProfilePermissionsOpen(false);
    if (profile) {
      setEditingProfile(profile.id || profile.name);
      setProfileForm({
        name: profile.name,
        display_name: profile.display_name || profile.name,
        description: profile.description || "",
        permissionsText: (profile.permissions || [])
          .map((perm) => (typeof perm === "string" ? perm : perm?.name))
          .filter(Boolean)
          .join("\n"),
        permissionSets: (profile.permission_sets || profile.permissionSets || profile.permission_set_names || [])
          .map((set) => (typeof set === "string" ? set : set?.name || set?.id))
          .filter(Boolean),
      });
    } else {
      setEditingProfile(null);
      setProfileForm({ name: "", display_name: "", description: "", permissionsText: "", permissionSets: [] });
    }
    setProfileModalOpen(true);
  }

  function duplicateProfile(profile) {
    if (!profile) return;
    const baseName = profile.name || profile.display_name || "profile";
    const baseDisplay = profile.display_name || profile.name || baseName;
    setProfileIsSystem(false);
    setEditingProfile(null);
    setProfilePermissionSetsOpen(false);
    setProfilePermissionsOpen(false);
    setProfileForm({
      name: `${baseName}_new`,
      display_name: `${baseDisplay}_new`,
      description: profile.description || "",
      permissionsText: (profile.permissions || [])
        .map((perm) => (typeof perm === "string" ? perm : perm?.name))
        .filter(Boolean)
        .join("\n"),
      permissionSets: (profile.permission_sets || profile.permissionSets || profile.permission_set_names || [])
        .map((set) => (typeof set === "string" ? set : set?.name || set?.id))
        .filter(Boolean),
    });
    setProfileModalOpen(true);
  }

  async function saveProfile() {
    if (!profileForm.name.trim()) return;
    setSavingProfile(true);
    try {
      const payload = {
        name: profileForm.name.trim(),
        display_name: profileForm.display_name || profileForm.name,
        description: profileForm.description,
        permissions: parsePermissions(profileForm.permissionsText),
        permission_sets: profileForm.permissionSets || [],
      };

      if (editingProfile) {
        await adminApi.updateProfile(editingProfile, payload);
      } else {
        await adminApi.createProfile(payload);
      }
      qc.invalidateQueries({ queryKey: ["admin", "profiles"] });
      setProfileForm({ name: "", display_name: "", description: "", permissionsText: "", permissionSets: [] });
      setEditingProfile(null);
      setProfileModalOpen(false);
    } catch {
      // ignore
    } finally {
      setSavingProfile(false);
    }
  }

  async function deleteProfile(name) {
    try {
      await adminApi.deleteProfile(name);
      qc.invalidateQueries({ queryKey: ["admin", "profiles"] });
      if (editingProfile === name) {
        setEditingProfile(null);
        setProfileForm({ name: "", display_name: "", description: "", permissionsText: "", permissionSets: [] });
      }
      setProfileModalOpen(false);
    } catch {
      // ignore
    }
  }

  function toggleProfilePermission(value) {
    setProfileForm((f) => {
      const current = new Set(parsePermissions(f.permissionsText));
      const removing = current.has(value);
      if (removing) current.delete(value);
      else current.add(value);
      let permissionSets = f.permissionSets || [];
      if (removing) {
        permissionSets = filterPermissionSetsByPermissions(permissionSets, current);
      }
      return {
        ...f,
        permissionsText: Array.from(current).join("\n"),
        permissionSets,
      };
    });
  }

  function selectAllProfilePermissions() {
    const combined = new Set([...selectedProfilePermissions, ...permissionList]);
    setProfileForm((f) => ({ ...f, permissionsText: Array.from(combined).join("\n") }));
  }

  function clearProfilePermissions() {
    setProfileForm((f) => ({ ...f, permissionsText: "" }));
  }

  function toggleProfilePermissionSet(value) {
    setProfileForm((f) => {
      const currentSets = new Set(f.permissionSets || []);
      const permissions = new Set(parsePermissions(f.permissionsText));
      const isActive = currentSets.has(value);
      if (isActive) {
        currentSets.delete(value);
        return { ...f, permissionSets: Array.from(currentSets), permissionsText: Array.from(permissions).join("\n") };
      }

      currentSets.add(value);
      const setPerms = permissionSetPermissionsMap.get(value);
      if (setPerms) setPerms.forEach((perm) => permissions.add(perm));
      return { ...f, permissionSets: Array.from(currentSets), permissionsText: Array.from(permissions).join("\n") };
    });
  }

  function selectAllProfilePermissionSets() {
    setProfileForm((f) => {
      const permissionSets = new Set([...(f.permissionSets || []), ...permissionSetValues]);
      const permissions = new Set(parsePermissions(f.permissionsText));
      permissionSets.forEach((setName) => {
        const setPerms = permissionSetPermissionsMap.get(setName);
        if (setPerms) setPerms.forEach((perm) => permissions.add(perm));
      });
      return {
        ...f,
        permissionSets: Array.from(permissionSets),
        permissionsText: Array.from(permissions).join("\n"),
      };
    });
  }

  function clearProfilePermissionSets() {
    setProfileForm((f) => ({ ...f, permissionSets: [] }));
  }

  return {
    profileForm,
    setProfileForm,
    editingProfile,
    setEditingProfile,
    profileModalOpen,
    setProfileModalOpen,
    profileIsSystem,
    setProfileIsSystem,
    profilePermissionSetsOpen,
    setProfilePermissionSetsOpen,
    profilePermissionsOpen,
    setProfilePermissionsOpen,
    savingProfile,
    openProfileModal,
    duplicateProfile,
    saveProfile,
    deleteProfile,
    selectedProfilePermissions,
    selectedProfilePermissionSet,
    selectedProfilePermissionSets,
    customProfilePermissions,
    toggleProfilePermission,
    selectAllProfilePermissions,
    clearProfilePermissions,
    toggleProfilePermissionSet,
    selectAllProfilePermissionSets,
    clearProfilePermissionSets,
  };
}

export function ProfilesModal({
  open,
  onClose,
  editingProfile,
  profileForm,
  setProfileForm,
  profileIsSystem,
  profilePermissionSetsOpen,
  setProfilePermissionSetsOpen,
  profilePermissionsOpen,
  setProfilePermissionsOpen,
  permissionSetValues,
  permissionSetsQuery,
  permissionSetList,
  selectedProfilePermissionSets,
  toggleProfilePermissionSet,
  selectAllProfilePermissionSets,
  clearProfilePermissionSets,
  selectedProfilePermissions,
  permissionList,
  permissionsQuery,
  selectedProfilePermissionSet,
  toggleProfilePermission,
  selectAllProfilePermissions,
  clearProfilePermissions,
  customProfilePermissions,
  setConfirmDelete,
  saveProfile,
  savingProfile,
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editingProfile ? `Edit profile: ${editingProfile}` : "Add profile"}
      maxWidth="640px"
    >
      <div className="space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <FormField label="Name">
            <input
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={profileForm.name}
              onChange={(e) => setProfileForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="system_admin"
              disabled={Boolean(editingProfile)}
            />
          </FormField>
          <FormField label="Display Name">
            <input
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={profileForm.display_name}
              onChange={(e) => setProfileForm((f) => ({ ...f, display_name: e.target.value }))}
              placeholder="System Admin"
            />
          </FormField>
        </div>
        <FormField label="Description">
          <input
            className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
            value={profileForm.description}
            onChange={(e) => setProfileForm((f) => ({ ...f, description: e.target.value }))}
            placeholder="What this profile can do"
          />
        </FormField>
        <FormField label="Permission Sets">
          <SoftCard className="p-4">
            <button
              type="button"
              className="flex w-full items-center justify-between gap-3 text-left"
              onClick={() => setProfilePermissionSetsOpen((openValue) => !openValue)}
              aria-expanded={profilePermissionSetsOpen}
            >
              <div>
                <div className="text-sm font-semibold text-black/80 dark:text-white/85">Permission sets</div>
                <div className="text-xs text-black/55 dark:text-white/60">
                  {selectionLabel(profileForm.permissionSets.length, "permission set", "permission sets")}
                </div>
              </div>
              <div className="flex items-center gap-2 text-xs text-black/50 dark:text-white/55">
                <span>{profilePermissionSetsOpen ? "Hide" : "Edit"}</span>
                <ChevronDown
                  size={16}
                  className={cn("transition-transform", profilePermissionSetsOpen && "rotate-180")}
                />
              </div>
            </button>

            {profilePermissionSetsOpen ? (
              <div className="mt-0 space-y-0">
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <div className="flex gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="rounded-xl"
                      onClick={selectAllProfilePermissionSets}
                      disabled={!permissionSetValues.length}
                    >
                      Select all
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="rounded-xl"
                      onClick={clearProfilePermissionSets}
                      disabled={!profileForm.permissionSets.length}
                    >
                      Clear
                    </Button>
                  </div>
                </div>

                {permissionSetsQuery.isLoading ? (
                  <LoadingEllipsis text="Loading permission sets" className="text-sm text-black/60 dark:text-white/65" />
                ) : permissionSetList.length ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-[168px] overflow-y-auto p-1">
                    {permissionSetList.map((set) => {
                      const value = set.name || set.id;
                      if (!value) return null;
                      const active = selectedProfilePermissionSets.has(value);
                      return (
                        <button
                          key={value}
                          type="button"
                          onClick={() => toggleProfilePermissionSet(value)}
                          className={cn(
                            "flex items-center justify-between gap-3 rounded-xl px-3 py-2 text-sm ring-1 transition-colors",
                            active
                              ? "bg-black/5 dark:bg-white/10 ring-black/20 dark:ring-white/20 text-black dark:text-white"
                              : "bg-white/60 dark:bg-white/5 ring-black/5 dark:ring-white/10 text-black/70 dark:text-white/70 hover:bg-black/5 dark:hover:bg-white/10"
                          )}
                        >
                          <span className="min-w-0 truncate text-sm font-medium">
                            {set.display_name || set.name || value}
                          </span>
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
                  <div className="text-sm text-black/60 dark:text-white/65">No permission sets available.</div>
                )}
              </div>
            ) : null}
          </SoftCard>
        </FormField>
        <FormField label="Permissions">
          <SoftCard className="p-4">
            <button
              type="button"
              className="flex w-full items-center justify-between gap-3 text-left"
              onClick={() => setProfilePermissionsOpen((openValue) => !openValue)}
              aria-expanded={profilePermissionsOpen}
            >
              <div>
                <div className="text-sm font-semibold text-black/80 dark:text-white/85">Permissions</div>
                <div className="text-xs text-black/55 dark:text-white/60">
                  {selectionLabel(selectedProfilePermissions.length, "permission")}
                </div>
              </div>
              <div className="flex items-center gap-2 text-xs text-black/50 dark:text-white/55">
                <span>{profilePermissionsOpen ? "Hide" : "Edit"}</span>
                <ChevronDown
                  size={16}
                  className={cn("transition-transform", profilePermissionsOpen && "rotate-180")}
                />
              </div>
            </button>

            {profilePermissionsOpen ? (
              <div className="mt-0 space-y-0">
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <div className="flex gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="rounded-xl"
                      onClick={selectAllProfilePermissions}
                      disabled={!permissionList.length}
                    >
                      Select all
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="rounded-xl"
                      onClick={clearProfilePermissions}
                      disabled={!selectedProfilePermissions.length}
                    >
                      Clear
                    </Button>
                  </div>
                </div>

                {permissionsQuery.isLoading ? (
                  <LoadingEllipsis text="Loading permissions" className="text-sm text-black/60 dark:text-white/65" />
                ) : permissionList.length ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-[110px] overflow-y-auto p-1">
                    {permissionList.map((perm) => {
                      const active = selectedProfilePermissionSet.has(perm);
                      return (
                        <button
                          key={perm}
                          type="button"
                          onClick={() => toggleProfilePermission(perm)}
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

                {customProfilePermissions.length ? (
                  <div className="rounded-2xl bg-white/50 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 p-3">
                    <div className="text-xs font-semibold text-black/60 dark:text-white/65">Custom permissions</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {customProfilePermissions.map((perm) => (
                        <button
                          key={perm}
                          type="button"
                          onClick={() => toggleProfilePermission(perm)}
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
          {editingProfile ? (
            <Button
              variant="ghost"
              className="rounded-2xl text-red-600 hover:text-red-700 dark:text-red-300"
              onClick={() =>
                setConfirmDelete({
                  open: true,
                  type: "profile",
                  payload: editingProfile,
                  label: `Delete profile "${profileForm.display_name || profileForm.name}"?`,
                })
              }
              disabled={profileIsSystem}
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
            <Button className="rounded-2xl" onClick={saveProfile} disabled={savingProfile || profileIsSystem}>
              {savingProfile ? <LoadingEllipsis text="Saving" /> : "Save"}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

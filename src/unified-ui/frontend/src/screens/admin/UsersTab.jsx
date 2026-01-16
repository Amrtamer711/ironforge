import React, { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, Pencil, UserRoundCheck, UserRoundX } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { FormField } from "../../components/ui/form-field";
import { SearchInput } from "../../components/ui/search-input";
import { SoftCard } from "../../components/ui/soft-card";
import { IconActionButton } from "../../components/ui/icon-action-button";
import { LoadingEllipsis } from "../../components/ui/loading-ellipsis";
import { ConfirmModal, Modal } from "../../components/ui/modal";
import { SelectDropdown } from "../../components/ui/select-dropdown";
import { adminApi } from "../../api";
import { cn, parsePermissions, selectionLabel } from "../../lib/utils";

function getValue(entry) {
  if (!entry) return "";
  if (typeof entry === "string") return entry;
  return entry.name || entry.id || entry.value || "";
}

function getPermissionValue(entry) {
  if (!entry) return "";
  if (typeof entry === "string") return entry;
  return entry.name || entry.value || entry.permission || "";
}

function isSubset(subset, container) {
  if (!subset || !container) return true;
  for (const value of subset) {
    if (!container.has(value)) return false;
  }
  return true;
}

function buildPermissionSetPermissionsMap(permissionSetList) {
  const map = new Map();
  (permissionSetList || []).forEach((set) => {
    const key = getValue(set);
    if (!key) return;
    const perms = (set.permissions || []).map(getPermissionValue).filter(Boolean);
    map.set(key, new Set(perms));
  });
  return map;
}

function buildProfilePermissionSetsMap(profileOptions) {
  const map = new Map();
  (profileOptions || []).forEach((profile) => {
    const key = profile.name || profile.id;
    if (!key) return;
    const sets = (profile.permission_sets || []).map(getValue).filter(Boolean);
    map.set(key, new Set(sets));
  });
  return map;
}

function buildProfilePermissionsMap(profileOptions) {
  const map = new Map();
  (profileOptions || []).forEach((profile) => {
    const key = profile.name || profile.id;
    if (!key) return;
    const perms = (profile.permissions || []).map(getPermissionValue).filter(Boolean);
    map.set(key, new Set(perms));
  });
  return map;
}

export function UsersTab({
  q,
  setQ,
  openNewUserModal,
  usersQuery,
  users,
  user,
  selectUser,
  setConfirmDelete,
  companyLookup,
  userCompanyFilter,
  setUserCompanyFilter,
  userProfileFilter,
  setUserProfileFilter,
  companyTreeOptions,
  profileFilterOptions,
}) {
  const companyTreeWithAll = useMemo(
    () => [{ value: "", label: "All companies" }, ...(companyTreeOptions || [])],
    [companyTreeOptions]
  );
  const profileSelectOptions = useMemo(
    () => [{ value: "", label: "All profiles" }, ...profileFilterOptions.map((opt) => ({ ...opt }))],
    [profileFilterOptions]
  );

  const headerContent = (
    <>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle>Users</CardTitle>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-end">
          <SearchInput
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="w-full sm:w-[220px]"
          />
          {/* <div className="flex w-full justify-end gap-1 md:w-auto">
            <Button variant="ghost" size="sm" className="rounded-xl" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>
              Prev
            </Button>
            <Button variant="ghost" size="sm" className="rounded-xl" disabled={!hasNext} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
          </div> */}
          <Button variant="secondary" className="rounded-2xl self-start sm:self-auto" onClick={openNewUserModal}>
            Add user
          </Button>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <SelectDropdown
          value={userCompanyFilter}
          treeOptions={companyTreeWithAll}
          onChange={setUserCompanyFilter}
        />
        <SelectDropdown
          value={userProfileFilter}
          options={profileSelectOptions}
          onChange={setUserProfileFilter}
        />
      </div>
    </>
  );

  return (
    <Card className="h-full min-h-0 flex flex-col">
      <CardHeader className="hidden md:block space-y-2">
        {headerContent}
      </CardHeader>
      <CardContent className="flex-1 min-h-0 overflow-y-auto p-0">
        <div className="space-y-2 p-5 pb-3 md:hidden">
          {headerContent}
        </div>
        <div className="space-y-4 p-5 pt-1">
          {usersQuery.isLoading ? (
            <LoadingEllipsis text="Loading" className="text-sm text-black/60 dark:text-white/65" />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {users.map((u) => {
                const profileText = u.profiles?.display_name || u.profiles?.name || "—";
                const isSelfCard = Boolean(
                  (u.id && user?.id && u.id === user.id) ||
                    (u.email && user?.email && u.email === user.email)
                );
                const rawActive = u.is_active;
                const hasActiveFlag = typeof rawActive === "boolean";
                const isActive = hasActiveFlag ? rawActive : true;
                const deactivateLabel = isActive ? "Deactivate" : "Reactivate";
                return (
                  <SoftCard key={u.id || u.email} className="p-4 space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="text-base font-semibold">{u.name || "—"}</div>
                          {hasActiveFlag && !isActive ? (
                            <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700 dark:bg-red-500/20 dark:text-red-200">
                              Inactive
                            </span>
                          ) : null}
                        </div>
                        <div className="text-sm text-black/55 dark:text-white/60">{u.email}</div>
                      </div>
                      <div className="flex items-center gap-2">
                        <IconActionButton onClick={() => selectUser(u)} title="Edit user" aria-label="Edit user">
                          <Pencil size={16} />
                        </IconActionButton>
                        <IconActionButton
                          variant="ghost"
                          onClick={() =>
                            setConfirmDelete({
                              open: true,
                              type: "user",
                              payload: { id: u.id, isActive },
                              label: `${deactivateLabel} user "${u.email}"?`,
                            })
                          }
                          disabled={isSelfCard}
                          title={isSelfCard ? "You cannot deactivate yourself" : `${deactivateLabel} user`}
                          aria-label={`${deactivateLabel} user`}
                          className={
                            isActive
                              ? undefined
                              : "text-emerald-600 hover:text-emerald-700 dark:text-emerald-300"
                          }
                        >
                          {isActive ? <UserRoundX size={16} /> : <UserRoundCheck size={16} />}
                        </IconActionButton>
                      </div>
                    </div>
                    <div className="text-sm text-black/55 dark:text-white/60">
                      Profiles: <span className="font-semibold">{profileText}</span>
                    </div>
                    <div className="text-sm text-black/55 dark:text-white/60">
                      Company:{" "}
                      <span className="font-semibold">
                        {companyLookup.get(u.primary_company_id) || "—"}
                      </span>
                    </div>
                  </SoftCard>
                );
              })}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function UsersPanel({
  q,
  setQ,
  usersQuery,
  users,
  user,
  companyLookup,
  companyCodeById,
  userCompanyFilter,
  setUserCompanyFilter,
  userProfileFilter,
  setUserProfileFilter,
  companyTreeOptions,
  profileFilterOptions,
  profileOptions,
  profileValues,
  permissionSetList,
  permissionSetValues,
  permissionList,
  permissionsQuery,
  page,
}) {
  const {
    selectedUser,
    setSelectedUser,
    userForm,
    setUserForm,
    userModalOpen,
    setUserModalOpen,
    userModalLoading,
    setUserModalLoading,
    userModalMode,
    setUserModalMode,
    userProfilesOpen,
    setUserProfilesOpen,
    userPermissionSetsOpen,
    setUserPermissionSetsOpen,
    userPermissionsOpen,
    setUserPermissionsOpen,
    savingUser,
    setPermissionsMessage,
    selectUser,
    openNewUserModal,
    saveUser,
    deleteUser,
    selectedUserProfiles,
    selectedUserPermissionSets,
    selectedUserPermissions,
    selectedUserPermissionSet,
    customUserPermissions,
    toggleUserPermission,
    selectAllUserPermissions,
    clearUserPermissions,
    toggleUserProfile,
    selectAllUserProfiles,
    clearUserProfiles,
    toggleUserPermissionSet,
    selectAllUserPermissionSets,
    clearUserPermissionSets,
  } = useUserActions({
    permissionList,
    profileValues,
    permissionSetValues,
    profileOptions,
    permissionSetList,
    companyCodeById,
  });
  const [confirmDelete, setConfirmDelete] = useState({ open: false, type: "", payload: null, label: "" });

  const isSelfUser = Boolean(
    selectedUser &&
      ((selectedUser.id && user?.id && selectedUser.id === user?.id) ||
        (selectedUser.email && user?.email && selectedUser.email === user?.email))
  );

  useEffect(() => {
    setSelectedUser(null);
  }, [page, setSelectedUser]);

  async function handleConfirmDelete() {
    if (!confirmDelete.open || !confirmDelete.payload) return;
    try {
      const payload = confirmDelete.payload;
      const targetId = payload?.id ?? payload;
      if (!targetId) return;
      if (user?.id && targetId === user.id) {
        return;
      }
      await deleteUser(payload);
    } finally {
      setConfirmDelete({ open: false, type: "", payload: null, label: "" });
    }
  }

  return (
    <>
      <UsersTab
        q={q}
        setQ={setQ}
        openNewUserModal={openNewUserModal}
        usersQuery={usersQuery}
        users={users}
        user={user}
        selectUser={selectUser}
        setConfirmDelete={setConfirmDelete}
        companyLookup={companyLookup}
        userCompanyFilter={userCompanyFilter}
        setUserCompanyFilter={setUserCompanyFilter}
        userProfileFilter={userProfileFilter}
        setUserProfileFilter={setUserProfileFilter}
        companyTreeOptions={companyTreeOptions}
        profileFilterOptions={profileFilterOptions}
      />

      <UsersModal
        open={userModalOpen}
        onClose={() => {
          setUserModalOpen(false);
          setSelectedUser(null);
          setPermissionsMessage("");
          setUserModalLoading(false);
          setUserModalMode("edit");
          setUserProfilesOpen(false);
          setUserPermissionSetsOpen(false);
          setUserPermissionsOpen(false);
        }}
        userModalLoading={userModalLoading}
        userModalMode={userModalMode}
        selectedUser={selectedUser}
        userForm={userForm}
        setUserForm={setUserForm}
        companyTreeOptions={companyTreeOptions}
        profileOptions={profileOptions}
        profileValues={profileValues}
        userProfilesOpen={userProfilesOpen}
        setUserProfilesOpen={setUserProfilesOpen}
        selectAllUserProfiles={selectAllUserProfiles}
        clearUserProfiles={clearUserProfiles}
        selectedUserProfiles={selectedUserProfiles}
        toggleUserProfile={toggleUserProfile}
        permissionSetList={permissionSetList}
        permissionSetValues={permissionSetValues}
        userPermissionSetsOpen={userPermissionSetsOpen}
        setUserPermissionSetsOpen={setUserPermissionSetsOpen}
        selectAllUserPermissionSets={selectAllUserPermissionSets}
        clearUserPermissionSets={clearUserPermissionSets}
        selectedUserPermissionSets={selectedUserPermissionSets}
        toggleUserPermissionSet={toggleUserPermissionSet}
        userPermissionsOpen={userPermissionsOpen}
        setUserPermissionsOpen={setUserPermissionsOpen}
        selectedUserPermissions={selectedUserPermissions}
        permissionList={permissionList}
        permissionsQuery={permissionsQuery}
        selectedUserPermissionSet={selectedUserPermissionSet}
        toggleUserPermission={toggleUserPermission}
        selectAllUserPermissions={selectAllUserPermissions}
        clearUserPermissions={clearUserPermissions}
        customUserPermissions={customUserPermissions}
        isSelfUser={isSelfUser}
        setConfirmDelete={setConfirmDelete}
        saveUser={saveUser}
        savingUser={savingUser}
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

function useUserActions({
  permissionList,
  profileValues,
  permissionSetValues,
  profileOptions,
  permissionSetList,
  companyCodeById,
}) {
  const qc = useQueryClient();
  const [selectedUser, setSelectedUser] = useState(null);
  const [userForm, setUserForm] = useState({
    name: "",
    email: "",
    profiles: [],
    permissionSets: [],
    company: "",
    is_active: true,
    permissionsText: "",
  });
  const [userModalOpen, setUserModalOpen] = useState(false);
  const [userModalLoading, setUserModalLoading] = useState(false);
  const [userModalMode, setUserModalMode] = useState("edit");
  const [userProfilesOpen, setUserProfilesOpen] = useState(false);
  const [userPermissionSetsOpen, setUserPermissionSetsOpen] = useState(false);
  const [userPermissionsOpen, setUserPermissionsOpen] = useState(false);
  const [savingUser, setSavingUser] = useState(false);
  const [permissionsMessage, setPermissionsMessage] = useState("");

  const selectedUserProfiles = useMemo(() => new Set(userForm.profiles || []), [userForm.profiles]);
  const selectedUserPermissionSets = useMemo(
    () => new Set(userForm.permissionSets || []),
    [userForm.permissionSets]
  );
  const selectedUserPermissions = useMemo(
    () => parsePermissions(userForm.permissionsText),
    [userForm.permissionsText]
  );
  const selectedUserPermissionSet = useMemo(
    () => new Set(selectedUserPermissions),
    [selectedUserPermissions]
  );
  const customUserPermissions = useMemo(() => {
    if (!permissionList.length) return selectedUserPermissions;
    const known = new Set(permissionList);
    return selectedUserPermissions.filter((perm) => !known.has(perm));
  }, [permissionList, selectedUserPermissions]);

  const permissionSetPermissionsMap = useMemo(
    () => buildPermissionSetPermissionsMap(permissionSetList),
    [permissionSetList]
  );
  const profilePermissionSetsMap = useMemo(
    () => buildProfilePermissionSetsMap(profileOptions),
    [profileOptions]
  );
  const profilePermissionsMap = useMemo(
    () => buildProfilePermissionsMap(profileOptions),
    [profileOptions]
  );

  function collectPermissionsFromSets(setValues) {
    const permissions = new Set();
    (setValues || []).forEach((setName) => {
      const setPerms = permissionSetPermissionsMap.get(setName);
      if (!setPerms) return;
      setPerms.forEach((perm) => permissions.add(perm));
    });
    return permissions;
  }

  function collectPermissionsFromProfiles(profileNames) {
    const permissions = new Set();
    (profileNames || []).forEach((profileName) => {
      const profilePerms = profilePermissionsMap.get(profileName);
      if (profilePerms) profilePerms.forEach((perm) => permissions.add(perm));
      const profileSets = profilePermissionSetsMap.get(profileName);
      if (profileSets) {
        profileSets.forEach((setName) => {
          const setPerms = permissionSetPermissionsMap.get(setName);
          if (!setPerms) return;
          setPerms.forEach((perm) => permissions.add(perm));
        });
      }
    });
    return permissions;
  }

  function filterPermissionSetsByPermissions(permissionSetValuesList, permissionSetPermissions, permissionsSet) {
    return (permissionSetValuesList || []).filter((setName) => {
      const required = permissionSetPermissions.get(setName);
      if (!required) return true;
      return isSubset(required, permissionsSet);
    });
  }

  function filterProfilesBySelections(profileValuesList, permissionsSet, permissionSetsList) {
    const permissionSets = new Set(permissionSetsList || []);
    return (profileValuesList || []).filter((profileName) => {
      const profilePerms = profilePermissionsMap.get(profileName);
      const profileSets = profilePermissionSetsMap.get(profileName);
      if (!profilePerms && !profileSets) return true;
      if (profileSets && !isSubset(profileSets, permissionSets)) return false;
      const required = new Set();
      if (profilePerms) profilePerms.forEach((perm) => required.add(perm));
      if (profileSets) {
        profileSets.forEach((setName) => {
          const setPerms = permissionSetPermissionsMap.get(setName);
          if (setPerms) setPerms.forEach((perm) => required.add(perm));
        });
      }
      return isSubset(required, permissionsSet);
    });
  }

  function applyProfileSelections(form, permissionsOverride) {
    const profiles = new Set(form.profiles || []);
    const permissionSets = new Set(form.permissionSets || []);
    const permissions = new Set(
      permissionsOverride || parsePermissions(form.permissionsText)
    );
    profiles.forEach((profileName) => {
      const profileSets = profilePermissionSetsMap.get(profileName);
      if (profileSets) profileSets.forEach((setName) => permissionSets.add(setName));
      const profilePerms = profilePermissionsMap.get(profileName);
      if (profilePerms) profilePerms.forEach((perm) => permissions.add(perm));
      if (profileSets) {
        profileSets.forEach((setName) => {
          const setPerms = permissionSetPermissionsMap.get(setName);
          if (setPerms) setPerms.forEach((perm) => permissions.add(perm));
        });
      }
    });
    return {
      ...form,
      permissionSets: Array.from(permissionSets),
      permissionsText: Array.from(permissions).join("\n"),
    };
  }

  async function selectUser(u) {
    setSelectedUser(u);
    setPermissionsMessage("");
    setUserModalMode("edit");
    setUserModalOpen(true);
    setUserModalLoading(true);
    setUserProfilesOpen(false);
    setUserPermissionSetsOpen(false);
    setUserPermissionsOpen(false);
    const profileValuesLocal = u.profiles?.name ? [u.profiles.name] : [];
    const permissionSetValuesLocal = [];
    setUserForm({
      name: u.name || "",
      email: u.email || "",
      profiles: profileValuesLocal,
      permissionSets: permissionSetValuesLocal,
      company: companyCodeById?.get(u.primary_company_id) || "",
      is_active: u.is_active !== false,
      permissionsText: "",
    });

    const userId = u.id;
    if (userId) {
      try {
        const perms = await adminApi.getUserPermissions(userId);
        const raw = perms?.permissions ?? perms;
        const list = Array.isArray(raw)
          ? raw.map((perm) => (typeof perm === "string" ? perm : perm?.name)).filter(Boolean)
          : [];
        setUserForm((f) => applyProfileSelections({ ...f, permissionsText: list.join("\n") }));
      } catch {
        // ignore
      }
    }

    setUserModalLoading(false);
  }

  function openNewUserModal() {
    setSelectedUser(null);
    setPermissionsMessage("");
    setUserModalMode("add");
    setUserModalLoading(false);
    setUserProfilesOpen(false);
    setUserPermissionSetsOpen(false);
    setUserPermissionsOpen(false);
    setUserForm({
      name: "",
      email: "",
      profiles: [],
      permissionSets: [],
      company: "",
      is_active: true,
      permissionsText: "",
    });
    setUserModalOpen(true);
  }

  async function saveUser() {
    if (userModalMode === "edit" && !selectedUser) return;
    setSavingUser(true);
    setPermissionsMessage("");
    const userId = selectedUser?.id;
    if (userModalMode === "edit" && !userId) {
      setSavingUser(false);
      setPermissionsMessage("Missing user id");
      return;
    }
    const permissions = parsePermissions(userForm.permissionsText);
    const selectedProfiles = userForm.profiles || [];
    const payload = {
      name: userForm.name,
      is_active: Boolean(userForm.is_active),
      profile_names: selectedProfiles,
      profile_name: selectedProfiles[0] || null,
      permission_sets: userForm.permissionSets || [],
      company_code: userForm.company || null,
      ...(userModalMode === "add" ? { email: userForm.email } : {}),
    };

    try {
      if (userModalMode === "add") {
        const created = await adminApi.createUser(payload);
        const createdId = created?.id || created?.user?.id;
        if (createdId != null) {
          await adminApi.setUserPermissions(createdId, permissions);
        }
        setPermissionsMessage("User created");
      } else {
        await adminApi.updateUser(userId, payload);
        await adminApi.setUserPermissions(userId, permissions);
        setPermissionsMessage("User updated");
      }
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
      setUserModalOpen(false);
      setSelectedUser(null);
    } catch (err) {
      setPermissionsMessage(err?.message || "Failed to save user");
    } finally {
      setSavingUser(false);
    }
  }

  async function deleteUser(payload) {
    const target = payload?.id ?? payload;
    if (!target) return;
    try {
      const rawActive = payload?.isActive ?? payload?.is_active;
      const isActive = typeof rawActive === "boolean" ? rawActive : true;
      if (isActive) {
        await adminApi.deactivateUser(target);
      } else {
        await adminApi.reactivateUser(target);
      }
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
      setUserModalOpen(false);
      setSelectedUser(null);
    } catch {
      // ignore
    }
  }

  function toggleUserPermission(value) {
    setUserForm((f) => {
      const current = new Set(parsePermissions(f.permissionsText));
      const removing = current.has(value);
      if (removing) current.delete(value);
      else current.add(value);

      let permissionSets = f.permissionSets || [];
      let profiles = f.profiles || [];
      if (removing) {
        permissionSets = filterPermissionSetsByPermissions(
          permissionSets,
          permissionSetPermissionsMap,
          current
        );
        profiles = filterProfilesBySelections(profiles, current, permissionSets);
      }
      return {
        ...f,
        permissionsText: Array.from(current).join("\n"),
        permissionSets,
        profiles,
      };
    });
  }

  function selectAllUserPermissions() {
    const combined = new Set([...selectedUserPermissions, ...permissionList]);
    setUserForm((f) => ({ ...f, permissionsText: Array.from(combined).join("\n") }));
  }

  function clearUserPermissions() {
    setUserForm((f) => ({ ...f, permissionsText: "", permissionSets: [], profiles: [] }));
  }

  function toggleUserProfile(value) {
    setUserForm((f) => {
      const profiles = new Set(f.profiles || []);
      const permissionSets = new Set(f.permissionSets || []);
      const permissions = new Set(parsePermissions(f.permissionsText));
      const isActive = profiles.has(value);

      if (isActive) {
        profiles.delete(value);
        const filteredPermissionSets = filterPermissionSetsByPermissions(
          Array.from(permissionSets),
          permissionSetPermissionsMap,
          permissions
        );
        const filteredProfiles = filterProfilesBySelections(
          Array.from(profiles),
          permissions,
          filteredPermissionSets
        );
        return {
          ...f,
          profiles: filteredProfiles,
          permissionSets: filteredPermissionSets,
          permissionsText: Array.from(permissions).join("\n"),
        };
      }

      profiles.add(value);
      const profileSets = profilePermissionSetsMap.get(value);
      if (profileSets) {
        profileSets.forEach((setName) => permissionSets.add(setName));
      }
      const profilePerms = profilePermissionsMap.get(value);
      if (profilePerms) profilePerms.forEach((perm) => permissions.add(perm));
      if (profileSets) {
        profileSets.forEach((setName) => {
          const setPerms = permissionSetPermissionsMap.get(setName);
          if (setPerms) setPerms.forEach((perm) => permissions.add(perm));
        });
      }
      return {
        ...f,
        profiles: Array.from(profiles),
        permissionSets: Array.from(permissionSets),
        permissionsText: Array.from(permissions).join("\n"),
      };
    });
  }

  function selectAllUserProfiles() {
    setUserForm((f) => {
      const profiles = new Set([...(f.profiles || []), ...profileValues]);
      const permissionSets = new Set(f.permissionSets || []);
      const permissions = new Set(parsePermissions(f.permissionsText));
      profiles.forEach((profileName) => {
        const profileSets = profilePermissionSetsMap.get(profileName);
        if (profileSets) profileSets.forEach((setName) => permissionSets.add(setName));
        const profilePerms = profilePermissionsMap.get(profileName);
        if (profilePerms) profilePerms.forEach((perm) => permissions.add(perm));
        if (profileSets) {
          profileSets.forEach((setName) => {
            const setPerms = permissionSetPermissionsMap.get(setName);
            if (setPerms) setPerms.forEach((perm) => permissions.add(perm));
          });
        }
      });
      return {
        ...f,
        profiles: Array.from(profiles),
        permissionSets: Array.from(permissionSets),
        permissionsText: Array.from(permissions).join("\n"),
      };
    });
  }

  function clearUserProfiles() {
    setUserForm((f) => ({ ...f, profiles: [] }));
  }

  function toggleUserPermissionSet(value) {
    setUserForm((f) => {
      const currentSets = new Set(f.permissionSets || []);
      const permissions = new Set(parsePermissions(f.permissionsText));
      const isActive = currentSets.has(value);

      if (isActive) {
        currentSets.delete(value);
        const profiles = filterProfilesBySelections(
          f.profiles || [],
          permissions,
          Array.from(currentSets)
        );
        return {
          ...f,
          permissionSets: Array.from(currentSets),
          profiles,
          permissionsText: Array.from(permissions).join("\n"),
        };
      }

      currentSets.add(value);
      const setPerms = permissionSetPermissionsMap.get(value);
      if (setPerms) setPerms.forEach((perm) => permissions.add(perm));
      return {
        ...f,
        permissionSets: Array.from(currentSets),
        permissionsText: Array.from(permissions).join("\n"),
      };
    });
  }

  function selectAllUserPermissionSets() {
    setUserForm((f) => {
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

  function clearUserPermissionSets() {
    setUserForm((f) => {
      const permissions = new Set(parsePermissions(f.permissionsText));
      const profiles = filterProfilesBySelections(f.profiles || [], permissions, []);
      return { ...f, permissionSets: [], profiles, permissionsText: Array.from(permissions).join("\n") };
    });
  }

  return {
    selectedUser,
    setSelectedUser,
    userForm,
    setUserForm,
    userModalOpen,
    setUserModalOpen,
    userModalLoading,
    setUserModalLoading,
    userModalMode,
    setUserModalMode,
    userProfilesOpen,
    setUserProfilesOpen,
    userPermissionSetsOpen,
    setUserPermissionSetsOpen,
    userPermissionsOpen,
    setUserPermissionsOpen,
    savingUser,
    permissionsMessage,
    setPermissionsMessage,
    selectUser,
    openNewUserModal,
    saveUser,
    selectedUserProfiles,
    selectedUserPermissionSets,
    selectedUserPermissions,
    selectedUserPermissionSet,
    customUserPermissions,
    toggleUserPermission,
    selectAllUserPermissions,
    clearUserPermissions,
    toggleUserProfile,
    selectAllUserProfiles,
    clearUserProfiles,
    toggleUserPermissionSet,
    selectAllUserPermissionSets,
    clearUserPermissionSets,
    deleteUser,
  };
}

export function UsersModal({
  open,
  onClose,
  userModalLoading,
  userModalMode,
  selectedUser,
  userForm,
  setUserForm,
  companyTreeOptions,
  profileOptions,
  profileValues,
  userProfilesOpen,
  setUserProfilesOpen,
  selectAllUserProfiles,
  clearUserProfiles,
  selectedUserProfiles,
  toggleUserProfile,
  permissionSetList,
  permissionSetValues,
  userPermissionSetsOpen,
  setUserPermissionSetsOpen,
  selectAllUserPermissionSets,
  clearUserPermissionSets,
  selectedUserPermissionSets,
  toggleUserPermissionSet,
  userPermissionsOpen,
  setUserPermissionsOpen,
  selectedUserPermissions,
  permissionList,
  permissionsQuery,
  selectedUserPermissionSet,
  toggleUserPermission,
  selectAllUserPermissions,
  clearUserPermissions,
  customUserPermissions,
  isSelfUser,
  setConfirmDelete,
  saveUser,
  savingUser,
}) {
  const companyTreeSelectOptions = useMemo(
    () => [{ value: "", label: "Select company" }, ...(companyTreeOptions || [])],
    [companyTreeOptions]
  );
  const statusOptions = useMemo(
    () => [
      { value: "active", label: "Active" },
      { value: "inactive", label: "Inactive" },
    ],
    []
  );

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={userModalMode === "add" ? "Add user" : "Edit user"}
      maxWidth="560px"
    >
      {userModalLoading ? (
        <LoadingEllipsis text="Loading user" className="text-sm text-black/60 dark:text-white/65" />
      ) : userModalMode === "add" || selectedUser ? (
        <div className="space-y-3">
          {userModalMode === "edit" ? (
            <div className="text-xs text-black/50 dark:text-white/55">Editing {selectedUser?.email}</div>
          ) : null}
          <FormField label="Name">
            <input
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={userForm.name}
              onChange={(e) => setUserForm((f) => ({ ...f, name: e.target.value }))}
            />
          </FormField>
          <FormField label="Email">
            <input
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={userForm.email}
              onChange={(e) => setUserForm((f) => ({ ...f, email: e.target.value }))}
              type="email"
              disabled={userModalMode === "edit"}
            />
          </FormField>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <FormField label="Company">
              <SelectDropdown
                value={userForm.company || ""}
                treeOptions={companyTreeSelectOptions}
                onChange={(nextValue) => setUserForm((f) => ({ ...f, company: nextValue }))}
              />
            </FormField>
            <FormField label="Status">
              <SelectDropdown
                value={userForm.is_active ? "active" : "inactive"}
                options={statusOptions}
                onChange={(nextValue) => setUserForm((f) => ({ ...f, is_active: nextValue === "active" }))}
              />
            </FormField>
          </div>
          <FormField label="Profiles">
            <SoftCard className="p-4">
              <button
                type="button"
                className="flex w-full items-center justify-between gap-3 text-left"
                onClick={() => setUserProfilesOpen((openValue) => !openValue)}
                aria-expanded={userProfilesOpen}
              >
                <div>
                  <div className="text-sm font-semibold text-black/80 dark:text-white/85">Profiles</div>
                  <div className="text-xs text-black/55 dark:text-white/60">
                    {selectionLabel(userForm.profiles.length, "profile")}
                  </div>
                </div>
                <div className="flex items-center gap-2 text-xs text-black/50 dark:text-white/55">
                  <span>{userProfilesOpen ? "Hide" : "Edit"}</span>
                  <ChevronDown size={16} className={cn("transition-transform", userProfilesOpen && "rotate-180")} />
                </div>
              </button>

              {userProfilesOpen ? (
                <div className="mt-0 space-y-0">
                  <div className="flex flex-wrap items-center justify-end gap-2">
                    <div className="flex gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="rounded-xl"
                        onClick={selectAllUserProfiles}
                        disabled={!profileValues.length}
                      >
                        Select all
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="rounded-xl"
                        onClick={clearUserProfiles}
                        disabled={!userForm.profiles.length}
                      >
                        Clear
                      </Button>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-[168px] overflow-y-auto p-1">
                    {profileOptions.map((profile) => {
                      const value = profile.name || profile.id;
                      if (!value) return null;
                      const active = selectedUserProfiles.has(value);
                      return (
                        <button
                          key={value}
                          type="button"
                          onClick={() => toggleUserProfile(value)}
                          className={cn(
                            "mmg-profile-option flex items-center justify-between gap-3 rounded-xl px-3 py-1.5 text-xs ring-1 transition-colors",
                            active
                              ? "bg-black/5 dark:bg-white/10 ring-black/20 dark:ring-white/20 text-black dark:text-white"
                              : "bg-white/60 dark:bg-white/5 ring-black/5 dark:ring-white/10 text-black/70 dark:text-white/70 hover:bg-black/5 dark:hover:bg-white/10"
                          )}
                        >
                          <span className="min-w-0 truncate">{profile.display_name || profile.name || value}</span>
                          <span
                            className={cn(
                              "h-4 w-4 rounded-full flex items-center justify-center transition-colors",
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
                    {!profileOptions.length ? (
                      <div className="text-sm text-black/60 dark:text-white/65">No profiles available.</div>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </SoftCard>
          </FormField>
          <FormField label="Permission Sets">
            <SoftCard className="p-4">
              <button
                type="button"
                className="flex w-full items-center justify-between gap-3 text-left"
                onClick={() => setUserPermissionSetsOpen((openValue) => !openValue)}
                aria-expanded={userPermissionSetsOpen}
              >
                <div>
                  <div className="text-sm font-semibold text-black/80 dark:text-white/85">Permission sets</div>
                  <div className="text-xs text-black/55 dark:text-white/60">
                    {selectionLabel(userForm.permissionSets.length, "permission set", "permission sets")}
                  </div>
                </div>
                <div className="flex items-center gap-2 text-xs text-black/50 dark:text-white/55">
                  <span>{userPermissionSetsOpen ? "Hide" : "Edit"}</span>
                  <ChevronDown
                    size={16}
                    className={cn("transition-transform", userPermissionSetsOpen && "rotate-180")}
                  />
                </div>
              </button>

              {userPermissionSetsOpen ? (
                <div className="mt-0 space-y-0">
                  <div className="flex flex-wrap items-center justify-end gap-2">
                    <div className="flex gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="rounded-xl"
                        onClick={selectAllUserPermissionSets}
                        disabled={!permissionSetValues.length}
                      >
                        Select all
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="rounded-xl"
                        onClick={clearUserPermissionSets}
                        disabled={!userForm.permissionSets.length}
                      >
                        Clear
                      </Button>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-[168px] overflow-y-auto p-1">
                    {permissionSetList.map((set) => {
                      const value = set.name || set.id;
                      if (!value) return null;
                      const active = selectedUserPermissionSets.has(value);
                      return (
                        <button
                          key={value}
                          type="button"
                          onClick={() => toggleUserPermissionSet(value)}
                          className={cn(
                            "flex items-center justify-between gap-3 rounded-xl px-3 py-1.5 text-xs ring-1 transition-colors",
                            active
                              ? "bg-black/5 dark:bg-white/10 ring-black/20 dark:ring-white/20 text-black dark:text-white"
                              : "bg-white/60 dark:bg-white/5 ring-black/5 dark:ring-white/10 text-black/70 dark:text-white/70 hover:bg-black/5 dark:hover:bg-white/10"
                          )}
                        >
                          <span className="min-w-0 truncate">{set.display_name || set.name || value}</span>
                          <span
                            className={cn(
                              "h-4 w-4 rounded-full flex items-center justify-center transition-colors",
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
                    {!permissionSetList.length ? (
                      <div className="text-sm text-black/60 dark:text-white/65">No permission sets available.</div>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </SoftCard>
          </FormField>
          <FormField label="Permissions">
            <SoftCard className="p-4">
              <button
                type="button"
                className="flex w-full items-center justify-between gap-3 text-left"
                onClick={() => setUserPermissionsOpen((openValue) => !openValue)}
                aria-expanded={userPermissionsOpen}
              >
                <div>
                  <div className="text-sm font-semibold text-black/80 dark:text-white/85">Permissions</div>
                  <div className="text-xs text-black/55 dark:text-white/60">
                    {selectionLabel(selectedUserPermissions.length, "permission")}
                  </div>
                </div>
                <div className="flex items-center gap-2 text-xs text-black/50 dark:text-white/55">
                  <span>{userPermissionsOpen ? "Hide" : "Edit"}</span>
                  <ChevronDown
                    size={16}
                    className={cn("transition-transform", userPermissionsOpen && "rotate-180")}
                  />
                </div>
              </button>

              {userPermissionsOpen ? (
                <div className="mt-0 space-y-0">
                  <div className="flex flex-wrap items-center justify-end gap-2">
                    <div className="flex gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="rounded-xl"
                        onClick={selectAllUserPermissions}
                        disabled={!permissionList.length}
                      >
                        Select all
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="rounded-xl"
                        onClick={clearUserPermissions}
                        disabled={!selectedUserPermissions.length}
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
                        const active = selectedUserPermissionSet.has(perm);
                        return (
                          <button
                            key={perm}
                            type="button"
                            onClick={() => toggleUserPermission(perm)}
                            className={cn(
                              "flex items-center justify-between gap-3 rounded-xl px-3 py-1.5 text-xs ring-1 transition-colors",
                              active
                                ? "bg-black/5 dark:bg-white/10 ring-black/20 dark:ring-white/20 text-black dark:text-white"
                                : "bg-white/60 dark:bg-white/5 ring-black/5 dark:ring-white/10 text-black/70 dark:text-white/70 hover:bg-black/5 dark:hover:bg-white/10"
                            )}
                          >
                            <span className="min-w-0 truncate">{perm}</span>
                            <span
                              className={cn(
                                "h-4 w-4 rounded-full flex items-center justify-center transition-colors",
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

                  {customUserPermissions.length ? (
                    <div className="rounded-2xl bg-white/50 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 p-3">
                      <div className="text-xs font-semibold text-black/60 dark:text-white/65">Custom permissions</div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {customUserPermissions.map((perm) => (
                          <button
                            key={perm}
                            type="button"
                            onClick={() => toggleUserPermission(perm)}
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
          <div className="flex gap-2 justify-end">
            {userModalMode === "edit" ? (
              <Button
                variant="ghost"
                className={cn(
                  "rounded-2xl",
                  typeof selectedUser?.is_active === "boolean" && !selectedUser?.is_active
                    ? "text-emerald-600 hover:text-emerald-700 dark:text-emerald-300"
                    : "text-red-600 hover:text-red-700 dark:text-red-300"
                )}
                onClick={() =>
                  setConfirmDelete({
                    open: true,
                    type: "user",
                    payload: {
                      id: selectedUser?.id,
                      isActive:
                        typeof selectedUser?.is_active === "boolean"
                          ? selectedUser?.is_active
                          : true,
                    },
                    label: `${
                      typeof selectedUser?.is_active === "boolean"
                        ? selectedUser?.is_active
                          ? "Deactivate"
                          : "Reactivate"
                        : "Deactivate"
                    } user \"${selectedUser?.email}\"?`,
                  })
                }
                disabled={isSelfUser}
              >
                {typeof selectedUser?.is_active === "boolean"
                  ? selectedUser?.is_active
                    ? "Deactivate"
                    : "Reactivate"
                  : "Deactivate"}
              </Button>
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              <Button variant="ghost" className="rounded-2xl" onClick={onClose}>
                Cancel
              </Button>
              <Button className="rounded-2xl" onClick={saveUser} disabled={savingUser}>
                {savingUser ? <LoadingEllipsis text="Saving" /> : "Save"}
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <div className="text-sm text-black/60 dark:text-white/65">Select a user to edit.</div>
      )}
    </Modal>
  );
}

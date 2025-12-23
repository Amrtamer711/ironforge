import React, { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { adminApi } from "../../api";
import { useAuth, canAccessAdmin } from "../../state/auth";
import { cn } from "../../lib/utils";

const PAGE_SIZE = 20;

function parsePermissions(text) {
  return text.split(/\n|,/).map((p) => p.trim()).filter(Boolean);
}

function selectionLabel(count, singular, plural = `${singular}s`) {
  if (!count) return `No ${plural} selected`;
  return `${count} ${count === 1 ? singular : plural} selected`;
}

export function AdminPage() {
  const { user } = useAuth();
  const qc = useQueryClient();

  const [tab, setTab] = useState("users");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
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

  const [companyForm, setCompanyForm] = useState({
    code: "",
    name: "",
    parent_id: "",
    country: "",
    currency: "",
    timezone: "",
    isgroup: false,
    is_active: true,
  });
  const [editingCompany, setEditingCompany] = useState(null);
  const [companyModalOpen, setCompanyModalOpen] = useState(false);
  const [savingCompany, setSavingCompany] = useState(false);

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

  const [permissionModal, setPermissionModal] = useState({ open: false, mode: "add", value: "", original: "" });
  const [savingPermission, setSavingPermission] = useState(false);
  const [savingUser, setSavingUser] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);
  const [permissionsMessage, setPermissionsMessage] = useState("");
  const [confirmDelete, setConfirmDelete] = useState({ open: false, type: "", payload: null, label: "" });

  if (!canAccessAdmin(user)) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Restricted</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-black/60 dark:text-white/65">
          You don't have access to the admin panel.
        </CardContent>
      </Card>
    );
  }

  const usersQuery = useQuery({
    queryKey: ["admin", "users", page],
    queryFn: () => adminApi.getUsers({ limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
  });

  const profilesQuery = useQuery({
    queryKey: ["admin", "profiles"],
    queryFn: adminApi.getProfiles,
  });

  const permissionsQuery = useQuery({
    queryKey: ["admin", "permissions"],
    queryFn: adminApi.getPermissions,
  });

  const companiesQuery = useQuery({
    queryKey: ["admin", "companies"],
    queryFn: adminApi.getCompanies,
  });

  const permissionSetsQuery = useQuery({
    queryKey: ["admin", "permission-sets"],
    queryFn: adminApi.getPermissionSets,
  });

  const users = useMemo(() => {
    const list = usersQuery.data?.users || usersQuery.data || [];
    const needle = q.trim().toLowerCase();
    if (!needle) return list;
    return list.filter((u) => {
      const profileName = Array.isArray(u.profiles)
        ? u.profiles.map((p) => p?.display_name || p?.name || p).filter(Boolean).join(" ")
        : u.profiles?.display_name || u.profiles?.name || u.profile || u.profile_name || "";
      const s = `${u.email || ""} ${u.name || ""} ${profileName}`.toLowerCase();
      return s.includes(needle);
    });
  }, [usersQuery.data, q]);

  const hasNext = useMemo(() => {
    const list = usersQuery.data?.users || usersQuery.data || [];
    return list.length === PAGE_SIZE;
  }, [usersQuery.data]);

  useEffect(() => {
    setSelectedUser(null);
  }, [page]);

  function openProfileModal(profile) {
    setProfileIsSystem(Boolean(profile?.is_system));
    if (profile?.is_system) return;
    setProfilePermissionSetsOpen(false);
    setProfilePermissionsOpen(false);
    if (profile) {
      setEditingProfile(profile.name);
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

  function openPermissionModal(mode = "add", value = "") {
    setPermissionModal({ open: true, mode, value, original: value });
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
    const profileValues = Array.isArray(u.profiles)
      ? u.profiles.map((p) => p?.name || p?.id || p).filter(Boolean)
      : [u.profiles?.name || u.profile || u.profile_name].filter(Boolean);
    const permissionSetValues =
      (u.permission_sets || u.permissionSets || u.permission_set_names || [])
        .map((set) => (typeof set === "string" ? set : set?.name || set?.id))
        .filter(Boolean);
    setUserForm({
      name: u.name || "",
      email: u.email || "",
      profiles: profileValues,
      permissionSets: permissionSetValues,
      company: u.company?.code || u.company_code || u.company_id || "",
      is_active: u.is_active !== false,
      permissionsText: "",
    });

    const userId = u.id || u.user_id;
    if (userId) {
      try {
        const perms = await adminApi.getUserPermissions(userId);
        const raw = perms?.permissions ?? perms;
        const list = Array.isArray(raw)
          ? raw.map((perm) => (typeof perm === "string" ? perm : perm?.name)).filter(Boolean)
          : [];
        setUserForm((f) => ({ ...f, permissionsText: list.join("\n") }));
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
    const userId = selectedUser?.id || selectedUser?.user_id;
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
        const createdId = created?.id || created?.user_id || created?.user?.id || created?.user?.user_id;
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

  function openCompanyModal(company) {
    if (company) {
      setEditingCompany(company.code || company.id);
      setCompanyForm({
        code: company.code || "",
        name: company.name || "",
        parent_id: company.parent_id ?? "",
        country: company.country ?? "",
        currency: company.currency ?? "",
        timezone: company.timezone ?? "",
        isgroup: Boolean(company.isgroup),
        is_active: company.is_active !== false,
      });
    } else {
      setEditingCompany(null);
      setCompanyForm({
        code: "",
        name: "",
        parent_id: "",
        country: "",
        currency: "",
        timezone: "",
        isgroup: false,
        is_active: true,
      });
    }
    setCompanyModalOpen(true);
  }

  async function saveCompany() {
    if (!companyForm.code.trim() || !companyForm.name.trim()) return;
    setSavingCompany(true);
    const payload = {
      code: companyForm.code.trim(),
      name: companyForm.name.trim(),
      parent_id: companyForm.parent_id || null,
      country: companyForm.country || null,
      currency: companyForm.currency || null,
      timezone: companyForm.timezone || null,
      isgroup: Boolean(companyForm.isgroup),
      is_active: Boolean(companyForm.is_active),
    };
    try {
      if (editingCompany) {
        await adminApi.updateCompany(editingCompany, payload);
      } else {
        await adminApi.createCompany(payload);
      }
      qc.invalidateQueries({ queryKey: ["admin", "companies"] });
      setCompanyModalOpen(false);
      setEditingCompany(null);
    } catch {
      // ignore
    } finally {
      setSavingCompany(false);
    }
  }

  async function deleteCompany(code) {
    if (!code) return;
    try {
      await adminApi.deleteCompany(code);
      qc.invalidateQueries({ queryKey: ["admin", "companies"] });
      setCompanyModalOpen(false);
      setEditingCompany(null);
    } catch {
      // ignore
    }
  }

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

  async function savePermissionModal() {
    const value = permissionModal.value.trim();
    if (!value) return;
    setSavingPermission(true);
    try {
      if (permissionModal.mode === "add") {
        await adminApi.addPermission(value);
      } else if (value !== permissionModal.original) {
        await adminApi.addPermission(value);
        await adminApi.deletePermission(permissionModal.original);
      } else {
        setPermissionModal({ open: false, mode: "add", value: "", original: "" });
        return;
      }
      qc.invalidateQueries({ queryKey: ["admin", "permissions"] });
      setPermissionModal({ open: false, mode: "add", value: "", original: "" });
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
      qc.invalidateQueries({ queryKey: ["admin", "permissions"] });
      setPermissionModal({ open: false, mode: "add", value: "", original: "" });
    } catch {
      // ignore
    } finally {
      setSavingPermission(false);
    }
  }

  async function handleConfirmDelete() {
    if (!confirmDelete.open) return;
    try {
      if (confirmDelete.type === "profile" && confirmDelete.payload) {
        await deleteProfile(confirmDelete.payload);
      }
      if (confirmDelete.type === "permission" && confirmDelete.payload) {
        await deletePermissionFromModal(confirmDelete.payload);
      }
      if (confirmDelete.type === "company" && confirmDelete.payload) {
        await deleteCompany(confirmDelete.payload);
      }
      if (confirmDelete.type === "permission-set" && confirmDelete.payload) {
        await deletePermissionSet(confirmDelete.payload);
      }
      if (confirmDelete.type === "user" && confirmDelete.payload) {
        if (
          confirmDelete.payload === user?.id ||
          confirmDelete.payload === user?.user_id
        ) {
          return;
        }
        await adminApi.deleteUser(confirmDelete.payload);
        qc.invalidateQueries({ queryKey: ["admin", "users"] });
        setUserModalOpen(false);
        setSelectedUser(null);
      }
    } finally {
      setConfirmDelete({ open: false, type: "", payload: null, label: "" });
    }
  }

  const profileOptions = useMemo(() => {
    const raw = profilesQuery.data?.profiles ?? profilesQuery.data;
    return Array.isArray(raw) ? raw : [];
  }, [profilesQuery.data]);
  const permissionList = useMemo(() => {
    const raw = permissionsQuery.data?.permissions ?? permissionsQuery.data;
    if (!Array.isArray(raw)) return [];
    return raw.map((perm) => (typeof perm === "string" ? perm : perm?.name)).filter(Boolean);
  }, [permissionsQuery.data]);
  const companyList = useMemo(() => {
    const raw = companiesQuery.data?.companies ?? companiesQuery.data;
    return Array.isArray(raw) ? raw : [];
  }, [companiesQuery.data]);
  const permissionSetList = useMemo(() => {
    const raw =
      permissionSetsQuery.data?.permission_sets ??
      permissionSetsQuery.data?.permissionSets ??
      permissionSetsQuery.data;
    if (!Array.isArray(raw)) return [];
    return raw.map((set) => (typeof set === "string" ? { name: set } : set));
  }, [permissionSetsQuery.data]);
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
  const permissionSetValues = useMemo(
    () =>
      permissionSetList
        .map((set) => set.name || set.id)
        .filter(Boolean),
    [permissionSetList]
  );
  const selectedPermissionSetPermissions = useMemo(
    () => parsePermissions(permissionSetForm.permissionsText),
    [permissionSetForm.permissionsText]
  );
  const selectedPermissionSetPermissionSet = useMemo(
    () => new Set(selectedPermissionSetPermissions),
    [selectedPermissionSetPermissions]
  );
  const profileValues = useMemo(
    () => profileOptions.map((profile) => profile.name || profile.id).filter(Boolean),
    [profileOptions]
  );
  const selectedUserProfiles = useMemo(
    () => new Set(userForm.profiles || []),
    [userForm.profiles]
  );
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
  const customProfilePermissions = useMemo(() => {
    if (!permissionList.length) return selectedProfilePermissions;
    const known = new Set(permissionList);
    return selectedProfilePermissions.filter((perm) => !known.has(perm));
  }, [permissionList, selectedProfilePermissions]);
  const customPermissionSetPermissions = useMemo(() => {
    if (!permissionList.length) return selectedPermissionSetPermissions;
    const known = new Set(permissionList);
    return selectedPermissionSetPermissions.filter((perm) => !known.has(perm));
  }, [permissionList, selectedPermissionSetPermissions]);
  const customUserPermissions = useMemo(() => {
    if (!permissionList.length) return selectedUserPermissions;
    const known = new Set(permissionList);
    return selectedUserPermissions.filter((perm) => !known.has(perm));
  }, [permissionList, selectedUserPermissions]);
  const companyLookup = useMemo(() => {
    const map = new Map();
    companyList.forEach((company) => {
      const key = company.code || company.id;
      if (key) map.set(key, company.name || company.code || key);
    });
    return map;
  }, [companyList]);
  const isSelfUser = Boolean(
    selectedUser &&
      (selectedUser.id === user?.id ||
        selectedUser.user_id === user?.user_id ||
        selectedUser.email === user?.email)
  );

  function toggleProfilePermission(value) {
    setProfileForm((f) => {
      const current = new Set(parsePermissions(f.permissionsText));
      if (current.has(value)) current.delete(value);
      else current.add(value);
      return { ...f, permissionsText: Array.from(current).join("\n") };
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
      const current = new Set(f.permissionSets || []);
      if (current.has(value)) current.delete(value);
      else current.add(value);
      return { ...f, permissionSets: Array.from(current) };
    });
  }

  function selectAllProfilePermissionSets() {
    const combined = new Set([...(profileForm.permissionSets || []), ...permissionSetValues]);
    setProfileForm((f) => ({ ...f, permissionSets: Array.from(combined) }));
  }

  function clearProfilePermissionSets() {
    setProfileForm((f) => ({ ...f, permissionSets: [] }));
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

  function toggleUserPermission(value) {
    setUserForm((f) => {
      const current = new Set(parsePermissions(f.permissionsText));
      if (current.has(value)) current.delete(value);
      else current.add(value);
      return { ...f, permissionsText: Array.from(current).join("\n") };
    });
  }

  function selectAllUserPermissions() {
    const combined = new Set([...selectedUserPermissions, ...permissionList]);
    setUserForm((f) => ({ ...f, permissionsText: Array.from(combined).join("\n") }));
  }

  function clearUserPermissions() {
    setUserForm((f) => ({ ...f, permissionsText: "" }));
  }

  function toggleUserProfile(value) {
    setUserForm((f) => {
      const current = new Set(f.profiles || []);
      if (current.has(value)) current.delete(value);
      else current.add(value);
      return { ...f, profiles: Array.from(current) };
    });
  }

  function selectAllUserProfiles() {
    const combined = new Set([...(userForm.profiles || []), ...profileValues]);
    setUserForm((f) => ({ ...f, profiles: Array.from(combined) }));
  }

  function clearUserProfiles() {
    setUserForm((f) => ({ ...f, profiles: [] }));
  }

  function toggleUserPermissionSet(value) {
    setUserForm((f) => {
      const current = new Set(f.permissionSets || []);
      if (current.has(value)) current.delete(value);
      else current.add(value);
      return { ...f, permissionSets: Array.from(current) };
    });
  }

  function selectAllUserPermissionSets() {
    const combined = new Set([...(userForm.permissionSets || []), ...permissionSetValues]);
    setUserForm((f) => ({ ...f, permissionSets: Array.from(combined) }));
  }

  function clearUserPermissionSets() {
    setUserForm((f) => ({ ...f, permissionSets: [] }));
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden">
      <div className="flex items-center gap-2 overflow-x-auto pb-1 px-1">
        <Button variant={tab === "users" ? "default" : "ghost"} onClick={() => setTab("users")} className="rounded-2xl shrink-0">
          Users
        </Button>
        <Button variant={tab === "companies" ? "default" : "ghost"} onClick={() => setTab("companies")} className="rounded-2xl shrink-0">
          Companies
        </Button>
        <Button variant={tab === "profiles" ? "default" : "ghost"} onClick={() => setTab("profiles")} className="rounded-2xl shrink-0">
          Profiles
        </Button>
        <Button variant={tab === "permission-sets" ? "default" : "ghost"} onClick={() => setTab("permission-sets")} className="rounded-2xl shrink-0">
          Permission Sets
        </Button>
        <Button variant={tab === "permissions" ? "default" : "ghost"} onClick={() => setTab("permissions")} className="rounded-2xl shrink-0">
          Permissions
        </Button>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto px-2 py-1 space-y-4">
      {tab === "users" ? (
        <Card className="flex-1 min-h-0">
          <CardHeader className="flex flex-row items-start justify-between">
            <CardTitle>Users</CardTitle>
            <div className="flex flex-col gap-2 md:flex-row md:items-center">
              <Button variant="secondary" size="sm" className="rounded-xl self-end md:self-auto" onClick={openNewUserModal}>
                Add user
              </Button>
              <div className="flex w-full flex-col gap-2 md:w-auto md:flex-row md:items-center md:ml-auto">
                <input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Search users…"
                  className="w-full md:w-[220px] rounded-2xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                />
                <div className="flex w-full justify-end gap-1 md:w-auto">
                  <Button variant="ghost" size="sm" className="rounded-xl" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>
                    Prev
                  </Button>
                  <Button variant="ghost" size="sm" className="rounded-xl" disabled={!hasNext} onClick={() => setPage((p) => p + 1)}>
                    Next
                  </Button>
                </div>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {usersQuery.isLoading ? (
              <div className="text-sm text-black/60 dark:text-white/65">Loading…</div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 p-1">
                {users.map((u) => {
                  const profileLabels = Array.isArray(u.profiles)
                    ? u.profiles.map((p) => p?.display_name || p?.name || p).filter(Boolean)
                    : [u.profiles?.display_name || u.profiles?.name || u.profile || u.profile_name].filter(Boolean);
                  const profileText = profileLabels.length
                    ? profileLabels.length > 2
                      ? `${profileLabels[0]}, +${profileLabels.length - 1}`
                      : profileLabels.join(", ")
                    : "—";
                  const isSelfCard = Boolean(
                    u.id === user?.id || u.user_id === user?.user_id || u.email === user?.email
                  );
                  return (
                    <div
                      key={u.id || u.user_id || u.email}
                      className="rounded-2xl p-4 bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 shadow-soft space-y-2"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="text-sm font-semibold">{u.name || "—"}</div>
                          <div className="text-xs text-black/55 dark:text-white/60">{u.email}</div>
                        </div>
                        <div className="flex gap-2">
                          <Button variant="secondary" size="sm" className="rounded-xl" onClick={() => selectUser(u)}>
                            Edit
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="rounded-xl"
                            onClick={() =>
                              setConfirmDelete({
                                open: true,
                                type: "user",
                                payload: u.id || u.user_id,
                                label: `Delete user "${u.email}"?`,
                              })
                            }
                            disabled={isSelfCard}
                          >
                            Delete
                          </Button>
                        </div>
                      </div>
                      <div className="text-xs text-black/55 dark:text-white/60">
                        Profiles: <span className="font-semibold">{profileText}</span>
                      </div>
                      <div className="text-xs text-black/55 dark:text-white/60">
                        Company:{" "}
                        <span className="font-semibold">
                          {u.company?.name || companyLookup.get(u.company?.code || u.company_code || u.company_id) || "—"}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

          </CardContent>
        </Card>
      ) : null}

      {tab === "companies" ? (
        <Card>
          <CardHeader className="flex flex-row items-start justify-between">
            <CardTitle>Companies</CardTitle>
            <Button variant="secondary" className="rounded-2xl" onClick={() => openCompanyModal(null)}>
              Add company
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {companiesQuery.isLoading ? (
              <div className="text-sm text-black/60 dark:text-white/65">Loading…</div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {companyList.map((company) => (
                  <div
                    key={company.code || company.id}
                    className="rounded-2xl p-4 bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 shadow-soft space-y-2"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-sm font-semibold">{company.name || company.code}</div>
                        <div className="text-xs text-black/55 dark:text-white/60">{company.code || "—"}</div>
                      </div>
                      <div className="flex gap-2">
                        <Button variant="secondary" size="sm" className="rounded-xl" onClick={() => openCompanyModal(company)}>
                          Edit
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="rounded-xl"
                          onClick={() =>
                            setConfirmDelete({
                              open: true,
                              type: "company",
                              payload: company.code || company.id,
                              label: `Delete company "${company.name || company.code}"?`,
                            })
                          }
                        >
                          Delete
                        </Button>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2 text-xs text-black/55 dark:text-white/60">
                      {company.country ? <span>{company.country}</span> : null}
                      {company.currency ? <span>• {company.currency}</span> : null}
                      {company.timezone ? <span>• {company.timezone}</span> : null}
                    </div>
                    <div className="flex flex-wrap gap-2 text-xs text-black/55 dark:text-white/60">
                      <span>Parent: {companyLookup.get(company.parent_id) || "—"}</span>
                      <span>• {company.isgroup ? "Group" : "Company"}</span>
                      <span>• {company.is_active === false ? "Inactive" : "Active"}</span>
                    </div>
                  </div>
                ))}
                {!companyList.length ? (
                  <div className="text-sm text-black/60 dark:text-white/65">No companies available.</div>
                ) : null}
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}

      {tab === "profiles" ? (
        <Card>
          <CardHeader className="flex flex-row items-start justify-between">
            <CardTitle>Profiles</CardTitle>
            <Button variant="secondary" className="rounded-2xl" onClick={() => openProfileModal(null)}>
              Add profile
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {profileOptions.map((p) => (
                <div
                  key={p.name}
                  className="rounded-2xl p-4 bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 shadow-soft space-y-1"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm font-semibold">{p.display_name || p.name}</div>
                      <div className="text-xs text-black/55 dark:text-white/60">{p.name}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        className="rounded-xl"
                        onClick={() => duplicateProfile(p)}
                      >
                        Duplicate
                      </Button>
                      {!p.is_system ? (
                        <>
                          <Button
                            variant="secondary"
                            size="sm"
                            className="rounded-xl"
                            onClick={() => openProfileModal(p)}
                          >
                            Edit
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="rounded-xl"
                            onClick={() =>
                              setConfirmDelete({
                                open: true,
                                type: "profile",
                                payload: p.name,
                                label: `Delete profile "${p.display_name || p.name}"?`,
                              })
                            }
                          >
                            Delete
                          </Button>
                        </>
                      ) : (
                        <span className="text-[11px] rounded-full px-2 py-0.5 bg-black/5 dark:bg-white/10">System</span>
                      )}
                    </div>
                  </div>
                  <div className="text-xs text-black/55 dark:text-white/60">
                    {(p.permissions || []).length} permission{(p.permissions || []).length === 1 ? "" : "s"}
                  </div>
                  {p.description ? <div className="text-xs text-black/60 dark:text-white/65">{p.description}</div> : null}
                </div>
              ))}
            </div>

          </CardContent>
        </Card>
      ) : null}

      {tab === "permission-sets" ? (
        <Card>
          <CardHeader className="flex flex-row items-start justify-between">
            <CardTitle>Permission Sets</CardTitle>
            <Button variant="secondary" className="rounded-2xl" onClick={() => openPermissionSetModal(null)}>
              Add permission set
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {permissionSetsQuery.isLoading ? (
              <div className="text-sm text-black/60 dark:text-white/65">Loading…</div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {permissionSetList.map((set) => (
                  <div
                    key={set.name}
                    className="rounded-2xl p-4 bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 shadow-soft space-y-1"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-sm font-semibold">{set.display_name || set.name}</div>
                        <div className="text-xs text-black/55 dark:text-white/60">{set.name}</div>
                      </div>
                      <div className="flex gap-2">
                        <Button
                          variant="secondary"
                          size="sm"
                          className="rounded-xl"
                          onClick={() => duplicatePermissionSet(set)}
                        >
                          Duplicate
                        </Button>
                        <Button
                          variant="secondary"
                          size="sm"
                          className="rounded-xl"
                          onClick={() => openPermissionSetModal(set)}
                        >
                          Edit
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="rounded-xl"
                          onClick={() =>
                            setConfirmDelete({
                              open: true,
                              type: "permission-set",
                              payload: set.name,
                              label: `Delete permission set "${set.display_name || set.name}"?`,
                            })
                          }
                        >
                          Delete
                        </Button>
                      </div>
                    </div>
                    <div className="text-xs text-black/55 dark:text-white/60">
                      {(set.permissions || []).length} permission{(set.permissions || []).length === 1 ? "" : "s"}
                    </div>
                    {set.description ? <div className="text-xs text-black/60 dark:text-white/65">{set.description}</div> : null}
                  </div>
                ))}
                {!permissionSetList.length ? (
                  <div className="text-sm text-black/60 dark:text-white/65">No permission sets available.</div>
                ) : null}
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}

      {tab === "permissions" ? (
        <Card>
          <CardHeader className="flex flex-row items-start justify-between">
            <CardTitle>Permissions</CardTitle>
            <Button className="rounded-2xl" variant="secondary" onClick={() => openPermissionModal("add", "")}>
              Add permission
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {permissionsQuery.isLoading ? (
              <div className="text-sm text-black/60 dark:text-white/65">Loading…</div>
            ) : (
              <div className="flex flex-wrap gap-2">
                {permissionList.map((p) => (
                  <span
                    key={p}
                    className="inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 cursor-pointer"
                    onClick={() => openPermissionModal("edit", p)}
                  >
                    <span>{p}</span>
                  </span>
                ))}
                {!permissionList.length ? <div className="text-sm text-black/60 dark:text-white/65">No permissions available.</div> : null}
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}
      </div>

      <Modal
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
        title={userModalMode === "add" ? "Add user" : "Edit user"}
        maxWidth="560px"
      >
        {userModalLoading ? (
          <div className="text-sm text-black/60 dark:text-white/65">Loading user...</div>
        ) : userModalMode === "add" || selectedUser ? (
          <div className="space-y-3">
            {userModalMode === "edit" ? (
              <div className="text-xs text-black/50 dark:text-white/55">Editing {selectedUser?.email}</div>
            ) : null}
            <Field label="Name">
              <input
                className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                value={userForm.name}
                onChange={(e) => setUserForm((f) => ({ ...f, name: e.target.value }))}
              />
            </Field>
            <Field label="Email">
              <input
                className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                value={userForm.email}
                onChange={(e) => setUserForm((f) => ({ ...f, email: e.target.value }))}
                type="email"
                disabled={userModalMode === "edit"}
              />
            </Field>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field label="Company">
                <select
                  className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                  value={userForm.company}
                  onChange={(e) => setUserForm((f) => ({ ...f, company: e.target.value }))}
                >
                  <option value="">Select company</option>
                  {companyList.map((company) => {
                    const value = company.code || company.id;
                    return (
                      <option key={value} value={value}>
                        {company.name || company.code || value}
                      </option>
                    );
                  })}
                </select>
              </Field>
              <Field label="Status">
                <select
                  className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                  value={userForm.is_active ? "active" : "inactive"}
                  onChange={(e) => setUserForm((f) => ({ ...f, is_active: e.target.value === "active" }))}
                >
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </select>
              </Field>
            </div>
            <Field label="Profiles">
              <div className="rounded-2xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 p-4 shadow-soft">
                <button
                  type="button"
                  className="flex w-full items-center justify-between gap-3 text-left"
                  onClick={() => setUserProfilesOpen((open) => !open)}
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
                    <ChevronDown
                      size={16}
                      className={cn("transition-transform", userProfilesOpen && "rotate-180")}
                    />
                  </div>
                </button>

                {userProfilesOpen ? (
                  <div className="mt-3 space-y-3">
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
                              "mmg-profile-option flex items-center justify-between gap-3 rounded-xl px-3 py-2 text-sm ring-1 transition-colors",
                              active
                                ? "bg-black/5 dark:bg-white/10 ring-black/20 dark:ring-white/20 text-black dark:text-white"
                                : "bg-white/60 dark:bg-white/5 ring-black/5 dark:ring-white/10 text-black/70 dark:text-white/70 hover:bg-black/5 dark:hover:bg-white/10"
                            )}
                          >
                            <span className="min-w-0 truncate">{profile.display_name || profile.name || value}</span>
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
                      {!profileOptions.length ? (
                        <div className="text-sm text-black/60 dark:text-white/65">No profiles available.</div>
                      ) : null}
                    </div>
                  </div>
                ) : null}
              </div>
            </Field>
            <Field label="Permission Sets">
              <div className="rounded-2xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 p-4 shadow-soft">
                <button
                  type="button"
                  className="flex w-full items-center justify-between gap-3 text-left"
                  onClick={() => setUserPermissionSetsOpen((open) => !open)}
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
                  <div className="mt-3 space-y-3">
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
                              "flex items-center justify-between gap-3 rounded-xl px-3 py-2 text-sm ring-1 transition-colors",
                              active
                                ? "bg-black/5 dark:bg-white/10 ring-black/20 dark:ring-white/20 text-black dark:text-white"
                                : "bg-white/60 dark:bg-white/5 ring-black/5 dark:ring-white/10 text-black/70 dark:text-white/70 hover:bg-black/5 dark:hover:bg-white/10"
                            )}
                          >
                            <span className="min-w-0 truncate">{set.display_name || set.name || value}</span>
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
                      {!permissionSetList.length ? (
                        <div className="text-sm text-black/60 dark:text-white/65">
                          No permission sets available.
                        </div>
                      ) : null}
                    </div>
                  </div>
                ) : null}
              </div>
            </Field>
            <Field label="Permissions">
              <div className="rounded-2xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 p-4 shadow-soft">
                <button
                  type="button"
                  className="flex w-full items-center justify-between gap-3 text-left"
                  onClick={() => setUserPermissionsOpen((open) => !open)}
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
                  <div className="mt-3 space-y-3">
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
                      <div className="text-sm text-black/60 dark:text-white/65">Loading permissions...</div>
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

                    {customUserPermissions.length ? (
                      <div className="rounded-2xl bg-white/50 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 p-3">
                        <div className="text-xs font-semibold text-black/60 dark:text-white/65">
                          Custom permissions
                        </div>
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
              </div>
            </Field>
            <div className="flex gap-2 justify-end">
              {userModalMode === "edit" ? (
                <Button
                  variant="ghost"
                  className="rounded-2xl text-red-600 hover:text-red-700 dark:text-red-300"
                  onClick={() =>
                    setConfirmDelete({
                      open: true,
                      type: "user",
                      payload: selectedUser?.id || selectedUser?.user_id,
                      label: `Delete user "${selectedUser?.email}"?`,
                    })
                  }
                  disabled={isSelfUser}
                >
                  Delete
                </Button>
              ) : (
                <span />
              )}
              <div className="flex gap-2">
                <Button variant="ghost" className="rounded-2xl" onClick={() => setUserModalOpen(false)}>
                  Cancel
                </Button>
                <Button className="rounded-2xl" onClick={saveUser} disabled={savingUser}>
                  {savingUser ? "Saving..." : "Save"}
                </Button>
              </div>
            </div>
          </div>
        ) : (
          <div className="text-sm text-black/60 dark:text-white/65">Select a user to edit.</div>
        )}
      </Modal>

      <Modal
        open={profileModalOpen}
        onClose={() => {
          setProfileModalOpen(false);
          setEditingProfile(null);
          setProfileForm({ name: "", display_name: "", description: "", permissionsText: "", permissionSets: [] });
          setProfileIsSystem(false);
          setProfilePermissionSetsOpen(false);
          setProfilePermissionsOpen(false);
        }}
        title={editingProfile ? `Edit profile: ${editingProfile}` : "Add profile"}
        maxWidth="640px"
      >
        <div className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="Name">
              <input
                className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                value={profileForm.name}
                onChange={(e) => setProfileForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="system_admin"
                disabled={Boolean(editingProfile)}
              />
            </Field>
            <Field label="Display Name">
              <input
                className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                value={profileForm.display_name}
                onChange={(e) => setProfileForm((f) => ({ ...f, display_name: e.target.value }))}
                placeholder="System Admin"
              />
            </Field>
          </div>
          <Field label="Description">
            <input
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={profileForm.description}
              onChange={(e) => setProfileForm((f) => ({ ...f, description: e.target.value }))}
              placeholder="What this profile can do"
            />
          </Field>
          <Field label="Permission Sets">
            <div className="rounded-2xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 p-4 shadow-soft">
              <button
                type="button"
                className="flex w-full items-center justify-between gap-3 text-left"
                onClick={() => setProfilePermissionSetsOpen((open) => !open)}
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
                <div className="mt-3 space-y-3">
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
                    <div className="text-sm text-black/60 dark:text-white/65">Loading permission sets...</div>
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
            </div>
          </Field>
          <Field label="Permissions">
            <div className="rounded-2xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 p-4 shadow-soft">
              <button
                type="button"
                className="flex w-full items-center justify-between gap-3 text-left"
                onClick={() => setProfilePermissionsOpen((open) => !open)}
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
                <div className="mt-3 space-y-3">
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
                    <div className="text-sm text-black/60 dark:text-white/65">Loading permissions...</div>
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
            </div>
          </Field>
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
              <Button
                variant="ghost"
                className="rounded-2xl"
                onClick={() => {
                  setProfileModalOpen(false);
                  setEditingProfile(null);
                  setProfileForm({ name: "", display_name: "", description: "", permissionsText: "", permissionSets: [] });
                }}
              >
                Cancel
              </Button>
              <Button className="rounded-2xl" onClick={saveProfile} disabled={savingProfile || profileIsSystem}>
                {savingProfile ? "Saving..." : "Save"}
              </Button>
            </div>
          </div>
        </div>
      </Modal>

      <Modal
        open={companyModalOpen}
        onClose={() => {
          setCompanyModalOpen(false);
          setEditingCompany(null);
          setCompanyForm({
            code: "",
            name: "",
            parent_id: "",
            country: "",
            currency: "",
            timezone: "",
            isgroup: false,
            is_active: true,
          });
        }}
        title={editingCompany ? `Edit company: ${companyForm.name || companyForm.code}` : "Add company"}
        maxWidth="640px"
      >
        <div className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="Code">
              <input
                className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                value={companyForm.code}
                onChange={(e) => setCompanyForm((f) => ({ ...f, code: e.target.value }))}
                placeholder="IF-001"
                disabled={Boolean(editingCompany)}
              />
            </Field>
            <Field label="Name">
              <input
                className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                value={companyForm.name}
                onChange={(e) => setCompanyForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="IronForge HQ"
              />
            </Field>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="Parent company">
              <select
                className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                value={companyForm.parent_id}
                onChange={(e) => setCompanyForm((f) => ({ ...f, parent_id: e.target.value }))}
              >
                <option value="">None</option>
                {companyList
                  .filter((company) => (company.code || company.id) !== companyForm.code)
                  .map((company) => {
                    const value = company.code || company.id;
                    return (
                      <option key={value} value={value}>
                        {company.name || company.code || value}
                      </option>
                    );
                  })}
              </select>
            </Field>
            <Field label="Country">
              <input
                className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                value={companyForm.country}
                onChange={(e) => setCompanyForm((f) => ({ ...f, country: e.target.value }))}
                placeholder="US"
              />
            </Field>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="Currency">
              <input
                className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                value={companyForm.currency}
                onChange={(e) => setCompanyForm((f) => ({ ...f, currency: e.target.value }))}
                placeholder="USD"
              />
            </Field>
            <Field label="Timezone">
              <input
                className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                value={companyForm.timezone}
                onChange={(e) => setCompanyForm((f) => ({ ...f, timezone: e.target.value }))}
                placeholder="America/New_York"
              />
            </Field>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="Type">
              <select
                className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                value={companyForm.isgroup ? "group" : "company"}
                onChange={(e) => setCompanyForm((f) => ({ ...f, isgroup: e.target.value === "group" }))}
              >
                <option value="company">Company</option>
                <option value="group">Group</option>
              </select>
            </Field>
            <Field label="Status">
              <select
                className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                value={companyForm.is_active ? "active" : "inactive"}
                onChange={(e) => setCompanyForm((f) => ({ ...f, is_active: e.target.value === "active" }))}
              >
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </Field>
          </div>
          <div className="flex items-center justify-between gap-2 pt-1">
            {editingCompany ? (
              <Button
                variant="ghost"
                className="rounded-2xl text-red-600 hover:text-red-700 dark:text-red-300"
                onClick={() =>
                  setConfirmDelete({
                    open: true,
                    type: "company",
                    payload: editingCompany,
                    label: `Delete company "${companyForm.name || companyForm.code}"?`,
                  })
                }
              >
                Delete
              </Button>
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              <Button
                variant="ghost"
                className="rounded-2xl"
                onClick={() => {
                  setCompanyModalOpen(false);
                  setEditingCompany(null);
                }}
              >
                Cancel
              </Button>
              <Button className="rounded-2xl" onClick={saveCompany} disabled={savingCompany}>
                {savingCompany ? "Saving..." : "Save"}
              </Button>
            </div>
          </div>
        </div>
      </Modal>

      <Modal
        open={permissionSetModalOpen}
        onClose={() => {
          setPermissionSetModalOpen(false);
          setEditingPermissionSet(null);
          setPermissionSetForm({ name: "", display_name: "", description: "", permissionsText: "" });
          setPermissionSetPermissionsOpen(false);
        }}
        title={editingPermissionSet ? `Edit permission set: ${editingPermissionSet}` : "Add permission set"}
        maxWidth="640px"
      >
        <div className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="Name">
              <input
                className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                value={permissionSetForm.name}
                onChange={(e) => setPermissionSetForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="sales_ops"
                disabled={Boolean(editingPermissionSet)}
              />
            </Field>
            <Field label="Display Name">
              <input
                className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
                value={permissionSetForm.display_name}
                onChange={(e) => setPermissionSetForm((f) => ({ ...f, display_name: e.target.value }))}
                placeholder="Sales Ops"
              />
            </Field>
          </div>
          <Field label="Description">
            <input
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={permissionSetForm.description}
              onChange={(e) => setPermissionSetForm((f) => ({ ...f, description: e.target.value }))}
              placeholder="What this permission set grants"
            />
          </Field>
          <Field label="Permissions">
            <div className="rounded-2xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 p-4 shadow-soft">
              <button
                type="button"
                className="flex w-full items-center justify-between gap-3 text-left"
                onClick={() => setPermissionSetPermissionsOpen((open) => !open)}
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
                <div className="mt-3 space-y-3">
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
                    <div className="text-sm text-black/60 dark:text-white/65">Loading permissions...</div>
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
            </div>
          </Field>
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
              <Button
                variant="ghost"
                className="rounded-2xl"
                onClick={() => {
                  setPermissionSetModalOpen(false);
                  setEditingPermissionSet(null);
                  setPermissionSetForm({ name: "", display_name: "", description: "", permissionsText: "" });
                }}
              >
                Cancel
              </Button>
              <Button className="rounded-2xl" onClick={savePermissionSet} disabled={savingPermissionSet}>
                {savingPermissionSet ? "Saving..." : "Save"}
              </Button>
            </div>
          </div>
        </div>
      </Modal>

      <Modal
        open={permissionModal.open}
        onClose={() => setPermissionModal({ open: false, mode: "add", value: "", original: "" })}
        title={permissionModal.mode === "edit" ? "Edit permission" : "Add permission"}
        maxWidth="520px"
      >
        <div className="space-y-3">
          <Field label="Permission">
            <input
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={permissionModal.value}
              onChange={(e) => setPermissionModal((m) => ({ ...m, value: e.target.value }))}
              placeholder="module:resource:action"
            />
          </Field>
          <div className="flex items-center justify-between gap-2">
            {permissionModal.mode === "edit" ? (
              <Button
                variant="ghost"
                className="rounded-2xl text-red-600 hover:text-red-700 dark:text-red-300"
                onClick={() =>
                  setConfirmDelete({
                    open: true,
                    type: "permission",
                    payload: permissionModal.original || permissionModal.value,
                    label: `Delete permission "${permissionModal.original || permissionModal.value}"?`,
                  })
                }
                disabled={savingPermission}
              >
                Delete
              </Button>
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              <Button
                variant="ghost"
                className="rounded-2xl"
                onClick={() => setPermissionModal({ open: false, mode: "add", value: "", original: "" })}
                disabled={savingPermission}
              >
                Cancel
              </Button>
              <Button className="rounded-2xl" onClick={savePermissionModal} disabled={savingPermission}>
                {savingPermission ? "Saving..." : "Save"}
              </Button>
            </div>
          </div>
        </div>
      </Modal>

      <ConfirmModal
        open={confirmDelete.open}
        message={confirmDelete.label}
        onClose={() => setConfirmDelete({ open: false, type: "", payload: null, label: "" })}
        onConfirm={handleConfirmDelete}
      />
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block space-y-1">
      <div className="text-xs font-semibold text-black/60 dark:text-white/65">{label}</div>
      {children}
    </label>
  );
}

function Modal({ open, onClose, title, children, maxWidth = "520px" }) {
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

function ConfirmModal({ open, onClose, onConfirm, message }) {
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

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { adminApi } from "../api";
import { useAuth, canAccessAdmin } from "../state/auth";
import { buildCompanyTreeOptions, parsePermissionParts } from "../lib/utils";
import * as UsersTabModule from "./admin/UsersTab";
import * as CompaniesTabModule from "./admin/CompaniesTab";
import * as ProfilesTabModule from "./admin/ProfilesTab";
import * as PermissionSetsTabModule from "./admin/PermissionSetsTab";
import * as PermissionsTabModule from "./admin/PermissionsTab";
import * as ServicesTabModule from "./admin/ServicesTab";

const PAGE_SIZE = 20;

export function AdminPage() {
  const { user } = useAuth();

  const [tab, setTab] = useState("users");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const [profileSearch, setProfileSearch] = useState("");
  const [companySearch, setCompanySearch] = useState("");
  const [permissionSetSearch, setPermissionSetSearch] = useState("");
  const [permissionSearch, setPermissionSearch] = useState("");
  const [userCompanyFilter, setUserCompanyFilter] = useState("");
  const [userProfileFilter, setUserProfileFilter] = useState("");
  const [permissionModuleFilter, setPermissionModuleFilter] = useState("");
  const [permissionServiceFilter, setPermissionServiceFilter] = useState("");
  const [permissionActionFilter, setPermissionActionFilter] = useState("");

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
    queryFn: adminApi.getCompanyHierarchy,
    staleTime: 5 * 60 * 1000,
  });

  const permissionSetsQuery = useQuery({
    queryKey: ["admin", "permission-sets"],
    queryFn: adminApi.getPermissionSets,
  });

  const queryClient = useQueryClient();

  const defaultVisibility = {
    chat: true,
    video_critique: true,
    mockup_setup: true,
    mockup_generate: true,
    proposals: true,
    asset_management: true,
  };

  const serviceVisibilityQuery = useQuery({
    queryKey: ["service-visibility"],
    queryFn: adminApi.getServiceVisibility,
    // Provide placeholder data during initial load to prevent UI flash
    placeholderData: defaultVisibility,
    // Keep previous data during refetch to prevent flicker
    keepPreviousData: true,
  });

  // Backend returns visibility dict directly (not wrapped)
  // Using isPlaceholderData to distinguish initial load from actual data
  const serviceVisibility = serviceVisibilityQuery.data || defaultVisibility;
  const isInitializing = serviceVisibilityQuery.isLoading && !serviceVisibilityQuery.isFetched;

  // Check if running in dev mode (all services forced visible)
  const isDevMode = serviceVisibility._dev_mode === true;

  const updateVisibilityMutation = useMutation({
    mutationFn: adminApi.updateServiceVisibility,
    // Optimistic update for immediate UI response
    onMutate: async (newVisibility) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: ["service-visibility"] });
      // Snapshot previous value
      const previousVisibility = queryClient.getQueryData(["service-visibility"]);
      // Optimistically update
      queryClient.setQueryData(["service-visibility"], newVisibility);
      return { previousVisibility };
    },
    onError: (_err, _newVisibility, context) => {
      // Rollback on error
      queryClient.setQueryData(["service-visibility"], context?.previousVisibility);
    },
    onSettled: () => {
      // Refetch to ensure sync with server
      queryClient.invalidateQueries({ queryKey: ["service-visibility"] });
    },
  });

  const handleToggleService = useCallback((key, currentValue) => {
    const newVisibility = { ...serviceVisibility, [key]: !currentValue };
    updateVisibilityMutation.mutate(newVisibility);
  }, [serviceVisibility, updateVisibilityMutation]);

  const companyCodeById = useMemo(() => {
    const raw = companiesQuery.data?.hierarchy;
    if (!Array.isArray(raw)) return new Map();
    const map = new Map();
    raw.forEach((company) => {
      if (company.id != null && company.code) {
        map.set(company.id, company.code);
      }
    });
    return map;
  }, [companiesQuery.data]);

  const users = useMemo(() => {
    const list = usersQuery.data?.users || [];
    const needle = q.trim().toLowerCase();
    return list.filter((u) => {
      const profileName = u.profiles?.display_name || u.profiles?.name || "";
      const s = `${u.email || ""} ${u.name || ""} ${profileName}`.toLowerCase();
      if (needle && !s.includes(needle)) return false;
      const companyValue =
        companyCodeById.get(u.primary_company_id) || "";
      if (userCompanyFilter && companyValue !== userCompanyFilter) return false;
      if (userProfileFilter) {
        const profileValues = u.profiles?.name ? [u.profiles.name] : [];
        if (!profileValues.includes(userProfileFilter)) return false;
      }
      return true;
    });
  }, [usersQuery.data, q, userCompanyFilter, userProfileFilter, companyCodeById]);

  const hasNext = useMemo(() => {
    const list = usersQuery.data?.users || [];
    return list.length === PAGE_SIZE;
  }, [usersQuery.data]);

  useEffect(() => {
    setPermissionServiceFilter("");
    setPermissionActionFilter("");
  }, [permissionModuleFilter]);

  useEffect(() => {
    setPermissionActionFilter("");
  }, [permissionServiceFilter]);
  const profileOptions = useMemo(() => {
    return Array.isArray(profilesQuery.data) ? profilesQuery.data : [];
  }, [profilesQuery.data]);
  const permissionTree = useMemo(() => {
    const raw = Array.isArray(permissionsQuery.data) ? permissionsQuery.data : [];
    const moduleMap = new Map();
    const descriptions = {};

    const addPermission = (module, service, action) => {
      if (!module || !service || !action) return;
      if (!moduleMap.has(module)) moduleMap.set(module, new Map());
      const serviceMap = moduleMap.get(module);
      if (!serviceMap.has(service)) serviceMap.set(service, new Set());
      serviceMap.get(service).add(action);
    };

    if (Array.isArray(raw)) {
      raw.forEach((perm) => {
        const name = typeof perm === "string" ? perm : perm?.name;
        const desc = typeof perm === "string" ? "" : perm?.description || "";
        if (name && desc) descriptions[name] = desc;
        if (!name) return;
        const parts = name.split(":");
        if (parts.length >= 3) {
          addPermission(parts[0], parts[1], parts[2]);
        }
      });
    } else if (raw && typeof raw === "object") {
      Object.entries(raw).forEach(([module, services]) => {
        if (!services || typeof services !== "object") return;
        Object.entries(services).forEach(([service, actions]) => {
          if (!Array.isArray(actions)) return;
          actions.forEach((action) => addPermission(module, service, action));
        });
      });
    }

    const modules = Array.from(moduleMap.keys()).sort();
    const servicesByModule = {};
    const actionsByService = {};
    const flat = [];
    const allServices = new Set();
    const allActions = new Set();

    modules.forEach((module) => {
      const services = Array.from(moduleMap.get(module).keys()).sort();
      servicesByModule[module] = services;
      services.forEach((service) => {
        allServices.add(service);
        const actions = Array.from(moduleMap.get(module).get(service)).sort();
        actionsByService[`${module}:${service}`] = actions;
        actions.forEach((action) => {
          allActions.add(action);
          flat.push(`${module}:${service}:${action}`);
        });
      });
    });

    return {
      modules,
      servicesByModule,
      actionsByService,
      flat,
      allServices: Array.from(allServices).sort(),
      allActions: Array.from(allActions).sort(),
      descriptions,
    };
  }, [permissionsQuery.data]);

  const permissionList = useMemo(() => permissionTree.flat, [permissionTree]);
  const permissionDescriptions = permissionTree.descriptions || {};
  const [localPermissionDescriptions, setLocalPermissionDescriptions] = useState({});
  const mergedPermissionDescriptions = useMemo(
    () => ({ ...(permissionDescriptions || {}), ...localPermissionDescriptions }),
    [permissionDescriptions, localPermissionDescriptions]
  );
  const updateLocalPermissionDescription = useCallback((name, desc) => {
    if (!name) return;
    const trimmed = desc?.trim() || "";
    setLocalPermissionDescriptions((prev) => {
      const next = { ...prev };
      if (trimmed) {
        next[name] = trimmed;
      } else {
        delete next[name];
      }
      return next;
    });
  }, []);
  const permissionModuleOptions = permissionTree.modules;
  const permissionFilterServiceOptions = permissionModuleFilter
    ? permissionTree.servicesByModule[permissionModuleFilter] || []
    : permissionTree.allServices;
  const permissionFilterActionOptions =
    permissionModuleFilter && permissionServiceFilter
      ? permissionTree.actionsByService[`${permissionModuleFilter}:${permissionServiceFilter}`] || []
      : permissionTree.allActions;
  const companyList = useMemo(() => {
    const raw = companiesQuery.data?.hierarchy;
    return Array.isArray(raw) ? raw : [];
  }, [companiesQuery.data]);
  const permissionSetList = useMemo(() => {
    return Array.isArray(permissionSetsQuery.data) ? permissionSetsQuery.data : [];
  }, [permissionSetsQuery.data]);
  const filteredCompanyList = useMemo(() => {
    const needle = companySearch.trim().toLowerCase();
    if (!needle) return companyList;
    return companyList.filter((company) => {
      const s = `${company.name || ""} ${company.code || ""} ${company.country || ""} ${company.currency || ""} ${
        company.timezone || ""
      }`.toLowerCase();
      return s.includes(needle);
    });
  }, [companyList, companySearch]);
  const filteredProfileOptions = useMemo(() => {
    const needle = profileSearch.trim().toLowerCase();
    if (!needle) return profileOptions;
    return profileOptions.filter((profile) => {
      const s = `${profile.display_name || ""} ${profile.name || ""} ${profile.description || ""}`.toLowerCase();
      return s.includes(needle);
    });
  }, [profileOptions, profileSearch]);
  const filteredPermissionSetList = useMemo(() => {
    const needle = permissionSetSearch.trim().toLowerCase();
    if (!needle) return permissionSetList;
    return permissionSetList.filter((set) => {
      const s = `${set.display_name || ""} ${set.name || ""} ${set.description || ""}`.toLowerCase();
      return s.includes(needle);
    });
  }, [permissionSetList, permissionSetSearch]);
  const filteredPermissionList = useMemo(() => {
    const needle = permissionSearch.trim().toLowerCase();
    let list = permissionList;
    if (permissionModuleFilter || permissionServiceFilter || permissionActionFilter) {
      list = list.filter((perm) => {
        const parts = parsePermissionParts(perm);
        if (permissionModuleFilter && parts.module !== permissionModuleFilter) return false;
        if (permissionServiceFilter && parts.service !== permissionServiceFilter) return false;
        if (permissionActionFilter && parts.action !== permissionActionFilter) return false;
        return true;
      });
    }
    if (!needle) return list;
    return list.filter((perm) => {
      const desc = mergedPermissionDescriptions[perm] || "";
      return `${perm} ${desc}`.toLowerCase().includes(needle);
    });
  }, [
    permissionList,
    permissionSearch,
    mergedPermissionDescriptions,
    permissionModuleFilter,
    permissionServiceFilter,
    permissionActionFilter,
  ]);

  const companyTreeOptions = useMemo(() => buildCompanyTreeOptions(companyList), [companyList]);

  const profileFilterOptions = useMemo(() => {
    return profileOptions
      .map((profile) => ({
        value: profile.name || profile.display_name || "",
        label: profile.display_name || profile.name || "—",
      }))
      .filter((opt) => opt.value);
  }, [profileOptions]);
  const permissionSetValues = useMemo(
    () =>
      permissionSetList
        .map((set) => set.name || set.id)
        .filter(Boolean),
    [permissionSetList]
  );
  const profileValues = useMemo(
    () => profileOptions.map((profile) => profile.name || profile.id).filter(Boolean),
    [profileOptions]
  );

  const companyLookup = useMemo(() => {
    const map = new Map();
    companyList.forEach((company) => {
      const name = company.name || company.code || company.id;
      if (company.code) map.set(company.code, name);
      if (company.id != null) map.set(company.id, name);
    });
    return map;
  }, [companyList]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex items-center gap-2 overflow-x-auto py-1">
        <Button
          variant={tab === "users" ? "default" : "ghost"}
          onClick={() => setTab("users")}
          className={`rounded-2xl shrink-0 mmg-tab-btn ${tab === "users" ? "mmg-tab-btn-active" : ""}`}
        >
          Users
        </Button>
        <Button
          variant={tab === "companies" ? "default" : "ghost"}
          onClick={() => setTab("companies")}
          className={`rounded-2xl shrink-0 mmg-tab-btn ${tab === "companies" ? "mmg-tab-btn-active" : ""}`}
        >
          Companies
        </Button>
        <Button
          variant={tab === "profiles" ? "default" : "ghost"}
          onClick={() => setTab("profiles")}
          className={`rounded-2xl shrink-0 mmg-tab-btn ${tab === "profiles" ? "mmg-tab-btn-active" : ""}`}
        >
          Profiles
        </Button>
        <Button
          variant={tab === "permission-sets" ? "default" : "ghost"}
          onClick={() => setTab("permission-sets")}
          className={`rounded-2xl shrink-0 mmg-tab-btn ${tab === "permission-sets" ? "mmg-tab-btn-active" : ""}`}
        >
          Permission Sets
        </Button>
        <Button
          variant={tab === "permissions" ? "default" : "ghost"}
          onClick={() => setTab("permissions")}
          className={`rounded-2xl shrink-0 mmg-tab-btn ${tab === "permissions" ? "mmg-tab-btn-active" : ""}`}
        >
          Permissions
        </Button>
        <Button
          variant={tab === "services" ? "default" : "ghost"}
          onClick={() => setTab("services")}
          className={`rounded-2xl shrink-0 mmg-tab-btn ${tab === "services" ? "mmg-tab-btn-active" : ""}`}
        >
          Services
        </Button>
      </div>
      <div className="flex-1 min-h-0">
        <div className={tab === "users" ? "h-full" : "hidden"} aria-hidden={tab !== "users"}>
          <UsersTabModule.UsersPanel
            q={q}
            setQ={setQ}
            usersQuery={usersQuery}
            users={users}
            user={user}
            companyLookup={companyLookup}
            companyCodeById={companyCodeById}
            userCompanyFilter={userCompanyFilter}
            setUserCompanyFilter={setUserCompanyFilter}
            userProfileFilter={userProfileFilter}
            setUserProfileFilter={setUserProfileFilter}
            companyTreeOptions={companyTreeOptions}
            profileFilterOptions={profileFilterOptions}
            profileOptions={profileOptions}
            profileValues={profileValues}
            permissionSetList={permissionSetList}
            permissionSetValues={permissionSetValues}
            permissionList={permissionList}
            permissionsQuery={permissionsQuery}
            page={page}
          />
        </div>

        <div className={tab === "companies" ? "h-full" : "hidden"} aria-hidden={tab !== "companies"}>
          <CompaniesTabModule.CompaniesPanel
            companySearch={companySearch}
            setCompanySearch={setCompanySearch}
            companiesQuery={companiesQuery}
            filteredCompanyList={filteredCompanyList}
            companyLookup={companyLookup}
            companyList={companyList}
          />
        </div>

        <div className={tab === "profiles" ? "h-full" : "hidden"} aria-hidden={tab !== "profiles"}>
          <ProfilesTabModule.ProfilesPanel
            profileSearch={profileSearch}
            setProfileSearch={setProfileSearch}
            filteredProfileOptions={filteredProfileOptions}
            permissionList={permissionList}
            permissionSetValues={permissionSetValues}
            permissionSetList={permissionSetList}
            permissionSetsQuery={permissionSetsQuery}
            permissionsQuery={permissionsQuery}
          />
        </div>

        <div className={tab === "permission-sets" ? "h-full" : "hidden"} aria-hidden={tab !== "permission-sets"}>
          <PermissionSetsTabModule.PermissionSetsPanel
            permissionSetSearch={permissionSetSearch}
            setPermissionSetSearch={setPermissionSetSearch}
            permissionSetsQuery={permissionSetsQuery}
            filteredPermissionSetList={filteredPermissionSetList}
            permissionList={permissionList}
            permissionsQuery={permissionsQuery}
          />
        </div>

        <div className={tab === "permissions" ? "h-full" : "hidden"} aria-hidden={tab !== "permissions"}>
          <PermissionsTabModule.PermissionsPanel
            permissionSearch={permissionSearch}
            setPermissionSearch={setPermissionSearch}
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
            permissionTree={permissionTree}
            updateLocalPermissionDescription={updateLocalPermissionDescription}
          />
        </div>

        <div className={tab === "services" ? "h-full min-h-0" : "hidden"} aria-hidden={tab !== "services"}>
          <ServicesTabModule.ServicesTab
            isInitializing={isInitializing}
            isDevMode={isDevMode}
            serviceVisibility={serviceVisibility}
            isUpdating={updateVisibilityMutation.isPending}
            onToggleService={handleToggleService}
          />
        </div>
      </div>
    </div>
  );
}

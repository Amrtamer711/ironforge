import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { adminApi } from "../../api";
import { useAuth, canAccessAdmin } from "../../state/auth";
import { parsePermissionParts } from "../../lib/utils";
import * as UsersTabModule from "./admin/UsersTab";
import * as CompaniesTabModule from "./admin/CompaniesTab";
import * as ProfilesTabModule from "./admin/ProfilesTab";
import * as PermissionSetsTabModule from "./admin/PermissionSetsTab";
import * as PermissionsTabModule from "./admin/PermissionsTab";

// Service toggle definitions
const SERVICE_TOGGLES = [
  { key: "chat", label: "AI Chat", description: "Chat assistant for general queries" },
  { key: "video_critique", label: "Video Critique", description: "AI-powered video analysis tool" },
  { key: "proposals", label: "Proposals", description: "Proposal generation and management" },
  { key: "asset_management", label: "Asset Management", description: "Digital asset management system" },
];

const MOCKUP_TOGGLES = [
  { key: "mockup_setup", label: "Mockup Setup", description: "Configure and upload mockup templates" },
  { key: "mockup_generate", label: "Mockup Generate", description: "Generate mockups from templates" },
];

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
    queryFn: adminApi.getCompanies,
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

  const users = useMemo(() => {
    const list = usersQuery.data?.users || usersQuery.data || [];
    const needle = q.trim().toLowerCase();
    return list.filter((u) => {
      const profileName = Array.isArray(u.profiles)
        ? u.profiles.map((p) => p?.display_name || p?.name || p).filter(Boolean).join(" ")
        : u.profiles?.display_name || u.profiles?.name || u.profile || u.profile_name || "";
      const s = `${u.email || ""} ${u.name || ""} ${profileName}`.toLowerCase();
      if (needle && !s.includes(needle)) return false;
      const companyValue = u.company?.code || u.company_code || u.company_id || "";
      if (userCompanyFilter && companyValue !== userCompanyFilter) return false;
      if (userProfileFilter) {
        const profileValues = Array.isArray(u.profiles)
          ? u.profiles.map((p) => p?.name || p?.display_name || p).filter(Boolean)
          : [u.profiles?.name || u.profiles?.display_name || u.profile || u.profile_name].filter(Boolean);
        if (!profileValues.includes(userProfileFilter)) return false;
      }
      return true;
    });
  }, [usersQuery.data, q, userCompanyFilter, userProfileFilter]);

  const hasNext = useMemo(() => {
    const list = usersQuery.data?.users || usersQuery.data || [];
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
    const raw = profilesQuery.data?.profiles ?? profilesQuery.data;
    return Array.isArray(raw) ? raw : [];
  }, [profilesQuery.data]);
  const permissionTree = useMemo(() => {
    const raw = permissionsQuery.data?.permissions ?? permissionsQuery.data;
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

  const companyFilterOptions = useMemo(() => {
    return companyList
      .map((company) => ({
        value: company.code || company.id || "",
        label: company.name || company.code || company.id || "—",
      }))
      .filter((opt) => opt.value);
  }, [companyList]);

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
      const key = company.code || company.id;
      if (key) map.set(key, company.name || company.code || key);
    });
    return map;
  }, [companyList]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex items-center gap-2 overflow-x-auto">
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
        <Button variant={tab === "services" ? "default" : "ghost"} onClick={() => setTab("services")} className="rounded-2xl shrink-0">
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
            userCompanyFilter={userCompanyFilter}
            setUserCompanyFilter={setUserCompanyFilter}
            userProfileFilter={userProfileFilter}
            setUserProfileFilter={setUserProfileFilter}
            companyFilterOptions={companyFilterOptions}
            profileFilterOptions={profileFilterOptions}
            companyList={companyList}
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

        <div className={tab === "services" ? "h-full overflow-y-auto" : "hidden"} aria-hidden={tab !== "services"}>
          <Card className="h-full">
            <CardHeader className="pb-2">
              <CardTitle className="text-lg">Service Visibility</CardTitle>
              <p className="text-sm text-black/60 dark:text-white/65">
                Toggle which services are visible to users in the sidebar. Admin and Settings are always visible.
              </p>
            </CardHeader>
            <CardContent className="space-y-6">
              {isInitializing ? (
                <div className="space-y-6 animate-pulse">
                  {/* Skeleton for General Services */}
                  <div className="space-y-3">
                    <div className="h-4 w-28 bg-black/10 dark:bg-white/10 rounded" />
                    <div className="grid gap-3">
                      {[1, 2, 3, 4].map((i) => (
                        <div key={i} className="flex items-center justify-between rounded-xl bg-black/[0.02] dark:bg-white/[0.03] p-3 ring-1 ring-black/5 dark:ring-white/10">
                          <div className="space-y-2">
                            <div className="h-4 w-24 bg-black/10 dark:bg-white/10 rounded" />
                            <div className="h-3 w-40 bg-black/5 dark:bg-white/5 rounded" />
                          </div>
                          <div className="h-6 w-11 bg-black/10 dark:bg-white/10 rounded-full" />
                        </div>
                      ))}
                    </div>
                  </div>
                  {/* Skeleton for Mockup Services */}
                  <div className="space-y-3">
                    <div className="h-4 w-28 bg-black/10 dark:bg-white/10 rounded" />
                    <div className="grid gap-3">
                      {[1, 2].map((i) => (
                        <div key={i} className="flex items-center justify-between rounded-xl bg-black/[0.02] dark:bg-white/[0.03] p-3 ring-1 ring-black/5 dark:ring-white/10">
                          <div className="space-y-2">
                            <div className="h-4 w-24 bg-black/10 dark:bg-white/10 rounded" />
                            <div className="h-3 w-40 bg-black/5 dark:bg-white/5 rounded" />
                          </div>
                          <div className="h-6 w-11 bg-black/10 dark:bg-white/10 rounded-full" />
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ) : (
                <>
                  {/* Dev Mode Banner */}
                  {isDevMode && (
                    <div className="rounded-xl bg-amber-500/10 border border-amber-500/30 p-3 mb-4">
                      <div className="flex items-center gap-2">
                        <span className="text-amber-600 dark:text-amber-400 font-medium text-sm">Dev Mode Active</span>
                      </div>
                      <p className="text-xs text-amber-600/80 dark:text-amber-400/80 mt-1">
                        All services are forced visible. Running with <code className="bg-amber-500/20 px-1 rounded">--dev-all-services</code> flag.
                        Toggles are disabled in this mode.
                      </p>
                    </div>
                  )}

                  {/* General Services */}
                  <div className="space-y-3">
                    <h3 className="text-sm font-medium text-black/70 dark:text-white/75">General Services</h3>
                    <div className="grid gap-3">
                      {SERVICE_TOGGLES.map((service) => (
                        <ServiceToggle
                          key={service.key}
                          label={service.label}
                          description={service.description}
                          enabled={serviceVisibility[service.key] === true}
                          onChange={() => handleToggleService(service.key, serviceVisibility[service.key])}
                          disabled={isDevMode || updateVisibilityMutation.isPending}
                        />
                      ))}
                    </div>
                  </div>

                  {/* Mockup Services */}
                  <div className="space-y-3">
                    <h3 className="text-sm font-medium text-black/70 dark:text-white/75">Mockup Services</h3>
                    <p className="text-xs text-black/50 dark:text-white/50">
                      If both are disabled, the Mockup service will be hidden entirely.
                    </p>
                    <div className="grid gap-3">
                      {MOCKUP_TOGGLES.map((service) => (
                        <ServiceToggle
                          key={service.key}
                          label={service.label}
                          description={service.description}
                          enabled={serviceVisibility[service.key] === true}
                          onChange={() => handleToggleService(service.key, serviceVisibility[service.key])}
                          disabled={isDevMode || updateVisibilityMutation.isPending}
                        />
                      ))}
                    </div>
                  </div>

                  {/* Always Visible Notice */}
                  <div className="pt-4 border-t border-black/10 dark:border-white/10">
                    <p className="text-xs text-black/50 dark:text-white/50">
                      <strong>Always visible:</strong> Admin (for admins only), Settings
                    </p>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

// Service toggle switch component
function ServiceToggle({ label, description, enabled, onChange, disabled }) {
  return (
    <div className="flex items-center justify-between rounded-xl bg-black/[0.02] dark:bg-white/[0.03] p-3 ring-1 ring-black/5 dark:ring-white/10">
      <div className="flex-1 min-w-0 mr-4">
        <div className="text-sm font-medium">{label}</div>
        <div className="text-xs text-black/50 dark:text-white/50 truncate">{description}</div>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        disabled={disabled}
        onClick={onChange}
        className={[
          "relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent",
          "transition-all duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-black/20",
          enabled ? "bg-green-500" : "bg-black/20 dark:bg-white/20",
          disabled ? "opacity-50 cursor-not-allowed" : "",
        ].join(" ")}
      >
        <span
          className={[
            "pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-lg ring-0",
            "transition-transform duration-200 ease-in-out",
            enabled ? "translate-x-5" : "translate-x-0",
          ].join(" ")}
        />
      </button>
    </div>
  );
}

import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { assetManagementApi } from "../../api";
import { useAuth, canAccessAdmin } from "../../state/auth";
import * as LocationsTabModule from "./asset-management/LocationsTab";
import * as NetworksTabModule from "./asset-management/NetworksTab";
import * as AssetTypesTabModule from "./asset-management/AssetTypesTab";
import * as NetworkAssetsTabModule from "./asset-management/NetworkAssetsTab";
import * as PackagesTabModule from "./asset-management/PackagesTab";

const TABS = [
  { key: "networks", label: "Networks", disabled: false },
  { key: "asset-types", label: "Asset Types", disabled: false },
  { key: "network-assets", label: "Network Assets", disabled: false },
  { key: "packages", label: "Packages", disabled: false },
  { key: "locations", label: "Locations", disabled: false },
];

function unwrapArray(data, keys = []) {
  if (Array.isArray(data)) return data;
  for (const key of keys) {
    if (Array.isArray(data?.[key])) return data[key];
  }
  if (Array.isArray(data?.data)) return data.data;
  return [];
}

export function AssetManagementPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState("networks");

  if (!canAccessAdmin(user)) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Restricted</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-black/60 dark:text-white/65">
          You don't have access to asset management.
        </CardContent>
      </Card>
    );
  }

  const networksQuery = useQuery({
    queryKey: ["asset-management", "networks"],
    queryFn: () => assetManagementApi.getNetworks(),
    enabled: tab === "networks",
  });

  const assetTypesQuery = useQuery({
    queryKey: ["asset-management", "asset-types"],
    queryFn: () => assetManagementApi.getAssetTypes(),
    enabled: tab === "asset-types",
  });

  const networkAssetsQuery = useQuery({
    queryKey: ["asset-management", "network-assets"],
    queryFn: () => assetManagementApi.getNetworkAssets(),
    enabled: tab === "network-assets",
  });

  const packagesQuery = useQuery({
    queryKey: ["asset-management", "packages"],
    queryFn: () => assetManagementApi.getPackages(),
    enabled: tab === "packages",
  });

  const locationsQuery = useQuery({
    queryKey: ["asset-management", "locations"],
    queryFn: () => assetManagementApi.getLocations(),
    enabled: tab === "locations",
  });

  const networks = useMemo(() => unwrapArray(networksQuery.data, ["networks"]), [networksQuery.data]);
  const assetTypes = useMemo(() => unwrapArray(assetTypesQuery.data, ["asset_types", "types"]), [assetTypesQuery.data]);
  const networkAssets = useMemo(
    () => unwrapArray(networkAssetsQuery.data, ["network_assets", "assets"]),
    [networkAssetsQuery.data]
  );
  const packages = useMemo(() => unwrapArray(packagesQuery.data, ["packages"]), [packagesQuery.data]);
  const locations = useMemo(() => unwrapArray(locationsQuery.data, ["locations"]), [locationsQuery.data]);

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col gap-4">
      <div className="flex items-center gap-2 overflow-x-auto">
        {TABS.map((tabItem) => (
          <Button
            key={tabItem.key}
            variant={tab === tabItem.key ? "default" : "ghost"}
            onClick={() => setTab(tabItem.key)}
            className="rounded-2xl shrink-0"
            disabled={tabItem.disabled}
            title={tabItem.disabled ? "Coming soon" : undefined}
          >
            {tabItem.label}
          </Button>
        ))}
      </div>

      <div className="flex-1 min-h-0 min-w-0">
        {tab === "networks" ? (
          <div className="h-full">
            <NetworksTabModule.NetworksTab networks={networks} networksQuery={networksQuery} />
          </div>
        ) : null}
        {tab === "asset-types" ? (
          <div className="h-full">
            <AssetTypesTabModule.AssetTypesTab assetTypes={assetTypes} assetTypesQuery={assetTypesQuery} />
          </div>
        ) : null}
        {tab === "network-assets" ? (
          <div className="h-full">
            <NetworkAssetsTabModule.NetworkAssetsTab
              networkAssets={networkAssets}
              networkAssetsQuery={networkAssetsQuery}
            />
          </div>
        ) : null}
        {tab === "packages" ? (
          <div className="h-full">
            <PackagesTabModule.PackagesTab packages={packages} packagesQuery={packagesQuery} />
          </div>
        ) : null}
        {tab === "locations" ? (
          <div className="h-full">
            <LocationsTabModule.LocationsTab locations={locations} locationsQuery={locationsQuery} />
          </div>
        ) : null}
      </div>
    </div>
  );
}

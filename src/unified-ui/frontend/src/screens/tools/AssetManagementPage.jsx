import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { locationsApi } from "../../api";
import { useAuth, canAccessAdmin } from "../../state/auth";
import * as LocationsTabModule from "./asset-management/LocationsTab";

const TABS = [
  { key: "locations", label: "Locations", disabled: false },
  { key: "network", label: "Network", disabled: true },
  { key: "package", label: "Package", disabled: true },
  { key: "assets", label: "Assets", disabled: true },
];

export function AssetManagementPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState("locations");

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

  const locationsQuery = useQuery({
    queryKey: ["asset-management", "locations"],
    queryFn: () => locationsApi.getLocations(),
  });

  const locations = useMemo(() => {
    const data = locationsQuery.data;
    if (Array.isArray(data)) return data;
    return data?.locations || [];
  }, [locationsQuery.data]);

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col gap-4 overflow-hidden">
      <div className="flex items-center gap-2 overflow-x-auto pb-1 px-1">
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

      <div className="flex-1 min-h-0 min-w-0 overflow-y-auto px-2 py-1 space-y-4">
        {tab === "locations" ? (
          <LocationsTabModule.LocationsTab locations={locations} locationsQuery={locationsQuery} />
        ) : null}
      </div>
    </div>
  );
}

import React from "react";
import { SimpleTableTab } from "./SimpleTableTab";

export function NetworkAssetsTab({ networkAssets, networkAssetsQuery }) {
  return (
    <SimpleTableTab
      title="Network Assets"
      items={networkAssets}
      itemsQuery={networkAssetsQuery}
      itemLabel="asset"
      searchPlaceholder="Search assets..."
      emptyMessage="No network assets found."
      preferredColumns={[
        "display_name",
        "asset_key",
        "location_key",
        "network_id",
        "type_id",
        "company",
        "is_active",
      ]}
    />
  );
}

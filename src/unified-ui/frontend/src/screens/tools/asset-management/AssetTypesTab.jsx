import React from "react";
import { SimpleTableTab } from "./SimpleTableTab";

export function AssetTypesTab({ assetTypes, assetTypesQuery }) {
  return (
    <SimpleTableTab
      title="Asset Types"
      items={assetTypes}
      itemsQuery={assetTypesQuery}
      itemLabel="type"
      searchPlaceholder="Search asset types..."
      emptyMessage="No asset types found."
      preferredColumns={["name", "type_key", "company", "network_id", "is_active", "location_count"]}
    />
  );
}

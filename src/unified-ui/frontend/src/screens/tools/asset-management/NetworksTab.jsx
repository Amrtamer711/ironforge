import React from "react";
import { SimpleTableTab } from "./SimpleTableTab";

export function NetworksTab({ networks, networksQuery }) {
  return (
    <SimpleTableTab
      title="Networks"
      items={networks}
      itemsQuery={networksQuery}
      itemLabel="network"
      searchPlaceholder="Search networks..."
      emptyMessage="No networks found."
      preferredColumns={["network_name", "name", "company", "company_schema", "is_active", "location_count"]}
    />
  );
}

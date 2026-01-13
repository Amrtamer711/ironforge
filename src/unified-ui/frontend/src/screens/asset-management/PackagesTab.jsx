import React from "react";
import { SimpleTableTab } from "./SimpleTableTab";

export function PackagesTab({ packages, packagesQuery }) {
  return (
    <SimpleTableTab
      title="Packages"
      items={packages}
      itemsQuery={packagesQuery}
      itemLabel="package"
      searchPlaceholder="Search packages..."
      emptyMessage="No packages found."
      preferredColumns={["name", "company", "is_active"]}
    />
  );
}

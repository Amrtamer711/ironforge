import React from "react";
import { SimpleTableTab } from "./SimpleTableTab";

export function CompaniesTab({ companies, companiesQuery }) {
  return (
    <SimpleTableTab
      title="Companies"
      items={companies}
      itemsQuery={companiesQuery}
      itemLabel="company"
      searchPlaceholder="Search companies..."
      emptyMessage="No companies found."
      preferredColumns={["company", "code", "name"]}
      stringKey="company"
    />
  );
}

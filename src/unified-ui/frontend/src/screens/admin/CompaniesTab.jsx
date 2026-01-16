import React, { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Pencil, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { FormField } from "../../components/ui/form-field";
import { SearchInput } from "../../components/ui/search-input";
import { SoftCard } from "../../components/ui/soft-card";
import { IconActionButton } from "../../components/ui/icon-action-button";
import { LoadingEllipsis } from "../../components/ui/loading-ellipsis";
import { ConfirmModal, Modal } from "../../components/ui/modal";
import { SelectDropdown } from "../../components/ui/select-dropdown";
import { adminApi } from "../../api";
import { buildCompanyTreeOptions } from "../../lib/utils";

export function CompaniesTab({
  companySearch,
  setCompanySearch,
  openCompanyModal,
  companiesQuery,
  filteredCompanyList,
  companyLookup,
  companyList,
  setConfirmDelete,
}) {
  const companyTree = React.useMemo(() => {
    const byCode = new Map();
    const byId = new Map();
    const childCodes = new Set();

    companyList.forEach((company) => {
      const code = company.code || String(company.id || "");
      if (code) byCode.set(code, company);
      if (company.id != null) byId.set(company.id, company);
      (company.children || []).forEach((child) => childCodes.add(child));
    });

    const getChildren = (company) => {
      if (Array.isArray(company.children) && company.children.length) {
        return company.children
          .map((code) => byCode.get(code))
          .filter(Boolean);
      }
      if (company.id == null) return [];
      return companyList.filter((child) => child.parent_id === company.id);
    };

    const roots = companyList.filter((company) => {
      if (company.parent_id == null) return true;
      if (byId.has(company.parent_id)) return false;
      if (company.code && childCodes.has(company.code)) return false;
      return true;
    });

    const buildNode = (company) => {
      const children = getChildren(company).map((child) => buildNode(child));
      return { company, children };
    };

    return roots.map((root) => buildNode(root));
  }, [companyList]);

  const rootCodes = React.useMemo(
    () => companyTree.map((node) => node.company.code || String(node.company.id || "")),
    [companyTree]
  );
  const [expandedNodes, setExpandedNodes] = useState(() => new Set());

  React.useEffect(() => {
    if (!rootCodes.length) return;
    setExpandedNodes(new Set(rootCodes.filter(Boolean)));
  }, [rootCodes]);

  const toggleNode = (key) => {
    if (!key) return;
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const renderTree = (nodes, depth = 0) =>
    nodes.map((node, index) => {
      const { company, children } = node;
      const key = company.code || company.id;
      const hasChildren = children.length > 0;
      const isExpanded = expandedNodes.has(key);
      const isGroup = company.isgroup || company.is_group || hasChildren;
      const name = company.name || company.code || "—";

      return (
        <div key={key} className="space-y-3">
          <div className="flex items-start gap-2" style={{ marginLeft: depth * 12 }}>
            <div className="mt-2 w-5 flex justify-center">
              {hasChildren ? (
                <button
                  type="button"
                  onClick={() => toggleNode(key)}
                  className="text-black/50 dark:text-white/60 hover:text-black/80 dark:hover:text-white/80"
                  aria-label={isExpanded ? "Collapse group" : "Expand group"}
                >
                  {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                </button>
              ) : (
                <span className="h-4 w-4" />
              )}
            </div>
            <SoftCard className="p-4 space-y-2 flex-1">
              <div className="flex items-start justify-between gap-2">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <div className="text-base font-semibold">{name}</div>
                    <span
                      className={
                        isGroup
                          ? "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold text-emerald-700 dark:text-emerald-200 bg-emerald-500/15 dark:bg-emerald-500/20"
                          : "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold text-sky-700 dark:text-sky-200 bg-sky-500/15 dark:bg-sky-500/20"
                      }
                    >
                      {isGroup ? "Group" : "Company"}
                    </span>
                  </div>
                  <div className="text-sm text-black/55 dark:text-white/60">{company.code || "—"}</div>
                </div>
                <div className="flex items-center gap-2">
                  <IconActionButton
                    onClick={() => openCompanyModal(company)}
                    title="Edit company"
                    aria-label="Edit company"
                  >
                    <Pencil size={16} />
                  </IconActionButton>
                  <IconActionButton
                    variant="ghost"
                    onClick={() =>
                      setConfirmDelete({
                        open: true,
                        type: "company",
                        payload: company.code || company.id,
                        label: `Delete company "${company.name || company.code}"?`,
                      })
                    }
                    title="Delete company"
                    aria-label="Delete company"
                  >
                    <Trash2 size={16} />
                  </IconActionButton>
                </div>
              </div>
              <div className="flex flex-wrap gap-2 text-sm text-black/55 dark:text-white/60">
                {company.country ? <span>{company.country}</span> : null}
                {company.currency ? <span>• {company.currency}</span> : null}
                {company.timezone ? <span>• {company.timezone}</span> : null}
              </div>
            </SoftCard>
          </div>
          {hasChildren && isExpanded ? (
            <div className="space-y-3">
              {renderTree(children, depth + 1)}
            </div>
          ) : null}
        </div>
      );
    });

  const headerContent = (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <CardTitle>Companies</CardTitle>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-end">
        <SearchInput
          value={companySearch}
          onChange={(e) => setCompanySearch(e.target.value)}
          className="w-full sm:w-[220px]"
        />
        <Button
          variant="secondary"
          className="rounded-2xl self-start sm:self-auto"
          onClick={() => openCompanyModal(null)}
        >
          Add company
        </Button>
      </div>
    </div>
  );

  return (
    <Card className="h-full min-h-0 flex flex-col">
      <CardHeader className="hidden md:block space-y-2">
        {headerContent}
      </CardHeader>
      <CardContent className="flex-1 min-h-0 overflow-y-auto p-0">
        <div className="space-y-2 p-5 pb-3 md:hidden">
          {headerContent}
        </div>
        <div className="space-y-4 p-5 pt-1">
          {companiesQuery.isLoading ? (
            <LoadingEllipsis text="Loading" className="text-sm text-black/60 dark:text-white/65" />
          ) : (
            <div className="space-y-3">
              {companySearch.trim()
                ? filteredCompanyList.map((company) => {
                    const name = company.name || company.code || "—";
                    const isGroup = company.isgroup || company.is_group;
                    return (
                    <SoftCard key={company.code || company.id} className="p-4 space-y-2">
                      <div className="flex items-start justify-between gap-2">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <div className="text-base font-semibold">{name}</div>
                            <span
                              className={
                                isGroup
                                  ? "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold text-emerald-700 dark:text-emerald-200 bg-emerald-500/15 dark:bg-emerald-500/20"
                                  : "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold text-sky-700 dark:text-sky-200 bg-sky-500/15 dark:bg-sky-500/20"
                              }
                            >
                              {isGroup ? "Group" : "Company"}
                            </span>
                          </div>
                          <div className="text-sm text-black/55 dark:text-white/60">{company.code || "—"}</div>
                        </div>
                        <div className="flex items-center gap-2">
                          <IconActionButton
                            onClick={() => openCompanyModal(company)}
                            title="Edit company"
                            aria-label="Edit company"
                          >
                            <Pencil size={16} />
                          </IconActionButton>
                          <IconActionButton
                            variant="ghost"
                            onClick={() =>
                              setConfirmDelete({
                                open: true,
                                type: "company",
                                payload: company.code || company.id,
                                label: `Delete company "${company.name || company.code}"?`,
                              })
                            }
                            title="Delete company"
                            aria-label="Delete company"
                          >
                            <Trash2 size={16} />
                          </IconActionButton>
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2 text-sm text-black/55 dark:text-white/60">
                        {company.country ? <span>{company.country}</span> : null}
                        {company.currency ? <span>• {company.currency}</span> : null}
                        {company.timezone ? <span>• {company.timezone}</span> : null}
                      </div>
                    </SoftCard>
                    );
                  })
                : renderTree(companyTree)}
              {companySearch.trim() ? null : !companyTree.length ? (
                <div className="text-sm text-black/60 dark:text-white/65">
                  No companies available.
                </div>
              ) : null}
              {companySearch.trim() && !filteredCompanyList.length ? (
                <div className="text-sm text-black/60 dark:text-white/65">No matching companies.</div>
              ) : null}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function CompaniesPanel({
  companySearch,
  setCompanySearch,
  companiesQuery,
  filteredCompanyList,
  companyLookup,
  companyList,
}) {
  const {
    companyForm,
    setCompanyForm,
    editingCompany,
    setEditingCompany,
    companyModalOpen,
    setCompanyModalOpen,
    savingCompany,
    openCompanyModal,
    saveCompany,
    deleteCompany,
  } = useCompanyActions();
  const [confirmDelete, setConfirmDelete] = useState({ open: false, type: "", payload: null, label: "" });

  async function handleConfirmDelete() {
    if (!confirmDelete.open || !confirmDelete.payload) return;
    try {
      await deleteCompany(confirmDelete.payload);
    } finally {
      setConfirmDelete({ open: false, type: "", payload: null, label: "" });
    }
  }

  return (
    <>
      <CompaniesTab
        companySearch={companySearch}
        setCompanySearch={setCompanySearch}
        openCompanyModal={openCompanyModal}
        companiesQuery={companiesQuery}
        filteredCompanyList={filteredCompanyList}
        companyLookup={companyLookup}
        companyList={companyList}
        setConfirmDelete={setConfirmDelete}
      />

      <CompaniesModal
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
        editingCompany={editingCompany}
        companyForm={companyForm}
        setCompanyForm={setCompanyForm}
        companyList={companyList}
        setConfirmDelete={setConfirmDelete}
        saveCompany={saveCompany}
        savingCompany={savingCompany}
      />

      <ConfirmModal
        open={confirmDelete.open}
        message={confirmDelete.label}
        onClose={() => setConfirmDelete({ open: false, type: "", payload: null, label: "" })}
        onConfirm={handleConfirmDelete}
      />
    </>
  );
}

function useCompanyActions() {
  const qc = useQueryClient();
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
        isgroup: Boolean(company.isgroup ?? company.is_group),
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

  return {
    companyForm,
    setCompanyForm,
    editingCompany,
    setEditingCompany,
    companyModalOpen,
    setCompanyModalOpen,
    savingCompany,
    openCompanyModal,
    saveCompany,
    deleteCompany,
  };
}

export function CompaniesModal({
  open,
  onClose,
  editingCompany,
  companyForm,
  setCompanyForm,
  companyList,
  setConfirmDelete,
  saveCompany,
  savingCompany,
}) {
  const parentCompanyTreeOptions = React.useMemo(() => {
    const treeOptions = buildCompanyTreeOptions(companyList, {
      excludeValues: [companyForm.code, editingCompany],
    });
    return [{ value: "", label: "None" }, ...treeOptions];
  }, [companyList, companyForm.code, editingCompany]);
  const typeOptions = [
    { value: "company", label: "Company" },
    { value: "group", label: "Group" },
  ];
  const statusOptions = [
    { value: "active", label: "Active" },
    { value: "inactive", label: "Inactive" },
  ];

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editingCompany ? `Edit company: ${companyForm.name || companyForm.code}` : "Add company"}
      maxWidth="640px"
    >
      <div className="space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <FormField label="Code">
            <input
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={companyForm.code}
              onChange={(e) => setCompanyForm((f) => ({ ...f, code: e.target.value }))}
              placeholder="MMG-001"
              disabled={Boolean(editingCompany)}
            />
          </FormField>
          <FormField label="Name">
            <input
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={companyForm.name}
              onChange={(e) => setCompanyForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="MMG Global"
            />
          </FormField>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <FormField label="Parent company">
            <SelectDropdown
              value={companyForm.parent_id || ""}
              treeOptions={parentCompanyTreeOptions}
              onChange={(nextValue) => setCompanyForm((f) => ({ ...f, parent_id: nextValue }))}
            />
          </FormField>
          <FormField label="Country">
            <input
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={companyForm.country}
              onChange={(e) => setCompanyForm((f) => ({ ...f, country: e.target.value }))}
              placeholder="US"
            />
          </FormField>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <FormField label="Currency">
            <input
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={companyForm.currency}
              onChange={(e) => setCompanyForm((f) => ({ ...f, currency: e.target.value }))}
              placeholder="USD"
            />
          </FormField>
          <FormField label="Timezone">
            <input
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={companyForm.timezone}
              onChange={(e) => setCompanyForm((f) => ({ ...f, timezone: e.target.value }))}
              placeholder="America/New_York"
            />
          </FormField>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <FormField label="Type">
            <SelectDropdown
              value={companyForm.isgroup ? "group" : "company"}
              options={typeOptions}
              onChange={(nextValue) => setCompanyForm((f) => ({ ...f, isgroup: nextValue === "group" }))}
            />
          </FormField>
          <FormField label="Status">
            <SelectDropdown
              value={companyForm.is_active ? "active" : "inactive"}
              options={statusOptions}
              onChange={(nextValue) => setCompanyForm((f) => ({ ...f, is_active: nextValue === "active" }))}
            />
          </FormField>
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
            <Button variant="ghost" className="rounded-2xl" onClick={onClose}>
              Cancel
            </Button>
            <Button className="rounded-2xl" onClick={saveCompany} disabled={savingCompany}>
              {savingCompany ? <LoadingEllipsis text="Saving" /> : "Save"}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

import React, { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { Button } from "../../../components/ui/button";
import { FormField } from "../../../components/ui/form-field";
import { SearchInput } from "../../../components/ui/search-input";
import { SoftCard } from "../../../components/ui/soft-card";
import { IconActionButton } from "../../../components/ui/icon-action-button";
import { LoadingEllipsis } from "../../../components/ui/loading-ellipsis";
import { ConfirmModal, Modal } from "../../../components/ui/modal";
import { adminApi } from "../../../api";

export function CompaniesTab({
  companySearch,
  setCompanySearch,
  openCompanyModal,
  companiesQuery,
  filteredCompanyList,
  companyLookup,
  setConfirmDelete,
}) {
  return (
    <Card>
      <CardHeader className="space-y-2">
        <div className="grid grid-cols-[auto_1fr_auto] items-center gap-2">
          <CardTitle>Companies</CardTitle>
          <SearchInput
            value={companySearch}
            onChange={(e) => setCompanySearch(e.target.value)}
            className="w-full sm:w-[220px] sm:justify-self-end"
          />
          <Button variant="secondary" className="rounded-2xl" onClick={() => openCompanyModal(null)}>
            Add company
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {companiesQuery.isLoading ? (
          <LoadingEllipsis text="Loading" className="text-sm text-black/60 dark:text-white/65" />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {filteredCompanyList.map((company) => (
              <SoftCard key={company.code || company.id} className="p-4 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-base font-semibold">{company.name || company.code}</div>
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
                <div className="flex flex-wrap gap-2 text-sm text-black/55 dark:text-white/60">
                  <span>Parent: {companyLookup.get(company.parent_id) || "—"}</span>
                  <span>• {company.isgroup ? "Group" : "Company"}</span>
                  <span>• {company.is_active === false ? "Inactive" : "Active"}</span>
                </div>
              </SoftCard>
            ))}
            {!filteredCompanyList.length ? (
              <div className="text-sm text-black/60 dark:text-white/65">
                {companySearch.trim() ? "No matching companies." : "No companies available."}
              </div>
            ) : null}
          </div>
        )}
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
        isgroup: Boolean(company.isgroup),
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
              placeholder="IF-001"
              disabled={Boolean(editingCompany)}
            />
          </FormField>
          <FormField label="Name">
            <input
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={companyForm.name}
              onChange={(e) => setCompanyForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="IronForge HQ"
            />
          </FormField>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <FormField label="Parent company">
            <select
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={companyForm.parent_id}
              onChange={(e) => setCompanyForm((f) => ({ ...f, parent_id: e.target.value }))}
            >
              <option value="">None</option>
              {companyList
                .filter((company) => (company.code || company.id) !== companyForm.code)
                .map((company, idx) => {
                  const value = company.code || company.id;
                  return (
                    <option key={`${value || "company"}-${idx}`} value={value || ""}>
                      {company.name || company.code || value}
                    </option>
                  );
                })}
            </select>
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
            <select
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={companyForm.isgroup ? "group" : "company"}
              onChange={(e) => setCompanyForm((f) => ({ ...f, isgroup: e.target.value === "group" }))}
            >
              <option value="company">Company</option>
              <option value="group">Group</option>
            </select>
          </FormField>
          <FormField label="Status">
            <select
              className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-sm outline-none"
              value={companyForm.is_active ? "active" : "inactive"}
              onChange={(e) => setCompanyForm((f) => ({ ...f, is_active: e.target.value === "active" }))}
            >
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
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
              {savingCompany ? "Saving..." : "Save"}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

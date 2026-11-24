"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { downloadAdminCsv } from "@/lib/admin/client";
import { type AdminFilters, writeFilters } from "@/lib/admin/query";

export type FilterField = {
  key: string;
  label: string;
  type?: "text" | "date" | "number";
  options?: readonly { value: string; label: string }[];
};

export function Filters({ filters, fields, exportPath, filename, initial }: {
  filters: AdminFilters; fields: readonly FilterField[]; exportPath?: `/api/admin/${string}`;
  filename?: string; initial?: AdminFilters;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [search, setSearch] = useState(filters.q ?? "");
  const [exporting, setExporting] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const go = (next: AdminFilters, replace = false) => {
    const values = writeFilters(next);
    const href = values.size ? `${pathname}?${values}` : pathname;
    if (replace) router.replace(href, { scroll: false });
    else router.push(href, { scroll: false });
  };
  return (
    <form className="flex flex-wrap items-end gap-3" onSubmit={(event) => {
      event.preventDefault();
      window.clearTimeout(timer.current);
      const form = new FormData(event.currentTarget);
      const next = Object.fromEntries(["q", ...fields.map(({ key }) => key)]
        .map((key) => [key, String(form.get(key) ?? "").trim()]).filter(([, value]) => value));
      if (filters.sort) next.sort = filters.sort;
      go(next);
    }}>
      <label className="grid gap-1">Buscar<input name="q" type="search" className="admin-input" value={search}
        onChange={(event) => {
          const value = event.target.value;
          setSearch(value);
          window.clearTimeout(timer.current);
          timer.current = window.setTimeout(() => {
            const next = { ...filters, q: value.trim() };
            go(Object.fromEntries(Object.entries(next).filter(([key]) => key !== "offset")), true);
          }, 300);
        }} /></label>
      {fields.map(({ key, label, type, options }) => (
        <label key={key} className="grid gap-1">{label}
          {options ? <select className="admin-input" name={key} defaultValue={filters[key] ?? ""}>
            <option value="">Todos</option>{options.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
          </select> : <input className="admin-input" name={key} type={type ?? "text"} defaultValue={filters[key] ?? ""} />}
        </label>
      ))}
      <button type="submit" className="admin-button">Aplicar filtros</button>
      <button type="button" className="admin-button" onClick={() => { window.clearTimeout(timer.current); go(initial ?? {}); }}>Limpiar filtros</button>
      {exportPath && <button type="button" className="admin-button" disabled={exporting} onClick={async () => {
        setExporting(true);
        const exportFilters = writeFilters(filters);
        exportFilters.delete("offset");
        exportFilters.delete("limit");
        exportFilters.delete("detail");
        try { await downloadAdminCsv(`${exportPath}?${exportFilters}`, filename ?? "exportacion"); }
        catch { toast.error("No se pudo exportar el archivo."); }
        finally { setExporting(false); }
      }}>Exportar CSV</button>}
    </form>
  );
}

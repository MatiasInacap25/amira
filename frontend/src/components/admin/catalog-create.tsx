"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { adminRequest } from "@/lib/admin/client";
import { DetailDrawer } from "./dialogs";

export function CatalogCreate() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  return <>
    <button type="button" className="admin-button admin-primary" onClick={() => setOpen(true)}>Crear tipo de servicio</button>
    {open && <DetailDrawer title="Crear tipo de servicio" onClose={() => { if (!saving) setOpen(false); }}>
      <form className="grid gap-4" onSubmit={async (event) => {
        event.preventDefault();
        const values = new FormData(event.currentTarget);
        setSaving(true);
        try {
          const response = await adminRequest("/api/admin/catalog/service-types", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: String(values.get("name")).trim(), description: String(values.get("description")).trim() || null }),
          });
          if (!response.ok) {
            const problem = await response.json().catch(() => null);
            throw new Error(typeof problem?.detail === "string" ? problem.detail : "No se pudo crear el tipo.");
          }
          setOpen(false);
          toast.success("Tipo de servicio creado.");
          router.refresh();
        } catch (problem) {
          toast.error(problem instanceof Error ? problem.message : "No se pudo crear el tipo.");
        } finally {
          setSaving(false);
        }
      }}>
        <label className="grid gap-1">Nombre<input name="name" className="admin-input" required maxLength={120} /></label>
        <label className="grid gap-1">Descripción<textarea name="description" className="admin-input" maxLength={5000} /></label>
        <button type="submit" className="admin-button admin-primary" disabled={saving}>Crear</button>
      </form>
    </DetailDrawer>}
  </>;
}

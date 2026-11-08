"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { authenticatedApiFetch } from "@/lib/auth/account-api";
import {
  buildVehicleFormData,
  emptyVehicleForm,
  validateVehicleForm,
  vehicleRequestError,
  VEHICLE_PHOTO_TYPES,
  VEHICLE_YEAR_MAX,
  VEHICLE_YEAR_MIN,
  type ProviderVehicle,
  type VehicleFormErrors,
  type VehicleFormValues,
} from "@/lib/vehicle-api";

const LOAD_ERROR = "No pudimos cargar tus vehículos.";

export function VehicleManager({ token }: { token: string }) {
  const [vehicles, setVehicles] = useState<ProviderVehicle[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [values, setValues] = useState<VehicleFormValues>(emptyVehicleForm);
  const [errors, setErrors] = useState<VehicleFormErrors>({});
  const [fileInputKey, setFileInputKey] = useState(0);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const api = useCallback((path: string, options?: RequestInit) =>
    authenticatedApiFetch(path, token, process.env.NEXT_PUBLIC_API_URL, options), [token]);

  const reload = useCallback(async () => {
    const response = await api("/api/provider/vehicles");
    if (!response.ok) throw new Error(await vehicleRequestError(response));
    const body = await response.json() as { items: ProviderVehicle[] };
    setVehicles(body.items);
    setLoaded(true);
  }, [api]);

  useEffect(() => {
    void Promise.resolve().then(() => reload()).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : LOAD_ERROR));
  }, [reload]);

  function update<Field extends keyof VehicleFormValues>(field: Field, value: VehicleFormValues[Field]) {
    setValues((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
  }

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    const nextErrors = validateVehicleForm(values);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0 || !values.photo) return;

    setBusy(true);
    try {
      const response = await api("/api/provider/vehicles", { method: "POST", body: buildVehicleFormData({ ...values, photo: values.photo }) });
      if (!response.ok) throw new Error(await vehicleRequestError(response));
      setValues(emptyVehicleForm);
      setFileInputKey((key) => key + 1);
      setNotice("Vehículo registrado.");
      await reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No pudimos registrar el vehículo.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(vehicle: ProviderVehicle) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await api(`/api/provider/vehicles/${vehicle.vehicleId}`, { method: "DELETE" });
      if (!response.ok) throw new Error(await vehicleRequestError(response));
      setNotice("Vehículo eliminado.");
      await reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No pudimos eliminar el vehículo.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="vehicle-manager">
      {notice && <p role="status" aria-live="polite" className="auth-notice">{notice}</p>}
      {error && <p role="alert" aria-live="assertive" className="auth-error">{error}</p>}

      <section aria-labelledby="vehicle-form-title">
        <h2 id="vehicle-form-title">Registrar vehículo</h2>
        <form className="auth-form" noValidate onSubmit={create}>
          <label className="auth-field" htmlFor="vehicle-plate">Patente
            <input aria-describedby={errors.plate ? "vehicle-plate-error" : undefined} aria-invalid={errors.plate ? true : undefined} autoComplete="off" id="vehicle-plate" maxLength={40} onChange={(event) => update("plate", event.target.value)} value={values.plate} />
            {errors.plate && <span className="auth-field-error" id="vehicle-plate-error">{errors.plate}</span>}
          </label>
          <label className="auth-field" htmlFor="vehicle-brand">Marca
            <input aria-describedby={errors.brand ? "vehicle-brand-error" : undefined} aria-invalid={errors.brand ? true : undefined} autoComplete="off" id="vehicle-brand" maxLength={120} onChange={(event) => update("brand", event.target.value)} value={values.brand} />
            {errors.brand && <span className="auth-field-error" id="vehicle-brand-error">{errors.brand}</span>}
          </label>
          <label className="auth-field" htmlFor="vehicle-model">Modelo
            <input aria-describedby={errors.model ? "vehicle-model-error" : undefined} aria-invalid={errors.model ? true : undefined} autoComplete="off" id="vehicle-model" maxLength={120} onChange={(event) => update("model", event.target.value)} value={values.model} />
            {errors.model && <span className="auth-field-error" id="vehicle-model-error">{errors.model}</span>}
          </label>
          <label className="auth-field" htmlFor="vehicle-year">Año (opcional)
            <input aria-describedby={errors.year ? "vehicle-year-error" : undefined} aria-invalid={errors.year ? true : undefined} id="vehicle-year" inputMode="numeric" max={VEHICLE_YEAR_MAX} min={VEHICLE_YEAR_MIN} onChange={(event) => update("year", event.target.value)} type="number" value={values.year} />
            {errors.year && <span className="auth-field-error" id="vehicle-year-error">{errors.year}</span>}
          </label>
          <label className="auth-field" htmlFor="vehicle-maximum-weight">Peso máximo en kg (opcional)
            <input aria-describedby={errors.maximumWeight ? "vehicle-maximum-weight-error" : undefined} aria-invalid={errors.maximumWeight ? true : undefined} id="vehicle-maximum-weight" inputMode="decimal" onChange={(event) => update("maximumWeight", event.target.value)} type="text" value={values.maximumWeight} />
            {errors.maximumWeight && <span className="auth-field-error" id="vehicle-maximum-weight-error">{errors.maximumWeight}</span>}
          </label>
          <label className="auth-field" htmlFor="vehicle-photo">Foto del vehículo
            <input accept={VEHICLE_PHOTO_TYPES.join(",")} aria-describedby={errors.photo ? "vehicle-photo-error" : undefined} aria-invalid={errors.photo ? true : undefined} id="vehicle-photo" key={fileInputKey} onChange={(event) => update("photo", event.target.files?.[0] ?? null)} type="file" />
            {errors.photo && <span className="auth-field-error" id="vehicle-photo-error">{errors.photo}</span>}
          </label>
          <button className="auth-submit" disabled={busy} type="submit">{busy ? "Guardando…" : "Registrar vehículo"}</button>
        </form>
      </section>

      <section aria-labelledby="vehicle-list-title">
        <h2 id="vehicle-list-title">Mis vehículos</h2>
        {loaded && vehicles.length === 0 && <p>No tienes vehículos registrados todavía.</p>}
        {vehicles.length > 0 && (
          <ul aria-label="Vehículos registrados" className="vehicle-list">
            {vehicles.map((vehicle) => (
              <li className="vehicle-card" key={vehicle.vehicleId}>
                {/* eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL; next/image would proxy and cache it */}
                <img alt={`Foto del vehículo ${vehicle.plate}`} src={vehicle.url} />
                <div>
                  <strong>{vehicle.plate}</strong>
                  <p>
                    {vehicle.brand} {vehicle.model}
                    {vehicle.year !== null ? ` · ${vehicle.year}` : ""}
                    {vehicle.maximumWeight !== null ? ` · ${vehicle.maximumWeight} kg` : ""}
                  </p>
                  <button aria-label={`Eliminar vehículo ${vehicle.plate}`} className="auth-secondary-action" disabled={busy} onClick={() => void remove(vehicle)} type="button">Eliminar</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

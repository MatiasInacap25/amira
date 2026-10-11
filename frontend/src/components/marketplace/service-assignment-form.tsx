"use client";

import { useState, type FormEvent } from "react";
import { SameDayConflictDialog } from "@/components/marketplace/same-day-conflict-dialog";
import type {
  ServiceAssignment,
  ServiceAssignmentOptions,
  ServiceAssignmentSaveResult,
  ServiceAssignmentUpdate,
  ServiceSameDayConflict,
} from "@/lib/marketplace-api";
import { serviceActionErrorMessage } from "@/lib/service-status";

type Props = {
  assignments: ServiceAssignment[];
  options: ServiceAssignmentOptions | undefined;
  optionsPending: boolean;
  optionsErrorMessage: string | undefined;
  onSave: (update: ServiceAssignmentUpdate) => Promise<ServiceAssignmentSaveResult>;
};

type AssignmentRow = {
  driverId: string;
  vehicleId: string;
};

type Choice = {
  id: string;
  label: string;
};

const DRIVER_FALLBACK_LABEL = "Conductor";
const VEHICLE_FALLBACK_LABEL = "Vehículo";

function initialRows(assignments: ServiceAssignment[]): AssignmentRow[] {
  if (assignments.length === 0) return [{ driverId: "", vehicleId: "" }];
  return assignments.map(({ driverId, vehicleId }) => ({ driverId, vehicleId }));
}

function validationMessage(rows: AssignmentRow[]): string | null {
  if (rows.length === 0) return "Agrega al menos un conductor y un vehículo.";
  if (rows.some((row) => !row.driverId || !row.vehicleId)) return "Completa cada fila con un conductor y un vehículo.";
  return null;
}

// A prefilled selection that the options no longer offer stays visible, labelled from the current assignment.
function withSelectedFallbacks(choices: Choice[], selectedIds: string[], fallbackFor: (id: string) => Choice): Choice[] {
  const missing = selectedIds.filter((id) => id && !choices.some((choice) => choice.id === id));
  return [...choices, ...missing.map(fallbackFor)];
}

// Each row offers its own current value plus every value not chosen in another row (no duplicate driver or vehicle).
function choicesForRow(choices: Choice[], rows: AssignmentRow[], index: number, field: "driverId" | "vehicleId"): Choice[] {
  const takenElsewhere = rows.filter((_, rowIndex) => rowIndex !== index).map((row) => row[field]);
  const current = rows[index][field];
  return choices.filter((choice) => choice.id === current || !takenElsewhere.includes(choice.id));
}

/** Assigns one or more driver + vehicle pairs to a confirmed service. Mounted only for the profile owner. */
export function ServiceAssignmentForm({ assignments, options, optionsPending, optionsErrorMessage, onSave }: Props) {
  const [rows, setRows] = useState<AssignmentRow[]>(() => initialRows(assignments));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [conflicts, setConflicts] = useState<ServiceSameDayConflict[] | null>(null);

  const driverChoices = withSelectedFallbacks(
    (options?.drivers ?? []).map((driver) => ({
      id: driver.driverId,
      label: driver.isOwner ? `${driverFullName(driver)} (tú)` : driverFullName(driver),
    })),
    rows.map((row) => row.driverId),
    (id) => ({ id, label: assignments.find((assignment) => assignment.driverId === id)?.driverFirstName || DRIVER_FALLBACK_LABEL }),
  );
  const vehicleChoices = withSelectedFallbacks(
    (options?.vehicles ?? []).map((vehicle) => ({ id: vehicle.vehicleId, label: `${vehicle.vehicleLabel} · ${vehicle.plate}` })),
    rows.map((row) => row.vehicleId),
    (id) => {
      const assignment = assignments.find((item) => item.vehicleId === id);
      return { id, label: assignment ? `${assignment.vehicleLabel} · ${assignment.plate}` : VEHICLE_FALLBACK_LABEL };
    },
  );

  const canAddRow = rows.length < Math.min(driverChoices.length, vehicleChoices.length);
  const driverNames = new Map(driverChoices.map((choice) => [choice.id, choice.label]));

  function updateRow(index: number, field: keyof AssignmentRow, value: string) {
    setRows((current) => current.map((row, rowIndex) => (rowIndex === index ? { ...row, [field]: value } : row)));
  }

  async function save(confirmSameDayConflicts: boolean) {
    const message = validationMessage(rows);
    if (message) {
      setError(message);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await onSave({
        assignments: rows.map((row) => ({ driverId: row.driverId, vehicleId: row.vehicleId })),
        confirmSameDayConflicts,
      });
      setConflicts(result.status === "same_day_conflicts" ? result.conflicts : null);
    } catch (cause) {
      setConflicts(null);
      setError(serviceActionErrorMessage(cause, "assign"));
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void save(false);
  }

  return (
    <>
      <form className="account-service-assignment-form" noValidate onSubmit={submit}>
        <p className="account-service-assignment-hint">
          Asigna uno o más pares de conductor y vehículo. Cada conductor y cada vehículo solo pueden usarse una vez en este servicio.
        </p>

        {optionsPending && <p className="account-service-empty" role="status">Cargando conductores y vehículos…</p>}
        {optionsErrorMessage && <p className="account-service-form-error" role="alert">{optionsErrorMessage}</p>}
        {options && options.drivers.length === 0 && (
          <p className="account-service-empty">No hay conductores disponibles en tu perfil.</p>
        )}
        {options && options.vehicles.length === 0 && (
          <p className="account-service-empty">No hay vehículos disponibles en tu perfil.</p>
        )}

        <ol className="account-service-assignment-rows">
          {rows.map((row, index) => (
            // Index keys are safe: the selects are controlled by the rows array, not by the DOM.
            <li className="account-service-assignment-row" key={index}>
              <label className="marketplace-field">
                <span>Conductor</span>
                <select
                  disabled={busy || !options}
                  onChange={(event) => updateRow(index, "driverId", event.target.value)}
                  value={row.driverId}
                >
                  <option value="">Selecciona un conductor</option>
                  {choicesForRow(driverChoices, rows, index, "driverId").map((choice) => (
                    <option key={choice.id} value={choice.id}>{choice.label}</option>
                  ))}
                </select>
              </label>
              <label className="marketplace-field">
                <span>Vehículo</span>
                <select
                  disabled={busy || !options}
                  onChange={(event) => updateRow(index, "vehicleId", event.target.value)}
                  value={row.vehicleId}
                >
                  <option value="">Selecciona un vehículo</option>
                  {choicesForRow(vehicleChoices, rows, index, "vehicleId").map((choice) => (
                    <option key={choice.id} value={choice.id}>{choice.label}</option>
                  ))}
                </select>
              </label>
              <button
                aria-label={`Quitar la fila ${index + 1}`}
                className="button button-secondary account-service-assignment-remove"
                disabled={busy || rows.length === 1}
                onClick={() => setRows((current) => current.filter((_, rowIndex) => rowIndex !== index))}
                type="button"
              >
                Quitar
              </button>
            </li>
          ))}
        </ol>

        <button
          className="button button-secondary account-service-assignment-add"
          disabled={busy || !options || !canAddRow}
          onClick={() => setRows((current) => [...current, { driverId: "", vehicleId: "" }])}
          type="button"
        >
          Añadir conductor y vehículo
        </button>

        {error && <p className="account-service-form-error" role="alert">{error}</p>}

        <div className="account-service-form-actions">
          <button className="button button-primary" disabled={busy || !options} type="submit">
            {busy ? "Guardando…" : "Guardar asignaciones"}
          </button>
        </div>
      </form>

      <SameDayConflictDialog
        busy={busy}
        conflicts={conflicts ?? []}
        driverNames={driverNames}
        onCancel={() => setConflicts(null)}
        onConfirm={() => void save(true)}
        open={conflicts !== null}
      />
    </>
  );
}

function driverFullName(driver: { firstName: string; lastName: string }) {
  return `${driver.firstName} ${driver.lastName}`.trim() || DRIVER_FALLBACK_LABEL;
}

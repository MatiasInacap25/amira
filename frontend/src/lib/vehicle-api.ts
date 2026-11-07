// Provider vehicle form rules and API helpers. Messages are Spanish; the backend enforces the same limits again.

export const VEHICLE_PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];
export const VEHICLE_PHOTO_MAX_BYTES = 5 * 1024 * 1024;
export const VEHICLE_YEAR_MIN = 1886;
export const VEHICLE_YEAR_MAX = 2200;

export type ProviderVehicle = {
  vehicleId: string;
  plate: string;
  brand: string;
  model: string;
  year: number | null;
  maximumWeight: number | null;
  url: string;
  expiresAt: string;
};

export type VehicleFormValues = {
  plate: string;
  brand: string;
  model: string;
  year: string;
  maximumWeight: string;
  photo: File | null;
};

export type VehicleFormErrors = Partial<Record<keyof VehicleFormValues, string>>;

export const emptyVehicleForm: VehicleFormValues = {
  plate: "",
  brand: "",
  model: "",
  year: "",
  maximumWeight: "",
  photo: null,
};

export function validateVehicleForm(values: VehicleFormValues): VehicleFormErrors {
  const errors: VehicleFormErrors = {};
  const plate = values.plate.trim();
  const brand = values.brand.trim();
  const model = values.model.trim();
  const year = values.year.trim();
  const weight = values.maximumWeight.trim();

  if (!plate) errors.plate = "Ingresa la patente.";
  else if (plate.length > 16) errors.plate = "La patente no puede tener más de 16 caracteres.";

  if (!brand) errors.brand = "Ingresa la marca.";
  else if (brand.length > 80) errors.brand = "La marca no puede tener más de 80 caracteres.";

  if (!model) errors.model = "Ingresa el modelo.";
  else if (model.length > 100) errors.model = "El modelo no puede tener más de 100 caracteres.";

  if (year) {
    const parsed = Number(year);
    if (!/^\d{4}$/.test(year) || parsed < VEHICLE_YEAR_MIN || parsed > VEHICLE_YEAR_MAX) {
      errors.year = `El año debe estar entre ${VEHICLE_YEAR_MIN} y ${VEHICLE_YEAR_MAX}.`;
    }
  }

  if (weight) {
    if (!/^\d+(\.\d{1,2})?$/.test(weight)) errors.maximumWeight = "El peso máximo debe ser un número con hasta dos decimales.";
    else if (Number(weight) <= 0) errors.maximumWeight = "El peso máximo debe ser mayor que 0 kg.";
  }

  if (!values.photo) errors.photo = "Sube una foto del vehículo.";
  else if (!VEHICLE_PHOTO_TYPES.includes(values.photo.type)) errors.photo = "La foto debe ser JPEG, PNG o WebP.";
  else if (values.photo.size > VEHICLE_PHOTO_MAX_BYTES) errors.photo = "La foto supera el tamaño máximo de 5 MB.";

  return errors;
}

// Builds the multipart body. Optional fields are omitted when empty so the API never sees a blank number.
export function buildVehicleFormData(values: VehicleFormValues & { photo: File }): FormData {
  const data = new FormData();
  data.append("plate", values.plate.trim());
  data.append("brand", values.brand.trim());
  data.append("model", values.model.trim());
  if (values.year.trim()) data.append("year", values.year.trim());
  if (values.maximumWeight.trim()) data.append("maximum_weight", values.maximumWeight.trim());
  data.append("photo", values.photo, values.photo.name);
  return data;
}

// A duplicate plate answers 409 with a Spanish detail; every other failure gets a fixed Spanish message.
export async function vehicleRequestError(response: Response): Promise<string> {
  const body = await response.json().catch(() => null) as { detail?: unknown } | null;
  if (response.status === 409 && typeof body?.detail === "string") return body.detail;
  if (response.status === 403) return "Solo los proveedores pueden gestionar vehículos.";
  if (response.status === 413) return "La foto supera el tamaño máximo permitido.";
  if (response.status === 415) return "La foto debe ser JPEG, PNG o WebP.";
  if (response.status === 422) return "Revisa los datos del vehículo.";
  return "No pudimos completar la operación. Inténtalo nuevamente.";
}

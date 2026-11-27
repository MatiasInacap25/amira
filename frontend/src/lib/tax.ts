// Pure tax rules for the quotation preview and the service breakdown. Mirrors backend/src/amira_api/tax.py.
// Amounts are whole CLP pesos. Keep this module free of imports so node unit tests can load it.

export const IVA_RATE_PERCENT = 19;

export type IvaSplit = { net: number; iva: number };

export type TaxDocumentType = "boleta" | "factura_comision";

// Every amount includes IVA: the net is extracted with half-up rounding and the IVA is the remainder.
export function splitIva(total: number): IvaSplit {
  if (!Number.isInteger(total) || total < 0) throw new RangeError("total must be a non-negative whole number of pesos");
  // round_half_up(total / 1.19) with integer arithmetic: floor((200 * total + 119) / 238).
  const net = Math.floor((200 * total + 119) / 238);
  return { net, iva: total - net };
}

export function documentTypeLabel(type: TaxDocumentType): string {
  return type === "boleta" ? "Boleta" : "Factura de comisión";
}

export function documentConceptLabel(type: TaxDocumentType): string {
  return type === "boleta" ? "Servicio de transporte" : "Comisión por intermediación";
}

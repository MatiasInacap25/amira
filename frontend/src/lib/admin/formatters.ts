const money = new Intl.NumberFormat("es-CL", { style: "currency", currency: "CLP" });
const time = new Intl.DateTimeFormat("es-CL", {
  timeZone: "America/Santiago", year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

export function adminMoney(amount: number | null | undefined) {
  return amount == null ? "Sin dato" : money.format(amount);
}

export function adminDate(value: string | null | undefined) {
  if (!value) return "Sin dato";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Sin dato";
  const parts = Object.fromEntries(time.formatToParts(date).map(({ type, value }) => [type, value]));
  return `${parts.day}-${parts.month}-${parts.year} ${parts.hour}:${parts.minute}`;
}

export function adminRut(value: string | null | undefined) {
  if (!value) return "Sin dato";
  const clean = value.replace(/[.\s-]/g, "").toUpperCase();
  if (!/^\d{1,8}[\dK]$/.test(clean)) return value;
  return `${clean.slice(0, -1).replace(/\B(?=(\d{3})+(?!\d))/g, ".")}-${clean.at(-1)}`;
}

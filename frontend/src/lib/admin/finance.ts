export type SearchParams = Record<string, string | string[] | undefined>;

const calendar = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Santiago", year: "numeric", month: "2-digit", day: "2-digit" });

export function dashboardPeriod(params: SearchParams, now = new Date()) {
  const today = calendar.format(now);
  const preset = typeof params.period === "string" && ["today", "week", "month", "custom"].includes(params.period) ? params.period : "30";
  const start = new Date(`${today}T00:00:00Z`);
  start.setUTCDate(start.getUTCDate() - (preset === "today" ? 0 : preset === "week" ? 6 : 29));
  const first = preset === "month" ? `${today.slice(0, 7)}-01` : start.toISOString().slice(0, 10);
  const valid = (value: unknown): value is string => typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value);
  return { preset, from: preset === "custom" && valid(params.from) ? params.from : first, to: preset === "custom" && valid(params.to) ? params.to : today };
}

export function monthlyPeriod(value: unknown, now = new Date()) {
  const month = typeof value === "string" && /^[1-9]\d{3}-(0[1-9]|1[0-2])$/.test(value) ? value : calendar.format(now).slice(0, 7);
  const end = new Date(`${month}-01T00:00:00Z`);
  end.setUTCMonth(end.getUTCMonth() + 1, 0);
  return { month, from: `${month}-01`, to: end.toISOString().slice(0, 10) };
}

type Amount = number | string;
export type FinanceSummary = {
  collected: Amount; refunded: Amount; net_collected: Amount; payout_due: Amount; payout_paid: Amount;
  payout_due_count: number; payout_blocked_count: number; commission_gross: Amount; commission_net: Amount;
  commission_iva: Amount; platform_iva: Amount; retained_net: Amount; retained_iva: Amount;
  service_counts: Record<string, number>; pending: Record<string, number>;
};
export type FinanceDay = { day: string; collected: Amount; commission: Amount };
export type FinanceMovement = {
  id: string; at: string; kind: "payment" | "refund" | "payout"; status: string; amount: Amount; service_id: string | null;
  first_name: string | null; last_name: string | null; provider: string | null;
};
export type ProviderCommission = { provider: string; services: number; gross: Amount; commission: Amount; commission_iva: Amount; net_paid: Amount };
export type AdminConfiguration = {
  app_env: string; commission_percent: number; claim_window_hours: number; payment_adapter: string | null; payout_adapter: string | null;
  admins: { user_id: string; email: string | null }[];
};

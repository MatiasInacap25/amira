import assert from "node:assert/strict";
import test from "node:test";
import { adminDate, adminMoney, adminRut } from "../../src/lib/admin/formatters.ts";
import { readFilters, writeFilters, updateFilter } from "../../src/lib/admin/query.ts";

test("admin formats CLP, Santiago time and RUT", () => {
  assert.equal(adminMoney(80000), "$80.000");
  assert.equal(adminDate("2026-11-24T13:15:00Z"), "24-11-2026 10:15");
  assert.equal(adminRut("123456789"), "12.345.678-9");
});

test("filters round-trip and changing a filter resets pagination only", () => {
  const allowed = ["q", "action", "sort", "offset"];
  const filters = readFilters(new URLSearchParams("q=garc%C3%ADa&action=rating.hide&offset=20&junk=1"), allowed);
  assert.deepEqual(filters, { q: "garcía", action: "rating.hide", offset: "20" });
  assert.equal(writeFilters(filters).toString(), "q=garc%C3%ADa&action=rating.hide&offset=20");
  assert.deepEqual(updateFilter(filters, "q", ""), { action: "rating.hide" });
});

test("reporting periods use Santiago dates and calendar month lengths", async () => {
  const { dashboardPeriod, monthlyPeriod } = await import("../../src/lib/admin/finance.ts");
  assert.deepEqual(dashboardPeriod({ period: "week" }, new Date("2026-11-24T01:00:00Z")),
    { preset: "week", from: "2026-11-17", to: "2026-11-23" });
  assert.deepEqual(monthlyPeriod("2024-02"), { month: "2024-02", from: "2024-02-01", to: "2024-02-29" });
});

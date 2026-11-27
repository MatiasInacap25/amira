import assert from "node:assert/strict";
import { test } from "node:test";
import { formatServiceRoute, formatServiceSchedule } from "../../src/lib/customer-service-schedule.ts";

test("missing scheduled date reads as to be confirmed", () => {
  assert.equal(formatServiceSchedule(null), "Fecha por confirmar");
});

test("scheduled date renders dd-mm-aaaa · HH:mm in America/Santiago during daylight saving time", () => {
  // October 2026 is UTC-3 in Santiago (CLST): 13:00Z is 10:00 local.
  assert.equal(formatServiceSchedule("2026-10-20T13:00:00Z"), "20-10-2026 · 10:00");
});

test("scheduled date uses standard time outside daylight saving", () => {
  // June 2026 is UTC-4 in Santiago (CLT, winter): 12:30Z is 08:30 local.
  assert.equal(formatServiceSchedule("2026-06-15T12:30:00Z"), "15-06-2026 · 08:30");
});

test("route joins origin and destination with an arrow", () => {
  assert.equal(formatServiceRoute("Santiago", "Valparaíso"), "Santiago → Valparaíso");
});

test("route shows the placeholder for each missing side", () => {
  assert.equal(formatServiceRoute(null, null), "Sin dirección → Sin dirección");
  assert.equal(formatServiceRoute("Santiago", null), "Santiago → Sin dirección");
  assert.equal(formatServiceRoute("  ", "Valparaíso"), "Sin dirección → Valparaíso");
});

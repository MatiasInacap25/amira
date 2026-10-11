import assert from "node:assert/strict";
import { test } from "node:test";
import {
  buildProviderRequestsQuery,
  customerDisplayName,
  formatRouteEndpoint,
  isProviderRole,
  nextProviderRequestOffset,
  parseProviderRequestStatus,
  pendingBadgeLabel,
  resolveInboxPanel,
} from "../../src/lib/provider-requests.ts";

function page(offset, count, total) {
  return { offset, limit: 20, total, items: Array.from({ length: count }, (_, index) => ({ requestId: String(index) })) };
}

test("returns the next offset while more requests remain", () => {
  assert.equal(nextProviderRequestOffset(page(0, 20, 45)), 20);
  assert.equal(nextProviderRequestOffset(page(20, 20, 45)), 40);
});

test("returns undefined once offset plus items reaches total", () => {
  assert.equal(nextProviderRequestOffset(page(40, 5, 45)), undefined);
  assert.equal(nextProviderRequestOffset(page(0, 20, 20)), undefined);
});

test("stops on an empty page even when total says more requests exist", () => {
  assert.equal(nextProviderRequestOffset(page(0, 0, 45)), undefined);
});

test("omits the status filter for the 'all' view and keeps paging parameters", () => {
  assert.equal(buildProviderRequestsQuery({ limit: 20, offset: 0 }), "limit=20&offset=0");
  assert.equal(buildProviderRequestsQuery({ status: "pending", limit: 20, offset: 40 }), "status=pending&limit=20&offset=40");
});

test("parses only the three contract statuses", () => {
  assert.equal(parseProviderRequestStatus("pending"), "pending");
  assert.equal(parseProviderRequestStatus("accepted"), "accepted");
  assert.equal(parseProviderRequestStatus("rejected"), "rejected");
  assert.equal(parseProviderRequestStatus("all"), undefined);
  assert.equal(parseProviderRequestStatus("PENDING"), undefined);
  assert.equal(parseProviderRequestStatus(null), undefined);
});

test("labels a route with commune and region when the catalog provides them", () => {
  assert.equal(formatRouteEndpoint("Providencia", "Región Metropolitana", "Av. Italia 123"), "Providencia, Región Metropolitana");
});

test("labels a route with the commune alone when the region is missing", () => {
  assert.equal(formatRouteEndpoint("Providencia", null, "Av. Italia 123"), "Providencia");
});

test("falls back to the free-text address when the commune is missing", () => {
  assert.equal(formatRouteEndpoint(null, null, "Av. Italia 123"), "Av. Italia 123");
  assert.equal(formatRouteEndpoint(null, "Región Metropolitana", "Av. Italia 123"), "Av. Italia 123");
});

test("uses a neutral label when neither the commune nor the free text is available", () => {
  assert.equal(formatRouteEndpoint(null, null, null), "Ubicación no indicada");
  assert.equal(formatRouteEndpoint(" ", null, "  "), "Ubicación no indicada");
});

test("shows only the first name before acceptance", () => {
  assert.equal(customerDisplayName({ customerFirstName: "Camila", customerLastName: null }), "Camila");
});

test("shows first and last name once the request is accepted", () => {
  assert.equal(customerDisplayName({ customerFirstName: "Camila", customerLastName: "Rojas" }), "Camila Rojas");
});

test("recognises only the provider account roles", () => {
  assert.equal(isProviderRole("company_owner"), true);
  assert.equal(isProviderRole("independent_driver"), true);
  assert.equal(isProviderRole("client"), false);
  assert.equal(isProviderRole(undefined), false);
});

test("formats the pending badge and caps large counts", () => {
  assert.equal(pendingBadgeLabel(0), undefined);
  assert.equal(pendingBadgeLabel(3), "3");
  assert.equal(pendingBadgeLabel(99), "99");
  assert.equal(pendingBadgeLabel(120), "99+");
});

test("hides rows and load-more and marks the panel busy while a tab's first page loads", () => {
  assert.deepEqual(
    resolveInboxPanel({ pending: false, placeholder: true, hasItems: true, hasNextPage: true }),
    { busy: true, showRows: false, showLoadMore: false },
  );
});

test("keeps the skeleton for the initial load of a tab", () => {
  assert.deepEqual(
    resolveInboxPanel({ pending: true, placeholder: false, hasItems: false, hasNextPage: false }),
    { busy: true, showRows: false, showLoadMore: false },
  );
});

test("shows rows and load-more once the current tab's data is loaded", () => {
  assert.deepEqual(
    resolveInboxPanel({ pending: false, placeholder: false, hasItems: true, hasNextPage: true }),
    { busy: false, showRows: true, showLoadMore: true },
  );
  assert.deepEqual(
    resolveInboxPanel({ pending: false, placeholder: false, hasItems: false, hasNextPage: false }),
    { busy: false, showRows: true, showLoadMore: false },
  );
});

import assert from "node:assert/strict";
import { test } from "node:test";
import { nextCustomerServicesOffset } from "../../src/lib/customer-services-pagination.ts";

function page(offset, count, total) {
  return { offset, limit: 20, total, items: Array.from({ length: count }, (_, index) => ({ serviceId: String(index) })) };
}

test("returns the next offset while more items remain", () => {
  assert.equal(nextCustomerServicesOffset(page(0, 20, 45)), 20);
  assert.equal(nextCustomerServicesOffset(page(20, 20, 45)), 40);
});

test("returns undefined once offset plus items reaches total", () => {
  assert.equal(nextCustomerServicesOffset(page(40, 5, 45)), undefined);
  assert.equal(nextCustomerServicesOffset(page(0, 20, 20)), undefined);
});

test("stops on an empty page even when total says more items exist", () => {
  assert.equal(nextCustomerServicesOffset(page(0, 0, 45)), undefined);
  assert.equal(nextCustomerServicesOffset(page(20, 0, 45)), undefined);
});

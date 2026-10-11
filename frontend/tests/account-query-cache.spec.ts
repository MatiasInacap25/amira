import { expect, test } from "@playwright/test";
import { QueryClient } from "@tanstack/react-query";
import {
  ACCOUNT_ROLE_KEY,
  clearAccountScopedQueries,
  CUSTOMER_SERVICES_KEY,
  PROVIDER_SERVICES_KEY,
  SERVICE_DETAIL_KEY,
} from "../src/lib/service-query-keys";

test("clearAccountScopedQueries drops every account-scoped service query and keeps unrelated ones", () => {
  const queryClient = new QueryClient();
  const roleKey = ACCOUNT_ROLE_KEY;
  const providerListKey = [...PROVIDER_SERVICES_KEY, "confirmed"];
  const serviceDetailKey = [...SERVICE_DETAIL_KEY, "provider", "service-1"];
  const customerListKey = [...CUSTOMER_SERVICES_KEY, "user-1"];
  const unrelatedKey = ["unrelated-query"];

  for (const key of [roleKey, providerListKey, serviceDetailKey, customerListKey, unrelatedKey]) {
    queryClient.setQueryData(key, { seeded: true });
  }

  clearAccountScopedQueries(queryClient);

  expect(queryClient.getQueryData(roleKey)).toBeUndefined();
  expect(queryClient.getQueryData(providerListKey)).toBeUndefined();
  expect(queryClient.getQueryData(serviceDetailKey)).toBeUndefined();
  expect(queryClient.getQueryData(customerListKey)).toBeUndefined();
  expect(queryClient.getQueryCache().findAll({ queryKey: PROVIDER_SERVICES_KEY })).toHaveLength(0);
  expect(queryClient.getQueryCache().findAll({ queryKey: SERVICE_DETAIL_KEY })).toHaveLength(0);
  expect(queryClient.getQueryCache().findAll({ queryKey: CUSTOMER_SERVICES_KEY })).toHaveLength(0);
  expect(queryClient.getQueryData(unrelatedKey)).toEqual({ seeded: true });
});

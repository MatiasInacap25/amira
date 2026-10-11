export type PagedItems = {
  offset: number;
  items: readonly unknown[];
  total: number;
};

// Stops on an empty page so a total/items mismatch cannot cause endless requests.
export function nextCustomerServicesOffset(page: PagedItems): number | undefined {
  if (page.items.length === 0) return undefined;
  const nextOffset = page.offset + page.items.length;
  return nextOffset < page.total ? nextOffset : undefined;
}

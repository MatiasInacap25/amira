import Link from "next/link";
import { notFound } from "next/navigation";
import { ResourceTable } from "@/components/admin/resource-table";
import { adminNavigation } from "@/lib/admin/navigation";
import { readFilters, writeFilters } from "@/lib/admin/query";
import { adminResources, paidPayoutResource, type AdminPageData, type AdminRow } from "@/lib/admin/resources";
import { adminData, checkAdmin } from "@/lib/admin/server";

export default async function AdminSectionPage({ params, searchParams }: PageProps<"/admin/[section]">) {
  const access = await checkAdmin();
  if (!access) return null;
  const { section } = await params;
  const item = adminNavigation.flatMap((group) => [...group.links]).find(({ slug }) => slug === section);
  if (!item) notFound();
  const raw = await searchParams;
  const paid = section === "desembolsos" && raw.tab === "paid";
  const resource = paid ? paidPayoutResource : adminResources[section];
  if (!resource) return <main className="space-y-2 p-6"><h1>{item.label}</h1><p>Sección en preparación.</p></main>;
  const get = (key: string) => {
    const value = raw[key];
    return typeof value === "string" ? value : null;
  };
  const filters = { ...resource.defaults, ...readFilters({ get }, ["q", "sort", "limit", "offset", ...resource.filters.map(({ key }) => key)]) };
  const detailId = get("detail") ?? undefined;
  const [data, detail] = await Promise.all([
    adminData<AdminPageData>(`${resource.path}?${writeFilters(filters)}`, access.accessToken),
    detailId ? adminData<AdminRow>(`${resource.path}/${encodeURIComponent(detailId)}`, access.accessToken) : null,
  ]);
  return <main className="space-y-4 p-6">
    <header><h1 className="text-2xl font-semibold">{resource.title}</h1><p>{resource.description}</p></header>
    {section === "desembolsos" && <nav aria-label="Vistas de desembolsos" className="flex gap-2">
      <Link className="admin-button" href="/admin/desembolsos" aria-current={paid ? undefined : "page"}>Pendientes</Link>
      <Link className="admin-button" href="/admin/desembolsos?tab=paid" aria-current={paid ? "page" : undefined}>Pagados</Link>
    </nav>}
    <ResourceTable resource={resource} data={data} filters={filters} detail={detail} detailId={detailId} live={get("live") === "1"} />
  </main>;
}

import { notFound } from "next/navigation";
import { adminNavigation } from "@/lib/admin/navigation";
import { checkAdmin } from "@/lib/admin/server";

export default async function AdminSectionPage({ params }: { params: Promise<{ section: string }> }) {
  if (!await checkAdmin()) return null;
  const { section } = await params;
  const item = adminNavigation.flatMap((group) => [...group.links]).find(({ slug }) => slug === section);
  if (!item) notFound();
  return <main className="space-y-2 p-6"><h1>{item.label}</h1><p>Sección en preparación.</p></main>;
}

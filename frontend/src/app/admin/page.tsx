import { checkAdmin } from "@/lib/admin/server";

export default async function AdminPage() {
  if (!await checkAdmin()) return null;
  return <main className="p-6"><h1>Principal</h1></main>;
}

import type { ReactNode } from "react";
import Link from "next/link";

export function KpiCard({ title, value, description, href }: {
  title: string; value: ReactNode; description?: ReactNode; href?: string;
}) {
  const content = <><h2>{title}</h2><strong className="text-2xl">{value}</strong>{description && <p>{description}</p>}</>;
  return href ? <Link className="admin-card" href={href}>{content}</Link> : <section className="admin-card">{content}</section>;
}

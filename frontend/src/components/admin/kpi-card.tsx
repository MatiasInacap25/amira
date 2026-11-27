import type { ReactNode } from "react";
import Link from "next/link";

export function KpiCard({ title, value, description, href }: {
  title: string; value: ReactNode; description?: ReactNode; href?: string;
}) {
  const content = <><h3>{title}</h3><strong>{value}</strong>{description && <p>{description}</p>}</>;
  return href ? <Link className="admin-card admin-kpi" href={href}>{content}</Link> : <section className="admin-card admin-kpi">{content}</section>;
}

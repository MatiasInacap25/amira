"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { type AdminFilters, updateFilter, writeFilters } from "@/lib/admin/query";

export type RowAction = { label: string; href?: string; newTab?: boolean; disabled?: string; onClick?: () => void };

export function RowActionsMenu({ actions, rowLabel }: { actions: readonly RowAction[]; rowLabel: string }) {
  const menu = useRef<HTMLDetailsElement>(null);
  return (
    <details ref={menu} onClick={(event) => event.stopPropagation()} className="admin-row-menu">
      <summary aria-label={`Acciones: ${rowLabel}`}>⋮</summary>
      <ul>
        {actions.map(({ label, href, newTab, disabled, onClick }) => (
          <li key={label}>
            {disabled ? <button type="button" aria-disabled title={disabled}>{label}</button>
              : href ? <Link href={href} target={newTab ? "_blank" : undefined} rel={newTab ? "noopener noreferrer" : undefined} onClick={() => { if (menu.current) menu.current.open = false; }}>{label}</Link>
              : <button type="button" onClick={() => { if (menu.current) menu.current.open = false; onClick?.(); }}>{label}</button>}
          </li>
        ))}
      </ul>
    </details>
  );
}

const UUID = /^[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/i;

function CopyIdentifier({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return <button className="admin-copy" type="button" aria-label={`Copiar ${label}: ${value}`}
    onBlur={() => setCopied(false)}
    onClick={() => { void navigator.clipboard?.writeText(value).then(() => setCopied(true), () => setCopied(false)); }}>
    {copied ? <Check size={14} aria-hidden /> : <Copy size={14} aria-hidden />}
  </button>;
}

type Column<T> = {
  title: string;
  sort?: string;
  format?: "money" | "date";
  identifier?: (item: T) => unknown;
  href?: (item: T) => string | undefined;
  cell: (item: T, shortId?: string) => ReactNode;
};

export function DataTable<T>({ columns, rows, rowId, rowLabel, onDetail, actions, filters, pathname, total, limit, offset,
  loading, error, onRetry }: {
  columns: readonly Column<T>[]; rows: readonly T[]; rowId: (row: T) => string; rowLabel?: (row: T) => string;
  onDetail?: (row: T) => void; actions?: (row: T) => readonly RowAction[];
  filters: AdminFilters; pathname: string; total: number; limit: number; offset: number;
  loading?: boolean; error?: boolean; onRetry?: () => void;
}) {
  const href = (key: string, value: string) => `${pathname}?${writeFilters(updateFilter(filters, key, value))}`;
  if (loading) return <div className="admin-skeleton" role="status" aria-label="Cargando resultados" />;
  if (error) return <p role="alert">No se pudieron cargar los resultados. <button className="admin-button" onClick={onRetry}>Reintentar</button></p>;
  if (!rows.length) return <p>No hay resultados con estos filtros</p>;
  return (
    <>
      <div className="admin-table-scroll">
        <table>
          <thead><tr>{columns.map(({ title, sort, format }) => (
            <th key={title} scope="col" data-format={format} aria-sort={sort && filters.sort === sort ? "ascending" : sort && filters.sort === `-${sort}` ? "descending" : undefined}>
              {sort ? <Link href={href("sort", filters.sort === sort ? `-${sort}` : sort)}>{title}</Link> : title}
            </th>
          ))}{actions && <th className="admin-actions-cell" scope="col"><span className="sr-only">Acciones</span></th>}</tr></thead>
          <tbody>{rows.map((row) => (
            <tr key={rowId(row)} onClick={onDetail ? (event) => {
              if (!(event.target as Element).closest("a,button,summary,details")) onDetail(row);
            } : undefined}>
              {columns.map(({ title, cell, format, identifier, href: cellHref }, index) => {
                const raw = identifier?.(row);
                const uuid = typeof raw === "string" && UUID.test(raw) ? raw : undefined;
                const value = cell(row, uuid ? `${uuid.slice(0, 8)}…` : undefined);
                const label = uuid ? <span title={uuid}>{value}</span> : value;
                const link = cellHref?.(row);
                const content = link ? <Link className="underline" href={link}>{label}</Link>
                  : index === 0 && onDetail
                    ? <button className="text-left underline" type="button" onClick={() => onDetail(row)}>{label}</button>
                    : label;
                return <td key={title} data-format={format}>
                  {uuid ? <span className="admin-id-cell">{content}<CopyIdentifier label={title} value={uuid} /></span> : content}
                </td>;
              })}
              {actions && <td className="admin-actions-cell"><RowActionsMenu actions={actions(row)} rowLabel={rowLabel?.(row) ?? rowId(row)} /></td>}
            </tr>
          ))}</tbody>
        </table>
      </div>
      <nav aria-label="Paginación" className="admin-pagination">
        <span>Mostrando {offset + 1}–{offset + rows.length} de {total}</span>
        {offset > 0 && <Link href={href("offset", String(Math.max(0, offset - limit)))}>Anterior</Link>}
        {offset + limit < total && <Link href={href("offset", String(offset + limit))}>Siguiente</Link>}
      </nav>
    </>
  );
}

"use client";

import { LogOut, Menu, X } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef } from "react";
import { useSignOut } from "@/components/marketplace/profile-menu";
import { adminHref, adminNavigation } from "@/lib/admin/navigation";

type SidebarProps = { email: string; counts?: Record<string, number> };

function SidebarContent({ email, counts = {}, onNavigate }: SidebarProps & { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { signOut, signingOut, error } = useSignOut(onNavigate);
  return (
    <div className="admin-nav-content">
      <Link href="/admin" onClick={onNavigate} className="admin-brand">
        <Image src="/brand/amira-logo.png" alt="Amira" width={157} height={65} loading="eager" />
        <span>Admin</span>
      </Link>
      <nav aria-label="Administración">
        {adminNavigation.map((group) => (
          <section key={group.name}>
            <h2>{group.name}</h2>
            <ul>
              {group.links.map(({ slug, label, icon: Icon }) => {
                const href = adminHref(slug);
                return (
                  <li key={slug}>
                    <Link href={href} prefetch={false} onClick={onNavigate} aria-current={pathname === href ? "page" : undefined}>
                      <Icon size={17} aria-hidden />
                      <span>{label}</span>
                      {counts[slug] > 0 && <small aria-label={`${counts[slug]} pendientes`}>{counts[slug]}</small>}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </nav>
      <footer>
        <p title={email}>{email}</p>
        <button type="button" onClick={signOut} disabled={signingOut}><LogOut size={16} aria-hidden /> Cerrar sesión</button>
        {error && <p role="alert">{error}</p>}
      </footer>
    </div>
  );
}

export function Sidebar(props: SidebarProps) {
  const menu = useRef<HTMLDialogElement>(null);
  const close = () => menu.current?.close();
  return (
    <>
      <aside className="admin-sidebar"><SidebarContent {...props} /></aside>
      <div className="admin-topbar">
        <button type="button" onClick={() => menu.current?.showModal()} aria-label="Abrir menú"><Menu size={24} /></button>
        <span>Amira Admin</span>
      </div>
      <dialog ref={menu} className="admin-mobile-menu" aria-label="Menú de administración" onClick={(event) => { if (event.target === event.currentTarget) close(); }}>
        <button type="button" className="admin-close" aria-label="Cerrar menú" onClick={close}><X size={20} /></button>
        <SidebarContent {...props} onNavigate={close} />
      </dialog>
    </>
  );
}

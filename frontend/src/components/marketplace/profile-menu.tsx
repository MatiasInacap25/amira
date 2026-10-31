"use client";

import { CircleUserRound } from "lucide-react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { clearAccountScopedQueries } from "@/lib/service-query-keys";
import { createClient } from "@/lib/supabase/client";

// Shared sign-out for the header dropdown and the mobile navigation. A failed sign-out resolves with an error message and keeps the caller usable.
export function useSignOut(onSignedOut?: () => void) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [signingOut, setSigningOut] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function signOut() {
    if (signingOut) return;
    setSigningOut(true);
    setError(null);
    try {
      const { error: signOutError } = await createClient().auth.signOut();
      if (signOutError) throw signOutError;
      clearAccountScopedQueries(queryClient);
      onSignedOut?.();
      router.replace("/");
      router.refresh();
    } catch {
      setError("No pudimos cerrar sesión. Inténtalo nuevamente.");
    } finally {
      setSigningOut(false);
    }
  }

  return { signOut, signingOut, error };
}

// Account icon for signed-in visitors. Opens a menu with the profile settings link and sign-out.
export function ProfileMenu() {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();
  const { signOut, signingOut, error } = useSignOut(() => setOpen(false));

  useEffect(() => {
    if (!open) return;

    function handlePointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setOpen(false);
      buttonRef.current?.focus();
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div className="profile-menu" ref={rootRef}>
      <button
        aria-controls={open ? menuId : undefined}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label="Menú de perfil"
        className="profile-menu-toggle"
        onClick={() => setOpen((current) => !current)}
        ref={buttonRef}
        type="button"
      >
        <CircleUserRound aria-hidden="true" size={24} strokeWidth={1.9} />
      </button>
      {open && (
        <div aria-label="Opciones de perfil" className="profile-menu-dropdown" id={menuId} role="menu">
          <Link className="profile-menu-item" href="/cuenta/perfil" onClick={() => setOpen(false)} role="menuitem">
            Configuración del perfil
          </Link>
          <button
            className="profile-menu-item"
            disabled={signingOut}
            onClick={signOut}
            role="menuitem"
            type="button"
          >
            {signingOut ? "Cerrando sesión…" : "Cerrar sesión"}
          </button>
          {error && <p className="profile-menu-error" role="alert">{error}</p>}
        </div>
      )}
    </div>
  );
}

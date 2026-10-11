"use client";

import { ArrowRight, Menu, Truck, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

export function MarketplaceHeader() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="site-header">
      <div className="header-inner">
        <Link aria-label="Amira, inicio" className="brand" href="/">
          <span className="brand-mark"><Truck aria-hidden="true" size={20} strokeWidth={2.2} /></span>
          <span>amira<span className="brand-period">.</span></span>
        </Link>
        <nav aria-label="Navegación principal" className="desktop-nav">
          <Link className="button button-secondary header-nav-button" href="/servicios">Buscar servicios</Link>
          <Link className="button button-secondary header-nav-button" href="/rutas-compartidas">Rutas compartidas</Link>
          <Link href="/solicitudes">Mis solicitudes</Link>
          <Link href="/#como-funciona">Cómo funciona</Link>
        </nav>
        <div className="header-actions">
          <div className="header-auth-links">
            <Link className="login-link" href="/login">Iniciar sesión</Link>
            <Link className="button button-secondary header-nav-button" href="/registro">Crear cuenta</Link>
          </div>
          <Link className="button button-primary header-cta" href="/servicios">Buscar un servicio <ArrowRight aria-hidden="true" size={16} /></Link>
          <button
            aria-controls="marketplace-mobile-navigation"
            aria-expanded={menuOpen}
            aria-label={menuOpen ? "Cerrar menú" : "Abrir menú"}
            className="mobile-menu-toggle"
            onClick={() => setMenuOpen((open) => !open)}
            type="button"
          >
            {menuOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
          </button>
        </div>
      </div>
      {menuOpen && (
        <nav aria-label="Navegación móvil" className="mobile-nav" id="marketplace-mobile-navigation">
          <Link className="header-nav-button" href="/servicios" onClick={() => setMenuOpen(false)}>Buscar servicios</Link>
          <Link className="header-nav-button" href="/rutas-compartidas" onClick={() => setMenuOpen(false)}>Rutas compartidas</Link>
          <Link className="header-nav-button" href="/solicitudes" onClick={() => setMenuOpen(false)}>Mis solicitudes</Link>
          <Link className="header-nav-button" href="/login" onClick={() => setMenuOpen(false)}>Iniciar sesión</Link>
          <Link className="header-nav-button" href="/registro" onClick={() => setMenuOpen(false)}>Crear cuenta</Link>
          <Link href="/#como-funciona" onClick={() => setMenuOpen(false)}>Cómo funciona</Link>
        </nav>
      )}
    </header>
  );
}

export function MarketplaceFooter() {
  return (
    <footer className="marketplace-footer">
      <div className="marketplace-footer-inner">
        <Link aria-label="Amira, inicio" className="brand" href="/">
          <span className="brand-mark"><Truck aria-hidden="true" size={18} strokeWidth={2.2} /></span>
          <span>amira<span className="brand-period">.</span></span>
        </Link>
        <p>Amira no procesa pagos ni confirma reservas. Coordina las condiciones directamente con el prestador.</p>
        <Link className="text-link" href="/">Volver al inicio <ArrowRight aria-hidden="true" size={15} /></Link>
      </div>
    </footer>
  );
}

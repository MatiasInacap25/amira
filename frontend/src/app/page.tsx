"use client";

/* Landing page, built with taste-skill 2.5 (.claude/skills/design-taste-frontend).
   type: software (a two-sided transport marketplace)
   deal: hero triptych, nav nav-cards (re-dealt to plain words: no photograph per nav item), close close-word,
         footer footer-columns, rhythm dark-band, buttons solid, mark dots, ground sand, type geist,
         palette: Amira's own colours (start.mjs brand: ground #f4f7f7, ink #17394b, accent #b84824)
   moments: the hero collage's set change (2.8 s, with pause); counter-rolls and liquid-hover were dealt but not
            built (see the branch report). Photographs are licensed stand-ins from Wikimedia Commons. */

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ChatNotifications } from "@/components/marketplace/chat-notifications";
import { ProfileMenu, useSignOut } from "@/components/marketplace/profile-menu";
import { useNavAccountRole, useNavUserId, useProviderNavAccountScope, usesPanelNavigation } from "@/components/marketplace/site-navigation";
import { RegionCommuneSelect, type RegionCommuneValue } from "@/components/marketplace/region-commune-select";
import { getServiceTypes } from "@/lib/marketplace-api";
import { AmiraLogo } from "@/components/marketplace/amira-logo";
import { geist } from "./fonts";
import "@/styles/lp-tokens.css";
import "./landing.css";

// Presentational copy keyed by catalog slug. Names and availability come from GET /api/service-types.
const serviceCopy: Record<string, string> = {
  mudanzas: "Hogares y oficinas: muebles, electrodomésticos y cajas.",
  mercaderia: "Envíos comerciales para pymes, distribuidores y talleres.",
  "carga-compartida": "Espacio para cargas parciales en viajes con ruta publicada.",
  fletes: "Cargas puntuales, materiales y compras de gran volumen.",
  escombros: "Retiro de restos de obra y material de construcción.",
  grua: "Traslado de vehículos y movimiento de maquinaria ligera.",
};

const SERVICE_TYPES_STALE_TIME = 60 * 60 * 1000;
const COLLAGE_SET_MS = 2800;

const requests = [
  { title: "Mudanza 2 ambientes", route: "Ñuñoa → Maipú", status: "3 cotizaciones", state: "open" },
  { title: "Flete de materiales", route: "Quilicura → Lampa", status: "Cotizando", state: "work" },
  { title: "Retiro de escombros", route: "Puente Alto", status: "Coordinada", state: "done" },
  { title: "Mercadería para tienda", route: "Santiago → Rancagua", status: "1 cotización", state: "open" },
  { title: "Traslado de auto", route: "La Florida → San Bernardo", status: "Cotizando", state: "work" },
  { title: "Mudanza de oficina", route: "Providencia → Las Condes", status: "Coordinada", state: "done" },
  { title: "Flete de muebles", route: "Viña del Mar → Quilpué", status: "2 cotizaciones", state: "open" },
  { title: "Carga compartida", route: "Santiago → Concepción", status: "Cotizando", state: "work" },
  { title: "Retiro de escombros", route: "Maipú", status: "Coordinada", state: "done" },
] as const;

const benefits = [
  { title: "Tú pones el precio", text: "Propón tu tarifa en cada cotización." },
  { title: "Cada solicitud con sus datos", text: "Revisa carga, accesos y horario antes de responder." },
  { title: "Particulares y empresas", text: "Conversa con hogares, pymes y talleres de tu zona." },
  { title: "Boleta o factura, según tu servicio", text: "Indica qué documento emites antes de aceptar." },
] as const;

const faqs = [
  {
    id: "pago",
    question: "¿Cómo se paga un servicio?",
    answer: "Hoy acuerdas el medio de pago directamente con el transportista. Amira no procesa ni retiene pagos; el pago en custodia aún no está disponible.",
  },
  {
    id: "factura",
    question: "¿Puedo pedir factura para mi empresa?",
    answer: "Depende de cada transportista. Pregunta antes de aceptar la cotización si emite boleta o factura y qué datos necesita.",
  },
  {
    id: "precio",
    question: "¿Cómo se calcula una cotización?",
    answer: "Cada transportista fija su precio. Indica origen, destino, tipo de carga, medidas aproximadas, accesos y horario para recibir una cotización completa.",
  },
  {
    id: "requisitos",
    question: "¿Qué necesito para ofrecer mis servicios?",
    answer: "Crea tu cuenta como transportista, confirma tu correo y tu teléfono y registra tus vehículos. La revisión de documentos todavía no está activa.",
  },
  {
    id: "compartidos",
    question: "¿Cómo funciona un viaje compartido?",
    answer: "Un transportista publica su ruta con espacio libre y tú pides sumar tu carga. Él confirma el espacio, el tipo de carga y el desvío que acepta.",
  },
  {
    id: "danos",
    question: "¿Qué pasa si mi carga sufre daños?",
    answer: "Amira aún no media en estos casos. Guarda la cotización y los acuerdos por escrito y pregunta al transportista qué cobertura ofrece.",
  },
] as const;

function Arrow() {
  return (
    <svg aria-hidden="true" className="lp-arrow" viewBox="0 0 12 12">
      <path d="M1 6h8" />
      <path d="M4.5 2.5 8 6l-3.5 3.5" />
    </svg>
  );
}

function HeroCollage() {
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (paused || reduced) return;
    const timer = window.setInterval(() => setActive((set) => (set + 1) % 3), COLLAGE_SET_MS);
    return () => window.clearInterval(timer);
  }, [paused, reduced]);

  return (
    <div className="ly-collage lp-collage">
      <div aria-label="Una solicitud de retiro de escombros, la conversación con un transportista y un viaje con espacio libre de Santiago a Concepción" className="lp-collage__stage" role="img">
        <div aria-hidden={active !== 0} className={`lp-set${active === 0 ? " is-on" : ""}`}>
          <div className="lp-piece lp-piece--photo" style={{ left: "4%", top: "4%", width: "92%", height: "62%" }}>
            <Image alt="" fill priority sizes="(max-width: 1023px) 92vw, 600px" src="/landing/f34585920.webp" style={{ objectPosition: "40% 70%" }} />
          </div>
          <div className="lp-piece lp-card" style={{ left: "8%", top: "58%", width: "56%" }}>
            <span className="lp-card__label">Nueva solicitud</span>
            <strong>Retiro de escombros</strong>
            <dl className="lp-card__rows">
              <div><dt>Comuna</dt><dd>Puente Alto</dd></div>
              <div><dt>Carga</dt><dd>Restos de obra, 12 sacos</dd></div>
              <div><dt>Acceso</dt><dd>Calle, sin escalones</dd></div>
            </dl>
          </div>
          <div className="lp-piece lp-chip" style={{ left: "68%", top: "70%", width: "28%" }}>
            <span className="lp-dot" aria-hidden="true" /> 2 cotizaciones
          </div>
        </div>

        <div aria-hidden={active !== 1} className={`lp-set${active === 1 ? " is-on" : ""}`}>
          <div className="lp-piece lp-piece--photo" style={{ left: "44%", top: "4%", width: "52%", height: "52%" }}>
            <Image alt="" fill sizes="(max-width: 1023px) 52vw, 340px" src="/landing/f201646340.webp" />
          </div>
          <div className="lp-piece lp-card lp-chat" style={{ left: "4%", top: "10%", width: "52%" }}>
            <span className="lp-card__label">Mudanza 2 ambientes · Ñuñoa → Maipú</span>
            <p className="lp-msg lp-msg--them">Puedo ir el sábado a las 9 con dos ayudantes. ¿El edificio tiene ascensor?</p>
            <p className="lp-msg lp-msg--me">No, es un tercer piso por escalera.</p>
            <p className="lp-msg lp-msg--them">Perfecto, lo incluyo en la cotización.</p>
          </div>
          <div className="lp-piece lp-card" style={{ left: "44%", top: "62%", width: "52%" }}>
            <span className="lp-card__label">Cotización recibida</span>
            <strong>Camión 3/4 con dos ayudantes</strong>
            <span className="lp-card__line">Sábado, 9:00 · Incluye frazadas y amarras</span>
          </div>
        </div>

        <div aria-hidden={active !== 2} className={`lp-set${active === 2 ? " is-on" : ""}`}>
          <div className="lp-piece lp-card lp-route" style={{ left: "4%", top: "6%", width: "70%" }}>
            <span className="lp-card__label">Viaje con espacio libre</span>
            <div className="lp-route__cities lp-route__cities--lg"><strong>Santiago</strong><span aria-hidden="true" className="lp-route__line" /><strong>Concepción</strong></div>
            <dl className="lp-card__rows">
              <div><dt>Salida</dt><dd>Viernes, 7:00</dd></div>
              <div><dt>Espacio libre</dt><dd>Un tercio de la carga</dd></div>
            </dl>
          </div>
          <div className="lp-piece lp-card" style={{ left: "26%", top: "48%", width: "70%" }}>
            <span className="lp-card__label">Tu carga</span>
            <strong>Mercadería para tienda, 8 cajas</strong>
            <span className="lp-card__line">Retiro en Santiago · Entrega en Concepción</span>
          </div>
          <div className="lp-piece lp-chip" style={{ left: "4%", top: "80%", width: "44%" }}>
            <span className="lp-dot" aria-hidden="true" /> Espacio confirmado
          </div>
        </div>
      </div>
      {!reduced && (
        <button
          aria-label={paused ? "Reanudar la animación" : "Pausar la animación"}
          aria-pressed={paused}
          className="lp-pause"
          onClick={() => setPaused((value) => !value)}
          type="button"
        >
          {paused ? (
            <svg aria-hidden="true" viewBox="0 0 16 16"><path d="M5 3.5v9l7-4.5z" fill="currentColor" /></svg>
          ) : (
            <svg aria-hidden="true" viewBox="0 0 16 16"><path d="M5 3.5v9M11 3.5v9" stroke="currentColor" strokeLinecap="round" strokeWidth="2" /></svg>
          )}
        </button>
      )}
    </div>
  );
}

export default function HomePage() {
  const router = useRouter();
  // The landing page has no chat nav, but signed-in visitors still get the in-app chat toasts.
  const { userId, pending } = useNavUserId();
  const panelNav = usesPanelNavigation(useNavAccountRole());
  // The landing page does not mount MarketplaceHeader, so it needs the same account-scope listener here.
  useProviderNavAccountScope();
  const [menuOpen, setMenuOpen] = useState(false);
  const { signOut, signingOut, error: signOutError } = useSignOut(() => setMenuOpen(false));
  const [service, setService] = useState("");
  const [location, setLocation] = useState<RegionCommuneValue>({ regionCode: "", communeCode: "" });
  const [searchError, setSearchError] = useState("");
  const errorRef = useRef<HTMLDivElement>(null);
  const serviceTypesQuery = useQuery({
    queryKey: ["service-types"],
    queryFn: ({ signal }) => getServiceTypes(signal),
    retry: false,
    staleTime: SERVICE_TYPES_STALE_TIME,
  });
  const serviceTypes = serviceTypesQuery.data?.items ?? [];

  // The dealt moment (counter-rolls) runs from taste-skill's moment modules, served as plain files from /public/moments.
  useEffect(() => {
    const main = document.getElementById("contenido");
    if (!main) return;
    let cancelled = false;
    let api: { mountAll: (root: Element) => unknown; unmountAll: (root: Element) => void } | null = null;
    const url = "/moments/moments.js";
    import(/* webpackIgnore: true */ /* turbopackIgnore: true */ url)
      .then((module) => { if (!cancelled) { api = module; module.mountAll(main); } })
      .catch(() => { /* the figures stand without the script */ });
    return () => { cancelled = true; api?.unmountAll(main); };
  }, []);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setMenuOpen(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [menuOpen]);

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!service) {
      setSearchError("Elige un tipo de servicio para buscar.");
      requestAnimationFrame(() => errorRef.current?.focus());
      return;
    }

    setSearchError("");
    const params = new URLSearchParams({ serviceType: service });
    if (location.regionCode) params.set("regionCode", location.regionCode);
    if (location.communeCode) params.set("communeCode", location.communeCode);
    router.push(`/servicios?${params.toString()}`);
  }

  function selectService(serviceSlug: string) {
    setService(serviceSlug);
    setSearchError("");
    document.getElementById("service-type")?.focus();
  }

  const closeMenu = () => setMenuOpen(false);

  return (
    <>
      <header className={`site-header nav lp lp-nav ${geist.variable}`}>
        <div className="wrap lp-wrap lp-nav__bar">
          <a className="lp-skip" href="#contenido">Ir al contenido</a>
          <a aria-label="Amira, inicio" className="nav__logo lp-logo" href="#inicio"><AmiraLogo /></a>
          <nav aria-label="Navegación principal" className="lp-nav__links">
            {!panelNav && <Link href="/servicios">Buscar servicios</Link>}
            {!panelNav && <Link href="/rutas-compartidas">Rutas compartidas</Link>}
            {!panelNav && <a href="#como-funciona">Cómo funciona</a>}
            <a href="#transportistas">Transportistas</a>
          </nav>
          <div className="nav__actions lp-nav__actions">
            {!pending && (userId ? <ProfileMenu /> : (
              <>
                <Link className="lp-nav__plain" href="/login">Iniciar sesión</Link>
                <Link className="lp-nav__plain" href="/registro">Crear cuenta</Link>
              </>
            ))}
            <Link className="btn lp-btn lp-btn--primary lp-nav__cta" href="/registro?intent=provider">Ofrecer mis servicios</Link>
            <button
              aria-controls="lp-sheet"
              aria-expanded={menuOpen}
              aria-label={menuOpen ? "Cerrar menú" : "Abrir menú"}
              className="nav__toggle lp-nav__toggle"
              onClick={() => setMenuOpen((open) => !open)}
              type="button"
            >
              <svg aria-hidden="true" viewBox="0 0 18 18">
                {menuOpen ? <path d="M4 4l10 10M14 4 4 14" /> : <path d="M2 6h14M2 12h14" />}
              </svg>
            </button>
          </div>
        </div>
        {menuOpen && (
          <nav aria-label="Navegación móvil" className="lp-sheet" id="lp-sheet">
            {!panelNav && <Link href="/servicios" onClick={closeMenu}>Buscar servicios</Link>}
            {!panelNav && <Link href="/rutas-compartidas" onClick={closeMenu}>Rutas compartidas</Link>}
            {!panelNav && <a href="#como-funciona" onClick={closeMenu}>Cómo funciona</a>}
            <a href="#empresas" onClick={closeMenu}>Empresas</a>
            <a href="#transportistas" onClick={closeMenu}>Transportistas</a>
            {!pending && (userId ? (
              <>
                <Link href="/cuenta/perfil" onClick={closeMenu}>Configuración del perfil</Link>
                <button disabled={signingOut} onClick={signOut} type="button">{signingOut ? "Cerrando sesión…" : "Cerrar sesión"}</button>
                {signOutError && <p className="lp-sheet__error" role="alert">{signOutError}</p>}
              </>
            ) : (
              <>
                <Link href="/login" onClick={closeMenu}>Iniciar sesión</Link>
                <Link href="/registro" onClick={closeMenu}>Crear cuenta</Link>
              </>
            ))}
            <Link href="/registro?intent=provider" onClick={closeMenu}>Registrar mi vehículo</Link>
            <Link className="btn lp-btn lp-btn--primary" href="/registro?intent=provider" onClick={closeMenu}>Ofrecer mis servicios</Link>
          </nav>
        )}
      </header>

      <main className={`lp ${geist.variable}`} id="contenido">
        <section aria-labelledby="hero-title" className="lp-sec lp-hero" data-enter id="inicio">
          <div className="wrap lp-wrap lp-hero__wrap">
            <div className="hero-text lp-grid lp-hero__grid">
              <div className="lp-hero__text">
                <h1 id="hero-title">Transporte de carga en todo Chile</h1>
                <p className="hero__lead lp-hero__lead">5 servicios: mudanzas, fletes, mercadería, escombros y grúas. Publica qué necesitas mover y compara cotizaciones de transportistas independientes.</p>
              </div>
              <HeroCollage />
              <div className="lp-hero__cta">
                <a className="btn lp-btn lp-btn--primary" href="#buscar">Buscar un servicio<Arrow /></a>
              </div>
            </div>
          </div>
        </section>

        <section aria-labelledby="search-title" className="lp-sec" id="buscar">
          <div className="wrap lp-wrap">
            <h2 id="search-title">Servicios de carga. <span className="lp-muted">Elige uno y tu comuna.</span></h2>
            <div className="lp-grid lp-search">
              <ul aria-label="Tipos de servicio" className="lp-services">
                {serviceTypes.map(({ id, slug, name }) => (
                  <li key={id}>
                    <button
                      aria-label={serviceCopy[slug] ? `${name}: ${serviceCopy[slug]}` : name}
                      aria-pressed={service === slug}
                      className="lp-service"
                      onClick={() => selectService(slug)}
                      type="button"
                    >
                      <span className="lp-service__name">{name}</span>
                      <span className="lp-service__text">{serviceCopy[slug] ?? ""}</span>
                      <span aria-hidden="true" className="lp-service__go"><Arrow /></span>
                    </button>
                  </li>
                ))}
              </ul>
              <form aria-label="Buscar un servicio de transporte" className="lp-form" noValidate onSubmit={submitSearch}>
                {searchError && (
                  <div className="lp-form__alert" ref={errorRef} role="alert" tabIndex={-1}>
                    <p id="search-error"><a href="#service-type">{searchError}</a></p>
                  </div>
                )}
                <label className="marketplace-field" htmlFor="service-type">
                  <span>Tipo de servicio</span>
                  <select
                    aria-describedby={searchError ? "search-error" : undefined}
                    aria-invalid={searchError && !service ? "true" : undefined}
                    id="service-type"
                    onChange={(event) => { setService(event.target.value); setSearchError(""); }}
                    value={service}
                  >
                    <option value="">Elige un servicio</option>
                    {serviceTypes.map((item) => <option key={item.id} value={item.slug}>{item.name}</option>)}
                  </select>
                </label>
                <RegionCommuneSelect idPrefix="home-search-location" onChange={setLocation} optional value={location} />
                <button className="btn lp-btn lp-btn--primary lp-btn--full" type="submit">Buscar servicio<Arrow /></button>
                <p className="lp-form__note">¿Tienes camión o camioneta? <a className="lp-link" href="#transportistas">Registra tu vehículo</a></p>
              </form>
            </div>
          </div>
        </section>

        <section aria-labelledby="how-title" className="lp-sec" id="como-funciona">
          <div className="wrap lp-wrap lp-howwrap">
            <div className="lp-grid lp-head">
              <h2 id="how-title">Tus solicitudes y sus cotizaciones, en un solo lugar</h2>
              <p>Publicas qué mover, desde dónde y cómo es el acceso. Cada transportista responde con su cotización y conversas con él antes de aceptar. <Link className="lp-link" href="/servicios">Ver transportistas publicados</Link></p>
            </div>
            <div aria-label="La lista de solicitudes de un cliente junto a una mudanza abierta con su conversación y dos cotizaciones" className="ui app fill lp-app" role="img">
              <div className="lp-app__bar"><span className="lp-app__dots" aria-hidden="true"><i /><i /><i /></span><span>amira <i>/</i> <b>Mis solicitudes</b></span></div>
              <div className="lp-app__body">
                <div className="app__pane app__pane--list lp-app__list">
                <ul data-ui="window">
                  {requests.map((request, index) => (
                    <li className={index === 0 ? "is-open" : undefined} key={`${request.title}-${request.route}`}>
                      <span className="lp-app__title">{request.title}</span>
                      <span className="lp-app__route">{request.route}</span>
                      <span className={`lp-app__state lp-app__state--${request.state}`}>{request.status}</span>
                    </li>
                  ))}
                </ul>
                </div>
                <div className="app__pane app__pane--open lp-app__open">
                  <div className="lp-app__inner" data-ui="thread">
                  <div className="lp-app__head">
                    <strong>Mudanza 2 ambientes</strong>
                    <span>Ñuñoa → Maipú · Sábado en la mañana · Tercer piso sin ascensor</span>
                  </div>
                  <div className="lp-quote">
                    <div><strong>Camión 3/4 con dos ayudantes</strong><span>Incluye frazadas, amarras y desarme de camas</span></div>
                    <span className="lp-quote__btn">Aceptar</span>
                  </div>
                  <div className="lp-quote">
                    <div><strong>Camión con rampa</strong><span>Un ayudante · Puede llegar a las 8:00</span></div>
                    <span className="lp-quote__btn">Aceptar</span>
                  </div>
                  <div className="lp-app__thread">
                    <p className="lp-msg lp-msg--them">¿Hay estacionamiento frente al edificio para el camión?</p>
                    <p className="lp-msg lp-msg--me">Sí, en la calle. Te dejo el número del conserje en la solicitud.</p>
                    <p className="lp-msg lp-msg--them">Gracias. Confirmo la hora el viernes.</p>
                  </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section aria-labelledby="carriers-title" className="lp-sec lp-dark" id="transportistas">
          <span aria-hidden="true" className="lp-anchor" id="empresas" />
          <div className="wrap lp-wrap lp-grid lp-split">
            <div className="lp-split__text">
              <h2 id="carriers-title">Para transportistas con camión o camioneta. <span className="lp-muted">Tú decides qué trabajos tomar.</span></h2>
              <ul className="lp-benefits">
                {benefits.map(({ title, text }) => <li key={title}><strong>{title}</strong><span>{text}</span></li>)}
              </ul>
              <Link className="btn lp-btn lp-btn--light" href="/registro?intent=provider">Registrar mi vehículo<Arrow /></Link>
            </div>
            <div className="lp-split__media">
              <Image alt="Un camión rojo con barandas y carga sobre la plataforma, estacionado en un terreno de tierra" fill sizes="(max-width: 1023px) 100vw, 960px" src="/landing/f89119366.webp" style={{ objectPosition: "70% 55%" }} />
            </div>
          </div>
        </section>

        <section aria-labelledby="shared-title" className="lp-sec" id="rutas">
          <div className="wrap lp-wrap lp-grid lp-split">
            <div className="lp-split__text">
              <h2 id="shared-title">Viajes compartidos con espacio libre</h2>
              <p className="lp-lead">Cuando un transportista ya tiene un viaje programado y le sobra espacio, tu carga parcial puede ir en ese trayecto. Él confirma el espacio, el tipo de carga y el desvío que acepta.</p>
              <Link className="btn lp-btn lp-btn--secondary" href="/rutas-compartidas">Ver viajes compartidos<Arrow /></Link>
              <div className="lp-stats" data-moment="counter-rolls">
                <div><p className="t-stat lp-stat">16</p><p className="lp-stat__label">regiones con búsqueda por comuna</p></div>
                <div><p className="t-stat lp-stat">346</p><p className="lp-stat__label">comunas para origen y destino</p></div>
              </div>
            </div>
            <div className="lp-panel">
              <div className="lp-trip">
                <span className="lp-card__label">Viaje publicado</span>
                <div className="lp-route__cities lp-trip__cities"><strong>Santiago</strong><span aria-hidden="true" className="lp-route__line" /><strong>Concepción</strong></div>
                <dl className="lp-card__rows">
                  <div><dt>Salida</dt><dd>Viernes, 7:00</dd></div>
                  <div><dt>Espacio libre</dt><dd>Un tercio de la carga</dd></div>
                  <div><dt>Desvío</dt><dd>Hasta 10 km de la ruta 5</dd></div>
                  <div><dt>Vehículo</dt><dd>Camión 3/4 cerrado</dd></div>
                </dl>
                <span className="lp-quote__btn lp-trip__btn">Pedir espacio</span>
              </div>
            </div>
          </div>
        </section>

        <section aria-labelledby="faq-title" className="lp-sec" id="faq">
          <div className="wrap lp-wrap lp-grid lp-faqgrid">
            <div className="lp-faq__intro">
              <h2 id="faq-title">Preguntas frecuentes</h2>
              <p className="lp-lead">Lo que puedes hacer hoy en Amira y lo que aún no está disponible.</p>
              <div aria-label="Una pregunta al transportista dentro de una solicitud, con su respuesta" className="ui lp-card lp-chat lp-faq__mock" role="img">
                <span className="lp-card__label">Chat de la solicitud</span>
                <p className="lp-msg lp-msg--me">¿Puede emitir factura a nombre de mi empresa?</p>
                <p className="lp-msg lp-msg--them">Sí, envíeme el RUT y la razón social antes del viaje.</p>
              </div>
              <Link className="btn lp-btn lp-btn--secondary" href="/registro">Crear una cuenta<Arrow /></Link>
            </div>
            <div className="lp-faq">
              {faqs.map(({ id, question, answer }) => (
                <div className="lp-faq__item" id={id} key={id}>
                  <h3>{question}</h3>
                  <p>{answer}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>

      <footer aria-labelledby="close-title" className={`footer closing lp lp-footer ${geist.variable}`} id="ayuda">
        <div className="wrap lp-wrap">
          <div className="lp-close">
            <div className="lp-close__head">
              <div>
                <h2 id="close-title">Encuentra transportista en tu comuna</h2>
                <p className="lp-lead">Compara cotizaciones y conversa antes de aceptar.</p>
              </div>
              <a className="btn lp-btn lp-btn--primary" href="#buscar">Buscar un servicio<Arrow /></a>
            </div>
            <p aria-hidden="true" className="lp-close__word">amira</p>
          </div>
          <div className="closing__links lp-footer__bottom">
          <div className="lp-footer__links">
            <div className="lp-footer__brand">
              <a aria-label="Amira, volver al inicio" className="nav__logo lp-logo" href="#inicio"><AmiraLogo /></a>
              <p>Transporte de carga entre personas, pymes y transportistas.</p>
            </div>
            <div className="lp-footer__col">
              <h3>Explora</h3>
              <ul>
                <li><Link href="/servicios">Servicios</Link></li>
                <li><Link href="/rutas-compartidas">Rutas compartidas</Link></li>
                <li><a href="#como-funciona">Cómo funciona</a></li>
              </ul>
            </div>
            <div className="lp-footer__col">
              <h3>Transportistas</h3>
              <ul>
                <li><a href="#transportistas">Para transportistas</a></li>
                <li><Link href="/registro?intent=provider">Ofrecer mis servicios</Link></li>
                <li><a href="#empresas">Empresas</a></li>
              </ul>
            </div>
            <div className="lp-footer__col">
              <h3>Ayuda</h3>
              <ul>
                <li><a href="#faq">Preguntas frecuentes</a></li>
                <li><a href="#pago">Pagos</a></li>
              </ul>
            </div>
          </div>
          <div className="lp-footer__legal">
            <span>© 2026 Amira</span>
            <Link className="lp-credits" href="/creditos">Fotografías vía Wikimedia Commons</Link>
          </div>
          </div>
        </div>
      </footer>
      <ChatNotifications userId={userId} />
    </>
  );
}

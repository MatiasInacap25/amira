"use client";

import {
  ArrowRight,
  ArrowUpRight,
  Box,
  Check,
  ChevronDown,
  CircleHelp,
  ClipboardList,
  FileText,
  MapPin,
  Menu,
  MessageCircle,
  Package,
  Shield,
  Truck,
  UsersRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRef, useState, type FormEvent } from "react";

const services = [
  {
    id: "mudanza",
    name: "Mudanzas",
    description: "Hogares y oficinas. Muebles, electrodomésticos y cajas.",
    tag: "Hogar y oficina",
    icon: Box,
  },
  {
    id: "mercaderia",
    name: "Transporte de mercadería",
    description: "Envíos comerciales para pymes, distribuidores y talleres.",
    tag: "Para empresas",
    icon: Package,
  },
  {
    id: "flete",
    name: "Fletes y traslados",
    description: "Cargas puntuales, materiales y compras de gran volumen.",
    tag: "Carga general",
    icon: Truck,
  },
  {
    id: "escombros",
    name: "Recolección de escombros",
    description: "Retiro de restos de obra y material de construcción.",
    tag: "Obra y remodelación",
    icon: ClipboardList,
  },
  {
    id: "grua",
    name: "Servicios de grúa",
    description: "Traslado de vehículos y movimiento de maquinaria ligera.",
    tag: "Asistencia y carga",
    icon: ArrowUpRight,
  },
] as const;

const steps = [
  {
    number: "01",
    title: "Publica tu necesidad",
    description: "Cuéntanos qué necesitas mover, desde dónde y con qué condiciones de acceso.",
    icon: ClipboardList,
  },
  {
    number: "02",
    title: "Coordina los detalles",
    description: "Compara lo que incluye el servicio y resuelve dudas directamente con el prestador.",
    icon: MessageCircle,
  },
  {
    number: "03",
    title: "Acuerda las condiciones",
    description: "Antes de confirmar, deja claros el precio, el horario y la forma de pago entre ambas partes.",
    icon: FileText,
  },
  {
    number: "04",
    title: "Recibe tu carga",
    description: "Coordina la entrega con el transportista y mantén sus datos de contacto a mano.",
    icon: Check,
  },
] as const;

const faqs = [
  {
    question: "¿Cómo funciona el pago protegido en Amira?",
    answer:
      "El pago en custodia aún no está disponible en esta etapa. Antes de contratar, confirma directamente con el prestador el medio de pago y las condiciones del servicio. Amira no procesa ni retiene fondos actualmente.",
  },
  {
    question: "¿Puedo solicitar factura para mi empresa o negocio?",
    answer:
      "Depende de cada prestador. Pregunta antes de aceptar la cotización si puede emitir factura o boleta y qué datos necesita para hacerlo.",
  },
  {
    question: "¿Cómo se calculan las cotizaciones de los fletes?",
    answer:
      "Cada prestador determina su precio. Comparte origen, destino, tipo de carga, medidas aproximadas, accesos y horario para que pueda cotizar con información completa.",
  },
  {
    question: "¿Qué requisitos necesito para ofrecer mis servicios?",
    answer:
      "El registro de transportistas todavía no está habilitado. Cuando se publique, los requisitos y el proceso de revisión se informarán aquí antes de solicitar datos personales o documentos.",
  },
  {
    question: "¿Cómo funcionan los viajes compartidos o de retorno?",
    answer:
      "Este ejemplo es ilustrativo; no hay espacios de carga disponibles para reservar desde esta página. Si se habilita la función, cada transportista confirmará espacio, compatibilidad de carga, desvíos y condiciones.",
  },
  {
    question: "¿Qué ocurre si la carga sufre daños o el servicio no se completa?",
    answer:
      "Aún no hay una mediación operativa de Amira para estos casos. Conserva la cotización y los acuerdos por escrito y consulta directamente con el prestador qué cobertura o procedimiento aplica a su servicio.",
  },
] as const;

function TruckIllustration() {
  return (
    <svg
      aria-hidden="true"
      className="truck-illustration"
      viewBox="0 0 720 530"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient id="sky" x1="82" y1="36" x2="622" y2="492" gradientUnits="userSpaceOnUse">
          <stop stopColor="#E6F0F4" />
          <stop offset="1" stopColor="#D8E2DA" />
        </linearGradient>
        <linearGradient id="truckCab" x1="328" y1="258" x2="594" y2="408" gradientUnits="userSpaceOnUse">
          <stop stopColor="#F7FAF7" />
          <stop offset="1" stopColor="#C7D7D3" />
        </linearGradient>
      </defs>
      <rect x="35" y="22" width="650" height="476" rx="28" fill="url(#sky)" />
      <circle cx="562" cy="111" r="35" fill="#F6C873" />
      <path d="M35 330C139 278 198 327 285 285C391 234 456 282 532 254C587 234 631 246 685 226V498H35V330Z" fill="#C7D8D0" />
      <path d="M35 377C142 332 230 376 322 342C448 295 523 348 685 302V498H35V377Z" fill="#AEC4BB" />
      <path d="M72 410H644" stroke="#879F96" strokeWidth="4" strokeLinecap="round" />
      <path d="M114 324L201 257H416V397H114V324Z" fill="#E9B75F" />
      <path d="M128 327L207 269H405V386H128V327Z" fill="#F7D78C" />
      <path d="M416 298H520L580 347V397H416V298Z" fill="url(#truckCab)" />
      <path d="M431 311H513L555 350H431V311Z" fill="#55727C" />
      <path d="M531 363H569V380H531V363Z" fill="#FAF3DD" />
      <rect x="96" y="388" width="492" height="18" rx="9" fill="#344D54" />
      <circle cx="192" cy="407" r="34" fill="#243A41" />
      <circle cx="192" cy="407" r="15" fill="#DDE4E0" />
      <circle cx="485" cy="407" r="34" fill="#243A41" />
      <circle cx="485" cy="407" r="15" fill="#DDE4E0" />
      <path d="M282 322V280M332 322V280" stroke="#D99E42" strokeWidth="6" strokeLinecap="round" />
      <path d="M76 445C132 430 189 432 240 446" stroke="#8AA098" strokeWidth="5" strokeLinecap="round" />
      <rect x="69" y="64" width="204" height="56" rx="16" fill="white" fillOpacity=".92" />
      <path d="M93 92H124" stroke="#DB7A41" strokeWidth="4" strokeLinecap="round" />
      <path d="M93 103H144" stroke="#A9BDB7" strokeWidth="4" strokeLinecap="round" />
      <circle cx="164" cy="92" r="11" fill="#E7B152" />
      <path d="M164 87V97M159 92H169" stroke="white" strokeWidth="2" strokeLinecap="round" />
      <circle cx="620" cy="168" r="27" fill="white" fillOpacity=".8" />
      <path d="M610 168L618 176L632 160" stroke="#5D7C6B" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Brand() {
  return (
    <a aria-label="Amira, inicio" className="brand" href="#inicio">
      <span className="brand-mark"><Truck aria-hidden="true" size={20} strokeWidth={2.2} /></span>
      <span>amira<span className="brand-period">.</span></span>
    </a>
  );
}

export default function HomePage() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [service, setService] = useState("");
  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [searchError, setSearchError] = useState("");
  const [searchSubmitted, setSearchSubmitted] = useState(false);
  const [demoNotice, setDemoNotice] = useState("");
  const errorRef = useRef<HTMLDivElement>(null);

  const destinationOptional = service === "escombros";

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSearchSubmitted(false);
    if (!service) {
      setSearchError("Selecciona un servicio para continuar.");
      requestAnimationFrame(() => errorRef.current?.focus());
      return;
    }
    if (!origin.trim()) {
      setSearchError("Ingresa una comuna o ciudad de retiro.");
      requestAnimationFrame(() => errorRef.current?.focus());
      return;
    }
    if (!destinationOptional && !destination.trim()) {
      setSearchError("Ingresa una comuna o ciudad de entrega.");
      requestAnimationFrame(() => errorRef.current?.focus());
      return;
    }

    setSearchError("");
    setSearchSubmitted(true);
  }

  function selectService(serviceId: string) {
    setService(serviceId);
    if (serviceId === "escombros") setDestination("");
    setSearchError("");
    setSearchSubmitted(false);
    document.getElementById("buscar")?.scrollIntoView({ behavior: "smooth", block: "center" });
    document.getElementById("service-type")?.focus({ preventScroll: true });
  }

  function showDemoNotice(message: string) {
    setDemoNotice(message);
  }

  return (
    <>
      <header className="site-header">
        <div className="header-inner">
          <Brand />
          <nav aria-label="Navegación principal" className="desktop-nav">
          <Link className="button button-secondary header-nav-button" href="/servicios">Buscar servicios</Link>
          <Link className="button button-secondary header-nav-button" href="/rutas-compartidas">Rutas compartidas</Link>
            <a href="#como-funciona">Cómo funciona</a>
            <a href="#empresas">Empresas</a>
            <a href="#transportistas">Para transportistas</a>
          </nav>
          <div className="header-actions">
            <Link className="login-link" href="/login">Iniciar sesión</Link>
            <Link className="login-link home-register-link" href="/registro">Crear cuenta</Link>
            <Link className="button button-primary header-cta" href="/registro?intent=provider">Ofrecer mis servicios <ArrowUpRight aria-hidden="true" size={16} /></Link>
            <button
              aria-label={mobileMenuOpen ? "Cerrar menú" : "Abrir menú"}
              aria-expanded={mobileMenuOpen}
              aria-controls="mobile-navigation"
              className="mobile-menu-toggle"
              onClick={() => setMobileMenuOpen((open) => !open)}
              type="button"
            >
              {mobileMenuOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
            </button>
          </div>
        </div>
        {mobileMenuOpen && (
          <nav aria-label="Navegación móvil" className="mobile-nav" id="mobile-navigation">
            <Link className="header-nav-button" href="/servicios" onClick={() => setMobileMenuOpen(false)}>Buscar servicios</Link>
            <Link className="header-nav-button" href="/rutas-compartidas" onClick={() => setMobileMenuOpen(false)}>Rutas compartidas</Link>
            <a href="#como-funciona" onClick={() => setMobileMenuOpen(false)}>Cómo funciona</a>
            <a href="#empresas" onClick={() => setMobileMenuOpen(false)}>Empresas</a>
            <a href="#transportistas" onClick={() => setMobileMenuOpen(false)}>Para transportistas</a>
            <Link href="/login" onClick={() => setMobileMenuOpen(false)}>Iniciar sesión</Link>
            <Link href="/registro" onClick={() => setMobileMenuOpen(false)}>Crear cuenta</Link>
            <a href="#buscar" onClick={() => setMobileMenuOpen(false)}>Solicitar un servicio</a>
            <Link href="/registro?intent=provider" onClick={() => setMobileMenuOpen(false)}>Registrar mi vehículo</Link>
          </nav>
        )}
      </header>

      <main id="contenido">
        <section aria-labelledby="hero-title" className="hero section-wrap" id="inicio">
          <div className="hero-copy">
            <p className="eyebrow"><span className="eyebrow-dot" /> Una red para mover lo que importa</p>
            <h1 id="hero-title">El servicio que necesitas, con el <span>camión adecuado.</span></h1>
            <p className="hero-description">Conecta con conductores independientes y empresas de transporte para mudanzas, fletes, mercadería, escombros y grúas en todo Chile.</p>
            <div className="hero-actions">
              <a className="button button-primary" href="#buscar">Buscar un servicio <ArrowRight aria-hidden="true" size={17} /></a>
              <Link className="text-link" href="/registro?intent=provider">Quiero transportar <ArrowUpRight aria-hidden="true" size={16} /></Link>
            </div>
            <div className="hero-note"><UsersRound aria-hidden="true" size={16} /><span>Personas y negocios conectando directamente</span></div>
          </div>
          <div aria-label="Ilustración de un camión de carga independiente en ruta" className="hero-art-wrap" role="img">
            <TruckIllustration />
            <div className="hero-art-caption"><span className="caption-dot" /> Vehículos independientes, distintas necesidades</div>
            <div className="hero-art-chip"><MapPin aria-hidden="true" size={14} /> En todo Chile</div>
          </div>
          <form aria-label="Buscar un servicio de transporte" className="search-card" id="buscar" onSubmit={submitSearch} noValidate>
            <div className="search-heading">
              <div><span className="search-kicker">ENCUENTRA TU SERVICIO</span><h2>¿Qué necesitas mover?</h2></div>
              <span aria-hidden="true" className="search-heading-icon"><Truck size={20} /></span>
            </div>
            {searchError && (
              <div aria-labelledby="search-error-title" className="form-alert" ref={errorRef} role="alert" tabIndex={-1}>
                <span aria-hidden="true">!</span><p id="search-error-title"><a href={searchError.includes("servicio") ? "#service-type" : searchError.includes("retiro") ? "#origin" : "#destination"}>{searchError}</a></p>
              </div>
            )}
            <div className="search-fields">
              <label className="field field-service" htmlFor="service-type">
                <span>Tipo de servicio</span>
                <span className="select-wrap"><select aria-describedby={searchError.includes("servicio") ? "search-error-title" : undefined} aria-invalid={searchError && !service ? "true" : undefined} id="service-type" onChange={(event) => { setService(event.target.value); if (event.target.value === "escombros") setDestination(""); setSearchError(""); setSearchSubmitted(false); }} value={service}>
                  <option value="">Selecciona una categoría</option>
                  {services.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select><ChevronDown aria-hidden="true" size={16} /></span>
              </label>
              <label className="field" htmlFor="origin">
                <span>Origen</span>
                <span className="input-wrap"><MapPin aria-hidden="true" size={16} /><input aria-describedby={searchError.includes("retiro") ? "search-error-title" : undefined} aria-invalid={searchError.includes("retiro") ? "true" : undefined} autoComplete="address-level2" id="origin" onChange={(event) => setOrigin(event.target.value)} placeholder="Comuna o ciudad" value={origin} /></span>
              </label>
              <label className="field" htmlFor="destination">
                <span>Destino <span className="optional-label">{destinationOptional ? "Opcional" : ""}</span></span>
                <span className="input-wrap"><MapPin aria-hidden="true" size={16} /><input aria-describedby={searchError.includes("entrega") ? "search-error-title" : undefined} aria-invalid={searchError.includes("entrega") ? "true" : undefined} autoComplete="off" disabled={destinationOptional} id="destination" onChange={(event) => setDestination(event.target.value)} placeholder={destinationOptional ? "No se requiere destino" : "Comuna o ciudad"} value={destination} /></span>
              </label>
              <button className="button button-primary search-submit" type="submit">Buscar servicio <ArrowRight aria-hidden="true" size={17} /></button>
            </div>
            {searchSubmitted && (
              <div aria-live="polite" className="search-results" role="status">
                <div className="results-title"><span className="results-icon"><Check aria-hidden="true" size={17} /></span><div><strong>Vista de demostración</strong><span>Solicitud de {services.find((item) => item.id === service)?.name.toLocaleLowerCase()} desde {origin.trim()}{destination.trim() && !destinationOptional ? ` hacia ${destination.trim()}` : ""}.</span></div></div>
                <p>Sin prestadores reales conectados todavía. Esta búsqueda no envía tus datos ni solicita cotizaciones.</p>
                <a className="text-link" href="#prestadores">Conocer ejemplos de perfiles <ArrowRight aria-hidden="true" size={15} /></a>
              </div>
            )}
            <p className="search-footnote">¿Tienes un camión o camioneta de carga? <a href="#transportistas">Registra tu vehículo y encuentra nuevos clientes aquí <ArrowUpRight aria-hidden="true" size={13} /></a></p>
          </form>
        </section>

        <section aria-label="Lo que distingue a Amira" className="value-strip section-wrap">
          <div><span className="value-icon"><UsersRound aria-hidden="true" size={19} /></span><span>Personas y pymes<small>Para clientes y negocios</small></span></div>
          <span className="value-divider" />
          <div><span className="value-icon"><Truck aria-hidden="true" size={19} /></span><span>Oferta independiente<small>Prestadores con sus vehículos</small></span></div>
          <span className="value-divider" />
          <div><span className="value-icon"><MapPin aria-hidden="true" size={19} /></span><span>Desde tu comuna<small>Servicios a lo largo de Chile</small></span></div>
        </section>

        <section aria-labelledby="services-title" className="content-section section-wrap" id="servicios">
          <div className="section-heading">
            <div><p className="eyebrow">SOLUCIONES PARA TU CARGA</p><h2 id="services-title">Un servicio para cada necesidad</h2></div>
            <p>Elige el tipo de traslado y encuentra el vehículo indicado para tu carga.</p>
            <Link className="text-link" href="/servicios">Explorar servicios <ArrowRight aria-hidden="true" size={15} /></Link>
          </div>
          <div className="service-grid">
            {services.map(({ id, name, description, tag, icon: Icon }, index) => (
              <button aria-label={`${name}: ${description}`} className={`service-card service-card-${index + 1}`} key={id} onClick={() => selectService(id)} type="button">
                <span className="service-icon"><Icon aria-hidden="true" size={22} strokeWidth={1.8} /></span>
                <span className="service-tag">{tag}</span>
                <strong>{name}</strong>
                <span className="service-description">{description}</span>
                <span aria-hidden="true" className="service-arrow"><ArrowUpRight size={17} /></span>
              </button>
            ))}
          </div>
        </section>

        <section aria-labelledby="providers-title" className="provider-section">
          <div className="section-wrap">
            <div className="section-heading provider-heading" id="prestadores">
              <div><p className="eyebrow">UNA RED ABIERTA</p><h2 id="providers-title">Conoce el tipo de prestador<br className="desktop-break" /> que puedes encontrar</h2></div>
              <div className="demo-disclosure"><span className="demo-dot" />Perfiles de ejemplo, no ofertas activas</div>
            </div>
            <div className="provider-grid">
              <article className="provider-card">
                <div className="provider-vehicle provider-vehicle-amber"><Truck aria-hidden="true" size={45} strokeWidth={1.35} /></div>
                <div className="provider-card-body"><span className="sample-label">EJEMPLO ILUSTRATIVO</span><h3>Transportista independiente</h3><p>Camión 3/4 <span aria-hidden="true">·</span> Carga general y mudanzas</p><div className="provider-location"><MapPin aria-hidden="true" size={14} /> Región Metropolitana</div><button className="provider-link" onClick={() => showDemoNotice("Los perfiles de transportistas son ejemplos ilustrativos; aún no hay perfiles reales para consultar.")} type="button">Ver perfil y cotizar <ArrowUpRight aria-hidden="true" size={15} /></button></div>
              </article>
              <article className="provider-card">
                <div className="provider-vehicle provider-vehicle-green"><Truck aria-hidden="true" size={45} strokeWidth={1.35} /></div>
                <div className="provider-card-body"><span className="sample-label">EJEMPLO ILUSTRATIVO</span><h3>Servicio local para pymes</h3><p>Camioneta de carga <span aria-hidden="true">·</span> Mercadería y fletes</p><div className="provider-location"><MapPin aria-hidden="true" size={14} /> Valparaíso y alrededores</div><button className="provider-link" onClick={() => showDemoNotice("Los perfiles de transportistas son ejemplos ilustrativos; aún no hay perfiles reales para consultar.")} type="button">Ver perfil y cotizar <ArrowUpRight aria-hidden="true" size={15} /></button></div>
              </article>
              <article className="provider-card">
                <div className="provider-vehicle provider-vehicle-blue"><Truck aria-hidden="true" size={45} strokeWidth={1.35} /></div>
                <div className="provider-card-body"><span className="sample-label">EJEMPLO ILUSTRATIVO</span><h3>Servicio de transporte regional</h3><p>Camión con tolva <span aria-hidden="true">·</span> Materiales y escombros</p><div className="provider-location"><MapPin aria-hidden="true" size={14} /> RM y Región de Valparaíso</div><button className="provider-link" onClick={() => showDemoNotice("Los perfiles de transportistas son ejemplos ilustrativos; aún no hay perfiles reales para consultar.")} type="button">Ver perfil y cotizar <ArrowUpRight aria-hidden="true" size={15} /></button></div>
              </article>
            </div>
          </div>
        </section>

        <section aria-labelledby="steps-title" className="content-section section-wrap how-section" id="como-funciona">
          <div className="section-heading">
            <div><p className="eyebrow">CLARO DESDE EL PRINCIPIO</p><h2 id="steps-title">Así puedes organizar tu traslado</h2></div>
            <p>Conversa directamente y deja cada condición acordada antes de confirmar.</p>
          </div>
          <div className="steps-grid">
            {steps.map(({ number, title, description, icon: Icon }) => (
              <article className="step-card" key={number}><div className="step-topline"><span>{number}</span><Icon aria-hidden="true" size={22} strokeWidth={1.7} /></div><h3>{title}</h3><p>{description}</p></article>
            ))}
          </div>
          <aside className="payment-note" id="pago"><span className="payment-note-icon"><Shield aria-hidden="true" size={19} /></span><p><strong>Sobre los pagos:</strong> el pago protegido o en custodia está planificado, pero todavía no está disponible. Amira no recibe ni retiene pagos; acuerda el medio de pago directamente con el prestador.</p><a href="#faq">Conoce más <ArrowRight aria-hidden="true" size={14} /></a></aside>
        </section>

        <section aria-labelledby="carriers-title" className="carrier-section" id="transportistas">
          <div className="section-wrap carrier-layout">
            <span aria-hidden="true" className="anchor-target" id="empresas" />
            <div className="carrier-visual"><div className="carrier-orbit carrier-orbit-one" /><div className="carrier-orbit carrier-orbit-two" /><div className="carrier-illustration"><Truck aria-hidden="true" size={110} strokeWidth={1.15} /></div><div className="carrier-route"><span className="route-dot" /><span className="route-line" /><MapPin aria-hidden="true" size={18} /></div><span className="carrier-tag">Tu ruta. Tu negocio.</span></div>
            <div className="carrier-copy"><p className="eyebrow">PARA TRANSPORTISTAS Y EMPRESAS</p><h2 id="carriers-title">Tu camión y tu trabajo, bajo tus propias condiciones.</h2><p className="carrier-intro">Súmate a la red donde tú tienes el control: muestra tus vehículos, conversa con clientes y aprovecha nuevas oportunidades.</p>
              <ul className="benefit-list">
                <li><span><Check aria-hidden="true" size={15} /></span><p><strong>Autonomía tarifaria</strong> Propón tus propios precios en cada cotización.</p></li>
                <li><span><Check aria-hidden="true" size={15} /></span><p><strong>Información clara</strong> Revisa tipo de carga y accesos antes de responder.</p></li>
                <li><span><Check aria-hidden="true" size={15} /></span><p><strong>Más tipos de clientes</strong> Conversa con particulares y empresas.</p></li>
                <li><span><Check aria-hidden="true" size={15} /></span><p><strong>Facturación según tu servicio</strong> Informa si puedes emitir boleta o factura.</p></li>
              </ul>
              <button className="button button-primary" onClick={() => showDemoNotice("El registro de transportistas aún no está habilitado. No se recopilaron datos.")} type="button">Registrar mi vehículo <ArrowRight aria-hidden="true" size={17} /></button>
              <p className="carrier-disclaimer">Registro de demostración. Todavía no recibimos solicitudes ni documentos.</p>
            </div>
          </div>
        </section>

        <section aria-labelledby="shared-title" className="shared-section section-wrap">
          <div className="shared-copy"><p className="eyebrow">UNA IDEA PARA MEJORAR CADA RUTA</p><h2 id="shared-title">Aprovecha viajes en ruta y optimiza costos.</h2><p>Si un transportista ya tiene una ruta programada con espacio libre, una carga parcial podría aprovechar ese trayecto.</p><div className="shared-disclaimer"><CircleHelp aria-hidden="true" size={17} /><span>La confirmación siempre depende del espacio, la carga y los desvíos que acepte el transportista.</span></div></div>
          <article className="route-card"><div className="route-card-top"><span className="route-example"><span className="route-example-dot" />EJEMPLO DE RUTA</span><span className="route-demo-tag">Ejemplo, no disponible</span></div><div className="route-cities"><div><MapPin aria-hidden="true" size={17} /><strong>Santiago</strong><span>Origen</span></div><span className="route-dash"><span /><ArrowRight aria-hidden="true" size={17} /><span /></span><div><MapPin aria-hidden="true" size={17} /><strong>Concepción</strong><span>Destino</span></div></div><div className="route-date"><span>Fecha estimada</span><strong>A coordinar con el transportista</strong></div><Link className="button button-secondary" href="/rutas-compartidas">Buscar viajes compartidos <ArrowUpRight aria-hidden="true" size={15} /></Link></article>
        </section>

        <section aria-labelledby="trust-title" className="trust-section">
          <div className="section-wrap">
            <div className="section-heading trust-heading"><div><p className="eyebrow">TRANSPARENCIA PRIMERO</p><h2 id="trust-title">Confianza que se construye con hechos</h2></div><p>Estas capacidades aún están en desarrollo. Hoy no hay verificaciones ni servicios de protección activos en la plataforma.</p></div>
            <div className="trust-grid">
              <article><span className="trust-icon"><FileText aria-hidden="true" size={21} /></span><h3>Validación documental</h3><p>Revisión de identidad y documentos del vehículo: función planificada, aún no activa.</p><span className="planned-label">En desarrollo</span></article>
              <article><span className="trust-icon"><Shield aria-hidden="true" size={21} /></span><h3>Pago en custodia</h3><p>La custodia de fondos no está disponible. Amira no procesa ni retiene pagos actualmente.</p><span className="planned-label">No disponible</span></article>
              <article><span className="trust-icon"><ClipboardList aria-hidden="true" size={21} /></span><h3>Preparado para empresas</h3><p>Consulta directamente si el prestador emite boletas o facturas para tu servicio.</p><span className="planned-label planned-available">A coordinar</span></article>
              <article><span className="trust-icon"><MessageCircle aria-hidden="true" size={21} /></span><h3>Soporte y mediación</h3><p>El canal formal de soporte y mediación todavía no está habilitado en Amira.</p><span className="planned-label">En desarrollo</span></article>
            </div>
          </div>
        </section>

        <section aria-labelledby="faq-title" className="faq-section section-wrap" id="faq">
          <div className="faq-intro"><p className="eyebrow">RESPUESTAS CLARAS</p><h2 id="faq-title">Preguntas frecuentes</h2><p>Queremos que sepas qué puedes hacer hoy y qué está por venir.</p><a className="text-link" href="#ayuda">Más información <ArrowRight aria-hidden="true" size={15} /></a></div>
          <div className="faq-list">{faqs.map(({ question, answer }) => <details className="faq-item" key={question}><summary>{question}<ChevronDown aria-hidden="true" size={18} /></summary><p>{answer}</p></details>)}</div>
        </section>

        <section aria-labelledby="closing-title" className="closing-section section-wrap" id="ayuda">
          <div className="closing-copy"><span className="closing-mark"><Truck aria-hidden="true" size={22} /></span><div><p className="eyebrow">AMIRA · MOVEMOS CONTIGO</p><h2 id="closing-title">Mueve tu carga o haz crecer tu negocio de transporte.</h2></div></div>
          <div className="closing-actions"><a className="button button-light" href="#buscar">Solicitar un servicio <ArrowRight aria-hidden="true" size={16} /></a><Link className="button button-outline-light" href="/registro?intent=provider">Ofrecer mis servicios <ArrowUpRight aria-hidden="true" size={16} /></Link></div>
        </section>
      </main>

      <footer className="site-footer" id="privacidad">
        <div className="section-wrap footer-main"><div className="footer-brand"><Brand /><p>Una red que conecta necesidades de transporte con prestadores independientes.</p></div><div className="footer-links"><div><strong>Explora</strong><Link href="/servicios">Servicios</Link><Link href="/rutas-compartidas">Viajes compartidos</Link><a href="#como-funciona">Cómo funciona</a><a href="#empresas">Empresas</a></div><div><strong>Participa</strong><a href="#transportistas">Para transportistas</a><a href="#buscar">Solicitar un servicio</a><Link href="/registro?intent=provider">Ofrecer mis servicios</Link></div><div><strong>Información</strong><a href="#faq">Centro de ayuda</a><a href="#pago">Política de pagos</a><a href="#privacidad" onClick={() => showDemoNotice("Los términos, la política de privacidad y el canal de ayuda aún no están publicados.")}>Privacidad y términos</a></div></div></div>
        <div className="section-wrap footer-bottom"><span>© 2026 Amira. Información de demostración.</span><span>Conecta. Cotiza. Coordina.</span></div>
      </footer>
      {demoNotice && <div aria-live="polite" className="notice-toast" role="status"><span>{demoNotice}</span><button aria-label="Cerrar aviso" onClick={() => setDemoNotice("")} type="button"><X aria-hidden="true" size={16} /></button></div>}
      <a className="skip-link" href="#contenido">Ir al contenido</a>
    </>
  );
}

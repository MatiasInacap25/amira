// Terms and Conditions content, transcribed verbatim (Spanish) from docs/legal/terminos-y-condiciones.md.
// Inline **bold** markers are kept in the strings and rendered through splitStrong.
// The version is a contract shared with the backend (backend/src/amira_api/terms.py).
export const TERMS_VERSION = "2026-11-23";

export const TERMS_TITLE = "Términos y Condiciones de Uso de Amira";

export type TermsNumberedItem = string | { text: string; children: string[] };

export type TermsBlock =
  | { type: "paragraph"; text: string }
  | { type: "note"; text: string }
  | { type: "bullets"; items: string[] }
  | { type: "numbered"; items: TermsNumberedItem[] }
  | { type: "table"; head: string[]; rows: string[][] };

export type TermsSection = { id: string; title: string; blocks: TermsBlock[] };

export const TERMS_INTRO: TermsBlock[] = [
  { type: "paragraph", text: "Última actualización: [fecha de publicación]" },
];

export const TERMS_SECTIONS: TermsSection[] = [
  {
    id: "quienes-somos",
    title: "1. Quiénes somos y qué es Amira",
    blocks: [
      {
        type: "paragraph",
        text: 'Amira es una plataforma digital operada por [razón social], RUT [RUT], con domicilio en [dirección] ("Amira", "nosotros"). Amira conecta a personas y empresas que necesitan trasladar bienes ("Clientes") con empresas de transporte y conductores independientes ("Transportistas") para servicios de mudanza, retiro de escombros, transporte de mercadería, fletes y remolque.',
      },
      {
        type: "paragraph",
        text: "**Amira es un intermediario, no una empresa de transporte.** El servicio de transporte lo contrata el Cliente directamente con el Transportista. Amira actúa como **mandatario** del Transportista para cobrar el precio al Cliente y entregárselo, descontando su comisión.",
      },
      {
        type: "paragraph",
        text: "Al crear una cuenta o usar la plataforma aceptas estos Términos. Si no estás de acuerdo, no uses Amira.",
      },
    ],
  },
  {
    id: "definiciones",
    title: "2. Definiciones",
    blocks: [
      {
        type: "bullets",
        items: [
          "**Solicitud**: el pedido que el Cliente hace a un Transportista, con origen, destino, fecha y descripción de la carga.",
          "**Cotización**: el precio que el Transportista ofrece por una Solicitud. Siempre incluye IVA.",
          "**Servicio**: el transporte que nace cuando el Cliente paga una Cotización.",
          "**Ruta compartida**: un viaje publicado por un Transportista al que otros Clientes pueden sumar su carga.",
          "**Servicio exclusivo**: un Servicio en que el Cliente no acepta compartir el vehículo con otras cargas.",
          "**Plazo de reclamo**: las 24 horas siguientes a que el Transportista marca el Servicio como completado.",
        ],
      },
    ],
  },
  {
    id: "de-que-se-encarga",
    title: "3. De qué se encarga Amira",
    blocks: [
      {
        type: "numbered",
        items: [
          "**Conectar a Clientes y Transportistas**: mostrar los servicios y rutas publicados y permitir enviar Solicitudes.",
          "**Verificar identidades**: validar la identidad de los usuarios al registrarse (documento de identidad, captura facial y segundo factor por SMS) y revisar los certificados de los conductores antes de que puedan ser asignados a un Servicio.",
          "**Ofrecer el canal de comunicación**: el chat entre Cliente y Transportista, donde se acuerdan los detalles y se envía la Cotización.",
          "**Cobrar el precio por cuenta del Transportista**: recibir el pago del Cliente a través de nuestra pasarela de pagos (Mercado Pago) como mandatarios del Transportista.",
          "**Retener el pago hasta la entrega**: guardar el dinero hasta que el Cliente dé su conformidad o venza el Plazo de reclamo sin reclamos abiertos.",
          "**Pagar al Transportista**: transferir al Transportista el precio cobrado, menos la comisión de Amira, a una cuenta bancaria a su nombre.",
          "**Dar seguimiento**: mostrar al Cliente el estado del Servicio, el conductor y la patente asignados, la ubicación en tiempo real mientras el Servicio está en curso y la foto de entrega.",
          "**Gestionar cancelaciones y reclamos**: aplicar las reglas de las secciones 9 y 10 y resolver los reclamos con la información disponible en la plataforma.",
          "**Facturar su comisión**: emitir al Transportista la factura por la comisión de intermediación.",
          "**Proteger los datos personales** según la sección 12.",
        ],
      },
    ],
  },
  {
    id: "de-que-no-se-encarga",
    title: "4. De qué NO se encarga Amira",
    blocks: [
      {
        type: "numbered",
        items: [
          "**No transportamos.** Amira no es porteador, no tiene vehículos ni conductores y no ejecuta el traslado. El Transportista es el único responsable de realizar el Servicio.",
          "**No fijamos el precio.** Cada Transportista define el precio de su Cotización. Amira no negocia ni garantiza precios.",
          "**No respondemos por la carga.** La custodia de la carga desde el retiro hasta la entrega corresponde al Transportista. Amira no responde por pérdidas, daños, mermas o atrasos, salvo que se deban a una falla de la plataforma.",
          "**No aseguramos la carga.** Los Servicios no incluyen seguro de carga. Si el Cliente lo necesita, debe pedirlo al Transportista o contratarlo por su cuenta.",
          "**No revisamos el contenido de la carga.** Amira no inspecciona lo que se transporta. La descripción, el peso y el volumen los declara el Cliente bajo su responsabilidad.",
          "**No emitimos la boleta o factura del flete.** El documento tributario por el transporte lo emite el Transportista al Cliente. Amira solo factura su comisión al Transportista.",
          "**No emitimos guías de despacho.** Cuando la ley exige una guía de despacho, la emite quien corresponda (normalmente el Cliente, como dueño de la mercadería).",
          "**No garantizamos espacio en una Ruta compartida** hasta que el pago se confirma. La compatibilidad de la carga y el espacio disponible los evalúa el Transportista.",
          "**No garantizamos disponibilidad.** Amira no asegura que haya Transportistas para todas las fechas, rutas o tipos de carga.",
          "**No respondemos por acuerdos fuera de la plataforma.** Pagos, cambios de precio o servicios acordados por fuera de Amira no están cubiertos por estos Términos ni por la retención del pago.",
        ],
      },
    ],
  },
  {
    id: "cuentas-y-verificacion",
    title: "5. Cuentas y verificación",
    blocks: [
      {
        type: "bullets",
        items: [
          "Debes ser mayor de 18 años y entregar datos verdaderos y actualizados.",
          "La cuenta es personal. Eres responsable de lo que se haga con ella y de mantener seguras tus credenciales.",
          "Amira puede **bloquear** una cuenta o **suspender** el perfil de un Transportista si detecta datos falsos, documentos rechazados, reclamos reiterados, uso fraudulento o incumplimiento de estos Términos. La decisión se informa con su motivo.",
        ],
      },
    ],
  },
  {
    id: "obligaciones-cliente",
    title: "6. Obligaciones del Cliente",
    blocks: [
      {
        type: "numbered",
        items: [
          "Describir la carga con veracidad: tipo, peso, volumen, fotos y condiciones especiales.",
          "No enviar cargas prohibidas: armas, drogas, explosivos, animales vivos, dinero, joyas o bienes ilícitos. Tampoco cargas peligrosas que no hayan sido declaradas y aceptadas expresamente por el Transportista.",
          "Embalar la carga de forma adecuada para el traslado.",
          "Estar presente, o designar a otra persona, en el retiro y en la entrega.",
          "Emitir la guía de despacho cuando la ley lo exija.",
          "Revisar la entrega y, si hay un problema, reclamar dentro del Plazo de reclamo.",
        ],
      },
    ],
  },
  {
    id: "obligaciones-transportista",
    title: "7. Obligaciones del Transportista",
    blocks: [
      {
        type: "numbered",
        items: [
          "Estar habilitado para operar: inicio de actividades vigente en el SII y los permisos que exija su actividad.",
          "Usar vehículos en buen estado, con su documentación al día, y asignar solo conductores verificados en Amira.",
          "Cotizar con el precio final, **con IVA incluido**.",
          "Realizar el Servicio en la fecha y las condiciones acordadas, y registrar el inicio y la entrega con su foto en la plataforma.",
          "Emitir al Cliente la boleta o factura por el Servicio.",
          "Registrar una cuenta bancaria **a nombre del mismo RUT** del perfil. Amira no paga a cuentas de terceros.",
          "Responder por la carga, por su personal y por los daños que cause durante el Servicio.",
          "Aceptar a otros Clientes en una Ruta compartida solo si la carga es compatible y hay espacio real.",
        ],
      },
    ],
  },
  {
    id: "precios-pago-comision",
    title: "8. Precios, pago y comisión",
    blocks: [
      {
        type: "bullets",
        items: [
          "El precio de la Cotización **incluye IVA**. Ese es el monto que paga el Cliente.",
          "El pago es **anticipado**: el Servicio queda confirmado cuando el pago se aprueba.",
          "Amira recibe el pago como mandataria del Transportista y lo mantiene retenido según la sección 10.",
          "Amira cobra al Transportista una **comisión del 10 % del monto pagado**, con IVA incluido, que se descuenta antes de transferirle.",
        ],
      },
      {
        type: "note",
        text: "Ejemplo: Cotización de $80.000. El Cliente paga $80.000. La comisión de Amira es $8.000 ($6.723 + $1.277 de IVA). El Transportista recibe $72.000.",
      },
    ],
  },
  {
    id: "cancelaciones",
    title: "9. Cancelaciones",
    blocks: [
      {
        type: "table",
        head: ["Quién cancela", "Cuándo", "Qué pasa con el pago"],
        rows: [
          ["El Cliente", "Antes de que el Servicio inicie", "Se devuelve el **90 %**. Amira retiene el **10 %** por gastos de gestión"],
          ["El Transportista", "Antes de que el Servicio inicie", "Se devuelve el **100 %** al Cliente"],
          ["Cualquiera", "Con el Servicio ya iniciado", "No se puede cancelar desde la plataforma. Si hay un problema, corresponde un reclamo"],
        ],
      },
      {
        type: "paragraph",
        text: "La devolución se hace al mismo medio de pago, en los plazos de la pasarela de pagos.",
      },
    ],
  },
  {
    id: "conformidad-reclamos",
    title: "10. Conformidad, reclamos y liberación del pago",
    blocks: [
      {
        type: "numbered",
        items: [
          "Cuando el Transportista marca el Servicio como completado, el Cliente tiene **24 horas** para dar su conformidad o abrir un reclamo.",
          "Un reclamo **bloquea el pago al Transportista** hasta que Amira lo resuelve.",
          {
            text: "Amira revisa el reclamo con la información de la plataforma (foto de entrega, chat, historial y evidencia que entreguen las partes) y lo resuelve:",
            children: [
              "**A favor del Cliente**: se le devuelve lo pagado y el Transportista no recibe el pago.",
              "**A favor del Transportista**: se libera el pago.",
            ],
          },
          "Si el Cliente da su conformidad o pasan 24 horas sin reclamos, el pago se libera al Transportista.",
          "La resolución de Amira no impide que las partes ejerzan sus derechos ante los tribunales o el SERNAC.",
        ],
      },
    ],
  },
  {
    id: "rutas-compartidas",
    title: "11. Rutas compartidas y servicio exclusivo",
    blocks: [
      {
        type: "bullets",
        items: [
          "Al solicitar un Servicio, el Cliente elige si acepta compartir el vehículo. Si elige **servicio exclusivo**, su carga no se combina con otras durante ese Servicio.",
          "En una Ruta compartida, cada Cliente tiene su propio Servicio, Cotización, chat y pago. Lo que le pase a un Cliente no afecta el Servicio de los demás.",
          "Las paradas y los horarios publicados son estimados. El Transportista puede ajustarlos para sumar retiros y entregas, avisando a los Clientes.",
        ],
      },
    ],
  },
  {
    id: "datos-personales",
    title: "12. Datos personales y privacidad",
    blocks: [
      {
        type: "bullets",
        items: [
          "Tratamos tus datos (identidad, contacto, RUT, direcciones, ubicación y documentos) solo para operar la plataforma, verificar identidades, procesar pagos y cumplir la ley, según la normativa chilena de protección de datos personales.",
          "La **ubicación en tiempo real** del conductor se comparte con el Cliente solo mientras el Servicio está en curso.",
          "Los **chats** son privados entre las partes. Amira solo accede a ellos para resolver un reclamo o por requerimiento legal, y deja registro de ese acceso.",
          "Compartimos con el Transportista solo los datos del Cliente necesarios para el Servicio, y con el Cliente solo los datos del Transportista y del conductor necesarios para identificarlos.",
          "Puedes pedir acceso, rectificación o eliminación de tus datos escribiendo a [correo de contacto], salvo los que debamos conservar por ley (por ejemplo, registros de pagos).",
        ],
      },
    ],
  },
  {
    id: "responsabilidad",
    title: "13. Responsabilidad de Amira",
    blocks: [
      {
        type: "paragraph",
        text: "Amira responde por el funcionamiento de la plataforma, por la custodia del dinero mientras lo retiene y por aplicar estas reglas. No responde por el Servicio de transporte en sí ni por lo que hagan Clientes o Transportistas, conforme a la sección 4. Nada en estos Términos limita los derechos irrenunciables del Cliente consumidor según la Ley N° 19.496.",
      },
    ],
  },
  {
    id: "cambios",
    title: "14. Cambios a estos Términos",
    blocks: [
      {
        type: "paragraph",
        text: "Podemos actualizar estos Términos. Si el cambio es relevante, te avisaremos en la plataforma o por correo antes de que entre en vigencia. Los Servicios ya pagados se rigen por los Términos vigentes al momento del pago.",
      },
    ],
  },
  {
    id: "ley-aplicable",
    title: "15. Ley aplicable y contacto",
    blocks: [
      {
        type: "paragraph",
        text: "Estos Términos se rigen por las leyes de la República de Chile. Consultas y reclamos: [correo de contacto] · [teléfono].",
      },
    ],
  },
];

export type InlineSegment = { text: string; strong: boolean };

// Splits a string on **bold** markers so the renderer can emit <strong> without HTML injection.
export function splitStrong(source: string): InlineSegment[] {
  const segments: InlineSegment[] = [];
  const pattern = /\*\*(.+?)\*\*/g;
  let cursor = 0;
  for (const match of source.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > cursor) segments.push({ text: source.slice(cursor, index), strong: false });
    segments.push({ text: match[1] ?? "", strong: true });
    cursor = index + match[0].length;
  }
  if (cursor < source.length) segments.push({ text: source.slice(cursor), strong: false });
  return segments;
}

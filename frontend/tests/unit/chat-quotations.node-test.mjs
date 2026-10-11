import assert from "node:assert/strict";
import { test } from "node:test";
import {
  CHAT_MESSAGE_MAX_LENGTH,
  canPayQuotation,
  canRejectQuotation,
  contactDetailMessage,
  findContactDetailKind,
  formatClp,
  paymentResultState,
  quotationStatusLabel,
  validateMessageDraft,
  validateQuotationDraft,
} from "../../src/lib/chat-quotations.ts";

const NOW = new Date("2026-10-11T15:00:00.000Z");
const HOURS_AHEAD = (hours) => new Date(NOW.getTime() + hours * 3_600_000).toISOString();

test("flags phone numbers, emails, links and social handles", () => {
  assert.equal(findContactDetailKind("llámame al +56 9 1234 5678"), "phone");
  assert.equal(findContactDetailKind("mi correo es ana@mail.com"), "email");
  assert.equal(findContactDetailKind("mira https://wa.me/abc"), "link");
  assert.equal(findContactDetailKind("escríbeme a www.ejemplo.cl"), "link");
  assert.equal(findContactDetailKind("sígueme en instagram"), "social");
  assert.equal(findContactDetailKind("mi usuario es @ana.transporte"), "social");
});

test("lets ordinary messages through", () => {
  assert.equal(findContactDetailKind("Llego a las 9:30 con la camioneta"), null);
  assert.equal(findContactDetailKind("Son 3 bultos de 20 kilos"), null);
  assert.equal(findContactDetailKind("¿Cuánto cobras por la mudanza?"), null);
});

test("names the blocked kind in the Spanish contact message", () => {
  assert.equal(contactDetailMessage("phone"), "No compartas números de teléfono en el chat.");
  assert.equal(contactDetailMessage("email"), "No compartas correos electrónicos en el chat.");
  assert.equal(contactDetailMessage("link"), "No compartas enlaces en el chat.");
  assert.equal(contactDetailMessage("social"), "No compartas redes sociales en el chat.");
});

test("validates the message draft after trimming", () => {
  assert.equal(validateMessageDraft("   "), "Escribe un mensaje antes de enviarlo.");
  assert.equal(validateMessageDraft("a".repeat(CHAT_MESSAGE_MAX_LENGTH + 1)), "El mensaje no puede superar los 2000 caracteres.");
  assert.equal(validateMessageDraft("  hola  "), null);
  assert.equal(validateMessageDraft("llámame +56 9 1234 5678"), "No compartas números de teléfono en el chat.");
});

test("formats CLP amounts without decimals", () => {
  assert.equal(formatClp(125000), "$125.000");
});

test("accepts a valid quotation draft and rejects bad fields", () => {
  const valid = { amount: 90000, serviceAt: "2026-10-20T10:00", description: "Mudanza pequeña", validityHours: 48 };
  assert.equal(validateQuotationDraft(valid), null);
  assert.equal(validateQuotationDraft({ ...valid, amount: 0 }), "Ingresa un monto mayor a cero.");
  assert.equal(validateQuotationDraft({ ...valid, amount: 10.5 }), "El monto debe ser un número entero de pesos.");
  assert.equal(validateQuotationDraft({ ...valid, serviceAt: "" }), "Indica la fecha del servicio.");
  assert.equal(validateQuotationDraft({ ...valid, description: " " }), "Describe el servicio que ofreces.");
  assert.equal(validateQuotationDraft({ ...valid, validityHours: 0 }), "La vigencia debe estar entre 1 y 168 horas.");
  assert.equal(validateQuotationDraft({ ...valid, validityHours: 169 }), "La vigencia debe estar entre 1 y 168 horas.");
});

test("allows paying and rejecting only a pending, unexpired quotation", () => {
  const pending = { status: "pending", expiresAt: HOURS_AHEAD(2) };
  assert.equal(canPayQuotation(pending, NOW), true);
  assert.equal(canRejectQuotation(pending, NOW), true);
  const expired = { status: "pending", expiresAt: HOURS_AHEAD(-1) };
  assert.equal(canPayQuotation(expired, NOW), false);
  assert.equal(canRejectQuotation(expired, NOW), false);
  const paid = { status: "paid", expiresAt: HOURS_AHEAD(2) };
  assert.equal(canPayQuotation(paid, NOW), false);
});

test("labels every quotation status in Spanish", () => {
  assert.equal(quotationStatusLabel("pending"), "Pendiente de pago");
  assert.equal(quotationStatusLabel("paid"), "Pagada");
  assert.equal(quotationStatusLabel("rejected"), "Rechazada");
  assert.equal(quotationStatusLabel("expired"), "Vencida");
  assert.equal(quotationStatusLabel("superseded"), "Reemplazada");
});

test("maps the payment return to success, failure or pending", () => {
  assert.equal(paymentResultState({ quotationStatus: "paid" }), "success");
  assert.equal(paymentResultState({ quotationStatus: "pending", status: "rejected" }), "failure");
  assert.equal(paymentResultState({ quotationStatus: "pending", status: "pending" }), "pending");
});

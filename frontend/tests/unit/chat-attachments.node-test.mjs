import assert from "node:assert/strict";
import { test } from "node:test";
import {
  CHAT_ATTACHMENT_MAX_BYTES,
  chatAttachmentErrorMessage,
  validateChatAttachment,
} from "../../src/lib/chat-attachments.ts";

const MB = 1024 * 1024;

test("accepts JPEG, PNG and WebP photos up to 5 MB", () => {
  assert.equal(CHAT_ATTACHMENT_MAX_BYTES, 5 * MB);
  assert.equal(validateChatAttachment({ type: "image/jpeg", size: 1024 }), null);
  assert.equal(validateChatAttachment({ type: "image/png", size: 1024 }), null);
  assert.equal(validateChatAttachment({ type: "image/webp", size: 5 * MB }), null);
});

test("rejects other types with a Spanish message", () => {
  assert.equal(
    validateChatAttachment({ type: "application/pdf", size: 1024 }),
    "Solo puedes adjuntar fotos en formato JPEG, PNG o WebP.",
  );
  assert.equal(
    validateChatAttachment({ type: "image/gif", size: 1024 }),
    "Solo puedes adjuntar fotos en formato JPEG, PNG o WebP.",
  );
});

test("rejects photos larger than 5 MB", () => {
  assert.equal(validateChatAttachment({ type: "image/png", size: 5 * MB + 1 }), "La foto no puede superar los 5 MB.");
});

test("maps upload errors to Spanish messages", () => {
  assert.equal(chatAttachmentErrorMessage(404, null), "Esta conversación ya no está disponible.");
  assert.equal(chatAttachmentErrorMessage(413, null), "La foto no puede superar los 5 MB.");
  assert.equal(chatAttachmentErrorMessage(415, null), "Solo puedes adjuntar fotos en formato JPEG, PNG o WebP.");
  assert.equal(chatAttachmentErrorMessage(502, null), "No pudimos subir la foto. Inténtalo nuevamente.");
  assert.equal(chatAttachmentErrorMessage(503, null), "El envío de fotos no está disponible en este momento.");
  assert.equal(chatAttachmentErrorMessage(500, null), "No pudimos enviar la foto. Revisa tu conexión e inténtalo nuevamente.");
});

test("shows the backend detail verbatim for contact-filter rejections", () => {
  assert.equal(
    chatAttachmentErrorMessage(422, "El chat no permite compartir datos de contacto."),
    "El chat no permite compartir datos de contacto.",
  );
  assert.equal(chatAttachmentErrorMessage(422, null), "No pudimos enviar la foto. Revisa tu conexión e inténtalo nuevamente.");
});

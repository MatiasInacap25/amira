import assert from "node:assert/strict";
import { register } from "node:module";
import { test } from "node:test";

register("../support/alias-loader.mjs", import.meta.url);
const {
  CERTIFICATE_LABELS,
  certificateStatusLabel,
  driverVerificationError,
  simulatedCertificateSubmission,
  validateCertificateFile,
} = await import("../../src/lib/driver-verification-api.ts");
const { missingProfileLabels } = await import("../../src/lib/provider-profile-api.ts");

function file(name, type, content = "%PDF-1.7\n", size) {
  const blob = new File([content], name, { type });
  return size === undefined ? blob : Object.defineProperty(blob, "size", { value: size });
}

test("a PDF certificate is valid", async () => {
  assert.equal(await validateCertificateFile(file("antecedentes.pdf", "application/pdf")), null);
  assert.equal(await validateCertificateFile(file("HOJA-VIDA.PDF", "")), null);
});

test("a certificate file is required", async () => {
  assert.equal(await validateCertificateFile(null), "Selecciona el certificado en PDF.");
});

test("only PDF files are accepted", async () => {
  const onlyPdf = "Solo se aceptan certificados en PDF.";
  assert.equal(await validateCertificateFile(file("foto.jpg", "image/jpeg", "\xff\xd8\xff")), onlyPdf);
  assert.equal(await validateCertificateFile(file("certificado.pdf", "image/png")), onlyPdf);
  assert.equal(await validateCertificateFile(file("renombrado.pdf", "application/pdf", "not a pdf")), onlyPdf);
});

test("a PDF over 5 MB is refused", async () => {
  assert.equal(
    await validateCertificateFile(file("grande.pdf", "application/pdf", "%PDF-1.7", 5 * 1024 * 1024 + 1)),
    "El PDF no puede pesar más de 5 MB.",
  );
});

test("the simulated submission never carries the file and uses a fresh valid folio", () => {
  const first = simulatedCertificateSubmission("criminal_record");
  const second = simulatedCertificateSubmission("driver_record");
  assert.deepEqual(Object.keys(first).sort(), ["folio", "type", "verification_code"]);
  assert.equal(first.type, "criminal_record");
  assert.equal(second.type, "driver_record");
  assert.match(first.folio, /^[1-9][0-9]{14}$/);
  assert.match(first.verification_code, /^[0-9A-Za-z_-]{1,64}$/);
  assert.notEqual(first.folio, second.folio);
});

test("each certificate type has its Spanish name", () => {
  assert.equal(CERTIFICATE_LABELS.criminal_record, "Certificado de antecedentes");
  assert.equal(CERTIFICATE_LABELS.driver_record, "Hoja de vida del conductor");
});

test("each status has its Spanish label", () => {
  assert.equal(certificateStatusLabel("missing"), "Pendiente");
  assert.equal(certificateStatusLabel("verified"), "Verificado");
  assert.equal(certificateStatusLabel("in_review"), "En revisión");
  assert.equal(certificateStatusLabel("rejected"), "Rechazado");
});

function response(status, body) {
  return new Response(body === undefined ? "" : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

test("the API's Spanish detail is shown for 409 and 422 answers", async () => {
  assert.equal(await driverVerificationError(response(409, { detail: "Este certificado ya fue usado en Amira." })), "Este certificado ya fue usado en Amira.");
  assert.equal(
    await driverVerificationError(response(422, { detail: "No encontramos un certificado con ese folio y código verificador." })),
    "No encontramos un certificado con ese folio y código verificador.",
  );
});

test("other failures get fixed Spanish messages and never echo a structured detail", async () => {
  assert.equal(await driverVerificationError(response(422, { detail: [{ msg: "x" }] })), "Revisa el certificado e inténtalo nuevamente.");
  assert.equal(await driverVerificationError(response(403, { detail: "Solo los conductores pueden verificar certificados." })), "Solo los conductores pueden verificar certificados.");
  assert.equal(await driverVerificationError(response(503, { detail: "boom" })), "La verificación de certificados no está disponible por el momento. Inténtalo más tarde.");
  assert.equal(await driverVerificationError(response(500)), "No pudimos completar la verificación. Inténtalo nuevamente.");
});

test("the profile checklist names the missing driver verification", () => {
  assert.deepEqual(missingProfileLabels(["driver_verification"]), ["Verifica tus certificados de conductor"]);
});

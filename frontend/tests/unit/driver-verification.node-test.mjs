import assert from "node:assert/strict";
import { register } from "node:module";
import { test } from "node:test";

register("../support/alias-loader.mjs", import.meta.url);
const {
  CERTIFICATE_LABELS,
  certificateStatusLabel,
  driverVerificationError,
  validateCertificateForm,
} = await import("../../src/lib/driver-verification-api.ts");
const { missingProfileLabels } = await import("../../src/lib/provider-profile-api.ts");

test("a folio of 10 to 15 letters or digits and a code are valid, after trimming", () => {
  assert.deepEqual(validateCertificateForm({ folio: " 50070080804 ", verificationCode: " 2aacbb9a636a " }), {});
});

test("the folio is required and must be 10 to 15 letters or digits", () => {
  assert.equal(validateCertificateForm({ folio: "", verificationCode: "abc" }).folio, "Ingresa el folio del certificado.");
  assert.equal(validateCertificateForm({ folio: "123456789", verificationCode: "abc" }).folio, "El folio tiene entre 10 y 15 letras o números.");
  assert.equal(validateCertificateForm({ folio: "5007008080412345", verificationCode: "abc" }).folio, "El folio tiene entre 10 y 15 letras o números.");
  assert.equal(validateCertificateForm({ folio: "50070-80804", verificationCode: "abc" }).folio, "El folio tiene entre 10 y 15 letras o números.");
});

test("the verification code is required and has no spaces or symbols", () => {
  assert.equal(validateCertificateForm({ folio: "50070080804", verificationCode: " " }).verificationCode, "Ingresa el código verificador.");
  assert.equal(validateCertificateForm({ folio: "50070080804", verificationCode: "2aac bb9a" }).verificationCode, "El código verificador solo tiene letras y números.");
  assert.equal(validateCertificateForm({ folio: "50070080804", verificationCode: "a".repeat(65) }).verificationCode, "El código verificador solo tiene letras y números.");
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
  assert.equal(await driverVerificationError(response(422, { detail: [{ msg: "x" }] })), "Revisa el folio y el código verificador.");
  assert.equal(await driverVerificationError(response(403, { detail: "Solo los conductores pueden verificar certificados." })), "Solo los conductores pueden verificar certificados.");
  assert.equal(await driverVerificationError(response(503, { detail: "boom" })), "La verificación de certificados no está disponible por el momento. Inténtalo más tarde.");
  assert.equal(await driverVerificationError(response(500)), "No pudimos completar la verificación. Inténtalo nuevamente.");
});

test("the profile checklist names the missing driver verification", () => {
  assert.deepEqual(missingProfileLabels(["driver_verification"]), ["Verifica tus certificados de conductor"]);
});

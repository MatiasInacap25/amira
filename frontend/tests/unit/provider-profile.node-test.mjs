import assert from "node:assert/strict";
import { register } from "node:module";
import { test } from "node:test";

register("../support/alias-loader.mjs", import.meta.url);
const { missingProfileLabels, profileRejectionMessage, profileMutationErrorMessage, ProviderProfileError } = await import(
  "../../src/lib/provider-profile-api.ts"
);
const { ProviderRequestAccessError } = await import("../../src/lib/provider-request-access.ts");

test("missing service types and commune map to their Spanish checklist labels", () => {
  assert.deepEqual(missingProfileLabels(["service_types", "commune"]), [
    "Elige al menos un tipo de servicio",
    "Elige tu comuna",
  ]);
});

test("the checklist keeps the order the backend sends", () => {
  assert.deepEqual(missingProfileLabels(["commune", "service_types"]), [
    "Elige tu comuna",
    "Elige al menos un tipo de servicio",
  ]);
});

test("a complete profile has no checklist labels", () => {
  assert.deepEqual(missingProfileLabels([]), []);
});

test("unknown missing keys are ignored instead of rendered raw", () => {
  assert.deepEqual(missingProfileLabels(["vehicle", "commune"]), ["Elige tu comuna"]);
});

const GENERIC = "No pudimos guardar tu perfil. Revisa los datos e inténtalo nuevamente.";

test("a publish 422 with missing items lists them in Spanish", () => {
  assert.equal(
    profileRejectionMessage({ detail: { message: "Profile is incomplete.", missing: ["service_types", "commune"] } }),
    "Para publicar tu perfil falta: Elige al menos un tipo de servicio, Elige tu comuna.",
  );
});

test("a publish 422 whose missing list has no known items gets the generic message", () => {
  assert.equal(profileRejectionMessage({ detail: { message: "Profile is incomplete.", missing: ["vehicle"] } }), GENERIC);
});

test("a missing description gets its own Spanish checklist label", () => {
  assert.deepEqual(missingProfileLabels(["description"]), ["Escribe una descripción"]);
});

test("description, commune and service types keep the backend order in the checklist", () => {
  assert.deepEqual(missingProfileLabels(["description", "commune", "service_types"]), [
    "Escribe una descripción",
    "Elige tu comuna",
    "Elige al menos un tipo de servicio",
  ]);
});

test("a blank company name gets a Spanish checklist label", () => {
  assert.deepEqual(missingProfileLabels(["name"]), ["Escribe el nombre de la empresa"]);
});

test("a publish 422 missing a description lists it first in Spanish", () => {
  assert.equal(
    profileRejectionMessage({ detail: { message: "Profile is incomplete.", missing: ["description", "commune"] } }),
    "Para publicar tu perfil falta: Escribe una descripción, Elige tu comuna.",
  );
});

test("'Only company profiles have a name.' maps to its Spanish copy", () => {
  assert.equal(
    profileRejectionMessage({ detail: "Only company profiles have a name." }),
    "Solo las empresas pueden cambiar el nombre.",
  );
});

test("'Company profiles require a name.' maps to the Spanish name message", () => {
  assert.equal(profileRejectionMessage({ detail: "Company profiles require a name." }), "Escribe el nombre de la empresa.");
});

test("'Unknown commune.' maps to its Spanish copy", () => {
  assert.equal(profileRejectionMessage({ detail: "Unknown commune." }), "La comuna elegida no existe.");
});

test("'Unknown service type.' maps to its Spanish copy", () => {
  assert.equal(profileRejectionMessage({ detail: "Unknown service type." }), "Uno de los tipos de servicio no existe.");
});

test("an unknown English detail string never reaches the UI and gets the generic message", () => {
  assert.equal(profileRejectionMessage({ detail: "Some new backend sentence." }), GENERIC);
});

test("a blank company name field error gets the Spanish name message", () => {
  assert.equal(
    profileRejectionMessage({ detail: [{ type: "value_error", loc: ["body", "name"], msg: "Value error, name must not be blank" }] }),
    "Escribe el nombre de la empresa.",
  );
});

test("a description over the backend limit gets the Spanish length message", () => {
  assert.equal(
    profileRejectionMessage({ detail: [{ type: "string_too_long", loc: ["body", "description"], msg: "String should have at most 2000 characters" }] }),
    "La descripción no puede tener más de 2000 caracteres.",
  );
});

test("a name that is too long is not reported as a blank name", () => {
  assert.equal(
    profileRejectionMessage({ detail: [{ type: "string_too_long", loc: ["body", "name"], msg: "String should have at most 160 characters" }] }),
    GENERIC,
  );
});

test("a field error on an unmapped field gets the generic message and never its raw text", () => {
  assert.equal(profileRejectionMessage({ detail: [{ type: "value_error", loc: ["body", "commune_code"], msg: "Raw English text" }] }), GENERIC);
});

const NETWORK = "No pudimos conectar con el servidor. Inténtalo nuevamente.";
const SESSION = "Tu sesión expiró. Inicia sesión nuevamente para continuar.";

test("an MFA-pending session on a save shows the SMS message for the profile", () => {
  assert.equal(profileMutationErrorMessage(new ProviderRequestAccessError("aal2")), "Verifica tu teléfono por SMS para ver tu perfil.");
});

test("an unconfirmed sign-in on a save shows the sign-in message for the profile", () => {
  assert.equal(
    profileMutationErrorMessage(new ProviderRequestAccessError("sign-in")),
    "Inicia sesión con tu correo confirmado para ver tu perfil.",
  );
});

test("an expired session on a save shows the session message", () => {
  assert.equal(profileMutationErrorMessage(new ProviderRequestAccessError("session")), SESSION);
});

test("an API 401 on a save shows the session message", () => {
  assert.equal(profileMutationErrorMessage(new ProviderProfileError(401, { detail: "Not authenticated" })), SESSION);
});

test("an API 403 on a save shows the permission message, not the session message", () => {
  assert.equal(
    profileMutationErrorMessage(new ProviderProfileError(403, { detail: "Forbidden" })),
    "No tienes permiso para modificar este perfil.",
  );
});

test("an API 422 on a save keeps the rejection mapping", () => {
  assert.equal(profileMutationErrorMessage(new ProviderProfileError(422, { detail: "Unknown commune." })), "La comuna elegida no existe.");
});

test("a failure that never reached the API shows the network message", () => {
  assert.equal(profileMutationErrorMessage(new TypeError("fetch failed")), NETWORK);
});

test("a missing body or an absent detail gets the generic message", () => {
  assert.equal(profileRejectionMessage(null), GENERIC);
  assert.equal(profileRejectionMessage({ message: "x" }), GENERIC);
});

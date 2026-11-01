import assert from "node:assert/strict";
import { register } from "node:module";
import { test } from "node:test";

register("../support/alias-loader.mjs", import.meta.url);
const { missingProfileLabels, profileRejectionMessage } = await import("../../src/lib/provider-profile-api.ts");

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

test("'Unknown commune.' maps to its Spanish copy", () => {
  assert.equal(profileRejectionMessage({ detail: "Unknown commune." }), "La comuna elegida no existe.");
});

test("'Unknown service type.' maps to its Spanish copy", () => {
  assert.equal(profileRejectionMessage({ detail: "Unknown service type." }), "Uno de los tipos de servicio no existe.");
});

test("an unknown English detail string never reaches the UI and gets the generic message", () => {
  assert.equal(profileRejectionMessage({ detail: "Some new backend sentence." }), GENERIC);
});

test("a Pydantic field-list 422 gets the generic message", () => {
  assert.equal(profileRejectionMessage({ detail: [{ loc: ["body", "description"], msg: "String too long" }] }), GENERIC);
});

test("a missing body or an absent detail gets the generic message", () => {
  assert.equal(profileRejectionMessage(null), GENERIC);
  assert.equal(profileRejectionMessage({ message: "x" }), GENERIC);
});

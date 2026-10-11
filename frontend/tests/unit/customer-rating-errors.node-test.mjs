import assert from "node:assert/strict";
import { test } from "node:test";
import { mapRatingRejection } from "../../src/lib/customer-rating-errors.ts";

const NOT_COMPLETED = "Solo puedes valorar servicios completados.";
const GENERIC = "No pudimos guardar la valoración. Revisa los datos e inténtalo nuevamente.";

test("maps service_not_completed to the completed-service message", () => {
  const result = mapRatingRejection({
    detail: [{ loc: ["path", "service_id"], msg: "Solo puedes valorar servicios completados.", type: "service_not_completed" }],
  });
  assert.equal(result.submitError, NOT_COMPLETED);
  assert.deepEqual(result.fieldErrors, {});
});

test("maps a rating field error to an inline field message", () => {
  const result = mapRatingRejection({
    detail: [{ loc: ["body", "rating"], msg: "Input should be less than or equal to 5", type: "less_than_equal" }],
  });
  assert.ok(result.fieldErrors.rating);
  assert.equal(result.fieldErrors.comment, undefined);
  assert.equal(result.submitError, "");
});

test("maps a comment field error to an inline field message", () => {
  const result = mapRatingRejection({
    detail: [{ loc: ["body", "comment"], msg: "String should have at most 1000 characters", type: "string_too_long" }],
  });
  assert.ok(result.fieldErrors.comment);
  assert.equal(result.fieldErrors.rating, undefined);
  assert.equal(result.submitError, "");
});

test("keeps both field messages when rating and comment are both rejected", () => {
  const result = mapRatingRejection({
    detail: [
      { loc: ["body", "rating"], msg: "x", type: "less_than_equal" },
      { loc: ["body", "comment"], msg: "y", type: "string_too_long" },
    ],
  });
  assert.ok(result.fieldErrors.rating);
  assert.ok(result.fieldErrors.comment);
});

test("prefers the completed-service message over field entries", () => {
  const result = mapRatingRejection({
    detail: [
      { loc: ["body", "rating"], msg: "x", type: "less_than_equal" },
      { loc: ["path", "service_id"], msg: "y", type: "service_not_completed" },
    ],
  });
  assert.equal(result.submitError, NOT_COMPLETED);
});

test("falls back to a generic Spanish message for unknown bodies and locations", () => {
  for (const body of [null, undefined, "x", {}, { detail: "x" }, { detail: [{ loc: ["body", "other"], msg: "z" }] }]) {
    const result = mapRatingRejection(body);
    assert.equal(result.submitError, GENERIC, `body ${JSON.stringify(body)}`);
    assert.deepEqual(result.fieldErrors, {});
  }
});

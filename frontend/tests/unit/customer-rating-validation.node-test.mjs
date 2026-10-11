import assert from "node:assert/strict";
import { test } from "node:test";
import { normalizeRatingComment, validateRatingDraft } from "../../src/lib/customer-rating-validation.ts";

test("normalizeRatingComment trims and maps blank comments to null", () => {
  assert.equal(normalizeRatingComment("   "), null);
  assert.equal(normalizeRatingComment(""), null);
  assert.equal(normalizeRatingComment("  Llegó a tiempo  "), "Llegó a tiempo");
});

test("validateRatingDraft requires an integer rating from 1 to 5", () => {
  assert.ok(validateRatingDraft({ rating: null, comment: "" }).rating);
  assert.ok(validateRatingDraft({ rating: 0, comment: "" }).rating);
  assert.ok(validateRatingDraft({ rating: 6, comment: "" }).rating);
  assert.ok(validateRatingDraft({ rating: 2.5, comment: "" }).rating);
  assert.equal(validateRatingDraft({ rating: 1, comment: "" }).rating, undefined);
  assert.equal(validateRatingDraft({ rating: 5, comment: "" }).rating, undefined);
});

test("validateRatingDraft caps the trimmed comment at 1000 characters", () => {
  assert.equal(validateRatingDraft({ rating: 4, comment: "a".repeat(1000) }).comment, undefined);
  assert.ok(validateRatingDraft({ rating: 4, comment: "a".repeat(1001) }).comment);
  assert.equal(validateRatingDraft({ rating: 4, comment: `  ${"a".repeat(1000)}  ` }).comment, undefined);
});

test("validateRatingDraft counts characters the way the API does (code points)", () => {
  assert.equal(validateRatingDraft({ rating: 4, comment: "😀".repeat(1000) }).comment, undefined);
  assert.ok(validateRatingDraft({ rating: 4, comment: "😀".repeat(1001) }).comment);
});

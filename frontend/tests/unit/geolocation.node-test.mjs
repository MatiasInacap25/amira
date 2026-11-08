import assert from "node:assert/strict";
import { test } from "node:test";
import {
  LOCATION_INTERVAL_MS,
  LocationError,
  POSITION_MAX_AGE_MS,
  geolocationErrorMessage,
  isFreshPosition,
  isNewerPosition,
  isValidCoordinates,
  requestDriverLocation,
  shouldSendLocation,
  shouldSendPosition,
  toLocationPayload,
} from "../../src/lib/geolocation.ts";

test("the sharing interval is about every 15 seconds", () => {
  assert.equal(LOCATION_INTERVAL_MS, 15000);
});

test("a position is fresh only while its age is within the freshness limit", () => {
  const now = 1_000_000;
  assert.equal(POSITION_MAX_AGE_MS, 30000);
  assert.equal(isFreshPosition(now, now), true);
  assert.equal(isFreshPosition(now - POSITION_MAX_AGE_MS, now), true);
  assert.equal(isFreshPosition(now - POSITION_MAX_AGE_MS - 1, now), false);
  assert.equal(isFreshPosition(now - 60000, now), false);
});

test("a position timestamp in the future or not a number is never fresh", () => {
  const now = 1_000_000;
  assert.equal(isFreshPosition(now + 1, now), false);
  assert.equal(isFreshPosition(Number.NaN, now), false);
  assert.equal(isFreshPosition(undefined, now), false);
});

test("a position is newer than the last sent one only when its timestamp advances", () => {
  assert.equal(isNewerPosition(2000, null), true);
  assert.equal(isNewerPosition(2000, 1000), true);
  assert.equal(isNewerPosition(1000, 1000), false);
  assert.equal(isNewerPosition(500, 1000), false);
});

test("a position is sent only when it is both fresh and newer than the last sent one", () => {
  const now = 1_000_000;
  assert.equal(shouldSendPosition(now - 1000, null, now), true);
  assert.equal(shouldSendPosition(now - 1000, now - 1000, now), false, "an already sent position is never resent");
  assert.equal(shouldSendPosition(now - 60000, null, now), false, "a stale position is never sent as current");
});

test("accepts coordinates inside the valid ranges, with an optional accuracy", () => {
  assert.equal(isValidCoordinates({ latitude: -33.4489, longitude: -70.6693 }), true);
  assert.equal(isValidCoordinates({ latitude: -90, longitude: 180, accuracy: 0 }), true);
  assert.equal(isValidCoordinates({ latitude: 90, longitude: -180, accuracy: 100000 }), true);
});

test("rejects out-of-range, non-finite or non-numeric coordinates", () => {
  assert.equal(isValidCoordinates({ latitude: 90.0001, longitude: 0 }), false);
  assert.equal(isValidCoordinates({ latitude: 0, longitude: -180.5 }), false);
  assert.equal(isValidCoordinates({ latitude: Number.NaN, longitude: 0 }), false);
  assert.equal(isValidCoordinates({ latitude: 0, longitude: Number.POSITIVE_INFINITY }), false);
  assert.equal(isValidCoordinates({ latitude: "10", longitude: 0 }), false);
  assert.equal(isValidCoordinates({ latitude: 0, longitude: 0, accuracy: -1 }), false);
  assert.equal(isValidCoordinates({ latitude: 0, longitude: 0, accuracy: 100001 }), false);
  assert.equal(isValidCoordinates(null), false);
});

test("sends the first position immediately and then only after the interval has elapsed", () => {
  assert.equal(shouldSendLocation(null, 1000), true);
  assert.equal(shouldSendLocation(1000, 1000 + LOCATION_INTERVAL_MS - 1), false);
  assert.equal(shouldSendLocation(1000, 1000 + LOCATION_INTERVAL_MS), true);
});

test("maps a browser position to the API payload and drops a missing accuracy", () => {
  assert.deepEqual(
    toLocationPayload({ coords: { latitude: -33.4, longitude: -70.6, accuracy: 12.5 } }),
    { latitude: -33.4, longitude: -70.6, accuracy: 12.5 },
  );
  assert.deepEqual(
    toLocationPayload({ coords: { latitude: -33.4, longitude: -70.6, accuracy: Number.NaN } }),
    { latitude: -33.4, longitude: -70.6 },
  );
});

test("maps geolocation error codes to Spanish messages that explain how to enable location", () => {
  assert.match(geolocationErrorMessage(1), /No puede iniciar/);
  assert.match(geolocationErrorMessage(1), /configuración de tu navegador/);
  assert.match(geolocationErrorMessage(2), /No pudimos obtener tu ubicación/);
  assert.match(geolocationErrorMessage(3), /Tardamos demasiado/);
  assert.match(geolocationErrorMessage("unavailable"), /No pudimos obtener tu ubicación/);
});

test("resolves with the payload when the browser grants the position", async () => {
  const geolocation = {
    getCurrentPosition(success) {
      success({ coords: { latitude: -33.4, longitude: -70.6, accuracy: 8 } });
    },
  };
  assert.deepEqual(await requestDriverLocation(geolocation), { latitude: -33.4, longitude: -70.6, accuracy: 8 });
});

test("rejects with the browser error code when permission is denied", async () => {
  const geolocation = {
    getCurrentPosition(_success, failure) {
      failure({ code: 1, message: "denied" });
    },
  };
  await assert.rejects(requestDriverLocation(geolocation), (error) => {
    assert.ok(error instanceof LocationError);
    assert.equal(error.code, 1);
    return true;
  });
});

test("rejects as unavailable when the browser has no geolocation or returns invalid coordinates", async () => {
  await assert.rejects(requestDriverLocation(undefined), (error) => error instanceof LocationError && error.code === "unavailable");
  const invalid = {
    getCurrentPosition(success) {
      success({ coords: { latitude: 200, longitude: 0, accuracy: 1 } });
    },
  };
  await assert.rejects(requestDriverLocation(invalid), (error) => error instanceof LocationError && error.code === "unavailable");
});

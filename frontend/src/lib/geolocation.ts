// Pure logic for sharing the driver's position: payload mapping, validation, throttling and error messages.
// The browser call is isolated in requestDriverLocation so the rest stays testable without a browser.

/** Position updates are sent about every 15 seconds while the driver's page is open. */
export const LOCATION_INTERVAL_MS = 15000;

const MAX_ACCURACY_METERS = 100000;
const POSITION_TIMEOUT_MS = 15000;

export type LocationPayload = {
  latitude: number;
  longitude: number;
  accuracy?: number;
};

export type LocationErrorCode = 1 | 2 | 3 | "unavailable";

/** A position could not be obtained. `code` is the browser's GeolocationPositionError code, or "unavailable". */
export class LocationError extends Error {
  readonly code: LocationErrorCode;

  constructor(code: LocationErrorCode) {
    super(`Location unavailable: ${code}`);
    this.name = "LocationError";
    this.code = code;
  }
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** Mirrors the backend limits: latitude -90..90, longitude -180..180, accuracy 0..100000 meters when present. */
export function isValidCoordinates(value: LocationPayload | null | undefined): boolean {
  if (!value) return false;
  const { latitude, longitude, accuracy } = value;
  if (!isFiniteNumber(latitude) || latitude < -90 || latitude > 90) return false;
  if (!isFiniteNumber(longitude) || longitude < -180 || longitude > 180) return false;
  if (accuracy === undefined) return true;
  return isFiniteNumber(accuracy) && accuracy >= 0 && accuracy <= MAX_ACCURACY_METERS;
}

type BrowserPosition = { coords: { latitude: number; longitude: number; accuracy?: number } };

/** Builds the request body from a browser position. A non-finite accuracy is omitted, not sent. */
export function toLocationPayload(position: BrowserPosition): LocationPayload {
  const { latitude, longitude, accuracy } = position.coords;
  return isFiniteNumber(accuracy) ? { latitude, longitude, accuracy } : { latitude, longitude };
}

/** Throttle: true when nothing was sent yet or the interval has elapsed since the last send. */
export function shouldSendLocation(lastSentAt: number | null, now: number, intervalMs: number = LOCATION_INTERVAL_MS): boolean {
  return lastSentAt === null || now - lastSentAt >= intervalMs;
}

/** A browser position older than this is never sent as the driver's current location. */
export const POSITION_MAX_AGE_MS = 30000;

/** True when the browser timestamp is a number, not in the future, and no older than the freshness limit. */
export function isFreshPosition(positionTimestamp: number | undefined, now: number, maxAgeMs: number = POSITION_MAX_AGE_MS): boolean {
  if (!isFiniteNumber(positionTimestamp)) return false;
  const age = now - positionTimestamp;
  return age >= 0 && age <= maxAgeMs;
}

/** True when nothing was sent yet or this position was obtained after the last sent one, so it is never resent. */
export function isNewerPosition(positionTimestamp: number, lastSentTimestamp: number | null): boolean {
  return lastSentTimestamp === null || positionTimestamp > lastSentTimestamp;
}

/** A position may be sent only when it is fresh and newer than the last sent position. */
export function shouldSendPosition(positionTimestamp: number, lastSentTimestamp: number | null, now: number): boolean {
  return isFreshPosition(positionTimestamp, now) && isNewerPosition(positionTimestamp, lastSentTimestamp);
}

const PERMISSION_DENIED_MESSAGE = "No puede iniciar el servicio sin compartir tu ubicación. Permite el acceso a la ubicación para este sitio en la configuración de tu navegador y vuelve a intentarlo.";
const POSITION_UNAVAILABLE_MESSAGE = "No pudimos obtener tu ubicación. Revisa que el GPS o la red estén activos e inténtalo nuevamente.";
const TIMEOUT_MESSAGE = "Tardamos demasiado en obtener tu ubicación. Inténtalo nuevamente.";

/** Shown while the driver's location is not being shared during an in-progress service; it stays until a fresh position arrives. */
export const SHARING_STOPPED_MESSAGE = "Tu ubicación no se está compartiendo con el cliente. Revisa que el GPS o la red estén activos y permite el acceso a la ubicación para este sitio en la configuración de tu navegador.";

export function geolocationErrorMessage(code: LocationErrorCode | number): string {
  if (code === 1) return PERMISSION_DENIED_MESSAGE;
  if (code === 3) return TIMEOUT_MESSAGE;
  return POSITION_UNAVAILABLE_MESSAGE;
}

type GeolocationSource = {
  getCurrentPosition: (
    success: (position: BrowserPosition) => void,
    failure: (error: { code: number }) => void,
    options?: PositionOptions,
  ) => void;
};

/**
 * Asks the browser for the current position once. Rejects with LocationError when the browser has no
 * geolocation, permission is denied, the position is unavailable or times out, or the coordinates are invalid.
 */
export function requestDriverLocation(geolocation: GeolocationSource | null | undefined = globalThis.navigator?.geolocation): Promise<LocationPayload> {
  if (!geolocation) return Promise.reject(new LocationError("unavailable"));
  return new Promise<LocationPayload>((resolve, reject) => {
    geolocation.getCurrentPosition(
      (position) => {
        const payload = toLocationPayload(position);
        if (isValidCoordinates(payload)) resolve(payload);
        else reject(new LocationError("unavailable"));
      },
      (error) => reject(new LocationError(error.code === 1 || error.code === 3 ? error.code : 2)),
      { enableHighAccuracy: true, timeout: POSITION_TIMEOUT_MS, maximumAge: 0 },
    );
  });
}

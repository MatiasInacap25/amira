"use client";

import { useEffect, useRef, useState } from "react";
import {
  geolocationErrorMessage,
  isValidCoordinates,
  LOCATION_INTERVAL_MS,
  type LocationPayload,
  shouldSendLocation,
  toLocationPayload,
} from "@/lib/geolocation";

const UPDATE_FAILED_MESSAGE = "No pudimos compartir tu ubicación en este momento. Se reintentará automáticamente.";

type DriverLocationSharingProps = {
  // Sends one position. Rejections are shown as a notice; the next interval tick tries again.
  sendLocation: (location: LocationPayload) => Promise<unknown>;
};

/**
 * Watches the driver's position while the service is in progress and sends the latest one about every 15 seconds.
 * Watch events only update the latest position, so the request rate is set by the interval, not by the browser.
 * Watching stops on unmount, which happens when the service leaves the in-progress state.
 */
export function DriverLocationSharing({ sendLocation }: DriverLocationSharingProps) {
  // A browser without geolocation is known before any effect runs, so the notice is the initial state.
  const [message, setMessage] = useState<string | null>(() =>
    globalThis.navigator?.geolocation ? null : geolocationErrorMessage("unavailable"),
  );
  const sendRef = useRef(sendLocation);

  useEffect(() => {
    sendRef.current = sendLocation;
  }, [sendLocation]);

  useEffect(() => {
    const geolocation = globalThis.navigator?.geolocation;
    if (!geolocation) return;

    let active = true;
    let latest: LocationPayload | null = null;
    let lastSentAt: number | null = null;
    let sending = false;

    const sendLatest = async () => {
      const now = Date.now();
      if (!latest || sending || !shouldSendLocation(lastSentAt, now)) return;
      sending = true;
      lastSentAt = now;
      try {
        await sendRef.current(latest);
        if (active) setMessage(null);
      } catch {
        if (active) setMessage(UPDATE_FAILED_MESSAGE);
      } finally {
        sending = false;
      }
    };

    const watchId = geolocation.watchPosition(
      (position) => {
        const payload = toLocationPayload(position);
        if (!isValidCoordinates(payload)) return;
        latest = payload;
        void sendLatest();
      },
      (error) => {
        if (active) setMessage(geolocationErrorMessage(error.code));
      },
      { enableHighAccuracy: true, maximumAge: 0 },
    );
    const timer = window.setInterval(() => void sendLatest(), LOCATION_INTERVAL_MS);

    return () => {
      active = false;
      geolocation.clearWatch(watchId);
      window.clearInterval(timer);
    };
  }, []);

  return (
    <div className="driver-location-sharing">
      <p className="driver-location-status">Compartiendo tu ubicación con el cliente</p>
      <p className="driver-location-warning">La ubicación solo se comparte mientras esta página permanezca abierta.</p>
      {message && <p className="account-service-form-error" role="alert">{message}</p>}
    </div>
  );
}

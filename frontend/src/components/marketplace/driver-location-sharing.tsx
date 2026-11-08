"use client";

import { useEffect, useRef, useState } from "react";
import {
  isFreshPosition,
  isValidCoordinates,
  LOCATION_INTERVAL_MS,
  type LocationPayload,
  SHARING_STOPPED_MESSAGE,
  shouldSendLocation,
  shouldSendPosition,
  toLocationPayload,
} from "@/lib/geolocation";

const UPDATE_FAILED_MESSAGE = "No pudimos compartir tu ubicación en este momento. Se reintentará automáticamente.";

type DriverLocationSharingProps = {
  // Sends one position. Rejections are shown as a notice; the next interval tick tries again.
  sendLocation: (location: LocationPayload) => Promise<unknown>;
};

/**
 * Watches the driver's position while the service is in progress and sends the latest fresh one about every 15 seconds.
 * Only positions obtained recently and not sent before are sent. A watch error stops sharing, drops the cached position,
 * and keeps a warning until a new fresh position arrives. Watching stops on unmount, when the service leaves in progress.
 */
export function DriverLocationSharing({ sendLocation }: DriverLocationSharingProps) {
  // A browser without geolocation is known before any effect runs, so the warning is the initial state.
  const [message, setMessage] = useState<string | null>(() =>
    globalThis.navigator?.geolocation ? null : SHARING_STOPPED_MESSAGE,
  );
  const sendRef = useRef(sendLocation);

  useEffect(() => {
    sendRef.current = sendLocation;
  }, [sendLocation]);

  useEffect(() => {
    const geolocation = globalThis.navigator?.geolocation;
    if (!geolocation) return;

    let active = true;
    // Cached position with its browser timestamp. Dropped on a watch error, so nothing stale is sent as current.
    let latest: { payload: LocationPayload; timestamp: number } | null = null;
    // Throttle base: the last successful send. A failed send does not reset it.
    let lastSentAt: number | null = null;
    let lastSentTimestamp: number | null = null;
    // Set by a failed send. Only the interval tick retries; watch events do not resend while it is set.
    let retryPending = false;
    let sending = false;
    let lost = false;

    const sendLatest = async (fromTick: boolean) => {
      const now = Date.now();
      if (!latest || lost || sending || !shouldSendLocation(lastSentAt, now)) return;
      if (!fromTick && retryPending) return;
      if (!shouldSendPosition(latest.timestamp, lastSentTimestamp, now)) return;
      const { payload, timestamp } = latest;
      sending = true;
      try {
        await sendRef.current(payload);
        lastSentAt = Date.now();
        lastSentTimestamp = timestamp;
        retryPending = false;
        if (active && !lost) setMessage(null);
      } catch {
        retryPending = true;
        if (active && !lost) setMessage(UPDATE_FAILED_MESSAGE);
      } finally {
        sending = false;
      }
    };

    const watchId = geolocation.watchPosition(
      (position) => {
        const payload = toLocationPayload(position);
        if (!isValidCoordinates(payload) || !isFreshPosition(position.timestamp, Date.now())) return;
        lost = false;
        latest = { payload, timestamp: position.timestamp };
        if (active) setMessage(null);
        void sendLatest(false);
      },
      () => {
        lost = true;
        latest = null;
        if (active) setMessage(SHARING_STOPPED_MESSAGE);
      },
      { enableHighAccuracy: true, maximumAge: 0 },
    );
    const timer = window.setInterval(() => void sendLatest(true), LOCATION_INTERVAL_MS);

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

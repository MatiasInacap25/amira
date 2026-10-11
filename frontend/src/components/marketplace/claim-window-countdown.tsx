"use client";

import { useEffect, useState } from "react";
import { type ClaimWindow, claimWindowAt, formatClaimCountdown } from "@/lib/service-status";

const CLOCK_INTERVAL_MS = 60_000;

/**
 * Reads the claim window against the client clock, refreshed once a minute.
 * The clock starts after mount, so the server render never depends on the current time.
 */
export function useClaimWindowClock(deadlineAt: string | null): ClaimWindow {
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    const tick = () => setNow(Date.now());
    tick();
    const intervalId = window.setInterval(tick, CLOCK_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, []);

  return claimWindowAt(deadlineAt, now);
}

type Props = {
  deadlineLabel: string;
  claimWindow: ClaimWindow;
};

/**
 * The state sentence is the only live region, so screen readers announce the switch to "expired" once.
 * The minutes change every minute and are kept outside the live region to avoid repeated announcements.
 */
export function ClaimWindowCountdown({ deadlineLabel, claimWindow }: Props) {
  const { expired, minutesLeft } = claimWindow;
  return (
    <div className="account-service-window">
      <p className="account-service-hint">Plazo para reclamar: {deadlineLabel}</p>
      <p aria-live="polite" className={`account-service-window-state${expired ? " account-service-window-state-expired" : ""}`} role="status">
        {expired ? "Plazo vencido. El pago se libera sin reclamo." : "Ventana de reclamo abierta."}
      </p>
      {!expired && (
        <p className="account-service-countdown">
          {minutesLeft === null ? "Calculando tiempo restante…" : `Quedan ${formatClaimCountdown(minutesLeft)}`}
        </p>
      )}
    </div>
  );
}

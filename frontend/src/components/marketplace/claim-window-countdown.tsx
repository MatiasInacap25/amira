"use client";

import { useEffect, useState } from "react";
import { claimWindowAt, formatClaimCountdown } from "@/lib/service-status";

const CLOCK_INTERVAL_MS = 60_000;

/**
 * What the customer can see of the claim window. "pending" lasts until the client clock is known, so neither an
 * open nor an expired window is shown during the server render. "unavailable" means the service has no deadline.
 */
export type ClaimWindowView =
  | { status: "unavailable" }
  | { status: "pending" }
  | { status: "open"; minutesLeft: number | null }
  | { status: "expired" };

/**
 * Reads the claim window against the client clock, refreshed once a minute.
 * The clock starts after mount, so the server render never depends on the current time.
 */
export function useClaimWindowClock(deadlineAt: string | null): ClaimWindowView {
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    const tick = () => setNow(Date.now());
    tick();
    const intervalId = window.setInterval(tick, CLOCK_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, []);

  if (deadlineAt === null) return { status: "unavailable" };
  if (now === null) return { status: "pending" };
  const remaining = claimWindowAt(deadlineAt, now);
  if (remaining.expired) return { status: "expired" };
  return { status: "open", minutesLeft: remaining.minutesLeft };
}

type Props = {
  deadlineLabel: string;
  claimWindow: ClaimWindowView;
};

/**
 * The state sentence is the only live region, so screen readers announce the switch to "expired" once.
 * The minutes change every minute and are kept outside the live region to avoid repeated announcements.
 */
export function ClaimWindowCountdown({ deadlineLabel, claimWindow }: Props) {
  if (claimWindow.status === "unavailable") {
    return (
      <div className="account-service-window">
        <p className="account-service-hint">El plazo para reclamar no está disponible.</p>
      </div>
    );
  }

  const expired = claimWindow.status === "expired";
  const stateMessage = {
    pending: "Calculando el plazo para reclamar…",
    open: "Ventana de reclamo abierta.",
    expired: "Plazo vencido. El pago se libera sin reclamo.",
    unavailable: "",
  }[claimWindow.status];

  return (
    <div className="account-service-window">
      <p className="account-service-hint">Plazo para reclamar: {deadlineLabel}</p>
      <p aria-live="polite" className={`account-service-window-state${expired ? " account-service-window-state-expired" : ""}`} role="status">
        {stateMessage}
      </p>
      {claimWindow.status === "open" && (
        <p className="account-service-countdown">
          {claimWindow.minutesLeft === null ? "Calculando tiempo restante…" : `Quedan ${formatClaimCountdown(claimWindow.minutesLeft)}`}
        </p>
      )}
    </div>
  );
}
